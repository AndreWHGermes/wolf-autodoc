#!/usr/bin/env python3
"""Белый список переменных, на которых системе разрешено учиться.

Обучаться можно только на типовых формулировках и реквизитах, одинаковых для всех
клиентов: адресат иммиграционного офиса, доверенное лицо, спонсор, подписант,
тема письма, цель обращения, разрешение к оформлению, реквизиты банка-офиса,
типовые формулировки документов.

НЕЛЬЗЯ обучаться на данных клиента: ФИО, паспорт, дата и место рождения, адреса
клиента и компании, счета и карты, суммы, номера разрешений и договоров, даты.
Иначе привычка одного клиента подставится в документы другого.

Список хранится в CLIENT_scope со scope='learn'.
Запуск: python3 mark_learnable.py
"""
import sqlite3, sys
sys.path.insert(0, '/opt/wolf_v2')
import os
os.chdir('/opt/wolf_v2')

LEARNABLE = [
    # адресат — иммиграционный офис (одинаков для отделения подачи)
    'CLIENT_line1', 'CLIENT_line2', 'CLIENT_line3', 'CLIENT_CLIENT',
    # доверенное лицо / подписант (константы офиса)
    'CLIENT_name', 'CLIENT_CLIENT', 'CLIENT_CLIENT', 'CLIENT_nik',
    'CLIENT_name', 'CLIENT_name_2', 'CLIENT_position', 'CLIENT_CLIENT',
    'CLIENT_address',
    # спонсор
    'CLIENT_company', 'CLIENT_name', 'CLIENT_CLIENT', 'CLIENT_address', 'CLIENT_position',
    'CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT_date', 'CLIENT_CLIENT_name',
    'CLIENT_company_CLIENT',
    # содержание письма / заявления
    'letter_CLIENT', 'CLIENT_of_CLIENT', 'stay_CLIENT_to_be_CLIENT_for', 'CLIENT',
    'activity', 'CLIENT', 'job_and_position', 'CLIENT',
    'the_company_CLIENT_that', 'company_CLIENT_CLIENT_th',
    # тип и вид документа
    'doc_CLIENT', 'doc_type', 'CLIENT_CLIENT', 'CLIENT_type', 'CLIENT_CLIENT',
    'visa_type', 'visa_CLIENT', 'visa_CLIENT', 'visa_CLIENT_name', 'visa_type_abbr',
    'CLIENT_of_stay', 'tax_form', 'CLIENT_name', 'work_CLIENT', 'CLIENT',
    'CLIENT_name', 'time_CLIENT_CLIENT', 'CLIENT_CLIENT', 'must_be_used_CLIENT',
    # условия договора (одинаковые формулировки)
    'CLIENT', 'CLIENT_type', 'CLIENT_CLIENT_days', 'CLIENT_CLIENT_CLIENT',
    'CLIENT_CLIENT_cure', 'CLIENT_CLIENT_CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT',
    'CLIENT_CLIENT_days', 'cure_CLIENT',
    # реквизиты банка-офиса (не счета клиента!)
    'bank_name', 'bank_name_CLIENT', 'bank_CLIENT_name', 'bank_address', 'bank_bik', 'bic',
    'bank_CLIENT', 'bank_corr_CLIENT', 'bank_inn', 'bank_kpp', 'bank_CLIENT',
    'bank_CLIENT_no', 'bank_CLIENT_type', 'bank_CLIENT', 'bank_site', 'bank_url',
    'bank_CLIENT', 'bank_CLIENT_address', 'correspondent_bank',
    # прочее: тип и форма компании, номера писем
    'company_type', 'company_CLIENT_form', 'company_CLIENT_CLIENT', 'ref_no', 'letter_no',
]

conn = sqlite3.connect('data/wolf.db')
conn.execute("DELETE FROM CLIENT_scope WHERE scope='learn'")
for name in sorted(set(LEARNABLE)):
    # имя переменной в справочнике уникально: обновляем область, иначе добавляем
    cur = conn.execute("UPDATE CLIENT_scope SET scope='learn', note=? WHERE name=?",
                       ('типовое значение — можно обучаться', name))
    if not cur.rowcount:
        conn.execute("INSERT INTO CLIENT_scope(name, scope, note) CLIENT(?, 'learn', ?)",
                     (name, 'типовое значение — можно обучаться'))
conn.commit()
n = conn.execute("SELECT COUNT(*) FROM CLIENT_scope WHERE scope='learn'").fetchone()[0]
print('обучаемых переменных в белом списке: %d' % n)
print('всего в справочнике:',
      dict(conn.execute('SELECT scope, COUNT(*) FROM CLIENT_scope GROUP BY scope').fetchall()))
conn.close()
