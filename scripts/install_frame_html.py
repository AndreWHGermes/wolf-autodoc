#!/usr/bin/env python3
"""Ставим каркас как рабочий HTML-шаблон документа (то, что видно в конструкторе).

Правила, выведенные из ошибок конструктора:
  * CSS встраивается в <style> прямо в HTML — админка изолирует встроенные стили;
    внешний <link> обходит эту защиту и ломает размеры окон и полей.
  * Никаких лишних обёрток: .sheet идёт прямым потомком <body>, иначе JS визора
    не находит лист и окно просмотра схлопывается.
  * Блоки значений собраны в КОЛОНКИ (поток внутри колонки): если длинное значение
    переносится на вторую строку, всё, что ниже в этой колонке, сдвигается вниз —
    как в Word. Иначе текст наползал бы на соседние блоки.
  * Ширина колонки не выходит за правое поле листа.

Установка выполняется только если документ проходит проверку вёрстки
(наложение текста, выход за поле) на длинных значениях.

Запуск: python3 scripts/install_frame_html.py [--apply] [--code <code>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import shutil
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
TEMPLATES = BASE / "data" / "templates"
SC = BASE / "scripts"

NOWRAP = ("doc_no", "ref_no", "doc_date", "card_mask", "period_from", "period_to",
          "balance_rub", "date", "date_iso", "itk_expiry", "passport_expiry", "phone")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hex(col):
    def ch(v):
        v = float(v)
        return int(round(v * 255)) if v <= 1.0 else int(round(v))
    return "#%02x%02x%02x" % (ch(col[0]), ch(col[1]), ch(col[2]))


def make_template(code: str) -> str:
    """HTML-шаблон с {{переменными}}: встроенный CSS, .sheet прямым потомком body, колонки."""
    flow = _load("bhf_%s" % code.replace("-", "_"), SC / "build_html_flow.py")
    layout = flow.build_layout(code, {})       # пустые значения: нужны координаты и ширина
    fz = layout["fonts"]
    reg = (fz["regular"] or Path("x")).name
    bold = (fz["bold"] or fz["regular"] or Path("x")).name
    css = f"""@font-face {{ font-family:'Doc'; src:url('frame/fonts/{reg}'); }}
