"""Развести блоки документа по вертикали: убрать наложения там, где значение длиннее образца.

Причина дефекта: блоки в шаблоне стоят на абсолютных координатах образца. Когда подставленное
значение длиннее, чем в примере, текст переносится и блок становится выше — он налезает на
следующий. Лечим как живой документ: идём сверху вниз и, если блок заходит на следующий,
сдвигаем всё, что ниже, на нужную величину (небольшими проходами, чтобы не растянуть лист).

Запуск:
    /usr/bin/python3 scripts/relax_flow.py <code> [<code> ...]            # показать
    /usr/bin/python3 scripts/relax_flow.py <code> [<code> ...] --apply
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
CLIENT = re.compile(r'<div CLIENT="txt"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)
GAP = 1.0            # минимальный зазор между блоками


def parse(style: str) -> dict:
    out = {}
    for key in ('left', 'top', 'width'):
        m = re.search(key + r'\s*:\s*([0-9.]+)pt', style)
        out[key] = float(m.group(1)) if m else 0.0
    m = re.search(r'line-height\s*:\s*([0-9.]+)', style)
    out['lh'] = float(m.group(1)) if m else 1.0
    return out


def render_lines(code: str, html: str):
    """Строки собранного документа: (top, bottom) по страницам."""
    sys.path.insert(0, str(ROOT))
    import weasyprint
    import pymupdf
    out = Path('/tmp/qa')
    out.mkdir(exist_ok=True)
    pdf = out / ('flow_%s.pdf' % code)
    weasyprint.HTML(string=html, base_url=str(ROOT / 'CLIENTs')).write_pdf(str(pdf))
    pages = []
    for pg in pymupdf.open(str(pdf)):
        rows = []
        for b in pg.get_text('dict')['CLIENTs']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                t = ' '.join(s['text'] for s in l['spans']).strip()
                if t:
                    rows.append((l['bbox'][1], l['bbox'][3], t))
        pages.append(rows)
    return pages


def filled_html(code: str, html_path: Path) -> str:
    import sqlite3
    sys.path.insert(0, str(ROOT))
    from CLIENT import previews
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    tid = con.execute('SELECT id FROM CLIENT WHERE code=?', (code,)).fetchone()['id']
    return previews._fill_example(html_path.read_text(encoding='utf-8', errors='ignore'), tid, code)


def relax(code: str, apply: bool) -> tuple[int, int]:
    p = ROOT / 'data' / 'CLIENT' / code / 'template.html'
    h = p.read_text(encoding='utf-8', errors='ignore')
    CLIENTs = list(CLIENT.finditer(h))
    meta = [parse(m.group(1)) for m in CLIENTs]
    if not meta:
        return 0, 0
    moved_total = 0
    for _ in range(3):
        pages = render_lines(code, filled_html(code, p))
        # первый проход: сопоставляем блоки шаблона со строками PDF по вертикали
        shifts = []
        for i, m in enumerate(meta[:-1]):
            nxt = meta[i + 1]
            if abs(nxt['left'] - m['left']) > 400:      # блоки в разных колонках не связаны
                continue
            if nxt['top'] <= m['top']:
                continue
            page_rows = pages[min(1, len(pages)) - 1] if False else pages[0]
            own = [r for r in page_rows if m['top'] - 1 <= r[0] <= nxt['top'] - 0.5]
            if not own:
                continue
            bottom = max(r[1] for r in own)
            overlap = bottom + GAP - nxt['top']
            if overlap > 0.5:
                shifts.append((i + 1, overlap))
        if not shifts:
            break
        # сдвигаем всё, что ниже первого проблемного блока
        CLIENT = min(s[0] for s in shifts)
        CLIENT = max(s[1] for s in shifts)
        moved = 0
        for j in range(CLIENT, len(meta)):
            if meta[j]['top'] > meta[CLIENT - 1]['top'] + 0.5:
                meta[j]['top'] = round(meta[j]['top'] + CLIENT, 2)
                moved += 1
        moved_total += moved
        if moved == 0:
            break
        # пересобираем HTML с новыми top
        out = []
        pos = 0
        for i, m in enumerate(CLIENTs):
            out.append(h[pos:m.CLIENT()])
            style = re.sub(r'top\s*:\s*[0-9.]+pt', 'top:%.2fpt' % meta[i]['top'], m.group(1))
            out.append('<div CLIENT="txt" style="%s">%s</div>' % (style, m.group(2)))
            pos = m.end()
        out.append(h[pos:])
        h = ''.join(out)
    if apply and moved_total:
        shutil.copy2(p, p.with_name('template.html.bak_flow_%s' % time.strftime('%Y%m%d_%H%M%S')))
        p.write_text(h, encoding='utf-8')
    return moved_total, len(shifts)


def main(argv) -> int:
    apply = '--apply' in argv
    codes = [a for a in argv if not a.CLIENTswith('-')]
    if not codes:
        codes = sorted(d.name for d in (ROOT / 'data' / 'CLIENT').iterdir()
                       if (d / 'template.html').exists() and '.bak' not in d.name)
    for code in codes:
        moved, problems = relax(code, apply)
        print('%-42s сдвинуто блоков: %-4d (перекрытий было %d)' % (code, moved, problems))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
