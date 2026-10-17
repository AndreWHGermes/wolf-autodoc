"""Предпросмотр шаблона с подставленными значениями полей + склейка с оригиналом.

Показывает то, что видит заказчик в конструкторе, и кладёт рядом настоящий образец —
чтобы сравнить один в один. Запуск: /usr/bin/python3 scripts/preview_check.py <code>
"""
import re
import sys
from pathlib import Path

import pymupdf
from weasyprint import HTML

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

code = sys.argv[1]
ROOT = Path("/opt/wolf_v2/data/templates") / code
html = (ROOT / "template.html").read_text(encoding="utf-8")

tid = D.q1("SELECT id FROM templates WHERE code=?", (code,))["id"]
vals = D.q("SELECT name, default_value FROM template_variables WHERE template_id=?", (tid,))
used = []
for r in vals:
    if not r["default_value"]:
        continue
    pat = r"\{\{\s*" + re.escape(r["name"]) + r"\s*\}\}"
    if re.search(pat, html):
        html = re.sub(pat, str(r["default_value"]).replace("&", "&amp;"), html)
        used.append(r["name"])
print("подставлено полей: %d (%s)" % (len(used), ", ".join(used)))
miss = sorted(set(re.findall(r"\{\{\s*([a-zA-Z_]+)\s*\}\}", html)))
print("остались незаполненными метки:", miss or "нет")

out = Path("/tmp/preview_%s.pdf" % code)
HTML(string=html, base_url=str(ROOT)).write_pdf(str(out))

ours = pymupdf.open(out)
ref = pymupdf.open(ROOT / "example_filled.pdf")
print("страниц: наш %d | оригинал %d" % (ours.page_count, ref.page_count))


def blocks(doc, n=1):
    return [" ".join(b[4].split()) for p in doc for b in p.get_text("blocks") if b[4].strip()]


for label, doc in (("НАШ", ours), ("ОРИГИНАЛ", ref)):
    bs = blocks(doc)
    print("--- %s (%d блоков)" % (label, len(bs)))
    for t in bs[:12]:
        print("     ", t[:96])

png = Path("/tmp/preview_%s.png" % code)
ours[0].get_pixmap(dpi=100).save(str(png))
ref_png = Path("/tmp/orig_%s.png" % code)
ref[0].get_pixmap(dpi=100).save(str(ref_png))
try:
    from PIL import Image
    a, b = Image.open(png), Image.open(ref_png)
    canvas = Image.new("RGB", (a.width + b.width + 20, max(a.height, b.height)), "white")
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 20, 0))
    side = Path("/tmp/side_%s.png" % code)
    canvas.save(str(side))
    print("картинка для сравнения:", side)
except Exception as e:
    print("картинки:", png, ref_png, "(склейка не удалась: %s)" % e)
