
import os, sys, re
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from services import render as doc_render
from core import pdf2html

CODE = "bank_statement_3m__sber"
html = open("data/templates/%s/template.html" % CODE, encoding="utf-8").read()
CASES = [
    ("обычный", "CLIENT ANNA SERGEEVNA", "115191, Moscow, Ul Bol'shaya Tul'skaya , D. 2, Kv. 846"),
    ("длинный", "ALEKSANDROVSKAYA-SEMENOVA CLIENT EVGENIEVNA",
     "350901, Krasnodarskiy Krai, Krasnodar, ul Rossiyskaya, d. 79/3, korp. 1, kv. 653, pomeshchenie 12"),
    ("очень длинный", "ALEKSANDROVSKAYA-SEMENOVA ANNA MARIA EVGENIEVNA",
     "350901, Krasnodarskiy Krai, Krasnodar, ul Rossiyskaya, d. 79/3, korp. 1, kv. 653, pomeshchenie 12, etazh 5, ofis 512, block A"),
]
for name, fio, addr in CASES:
    vals = {"client_name": fio, "address_live": addr, "doc_date": "01.10.2026"}
    filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=CODE)
    open("/tmp/aw.html", "w", encoding="utf-8").write(filled)
    out = "/tmp/aw_%s.pdf" % re.sub(r"\W+", "_", name)
    pdf2html.render_pdf("/tmp/aw.html", out)
    d = pymupdf.open(out); page = d[0]
    print("=== %s" % name)
    over = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            x0, y0, x1, y1 = l["bbox"]
            if 140 < y0 < 200 and x0 > 200:
                print("   x %6.1f..%6.1f y %6.1f  %s" % (x0, x1, y0, t[:95]))
                if x1 > 541:
                    over.append(t)
    print("   выходит за границу 540pt:", over if over else "нет")
    if name == "очень длинный":
        page.get_pixmap(dpi=150, clip=pymupdf.Rect(0, 40, 600, 230)).save("/opt/wolf_v2/reports/visual/addr_wrap.png")
    d.close()
