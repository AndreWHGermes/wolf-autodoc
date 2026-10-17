#!/usr/bin/env python3
"""Невидимые границы рабочего поля во всех HTML-шаблонах документов.

Задача (Андрей, 06.10.2026): текст в собранном документе не должен улетать за край листа.
Сделать как в Word: у листа есть границы, и есть рабочее поле, за которое текст не выходит —
длинная строка переносится на следующую, а не обрывается на краю.

Что делает скрипт по каждому data/templates/<code>/template.html:

1. вычисляет границы рабочего поля ПО САМОМУ ДОКУМЕНТУ: левое поле — самый левый текстовый
   блок, правое — самый правый край текста (не ближе 36pt к краю листа);
2. записывает эти границы в CSS листа как переменные (--margin-l/r/t/b) — это и есть
   «невидимые границы», по ним вёрстка понимает, где кончается рабочее поле;
3. каждому текстовому блоку без width проставляет ширину до правой границы;
4. включает перенос: .txt { white-space: normal; overflow-wrap: break-word };
5. показывает, сколько блоков всё ещё выходит за границы справа (должно быть 0).

Запуск:
    python3 scripts/apply_margins.py               # показать, что изменится
    python3 scripts/apply_margins.py --apply       # записать (делается .bak_margins)
    python3 scripts/apply_margins.py --only bank_statement_3m__tbank --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
TEMPLATES = BASE / "data" / "templates"
PAGE_W, PAGE_H = 595.28, 841.89
MIN_EDGE = 36.0          # ближе этого к краю листа рабочее поле не начинается

STYLE_BLOCK = """
/* ── Рабочее поле листа («невидимые границы»): длинный текст переносится, а не уходит за край ──
   Границы вычислены по самому документу: левое поле __ML__pt, правое __MR__pt,
   верхнее __MT__pt, нижнее __MB__pt. Данные блока — scripts/apply_margins.py. */
:root { --page-w: __PW__pt; --page-h: __PH__pt;
        --margin-l: __ML__pt; --margin-r: __MR__pt; --margin-t: __MT__pt; --margin-b: __MB__pt; }
.sheet .txt, .sheet p, .sheet span.txt {
  white-space: pre-wrap; overflow-wrap: break-word; word-break: normal; }
