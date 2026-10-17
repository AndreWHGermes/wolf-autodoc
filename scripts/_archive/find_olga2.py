
import sqlite3, sys, os, re, json
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from services import render as doc_render
from core import pdf2html

c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
NEEDLES = ("МАКАРОВ", "ОЛЬГА", "OLGA", "MAKAROVA")
print("=== кириллица/латиница по всем таблицам")
hits = 0
for t in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
    cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
    for col in cols:
        for n in NEEDLES:
            try:
                for r in c.execute("SELECT * FROM %s WHERE upper(coalesce(CAST(%s AS TEXT),'')) LIKE ?" % (t, col), ("%" + n + "%",)):
                    d = {k: str(v)[:70] for k, v in dict(r).items() if v and any(x in str(v).upper() for x in NEEDLES)}
                    print("   %-20s %s" % (t, d))
                    hits += 1
                    break
            except Exception:
                pass
print("   всего записей:", hits)
print()
print("=== поиск по файлам данных (паспорта, кэш Google Drive)")
import subprocess
out = subprocess.run("grep -ril 'МАКАРОВ\|MAKAROVA' /opt/wolf_v2/data /opt/wolf_v2/data 2>/dev/null | head -12", shell=True, capture_output=True, text=True).stdout
print(out or "   ничего не найдено")
print()
print("=== Т-Банк: двухстрочные ФИО и адрес — нет ли наложений")
html = open("data/templates/bank_statement_3m__tbank/template.html", encoding="utf-8").read()
vals = {"client_name": "ALEKSANDROVSKAYA-SEMENOVA OLGA SERGEEVNA",
        "address_live": "350901, Krasnodarskiy Krai, Krasnodar, ul Rossiyskaya, d. 79/3, korp. 1, kv. 653",
        "doc_date": "01.10.2026"}
filled = doc_render.fill(html, vals, keep_unfilled=True, template_code="bank_statement_3m__tbank")
open("/tmp/d1c.html", "w", encoding="utf-8").write(filled)
pdf2html.render_pdf("/tmp/d1c.html", "/tmp/d1c.pdf")
d = pymupdf.open("/tmp/d1c.pdf")
rows = []
for b in d[0].get_text("dict")["blocks"]:
    for l in b.get("lines", []):
        t = "".join(s["text"] for s in l["spans"]).strip()
        if t and 140 < l["bbox"][1] < 215:
            rows.append((round(l["bbox"][1], 1), round(l["bbox"][0], 1), round(l["bbox"][2], 1), t[:72]))
seen = {}
for y, x0, x1, t in sorted(rows):
    clash = [yy for yy in seen if abs(yy - y) < 8 and x0 < seen[yy] - 5]
    print("   y %6.1f x %6.1f..%6.1f %s%s" % (y, x0, x1, t, "  <-- ПЕРЕКРЫТИЕ" if clash else ""))
    seen[y] = x1
d[0].get_pixmap(dpi=140, clip=pymupdf.Rect(0, 135, 600, 215)).save("reports/visual/doc1_long.png")
d.close()
