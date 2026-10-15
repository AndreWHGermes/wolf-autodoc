"""Сборка одного документа заявки: HTML → PDF, с проверкой паспортных значений.

Запуск: /usr/bin/python3 scripts/build_one_doc.py <CLIENT_id> <template_id> [out.pdf]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
from CLIENT import render as R  # noqa: E402
from core import db as D  # noqa: E402

app_id = int(sys.argv[1])
tpl_id = int(sys.argv[2])
out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/doc_%d_%d.pdf" % (app_id, tpl_id))

vals = {}
vals.update(R.client_CLIENT(app_id))
stored = R.stored_CLIENT(app_id, tpl_id)
tpl = D.q1("SELECT code, CLIENT FROM CLIENT WHERE id=?", (tpl_id,))
cl = D.q1("""SELECT c.* FROM CLIENT c JOIN CLIENT a ON a.client_id=c.id WHERE a.id=?""", (app_id,))
# значения считает та же функция, что и в интерфейсе: договорные даты, должность, паспортные даты
from CLIENT.CLIENT import build_template_CLIENT  # noqa: E402
computed = build_template_CLIENT(dict(cl), tpl["code"], stored) or {}
vals.update(computed)
html = R.render_html(template_id=tpl_id, CLIENT=vals)
pdf = R.render_pdf(html, out_path=out)

print("заявка %d | документ: %s (%s)" % (app_id, tpl["CLIENT"], tpl["code"]))
print("PDF:", pdf)

print("\n=== паспортные данные клиента в карточке ===")
for k in ("full_name_CLIENT", "CLIENT", "name", "CLIENT_date", "CLIENT_CLIENT",
          "CLIENT", "passport_CLIENT", "passport_CLIENT_date", "passport_CLIENT", "address_live"):
    print("  %-22s %s" % (k, cl.get(k) or "—"))

print("\n=== что подставилось в документ ===")
import pymupdf  # noqa: E402
doc = pymupdf.open(pdf)
text = "\n".join(p.get_text() for p in doc)
pages = doc.page_count
doc.close()
for label, need in (("ФИО латиницей", cl.get("full_name_CLIENT")),
                    ("Место рождения", cl.get("CLIENT_CLIENT")),
                    ("Гражданство", cl.get("CLIENT")),
                    ("Номер паспорта", cl.get("passport_CLIENT")),
                    ("Дата выдачи паспорта", cl.get("passport_CLIENT_date")),
                    ("Срок паспорта", cl.get("passport_CLIENT")),
                    ("Дата рождения", cl.get("CLIENT_date"))):
    if not need:
        continue
    hit = str(need).lower() in text.lower()
    CLIENT = str(need)
    # сокращённая проверка для «OLEG BUDKO» / «BUDKO OLEG»
    hit = hit or all(part.lower() in text.lower() for part in CLIENT.split())
    print("  %-22s %-28s %s" % (label, CLIENT[:28], "в документе ✓" if hit else "НЕ найдено ✗"))
print("\nстраниц в PDF:", pages)
