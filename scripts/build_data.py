"""
Builds the data files consumed by the web app and Netlify Function.

Outputs:

  web/data.js
    Loaded by the browser. Contains only coordinates + IDs — the minimum
    needed to render map markers. No metadata is included.

  functions/datacenter-data.js
    Required by the Netlify Function. Contains per-datacenter metadata plus
    the nearest USGS streamflow gage, and (keyed separately) the RDC drought
    forecast time series per gage. Never served as a static asset.

Forecast data is fetched live from the USGS River DroughtCast CDN (conditions
CSV files for weeks 0–13).  If the CDN is unreachable, falls back to a local
parquet snapshot in input_files/.

Caches NWIS site metadata under .build-cache/stations.json so repeat builds
don't re-fetch.

Run from the project root:
    python3 scripts/build_data.py
"""

import csv
import glob
import io
import json
import os
import sys
import urllib.request
import urllib.error

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree


ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH    = os.path.join(ROOT, 'input_files', 'datacenters.csv')
PARQUET_GLOB = os.path.join(ROOT, 'input_files', 'USGS_streamflow_drought_forecasts_*.parquet')
WEB_OUT     = os.path.join(ROOT, 'web', 'data.js')
FUNC_OUT    = os.path.join(ROOT, 'functions', 'datacenter-data.js')
CACHE_DIR   = os.path.join(ROOT, '.build-cache')
STATIONS_CACHE = os.path.join(CACHE_DIR, 'stations.json')

NWIS_SITE_URL = 'https://waterservices.usgs.gov/nwis/site/'
BATCH_SIZE  = 200
EARTH_RADIUS_KM = 6371.0

RDC_CDN_BASE = (
    'https://dfi09q69oy2jm.cloudfront.net'
    '/visualizations/streamflow-drought-forecasts/conditions'
)
RDC_WEEKS = range(0, 14)  # w0 = observed, w1..w13 = forecast


# ── Datacenter loading ────────────────────────────────────────────────────────

def load_datacenters():
    rows = []
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                row['_lat'] = float(row['Latitude'])
                row['_lng'] = float(row['Longitude'])
                row['_id']  = int(row['_id'])
            except (ValueError, KeyError):
                continue
            rows.append(row)
    return rows


# ── Forecast loading ──────────────────────────────────────────────────────────

def fetch_forecasts_from_cdn():
    """Fetch the 14 weekly CSVs (w0–w13) from the USGS RDC CDN.
    Returns a DataFrame with columns [StaID, forecast_date, median_pct]."""
    frames = []
    for w in RDC_WEEKS:
        url = f'{RDC_CDN_BASE}/conditions_w{w}.csv'
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                text = resp.read().decode('utf-8')
            df = pd.read_csv(io.StringIO(text))
            df.columns = df.columns.str.strip()
            df = df.rename(columns={'dt': 'forecast_date', 'pd': 'median_pct'})
            df['forecast_week'] = w
            frames.append(df)
        except Exception as e:
            print(f'  CDN w{w}: failed ({e})', file=sys.stderr)
    if not frames:
        return None
    combined = pd.concat(frames, ignore_index=True)
    combined['StaID'] = combined['StaID'].astype(str).str.zfill(8)
    combined['forecast_date'] = pd.to_datetime(combined['forecast_date']).dt.strftime('%Y-%m-%d')
    return combined


def load_forecasts_from_parquet():
    """Fallback: load from the most recent local parquet snapshot."""
    matches = sorted(glob.glob(PARQUET_GLOB))
    if not matches:
        return None
    path = matches[-1]
    print(f'build_data: (fallback) reading forecasts from {os.path.basename(path)}')
    df = pd.read_parquet(path)
    df['StaID'] = df['StaID'].astype(str).str.zfill(8)
    df['forecast_date'] = pd.to_datetime(df['forecast_date']).dt.strftime('%Y-%m-%d')
    return df


def load_forecasts():
    """Try USGS CDN first; fall back to local parquet."""
    print('build_data: fetching forecasts from USGS RDC CDN (w0–w13)...')
    df = fetch_forecasts_from_cdn()
    if df is not None and len(df) > 0:
        print(f'build_data: CDN returned {len(df):,} rows, '
              f'{df["StaID"].nunique():,} stations')
        return df

    print('build_data: CDN unavailable, trying local parquet fallback')
    df = load_forecasts_from_parquet()
    if df is not None and len(df) > 0:
        print(f'build_data: parquet returned {len(df):,} rows')
        return df

    print('build_data: no forecast data available', file=sys.stderr)
    return pd.DataFrame(columns=['StaID', 'forecast_date', 'median_pct'])


# ── NWIS station metadata ────────────────────────────────────────────────────

