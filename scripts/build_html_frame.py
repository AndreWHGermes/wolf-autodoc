#!/usr/bin/env python3
"""КАРКАС HTML-документа формата A4 с координатной сеткой из оригинала.

Идея каркаса (учтены все прошлые ошибки — наложения, уползание за край, другой шрифт):
  1. Страница строго A4: 595.28 × 841.89 pt, margin 0; внутри .sheet того же размера.
     Ничего не может выйти за лист: у листа жёсткая рамка (overflow hidden), а рабочее поле
     задано отдельными направляющими — как границы печатного поля в Word.
  2. Все элементы стоят АБСОЛЮТНО по координатам, взятым из оригинала (не поток):
     left/top/width в pt, line-height:1. Поток — источник «прыжков», поэтому его нет.
  3. Шрифты — те же самые файлы, что вложены в оригинальный PDF (Arial / Arial Bold),
     подключаются через @font-face. Никаких подстановок браузера.
  4. Кегль, цвет и начертание — точные из оригинала (9.12 pt — значит 9.12 pt, без округления).
  5. Переполнение ведёт себя как в Word: блок многострочный, переносится по словам внутри
     своей ширины (white-space: normal; overflow-wrap: break-word). Кегль НЕ уменьшается.
  6. Графика бланка (линии, логотип, печать, подпись, статический текст) берётся из
     подготовленного бланка blank.pdf — то есть из самого оригинала, а не рисуется заново.

Результат работы скрипта — папка data/CLIENT/<code>/frame/:
    frame.html   — каркас с {{переменными}} в их координатах
    frame.css    — правила листа, полей и переноса
    bg.png       — подложка бланка (300 dpi)
    fonts/*.ttf  — шрифты, извлечённые из оригинала

Запуск: python3 scripts/build_html_frame.py <code> [--apply]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pymupdf
import pymupdf as fitz

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
A4_W, A4_H = 595.28, 841.89
ASCENT = 0.905            # доля кегля от базовой линии вверх (метрика Arial)
LEFT_EDGE, RIGHT_EDGE = 40.0, 555.0     # направляющие рабочего поля (pt)
TOP_EDGE, BOTTOM_EDGE = 30.0, 812.0


def export_fonts(doc, page, out_dir: Path) -> dict:
    """Складываем шрифты страницы в файлы — их подключает @font-face."""
    out_dir.mkdir(parents=True, exist_ok=True)
    got = {}
    for f in page.get_fonts(full=True):
        xref, _ext, ftype, name = int(f[0]), f[1], f[2], str(f[3])
        if not name or name in got:
            continue
        try:
            _n, ext, _t, buf = doc.extract_font(xref)
            if not buf:
                continue
            fn = "".join(ch if ch.isalnum() else "_" for ch in name) + "." + (ext or "ttf")
            (out_dir / fn).write_bytes(buf)
            got[name] = fn
        except Exception:
            continue
    return got


def make_background(code: str, out_png: Path, dpi: int = 300) -> None:
    """Подложки: подготовленный бланк (без данных прежнего клиента), 300 dpi, по страницам.

    Договоры занимают 2-3 страницы: каркас должен рисовать каждый лист отдельно, иначе
    в документе останется только первая страница. Рядом с bg.png кладём bg-1.png, bg-2.png…
    """
    blank = CLIENT / code / "blank.pdf"
    src = blank if blank.exists() else CLIENT / code / "example_filled.pdf"
    d = pymupdf.open(str(src))
    for i, page in enumerate(d, 1):
        page.get_pixmap(dpi=dpi).save(str(out_png.parent / ("bg-%d.png" % i)))
        if i == 1:
            page.get_pixmap(dpi=dpi).save(str(out_png))
    d.close()


def build(code: str, apply: bool = False) -> dict:
    tpl_dir = CLIENT / code
    fields = json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8"))
    zones = [z for z in fields["zones"] if z.get("bbox")]
    ref = tpl_dir / "example_filled.pdf"

    doc = pymupdf.open(str(ref))
    page = doc[0]
    fonts = export_fonts(doc, page, tpl_dir / "frame" / "fonts")
    doc.close()
    make_background(code, tpl_dir / "frame" / "bg.png")

    # имя семейства: обычный и жирный варианты (по имени шрифта из PDF)
    fam_regular = next((f for n, f in fonts.items() if "bold" not in n.lower()), None)
    fam_bold = next((f for n, f in fonts.items() if "bold" in n.lower()), None)

    css = f"""/* Каркас A4 для документа «{code}» — сгенерирован build_html_frame.py */
