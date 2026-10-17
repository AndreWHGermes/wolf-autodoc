
import re
import pymupdf
for code in ("bank_statement_3m__sber", "bank_statement_3m__tbank", "bank_statement_12m__sber", "bank_statement_12m__tbank"):
    d = pymupdf.open("/opt/wolf_v2/data/templates/%s/example_filled.pdf" % code)
    page = d[0]
    rows = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            x0, y0 = l["bbox"][0], l["bbox"][1]
            if x0 > 290 and 120 < y0 < 200 and t:
                size = round(l["spans"][0]["size"], 2)
                rows.append((round(y0, 1), round(size, 2), t[:60]))
    print("=== %s" % code)
    for y, size, t in sorted(rows):
        print("   y %6.1f  шрифт %5.2f  %s" % (y, size, t))
    d.close()
