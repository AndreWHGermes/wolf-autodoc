#!/usr/bin/env python3
"""Белый список переменных, на которых системе разрешено учиться.

Обучаться можно только на типовых формулировках и реквизитах, одинаковых для всех
клиентов: адресат иммиграционного офиса, доверенное лицо, спонсор, подписант,
тема письма, цель обращения, разрешение к оформлению, реквизиты банка-офиса,
типовые формулировки документов.

НЕЛЬЗЯ обучаться на данных клиента: ФИО, паспорт, дата и место рождения, адреса
клиента и компании, счета и карты, суммы, номера разрешений и договоров, даты.
Иначе привычка одного клиента подставится в документы другого.

Список хранится в variable_scope со scope='learn'.
Запуск: python3 mark_learnable.py
"""
import sqlite3, sys
sys.path.insert(0, '/opt/wolf_v2')
import os
os.chdir('/opt/wolf_v2')

LEARNABLE = [
    # содержание письма / заявления — формулировки, одинаковые для всех клиентов
    'letter_subject', 'purpose_of_application', 'the_company_confirms_that',
    'company_formally_confirms_th', 'doc_title', 'doc_type', 'document_title',
    'document_type', 'legal_reference', 'service_name', 'work_product',
    # вид визы и срок — типовые для продукта
    'visa_type', 'visa_class', 'visa_category', 'visa_short_name', 'visa_type_abbr',
    'duration_of_stay', 'tax_form', 'stay_permit_to_be_applied_for',
    # условия договора — одинаковые формулировки
    'currency', 'compensation_type', 'change_notification_days', 'change_notification_hours',
    'notice_period_cure', 'notice_period_schedule_change', 'notice_period_termination',
    'termination_notice_days', 'cure_period', 'software', 'software_name',
    'time_tracking_software', 'autogate_eligibility', 'must_be_used_before',
    # реквизиты банка-офиса (не счета и не суммы клиента)
    'bank_name', 'bank_name_short', 'bank_short_name', 'bank_address', 'bank_bik', 'bic',
    'bank_branch', 'bank_corr_branch', 'bank_inn', 'bank_kpp', 'bank_license',
    'bank_license_no', 'bank_license_type', 'bank_phone', 'bank_site', 'bank_url',
    'bank_website', 'bank_header_address', 'correspondent_bank',
    # прочее: тип и форма компании
    'company_type', 'company_legal_form', 'company_registration_state',
]

# Эти переменные обучать НЕЛЬЗЯ, даже если они кажутся типовыми:
#   attorney_*, signatory_*, sponsor_*  — зависят от отделения подачи, ими управляет код;
#   addressee_line*, issuing_office     — адрес и название офиса тоже по отделению;
#   letter_no, ref_no, doc_no           — номер конкретного документа, у каждого свой;
#   guarantor, activity, occupation     — зависят от продукта и заявки;
#   все данные клиента (ФИО, паспорт, адреса, счета, суммы, даты, номера разрешений).
FORBIDDEN_HINT = ('attorney', 'signatory', 'sponsor', 'addressee', 'issuing_office',
                  'letter_no', 'ref_no', 'doc_no', 'guarantor', 'activity', 'occupation')

conn = sqlite3.connect('data/wolf.db')
conn.execute("DELETE FROM variable_scope WHERE scope='learn'")
for name in sorted(set(LEARNABLE)):
    # имя переменной в справочнике уникально: обновляем область, иначе добавляем
    cur = conn.execute("UPDATE variable_scope SET scope='learn', note=? WHERE name=?",
                       ('типовое значение — можно обучаться', name))
    if not cur.rowcount:
        conn.execute("INSERT INTO variable_scope(name, scope, note) VALUES(?, 'learn', ?)",
                     (name, 'типовое значение — можно обучаться'))
conn.commit()
# снимаем подтверждения с переменных, которые больше не в белом списке
# (в т.ч. номера документов, подписанты и данные клиента — они управляются кодом/карточкой)
allow = {n for n in LEARNABLE} - {n for n in LEARNABLE if any(h in n for h in FORBIDDEN_HINT)}
row = conn.execute("""UPDATE variable_value_history SET approved=0, approved_at=NULL
                       WHERE COALESCE(approved,0)=1 AND variable_name NOT IN (%s)"""
                   % ','.join('?' * len(allow)), tuple(sorted(allow)))
conn.commit()
print('снято подтверждений с запрещённых переменных:', row.rowcount)
n = conn.execute("SELECT COUNT(*) FROM variable_scope WHERE scope='learn'").fetchone()[0]
print('обучаемых переменных в белом списке: %d' % n)
print('всего в справочнике:',
      dict(conn.execute('SELECT scope, COUNT(*) FROM variable_scope GROUP BY scope').fetchall()))
conn.close()
