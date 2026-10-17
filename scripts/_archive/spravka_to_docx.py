#!/usr/bin/env python3
"""Оригинальная заполненная справка №1 → Word (.docx) с жёлтой разметкой переменных.

Берём подлинную справку Т-Банка с реальными данными клиента и воспроизводим её в .docx,
подсвечивая жёлтым (как в остальных документах) значения полей-переменных шаблона №1.
"""
import re
import sys

import pymupdf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docx.enum.text import WD_COLOR_INDEX

CANDIDATES = [
    '/opt/wolf_v2/data/templates/bank_statement_3m__tbank/example_filled.pdf',
    '/opt/wolf_v2/data/gdrive_examples/ALEKSANDR KARPOV/BANKSTATEMENT.pdf',
]
OUT = '/tmp/Справка_1_Т-Банк_3мес_размеченная.docx'


def read_source(path):
    d = pymupdf.open(path)
    text = '\n'.join(p.get_text() for p in d)
    meta = str((d.metadata or {}).get('producer') or '')
    d.close()
    return ' '.join(text.split()), meta


src = None
for c in CANDIDATES:
    try:
        t, meta = read_source(c)
    except Exception:
        continue
    if 'ALEKSANDR KARPOV' in t or re.search(r'card No \d{6}\*+', t):
        src = (c, t, meta)
        break
if not src:
    print('подлинник не найден'); sys.exit(1)
path, text, meta = src
print('источник:', path)

v = {}
v['ref_no'] = re.search(r'Ref\.\s*([A-Z0-9]+)', text).group(1)
v['doc_date'] = re.search(r'Ref\.\s*[A-Z0-9]+\s+(\d{2}\.\d{2}\.\d{4})', text).group(1)
v['doc_no'] = re.search(r'No\s+([A-Za-z0-9]+)', text).group(1)
# ФИО — слова капсом сразу после номера, остальное — адрес
tail = re.search(r'No\s+[A-Za-z0-9]+\s+(.*?)«TBank»', text).group(1).strip()
words = tail.split()
caps = 0
while caps < len(words) and words[caps].isupper():
    caps += 1
v['client_name'] = ' '.join(words[:caps])
v['address_live'] = ' '.join(words[caps:]).rstrip(',')
v['card_mask'] = re.search(r'card No\s+(\d{6}\*+\d+)', text).group(1)
v['period_from'] = re.search(r'As from (\d{2}\.\d{2}\.\d{4})', text).group(1)
v['period_to'] = re.search(r'As from \d{2}\.\d{2}\.\d{4} to (\d{2}\.\d{2}\.\d{4})', text).group(1)
v['balance_rub'] = re.search(r'deposit balance is ([\d\s]+,\s*\d{2})', text).group(1)
v['balance_words'] = re.search(r'\(([^()]*(?:kopeks|kopecks))\)', text).group(1)

doc = Document()
st = doc.styles['Normal']
st.font.name = 'Times New Roman'
st.font.size = Pt(11)


def para(runs, align=None, space_after=6):
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    for text_, hl in runs:
        r = p.add_run(text_)
        if hl:
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    p.paragraph_format.space_after = Pt(space_after)
    return p


# шапка банка (не переменные)
para([('38A, BLD. 26, 2 KHUTORSKAYA STREET, MOSCOW, 127287, RUSSIA', False)])
para([('TEL.: +7 495 648-10-00, TBANK.RU', False)], space_after=14)

para([('Ref. ', False), (v['ref_no'], True), ('  ', False), (v['doc_date'], True),
      ('\t\t\t\t\tTBANK', False)], space_after=14)
para([('No ', False), (v['doc_no'], True)], space_after=10)
para([(v['client_name'], True)], space_after=2)
para([(v['address_live'], True)], space_after=18)

para([('«TBank», universal license of Bank of Russia No 9441, hereby informs that card No ', False),
      (v['card_mask'], True), (' has been issued for ', False), (v['client_name'], True), (' .', False)],
     space_after=14)
para([('As from ', False), (v['period_from'], True), (' to ', False), (v['period_to'], True),
      (' the deposit balance is ', False), (v['balance_rub'], True), (' rubles (', False),
      (v['balance_words'], True), (').', False)], space_after=26)

para([('Best regards,', False)], space_after=2)
para([('Head of Back-office Department', False)], space_after=2)
para([('E.S. Shadrina', False)], space_after=24)
para([('c/a 30101810900000000974 1st Office in the Main Department of the Central Bank of the '
       'Russian Federation in the Central Federal District Moscow BIC 044583974', False)],
     space_after=0)

doc.save(OUT)
print('готово:', OUT)
print('значения примера:')
for k, x in v.items():
    print(f'  {k:14} = {x}')
