
import re, sys
import pymupdf
PDF = "/opt/wolf_v2/data/templates/bank_statement_3m__sber/example_filled.pdf"
doc = pymupdf.open(PDF)
page = doc[0]
print("=== PDF: строки шапки (x0..x1, y):")
for b in page.get_text("dict")["blocks"]:
    for l in b.get("lines", []):
        txt = "".join(s["text"] for s in l["spans"])
        if re.search(r"(?i)VAVILOVA|SBERBANK|117312|MOSCOW|address|Address", txt):
            x0, y0, x1, y1 = l["bbox"]
            print("  x %7.1f..%7.1f  y %6.1f  %s" % (x0, x1, y0, txt[:80]))
print("\n=== HTML-шаблон: блоки с адресом и шапкой")
html = open("/opt/wolf_v2/data/templates/bank_statement_3m__sber/template.html", encoding="utf-8").read()
for m in re.finditer(r"<div[^>]*style=\"([^\"]*)\"[^>]*>([^<]{0,120})", html):
    style, body = m.group(1), m.group(2)
    if "address_live" in body or re.search(r"(?i)vavilova|117312|sberbank", body):
        print("  style:", style.replace("  ", " ")[:150])
        print("     текст:", body[:110])
print("\n=== фрагменты шаблона вокруг address_live:")
i = html.find("address_live")
print(html[max(0, i-700):i+200])
