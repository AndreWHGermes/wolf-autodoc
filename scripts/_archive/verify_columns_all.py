
import os, re, sys, json, sqlite3
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")
import pymupdf
from services import render as doc_render
from core import pdf2html

RIGHT_LIMIT = 543.88
LONG = "350901, Krasnodarskiy Krai, Krasnodar, ul Rossiyskaya, d. 79/3, korp. 1, kv. 653, pomeshchenie 12 ZZQ"
TEXTISH = re.compile(r"(?i)address|name|fio|client|position|company|job|activity|descr|purpose|education|note|remark|place|city|street|bank|words|reason|letter|school|special|about")

c = sqlite3.connect("data/wolf.db"); c.row_factory = sqlite3.Row
out = []
for t in c.execute("SELECT id, code FROM templates ORDER BY id"):
    code = t["code"]
    p = "data/templates/%s/template.html" % code
    if not os.path.exists(p):
        out.append({"code": code, "verdict": "нет шаблона"}); continue
    html = open(p, encoding="utf-8").read()
    vals = {}
    textish_hit = 0
    for r in c.execute("SELECT name, default_value, examples_json FROM template_variables WHERE template_id=?", (t["id"],)):
        v = r["default_value"] or ""
        if not v and r["examples_json"]:
            try:
                j = json.loads(r["examples_json"])
                v = j[0] if isinstance(j, list) and j else ""
            except Exception:
                v = ""
        if TEXTISH.search(r["name"]):
            v = LONG; textish_hit += 1
        vals[r["name"]] = v
    if not textish_hit:
        out.append({"code": code, "verdict": "нет текстовых переменных", "prom": 0}); continue
    filled = doc_render.fill(html, vals, keep_unfilled=True, template_code=code)
    open("/tmp/vc.html", "w", encoding="utf-8").write(filled)
    outp = "/tmp/vc_%s.pdf" % re.sub(r"\W+", "_", code)
    pdf2html.render_pdf("/tmp/vc.html", outp)
    d = pymupdf.open(outp)
    worst, over, pages = 0.0, [], d.page_count
    for pno in range(d.page_count):
        for b in d[pno].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                txt = "".join(s["text"] for s in l["spans"])
                if "ZZQ" in txt or "Rossiyskaya" in txt or "Krasnodarskiy" in txt:
                    x1 = l["bbox"][2]
                    worst = max(worst, x1)
                    if x1 > RIGHT_LIMIT + 1:
                        over.append((round(x1, 1), txt[:50]))
    d.close()
    out.append({"code": code, "worst_right": round(worst, 1), "over": over, "pages": pages, "textish": textish_hit})
    print("%-36s край %6.1f  %-8s страниц: %d" % (code[:36], worst, "ВЫХОД!" if over else "в границе", pages))
    for o in over:
        print("        за границей: x=%.1f  %s" % o)
json.dump(out, open("reports/columns_verify.json", "w"), ensure_ascii=False, indent=1)
bad = [o for o in out if o.get("over")]
print("\nпроверено шаблонов:", len(out), "| с выходом за границу:", len(bad))
