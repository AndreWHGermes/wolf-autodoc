#!/usr/bin/env python3
"""ПРОТОТИП: подмена значений прямо в PDF-оригинале (без HTML).

Идея: фон, линии, печати, рамки, подписи — всё из настоящего PDF остаётся как есть.
Меняется только текст: значения в известных зонах затираются и печатаются заново тем же
шрифтом и кеглем. Визуально документ не может «поехать» — он тот же самый PDF.

Запуск: python3 /opt/wolf_v2/scripts/pdf_overlay_demo.py
Результат: /tmp/pdf_overlay_demo.pdf и /tmp/pdf_overlay_side.png (оригинал | подмена).
"""
from __future__ import annotations

import sys

import pymupdf

SRC = "/opt/wolf_v2/data/gdrive_cache/client_65/bankstatement.pdf"
OUT_PDF = "/tmp/pdf_overlay_demo.pdf"
OUT_PNG = "/tmp/pdf_overlay_side.png"

# что меняем: (искать этот текст, заменить на этот)
REPLACE = [
    ("ae32271197", "ZN44719023"),
    ("ANNA", "IRINA"),
    ("CLIENT", "SOKOLOVA"),
]


def find_span(page: pymupdf.Page, needle: str):
    """Находит отрезок текста (span) с нужным содержимым: координаты, шрифт, кегль, цвет."""
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if needle.lower() in span["text"].lower():
                    return span
    return None


def fill(src: str = SRC, out: str = OUT_PDF) -> dict:
    doc = pymupdf.open(src)
    report = []
    for page in doc:
        for old, new in REPLACE:
            span = find_span(page, old)
            if not span:
                continue
            # 1. затираем старый текст его же прямоугольником (фон, линии под ним не пострадают,
            #    если они нарисованы, а не часть текста — для справок банка это так)
            rect = pymupdf.Rect(span["bbox"])
            page.add_redact_annot(rect + (-0.5, -0.5, 0.5, 0.5), fill=(1, 1, 1))
            report.append({"page": page.number + 1, "old": span["text"].strip()[:40],
                           "new": new, "size": round(span["size"], 2),
                           "font": span["font"], "bbox": [round(v, 1) for v in span["bbox"]]})
    for page in doc:
        page.apply_redactions()
    # 2. печатаем новые значения тем же кеглем и с той же базовой линией
    for page in doc:
        for item in report:
            if item["page"] != page.number + 1:
                continue
            x0, y0, x1, y1 = item["bbox"]
            size = item["size"]
            page.insert_text((x0, y1 - size * 0.22), item["new"], fontsize=size,
                             fontname="helv", color=(0, 0, 0))
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    return {"out": out, "changes": report}


def side_by_side(src: str = SRC, out: str = OUT_PNG) -> str:
    d1, d2 = pymupdf.open(src), pymupdf.open(OUT_PDF)
    p1 = d1[0].get_pixmap(dpi=140)
    p2 = d2[0].get_pixmap(dpi=140)
    from PIL import Image
    import io
    i1 = Image.open(io.BytesIO(p1.tobytes("png"))).convert("RGB")
    i2 = Image.open(io.BytesIO(p2.tobytes("png"))).convert("RGB")
    c = Image.new("RGB", (i1.width + i2.width + 24, max(i1.height, i2.height)), "white")
    c.paste(i1, (0, 0))
    c.paste(i2, (i1.width + 24, 0))
    c.save(out)
    return out


if __name__ == "__main__":
    res = fill()
    print("изменено значений:", len(res["changes"]))
    for c in res["changes"]:
        print("  стр.%-2s %-22s → %-14s кегль %-5s шрифт %s" % (c["page"], c["old"], c["new"], c["size"], c["font"]))
    print("PDF:", res["out"])
    print("склейка:", side_by_side())
    sys.exit(0)
