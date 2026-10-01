
import os, sys, re
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from CLIENT import render as doc_render
from core import pdf2html

for code in ("bank_CLIENTment_3m__sber", "bank_CLIENTment_3m__tbank", "bank_CLIENTment_12m__sber", "bank_CLIENTment_12m__tbank"):
    html = open("data/CLIENT/%s/template.html" % code, encoding="utf-8").read()
    vals = {}
    for r in __import__("sqlite3").connect("data/wolf.db").execute(
            "SELECT name, default_CLIENT, examples_json FROM template_CLIENT WHERE template_id=(SELECT id FROM CLIENT WHERE code=?)", (code,)):
        v = r[1]
        if not v and r[2]:
            try:
                v = __import__("json").loads(r[2])[0]
            except Exception:
                v = ""
        if v:
            vals[r[0]] = v
    vals.setdefault("client_name", "CLIENT ANNA SERGEEVNA")
    vals.setdefault("doc_date", "01.10.2026")
    filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=code)
    open("/tmp/v.html", "w", encoding="utf-8").write(filled)
    out = "/tmp/verify_%s.pdf" % code
    pdf2html.render_pdf("/tmp/v.html", out)
    d = pymupdf.open(out); page = d[0]
    print("=== %s" % code)
    for b in page.get_text("dict")["CLIENTs"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            x0, y0, x1 = l["bbox"][0], l["bbox"][1], l["bbox"][2]
            if x0 > 290 and 120 < y0 < 210 and t:
                flag = "  <-- ЗА ГРАНИЦЕЙ" if x1 > 541 else ""
                print("   x %6.1f..%6.1f y %6.1f  %s%s" % (x0, x1, y0, t[:70], flag))
    d.close()
