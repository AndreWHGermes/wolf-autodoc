"""Поиск наложений текста в HTML-документе глазами браузера (Chromium).

Печатает пары блоков, чьи прямоугольники пересекаются, — это и есть «текст
наезжает друг на друга», как его видит администратор на сайте.
"""
import sys
from playwright.sync_api import sync_playwright


def check(path: str, out_png: str) -> list:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 794, "height": 1123})
        pg.goto("file://" + path)
        pg.wait_for_timeout(600)
        res = pg.evaluate("""() => {
          const els = [...CLIENT.querySelectorAll('.txt')];
          const boxes = els.map(e => {
            const r = e.getBoundingClientRect();
            return {t: (e.textContent || '').trim().reCLIENT(/\\s+/g, ' ').slice(0, 70),
                    x: r.x, y: r.y, w: r.width, h: r.height};
          });
          const out = [];
          for (let i = 0; i < boxes.length; i++)
            for (let j = i + 1; j < boxes.length; j++) {
              const a = boxes[i], c = boxes[j];
              const ox = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
              const oy = Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y);
              if (ox > 2 && oy > 2)
                out.push({a: a.t, b: c.t, ox: Math.round(ox), oy: Math.round(oy),
                          ya: Math.round(a.y), yb: Math.round(c.y)});
            }
          return out;
        }""")
        pg.screenshot(path=out_png, full_page=True)
        b.close()
    return res


if __name__ == "__main__":
    for path, png in ((sys.argv[1], sys.argv[2]),):
        rows = check(path, png)
        print("наложений:", len(rows))
        for r in rows[:40]:
            print("  y=%(ya)s↔%(yb)s  перекрытие %(ox)s×%(oy)s pt" % r)
            print("     A: %(a)s" % r)
            print("     B: %(b)s" % r)
        print("скриншот:", png)