@font-face {{ font-family:'Doc'; font-weight:700; src:url('frame/fonts/{bold}'); }}
@page {{ size:A4; margin:0; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; }}
.sheet {{ position:relative; width:{flow.A4_W}pt; height:{flow.A4_H}pt; overflow:hidden; background:#fff; }}
.bg {{ position:absolute; left:0; top:0; width:{flow.A4_W}pt; height:{flow.A4_H}pt; }}
.guide {{ position:absolute; left:{flow.LEFT_EDGE}pt; top:{flow.TOP_EDGE}pt;
          width:{flow.RIGHT_EDGE-flow.LEFT_EDGE}pt; height:{flow.BOTTOM_EDGE-flow.TOP_EDGE}pt; }}
.col {{ position:absolute; }}
.v {{ display:block; line-height:{flow.LINE_FACTOR}; white-space:pre-wrap;
      overflow-wrap:normal; word-break:keep-all; font-family:'Doc'; color:#000; }}
.v.nowrap {{ white-space:pre; }}
"""
    # Колонки: в одну колонку попадают только блоки, стоящие ДРУГ ПОД ДРУГОМ по вертикали
    # и перекрывающиеся по горизонтали (цепочка «как в Word»). Блоки одной строки бланка
    # («As from … to … the deposit balance is … rubles») остаются каждый на своём месте —
    # поэтому у колонки проверяем, что новый блок начинается НИЖЕ последнего в колонке.
    cols: list[dict] = []
    for b in sorted(layout["blocks"], key=lambda b: (round(b["top"], 1), b["x"])):
        w_b = min(b["w"], flow.RIGHT_EDGE - b["x"])
        placed = False
        for col in cols:
            if (b["top"] >= col["bottom"] + 2.0 and b["x"] <= col["x_right"] - 2.0
                    and b["x"] + w_b >= col["x"] + 2.0):
                col["items"].append(b)
                col["x"] = min(col["x"], b["x"])
                col["x_right"] = max(col["x_right"], b["x"] + w_b)
                col["bottom"] = b["top"] + b["h"]
                placed = True
                break
        if not placed:
            cols.append({"x": b["x"], "x_right": b["x"] + w_b, "items": [b],
                         "top": b["top"], "bottom": b["top"] + b["h"]})

    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             "<title>%s</title>" % code, "<style>%s</style></head><body>" % css,
             '<div class="sheet">', '<img class="bg" src="frame/bg.png" alt="">',
             '<div class="guide"></div>']
    # Каждый блок — в своей колонке: перенос строки внутри блока сдвигает то, что ниже в этой же
    # колонке (как в Word), но не трогает блоки, стоящие в одной строке бланка.
    for col in cols:
        items = [b for b in col["items"] if (b.get("var") or "").strip()]
        if not items:
            continue
        left = min(b["x"] for b in items)
        width = max(min(b["w"], flow.RIGHT_EDGE - left) for b in items)
        parts.append('<div class="col" style="left:%.2fpt;top:%.2fpt;width:%.2fpt">'
                     % (left, items[0]["top"], max(width, 20.0)))
        prev_bottom = None
        for b in items:
            var = (b.get("var") or "").strip()
            mt = 0.0 if prev_bottom is None else max(0.0, b["top"] - prev_bottom)
            cls = "v nowrap" if var in NOWRAP else "v"
            style = ("margin-top:%.2fpt;font-size:%.2fpt;color:%s"
                     % (mt, b["size"], _hex(b["color"])))
            if b.get("bold"):
                style += ";font-weight:700"
            parts.append('<span class="%s" style="%s">{{ %s }}</span>' % (cls, style, var))
            prev_bottom = b["top"] + b["h"]
        parts.append("</div>")
    parts.append("</div></body></html>")
    return "".join(parts)


def layout_ok(code: str, long_values: bool = True):
    """Проверка вёрстки: наложения текста и выход за поле."""
    dlc = _load("dlc_%s" % code.replace("-", "_"), SC / "doc_layout_check.py")
    out, ok = dlc.build(code, None, long_values)
    if not ok:
        return False, ["сборка по каркасу не удалась"]
    probs = dlc.check_spans(dlc.spans_from_pdf(out), None)
    return (not probs), probs


def html_ok(code: str):
    """Проверка самого HTML-шаблона (то, что видно в конструкторе) на длинных значениях."""
    import re
    sys.path.insert(0, str(BASE))
    dlc = _load("dlc2_%s" % code.replace("-", "_"), SC / "doc_layout_check.py")
    from app import app as flask_app
    with flask_app.app_context():
        from services import html_frame, render as _r
        tdir = TEMPLATES / code
        html = make_template(code)
        vals = html_frame.values_with_frames(code, {}, 92)
        vals.update(dlc.LONG_VALUES)
        filled = re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(vals.get(m.group(1), "")), html)
        out = Path("/tmp/htmlvis_%s.pdf" % code)
        _r.render_pdf(filled, base_dir=str(tdir), out_path=str(out))
    probs = dlc.check_spans(dlc.spans_from_pdf(out), None)
    return (not probs), probs


def install(code: str, apply: bool = False) -> dict:
    tdir = TEMPLATES / code
    q = tdir / "frame" / "quality.json"
    if not q.exists() or not json.loads(q.read_text(encoding="utf-8")).get("ok"):
        return {"code": code, "skip": "нет паспорта качества"}
    good, probs = layout_ok(code)
    if not good:
        return {"code": code, "skip": "НЕ прошёл проверку вёрстки (сборка)", "problems": probs[:5]}
    good2, probs2 = html_ok(code)
    if not good2:
        return {"code": code, "skip": "НЕ прошёл проверку вёрстки (HTML)", "problems": probs2[:5]}
    html = make_template(code)
    if apply:
        tpl = tdir / "template.html"
        if tpl.exists():
            shutil.copy2(tpl, tdir / ("template.html.bak_frame_%s" % dt.date.today().strftime("%Y%m%d")))
        tpl.write_text(html, encoding="utf-8")
    return {"code": code, "bytes": len(html), "vars": html.count("{{")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    a = ap.parse_args()
    codes = [a.code] if a.code else sorted(p.name for p in TEMPLATES.iterdir()
                                           if p.is_dir() and (p / "frame" / "quality.json").exists())
    for c in codes:
        r = install(c, a.apply)
        print("%-38s %s" % (c, r.get("skip") or ("установлен, переменных %d" % r.get("vars", 0))))
        for p in r.get("problems", []):
            print("      - %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
