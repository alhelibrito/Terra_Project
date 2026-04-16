"""
Local development server.

Serves static files from web/ and emulates the Netlify Function at
/.netlify/functions/datacenter?id=N. The streamflow logic mirrors
functions/datacenter.js so the UI can be tested without Node or Netlify CLI.

Run from the project root:
    python3 scripts/dev_server.py
"""

import http.server
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR   = os.path.join(ROOT, 'web')
DATA_FILE = os.path.join(ROOT, 'functions', 'datacenter-data.js')
PORT      = 8765

USGS_DV_URL   = 'https://waterservices.usgs.gov/nwis/dv/'
USGS_STAT_URL = 'https://waterservices.usgs.gov/nwis/stat/'
STATS_TTL_S   = 30 * 24 * 60 * 60  # 30 days


def load_bundle():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    content = re.sub(r'^module\.exports=', '', content).rstrip(';')
    return json.loads(content)


BUNDLE      = load_bundle()
DATACENTERS = BUNDLE['datacenters']
FORECASTS   = BUNDLE['forecasts']

STATS_CACHE = {}  # gage_id -> (entry, fetched_at)


def fetch_latest_daily_value(gage_id):
    url = (
        f'{USGS_DV_URL}?sites={gage_id}&parameterCd=00060'
        f'&format=json&period=P14D'
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    series = (
        data.get('value', {})
        .get('timeSeries', [{}])[0]
        .get('values', [{}])[0]
        .get('value', [])
    )
    for v in reversed(series):
        try:
            cfs = float(v['value'])
        except (KeyError, TypeError, ValueError):
            continue
        if cfs >= 0:
            return {'cfs': cfs, 'dateTime': v.get('dateTime')}
    return None


def fetch_historical_stats(gage_id):
    cached = STATS_CACHE.get(gage_id)
    if cached and (time.time() - cached[1]) < STATS_TTL_S:
        return cached[0]

    url = (
        f'{USGS_STAT_URL}?sites={gage_id}&parameterCd=00060&statReportType=daily'
        f'&statTypeCd=min,p05,p10,p25,p50,p75,p90,p95,max'
        f'&startDT=1991-01-01&endDT=2020-12-31&format=rdb'
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        text = resp.read().decode('utf-8', errors='replace')

    by_day = {}
    headers = None
    for line in text.split('\n'):
        if not line or line.startswith('#'):
            continue
        cols = line.split('\t')
        if cols[0] == 'agency_cd':
            headers = cols
            continue
        if cols[0] != 'USGS' or headers is None:
            continue

        row = {h: (cols[i] if i < len(cols) else '') for i, h in enumerate(headers)}
        try:
            m = int(row['month_nu'])
            d = int(row['day_nu'])
        except (KeyError, ValueError):
            continue

        pts = {}
        for pct, field in [(0, 'min_va'), (5, 'p05_va'), (10, 'p10_va'),
                           (25, 'p25_va'), (50, 'p50_va'), (75, 'p75_va'),
                           (90, 'p90_va'), (95, 'p95_va'), (100, 'max_va')]:
            try:
                pts[pct] = float(row.get(field, ''))
            except (ValueError, TypeError):
                pass

        sorted_points = sorted(pts.items(), key=lambda x: x[1])
        try:
            count = int(row.get('count_nu', '0') or 0)
        except ValueError:
            count = 0
        by_day[f'{m:02d}-{d:02d}'] = {'points': sorted_points, 'count': count}

    STATS_CACHE[gage_id] = (by_day, time.time())
    return by_day


def interpolate_percentile(cfs, points):
    if not points:
        return None
    if cfs <= points[0][1]:
        return points[0][0]
    if cfs >= points[-1][1]:
        return points[-1][0]
    for i in range(len(points) - 1):
        p1, v1 = points[i]
        p2, v2 = points[i + 1]
        if v1 <= cfs <= v2:
            if v2 == v1:
                return p1
            frac = (cfs - v1) / (v2 - v1)
            return p1 + frac * (p2 - p1)
    return None


def categorize(pct):
    if pct is None:
        return None
    if pct < 10:  return 'Much Below Normal'
    if pct < 25:  return 'Below Normal'
    if pct <= 75: return 'Normal'
    if pct <= 90: return 'Above Normal'
    return 'Much Above Normal'


def build_streamflow(gage_id):
    out = {'gage_id': gage_id}
    try:
        current = fetch_latest_daily_value(gage_id)
    except Exception as e:
        current = None
        out['current_error'] = str(e)

    if current:
        out['current_cfs'] = current['cfs']
        out['as_of'] = current['dateTime']
    elif 'current_error' not in out:
        out['current_error'] = 'no recent observation'

    if current:
        try:
            by_day = fetch_historical_stats(gage_id)
        except Exception as e:
            out['stats_error'] = str(e)
            return out

        dt = current['dateTime'] or ''
        key = dt[5:10].replace('/', '-')  # "YYYY-MM-DD..." -> "MM-DD"
        day_stats = by_day.get(key) or by_day.get('02-28')
        if day_stats:
            pct = interpolate_percentile(current['cfs'], day_stats['points'])
            if pct is not None:
                out['percentile'] = round(pct * 10) / 10
                out['category'] = categorize(out['percentile'])
                out['baseline_years'] = '1991–2020'
                out['baseline_count'] = day_stats['count']

    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/.netlify/functions/datacenter':
            self._handle_datacenter(parsed.query)
        else:
            super().do_GET()

    def _handle_datacenter(self, query_string):
        params = urllib.parse.parse_qs(query_string)
        id_param = params.get('id', [None])[0]
        try:
            _id = str(int(id_param))
        except (TypeError, ValueError):
            self._json(400, {'error': 'id parameter is required'})
            return

        record = DATACENTERS.get(_id)
        if record is None:
            self._json(404, {'error': 'Not found'})
            return

        response = dict(record)
        gage = record.get('gage') or {}
        gage_id = gage.get('id')
        if gage_id:
            response['forecast'] = FORECASTS.get(gage_id, [])
            response['streamflow'] = build_streamflow(gage_id)

        self._json(200, response)

    def _json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if '/.netlify/' in args[0]:
            super().log_message(fmt, *args)


if __name__ == '__main__':
    print(f'Dev server: http://localhost:{PORT}')
    http.server.HTTPServer(('', PORT), Handler).serve_forever()
