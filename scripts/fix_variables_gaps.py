#!/usr/bin/env python3
"""Закрывает дыры в переменных: заводит отсутствующие и заполняет пустые источники.

Только то, что подтверждено кодом services/values.py: откуда значение реально берётся.
"""
import sqlite3

DB = '/opt/wolf_v2/data/wolf.db'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

NEW = {
    'bank_statement_3m__sber': [
        ('address_live_2', 'client', 'client_card', 'Вторая строка адреса проживания клиента (город/регион), как в справке банка.'),
        ('balance_words_2', 'client', 'client_card', 'Остаток на счёте прописью для второй строки справки.'),
    ],
    'bank_statement_12m__sber': [
        ('address_live_2', 'client', 'client_card', 'Вторая строка адреса проживания клиента (город/регион), как в справке банка.'),
        ('balance_words_2', 'client', 'client_card', 'Остаток на счёте прописью для второй строки справки.'),
    ],
    'bridging_request_letter__default': [
        ('attorney_citizenship', 'agency_signatory', 'manual', 'Гражданство подписанта агентства (доверенного лица), например Indonesia.'),
        ('citizenship', 'client', 'client_card', 'Гражданство клиента в индонезийской записи (RUSIA, UKRAINE), заглавными.'),
        ('sponsor_company', 'organization', 'pool', 'Компания-спонсор из пула организаций (та же, что в договоре и E-02).'),
    ],
    'conversion_request_letter__default': [
        ('letter_place_date', 'auto', 'auto', 'Место и дата письма (Badung, <дата>), считаются от базовой даты заявки.'),
        ('signatory_address', 'agency', 'manual', 'Адрес подписанта агентства.'),
        ('sponsor_contact', 'organization', 'pool', 'Контакт компании-спонсора (телефон/email) из пула организаций.'),
        ('attorney_occupation', 'agency_signatory', 'manual', 'Должность подписанта агентства (Direktur).'),
    ],
    'd12_cover_letter__default': [
        ('sponsor_address', 'organization', 'pool', 'Адрес компании-спонсора из пула организаций.'),
        ('sponsor_contact', 'organization', 'pool', 'Контакт компании-спонсора (телефон/email).'),
    ],
}

# пустые source_kind по имени переменной
SRC = {
    'letter_no': ('application', 'auto'),
    'letter_subject': ('product', 'auto'),
    'addressee_line1': ('office', 'auto'),
    'addressee_line2': ('office', 'auto'),
    'addressee_line3': ('office', 'auto'),
    'client_gender': ('client', 'client_card'),
    'sponsor_address': ('organization', 'pool'),
    'sponsor_contact': ('organization', 'pool'),
    'attorney_occupation': ('agency_signatory', 'manual'),
    'signatory_address': ('agency', 'manual'),
    'letter_place_date': ('auto', 'auto'),
}

added = fixed = 0
for code, items in NEW.items():
    t = c.execute('SELECT id FROM templates WHERE code=?', (code,)).fetchone()
    if not t:
        print('нет шаблона', code)
        continue
    for name, src, method, rule in items:
        if c.execute('SELECT 1 FROM template_variables WHERE template_id=? AND name=?', (t['id'], name)).fetchone():
            continue
        c.execute('''INSERT INTO template_variables
                     (template_id, name, label, vtype, format, source_kind, source_ref, default_value,
                      sort_order, rule_note, approved, method, rule_text)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (t['id'], name, name, 'text', '', src, '', '',
                   900, rule, 0, method, rule))
        added += 1

for r in [dict(x) for x in c.execute(
        "SELECT id, name, source_kind, method FROM template_variables "
        "WHERE COALESCE(TRIM(source_kind),'')='' OR COALESCE(TRIM(method),'')=''")]:
    src, meth = SRC.get(r['name'], ('', ''))
    if not src:
        continue
    new_src = r['source_kind'] or src
    new_meth = r['method'] or meth
    c.execute('UPDATE template_variables SET source_kind=?, method=? WHERE id=?',
              (new_src, new_meth, r['id']))
    fixed += 1

c.commit()
left = c.execute("SELECT COUNT(*) FROM template_variables WHERE COALESCE(TRIM(source_kind),'')=''").fetchone()[0]
print('заведено переменных:', added, '| заполнено источников:', fixed, '| осталось без источника:', left)
