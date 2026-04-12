"""
Converts input_files/datacenters.csv into two generated files:

  web/data.js
    Loaded by the browser. Contains only coordinates + IDs — the minimum
    needed to render map markers. No metadata is included.

  functions/datacenter-data.js
    Required by the Netlify Function. Contains the full record for every
    datacenter, keyed by ID. This file is never served as a static asset.

Run from the project root:
    python3 scripts/build_data.py
"""

import csv
import json
import os

ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH     = os.path.join(ROOT, 'input_files', 'datacenters.csv')
WEB_OUT      = os.path.join(ROOT, 'web', 'data.js')
FUNC_OUT     = os.path.join(ROOT, 'functions', 'datacenter-data.js')

features = []
lookup   = {}

with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            lat = float(row['Latitude'])
            lng = float(row['Longitude'])
        except (ValueError, KeyError):
            continue

        _id = int(row['_id'])
        features.append({
            'type': 'Feature',
            'id': _id,
            'geometry': {'type': 'Point', 'coordinates': [lng, lat]},
            'properties': {}          # no metadata in the browser payload
        })
        lookup[_id] = {k: v for k, v in row.items()}

# ── web/data.js — coordinates only ───────────────────────────────────────────
geojson = {'type': 'FeatureCollection', 'features': features}
with open(WEB_OUT, 'w', encoding='utf-8') as f:
    f.write('window.DATACENTER_GEOJSON=')
    json.dump(geojson, f, separators=(',', ':'))
    f.write(';\n')

print(f'build_data: wrote {len(features)} coordinates to web/data.js')

# ── functions/datacenter-data.js — full records ───────────────────────────────
with open(FUNC_OUT, 'w', encoding='utf-8') as f:
    f.write('module.exports=')
    json.dump(lookup, f, separators=(',', ':'))
    f.write(';\n')

print(f'build_data: wrote {len(lookup)} full records to functions/datacenter-data.js')
