#!/usr/bin/env python3
"""Обучение на уже подтверждённых значениях.

В application_documents.values_json лежат значения, с которыми документ был
собран и подтверждён администратором. Если значение отличается от того, что
система собрала бы сама, — значит человек его поправил, и это правило вернее
автогенерации. Помечаем такие значения как подтверждённые (вес +100).

Персональные переменные не обучаются — данные клиента берутся из карточки.

Запуск: python3 learn_from_documents.py [--apply]
"""
import json, os, sqlite3, sys
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
APPLY = '--apply' in sys.argv

from core import db
from services.values import build_template_values

PERSONAL = {
    "balance_value", "balance_rub", "account_no", "contract_no", "card_mask", "doc_no",
    "stay_permit_no", "passport_number", "passport_no", "passport_series", "inn", "snils",
    "phone", "email", "ref_no", "itk_no", "itk_expiry", "company_inn", "company_kpp",
    "company_ogrn", "company_registered_address", "employer_name", "company_name_in_quotes",
    "agreement_date", "term_start_date", "term_end_date", "monthly_amount_numeric",
    "monthly_amount_words", "annual_amount_numeric", "annual_amount_words",
    "passport_issued_by", "passport_issue_date", "passport_expiry", "employee_address",
    "place_of_birth", "date_of_birth", "the_company_confirms_that", "services_list",
    "position_title", "position", "company_name", "full_name_latin",
}
try:
    for r in db.q("SELECT name FROM variable_scope WHERE scope='individual'"):
        PERSONAL.add(r["name"])
except Exception:
    pass

docs = db.q("""SELECT ad.id, ad.application_id, ad.template_id, ad.values_json, t.code AS tpl_code
                 FROM application_documents ad JOIN templates t ON t.id = ad.template_id
                WHERE COALESCE(ad.values_json,'') NOT IN ('', '{}')
                ORDER BY ad.application_id""")
print('документов с сохранёнными значениями: %d' % len(docs))

clients_cache, learned, pairs = {}, [], {}
for d in docs:
    try:
        saved = json.loads(d["values_json"] or "{}")
    except Exception:
        continue
    if not isinstance(saved, dict) or not saved:
        continue
    app = db.q1("SELECT client_id FROM applications WHERE id=?", (d["application_id"],)) or {}
    cid = app.get("client_id")
    if not cid:
        continue
    if cid not in clients_cache:
        clients_cache[cid] = dict(db.q1("SELECT * FROM clients WHERE id=?", (cid,)) or {})
    try:
        auto = build_template_values(clients_cache[cid], d["tpl_code"], None)
    except Exception:
        continue
    for k, v in saved.items():
        if not k or v in (None, "") or k in PERSONAL:
            continue
        sv = str(v).strip()
        if not sv or len(sv) > 600 or '\n' in sv:
            continue
        av = str(auto.get(k) or "").strip()
        if sv == av:
            continue                      # система собрала так же — это не правка
        learned.append((k, sv))
        pairs.setdefault(k, set()).add(sv)

print('отличий от автогенерации (правки человека): %d' % len(learned))
for k in list(pairs)[:14]:
    for v in list(pairs[k])[:2]:
        print('   %-28s %s' % (k, v[:64]))
if APPLY and learned:
    n = 0
    for k, v in learned:
        db.remember_value(k, v, approved=True)
        n += 1
    print()
    print('запомнено подтверждённых значений: %d' % n)
    print('всего подтверждённых переменных:', len(db.approved_values()))
