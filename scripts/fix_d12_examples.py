#!/usr/bin/env python3
"""Значения примера для D12 (№8 ходатайство, №9 заявление гаранта) и проверка E-02 (№10, 11).

Источник — подлинные письма PT ALPHA PRIME BALI из архива образцов.
"""
import json
import re
import sqlite3

import pymupdf

DB = '/opt/wolf_v2/data/wolf.db'
SP_ADDR = 'Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten Gianyar, Bali 80581'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row


def parse_d12(text):
    v = {
        'signatory_name': 'BARTOSZ PAWEL NAFALSKI',
        'signatory_name_2': 'Marcellena Nirmala Chrisna Moeri',
        'signatory_position': 'Direktur ALPHA PRIME BALI',
        'signatory_citizenship': 'Poland',
        'signatory_address': SP_ADDR,
        'sponsor_person_name': 'BARTOSZ PAWEL NAFALSKI',
        'sponsor_position': 'Direktur',
        'sponsor_company': 'PT ALPHA PRIME BALI',
        'sponsor_address': SP_ADDR,
        'sponsor_nationality': 'Poland',
        'sponsor_birth_place_date': 'Poland, 20-03-1973',
        'sponsor_contact': 'Telp: +08113979669, Email: PTALPHAPRIMECONSULTING@GMAIL.COM',
        'job_and_position': 'Direktur',
        'letter_subject': 'Permohonan Visa D12',
        'letter_no': '',
    }
    m = re.search(r'Badung,\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    if m:
        v['place_date'] = 'Badung, ' + m.group(1)
    # данные иностранца: в подлиннике поля пустые (заполняются под клиента)
    m = re.search(r'Nama\s*:\s*([A-Z][A-Z ]+?)\s*Tempat', text)
    if m:
        v['client_name'] = m.group(1).strip()
    m = re.search(r'pemegang paspor no\s*:?\s*(\d{5,})', text, re.I)
    if m:
        v['passport_no'] = m.group(1)
    return v


for did in (8, 9):
    tpl = conn.execute('SELECT id, code, title FROM templates WHERE doc_index=?', (did,)).fetchone()
    d = pymupdf.open(f'/opt/wolf_v2/data/sources/{tpl["code"]}.pdf')
    text = ' '.join(' '.join(p.get_text() for p in d).split())
    d.close()
    vals = parse_d12(text)
    print(f'=== №{did} {tpl["title"][:50]}')
    saved = 0
    for name in [r['name'] for r in conn.execute('SELECT name FROM template_variables WHERE template_id=?',
                                                 (tpl['id'],))]:
        val = vals.get(name)
        if not val:
            continue
        payload = json.dumps([val], ensure_ascii=False)
        cur = conn.execute('SELECT examples_json FROM template_variables WHERE template_id=? AND name=?',
                           (tpl['id'], name)).fetchone()
        if (cur['examples_json'] or '') == payload:
            continue
        conn.execute('UPDATE template_variables SET examples_json=? WHERE template_id=? AND name=?',
                     (payload, tpl['id'], name))
        saved += 1
    conn.commit()
    empty = [r['name'] for r in conn.execute('SELECT name FROM template_variables WHERE template_id=?',
                                             (tpl['id'],)) if not vals.get(r['name'])]
    print(f'   записано: {saved}; без данных (в подлиннике пусто): {", ".join(empty) if empty else "—"}')

# E-02: подлинник — пустой бланк без данных, проверим ещё раз
for did in (10, 11):
    tpl = conn.execute('SELECT id, code, title FROM templates WHERE doc_index=?', (did,)).fetchone()
    d = pymupdf.open(f'/opt/wolf_v2/data/sources/{tpl["code"]}.pdf')
    text = ' '.join(' '.join(p.get_text() for p in d).split())
    d.close()
    dots = len(re.findall(r'\.{4,}|…{2,}', text))
    real = re.findall(r'Full Name\s*:\s*([A-Z][A-Za-z ]{3,})', text)
    print(f'=== №{did} {tpl["title"][:50]}: заполнителей-точек {dots}, реальных ФИО в бланке: {len(real)}')
conn.close()