/* Проверка границ: включить класс margins-on у body — поле покажется оранжевым пунктиром */
body.margins-on .sheet::after {
  content: ""; position: absolute; left: __ML__pt; top: __MT__pt;
  width: __IW__pt; height: __IH__pt; border: 0.5pt dashed #E8590C; pointer-events: none; }
"""

LEFT_RE = re.compile(r"left\s*:\s*(-?[0-9.]+)pt")
TOP_RE = re.compile(r"top\s*:\s*(-?[0-9.]+)pt")
WIDTH_RE = re.compile(r"(?<![a-z-])width\s*:\s*([0-9.]+)pt")
HEIGHT_RE = re.compile(r"(?<![a-z-])height\s*:\s*([0-9.]+)pt")
STYLE_RE = re.compile(r"<style[^>]*>([\s\S]*?)</style>", re.I)
MARGIN_BLOCK_RE = re.compile(r"\n?/\* ── Рабочее поле листа[\s\S]*?pointer-events: none; \}\n?", re.I)
TXT_TAG_RE = re.compile(r"<(?P<tag>div|p|span)(?P<attrs>[^>]*\bclass=\"[^\"]*\btxt\b[^\"]*\"[^>]*)>", re.I)
STYLE_ATTR_RE = re.compile(r'style="([^"]*)"', re.I)
SKIP_DIRS = ("bak", "~", "tmp", "временн")


def block_boxes(html: str) -> list[tuple[float, float, float]]:
    """(left, right, top) по каждому текстовому блоку."""
    out = []
    for m in TXT_TAG_RE.finditer(html):
        sm = STYLE_ATTR_RE.search(m.group("attrs"))
        if not sm:
            continue
        style = sm.group(1)
        lm, wm = LEFT_RE.search(style), WIDTH_RE.search(style)
        if not lm:
            continue
        left = float(lm.group(1))
        width = float(wm.group(1)) if wm else 0.0
        out.append((left, left + width, float(TOP_RE.search(style).group(1)) if TOP_RE.search(style) else 0.0))
    return out


def margins_of(html: str) -> tuple[float, float, float, float]:
    boxes = block_boxes(html)
    if not boxes:
        return 56.7, 56.7, 56.7, 56.7
    left = max(MIN_EDGE, min(b[0] for b in boxes))
    tops = [b[2] for b in boxes if b[2] > 0]
    top = max(28.0, min(tops) if tops else 56.7)
    rights = [b[1] for b in boxes if b[1] > 0]
    right_edge = max(rights) if rights else PAGE_W - 56.7
    right = max(MIN_EDGE, PAGE_W - max(right_edge, PAGE_W - 180.0))
    bottom = max(28.0, PAGE_H - 46.0) if False else 46.0
    return round(left, 2), round(right, 2), round(top, 2), round(bottom, 2)


def process(path: Path, apply: bool) -> dict:
    orig = path.read_text(encoding="utf-8")
    html = orig
    # Сначала убираем прежний блок полей (в любом месте файла) — иначе он копится и остаётся
    # голым CSS вне <style> (тогда он печатается в документе).
    html = MARGIN_BLOCK_RE.sub("\n", html)
    ml, mr, mt, mb = margins_of(html)
    stats = {"file": path.parent.name, "fields": (ml, mr, mt, mb), "widths": 0, "over": 0}

    # 1. описание полей — ВНУТРЬ первого <style> (иначе CSS-текст попадёт в документ и напечатается)
    m = STYLE_RE.search(html)
    if m:
        css = (STYLE_BLOCK.replace("__PW__", str(PAGE_W)).replace("__PH__", str(PAGE_H))
               .replace("__ML__", str(ml)).replace("__MR__", str(mr))
               .replace("__MT__", str(mt)).replace("__MB__", str(mb))
               .replace("__IW__", str(round(PAGE_W - ml - mr, 2)))
               .replace("__IH__", str(round(PAGE_H - mt - mb, 2))))
        # вставляем прямо перед первым закрывающим </style> — гарантированно внутри стилей
        html = html.replace("</style>", css + "\n</style>", 1)

    # 2. ширина текстовым блокам до правой границы рабочего поля
    def fix_tag(match: re.Match) -> str:
        attrs = match.group("attrs")
        sm = STYLE_ATTR_RE.search(attrs)
        if not sm:
            return match.group(0)
        style = sm.group(1)
        # Главная причина «улетания» текста за край — inline white-space:pre: браузер не переносит
        # такой текст вообще. Ставим pre-wrap: авторские пробелы сохраняются, длинная строка переносится.
        new_style_norm = re.sub(r"white-space\s*:\s*pre\s*;", "white-space:pre-wrap;", style)
        new_style_norm = re.sub(r"white-space\s*:\s*pre(?![-\w])", "white-space:pre-wrap", new_style_norm)
        new_style = new_style_norm
        lm = LEFT_RE.search(new_style)
        if not lm:
            return match.group(0).replace(sm.group(0), f'style="{new_style}"', 1) if new_style != style else match.group(0)
        left = float(lm.group(1))
        avail = round(PAGE_W - mr - left, 2)
        if WIDTH_RE.search(new_style):
            w = float(WIDTH_RE.search(new_style).group(1))
            if left + w > PAGE_W - mr + 0.5:
                stats["over"] += 1
            if abs(avail - w) >= 1:
                new_style = WIDTH_RE.sub("width:%spt" % avail, new_style, count=1)
                stats["widths"] += 1
        else:
            if avail <= 0:
                stats["over"] += 1
                return match.group(0)
            new_style = new_style.rstrip().rstrip(";") + f";width:{avail}pt"
            stats["widths"] += 1
        if new_style == style:
            return match.group(0)
        return match.group(0).replace(sm.group(0), f'style="{new_style}"', 1)

    html_new = TXT_TAG_RE.sub(fix_tag, html)
    if apply and html_new != html:
        bak = path.with_suffix(".html.bak_margins")
        if not bak.exists():
            bak.write_text(html, encoding="utf-8")
        path.write_text(html_new, encoding="utf-8")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="записать изменения")
    ap.add_argument("--only", help="только один шаблон")
    args = ap.parse_args()

    files = [p for p in sorted(TEMPLATES.glob("*/template.html"))
             if p.is_file() and not any(s in p.parent.name.lower() for s in SKIP_DIRS)]
    if args.only:
        files = [p for p in files if p.parent.name == args.only]
    if not files:
        print("шаблоны не найдены")
        return 1

    tw = to = 0
    for p in files:
        st = process(p, args.apply)
        tw += st["widths"]
        to += st["over"]
        print("%-38s поля L%s/R%s/T%s · ширин проставлено %-3s · за границей справа %s"
              % (st["file"][:38], st["fields"][0], st["fields"][1], st["fields"][2], st["widths"], st["over"]))
    print("\nИТОГО: шаблонов %s · ширин проставлено %s · блоков за правой границей %s · режим %s"
          % (len(files), tw, to, "ЗАПИСЬ" if args.apply else "проверка (--apply чтобы записать)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
