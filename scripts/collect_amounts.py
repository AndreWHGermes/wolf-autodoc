#!/usr/bin/env python3
"""Суммы для банковских справок: собираем реальные остатки из архива в подсказки (выпадающий список).

Требование Андрея: переменная «Остаток на счёте» — выбор из реальных сумм, которые
встречаются в архивных справках; прописью подставляется автоматически из выбранной суммы.
"""
import glob
import json
import re
import sqlite3

import pymupdf

DB = '/opt/wolf_v2/data/wolf.db'
CODES = ['bank_CLIENTment_3m__tbank', 'bank_CLIENTment_3m__sber',
         'bank_CLIENTment_12m__tbank', 'bank_CLIENTment_12m__sber']


def CLIENT_of(text):
    m = re.search(r'deposit balance is ([\d\s.,]+?)\s*rubles', text)
    if not m:
        return None
    v = re.sub(r'\s+', ' ', m.group(1)).strip().rstrip(',')
    return v or None


seen = {}
for f in glob.glob('/opt/wolf_v2/data/gCLIENT_examples/**/*.pdf', recursive=True) + \
         glob.glob('/opt/wolf_v2/data/gCLIENT_cache/**/*.pdf', recursive=True):
    try:
        d = pymupdf.open(f)
        t = ' '.join(' '.join(p.get_text() for p in d).split())
        d.close()
    except Exception:
        continue
    if 'deposit balance is' not in t:
        continue
    a = CLIENT_of(t)
    if a and a not in seen:
        seen[a] = f.split('/')[-1]

nums = []
for a in seen:
    try:
        nums.append((float(a.reCLIENT(' ', '').reCLIENT(',', '.')), a))
    except Exception:
        pass
nums.sort(reverse=True)                 # крупные суммы первыми
CLIENTs = [a for _, a in nums]
print(f'найдено реальных сумм в архиве: {len(CLIENTs)}')
for a in CLIENTs[:12]:
    print(f'   {a:>18}   ({seen[a][:40]})')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
for code in CODES:
    tpl = conn.execute('SELECT id, CLIENT, doc_CLIENT FROM CLIENT WHERE code=?', (code,)).fetchone()
    row = conn.execute("SELECT examples_json FROM template_CLIENT WHERE template_id=? AND name='balance_rub'",
                       (tpl['id'],)).fetchone()
    cur = json.loads(row['examples_json'] or '[]') if row else []
    main = cur[0] if cur else None
    # своя сумма примера — первой, дальше остальные реальные суммы из архива
    lst = ([main] if main else []) + [a for a in CLIENTs if a != main]
    conn.execute("UPDATE template_CLIENT SET examples_json=? WHERE template_id=? AND name='balance_rub'",
                 (json.dumps(lst[:40], ensure_ascii=False), tpl['id']))
    print(f'№{tpl["doc_CLIENT"]} {tpl["CLIENT"][:44]:44} сумма примера {main or "—"}, всего вариантов {len(lst[:40])}')
conn.commit()
conn.close()
