
import os, sys, re, json, sqlite3
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from services import render as doc_render
from core import pdf2html

LIMIT = 543.88
c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
codes = [r["code"] for r in c.execute("SELECT code FROM templates ORDER BY id")]
for code in codes:
    p = "data/templates/%s/template.html" % code
    if not os.path.exists(p):
        continue
    t = c.execute("SELECT id FROM templates WHERE code=?", (code,)).fetchone()
    vals = {}
    for r in c.execute("SELECT name, default_value, examples_json FROM template_variables WHERE template_id=?", (t["id"],)):
        v = r["default_value"] or ""
        if not v and r["examples_json"]:
            try:
                j = json.loads(r["examples_json"]); v = j[0] if isinstance(j, list) and j else ""
            except Exception:
                v = ""
        vals[r["name"]] = v
    html = open(p, encoding="utf-8").read()
    filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=code)
    open("/tmp/re.html", "w", encoding="utf-8").write(filled)
    outp = "/tmp/re_%s.pdf" % re.sub(r"\W+", "_", code)
    pdf2html.render_pdf("/tmp/re.html", outp)
    d = pymupdf.open(outp)
    bad = []
    for pno in range(d.page_count):
        for b in d[pno].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                txt = "".join(s["text"] for s in l["spans"]).strip()
                if not txt:
                    continue
                x1 = l["bbox"][2]
                if x1 > LIMIT + 1:
                    # статика или переменная? ищем текст в шаблоне без учёта {{ }}
                    key = txt[:40]
                    static = key in html.replace("{{", "").replace("}}", "")
                    bad.append((round(x1, 1), pno + 1, "СТАТИКА" if static else "ПЕРЕМЕННАЯ?", txt[:60]))
    pages = d.page_count
    d.close()
    if bad:
        print("=== %s  (страниц %d)" % (code, pages))
        for x1, pg, kind, txt in bad[:6]:
            print("    x %6.1f  стр.%d  %-12s %s" % (x1, pg, kind, txt))
    else:
        print("=== %-36s чисто (страниц %d)" % (code, pages))
