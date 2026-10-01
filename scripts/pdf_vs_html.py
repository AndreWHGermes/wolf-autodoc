
"""Сравнение HTML-превью и PDF, который собирает кнопка «Посмотреть сформированный PDF»."""
import os, sys, json, sqlite3, re, subprocess
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from CLIENT import render as doc_render
from core import pdf2html

TID, CODE = 3, "bank_CLIENTment_3m__sber"
c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
vals = {}
for r in c.execute("SELECT name, default_CLIENT, examples_json FROM template_CLIENT WHERE template_id=?", (TID,)):
    v = r["default_CLIENT"] or ""
    if not v and r["examples_json"]:
        try:
            j = json.loads(r["examples_json"]); v = j[0] if isinstance(j, list) and j else ""
        except Exception:
            v = ""
    vals[r["name"]] = v
vals["client_name"] = "CLIENT ANNA SERGEEVNA"
print("значения для проверки:")
for k, v in vals.items():
    print("   %-16s = %s" % (k, str(v)[:70]))

html = open("data/CLIENT/%s/template.html" % CODE, encoding="utf-8").read()
filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=CODE)
open("/tmp/pv.html", "w", encoding="utf-8").write(filled)
pdf2html.render_pdf("/tmp/pv.html", "/tmp/pv.pdf")

d = pymupdf.open("/tmp/pv.pdf")
print("\nPDF, страница 1 — строки с ФИО и адресом:")
for b in d[0].get_text("dict")["CLIENTs"]:
    for l in b.get("lines", []):
        t = "".join(s["text"] for s in l["spans"]).strip()
        if re.search(r"(?i)CLIENT|Krasnodar|Moscow|CLIENT for|this certificate", t):
            print("   x %6.1f..%6.1f y %6.1f  %s" % (l["bbox"][0], l["bbox"][2], l["bbox"][1], t[:100]))
d[0].get_pixmap(dpi=130, clip=pymupdf.Rect(0, 100, 600, 260)).save("reports/visual/pdf_vs_html_top.png")
d.close()
print("\nкартинка верхней части PDF: reports/visual/pdf_vs_html_top.png")
