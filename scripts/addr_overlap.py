
import re, sys
import pymupdf
from PIL import Image

d = pymupdf.open("/tmp/addr_очень_длинный.pdf")
page = d[0]
print("=== все строки первой страницы в области y 140..215 (проверка наложений):")
rows = []
for b in page.get_text("dict")["CLIENTs"]:
    for l in b.get("lines", []):
        t = "".join(s["text"] for s in l["spans"]).strip()
        if not t:
            continue
        x0, y0, x1, y1 = l["bbox"]
        if 130 < y0 < 220:
            rows.append((y0, x0, x1, t))
for y0, x0, x1, t in sorted(rows):
    print("   y %6.1f  x %6.1f..%6.1f  %s" % (y0, x0, x1, t[:90]))
print("\nстроки, CLIENTящие за 527pt по правому краю:")
bad = [(y0, x0, x1, t) for y0, x0, x1, t in rows if x1 > 528]
print("   ", bad if bad else "нет — ничего не CLIENTит за границу")
# картинка верхней части листа для глазами-проверки
pix = page.get_pixmap(dpi=150, clip=pymupdf.Rect(0, 40, 600, 250))
pix.save("/opt/wolf_v2/reports/visual/addr_wrap.png")
print("картинка:", "/opt/wolf_v2/reports/visual/addr_wrap.png")
d.close()
