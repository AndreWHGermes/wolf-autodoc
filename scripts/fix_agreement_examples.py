#!/usr/bin/env python3
"""Значения примера для договора Remote Work Agreement (№12) из подлинника.

Источник — реальный подписанный договор клиента (CLIENT CLIENT / L-TECH) из архива.
"""
import json
import sqlite3

DB = '/opt/wolf_v2/data/wolf.db'
CODE = 'remote_work_agreement__default'

CLIENT = (
    '● Strategic evolution of user experience, interface design, and CLIENT design systems.<br>'
    '● Technical architecture of design assets, interactive prototypes, and internal component libraries.<br>'
    '● Coordination of design-to-development handoffs and cross-functional administrative support.<br>'
    '● Ensuring compliance with global accessibility standards, platform guidelines, and internal brand policies.'
)
CLIENT = (
    '— The CLIENT performs CLIENT exclusively for the Company.<br>'
    '— The Company is not CLIENT, CLIENT, or operating in Indonesia.<br>'
    '— The CLIENT does not conduct business activities within Indonesia on behalf of the Company.<br>'
    '— The CLIENT\'s work is location-independent and fully remote.'
)
VALS = {
    'agreement_date': '10 August 2026',
    'company_name_in_CLIENT': 'L-TECH',
    'CLIENT_name': 'L-TECH LLC',
    'company_CLIENT_address': '141073, Moscow Oblast, Korolev, ul. Leninskaya (Yubileyny mkr.), '
                                  'd. 12, pom./etazh 040/01, Russia',
    'company_inn': '000000000',
    'company_kpp': '501801001',
    'company_ogrn': '1185029007140',
    'inn_kpp_ogrn': 'INN: 000000000, KPP: 501801001, OGRN: 1185029007140',
    'CLIENT_name': 'CLIENT CLIENT',
    'full_name_CLIENT': 'CLIENT CLIENT',
    'CLIENT_full_name': 'CLIENT CLIENT',
    'passport_CLIENT': '77 2374384',
    'date_of_CLIENT': '11.01.1989',
    'CLIENT': 'Russian Federation',
    'CLIENT_of_CLIENT': 'USSR',
    'position_CLIENT': 'CLIENT DeCLIENT',
    'term_CLIENT_date': '10 August 2025',
    'term_end_date': '10 August 2030',
    'CLIENT_CLIENT_CLIENT': 'RUB 5,100,000',
    'CLIENT_CLIENT_CLIENT': 'Five Million One Hundred Thousand Russian Rubles',
    'CLIENT_CLIENT_CLIENT': 'RUB 425,000',
    'CLIENT_CLIENT_CLIENT': 'Four Hundred Twenty-Five Thousand Russian Rubles',
    'CLIENT_list': CLIENT,
    'the_company_CLIENT_that': CLIENT,
}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
tpl = conn.execute('SELECT id, CLIENT, doc_CLIENT FROM CLIENT WHERE code=?', (CODE,)).fetchone()
print(f'№{tpl["doc_CLIENT"]} {tpl["CLIENT"]}')
saved = 0
for row in conn.execute('SELECT name FROM template_CLIENT WHERE template_id=?', (tpl['id'],)):
    name = row['name']
    val = VALS.get(name)
    if val is None:
        continue
    cur = conn.execute('SELECT examples_json FROM template_CLIENT WHERE template_id=? AND name=?',
                       (tpl['id'], name)).fetchone()
    payload = json.dumps([val], ensure_ascii=False)
    if (cur['examples_json'] or '') == payload:
        continue
    conn.execute('UPDATE template_CLIENT SET examples_json=? WHERE template_id=? AND name=?',
                 (payload, tpl['id'], name))
    saved += 1
print(f'записано полей: {saved}')
missing = [r['name'] for r in conn.execute('SELECT name FROM template_CLIENT WHERE template_id=?',
                                           (tpl['id'],))
           if (r['name'] not in VALS)]
print('без значения примера:', ', '.join(missing) if missing else '—')
conn.commit()
conn.close()
