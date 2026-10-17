#!/usr/bin/env python3
"""Сверка вёрстки: наш документ против оригинала по координатам текста.

    compare_layout.py <код_шаблона> <наш.pdf> [оригинал.pdf]

Для каждой строки оригинала ищет такую же строку у нас и показывает сдвиг
в пунктах. Совпало (≤1.5pt) — молчит; разошлось — печатает. Плюс отдельно:
что есть только у оригинала и что только у нас.
"""
import os
import re
import sys

import pymupdf


def lines(path):
    """Все строки страницы: текст + координаты (x — левый край, y — базовая линия)."""
    d = pymupdf.open(path)
    out = []
    for pno, page in enumerate(d):
        for blk in page.get_text('dict')['blocks']:
            for ln in blk.get('lines', []):
                txt = ' '.join(s['text'] for s in ln['spans'])
                t = re.sub(r'\s+', ' ', txt).strip()
                if not t:
                    continue
                x = min(s['origin'][0] for s in ln['spans'])
                y = max(s['origin'][1] for s in ln['spans'])
                size = max(s['size'] for s in ln['spans'])
                out.append({'page': pno, 'text': t, 'x': round(x, 2), 'y': round(y, 2), 'size': round(size, 2)})
    d.close()
    return out


def norm(t):
    return re.sub(r'[^\w]+', ' ', t.lower()).strip()


def main():
    code, ours = sys.argv[1], sys.argv[2]
    orig = sys.argv[3] if len(sys.argv) > 3 else '/opt/wolf_v2/data/templates/%s/example_filled.pdf' % code
    A, B = lines(orig), lines(ours)
    used = set()
    shifted, missing = [], []
    for a in A:
        na = norm(a['text'])
        best, bi = None, None
        for i, b in enumerate(B):
            if i in used:
                continue
            nb = norm(b['text'])
            if nb == na or (len(na) > 12 and (na in nb or nb in na)):
                dy = abs(a['y'] - b['y']); dx = abs(a['x'] - b['x'])
                if best is None or dy + dx < best:
                    best, bi = dy + dx, i
        if bi is None:
            missing.append(a)
            continue
        used.add(bi)
        b = B[bi]
        if abs(a['y'] - b['y']) > 1.5 or abs(a['x'] - b['x']) > 1.5 or abs(a['size'] - b['size']) > 0.3:
            shifted.append((a, b))
    extra = [b for i, b in enumerate(B) if i not in used]
    print('=== СВЕРКА ВЁРСТКИ: %s' % code)
    print('оригинал: %s (%d строк)' % (os.path.basename(orig), len(A)))
    print('наш:      %s (%d строк)' % (os.path.basename(ours), len(B)))
    print()
    print('--- сдвиги (%d):' % len(shifted))
    for a, b in shifted[:40]:
        print('  «%s»' % a['text'][:52])
        print('     оригинал y=%.1f x=%.1f %.1fpt | наш y=%.1f x=%.1f %.1fpt | Δy=%+.1f Δx=%+.1f Δsize=%+.2f'
              % (a['y'], a['x'], a['size'], b['y'], b['x'], b['size'],
                 b['y'] - a['y'], b['x'] - a['x'], b['size'] - a['size']))
    print()
    print('--- нет у нас (%d):' % len(missing))
    for a in missing[:30]:
        print('  «%s»  y=%.1f x=%.1f' % (a['text'][:60], a['y'], a['x']))
    print()
    print('--- только у нас (%d):' % len(extra))
    for b in extra[:30]:
        print('  «%s»  y=%.1f x=%.1f' % (b['text'][:60], b['y'], b['x']))


if __name__ == '__main__':
    main()
