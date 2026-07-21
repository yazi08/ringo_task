# -*- coding: utf-8 -*-
"""Генерация PNG-карт (точки + плотность) с подложкой OSM для отчёта."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import plotly.express as px

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
IMG = os.path.join(HERE, 'img')

geo = pd.read_csv(os.path.join(BASE, 'blok_4', 'geocoded.csv')).dropna(subset=['lat', 'lon'])
geo['lat'] = geo['lat'].astype(float)
geo['lon'] = geo['lon'].astype(float)
t4 = pd.read_excel(os.path.join(BASE, 'task_4.xlsx'))
pts = t4.merge(geo, on='Адрес', how='inner')

# Карта точек
fig = px.scatter_map(pts, lat='lat', lon='lon', zoom=10, height=700, width=950,
                     map_style='open-street-map')
fig.update_traces(marker=dict(size=7, color='red', opacity=0.75))
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
fig.write_image(os.path.join(IMG, 'b5_map.png'), scale=1.5)

# Тепловая карта плотности
figh = px.density_map(pts, lat='lat', lon='lon', radius=14, zoom=10,
                      height=700, width=950, map_style='open-street-map')
figh.update_layout(margin=dict(l=0, r=0, t=0, b=0))
figh.write_image(os.path.join(IMG, 'b5_heat.png'), scale=1.5)

print('Карты сохранены: b5_map.png, b5_heat.png')