@font-face {{ font-family: 'Doc'; src: url('fonts/{fam_regular or ''}'); }}
@font-face {{ font-family: 'Doc'; font-weight: 700; src: url('fonts/{fam_bold or fam_regular or ''}'); }}

@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
.sheet {{                      /* лист A4: жёсткая рамка, из листа выйти нельзя */
  position: relative; width: {A4_W}pt; height: {A4_H}pt; overflow: hidden;
  background: #fff;
}}
.sheet + .sheet {{ page-break-CLIENT: always; }}
.bg {{                         /* графика бланка — из оригинала */
  position: absolute; left: 0; top: 0; width: {A4_W}pt; height: {A4_H}pt;
}}
.guide {{                      /* направляющие рабочего поля: текст доходит только до них */
  position: absolute; left: {LEFT_EDGE}pt; top: {TOP_EDGE}pt;
  width: {RIGHT_EDGE - LEFT_EDGE}pt; height: {BOTTOM_EDGE - TOP_EDGE}pt;
}}
.v {{                          /* значение переменной: абсолютно, по координатам оригинала */
  position: absolute; line-height: 1; white-space: pre;
  font-family: 'Doc'; color: #000;
}}
.v.flow {{                     /* длинное значение: переносится по словам, как в Word */
  white-space: normal; overflow-wrap: break-word; hyphens: none;
}}
"""

    CLIENTs = []
    for z in zones:
        fam_weight = "font-weight:700;" if z.get("bold") else ""
        col = z.get("color") or [0, 0, 0]
        color = "#%02X%02X%02X" % (col[0], col[1], col[2])
        size = float(z.get("size") or 9.0)
        x = float(z["bbox"][0])
        baseline = float((z.get("origin") or [x, z["bbox"][3]])[1])
        top = baseline - ASCENT * size
        width = float(z["bbox"][2]) - x
        flow = " flow" if z.get("wipe") or z["var"].endswith("_2") else ""
        CLIENTs.append(
            '<span CLIENT="v%s" style="left:%.2fpt; top:%.2fpt; font-size:%.2fpt; '
            'color:%s;%s width:%.2fpt">{{ %s }}</span>'
            % (flow, x, top, size, color, fam_weight, max(width, 10.0), z["var"]))

    html = (f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<CLIENT>{code}</CLIENT>\n<link rel=\"stylesheet\" href=\"frame.css\">\n"
            f"</head>\n<body>\n<div CLIENT=\"sheet\">\n"
            f"  <img CLIENT=\"bg\" src=\"bg.png\" alt=\"\">\n"
            f"  <div CLIENT=\"guide\"></div>\n"
            + "".join("  " + b + "\n" for b in CLIENTs) +
            "</div>\n</body>\n</html>\n")

    if apply:
        (tpl_dir / "frame" / "frame.css").write_text(css, encoding="utf-8")
        (tpl_dir / "frame" / "frame.html").write_text(html, encoding="utf-8")
    return {"code": code, "zones": len(zones), "fonts": fonts,
            "html": str(tpl_dir / "frame" / "frame.html"),
            "css": str(tpl_dir / "frame" / "frame.css")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    r = build(args.code, args.apply)
    print("каркас: %s" % r["code"])
    print("  блоков значений: %d" % r["zones"])
    print("  шрифты из оригинала: %s" % ", ".join(r["fonts"].keys()))
    print("  %s" % r["html"])
    print("  %s" % r["css"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
