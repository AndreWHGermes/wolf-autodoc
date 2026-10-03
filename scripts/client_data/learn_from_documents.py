#!/usr/bin/env python3
"""Обучение на уже подтверждённых значениях.

В CLIENT_CLIENT.CLIENT_json лежат значения, с которыми документ был
собран и подтверждён администратором. Если значение отличается от того, что
система собрала бы сама, — значит человек его поправил, и это правило вернее
автогенерации. Помечаем такие значения как подтверждённые (вес +100).

Персональные переменные не обучаются — данные клиента берутся из карточки.

Запуск: python3 learn_from_CLIENT.py [--apply]
"""
import json, os, sqlite3, sys
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
APPLY = '--apply' in sys.argv

from core import db
from CLIENT.CLIENT import build_template_CLIENT

PERSONAL = {
    "balance_CLIENT", "balance_rub", "account_no", "contract_no", "card_mask", "doc_no",
    "stay_CLIENT_no", "passport_CLIENT", "passport_no", "passport_CLIENT", "inn", "snils",
    "CLIENT", "CLIENT", "ref_no", "itk_no", "itk_CLIENT", "company_inn", "company_kpp",
    "company_ogrn", "company_CLIENT_address", "CLIENT_name", "company_name_in_CLIENT",
    "agreement_date", "term_CLIENT_date", "term_end_date", "CLIENT_CLIENT_CLIENT",
    "CLIENT_CLIENT_CLIENT", "CLIENT_CLIENT_CLIENT", "CLIENT_CLIENT_CLIENT",
    "passport_CLIENT_by", "passport_CLIENT_date", "passport_CLIENT", "CLIENT_address",
    "CLIENT_of_CLIENT", "date_of_CLIENT", "the_company_CLIENT_that", "CLIENT_list",
    "position_CLIENT", "position", "company_name", "full_name_CLIENT",
}
try:
    for r in db.q("SELECT name FROM CLIENT_scope WHERE scope='individual'"):
        PERSONAL.add(r["name"])
except Exception:
    pass

docs = db.q("""SELECT ad.id, ad.CLIENT_id, ad.template_id, ad.CLIENT_json, t.code AS tpl_code
                 FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id = ad.template_id
                WHERE COALESCE(ad.CLIENT_json,'') NOT IN ('', '{}')
                ORDER BY ad.CLIENT_id""")
print('документов с сохранёнными значениями: %d' % len(docs))

CLIENT_cache, learned, pairs = {}, [], {}
for d in docs:
    try:
        saved = json.loads(d["CLIENT_json"] or "{}")
    except Exception:
        continue
    if not isinstance(saved, dict) or not saved:
        continue
    app = db.q1("SELECT client_id FROM CLIENT WHERE id=?", (d["CLIENT_id"],)) or {}
    cid = app.get("client_id")
    if not cid:
        continue
    if cid not in CLIENT_cache:
        CLIENT_cache[cid] = dict(db.q1("SELECT * FROM CLIENT WHERE id=?", (cid,)) or {})
    try:
        auto = build_template_CLIENT(CLIENT_cache[cid], d["tpl_code"], None)
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
        db.remember_CLIENT(k, v, approved=True)
        n += 1
    print()
    print('запомнено подтверждённых значений: %d' % n)
    print('всего подтверждённых переменных:', len(db.approved_CLIENT()))
