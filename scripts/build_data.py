"""
Converts input_files/datacenters.csv into web/data.js.

The output file assigns a GeoJSON FeatureCollection to window.DATACENTER_GEOJSON
so it can be used directly by app.js without any runtime CSV fetch.

Run from the project root:
    python3 scripts/build_data.py
"""

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, 'input_files', 'datacenters.csv')
OUT_PATH = os.path.join(ROOT, 'web', 'data.js')

features = []
with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            lat = float(row['Latitude'])
            lng = float(row['Longitude'])
        except (ValueError, KeyError):
            continue
        features.append({
            'type': 'Feature',
            'id': int(row['_id']),
            'geometry': {
                'type': 'Point',
                'coordinates': [lng, lat]
            },
            'properties': {k: v for k, v in row.items()}
        })

geojson = {'type': 'FeatureCollection', 'features': features}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write('window.DATACENTER_GEOJSON=')
    json.dump(geojson, f, separators=(',', ':'))
    f.write(';\n')

print(f'build_data: wrote {len(features)} datacenters to web/data.js')
