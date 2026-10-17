#!/usr/bin/env python3
"""Слепая сверка: наш документ из HTML-шаблона ↔ оригинальный пример клиента.

Собирает PDF из шаблона со значениями примера, рендерит обе первые страницы
и склеивает их в одну картинку (слева — наш, справа — оригинал), чтобы можно
было глазами увидеть расхождения вёрстки.

Запуск: /usr/bin/python3 scripts/visual_check.py 2 3 24 25
Результат: reports/visual/<код>.png
"""
import json
import os
import sqlite3
import sys

import pymupdf
from PIL import Image

BASE = "/opt/wolf_v2"
sys.path.insert(0, BASE)

from services import render as doc_render      # noqa: E402
from core import pdf2html                      # noqa: E402

DB = os.path.join(BASE, "data", "wolf.db")
OUT_DIR = os.path.join(BASE, "reports", "visual")


def example_values(conn, tid):
    m = {}
    for name, ex in conn.execute(
            "select name, examples_json from template_variables where template_id=?", (tid,)):
        try:
            vals = json.loads(ex or "[]")
            if vals:
                m[name] = str(vals[0])
        except Exception:
            pass
    return m


def make(tid):
    conn = sqlite3.connect(DB)
    row = conn.execute("select code, example_path from templates where id=?", (tid,)).fetchone()
    if not row:
        print(f"[{tid}] шаблон не найден")
        return
    code, ex_rel = row
    ex_path = ex_rel if os.path.isabs(ex_rel or "") else os.path.join(BASE, ex_rel or "")
    if not ex_rel or not os.path.exists(ex_path):
        print(f"[{tid}] {code}: оригинального примера нет — сверять не с чем")
        return
    html_path = os.path.join(BASE, "data", "templates", code, "template.html")
    if not os.path.exists(html_path):
        print(f"[{tid}] {code}: нет template.html")
        return
    html = open(html_path, encoding="utf-8").read()
    filled = doc_render.fill(html, example_values(conn, tid), keep_unfilled=True, template_code=code)
    tmp_html = os.path.join(BASE, "data", "templates", code, "filled_visual.html")
    open(tmp_html, "w", encoding="utf-8").write(filled)
    os.makedirs(OUT_DIR, exist_ok=True)
    ours = os.path.join(OUT_DIR, f"{code}_ours.pdf")
    try:
        pdf2html.render_pdf(tmp_html, ours)
    except Exception as exc:                       # noqa: BLE001
        print(f"[{tid}] {code}: PDF не собрался — {exc}")
        return
    pa = pymupdf.open(ours)[0].get_pixmap(dpi=110)
    pb = pymupdf.open(ex_path)[0].get_pixmap(dpi=110)
    ia = Image.frombytes("RGB", (pa.width, pa.height), pa.samples)
    ib = Image.frombytes("RGB", (pb.width, pb.height), pb.samples)
    gap = 24
    canvas = Image.new("RGB", (ia.width + ib.width + gap, max(ia.height, ib.height)), "white")
    canvas.paste(ia, (0, 0))
    canvas.paste(ib, (ia.width + gap, 0))
    out_png = os.path.join(OUT_DIR, f"{code}.png")
    canvas.save(out_png)
    print(f"[{tid}] {code}: слева наш / справа оригинал → {out_png}")


if __name__ == "__main__":
    for arg in (sys.argv[1:] or ["2"]):
        make(int(arg))
