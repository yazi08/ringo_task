"""Догеокодинг неудачных адресов с раскрытием сокращений. Обновляет geocoded.csv на месте."""
import sys, io, os, csv, time, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'geocoded.csv')
UA = 'ringo-client-geo/1.0 (educational task)'
MINSK_BBOX = (53.80, 54.05, 27.35, 27.80)

REPL = {r'\bпр-т\.?': 'проспект', r'\bпр-д\.?': 'проезд', r'\bпер\.?': 'переулок',
        r'\bул\.?': 'улица', r'\bтракт\b': 'тракт', r'\bд\.\s*': ''}


def clean(addr):
    s = addr
    for pat, rep in REPL.items():
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    s = re.sub(r'\s+', ' ', s).strip().strip(',')
    return s


def geocode(q):
    try:
        r = requests.get('https://nominatim.openstreetmap.org/search',
                         params={'q': f'{q}, Минск, Беларусь', 'format': 'json',
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
        print(f'  ошибка [{q}]: {e}')
    return '', ''


geo = pd.read_csv(CACHE, dtype=str)
failed = geo[geo['lat'].isna() | (geo['lat'] == '')]
print(f'Неудачных адресов: {len(failed)}. Повторный проход с раскрытием сокращений...')

fixed = 0
for i, addr in enumerate(failed['Адрес'].tolist(), 1):
    q = clean(addr)
    if q == addr:
        # всё равно пробуем — вдруг помогут countrycodes
        pass
    lat, lon = geocode(q)
    if lat != '':
        geo.loc[geo['Адрес'] == addr, ['lat', 'lon']] = [str(lat), str(lon)]
        fixed += 1
    if i % 25 == 0:
        print(f'  {i}/{len(failed)} ... починено {fixed}')
    time.sleep(1.1)

geo.to_csv(CACHE, index=False)
ok = geo['lat'].replace('', pd.NA).notna().sum()
print(f'Готово. Дополнительно найдено: {fixed}. Итого с координатами: {ok}/{len(geo)} '
      f'({ok/len(geo)*100:.0f}%).')
