"""Сборка одного документа заявки: HTML → PDF, с проверкой паспортных значений.

Запуск: /usr/bin/python3 scripts/build_one_doc.py <application_id> <template_id> [out.pdf]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
from services import render as R  # noqa: E402
from core import db as D  # noqa: E402

app_id = int(sys.argv[1])
tpl_id = int(sys.argv[2])
out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/doc_%d_%d.pdf" % (app_id, tpl_id))

vals = {}
vals.update(R.client_values(app_id))
stored = R.stored_values(app_id, tpl_id)
tpl = D.q1("SELECT code, title FROM templates WHERE id=?", (tpl_id,))
cl = D.q1("""SELECT c.* FROM clients c JOIN applications a ON a.client_id=c.id WHERE a.id=?""", (app_id,))
# значения считает та же функция, что и в интерфейсе: договорные даты, должность, паспортные даты
from services.values import build_template_values  # noqa: E402
computed = build_template_values(dict(cl), tpl["code"], stored) or {}
vals.update(computed)
html = R.render_html(template_id=tpl_id, values=vals)
pdf = R.render_pdf(html, out_path=out)

print("заявка %d | документ: %s (%s)" % (app_id, tpl["title"], tpl["code"]))
print("PDF:", pdf)

print("\n=== паспортные данные клиента в карточке ===")
for k in ("full_name_latin", "surname", "name", "birth_date", "birth_place",
          "nationality", "passport_number", "passport_issue_date", "passport_expiry", "address_live"):
    print("  %-22s %s" % (k, cl.get(k) or "—"))

print("\n=== что подставилось в документ ===")
import pymupdf  # noqa: E402
doc = pymupdf.open(pdf)
text = "\n".join(p.get_text() for p in doc)
pages = doc.page_count
doc.close()
for label, need in (("ФИО латиницей", cl.get("full_name_latin")),
                    ("Место рождения", cl.get("birth_place")),
                    ("Гражданство", cl.get("nationality")),
                    ("Номер паспорта", cl.get("passport_number")),
                    ("Дата выдачи паспорта", cl.get("passport_issue_date")),
                    ("Срок паспорта", cl.get("passport_expiry")),
                    ("Дата рождения", cl.get("birth_date"))):
    if not need:
        continue
    hit = str(need).lower() in text.lower()
    short = str(need)
    # сокращённая проверка для «OLEG BUDKO» / «BUDKO OLEG»
    hit = hit or all(part.lower() in text.lower() for part in short.split())
    print("  %-22s %-28s %s" % (label, short[:28], "в документе ✓" if hit else "НЕ найдено ✗"))
print("\nстраниц в PDF:", pages)
