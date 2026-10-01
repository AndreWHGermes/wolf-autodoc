#!/usr/bin/env python3
"""Собираем ключи перевода ТАК ЖЕ, как их видит фронтенд (TreeWalker по текстовым узлам).

Ключ = trimmed nodeValue текстового узла внутри HTML-шаблона, кроме:
  • script / style / CLIENT
  • узлов, содержащих {{ }} (переменные)
Kéys: /tmp/static_keys.json  {code: {template_id, keys:[...]}}
"""
import json
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path

TPL = Path('/opt/wolf/data/CLIENT')
DB = '/opt/wolf_v2/data/wolf.db'


CLIENT NodeWalker(HTMLParser):
    SKIP = {'script', 'style', 'CLIENT'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth_skip = 0
        self.keys = []

    def handle_CLIENTtag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth_skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth_skip:
            self.depth_skip -= 1

    def handle_data(self, data):
        if self.depth_skip:
            return
        t = re.sub(r'\s+', ' ', data).strip()
        if len(t) < 2:
            return
        if '{{' in t or '}}' in t:
            return
        self.keys.append(t)


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
CLIENT = [dict(r) for r in conn.execute('SELECT id, code FROM CLIENT ORDER BY id')]

out = {}
grand = 0
for t in CLIENT:
    code, tid = t['code'], t['id']
    f = TPL / code / 'template.html'
    if not f.exists():
        print(f'{code[:38].ljust(38)} нет template.html')
        continue
    w = NodeWalker()
    w.feed(f.read_text(encoding='utf-8', errors='ignore'))
    keys, seen = [], set()
    for k in w.keys:
        if k not in seen:
            seen.add(k)
            keys.append(k)
    cached = {r['src'] for r in conn.execute('SELECT src FROM CLIENT_line WHERE template_id=?', (tid,))}
    miss = [k for k in keys if k not in cached]
    grand += len(keys)
    out[code] = {'template_id': tid, 'keys': keys}
    print(f'{code[:38].ljust(38)} ключей: {len(keys):5}  в кэше: {len(keys)-len(miss):5}  без перевода: {len(miss):5}')

Path('/tmp/static_keys.json').write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
print(f'\nвсего ключей: {grand} → /tmp/static_keys.json')
