#!/usr/bin/env python3
"""Сверка каждого шаблона с оригиналом: сборка + сравнение текста.

Для каждого активного шаблона:
  * берём заявку его продукта, считаем значения, собираем документ через путь сайта;
  * сравниваем текст сборки с example_filled.real.pdf (подлинник), если он есть,
    иначе с example_filled.pdf;
  * считаем долю совпадения по словам и показываем слова оригинала, которых нет у нас
    (это и есть «не тот бланк» или «потерянный статичный текст»).
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
import pymupdf

from services.values import build_template_values
from services import doc_engine

OUT = Path('/root/.hermes/cache/wolf_audit2')
OUT.mkdir(parents=True, exist_ok=True)
ROOT = Path('/opt/wolf_v2/data/templates')
c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row


def words(text: str) -> list[str]:
    return re.findall(r'[A-Za-zА-Яа-я0-9]+', text.lower())


rows = []
for t in [dict(r) for r in c.execute(
        'SELECT * FROM templates WHERE engine IS NOT NULL ORDER BY doc_index')]:
    if (t['status'] or 'ok') not in ('ok', 'active', 'published'):
        continue
    code = t['code']
    app = c.execute('''SELECT a.id FROM applications a
                       JOIN product_documents pd ON pd.product_id=a.product_id
                       WHERE pd.template_id=? ORDER BY a.id DESC LIMIT 1''', (t['id'],)).fetchone()
    if not app:
        continue
    app_id = app['id']
    a = dict(c.execute('SELECT * FROM applications WHERE id=?', (app_id,)).fetchone())
    cl = {}
    if a.get('client_id'):
        cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone())
    vals = build_template_values(cl, code, {}, app_id) or {}
    res = doc_engine.build_document(code, vals, OUT / 'build', engine=t['engine'],
                                   name=f"{t['doc_index']:02d}_{code}")
    if not res.get('pdf'):
        rows.append({'doc': t['doc_index'], 'code': code, 'error': 'не собрался'})
        continue
    ours = pymupdf.open(res['pdf'])
    our_text = '\n'.join(p.get_text() for p in ours)
    ref_path = ROOT / code / 'example_filled.real.pdf'
    if not ref_path.exists():
        ref_path = ROOT / code / 'example_filled.pdf'
    ref_text = '\n'.join(p.get_text() for p in pymupdf.open(ref_path)) if ref_path.exists() else ''
    ow, rw = words(our_text), words(ref_text)
    ratio = difflib.SequenceMatcher(None, ow, rw).ratio() if rw else 0
    missing = [w for w in dict.fromkeys(rw) if w not in set(ow)][:12]
    rows.append({'doc': t['doc_index'], 'code': code, 'app': app_id,
                 'ours_pages': len(ours), 'ref_pages': len(pymupdf.open(ref_path)) if ref_path.exists() else None,
                 'same': round(ratio, 2), 'missing': missing,
                 'vars_missing': res.get('missing') or [], 'placeholders': res.get('placeholders') or [],
                 'ref': ref_path.name})

(OUT / 'report.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
for r in rows:
    if r.get('error'):
        print(f"{r['doc']:>2} {r['code']:<36} ОШИБКА: {r['error']}")
        continue
    print(f"{r['doc']:>2} {r['code']:<36} стр {r['ours_pages']}/{r['ref_pages']} "
          f"совпадение={r['same']:<5} пусто={len(r['vars_missing'])} ph={len(r['placeholders'])} "
          f"нет слов: {', '.join(r['missing'][:7])}")
print('\nотчёт:', OUT / 'report.json')
