"""
Гибридная классификация наименований по группам.

Логика:
  1. Локальные правила (keyword -> группа). Первое совпадение выигрывает.
  2. Если ни одно правило не сработало -> запрос в polza.ai (OpenAI-совместимый API).
     LLM возвращает {"группа", "ключевое_слово"}.
  3. Новое правило (ключевое_слово -> группа) сохраняется в learned_rules.json,
     чтобы при следующей встрече похожего наименования к API не обращаться.

Файлы .env и task_*.xlsx ищутся в папке скрипта и в родительской папке.

Запуск (из корня проекта):
  python blok_2/classify_hybrid.py                 # обработать task_1.xlsx
  python blok_2/classify_hybrid.py task_2.xlsx     # другой файл
  python blok_2/classify_hybrid.py --test-llm 5    # прогнать 5 строк через LLM (проверка связи)
"""
import sys, io, os, json, re, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import requests


_dns_installed = False


def install_dns_fallback():
    """Если системный DNS не резолвит *.polza.ai — узнаём IP через DNS-over-HTTPS.
    Правит резолвинг только внутри процесса, систему не трогает."""
    global _dns_installed
    if _dns_installed:
        return
    _dns_installed = True
    _orig = socket.getaddrinfo
    cache = {}

    def resolve_doh(host):
        if host in cache:
            return cache[host]
        r = requests.get('https://dns.google/resolve',
                         params={'name': host, 'type': 'A'}, timeout=15)
        ip = next((a['data'] for a in r.json().get('Answer', []) if a.get('type') == 1), None)
        cache[host] = ip
        return ip

    def patched(host, *args, **kwargs):
        try:
            return _orig(host, *args, **kwargs)
        except socket.gaierror:
            if host and str(host).endswith('polza.ai'):
                ip = resolve_doh(host)
                if ip:
                    return _orig(ip, *args, **kwargs)  # IP числовой — DNS не нужен
            raise

    socket.getaddrinfo = patched

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
LEARNED_PATH = os.path.join(HERE, 'learned_rules.json')

CATEGORIES = ['коврик', 'парктроник', 'сигнализация', 'защита', 'камера заднего вида']
NAME_COL = 'наименование'
GROUP_COL = 'группа'

# --- Базовые правила: (группа, [ключевые слова]). Порядок = приоритет. ---
BASE_RULES = [
    ('камера заднего вида', ['ЗАДНЕГО ВИДА', 'КАМЕРА З/В', 'КАМЕР']),
    ('парктроник',          ['ПАРКОВ', 'PARK MASTER', 'ПАРКТРОН', 'ДАТЧИК']),
    ('защита',              ['ЗАЩИТ', 'ЗАЩ', 'КАРТЕРА', 'РЕДУКТОРА']),
    ('коврик',              ['КОВР', 'КОВЁР', 'КОВЕР', 'КОВЫ']),
    ('сигнализация',        ['СИГНАЛ', 'STARLINE', 'СИРЕНА', 'БЕСКЛЮЧ', 'ЦЕПИ ПИТАНИЯ',
                             'ДИСТАНЦИОН', 'ДИАГНОСТИЧ', 'ПРОКЛАДКА ПРОВОДОВ', 'ПРОВОДОВ',
                             'ALFA COMFORT', 'ЗАПУСКОВ', 'GSM', 'GPS', 'CAN', 'МОДУЛ']),
]


def find_file(name):
    """Найти файл в папке скрипта или в родительской папке."""
    for base in (os.getcwd(), HERE, PARENT):
        p = name if os.path.isabs(name) else os.path.join(base, name)
        if os.path.exists(p):
            return p
    return name  # вернём как есть — вызов упадёт с понятной ошибкой


