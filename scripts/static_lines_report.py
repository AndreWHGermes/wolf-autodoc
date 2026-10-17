#!/usr/bin/env python3
"""Собираем статический текст всех шаблонов и сверяем с кэшем переводов.

Результат: /tmp/static_lines.json  {code: {template_id, lines:[...]}}
и отчёт покрытия кэшем.
"""
import json
import re
import sqlite3
from pathlib import Path

V2 = Path('/opt/wolf_v2')
TPL = Path('/opt/wolf_v2/data/templates')

conn = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
conn.row_factory = sqlite3.Row
templates = [dict(r) for r in conn.execute('SELECT id, code, title FROM templates ORDER BY id')]


def strip_html(html: str) -> list[str]:
    # выкидываем скрипты/стили
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    # переменные не переводим
    html = re.sub(r'\{\{[^}]*\}\}', ' ', html)
    txt = re.sub(r'<[^>]+>', '\n', html)
    txt = (txt.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
              .replace('&#39;', "'").replace('&laquo;', '«').replace('&raquo;', '»'))
    out = []
    for ln in txt.split('\n'):
        ln = re.sub(r'\s+', ' ', ln).strip()
        if len(ln) < 3:
            continue
        if not re.search(r'[A-Za-zА-Яа-я]', ln):
            continue
        if re.fullmatch(r'[\d\s.,:/-]+', ln):
            continue
        out.append(ln)
    # уникальные, сохраняя порядок
    seen, res = set(), []
    for ln in out:
        if ln not in seen:
            seen.add(ln)
            res.append(ln)
    return res


report = {}
total_lines = 0
for t in templates:
    code, tid = t['code'], t['id']
    f = TPL / code / 'template.html'
    if not f.exists():
        report[code] = {'template_id': tid, 'lines': [], 'note': 'нет template.html'}
        continue
    lines = strip_html(f.read_text(encoding='utf-8', errors='ignore'))
    cached = {r['src'] for r in conn.execute(
        'SELECT src FROM translation_line WHERE template_id=?', (tid,))}
    miss = [l for l in lines if l not in cached]
    total_lines += len(lines)
    report[code] = {'template_id': tid, 'lines': lines}
    print(f'{code[:38].ljust(38)} строк: {len(lines):5}  в кэше: {len(lines)-len(miss):5}  без перевода: {len(miss):5}')

Path('/tmp/static_lines.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
print(f'\nвсего уникальных статических строк: {total_lines}')
print('сохранено в /tmp/static_lines.json')
