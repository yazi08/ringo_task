"""
Геокодинг адресов клиентов (Минск) через Nominatim (OpenStreetMap).
Результат кэшируется в geocoded.csv: повторный запуск догеокодирует только новые адреса.
Пауза 1.1 сек между запросами — по правилам использования Nominatim.
"""
import sys, io, os, csv, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, 'geocoded.csv')
UA = 'ringo-client-geo/1.0 (educational task)'

# Приблизительный bbox Минска — для отсева выбросов за городом
MINSK_BBOX = (53.80, 54.05, 27.35, 27.80)  # lat_min, lat_max, lon_min, lon_max


def find_src():
    for base in (os.getcwd(), HERE, PARENT):
        p = os.path.join(base, 'task_4.xlsx')
        if os.path.exists(p):
            return p
    return 'task_4.xlsx'


def load_cache():
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                cache[row['Адрес']] = (row['lat'], row['lon'])
    return cache


def geocode(addr):
    try:
        r = requests.get('https://nominatim.openstreetmap.org/search',
                         params={'q': f'{addr}, Минск, Беларусь', 'format': 'json',
                                 'limit': 1, 'countrycodes': 'by'},
                         headers={'User-Agent': UA}, timeout=25)
        r.raise_for_status()
        d = r.json()
        if d:
            lat, lon = float(d[0]['lat']), float(d[0]['lon'])
            la0, la1, lo0, lo1 = MINSK_BBOX
            if la0 <= lat <= la1 and lo0 <= lon <= lo1:
                return lat, lon
    except Exception as e:
        print(f'  ошибка [{addr}]: {e}')
    return '', ''


def main():
    df = pd.read_excel(find_src())
    addresses = df['Адрес'].dropna().unique().tolist()
    cache = load_cache()

    new_file = not os.path.exists(CACHE)
    f = open(CACHE, 'a', encoding='utf-8', newline='')
    w = csv.writer(f)
    if new_file:
        w.writerow(['Адрес', 'lat', 'lon'])

    todo = [a for a in addresses if a not in cache]
    print(f'Всего уникальных адресов: {len(addresses)}, в кэше: {len(cache)}, к геокодингу: {len(todo)}')
    for i, addr in enumerate(todo, 1):
        lat, lon = geocode(addr)
        w.writerow([addr, lat, lon]); f.flush()
        cache[addr] = (lat, lon)
        if i % 25 == 0:
            print(f'  {i}/{len(todo)} ...')
        time.sleep(1.1)
    f.close()

    ok = sum(1 for v in cache.values() if v[0] != '')
    print(f'Готово. Успешно: {ok}/{len(cache)} ({ok/len(cache)*100:.0f}%). '
          f'Не найдено: {len(cache)-ok}. Файл: {CACHE}')


if __name__ == '__main__':
    main()
