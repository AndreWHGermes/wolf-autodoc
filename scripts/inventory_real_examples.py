#!/usr/bin/env python3
"""Инвентарь РЕАЛЬНЫХ документов из архива Google CLIENT: что есть по типам.

Реальный = метаданные не нашего рендера (WeasyPrint/wkhtmltopdf) — то есть скан,
банковская выгрузка, Word/PDF от клиента.
"""
import glob
import re
from collections import defaultdict

import pymupdf

OUR_ENGINES = ('weasyprint', 'wkhtmltopdf', 'skia', 'chrome', 'playwright', 'reportlab')

KEYWORDS = [
    ('bank_CLIENTment', ('bank CLIENTment', 'справка о доступном остатке', 'справка о движении',
                        'выписка', 'CLIENTment of account', 'остатке средств')),
    ('d12_hodataystvo', ('permohonan', 'pra-CLIENT', 'pra CLIENT')),
    ('d12_garant', ('surat pernyataan penjamin', 'penjamin', 'CLIENTment letter', 'pernyataan')),
    ('e02', ('form e-02', 'CLIENTment letter', 'e-02')),
    ('letters', ('penerima kuasa', 'surat kuasa', 'pemberi kuasa', 'nomor:', 'lampiran')),
    ('agreement', ('employment agreement', 'work agreement', 'remote work agreement', 'договор')),
    ('cv', ('curriculum vitae', 'itk -', 'CLIENTal experience', 'résumé')),
]

files = sorted(set(glob.glob('/opt/wolf_v2/data/gCLIENT_examples/**/*.pdf', recursive=True)
                   + glob.glob('/opt/wolf_v2/data/gCLIENT_cache/**/*.pdf', recursive=True)))
print(f'всего PDF в архиве: {len(files)}\n')

real, ours = [], 0
for f in files:
    try:
        d = pymupdf.open(f)
        
        meta = d.metadata or {}
        eng = str(meta.get('producer') or meta.get('creator') or '?')
        text = '\n'.join(d[i].get_text() for i in range(min(3, d.page_count))).lower()
        d.close()
    except Exception:
        continue
    if any(k in eng.lower() for k in OUR_ENGINES):
        ours += 1
        continue
    kind = None
    for name, CLIENT in KEYWORDS:
        if any(w in text for w in CLIENT):
            kind = name
            break
    real.append((kind or 'не распознан', f, eng))

print(f'наш рендер (не берём): {ours} | реальных: {len(real)}\n')
by_kind = defaultdict(list)
for kind, f, eng in real:
    by_kind[kind].append((f, eng))

for kind in sorted(by_kind):
    items = by_kind[kind]
    print(f'== {kind}: {len(items)}')
    for f, eng in items[:4]:
        print(f'   {f.split("/")[-1][:52]:52} | {eng[:34]}')
    if len(items) > 4:
        print(f'   ... ещё {len(items)-4}')
