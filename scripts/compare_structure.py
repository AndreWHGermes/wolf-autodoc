"""Структурная сверка HTML-шаблона с оригинальным примером.

Сравниваем не значения (они у примера и у шаблона разные), а структуру: набор блоков,
их координаты, ширину и кегль. Так видно, где HTML-шаблон разошёлся с образцом.

Запуск: python3 scripts/compare_structure.py [код ...]
"""
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
TXT = re.compile(r'<div class="txt"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)
PARA = re.compile(r'<div class="para"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)
VAR = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')


def parse_style(style: str) -> dict:
    out = {}
    for m in re.finditer(r'(left|top|width|height|font-size)\s*:\s*([0-9.]+)pt', style):
        out[m.group(1)] = float(m.group(2))
    return out


def html_blocks(path: Path):
    h = path.read_text(encoding='utf-8', errors='ignore')
    h = re.sub(r'<(script|style).*?</\1>', ' ', h, flags=re.S)
    out = []
    for style, inner in TXT.findall(h):
        s = parse_style(style)
        txt = ' '.join(re.sub(r'<[^>]+>', ' ', inner).split())
        fs = re.search(r'font-size\s*:\s*([0-9.]+)pt', inner)
        out.append({'left': s.get('left'), 'top': s.get('top'), 'width': s.get('width'),
                    'size': float(fs.group(1)) if fs else None,
                    'var': (VAR.search(inner) or [None, None])[1], 'text': txt})
    # потоковые абзацы (.para): координат top нет — в приёмке сверяем их по тексту
    for style, inner in PARA.findall(h):
        txt = ' '.join(re.sub(r'<[^>]+>', ' ', inner).split())
        if not txt:
            continue
        out.append({'left': None, 'top': None, 'width': None, 'size': None,
                    'var': None, 'text': txt})
    return out


def pdf_blocks(path: Path):
    import pymupdf
    out = []
    for pg in pymupdf.open(str(path)):
        for b in pg.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for line in b['lines']:
                # строку собираем из span'ов целиком: иначе один ряд текста считается
                # за десяток «блоков» и сверка показывает ложные расхождения
                txt = ' '.join(s['text'] for s in line['spans']).strip()
                if not txt:
                    continue
                x0 = min(s['bbox'][0] for s in line['spans'])
                y0 = min(s['bbox'][1] for s in line['spans'])
                size = max(s['size'] for s in line['spans'])
                out.append({'left': round(x0, 1), 'top': round(y0, 1),
                            'size': round(size, 2), 'text': txt})
    return out


def main(argv) -> int:
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    codes = [a for a in argv if not a.startswith('-')]
    q = ("SELECT id, code, doc_index FROM templates "
         "WHERE COALESCE(status,'ok') NOT IN ('merged','hidden')")
    if codes:
        q += " AND code IN (%s)" % ','.join('?' * len(codes))
    q += " ORDER BY COALESCE(doc_index,999)"
    for r in con.execute(q, codes):
        tdir = ROOT / 'data' / 'templates' / r['code']
        html, ex = tdir / 'template.html', tdir / 'example_filled.pdf'
        print('\n=== №%s %s' % (r['doc_index'] or '—', r['code']))
        if not html.is_file():
            print('    template.html ОТСУТСТВУЕТ')
            continue
        if not ex.is_file():
            print('    пример ОТСУТСТВУЕТ')
            continue
        hb, pb = html_blocks(html), pdf_blocks(ex)
        print('    блоков: HTML=%d, пример=%d (строк с текстом)' % (len(hb), len(pb)))
        # блоки примера, которым не нашлось места в HTML (по координате top ±3pt и кеглю ±0.6)
        missed = []
        for p in pb:
            if not any(h['top'] is not None and abs(h['top'] - p['top']) <= 3.0
                       and (h['size'] is None or abs((h['size'] or 0) - p['size']) <= 0.7)
                       for h in hb):
                missed.append(p)
        extra = []
        for h in hb:
            if h['top'] is None:
                continue
            if not any(abs(h['top'] - p['top']) <= 3.0 for p in pb):
                extra.append(h)
        print('    нет в HTML: %d' % len(missed))
        for p in missed[:6]:
            print('       top=%-7s кегль=%-5s %r' % (p['top'], p['size'], p['text'][:52]))
        print('    лишнее в HTML: %d' % len(extra))
        for h in extra[:6]:
            print('       top=%-7s кегль=%-5s var=%-22s %r' % (h['top'], h['size'], h['var'], h['text'][:40]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
