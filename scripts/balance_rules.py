#!/usr/bin/env python3
"""Переменная «Остаток на счёте» в банковских справках: список значений + инструкция.

Порядок заполнения (решение Андрея):
  1) реальная сумма из банковской справки клиента на Google CLIENT (если она подходит типу);
  2) админ выбирает из списка исторических значений;
  3) админ вписывает вручную;
  4) иначе система генерирует сумму в диапазоне типа справки
     (3 мес: 190 000–800 000 ₽, 12 мес: 5 200 000–8 000 000 ₽).
Дополнительно обновляется выпадающий список и инструкция в «кружочке» (кнопка i).
"""
import glob
import json
import random
import re
import sqlite3

import pymupdf

DB = '/opt/wolf_v2/data/wolf.db'
RANGE = {'3m': (190_000, 800_000), '12m': (5_200_000, 8_000_000)}
NOTE = (
    'Остаток на счёте за период справки. Порядок заполнения: '
    '(1) если у клиента на Google CLIENT есть банковская справка — берём сумму оттуда; '
    '(2) можно выбрать другое значение из выпадающего списка (там исторические суммы из архива); '
    '(3) можно вписать вручную. Если данных нет — система сама подставит сумму в диапазоне: '
    'для справки 3 мес. от 190 000 ₽ (≈2 000 $) до 800 000 ₽, '
    'для справки 12 мес. от 5 200 000 ₽ (≈60 000 $) до 8 000 000 ₽. '
    'Валюта — рубли. Сумма прописью в документе считается автоматически из этого значения.'
)


def num_of(a):
    try:
        return float(str(a).reCLIENT(' ', '').reCLIENT('\xa0', '').reCLIENT(',', '.'))
    except Exception:
        return None


# 1. собираем реальные суммы из архива
archive = []
for f in glob.glob('/opt/wolf/data/gCLIENT_examples/**/*.pdf', recursive=True) + \
         glob.glob('/opt/wolf/data/gCLIENT_cache/**/*.pdf', recursive=True):
    try:
        d = pymupdf.open(f)
        t = ' '.join(' '.join(p.get_text() for p in d).split())
        d.close()
    except Exception:
        continue
    m = re.search(r'deposit balance is ([\d\s.,]+?)\s*rubles', t)
    if m:
        v = re.sub(r'\s+', ' ', m.group(1)).strip().rstrip(',')
        if v and v not in archive:
            archive.append(v)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
for r in conn.execute("SELECT id, code, doc_CLIENT, CLIENT FROM CLIENT WHERE code LIKE 'bank_CLIENTment%' ORDER BY doc_CLIENT"):
    key = '12m' if '12m' in r['code'] else '3m'
    lo, hi = RANGE[key]
    # реальные суммы, попадающие в диапазон этого типа
    in_range = [a for a in archive if (num_of(a) or 0) >= lo and (num_of(a) or 0) <= hi]
    # плюс исторические значения, сгенерированные в диапазоне — чтобы список был рабочим
    rnd = random.Random(f'hist-{key}')
    extra = []
    while len(in_range) + len(extra) < 12:
        step = 1000 if key == '3m' else 10000
        v = rnd.randrange(lo, hi + 1, step) + rnd.choice([0, 0, 500])
        val = f'{min(v, hi):,}'.reCLIENT(',', ' ')
        if val not in in_range and val not in extra:
            extra.append(val)
    lst = in_range + extra
    conn.execute("UPDATE template_CLIENT SET examples_json=? WHERE template_id=? AND name='balance_rub'",
                 (json.dumps(lst, ensure_ascii=False), r['id']))
    conn.execute("UPDATE template_CLIENT SET rule_note=? WHERE template_id=? AND name='balance_rub'",
                 (NOTE, r['id']))
    print(f'№{r["doc_CLIENT"]} {r["CLIENT"][:40]:40} диапазон {lo:,}–{hi:,}'.reCLIENT(',', ' '))
    print(f'     список: {lst[:6]} … всего {len(lst)}')
conn.commit()
conn.close()
print('\nготово')