def load_env():
    env = {}
    for cand in (os.path.join(HERE, '.env'), os.path.join(PARENT, '.env')):
        if os.path.exists(cand):
            with open(cand, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for k in ('POLZA_API_KEY', 'POLZA_BASE_URL', 'POLZA_MODEL'):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def load_learned():
    if os.path.exists(LEARNED_PATH):
        with open(LEARNED_PATH, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_learned(rules):
    with open(LEARNED_PATH, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def classify_local(name, learned):
    """Локальная классификация: базовые правила, затем выученные. None если не нашлось."""
    if pd.isna(name):
        return None
    t = str(name).upper()
    for group, keys in BASE_RULES:
        if any(k in t for k in keys):
            return group
    for r in learned:
        if r['keyword'] in t:
            return r['группа']
    return None


def polza_classify(name, env):
    """Запрос в polza.ai. Возвращает (группа, ключевое_слово) или (None, None)."""
    key = env.get('POLZA_API_KEY')
    if not key:
        return None, None
    install_dns_fallback()
    base = env.get('POLZA_BASE_URL', 'https://api.polza.ai/api/v1').rstrip('/')
    model = env.get('POLZA_MODEL', 'openai/gpt-4o-mini')

    cats = ', '.join(CATEGORIES)
    system = (
        "Ты классификатор наименований услуг/товаров для автомобилей. "
        f"Отнеси наименование ровно к ОДНОЙ из категорий: {cats}. "
        "Также выдели короткое ключевое слово (в ВЕРХНЕМ регистре), которое является "
        "подстрокой наименования и однозначно указывает на эту категорию. "
        'Ответь строго JSON без пояснений: {"группа": "...", "ключевое_слово": "..."}'
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Наименование: {name}"},
        ],
        "temperature": 0,
    }
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [polza.ai ошибка] {e}")
        return None, None

    m = re.search(r'\{.*\}', content, re.DOTALL)
    if not m:
        print(f"  [polza.ai] не удалось распарсить ответ: {content!r}")
        return None, None
    try:
        data = json.loads(m.group(0))
    except Exception:
        print(f"  [polza.ai] невалидный JSON: {content!r}")
        return None, None

    group = str(data.get('группа', '')).strip().lower()
    kw = str(data.get('ключевое_слово', '')).strip().upper()

    if group not in CATEGORIES:
        print(f"  [polza.ai] группа вне списка: {group!r}")
        return None, None
    # ключевое слово должно быть реальной подстрокой; иначе фолбэк на всё наименование
    if len(kw) < 3 or kw not in str(name).upper():
        kw = str(name).upper()
    return group, kw


def add_learned_rule(learned, keyword, group):
    for r in learned:
        if r['keyword'] == keyword:
            return False
    learned.append({'keyword': keyword, 'группа': group})
    save_learned(learned)
    return True


def process_file(path, env, learned):
    src = find_file(path)
    df = pd.read_excel(src)
    if NAME_COL not in df.columns:
        print(f"В файле нет столбца '{NAME_COL}'. Столбцы: {list(df.columns)}")
        return

    api_calls = 0
    new_rules = 0
    result = []
    seen = {}
    for name in df[NAME_COL]:
        g = classify_local(name, learned)
        if g is None:
            keyname = str(name).upper()
            if keyname in seen:
                g = seen[keyname]
            else:
                group, kw = polza_classify(name, env)
                api_calls += 1
                if group:
                    if add_learned_rule(learned, kw, group):
                        new_rules += 1
                        print(f"  + правило: '{kw}' -> {group}   (из '{name}')")
                    g = group
                else:
                    g = 'не определено'
                seen[keyname] = g
        result.append(g)

    df[GROUP_COL] = result
    #out = os.path.splitext(src)[0] + '_result.xlsx'
    df.to_excel(r'D:\Yaroslav\python_script\ringo_task\blok_2\task_1_result.xlsx', index=False)

    print('\nРаспределение по группам:')
    print(df[GROUP_COL].value_counts(dropna=False).to_string())
    print(f'\nОбращений к polza.ai: {api_calls}, новых правил выучено: {new_rules}')
    #print(f'Сохранено: {out}')
    undef = df.loc[df[GROUP_COL] == 'не определено', NAME_COL].unique()
    if len(undef):
        print(f'НЕ определено ({len(undef)}): не задан ключ .env или ошибка API:')
        for u in undef:
            print('  ', u)


def test_llm(n, env, learned):
    """Прогнать n уникальных наименований из task_1 напрямую через LLM (проверка связи)."""
    df = pd.read_excel(find_file('task_1.xlsx'))
    names = df[NAME_COL].dropna().unique()[:n]
    print(f'Проверка polza.ai на {len(names)} наименованиях:')
    for name in names:
        group, kw = polza_classify(name, env)
        if group:
            add_learned_rule(learned, kw, group)
            print(f"  '{name}'\n     -> {group}  (ключ: '{kw}')")
        else:
            print(f"  '{name}'\n     -> не удалось (проверь .env)")


if __name__ == '__main__':
    env = load_env()
    learned = load_learned()

    args = sys.argv[1:]
    if args and args[0] == '--test-llm':
        n = int(args[1]) if len(args) > 1 else 3
        test_llm(n, env, learned)
    else:
        src = args[0] if args else 'task_1.xlsx'
        if not env.get('POLZA_API_KEY'):
            print('[!] POLZA_API_KEY не задан в .env — фолбэк к polza.ai отключён, '
                  'нераспознанные строки получат "не определено".\n')
        process_file(src, env, learned)
