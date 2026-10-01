#!/usr/bin/env python3
"""Чистые значения примера для банковских справок (№1-4) из подлинников.

Значения берутся из реального заполненного документа (example_filled.pdf) и
записываются в template_CLIENT.examples_json — их видно в HTML-шаблоне
и подставляет кнопка «Подставить значения из примера».
"""
import json
import re
import sqlite3

import pymupdf

DB = '/opt/wolf_v2/data/wolf.db'
CODES = ['bank_CLIENTment_3m__tbank', 'bank_CLIENTment_3m__sber',
         'bank_CLIENTment_12m__tbank', 'bank_CLIENTment_12m__sber']


def flat_text(path):
    d = pymupdf.open(path)
    t = ' '.join(' '.join(p.get_text() for p in d).split())
    d.close()
    return t


def parse_bank_CLIENTment(t):
    v = {}
    m = re.search(r'Ref\.\s*([A-Za-z0-9]+)\s+(\d{2}\.\d{2}\.\d{4})', t)
    if m:
        v['ref_no'], v['doc_date'] = m.group(1), m.group(2)
    m = re.search(r'(?:TBANK|SberBank)\s+No\s+([A-Za-z0-9]+)', t)
    if m:
        v['doc_no'] = m.group(1)
    # ФИО и адрес: между номером документа и началом текста банка
    m = re.search(r'No\s+[A-Za-z0-9]+\s+(.*?)«[ST]', t)
    if m:
        tail = m.group(1).strip().rstrip(',')
        CLIENT = tail.split()
        caps = 0
        while caps < len(CLIENT) and (CLIENT[caps].isupper() or len(CLIENT[caps]) <= 2 and CLIENT[caps].isalpha()):
            caps += 1
        v['client_name'] = ' '.join(CLIENT[:caps]).strip()
        addr = ' '.join(CLIENT[caps:]).strip()
        addr = re.sub(r'\s+([,.])', r'\1', addr)          # убрать пробел перед запятой
        addr = re.sub(r'\s{2,}', ' ', addr).strip()
        v['address_live'] = addr
    m = re.search(r'card No\s+(\d{6}\*+\d{4})', t)
    if m:
        v['card_mask'] = m.group(1)
    m = re.search(r'As from (\d{2}\.\d{2}\.\d{4}) to (\d{2}\.\d{2}\.\d{4})', t)
    if m:
        v['CLIENT_from'], v['CLIENT_to'] = m.group(1), m.group(2)
    m = re.search(r'deposit balance is ([\d\s.,]+?)\s*rubles', t)
    if m:
        v['balance_rub'] = re.sub(r'\s+', ' ', m.group(1)).strip()
    m = re.search(r'\(([^()]*kopeks)\)', t)
    v['balance_CLIENT'] = m.group(1).strip() if m else ''
    return v


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
for code in CODES:
    tpl = conn.execute('SELECT id, CLIENT, doc_CLIENT FROM CLIENT WHERE code=?', (code,)).fetchone()
    src = f'/opt/wolf/data/CLIENT/{code}/example_filled.pdf'
    t = flat_text(src)
    vals = parse_bank_CLIENTment(t)
    print(f'=== №{tpl["doc_CLIENT"]} {tpl["CLIENT"]}  ({code})')
    saved = cleared = 0
    for name in [r['name'] for r in conn.execute(
            'SELECT name FROM template_CLIENT WHERE template_id=?', (tpl['id'],))]:
        if name not in vals:
            continue
        val = vals[name]
        cur = conn.execute('SELECT examples_json FROM template_CLIENT WHERE template_id=? AND name=?',
                           (tpl['id'], name)).fetchone()
        payload = json.dumps([val], ensure_ascii=False) if val else '[]'
        if (cur['examples_json'] or '') == payload:
            continue
        conn.execute('UPDATE template_CLIENT SET examples_json=? WHERE template_id=? AND name=?',
                     (payload, tpl['id'], name))
        saved += 1
        if not val:
            cleared += 1
        print(f'   {name:14} = {val}')
    conn.commit()
    print(f'   обновлено полей: {saved} (очищено пустых: {cleared})\n')
conn.close()
print('готово')
