
import re
import pymupdf
TPL = {
 3: ("bank_statement_3m__sber", "ПРАВО: Сбер 3м"),
 2: ("bank_statement_3m__tbank", "Т-Банк 3м"),
 25: ("bank_statement_12m__sber", "Сбер 12м"),
 24: ("bank_statement_12m__tbank", "Т-Банк 12м"),
}
for tid, (code, name) in TPL.items():
    print("=== id=%d %s" % (tid, name))
    # правая граница шапки в PDF-примере
    try:
        doc = pymupdf.open("/opt/wolf_v2/data/templates/%s/example_filled.pdf" % code)
        page = doc[0]
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"])
                if re.search(r"(?i)VAVILOVA|SBERBANK|TBANK|Bank\b", t) and l["bbox"][1] < 90:
                    print("   шапка PDF: x %.0f..%.0f  y %.0f  %s" % (l["bbox"][0], l["bbox"][2], l["bbox"][1], t[:60]))
        doc.close()
    except Exception as e:
        print("   PDF:", e)
    html = open("/opt/wolf_v2/data/templates/%s/template.html" % code, encoding="utf-8").read()
    for m in re.finditer(r'<div class="txt"[^>]*style="([^"]*)"[^>]*>\s*<span[^>]*>\{\{\s*(address_live|client_name)\s*\}\}', html):
        st = m.group(1)
        left = re.search(r"left:\s*([\d.]+)pt", st)
        width = re.search(r"width:\s*([\d.]+)pt", st)
        h = re.search(r"height:\s*([\d.]+)pt", st)
        l, w = float(left.group(1)) if left else 0, float(width.group(1)) if width else 0
        print("   HTML %-13s left=%.0f width=%.0f (правый край %.0f) height=%s" % (
            m.group(2), l, w, l + w, h.group(1) if h else "нет"))
