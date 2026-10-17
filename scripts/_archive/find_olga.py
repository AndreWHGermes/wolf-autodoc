
import sqlite3, sys, os, json, re
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from services import render as doc_render
from core import pdf2html

c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("=== где в базе встречается MAKAROVA / OLGA")
for t in tables:
    cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
    txt_cols = [x for x in cols]
    for col in txt_cols:
        try:
            q = "SELECT rowid, * FROM %s WHERE upper(coalesce(CAST(%s AS TEXT),'')) LIKE '%%MAKAROVA%%'" % (t, col)
            for r in c.execute(q):
                d = dict(r)
                interesting = {k: str(v)[:60] for k, v in d.items() if v and ("MAKAROVA" in str(v).upper() or "OLGA" in str(v).upper() or "патрон" in k.lower() or "patronym" in k.lower() or "name" in k.lower())}
                print("   %s: %s" % (t, interesting))
                break
        except Exception:
            pass
print()
print("=== рендер Т-Банка с ФИО и отчеством: не наползает ли адрес")
html = open("data/templates/bank_statement_3m__tbank/template.html", encoding="utf-8").read()
for fio in ("OLGA MAKAROVA", "OLGA MAKAROVA SERGEEVNA"):
    vals = {"client_name": fio, "address_live": "115191, Moscow, Ul Bol'shaya Tul'skaya, D. 2, Kv. 846", "doc_date": "01.10.2026"}
    filled = doc_render.fill(html, vals, keep_unfilled=True, template_code="bank_statement_3m__tbank")
    open("/tmp/d1b.html", "w", encoding="utf-8").write(filled)
    pdf2html.render_pdf("/tmp/d1b.html", "/tmp/d1b.pdf")
    d = pymupdf.open("/tmp/d1b.pdf")
    print("   ---", fio)
    rows = []
    for b in d[0].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t and 145 < l["bbox"][1] < 205 and l["bbox"][0] > 60:
                rows.append((round(l["bbox"][1], 1), round(l["bbox"][0], 1), round(l["bbox"][2], 1), t[:70]))
    for y, x0, x1, t in sorted(rows):
        print("      y %6.1f x %6.1f..%6.1f  %s" % (y, x0, x1, t))
    d[0].get_pixmap(dpi=140, clip=pymupdf.Rect(0, 140, 600, 210)).save("reports/visual/doc1_fio_%s.png" % fio.count(" "))
    d.close()
