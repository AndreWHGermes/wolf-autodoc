"""Выравнивание ширин блоков в HTML-шаблоне документа.

Проблема: блоки значений (`.txt`) стоят с шириной уже, чем их текст. Текст
переносится и налезает на следующую строку таблицы. Скрипт измеряет каждую
строку в браузере и расширяет узкие блоки до нужного размера, не выходя за
поле листа (правое поле как у остальных блоков — 524.41pt от левого края).

Запуск:
    /usr/bin/python3 scripts/fix_block_widths.py <файл.html> [--apply]

Без `--apply` — только показывает, что будет изменено.
Рядом сохраняется копия `<файл>.bak_widths_YYYYMMDD_HHMM`.
"""
import math
import re
import shutil
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright

PAGE_RIGHT = 524.41          # правый предел текста на листе A4 (как у прочих блоков)
MEASURE_JS = """() => {
  const els = [...document.querySelectorAll('.txt')];
  return els.map(e => {
    const cs = getComputedStyle(e);
    const probe = e.cloneNode(true);
    probe.style.position = 'absolute'; probe.style.whiteSpace = 'pre';
    probe.style.width = 'auto'; probe.style.height = 'auto'; probe.style.visibility = 'hidden';
    document.body.appendChild(probe);
    const need = probe.getBoundingClientRect().width;
    document.body.removeChild(probe);
    const r = e.getBoundingClientRect();
    return {t: (e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,60),
            left: r.x / (96/72), need: need / (96/72), w: parseFloat(cs.width) || 0};
  });
}"""


def measure(path: str) -> list:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 794, "height": 1123})
        pg.goto("file://" + path)
        pg.wait_for_timeout(500)
        data = pg.evaluate(MEASURE_JS)
        b.close()
    return data


def main() -> None:
    path = sys.argv[1]
    apply_changes = "--apply" in sys.argv
    html = open(path, encoding="utf-8").read()
    rows = measure(path)
    # позиции блоков .txt в файле — в том же порядке, что и в DOM
    spans = [m for m in re.finditer(r'<div class="txt" style="([^"]*)"', html)]
    fixes = []
    for idx, m in enumerate(spans):
        if idx >= len(rows):
            break
        r = rows[idx]
        need = r["need"] + 2
        limit = PAGE_RIGHT - r["left"]
        target = min(math.ceil(need), math.floor(limit))
        cur = r["w"]
        if cur and target > cur + 1:
            style = m.group(1)
            new_style = re.sub(r"width:\s*[\d.]+pt", "width:%.2fpt" % target, style, count=1)
            if new_style != style:
                fixes.append((idx, r["t"], cur, target, m.start(1), m.end(1), new_style))
    print("файл:", path)
    print("блоков .txt:", len(spans), "| нужно расширить:", len(fixes))
    for f in fixes[:25]:
        print("   №%-3s %-58s %s → %s pt" % (f[0], f[1][:58], f[2], f[3]))
    if not fixes:
        print("правки не нужны")
        return
    if not apply_changes:
        print("\n(черновой прогон — добавьте --apply для записи)")
        return
    out = html
    for f in sorted(fixes, key=lambda x: -x[4]):          # с конца, чтобы не сбить позиции
        out = out[:f[4]] + f[6] + out[f[5]:]
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    shutil.copy2(path, path + ".bak_widths_" + stamp)
    open(path, "w", encoding="utf-8").write(out)
    print("записано, копия:", path + ".bak_widths_" + stamp)


if __name__ == "__main__":
    main()
