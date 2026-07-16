import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)


def find_file(name):
    for base in (os.getcwd(), HERE, PARENT):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return name


SRC = find_file('task_1.xlsx')
OUT = os.path.splitext(SRC)[0] + '_result.xlsx'

# Правила: (группа, [ключевые слова]). Порядок = приоритет (сверху вниз).
RULES = [
    ('камера заднего вида', ['ЗАДНЕГО ВИДА', 'КАМЕРА З/В', 'КАМЕР']),
    ('парктроник',          ['ПАРКОВ', 'PARK MASTER', 'ПАРКТРОН', 'ДАТЧИК']),
    ('защита',              ['ЗАЩИТ', 'ЗАЩ', 'КАРТЕРА', 'РЕДУКТОРА']),
    ('коврик',              ['КОВР', 'КОВЁР', 'КОВЕР', 'КОВЫ']),
    ('сигнализация',        ['СИГНАЛ', 'STARLINE', 'СИРЕНА', 'БЕСКЛЮЧ', 'ЦЕПИ ПИТАНИЯ',
                             'ДИСТАНЦИОН', 'ДИАГНОСТИЧ', 'ПРОКЛАДКА ПРОВОДОВ', 'ПРОВОДОВ',
                             'ALFA COMFORT', 'ЗАПУСКОВ', 'GSM', 'GPS', 'CAN', 'МОДУЛ']),
]


def classify(name):
    if pd.isna(name):
        return None
    t = str(name).upper()
    for group, keys in RULES:
        if any(k in t for k in keys):
            return group
    return 'не определено'


df = pd.read_excel(SRC)
df['группа'] = df['наименование'].apply(classify)

print('Распределение по группам:')
print(df['группа'].value_counts(dropna=False).to_string())
print()

undef = df[df['группа'] == 'не определено']['наименование'].unique()
print('НЕ определено (уникальные):', len(undef))
for u in undef:
    print('  ', u)
print()

etalon = pd.read_excel(SRC)
mask = etalon['группа'].notna()
chk = etalon.loc[mask, ['наименование', 'группа']].copy()
chk['предсказано'] = chk['наименование'].apply(classify)
chk['совпало'] = chk['группа'].astype(str).str.strip() == chk['предсказано']
print('Сверка с эталонными строками:')
print(chk.to_string(index=False))
if len(chk):
    print('Точность на эталоне:', chk['совпало'].mean())

df.to_excel(OUT, index=False)
print('\nСохранено в', OUT)
