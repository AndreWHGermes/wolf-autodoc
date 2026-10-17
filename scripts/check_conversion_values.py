#!/usr/bin/env python3
"""Что система отдаёт для письма конверсии: имена значений, пригодные для общего каркаса."""
import sqlite3
import sys
sys.path.insert(0, '/opt/wolf_v2')
from services.values import build_template_values

c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row
app = c.execute('''SELECT a.id FROM applications a JOIN product_documents pd ON pd.product_id=a.product_id
                   JOIN templates t ON t.id=pd.template_id
                   WHERE t.code='conversion_request_letter__default' ORDER BY a.id DESC LIMIT 1''').fetchone()
app_id = app['id']
a = dict(c.execute('SELECT * FROM applications WHERE id=?', (app_id,)).fetchone())
cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone()) if a.get('client_id') else {}
vals = build_template_values(cl, 'conversion_request_letter__default', {}, app_id) or {}
print('заявка', app_id, '| значений', len(vals))
for k in ('letter_no', 'letter_subject', 'addressee_line1', 'addressee_line2', 'addressee_line3',
          'sponsor_company', 'sponsor_name', 'body_request_line', 'attorney_name', 'attorney_address',
          'attorney_nik', 'attorney_citizenship', 'attorney_occupation', 'signatory_position',
          'place_date', 'letter_place_date', 'client_name', 'client_gender', 'place_birth_inline',
          'citizenship', 'client_nationality', 'passport_no', 'passport_expiry', 'itk_no', 'itk_expiry',
          'client_address', 'sponsor_address', 'sponsor_contact', 'signatory_address'):
    v = str(vals.get(k) or '').strip()
    print(f'  {k:<22} {"ЕСТЬ" if v else "пусто":<6} {v[:44]}')
