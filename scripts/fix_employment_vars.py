#!/usr/bin/env python3
"""Догоняет переменные трудового договора: заводит в базе и подставляет значения."""
import re
import sqlite3
import sys

sys.path.insert(0, '/opt/wolf_v2')

DB = '/opt/wolf_v2/data/wolf.db'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

t = c.execute("SELECT id FROM templates WHERE code='employment_contract__default'").fetchone()
tid = t['id']

NEW = [
    ('employer_representative', 'organization', 'manual',
     'ФИО руководителя работодателя, подписывающего договор (Director). В пуле организаций нет — заполняется администратором.'),
    ('inn_kpp', 'organization', 'pool', 'ИНН и КПП работодателя из пула организаций (значение company_inn + KPP).'),
    ('ogrn', 'organization', 'pool', 'ОГРН работодателя из пула организаций (company_ogrn).'),
    ('salary_words', 'auto', 'auto', 'Сумма оклада прописью по-английски (monthly_amount_words).'),
    ('registration_address', 'client', 'client_card', 'Адрес регистрации сотрудника из карточки клиента.'),
]
for name, src, method, rule in NEW:
    if c.execute('SELECT 1 FROM template_variables WHERE template_id=? AND name=?', (tid, name)).fetchone():
        continue
    c.execute('''INSERT INTO template_variables
                 (template_id, name, label, vtype, format, source_kind, source_ref, default_value,
                  sort_order, rule_note, approved, method, rule_text)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (tid, name, name, 'text', '', src, '', '', 800, rule, 0, method, rule))
c.commit()

# --- значения ---
from services.values import build_template_values  # noqa: E402

a = c.execute('''SELECT a.id FROM applications a JOIN product_documents pd ON pd.product_id=a.product_id
                 WHERE pd.template_id=? ORDER BY a.id DESC LIMIT 1''', (tid,)).fetchone()
app = a['id']
row = dict(c.execute('SELECT * FROM applications WHERE id=?', (app,)).fetchone())
cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (row['client_id'],)).fetchone()) if row.get('client_id') else {}
vals = build_template_values(cl, 'employment_contract__default', {}, app) or {}

kpp = ''
m = re.search(r'KPP:\s*(\d+)', str(vals.get('inn_kpp_ogrn') or ''))
if m:
    kpp = m.group(1)
print('заявка', app)
print('  company_inn =', vals.get('company_inn'), '| KPP =', kpp, '| company_ogrn =', vals.get('company_ogrn'))
print('  monthly_amount_words =', str(vals.get('monthly_amount_words'))[:50])
print('  address_ru =', str(vals.get('address_ru'))[:40], '| address_live =', str(vals.get('address_live'))[:30])
