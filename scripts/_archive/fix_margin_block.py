#!/usr/bin/env python3
"""Разовый ремонт: перенести блок «Рабочее поле листа» внутрь <style> во всех шаблонах.

Если блок полей оказался вне <style> (голым CSS), он печатается прямо в документе — это и
случилось при первом применении apply_margins.py. Скрипт:
  1) вырезает все такие блоки (по подстроке «Рабочее поле листа»),
  2) вставляет один блок сразу перед первым </style>,
  3) всегда сохраняет файл, если что-то изменилось.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TEMPLATES = Path("/opt/wolf_v2/data/templates")
MARK = "Рабочее поле листа"
SKIP = ("bak", "~", "tmp", "временн")


def repair(path: Path, apply: bool) -> str:
    html = path.read_text(encoding="utf-8")
    i = html.find(MARK)
    if i < 0:
        return "блока полей нет"
    start = html.rfind("/*", 0, i)
    end = html.find("pointer-events: none; }", i)
    if start < 0 or end < 0:
        return "блок не распознан"
    block = html[start:end + len("pointer-events: none; }")]
    in_style = html.rfind("<style", 0, start) > html.rfind("</style>", 0, start)
    # вырезаем блок (вместе с окружающими пустыми строками)
    cleaned = (html[:start].rstrip("\n") + "\n" + html[end + len("pointer-events: none; }"):].lstrip("\n"))
    if "</style>" not in cleaned:
        return "нет </style> — пропуск"
    fixed = cleaned.replace("</style>", "\n" + block + "\n</style>", 1)
    if apply and fixed != html:
        path.write_text(fixed, encoding="utf-8")
    return ("был внутри стилей" if in_style else "был ВНЕ стилей") + (", перенесён внутрь" if apply and fixed != html else "")


def main() -> int:
    apply = "--apply" in sys.argv
    files = [p for p in sorted(TEMPLATES.glob("*/template.html"))
             if p.is_file() and not any(s in p.parent.name.lower() for s in SKIP)]
    fixed = 0
    for p in files:
        res = repair(p, apply)
        if "перенесён" in res:
            fixed += 1
        print("%-38s %s" % (p.parent.name[:38], res))
    print("\nИТОГО: шаблонов %s · перенесено блоков внутрь <style>: %s · режим %s"
          % (len(files), fixed, "ЗАПИСЬ" if apply else "проверка"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
