#!/usr/bin/env python3
"""Подмена значений прямо в PDF-оригинале — версия 2 (исправлены наложения).

Что исправлено против v1:
  • замена идёт ЦЕЛЫМ значением (одна зона = одно значение), а не по вхождению —
    поэтому два куска текста больше не печатаются в одну точку (было «RINAKOLOVA»);
  • зоны дедуплицируются по прямоугольнику;
  • новое значение печатается шрифтом из самого PDF (Arial из оригинала), а не подменным;
  • если значение шире зоны — кегль автоматически уменьшается до вписывания;
  • проверка «вне зон подстановки отличий ноль»: считается пиксельная разница
    между оригиналом и результатом за пределами зон.

Запуск: python3 /opt/wolf_v2/scripts/pdf_overlay_v2.py
Выход: /tmp/pdf_overlay_demo.pdf, /tmp/pdf_overlay_side.png, /tmp/pdf_overlay_diff.png
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

SRC = "/opt/wolf_v2/data/gdrive_cache/client_65/bankstatement.pdf"
OUT_PDF = "/tmp/pdf_overlay_demo.pdf"
OUT_PNG = "/tmp/pdf_overlay_side.png"
OUT_DIFF = "/tmp/pdf_overlay_diff.png"

# Замена ЦЕЛЫМИ значениями: полный текст отрезка → новое значение
REPLACE = [
    ("ae32271197", "ZN44719023"),
    ("ANNA MARKAROVA", "IRINA SOKOLOVA"),
]


def template_font(page: pymupdf.Page) -> str | None:
    """Достаём встроенный в PDF шрифт, чтобы печатать точно как в оригинале."""
    for f in page.get_fonts(full=True):
        xref, name = f[0], f[3]
        if "arial" in str(name).lower():
            try:
                _n, _e, _t, buf = page.parent.extract_font(xref)
                p = Path("/tmp/_tpl_font.ttf")
                p.write_bytes(buf)
                return str(p)
            except Exception:
                return None
    return None


def spans(page: pymupdf.Page) -> list[dict]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            out.extend(line["spans"])
    return out


def fill(src: str = SRC, out: str = OUT_PDF) -> dict:
    doc = pymupdf.open(src)
    font_file = template_font(doc[0])
    changes, used = [], set()
    for page in doc:
        for old, new in REPLACE:
            for span in spans(page):
                if span["text"].strip() != old:        # только полное совпадение значения
                    continue
                key = (page.number, tuple(round(v, 1) for v in span["bbox"]))
                if key in used:                        # одна зона — одна замена
                    continue
                used.add(key)
                page.add_redact_annot(pymupdf.Rect(span["bbox"]) + (-0.6, -0.6, 0.6, 0.6),
                                      fill=(1, 1, 1))
                changes.append({"page": page.number + 1, "old": old, "new": new,
                                "size": round(span["size"], 2), "font": span["font"],
                                "bbox": [round(v, 1) for v in span["bbox"]]})
    for page in doc:
        page.apply_redactions()

    _fobj = None
    if font_file:
        try:
            _fobj = pymupdf.Font(fontfile=font_file)
        except Exception:
            _fobj = None
    if _fobj is None:
        _fobj = pymupdf.Font("helv")
    for page in doc:
        for c in [x for x in changes if x["page"] == page.number + 1]:
            x0, y0, x1, y1 = c["bbox"]
            zone_w = x1 - x0
            size = c["size"]
            fontname = "helv"
            if font_file:
                try:
                    page.insert_font(fontname="tpl", fontfile=font_file)
                    fontname = "tpl"
                except Exception:
                    fontname = "helv"
            for _ in range(14):
                w = _fobj.text_length(c["new"], fontsize=size)
                if w <= zone_w + 0.5 or size <= c["size"] * 0.7:
                    break
                size -= 0.25
            page.insert_text((x0, y1 - size * 0.22), c["new"], fontsize=size,
                             fontname=fontname, color=(0, 0, 0))
            c["size_used"] = round(size, 2)

    doc.save(out, garbage=3, deflate=True, clean=True)
    doc.close()
    return {"out": out, "changes": changes, "font": font_file}


def _render(path: str, page: int = 0, dpi: int = 150) -> Image.Image:
    d = pymupdf.open(path)
    pm = d[page].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")


if __name__ == "__main__":
    res = fill()
    print("замен целыми значениями:", len(res["changes"]), "| шрифт из PDF:", res["font"])
    for c in res["changes"]:
        print("  стр.%-2s «%s» → «%s» кегль %s→%s (%s)"
              % (c["page"], c["old"], c["new"], c["size"], c.get("size_used"), c["font"]))

    dpi, zoom = 150, 150 / 72.0
    a, b = _render(SRC), _render(OUT_PDF)
    diff = ImageChops.difference(a, b).convert("L")
    mask = Image.new("L", a.size, 255)
    for c in res["changes"]:
        x0, y0, x1, y1 = [v * zoom for v in c["bbox"]]
        mask.paste(0, (int(x0) - 3, int(y0) - 3, int(x1) + 3, int(y1) + 3))
    outside = ImageChops.multiply(diff, mask)
    strong = sum(outside.histogram()[24:])
    total = a.size[0] * a.size[1]
    print("отличий ВНЕ зон подстановки: %.4f%% пикселей" % (100.0 * strong / total))

    side = Image.new("RGB", (a.width + b.width + 24, max(a.height, b.height)), "white")
    side.paste(a, (0, 0))
    side.paste(b, (a.width + 24, 0))
    side.thumbnail((1700, 1200))
    side.save(OUT_PNG)

    zone = ImageChops.multiply(diff.point(lambda v: 255 if v > 24 else 0), mask)
    heat = Image.new("RGB", a.size, "white")
    heat.paste((220, 30, 30), mask=zone)
    heat.thumbnail((900, 700))
    heat.save(OUT_DIFF)
    print("склейка:", OUT_PNG)
    print("карта отличий вне зон (должна быть пустой):", OUT_DIFF)
    sys.exit(0)
