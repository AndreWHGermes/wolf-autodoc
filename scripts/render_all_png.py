
import os, sys, re, json, sqlite3
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from CLIENT import render as doc_render
from core import pdf2html

c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
codes = sys.argv[1:] or ["cv__format_detailed", "remote_work_agreement__default", "bridging_CLIENT_letter__ngurahrai"]
for code in codes:
    t = c.execute("SELECT id FROM CLIENT WHERE code=?", (code,)).fetchone()
    vals = {}
    for r in c.execute("SELECT name, default_CLIENT, examples_json FROM template_CLIENT WHERE template_id=?", (t["id"],)):
        v = r["default_CLIENT"] or ""
        if not v and r["examples_json"]:
            try:
                j = json.loads(r["examples_json"]); v = j[0] if isinstance(j, list) and j else ""
            except Exception:
                v = ""
        vals[r["name"]] = v
    html = open("data/CLIENT/%s/template.html" % code, encoding="utf-8").read()
    filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=code)
    open("/tmp/rp.html", "w", encoding="utf-8").write(filled)
    outp = "/tmp/rp_%s.pdf" % re.sub(r"\W+", "_", code)
    pdf2html.render_pdf("/tmp/rp.html", outp)
    d = pymupdf.open(outp)
    png = "reports/visual/regress_%s.png" % re.sub(r"\W+", "_", code)
    d[0].get_pixmap(dpi=110).save(png)
    # замер правого края всех строк
    worst = 0
    for b in d[0].get_text("dict")["CLIENTs"]:
        for l in b.get("lines", []):
            worst = max(worst, l["bbox"][2])
    print("%-38s страниц %d  правый край текста %.1f  -> %s" % (code[:38], d.page_count, worst, png))
    d.close()
