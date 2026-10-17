#!/usr/bin/env python3
"""Значения примера для писем в иммиграцию (№13-16) из подлинников PT ALPHA PRIME BALI.

Парсим реальные письма из архива образцов: номер письма, дата, тема, адресат,
доверенное лицо, данные иностранца, адрес офиса компании.
"""
import json
import re
import sqlite3

import pymupdf

DB = '/opt/wolf_v2/data/db'
DB = '/opt/wolf_v2/data/wolf.db'

SPONSOR_ADDRESS = 'Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten Gianyar, Bali 80581'
SPONSOR_CONTACT = 'Telp: +62 811 397 9669, Email: ptalphaprimeconsulting@gmail.com'

MONTHS = {'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6, 'juli': 7,
          'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12,
          'january': 1, 'february': 2, 'march': 3, 'may': 5, 'june': 6, 'july': 7,
          'august': 8, 'october': 10, 'november': 11, 'december': 12}


def parse_flat_pairs(t, anchor, labels):
    """Формат писем, где сначала идут все метки, потом через « : » все значения."""
    idx = t.find(anchor)
    if idx < 0:
        return {}
    parts = re.split(r'\s*:\s*', t[idx:idx + 1600])
    out = {}
    for i, lab in enumerate(labels):
        out[lab] = parts[i + 1].strip() if i + 1 < len(parts) else ''
    return out


def iso_of(text):
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', text)
    if not m:
        return ''
    mon = MONTHS.get(m.group(2).lower())
    return f'{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}' if mon else ''