def fetch_station_metadata(station_ids):
    """Return {station_id: {name, lat, lng}}. Uses .build-cache to avoid refetching."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = {}
    if os.path.exists(STATIONS_CACHE):
        with open(STATIONS_CACHE, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    missing = [sid for sid in station_ids if sid not in cache]
    if missing:
        print(f'build_data: fetching metadata for {len(missing):,} new stations from NWIS')
        for i in range(0, len(missing), BATCH_SIZE):
            batch = missing[i:i + BATCH_SIZE]
            url = f'{NWIS_SITE_URL}?sites={",".join(batch)}&format=rdb&siteOutput=expanded'
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    text = resp.read().decode('utf-8', errors='replace')
            except urllib.error.URLError as e:
                print(f'  batch {i}: request failed: {e}', file=sys.stderr)
                continue

            seen_this_batch = set()
            for line in text.splitlines():
                if not line.startswith('USGS\t'):
                    continue
                parts = line.split('\t')
                if len(parts) < 8:
                    continue
                _, site_no, station_nm, _, _, _, dec_lat, dec_lng = parts[:8]
                try:
                    cache[site_no] = {
                        'name': station_nm,
                        'lat': float(dec_lat),
                        'lng': float(dec_lng),
                    }
                    seen_this_batch.add(site_no)
                except ValueError:
                    continue

            for sid in batch:
                if sid not in seen_this_batch and sid not in cache:
                    cache[sid] = None

            print(f'  batch {i:>5}..{i + len(batch):>5}: +{len(seen_this_batch)}')

        with open(STATIONS_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, separators=(',', ':'))

    return {sid: cache[sid] for sid in station_ids if cache.get(sid) is not None}


# ── Forecast index ────────────────────────────────────────────────────────────

def build_forecast_index(df_forecasts, valid_station_ids):
    """Group forecasts by station into compact records.
    If the DataFrame has CIs (parquet source), include them; otherwise null."""
    df = df_forecasts[df_forecasts['StaID'].isin(valid_station_ids)].copy()

    has_ci = 'pred_interv_05_pct' in df.columns and 'pred_interv_95_pct' in df.columns

    if has_ci:
        df = (
            df.groupby(['StaID', 'forecast_date'], as_index=False)
              .agg(median_pct=('median_pct', 'mean'),
                   p05=('pred_interv_05_pct', 'mean'),
                   p95=('pred_interv_95_pct', 'mean'))
              .sort_values(['StaID', 'forecast_date'])
        )
    else:
        df = (
            df.groupby(['StaID', 'forecast_date'], as_index=False)
              .agg(median_pct=('median_pct', 'mean'))
              .sort_values(['StaID', 'forecast_date'])
        )
        df['p05'] = None
        df['p95'] = None

    out = {}
    for sta, g in df.groupby('StaID', sort=False):
        out[sta] = [
            {
                'date': r.forecast_date,
                'median_pct': None if pd.isna(r.median_pct) else round(float(r.median_pct), 2),
                'p05': None if pd.isna(r.p05) else round(float(r.p05), 2),
                'p95': None if pd.isna(r.p95) else round(float(r.p95), 2),
            }
            for r in g.itertuples(index=False)
        ]
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    datacenters = load_datacenters()
    print(f'build_data: loaded {len(datacenters):,} datacenters')

    df_forecasts = load_forecasts()
    station_ids = sorted(df_forecasts['StaID'].unique().tolist())
    print(f'build_data: {len(station_ids):,} unique forecast stations')

    station_meta = fetch_station_metadata(station_ids)
    print(f'build_data: resolved metadata for {len(station_meta):,} stations')

    if not station_meta:
        print('build_data: no station metadata — gage assignment skipped', file=sys.stderr)
        assigned = {}
    else:
        sids = list(station_meta.keys())
        sta_rad = np.deg2rad(np.array([[station_meta[s]['lat'], station_meta[s]['lng']] for s in sids]))
        tree = BallTree(sta_rad, metric='haversine')

        dc_rad = np.deg2rad(np.array([[d['_lat'], d['_lng']] for d in datacenters]))
        dist_rad, idx = tree.query(dc_rad, k=1)

        assigned = {}
        for i, dc in enumerate(datacenters):
            sid = sids[int(idx[i][0])]
            assigned[dc['_id']] = {
                'id': sid,
                'name': station_meta[sid]['name'],
                'lat': station_meta[sid]['lat'],
                'lng': station_meta[sid]['lng'],
                'distance_km': round(float(dist_rad[i][0] * EARTH_RADIUS_KM), 2),
            }

    forecasts_by_station = build_forecast_index(df_forecasts, set(station_meta.keys()))
    print(f'build_data: forecast series for {len(forecasts_by_station):,} stations')

    # ── web/data.js — coordinates only ────────────────────────────────────────
    features = [
        {
            'type': 'Feature',
            'id': dc['_id'],
            'geometry': {'type': 'Point', 'coordinates': [dc['_lng'], dc['_lat']]},
            'properties': {},
        }
        for dc in datacenters
    ]
    geojson = {'type': 'FeatureCollection', 'features': features}
    with open(WEB_OUT, 'w', encoding='utf-8') as f:
        f.write('window.DATACENTER_GEOJSON=')
        json.dump(geojson, f, separators=(',', ':'))
        f.write(';\n')
    print(f'build_data: wrote {len(features):,} coordinates to web/data.js')

    # ── functions/datacenter-data.js — full records + forecasts ──────────────
    drop_keys = {'_lat', '_lng', '_id', 'Latitude', 'Longitude'}
    dc_records = {}
    for dc in datacenters:
        rec = {k: v for k, v in dc.items() if k not in drop_keys and v not in (None, '')}
        rec['Latitude'] = dc['_lat']
        rec['Longitude'] = dc['_lng']
        if dc['_id'] in assigned:
            rec['gage'] = assigned[dc['_id']]
        dc_records[str(dc['_id'])] = rec

    payload = {
        'datacenters': dc_records,
        'forecasts': forecasts_by_station,
    }
    with open(FUNC_OUT, 'w', encoding='utf-8') as f:
        f.write('module.exports=')
        json.dump(payload, f, separators=(',', ':'))
        f.write(';\n')
    size_mb = os.path.getsize(FUNC_OUT) / 1e6
    print(f'build_data: wrote {len(dc_records):,} datacenters + {len(forecasts_by_station):,} '
          f'forecast series to functions/datacenter-data.js ({size_mb:.2f} MB)')


if __name__ == '__main__':
    main()
