
import os, sys, re, json, sqlite3
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from services import render as doc_render
from core import pdf2html

c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
print("=== шаблоны: какой документ №1")
for r in c.execute("SELECT id, code, doc_index, title FROM templates ORDER BY id LIMIT 5"):
    print("   id=%s doc_index=%s %s" % (r["id"], r["doc_index"], r["code"]))
print()
print("=== поиск OLGA MAKAROVA в базе")
for t, q in (("clients", "SELECT id, surname, name, patronymic, full_name_latin FROM clients WHERE upper(surname||' '||name||' '||coalesce(patronymic,'')) LIKE '%MAKAROVA%' OR upper(coalesce(full_name_latin,'')) LIKE '%MAKAROVA%'"),
             ("applications", "SELECT id, client_id, applicant_name FROM applications WHERE upper(coalesce(applicant_name,'')) LIKE '%MAKAROVA%'"),
             ("template_variables", "SELECT template_id, name, default_value FROM template_variables WHERE upper(coalesce(default_value,'')) LIKE '%MAKAROVA%'")):
    try:
        for r in c.execute(q):
            print("   %s: %s" % (t, dict(r)))
    except Exception as e:
        print("   %s: ошибка %s" % (t, e))
print()
print("=== рендер документа id=2 (Т-Банк 3 мес) и проверка наложений")
TID, CODE = 2, "bank_statement_3m__tbank"
vals = {}
for r in c.execute("SELECT name, default_value, examples_json FROM template_variables WHERE template_id=?", (TID,)):
    v = r["default_value"] or ""
    if not v and r["examples_json"]:
        try:
            j = json.loads(r["examples_json"]); v = j[0] if isinstance(j, list) and j else ""
        except Exception:
            v = ""
    vals[r["name"]] = v
print("   client_name из базы:", repr(vals.get("client_name")), "| address:", repr((vals.get("address_live") or "")[:40]))
html = open("data/templates/%s/template.html" % CODE, encoding="utf-8").read()
filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=CODE)
open("/tmp/d1.html", "w", encoding="utf-8").write(filled)
pdf2html.render_pdf("/tmp/d1.html", "/tmp/d1.pdf")
d = pymupdf.open("/tmp/d1.pdf")
rows = []
for b in d[0].get_text("dict")["blocks"]:
    for l in b.get("lines", []):
        t = "".join(s["text"] for s in l["spans"]).strip()
        if t and 130 < l["bbox"][1] < 215:
            rows.append((round(l["bbox"][1], 1), round(l["bbox"][0], 1), round(l["bbox"][2], 1), t[:78]))
for y, x0, x1, t in sorted(rows):
    print("   y %6.1f x %6.1f..%6.1f  %s" % (y, x0, x1, t))
d[0].get_pixmap(dpi=140, clip=pymupdf.Rect(0, 120, 600, 230)).save("reports/visual/doc1_zone.png")
d.close()
