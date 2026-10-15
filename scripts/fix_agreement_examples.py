#!/usr/bin/env python3
"""Значения примера для договора Remote Work Agreement (№12) из подлинника.

Источник — реальный подписанный договор клиента (VASILEV CLIENT / L-TECH) из архива.
"""
import json
import sqlite3

DB = '/opt/wolf_v2/data/wolf.db'
CODE = 'remote_work_agreement__default'

SERVICES = (
    '● Strategic evolution of user experience, interface design, and product design systems.<br>'
    '● Technical architecture of design assets, interactive prototypes, and internal component libraries.<br>'
    '● Coordination of design-to-development handoffs and cross-functional administrative support.<br>'
    '● Ensuring compliance with global accessibility standards, platform guidelines, and internal brand policies.'
)
CONFIRMS = (
    '— The Contractor performs services exclusively for the Company.<br>'
    '— The Company is not incorporated, registered, or operating in Indonesia.<br>'
    '— The Contractor does not conduct business activities within Indonesia on behalf of the Company.<br>'
    '— The Contractor\'s work is location-independent and fully remote.'
)
VALS = {
    'agreement_date': '10 August 2026',
    'company_name_in_quotes': 'L-TECH',
    'employer_name': 'L-TECH LLC',
    'company_registered_address': '141073, Moscow Oblast, Korolev, ul. Leninskaya (Yubileyny mkr.), '
                                  'd. 12, pom./etazh 040/01, Russia',
    'company_inn': '000000000',
    'company_kpp': '501801001',
    'company_ogrn': '1185029007140',
    'inn_kpp_ogrn': 'INN: 000000000, KPP: 501801001, OGRN: 1185029007140',
    'employee_name': 'VASILEV CLIENT',
    'full_name_latin': 'VASILEV CLIENT',
    'contractor_full_name': 'VASILEV CLIENT',
    'passport_number': '77 2374384',
    'date_of_birth': '11.01.1989',
    'nationality': 'Russian Federation',
    'place_of_birth': 'USSR',
    'position_title': 'Product Designer',
    'term_start_date': '10 August 2025',
    'term_end_date': '10 August 2030',
    'annual_amount_numeric': 'RUB 5,100,000',
    'annual_amount_words': 'Five Million One Hundred Thousand Russian Rubles',
    'monthly_amount_numeric': 'RUB 425,000',
    'monthly_amount_words': 'Four Hundred Twenty-Five Thousand Russian Rubles',
    'services_list': SERVICES,
    'the_company_confirms_that': CONFIRMS,
}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
tpl = conn.execute('SELECT id, title, doc_index FROM templates WHERE code=?', (CODE,)).fetchone()
print(f'№{tpl["doc_index"]} {tpl["title"]}')
saved = 0
for row in conn.execute('SELECT name FROM template_variables WHERE template_id=?', (tpl['id'],)):
    name = row['name']
    val = VALS.get(name)
    if val is None:
        continue
    cur = conn.execute('SELECT examples_json FROM template_variables WHERE template_id=? AND name=?',
                       (tpl['id'], name)).fetchone()
    payload = json.dumps([val], ensure_ascii=False)
    if (cur['examples_json'] or '') == payload:
        continue
    conn.execute('UPDATE template_variables SET examples_json=? WHERE template_id=? AND name=?',
                 (payload, tpl['id'], name))
    saved += 1
print(f'записано полей: {saved}')
missing = [r['name'] for r in conn.execute('SELECT name FROM template_variables WHERE template_id=?',
                                           (tpl['id'],))
           if (r['name'] not in VALS)]
print('без значения примера:', ', '.join(missing) if missing else '—')
conn.commit()
conn.close()
