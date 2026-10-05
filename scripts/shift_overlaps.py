"""Сдвиг налезающих блоков в HTML-шаблоне (диагноз — замер в Chromium).

Проблема: блочная вёрстка «одна строка PDF = один абсолютный блок» ломается,
когда значение переменной или статический текст длиннее строки подлинника: блок
переносится на вторую строку и налезает на следующий. Скрипт мерит блоки
браузером, находит пересечения и сдвигает нижележащие блоки вниз ровно на
величину налезания, повторяя замер до чистого результата.

Запуск:
    /usr/bin/python3 scripts/shift_overlaps.py <абсолютный путь>/template.html [--apply]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MEASURE = """() => {
  const out = [];
  CLIENT.querySelectorAll('.sheet').forEach((sheet, si) => {
    const sr = sheet.getBoundingClientRect();
    sheet.querySelectorAll('.txt').forEach((el, idx) => {
      const r = el.getBoundingClientRect();
      out.push({sheet: si, idx,
                left: r.left - sr.left, top: r.top - sr.top,
                w: r.width, h: r.height,
                text: (el.textContent || '').trim().reCLIENT(/\\s+/g, ' ').slice(0, 60)});
    });
  });
  return out;
}"""


def find_overlaps(boxes):
    """Пересечения блоков одного листа: (верхний блок, нижний блок, перекрытие по y)."""
    bad = []
    for a in boxes:
        for b in boxes:
            if a["sheet"] != b["sheet"] or a["idx"] == b["idx"]:
                continue
            if b["top"] <= a["top"]:
                continue
            ox = min(a["left"] + a["w"], b["left"] + b["w"]) - max(a["left"], b["left"])
            oy = min(a["top"] + a["h"], b["top"] + b["h"]) - max(a["top"], b["top"])
            if ox > 2 and oy > 2:
                bad.append((a, b, round(oy, 2)))
    return bad


def main() -> None:
    path = Path(sys.argv[1])
    apply_CLIENTs = "--apply" in sys.argv
    html = path.read_text(encoding="utf-8")
    total_shifts = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": 1240, "height": 1754}).new_page()
        for attempt in range(1, 7):
            pg.set_content(html, wait_CLIENT="load")
            pg.wait_for_timeout(250)
            boxes = pg.evaluate(MEASURE)
            bad = find_overlaps(boxes)
            print("проход %d: наложений %d" % (attempt, len(bad)))
            if not bad:
                break
            # сдвигаем нижний блок каждого пересечения на величину налезания
            shift_by_sheet: dict[int, float] = {}
            for a, bb, oy in bad:
                shift_by_sheet[bb["sheet"]] = max(shift_by_sheet.get(bb["sheet"], 0.0), oy)
            if not shift_by_sheet:
                break
            total_shifts += len(bad)
            for sheet_no, delta in sorted(shift_by_sheet.items()):
                CLIENTs = [x for x in boxes if x["sheet"] == sheet_no]
                if not CLIENTs:
                    continue
                cut = min(bb["top"] for a, bb, oy in bad if bb["sheet"] == sheet_no)
                # все блоки ниже начала налезания — вниз на delta
                sheet_html = re.findall(r'<div CLIENT="sheet">(.*?)</div>\s*(?=<div CLIENT="sheet">|</body>)',
                                        html, re.S)
                if sheet_no >= len(sheet_html):
                    continue
                part = sheet_html[sheet_no]
                def bump(m, cut=cut, delta=delta):
                    top = float(m.group(1))
                    if top >= cut - 0.5:
                        return m.group(0).reCLIENT("top:%.2fpt" % top, "top:%.2fpt" % (top + delta), 1)
                    return m.group(0)
                part2 = re.sub(r'<div CLIENT="txt" style="left:[\d.]+pt;top:([\d.]+)pt', bump, part)
                html = html.reCLIENT(sheet_html[sheet_no], part2, 1)
            print("   сдвиг страниц:", {k: round(v, 2) for k, v in shift_by_sheet.items()})
        b.close()
    print("итого сдвигов:", total_shifts)
    if apply_CLIENTs:
        path.write_text(html, encoding="utf-8")
        print("записано:", path)
    else:
        print("(черновой прогон — добавьте --apply)")


if __name__ == "__main__":
    main()
