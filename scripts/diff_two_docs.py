#!/usr/bin/env python3
"""Почему Remote Work Agreement 2 страницы вместо 3 и чем 12m-справка Сбера отличается от подлинника."""
import difflib
import re
from pathlib import Path

import pymupdf

R = Path('/opt/wolf_v2/data')
pairs = [
    ('RWA', R / 'templates/remote_work_agreement__default/example_filled.real.pdf',
     Path('/root/.hermes/cache/wolf_audit2/build/08_remote_work_agreement__default.pdf')),
    ('SBER12', R / 'originals/bank_statement_12m__sber.pdf',
     Path('/root/.hermes/cache/wolf_audit2/build/04_bank_statement_12m__sber.pdf')),
]


def w(t):
    return re.findall(r'[A-Za-zА-Яа-я0-9]+', t.lower())


for name, ref, ours in pairs:
    if not ours.exists():
        print(name, '— нет собранного файла', ours)
        continue
    a = pymupdf.open(ref)
    b = pymupdf.open(ours)
    ta = '\n'.join(p.get_text() for p in a)
    tb = '\n'.join(p.get_text() for p in b)
    print(f'=== {name}: оригинал {len(a)} стр, наш {len(b)} стр, совпадение '
          f'{difflib.SequenceMatcher(None, w(tb), w(ta)).ratio():.2f}')
    for i in range(len(a)):
        pa = a[i].get_text().split('\n')
        pb = b[i].get_text().split('\n') if i < len(b) else []
        print(f'  стр {i + 1}: строк {len(pa)} / {len(pb)}')
        if i == 0:
            print('   начало оригинала:', ' | '.join(x.strip() for x in pa[:4] if x.strip())[:160])
            print('   начало нашего  :', ' | '.join(x.strip() for x in pb[:4] if x.strip())[:160])
    if len(a) > len(b):
        last = a[-1].get_text().strip().split('\n')
        print('   последняя страница оригинала:', ' | '.join(x.strip() for x in last[:6])[:200])
