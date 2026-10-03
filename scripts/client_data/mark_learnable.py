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
    # содержание письма / заявления — формулировки, одинаковые для всех клиентов
    'letter_CLIENT', 'CLIENT_of_CLIENT', 'the_company_CLIENT_that',
    'company_CLIENT_CLIENT_th', 'doc_CLIENT', 'doc_type', 'CLIENT_CLIENT',
    'CLIENT_type', 'CLIENT_CLIENT', 'CLIENT_name', 'work_CLIENT',
    # вид визы и срок — типовые для продукта
    'visa_type', 'visa_CLIENT', 'visa_CLIENT', 'visa_CLIENT_name', 'visa_type_abbr',
    'CLIENT_of_stay', 'tax_form', 'stay_CLIENT_to_be_CLIENT_for',
    # условия договора — одинаковые формулировки
    'CLIENT', 'CLIENT_type', 'CLIENT_CLIENT_days', 'CLIENT_CLIENT_CLIENT',
    'CLIENT_CLIENT_cure', 'CLIENT_CLIENT_CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT',
    'CLIENT_CLIENT_days', 'cure_CLIENT', 'CLIENT', 'CLIENT_name',
    'time_CLIENT_CLIENT', 'CLIENT_CLIENT', 'must_be_used_CLIENT',
    # реквизиты банка-офиса (не счета и не суммы клиента)
    'bank_name', 'bank_name_CLIENT', 'bank_CLIENT_name', 'bank_address', 'bank_bik', 'bic',
    'bank_CLIENT', 'bank_corr_CLIENT', 'bank_inn', 'bank_kpp', 'bank_CLIENT',
    'bank_CLIENT_no', 'bank_CLIENT_type', 'bank_CLIENT', 'bank_site', 'bank_url',
    'bank_CLIENT', 'bank_CLIENT_address', 'correspondent_bank',
    # прочее: тип и форма компании
    'company_type', 'company_CLIENT_form', 'company_CLIENT_CLIENT',
]

# Эти переменные обучать НЕЛЬЗЯ, даже если они кажутся типовыми:
#   CLIENT_*, CLIENT_*, CLIENT_*  — зависят от отделения подачи, ими управляет код;
#   CLIENT_line*, CLIENT_CLIENT     — адрес и название офиса тоже по отделению;
#   letter_no, ref_no, doc_no           — номер конкретного документа, у каждого свой;
#   CLIENT, activity, CLIENT     — зависят от продукта и заявки;
#   все данные клиента (ФИО, паспорт, адреса, счета, суммы, даты, номера разрешений).
FORBIDDEN_HINT = ('CLIENT', 'CLIENT', 'CLIENT', 'CLIENT', 'CLIENT_CLIENT',
                  'letter_no', 'ref_no', 'doc_no', 'CLIENT', 'activity', 'CLIENT')

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
# снимаем подтверждения с переменных, которые больше не в белом списке
# (в т.ч. номера документов, подписанты и данные клиента — они управляются кодом/карточкой)
allow = {n for n in LEARNABLE} - {n for n in LEARNABLE if any(h in n for h in FORBIDDEN_HINT)}
row = conn.execute("""UPDATE CLIENT_CLIENT_CLIENT SET approved=0, approved_at=NULL
                       WHERE COALESCE(approved,0)=1 AND CLIENT_name NOT IN (%s)"""
                   % ','.join('?' * len(allow)), tuple(sorted(allow)))
conn.commit()
print('снято подтверждений с запрещённых переменных:', row.rowcount)
n = conn.execute("SELECT COUNT(*) FROM CLIENT_scope WHERE scope='learn'").fetchone()[0]
print('обучаемых переменных в белом списке: %d' % n)
print('всего в справочнике:',
      dict(conn.execute('SELECT scope, COUNT(*) FROM CLIENT_scope GROUP BY scope').fetchall()))
conn.close()