def parse(path):
    d = pymupdf.open(path)
    t = ' '.join(' '.join(p.get_text() for p in d).split())
    d.close()
    v = {}
    m = re.search(r'Nomor:\s*(\S+)', t)
    if m:
        v['letter_no'] = m.group(1)
    m = re.search(r'Hal:\s*(.+?)\s*Kepada Yth', t)
    if m:
        v['letter_subject'] = m.group(1).strip()
    m = re.search(r'Kepada Yth\.?\s*(.+?)\s*Jalan\s+([^,]+),\s*(.+?)\s*Bersama ini', t)
    if m:
        v['addressee_line1'] = m.group(1).strip()
        v['addressee_line2'] = 'Jalan ' + m.group(2).strip()
        v['addressee_line3'] = m.group(3).strip().rstrip(',')
    m = re.search(r'Badung,\s*(\d{1,2}\s+\w+\s+\d{4})', t)
    if m:
        v['date'] = m.group(1)
        v['place_date'] = 'Badung, ' + m.group(1)
        v['date_iso'] = v['date_iso_2'] = v['date_iso_3'] = iso_of(m.group(1))
    # доверенное лицо (penerima kuasa) + подписант
    m = re.search(r'Nama\s*:\s*(Marcellena[^:]*?)\s*Pekerjaan\s*:\s*(\S+)\s*Kewarganegaraan\s*:\s*(\S+)\s*NIK\s*:\s*(\d+)\s*Alamat\s*:\s*(.+?)\s*selaku', t)
    if m:
        v['attorney_name'] = v['signatory_name'] = m.group(1).strip()
        v['attorney_occupation'] = m.group(2).strip()
        v['attorney_citizenship'] = v['signatory_citizenship'] = m.group(3).strip()
        v['attorney_nik'] = m.group(4)
        v['attorney_address'] = v['signatory_address'] = m.group(5).strip()
    # иностранец
    m = re.search(r'Nama\s*:\s*([A-Z][A-Z ]+?)\s*Jenis Kelamin\s*:\s*([^\s]+(?:-[^\s]+)?)\s*'
                  r'Tempat/Tgl\. Lahir\s*:\s*([^/]*)/\s*(\d{2}-\d{2}-\d{4})', t)
    if m:
        v['client_name'] = m.group(1).strip()
        v['client_gender'] = m.group(2).strip()
        v['place_of_birth'] = m.group(3).strip()
    m = re.search(r'Kewarganegaraan\s*:\s*(\S+)\s*No\. Paspor\s*:\s*(\d+)', t)
    if m:
        v['client_nationality'] = m.group(1).strip()
        v['passport_no'] = m.group(2)
    m = re.search(r'Nomor (?:ITK|Bridging Visa)\s*:\s*(\S+)', t)
    if m:
        v['application_no'] = m.group(1)
    v['surname'] = (v.get('client_name') or '').split()[-1] if v.get('client_name') else ''
    # «плоский» формат вёрстки: сначала метки, потом значения
    ATT = ['Nama', 'Pekerjaan', 'Kewarganegaraan', 'NIK', 'Alamat']
    CL = ['Nama', 'Jenis Kelamin', 'Tempat/Tgl. Lahir', 'Kewarganegaraan', 'No. Paspor',
          'Masa Berlaku Paspor', 'Nomor Bridging Visa', 'Masa Berlaku Bridging Visa', 'Alamat']
    if 'Nama Pekerjaan' in t or 'Nama Jenis Kelamin' in t:
        att = parse_flat_pairs(t, 'Nama Pekerjaan', ATT)
        cl = parse_flat_pairs(t, 'Nama Jenis Kelamin', CL)
        if 'Marcellena' in att.get('Nama', ''):
            v.setdefault('attorney_name', att['Nama'])
            v.setdefault('signatory_name', att['Nama'])
            v.setdefault('attorney_occupation', att.get('Pekerjaan', 'Swasta'))
            v.setdefault('attorney_citizenship', att.get('Kewarganegaraan', 'Indonesia'))
            v.setdefault('signatory_citizenship', att.get('Kewarganegaraan', 'Indonesia'))
            v.setdefault('attorney_nik', att.get('NIK', ''))
            v.setdefault('attorney_address', att.get('Alamat', ''))
            v.setdefault('signatory_address', att.get('Alamat', ''))
        if cl.get('Nama'):
            v.setdefault('client_name', cl['Nama'].strip())
            v.setdefault('client_gender', cl.get('Jenis Kelamin', ''))
            v.setdefault('client_nationality', cl.get('Kewarganegaraan', ''))
            v.setdefault('passport_no', cl.get('No. Paspor', ''))
            v.setdefault('application_no', cl.get('Nomor Bridging Visa', ''))
            v.setdefault('bridging_visa_no', cl.get('Nomor Bridging Visa', ''))
            v.setdefault('address_live', cl.get('Alamat', ''))
            pob = cl.get('Tempat/Tgl. Lahir', '')
            v.setdefault('place_of_birth', pob.split('/')[0].strip())
            v.setdefault('place_date_of_birth', pob.replace('/', ',').strip())
            v.setdefault('surname', cl['Nama'].split()[-1])
    # адрес клиента (в других форматах)
    if not v.get('address_live'):
        m = re.search(r'(?:Bridging Visa|Visa)\s*(?:Masa Berlaku[^:]*:\s*[\d-]+\s*)?Alamat\s*:\s*(.+?)\s*Demikian', t)
        if m:
            v['address_live'] = m.group(1).strip()
    # адресат: разбиваем «Kepada Yth … Bersama ini» на три строки
    if not v.get('addressee_line1'):
        m = re.search(r'Kepada Yth\.?\s*(.+?)\s*Bersama ini', t)
        if m:
            addr = m.group(1).strip()
            head = re.split(r'\s+(?=J(?:l|alan)\b)', addr, maxsplit=1)
            v['addressee_line1'] = head[0].strip().rstrip(',')
            if len(head) > 1:
                tail = head[1].strip()
                cut = re.split(r',\s*(?=Kec\.|Kecamatan|Kota|Kabupaten)', tail, maxsplit=1)
                v['addressee_line2'] = cut[0].strip().rstrip(',')
                v['addressee_line3'] = cut[1].strip() if len(cut) > 1 else ''
    v['sponsor_name'] = v['sponsor_company'] = 'PT ALPHA PRIME BALI'
    v['sponsor_address'] = SPONSOR_ADDRESS
    v['sponsor_contact'] = SPONSOR_CONTACT
    v['sponsor_person_name'] = 'Marcellena Nirmala Chrisna Moeri'
    return v


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
for did in (13, 14, 15, 16):
    tpl = conn.execute('SELECT id, code, title FROM templates WHERE doc_index=?', (did,)).fetchone()
    vals = parse(f'/opt/wolf_v2/data/sources/{tpl["code"]}.pdf')
    print(f'=== №{did} {tpl["title"][:52]}')
    saved = 0
    for name in [r['name'] for r in conn.execute('SELECT name FROM template_variables WHERE template_id=?',
                                                 (tpl['id'],))]:
        if name not in vals or not vals[name]:
            continue
        payload = json.dumps([vals[name]], ensure_ascii=False)
        cur = conn.execute('SELECT examples_json FROM template_variables WHERE template_id=? AND name=?',
                           (tpl['id'], name)).fetchone()
        if (cur['examples_json'] or '') == payload:
            continue
        conn.execute('UPDATE template_variables SET examples_json=? WHERE template_id=? AND name=?',
                     (payload, tpl['id'], name))
        saved += 1
        print(f'   {name:20} = {vals[name][:64]}')
    conn.commit()
    empty = [r['name'] for r in conn.execute('SELECT name FROM template_variables WHERE template_id=?',
                                             (tpl['id'],)) if not vals.get(r['name'])]
    print(f'   записано: {saved}; без данных: {", ".join(empty) if empty else "—"}\n')
conn.close()
