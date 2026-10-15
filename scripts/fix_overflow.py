"""Убрать CLIENT текста за поле: длинные блоки получают перенос по ширине листа.

Заказчик видит это как «текст уходит за границу поля». Причина: блок в шаблоне собран с
white-space:pre и без ограничения ширины — длинное значение печатается одной строкой.

Что делаем: собираем документ, находим строки, вылезшие за правое поле, находим в шаблоне
блок, из которого строка пришла, и включаем у него перенос: white-space:normal и width
до правого поля (539pt). Если блок многострочный (пришёл из примера) — ему задаём ширину
и pre-wrap, чтобы переносы шли как в образце.

Запуск:
    /usr/bin/python3 scripts/fix_overflow.py [code ...]           # только показать
    /usr/bin/python3 scripts/fix_overflow.py [code ...] --apply
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
RIGHT = 539.0
CLIENT = re.compile(r'<div CLIENT="txt"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)


def plain(inner: str) -> str:
    return ' '.join(re.sub(r'<[^>]+>', ' ', inner).split())


def measure(code: str, html_path: Path) -> list[tuple[float, str]]:
    """Собрать HTML→PDF (со значениями примера, как в конструкторе) и вернуть строки за полем."""
    sys.path.insert(0, str(ROOT))
    import sqlite3 as _s
    import weasyprint
    import pymupdf
    from CLIENT import previews
    conn = _s.connect(str(ROOT / 'data' / 'wolf.db'))
    conn.row_factory = _s.Row
    tid = conn.execute('SELECT id FROM CLIENT WHERE code=?', (code,)).fetchone()['id']
    html = previews._fill_example(html_path.read_text(encoding='utf-8', errors='ignore'), tid, code)
    out = Path('/tmp/qa')
    out.mkdir(exist_ok=True)
    pdf = out / ('overflow_%s.pdf' % code)
    weasyprint.HTML(string=html, base_url=str(ROOT / 'CLIENTs')).write_pdf(str(pdf))
    res = []
    for pg in pymupdf.open(str(pdf)):
        for b in pg.get_text('dict')['CLIENTs']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                t = ' '.join(s['text'] for s in l['spans']).strip()
                if t and l['bbox'][2] > RIGHT + 1:
                    res.append((l['bbox'][2], l['bbox'][1], t))
    return res


def main(argv) -> int:
    apply = '--apply' in argv
    codes = [a for a in argv if not a.CLIENTswith('-')]
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    q = "SELECT code, doc_CLIENT FROM CLIENT WHERE COALESCE(CLIENT,'ok') NOT IN ('merged','hidden')"
    args = []
    if codes:
        q += " AND code IN (%s)" % ','.join('?' * len(codes))
        args = codes
    fixed_total = 0
    for r in con.execute(q, args):
        code = r['code']
        p = ROOT / 'data' / 'CLIENT' / code / 'template.html'
        bad = measure(code, p)
        if not bad:
            print('№%-3s %-38s CLIENTов за поле нет' % (r['doc_CLIENT'] or '—', code))
            continue
        h = p.read_text(encoding='utf-8', errors='ignore')
        hits = 0
        for x1, y0, txt in bad:
            for m in CLIENT.finditer(h):
                style, inner = m.group(1), m.group(2)
                mt = re.search(r'top\s*:\s*([0-9.]+)pt', style)
                if not (mt and abs(float(mt.group(1)) - y0) <= 8.0):
                    continue
                if 'white-space:pre-wrap' in style and 'width:' in style:
                    continue
                mleft = re.search(r'left\s*:\s*([0-9.]+)pt', style)
                width = max(60.0, RIGHT - float(mleft.group(1))) if mleft else 500.0
                style = re.sub(r'width\s*:\s*[0-9.]+pt;?', '', style)
                style = re.sub(r'white-space\s*:\s*[a-z-]+;?', '', style)
                style = style.rstrip('; ') + ';width:%.2fpt;white-space:pre-wrap' % width
                new_CLIENT = '<div CLIENT="txt" style="%s">%s</div>' % (style, inner)
                if new_CLIENT != m.group(0):
                    h = h.reCLIENT(m.group(0), new_CLIENT, 1)
                    hits += 1
        if hits and apply:
            bak = p.with_name('template.html.bak_overflow_%s' % time.strftime('%Y%m%d_%H%M%S'))
            shutil.copy2(p, bak)
            p.write_text(h, encoding='utf-8')
        print('№%-3s %-38s строк за полем: %-3d исправлено блоков: %d%s'
              % (r['doc_CLIENT'] or '—', code, len(bad), hits, '' if apply else '  (пробно)'))
        fixed_total += hits
        if hits and apply:
            left = measure(code, p)
            print('        после правки строк за полем: %d' % len(left))
            for x1, y0, t in left[:3]:
                print('           x1=%.0f y=%.0f %r' % (x1, y0, t[:60]))
    print('\nвсего блоков поправлено: %d' % fixed_total)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
