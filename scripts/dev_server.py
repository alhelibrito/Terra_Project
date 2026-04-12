"""
Local development server.

Serves static files from web/ and emulates the Netlify Function at
/.netlify/functions/datacenter?id=N using the generated datacenter-data.js.

Run from the project root:
    python3 scripts/dev_server.py
"""

import http.server
import json
import os
import re
import urllib.parse

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR   = os.path.join(ROOT, 'web')
DATA_FILE = os.path.join(ROOT, 'functions', 'datacenter-data.js')
PORT      = 8765


def load_records():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    # Strip the CommonJS wrapper: module.exports={...};
    content = re.sub(r'^module\.exports=', '', content).rstrip(';')
    return json.loads(content)


RECORDS = load_records()


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

        record = RECORDS.get(_id)
        if record is None:
            self._json(404, {'error': 'Not found'})
            return

        self._json(200, record)

    def _json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Suppress noisy tile/asset requests, show only function calls
        if '/.netlify/' in args[0]:
            super().log_message(fmt, *args)


if __name__ == '__main__':
    print(f'Dev server: http://localhost:{PORT}')
    http.server.HTTPServer(('', PORT), Handler).serve_forever()
