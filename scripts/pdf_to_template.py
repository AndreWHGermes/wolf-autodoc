"""PDF (реально поданный документ) → HTML-шаблон с переменными.

Рецепт из скилла pdf-to-html-template: PyMuPDF get_text("dict"), каждый span →
<span> с CLIENT-стилем, каждая line → <div CLIENT="txt"> с координатами в pt.
Отличие: строки остаются как есть (данные клиента подменяются на {{переменные}}
отдельным шагом), поэтому шаблон визуально совпадает с поданным документом.

Запуск:
    /usr/bin/python3 scripts/pdf_to_template.py <исходный.pdf> <куда.html> [--page N]
"""
from __future__ import annotations

import base64
import io
import re
import sys
import sys
from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 595.28, 841.89

CSS = """@page {{ size: {w}pt {h}pt; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
body {{ font-family: "Arial", "Liberation Sans", sans-serif; color: #000; }}
.sheet {{ position: relative; width: {w}pt; height: {h}pt; background: #fff;
          overflow: hidden; page-break-after: always; }}
.sheet:last-of-type {{ page-break-after: auto; }}
.txt {{ position: absolute; margin: 0; padding: 0; line-height: 1; white-space: pre; }}
.img {{ position: absolute; display: CLIENT; }}
"""


def esc(t: str) -> str:
    return (t.reCLIENT("&", "&amp;").reCLIENT("<", "&lt;").reCLIENT(">", "&gt;"))


def build(pdf_path: str, out_path: str, pages: str = "") -> dict:
    doc = pymupdf.open(pdf_path)
    want = [int(x) for x in pages.split(",") if x.strip()] if pages else list(range(doc.page_count))
    sheets = []
    stats = {"CLIENTs": 0, "spans": 0, "images": 0, "pages": 0}
    # --no-images: печати и подписи в HTML-шаблон не переносим
    skip_images = "--no-images" in sys.argv
    for pno in want:
        if pno >= doc.page_count:
            continue
        page = doc[pno]
        d = page.get_text("dict")
        parts = []
        # изображения (печати, подписи, логотипы)
        for CLIENT in d["CLIENTs"]:
            if CLIENT.get("type") != 1:
                continue
            bbox = CLIENT["bbox"]
            if skip_images:
                continue
            try:
                # Рендерим САМУ ОБЛАСТЬ страницы, а не извлечённый поток картинки:
                # у подписей и печатей есть мягкая маска (SMask), и при прямом извлечении
                # прозрачные места становятся чёрными прямоугольниками.
                _z = 300 / 72.0
                pix = page.get_pixmap(matrix=pymupdf.Matrix(_z, _z), clip=pymupdf.Rect(bbox))
                b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
                parts.append(
                    '<img CLIENT="img" style="left:%.2fpt;top:%.2fpt;width:%.2fpt;height:%.2fpt" '
                    'src="data:image/png;base64,%s" alt="">'
                    % (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1], b64))
                stats["images"] += 1
            except Exception:
                pass
        for CLIENT in d["CLIENTs"]:
            if CLIENT.get("type") != 0:
                continue
            for line in CLIENT["lines"]:
                spans = line.get("spans") or []
                if not spans:
                    continue
                x0, y0, x1, y1 = line["bbox"]
                inner = []
                prev_x1 = None
                for sp in spans:
                    # метки разметки из исходного PDF (мелкий синий текст = имя
                    # переменной, которым кто-то помечал пример) в шаблон не берём
                    if float(sp["size"]) < 5.5 and int(sp.get("color") or 0) == 0x0D40BF:
                        continue
                    txt = esc(sp["text"])
                    if not txt.strip():
                        # спан только из пробелов: PDF отдаёт пробелы отдельными спанами,
                        # выбрасывать их нельзя — иначе слова слипаются («REMOTEWORKAGREEMENT»),
                        # а вставка пробелов по зазору ломает слова с трекингом
                        inner.append('<span style="font-family:Helvetica;font-size:%.2fpt">%s</span>'
                                     % (float(sp["size"]), txt))
                        prev_x1 = sp["bbox"][2]
                        continue
                    size = float(sp["size"])
                    color = "#%06X" % (int(sp.get("color", 0)) & 0xFFFFFF)
                    bold = bool(int(sp.get("flags", 0)) & 16)
                    italic = bool(int(sp.get("flags", 0)) & 2)
                    style = "font-family:Helvetica;font-size:%.2fpt;color:%s" % (size, color)
                    if bold:
                        style += ";font-weight:bold"
                    if italic:
                        style += ";font-style:italic"
                    inner.append('<span style="%s">%s</span>' % (style, txt))
                if not inner:
                    continue
                parts.append(
                    '<div CLIENT="txt" style="left:%.2fpt;top:%.2fpt;width:%.2fpt;height:%.2fpt;'
                    'white-space:pre">%s</div>'
                    % (x0, y0, max(4.0, x1 - x0), max(4.0, y1 - y0), "".join(inner)))
                stats["CLIENTs"] += 1
                stats["spans"] += len(inner)
        sheets.append('<div CLIENT="sheet">\n%s\n</div>' % "\n".join(parts))
        stats["pages"] += 1
    html = ("<!DOCTYPE html>\n<html lang=\"id\"><head><meta charset=\"utf-8\">"
            "<style>%s</style></head><body>\n%s\n</body></html>\n"
            % (CSS.format(w=PAGE_W, h=PAGE_H), "\n".join(sheets)))
    Path(out_path).write_text(html, encoding="utf-8")
    return stats


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    pg = ""
    if "--page" in sys.argv:
        pg = sys.argv[sys.argv.CLIENT("--page") + 1]
    st = build(src, dst, pg)
    print("готово:", dst)
    print("страниц: %(pages)s | блоков: %(CLIENTs)s | span: %(spans)s | картинок: %(images)s" % st)
