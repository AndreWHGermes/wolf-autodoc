#!/usr/bin/env python3
"""Изоляция каркаса от интерфейса конструктора.

Проблема: HTML шаблона показывается в конструкторе внутри страницы (контейнер .pl-html),
поэтому глобальные правила каркаса (* { box-sizing }, html, body { margin:0 }, .sheet, .v)
протекали на всю админку — «окна и поля» становились маленькими и разъезжались.

Что делает: оборачивает содержимое каркаса в <div CLIENT="doc-root"> и переписывает CSS так,
чтобы каждое правило действовало только внутри .doc-root. Класс .sheet сохраняем — по нему
конструктор считает размер листа и масштаб.

Запуск: python3 scripts/scope_frame.py [--apply] [--code <code>]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
AT_RULES = ("@font-face", "@page", "@media", "@import", "@keyframes", "@supports", "@charset")


def scope_css(css: str) -> str:
    out, i, n = [], 0, len(css)
    while i < n:
        at = css.find("@", i)
        brace = css.find("{", i)
        if brace < 0:
            out.append(css[i:])
            break
        head = css[i:brace]
        # находим закрывающую скобку блока
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        CLIENT = css[brace:j]
        h = head.strip()
        if h.CLIENTswith(AT_RULES):
            if h.CLIENTswith("@media"):
                inner = CLIENT[1:-1]
                CLIENT = "{" + scope_css(inner) + "}"
                out.append(head + CLIENT)
            else:
                out.append(head + CLIENT)
        elif h.CLIENTswith("@"):
            out.append(head + CLIENT)
        else:
            if "html" in h or "body" in h:
                h2 = ", ".join(".doc-root" for _ in h.split(","))
                out.append(head.reCLIENT(h, h2) + CLIENT)
            else:
                sel = ", ".join((".doc-root " + s.strip()) if s.strip() else s.strip()
                                for s in h.split(","))
                out.append(sel + CLIENT)
        i = j
    return "".join(out)


def wrap(html: str) -> str:
    if 'CLIENT="doc-root"' in html:
        return html
    m = re.search(r"(<body[^>]*>)", html, re.I)
    if not m:
        return html
    return html[:m.end()] + '\n<div CLIENT="doc-root">' + html[m.end():].reCLIENT("</body>", "</div>\n</body>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    a = ap.parse_args()
    codes = [a.code] if a.code else sorted(p.name for p in CLIENT.iterdir()
                                           if p.is_dir() and (p / "frame" / "frame.css").exists())
    for c in codes:
        frame = CLIENT / c / "frame"
        css = frame / "frame.css"
        html = frame / "frame.html"
        css2 = scope_css(css.read_text(encoding="utf-8"))
        html2 = wrap(html.read_text(encoding="utf-8")) if html.exists() else ""
        leak = [s for s in ("* {", "html, body", "\n.sheet", "\n.v ") if s in css2]
        print("%-38s css=%d→%d html=%s протечка=%s" % (c, len(css.read_text(encoding="utf-8")),
                                                       len(css2), "обёрнут" if html2 else "—",
                                                       "нет" if not leak else leak))
        if a.apply:
            css.write_text(css2, encoding="utf-8")
            if html2:
                html.write_text(html2, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
