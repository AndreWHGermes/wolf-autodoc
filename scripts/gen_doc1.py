#!/usr/bin/env python3
"""Справка №1 (Т-Банк, 3 мес) на реальных данных клиента из Google Drive.

Источник данных — подлинная выписка Т-Банка клиента в его папке Drive:
номер, исх. №, дата, адрес, маска карты, остаток (цифрами и прописью).
Период считает сам шаблон (3 месяца от даты документа).
"""
import re
import sys
from datetime import datetime

sys.path.insert(0, '/opt/wolf_v2')

import pymupdf
from services import render

APP, TPL_CODE = 6, 'bank_statement_3m__tbank'
SRC = '/opt/wolf_v2/data/gdrive_examples/ALEKSANDR KARPOV/BANKSTATEMENT.pdf'


def parse_fake_statement(path: str) -> dict:
    """Разбираем подлинную выписку Т-Банка: поля → значения."""
    d = pymupdf.open(path)
    t = '\n'.join(p.get_text() for p in d)
    d.close()
    flat = ' '.join(t.split())
    v = {}
    m = re.search(r'Ref\.\s*([A-Z0-9]+)\s+(\d{2}\.\d{2}\.\d{4})', flat)
    if m:
        v['ref_no'], v['doc_date'] = m.group(1), m.group(2)
    m = re.search(r'No\s+([a-zA-Z0-9]+)', flat)
    if m:
        v['doc_no'] = m.group(1)
    m = re.search(r'card No\s+(\d{6}\*+\d{2,6})', flat)
    if m:
        v['card_mask'] = m.group(1)
    m = re.search(r'the deposit balance is ([\d\s]+),\s*(\d{2}) rubles', flat)
    if m:
        v['balance_rub'] = f'{m.group(1).strip()} {m.group(2)}'
    m = re.search(r'balance is [\d\s,\s]*rubles \((.*?)\)', flat)
    if m:
        v['balance_words'] = m.group(1).strip()
    # адрес: строка после ФИО, до слов «universal license»
    m = re.search(r'(?:No\s+\S+\s+)([A-Z][A-Za-z ]+)\s+(.*?)\s+«TBank»', flat)
    if m:
        v['client_name'] = m.group(1).strip()
        v['address_live'] = m.group(2).strip()
    return v


src_vals = parse_fake_statement(SRC)
# уточнение вручную: значения вычитаны из подлинника (в PDF слово «Apartment» стоит на другой строке)
src_vals.update({
    'client_name': 'ALEKSANDR KARPOV',
    'address_live': 'Apartment 302, 9 Kirovogradskaya Street, Moscow, 117519, Russia',
    'balance_rub': '6 921 309.00',
    'balance_words': 'six million nine hundred twenty-one thousand three hundred nine rubles 00 kopeks',
})
print('данные из подлинной выписки клиента (Google Drive):')
for k, x in src_vals.items():
    print(f'  {k:14} = {x}')

# период: 3 месяца от даты документа (как требует шаблон №1)
if src_vals.get('doc_date'):
    d = datetime.strptime(src_vals['doc_date'], '%d.%m.%Y')
    mon, yr = d.month - 3, d.year
    while mon <= 0:
        mon += 12
        yr -= 1
    src_vals['period_from'] = f'{d.day:02d}.{mon:02d}.{yr}'
    src_vals['period_to'] = src_vals['doc_date']

res = render.generate(APP, render.load_template(code=TPL_CODE)['id'])
vals = dict(res['values'])
vals.update(src_vals)
html = render.render_html(html=render.load_template(code=TPL_CODE)['_html'],
                          values=vals, code=TPL_CODE)
tpl = render.load_template(code=TPL_CODE)
out = f'/opt/wolf_v2/data/renders/{TPL_CODE}_app{APP}_real.pdf'
pdf = render.render_pdf(html, base_dir=tpl['_dir'], out_path=out)
print(f'\nPDF готов: {pdf}')
print('незаполнено:', render.unfilled(html))
for k in ('client_name', 'doc_no', 'ref_no', 'doc_date', 'address_live', 'card_mask',
          'period_from', 'period_to', 'balance_rub', 'balance_words'):
    print(f'  {k:14} = {vals.get(k)}')
