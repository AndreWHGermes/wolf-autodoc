#!/usr/bin/env python3
"""Замер: насколько HTML-сборка отличается от оригинала по сравнению с PDF-подстановкой.

Считаем пиксельное расхождение с эталоном:
  • вся страница целиком (как видит человек);
  • вне зон подстановки (там, где должен быть нетронутый бланк).

Запуск: python3 scripts/compare_html_vs_pdf.py <code> <app_id>
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

BASE = Path("/opt/wolf_v2")
sys.path.insert(0, str(BASE))


def render(p: str, dpi: int = 150) -> Image.Image:
    d = pymupdf.open(p)
    pm = d[0].get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")
    d.close()
    return img


def diff_pct(a: Image.Image, b: Image.Image, mask: Image.Image | None = None) -> float:
    if a.size != b.size:
        b = b.resize(a.size)
    d = ImageChops.difference(a, b).convert("L")
    if mask is not None:
        d = ImageChops.multiply(d, mask)
    total = a.size[0] * a.size[1]
    return 100.0 * sum(d.histogram()[24:]) / total


def main() -> int:
    code = sys.argv[1] if len(sys.argv) > 1 else "bank_CLIENTment_3m__tbank"
    app_id = int(sys.argv[2]) if len(sys.argv) > 2 else 92
    tpl_dir = BASE / "data" / "CLIENT" / code
    ref = str(tpl_dir / "example_filled.pdf")
    fields = json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8"))
    zones = fields["zones"]

    # 1. HTML-путь: рендер шаблона и сборка PDF через weasyprint (как это делает конструктор)
    from app import app
    with app.app_context():
        from CLIENT import render as R
        res = R.generate(app_id, fields.get("template_id"))
        html = res.get("html") if isinstance(res, dict) else str(res)
    html_pdf = "/tmp/html_build_%s_%s.pdf" % (code, app_id)
    from CLIENT.render import render_pdf
    render_pdf(html, out_path=html_pdf)

    # 2. PDF-путь: подстановка в бланк (то, что показано заказчику)
    pdf_build = str(BASE / "data" / "cache" / "pdf_fill" / ("%s_app%s.pdf" % (code, app_id)))

    ref_img = render(ref)
    html_img = render(html_pdf)
    pdf_img = render(pdf_build)

    mask = Image.new("L", ref_img.size, 255)
    zoom = 150 / 72.0
    for z in zones:
        if not z.get("bbox"):
            continue
        x0, y0, x1, y1 = [v * zoom for v in z["bbox"]]
        mask.paste(0, (max(0, int(x0) - 4), max(0, int(y0) - 4),
                       min(ref_img.width, int(x1) + 4), min(ref_img.height, int(y1) + 4)))

    print("страниц: %d" % pymupdf.open(ref).page_count)
    print("%-14s %-22s %-22s" % ("способ", "отличий всего", "отличий вне зон"))
    print("%-14s %-22s %-22s" % ("HTML", "%.2f%%" % diff_pct(ref_img, html_img),
                                 "%.2f%%" % diff_pct(ref_img, html_img, mask)))
    print("%-14s %-22s %-22s" % ("PDF-подстановка", "%.2f%%" % diff_pct(ref_img, pdf_img),
                                 "%.4f%%" % diff_pct(ref_img, pdf_img, mask)))
    print("файлы: %s | %s" % (html_pdf, pdf_build))
    return 0


if __name__ == "__main__":
    sys.exit(main())
