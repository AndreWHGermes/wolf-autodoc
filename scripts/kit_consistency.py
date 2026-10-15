#!/usr/bin/env python3
"""Сверка конструктора продукта: клиентские документы ↔ наши шаблоны ↔ собранный HTML.

Проверяет требование Андрея (06.10.2026): открывая конструктор продукта, видно
  1) реальные документы клиента (вкладка «Клиент»),
  2) только те наши шаблоны, которые нужны этому продукту (отсечка по банку и т.п.),
  3) по каждому шаблону собран HTML с подставленными данными ИМЕННО этого клиента.

Запуск: /usr/bin/python3 scripts/kit_consistency.py [--product C1] [--png]
Выход: docs/KIT_CONSISTENCY.md + картинки в /tmp/kit_check/ (если --png)
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
ROOT = Path('/opt/wolf_v2')
VAR_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')
KEY_VARS = ('client_name', 'full_name_latin', 'employee_full_name', 'passport_no',
            'passport_number', 'date_of_birth', 'address_live', 'balance_rub', 'card_mask')

from app import app  # noqa: E402

with app.app_context():
    from core import db
    from blocks.templates import page as P
    from services import render

    ap = argparse.ArgumentParser()
    ap.add_argument('--product', default='')
    ap.add_argument('--png', action='store_true')
    a = ap.parse_args()

    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    prods = con.execute("SELECT id, code, name FROM products WHERE active=1 "
                        + ("AND code=? " if a.product else "") + "ORDER BY id",
                        ((a.product,) if a.product else ())).fetchall()
    md = ['# Сходимость конструктора продукта', '',
          'Клиентские документы (Google Диск) ↔ наши шаблоны ↔ собранный HTML с данными клиента.', '']
    problems = []
    outdir = Path('/tmp/kit_check')
    outdir.mkdir(parents=True, exist_ok=True)

    for p in prods:
        pcode = p['code']
        app_row = con.execute(
            """SELECT a.id, a.client_id FROM applications a
               WHERE a.product_id=? ORDER BY (a.record_kind='real_test') DESC, a.id DESC LIMIT 1""",
            (p['id'],)).fetchone()
        if not app_row:
            continue
        app_id, cid = int(app_row['id']), int(app_row['client_id'])
        cl = dict(con.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone())
        fio = ('%s %s' % (cl.get('surname') or '', cl.get('name') or '')).strip()
        tpls = con.execute(
            """SELECT t.id, t.code, t.title, t.html_path, pd.slot_code, COALESCE(t.status,'ok') st
               FROM product_documents pd JOIN templates t ON t.id=pd.template_id
               WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden')
               ORDER BY pd.sort_order, t.code""", (p['id'],)).fetchall()
        client_files = P._client_files_of(cid)
        client_only = [f for f in client_files if not P._manager_kind(f.name)]
        md += ['## %s (%s) — заявка %s, клиент %s' % (pcode, p['name'], app_id, fio), '',
               '**Документы клиента на Google Диске** (вкладка «Клиент»): ' +
               ', '.join('`%s`' % f.name for f in client_only) or '— нет', '']
        md.append('**Наши документы по этому продукту** (полоска миниатюр):')
        md.append('')
        for t in tpls:
            # отсечка по банку — как в конструкторе
            cbank = str(cl.get('bank_name') or '').lower()
            tcode = (t['code'] or '').lower()
            off = False
            if cbank and 'bank' in tcode:
                if ('tbank' in tcode or 'tinkoff' in tcode) and ('sber' in cbank or 'сбер' in cbank):
                    off = True
                elif 'sber' in tcode and 'sber' not in cbank and 'сбер' not in cbank:
                    off = True
            base = P._client_original_path(t['code'], cid)
            html_src = ''
            if t['html_path'] and Path(t['html_path']).is_file():
                html_src = Path(t['html_path']).read_text(encoding='utf-8')
            names = sorted(set(VAR_RE.findall(html_src)))
            try:
                vals = render.client_values(app_id) or {}
                vals = {**vals, **{k: v for k, v in render.stored_values(app_id, t['id']).items() if v}}
            except Exception:
                vals = {}
            filled = render.fill(html_src, vals, keep_unfilled=False, template_code=t['code'])
            left = sorted(set(VAR_RE.findall(filled)))
            shown = ['%s = %s' % (k, str(vals.get(k))[:40]) for k in KEY_VARS if vals.get(k)]
            md.append('- `%s` — «%s» %s' % (t['code'], (t['title'] or '')[:44],
                                            '· ВЫКЛЮЧЕН правилом (банк клиента)' if off else ''))
            md.append('    - основа-образец: `%s`' % (Path(base).name if base else 'нет'))
            md.append('    - переменных %d, подставлено %d, осталось незаполненных %s'
                      % (len(names), len(names) - len(left), left or 'нет'))
            md.append('    - данные клиента в HTML: %s' % ('; '.join(shown) or 'нет'))
            if left:
                problems.append('%s/%s: не подставились %s' % (pcode, t['code'], left))
            if not off:
                hp = outdir / ('%s_%s.html' % (pcode, t['code']))
                hp.write_text(filled, encoding='utf-8')
                if a.png:
                    try:
                        render.generate(app_id, t['id'], out_path=str(hp.with_suffix('.pdf')))
                        subprocess.run(['pdftoppm', '-f', '1', '-l', '1', '-r', '80', '-png',
                                        str(hp.with_suffix('.pdf')), str(hp.with_suffix(''))],
                                       check=False, timeout=120)
                    except Exception as exc:  # noqa: BLE001
                        problems.append('%s: не собрался PDF (%s)' % (t['code'], str(exc)[:60]))
        md.append('')
    md += ['## Итог', '']
    md.append('- проблем: %d' % len(problems))
    for x in problems:
        md.append('    - %s' % x)
    (ROOT / 'docs' / 'KIT_CONSISTENCY.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('\n'.join(md))
