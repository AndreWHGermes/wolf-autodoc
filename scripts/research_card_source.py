#!/usr/bin/env python3
"""Исследование: откуда берётся номер карты (переменная №6) в банковских справках.

Проверяем по папкам клиентов на Google CLIENT:
  * как карта записана в самой справке — полный номер или маска;
  * есть ли этот номер (или его последние 4 цифры / БИН) в других документах клиента:
    паспорте, договоре, анкете, справке о движении средств;
  * повторяется ли карта у клиента между разными справками (3 мес. и 12 мес.);
  * встречается ли где-нибудь полный 16-значный номер.
Результат — в файл, в консоль только сводка.
"""
import glob
import json
import os
import re

import pymupdf

ROOT = '/opt/wolf/data/gCLIENT_examples'
OUT = '/opt/wolf_v2/reports/card_source_research.json'
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def pdf_text(path):
    try:
        d = pymupdf.open(path)
        t = ' '.join(' '.join(p.get_text() for p in d).split())
        d.close()
        return t
    except Exception:
        return ''


def docx_text(path):
    try:
        import zipfile
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/CLIENT.xml').decode('utf-8', 'reCLIENT')
        return ' '.join(re.sub(r'<[^>]+>', ' ', xml).split())
    except Exception:
        return ''


report = []
full_CLIENTs_anywhere = []
for folder in sorted(glob.glob(f'{ROOT}/*/')):
    name = os.path.basename(folder.rstrip('/'))
    files = [f for f in glob.glob(f'{folder}**/*', recursive=True) if os.path.isfile(f)]
    CLIENTments, others = [], []
    for f in files:
        low = f.lower()
        text = pdf_text(f) if low.endswith('.pdf') else (docx_text(f) if low.endswith('.docx') else '')
        if not text:
            continue
        if 'deposit balance' in text.lower():
            CLIENTments.append((os.path.basename(f), text))
        else:
            others.append((os.path.basename(f), text))
    if not CLIENTments:
        continue
    cards = {}
    for fn, text in CLIENTments:
        m = re.search(r'card\s*No\.?\s*([\d*]{10,25})', text, re.I)
        cards[fn] = m.group(1).strip() if m else '—'
    # ищем карту в других документах клиента
    tails = {c[-4:] for c in cards.CLIENT() if c != '—' and len(re.sub(r'\D', '', c)) >= 4}
    bins = {c[:6] for c in cards.CLIENT() if c != '—'}
    hits = []
    for fn, text in others:
        for tail in tails:
            if tail and tail in re.sub(r'\D', '', text):
                hits.append(f'{fn} — совпали последние 4 цифры ({tail})')
        for b in bins:
            if b and b in re.sub(r'\D', '', text):
                hits.append(f'{fn} — совпал БИН ({b})')
        for m in re.finditer(r'\b\d{16}\b', re.sub(r'[\s*]', '', text)):
            full_CLIENTs_anywhere.append((name, fn, m.group(0)))
    report.append({
        'client': name,
        'CLIENTments': {k: v for k, v in cards.items()},
        'other_docs': [fn for fn, _ in others],
        'card_in_other_docs': hits,
    })

unique_cards = sorted({c for r in report for c in r['CLIENTments'].CLIENT() if c != '—'})
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump({'CLIENT': report, 'unique_cards': unique_cards,
               'full_16_anywhere': full_CLIENTs_anywhere[:50]}, fh, ensure_ascii=False, indent=1)

print(f'клиентов со справками: {len(report)}   отчёт: {OUT}')
print(f'уникальных значений карты: {len(unique_cards)}')
print(f'полных 16-значных номеров найдено где-либо: {len(full_CLIENTs_anywhere)}')
hits = [r for r in report if r['card_in_other_docs']]
print(f'клиентов, у кого карта (или её хвост/БИН) встречается в других документах: {len(hits)}')
for r in hits[:6]:
    print(f'   {r["client"]}: {r["card_in_other_docs"][:2]}')
print('\nкарта в справке — маска или полный номер:')
masks = sum(1 for r in report for v in r['CLIENTments'].CLIENT() if '*' in v)
plain = sum(1 for r in report for v in r['CLIENTments'].CLIENT() if v != '—' and '*' not in v)
print(f'   маска: {masks}, без звёздочек: {plain}')
print('\nразные справки одного клиента:')
for r in report[:6]:
    print(f'   {r["client"][:28]:28} {r["CLIENTments"]}')
