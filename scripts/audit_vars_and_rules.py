#!/usr/bin/env python3
"""Аудит трёх вопросов Андрея:
1) у каждого документа один активный шаблон и он сверен с оригиналом;
2) все ли переменные каркаса заведены в базе (и наоборот);
3) у каждой ли переменной заполнено правило (rule_text/rule_note) и источник.
"""
import json
import re
import sqlite3
import zipfile
from pathlib import Path

DB = '/opt/wolf_v2/data/wolf.db'
TPL = Path('/opt/wolf_v2/data/templates')
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

tpls = [dict(r) for r in c.execute(
    'SELECT id, code, title, doc_index, engine, status, example_path, example_source '
    'FROM templates ORDER BY doc_index, id')]
active = [t for t in tpls if (t['status'] or 'ok') in ('ok', 'active', 'published') and t['engine']]

print('=== 1. ШАБЛОНЫ ===')
for t in tpls:
    links = [dict(r) for r in c.execute(
        'SELECT pd.product_id, p.code AS product FROM product_documents pd '
        'LEFT JOIN products p ON p.id = pd.product_id WHERE pd.template_id=?', (t['id'],))]
    prods = ','.join(sorted({x['product'] or str(x['product_id']) for x in links})) or '—'
    ex = 'есть' if (TPL / t['code'] / 'example_filled.pdf').exists() else 'НЕТ'
    print(f"{t['doc_index'] or '—':>2} {t['code']:<38} {str(t['engine'] or '-'):<5} {t['status']:<7} "
          f"образец={ex:<5} продуктов={len(links)} [{prods}]")

print('\n=== 2. ПЕРЕМЕННЫЕ КАРКАСА vs БАЗА ===')
gaps_total = 0
for t in active:
    code = t['code']
    if t['engine'] == 'word':
        p = TPL / code / 'word' / 'template.docx'
        if not p.exists():
            print(f'{code}: НЕТ template.docx'); continue
        xml = zipfile.ZipFile(p).read('word/document.xml').decode()
        text = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', xml))
        names = set(re.findall(r'\{\{\s*([A-Za-z_]\w*)\s*\}\}', text))
    else:
        p = TPL / code / 'template.html'
        if not p.exists():
            print(f'{code}: НЕТ template.html'); continue
        raw = p.read_text(encoding='utf-8', errors='ignore')
        names = set(re.findall(r'\{\{\s*([A-Za-z_]\w*)\s*\}\}', raw))
    db = {r['name']: dict(r) for r in c.execute(
        'SELECT * FROM template_variables WHERE template_id=?', (t['id'],))}
    missing = sorted(n for n in names if n not in db)
    unused = sorted(n for n in db if n not in names)
    gaps_total += len(missing)
    print(f"{t['doc_index']:>2} {code:<38} в каркасе={len(names):<3} в базе={len(db):<3} "
          f"нет в базе={len(missing)} не используется={len(unused)}")
    if missing:
        print('     нет в базе:', ', '.join(missing))

print('\n=== 3. ПРАВИЛА И ИСТОЧНИКИ ===')
for t in active:
    rows = [dict(r) for r in c.execute(
        'SELECT name, source_kind, rule_note, rule_text, method FROM template_variables WHERE template_id=?',
        (t['id'],))]
    no_rule = [r['name'] for r in rows if not (r['rule_text'] or '').strip() and not (r['rule_note'] or '').strip()]
    no_src = [r['name'] for r in rows if not (r['source_kind'] or '').strip()]
    no_method = [r['name'] for r in rows if not (r['method'] or '').strip()]
    print(f"{t['doc_index']:>2} {t['code']:<38} всего={len(rows):<3} без правила={len(no_rule):<3} "
          f"без источника={len(no_src):<3} без метода={len(no_method)}")
    if no_rule:
        print('     без правила:', ', '.join(no_rule[:8]))
    if no_src:
        print('     без источника:', ', '.join(no_src[:8]))
