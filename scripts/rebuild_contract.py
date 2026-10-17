"""Пересборка шаблона договора по настоящему образцу (одна вёрстка, без двойных слоёв).

В договоре накопились два набора блоков: старый и доклеенный — текст печатается дважды и
налезает друг на друга. Лечим радикально: берём строки образца как вёрстку, значения клиента
и организации заменяем на {{ переменные }}.

Запуск:
    /usr/bin/python3 scripts/rebuild_contract.py <code>            # показать, что получится
    /usr/bin/python3 scripts/rebuild_contract.py <code> --apply
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')

# Ручная привязка переменных по формулировке образца: значения в БД и в примере могут
# различаться (другой клиент), поэтому для этих мест указываем переменную явно.
PRECISE = {
    'employment_contract__default': [
        (r'Anna Rudolfovna Markarova', '{{ employee_full_name }}'),
        (r'ANNA MARKAROVA', '{{ employee_name_upper }}'),
        (r'A\.\s*MARKAROVA', '{{ employee_signature }}'),
        (r'76\s+3655709', '{{ passport_number }}'),
        (r'Russia\|', '{{ contract_place }}'),
        (r'\bLI-158\b', '{{ contract_no }}'),
        (r'(Start Date:\s*)01\s+September\s+2025', r'\1{{ term_start_date }}'),
        (r'01\s+September\s+2025', '{{ contract_date }}'),
        (r'01\s+September\s+2030', '{{ term_end_date }}'),
        (r'1\s+February\s+1995', '{{ date_of_birth }}'),
        (r'Stavropolsky\s+Krai,\s+Russia', '{{ place_of_birth }}'),
        (r'(position of\s+)Social\s+Media\s+Producer', r'\1{{ position_title }}'),
    ],
}


def load_vars(code: str) -> dict:
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    tid = con.execute('SELECT id FROM templates WHERE code=?', (code,)).fetchone()['id']
    out = {}
    for r in con.execute('SELECT name, default_value, examples_json FROM template_variables '
                         'WHERE template_id=?', (tid,)):
        v = (r['default_value'] or '').strip()
        if not v and r['examples_json']:
            try:
                ex = json.loads(r['examples_json'])
                v = ex[0] if isinstance(ex, list) and ex else (list(ex.values())[0] if ex else '')
            except Exception:
                v = ''
        out[r['name']] = ' '.join(str(v or '').split())
    return out


def build_pages(tdir: Path, long_vals, code: str):
    """Строки образца, сгруппированные в абзацы.

    Отдельная строка — единица измерения PDF, но единица вёрстки — абзац. Если оставить
    блоки построчно, длинное значение переносится внутри строки и налезает на следующую.
    Поэтому строки с общим левым краем и шагом как у строки абзаца собираются в один блок:
    он переносится ровно, с тем же межстрочным шагом, что в образце.
    """
    import pymupdf
    doc = pymupdf.open(str(tdir / 'example_filled.pdf'))
    pages = []
    used = set()
    for pg in doc:
        rect = pg.rect
        rows = []
        for b in pg.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                txt = ' '.join(s['text'] for s in l['spans']).strip()
                if not txt:
                    continue
                sp = l['spans'][0]
                body = txt
                for v, k in long_vals:
                    if len(v) >= 4 and v in body:
                        body = body.replace(v, '{{ %s }}' % k)
                        used.add(k)
                for rx, k in PRECISE.get(code, ()):   # привязка по формулировке образца
                    body, n = re.subn(rx, k, body)
                    if n:
                        used.add(k.strip('{{ }}'))
                rows.append({'left': round(l['bbox'][0], 2), 'top': round(l['bbox'][1], 2),
                             'x1': round(l['bbox'][2], 2), 'size': round(sp['size'], 2),
                             'font': sp['font'].split('+')[-1].replace(' ', ''),
                             'bold': 'bold' in sp['font'].lower() or bool(sp['flags'] & 16),
                             'text': body})
        rows.sort(key=lambda r: r['top'])
        paragraphs = []
        for r in rows:
            if paragraphs:
                p = paragraphs[-1]
                gap = r['top'] - p['rows'][-1]['top']
                same_col = abs(r['left'] - p['left']) <= 3.0
                step_ok = 5.0 <= gap <= (max(11.0, p['size'] * 1.55))
                no_bullet = not r['text'].startswith(('•', '-', '1.', '2.', '3.', '4.', '5.'))
                if same_col and step_ok and no_bullet and len(p['rows']) < 40:
                    p['rows'].append(r)
                    p['x1'] = max(p['x1'], r['x1'])
                    continue
            paragraphs.append({'left': r['left'], 'top': r['top'], 'x1': r['x1'],
                               'size': r['size'], 'font': r['font'], 'bold': r['bold'],
                               'rows': [r]})
        blocks = []
        for p in paragraphs:
            text = '\n'.join(x['text'] for x in p['rows'])
            lines = len(p['rows'])
            lh = 1.0
            if lines > 1:
                tops = [x['top'] for x in p['rows']]
                step = (tops[-1] - tops[0]) / (lines - 1)
                lh = max(1.0, round(step / max(1.0, p['size']), 3))
            blocks.append({'left': p['left'], 'top': p['top'], 'x1': p['x1'],
                           'width': round(max(60.0, p['x1'] - p['left'] + 8), 2),
                           'size': p['size'], 'font': p['font'], 'bold': p['bold'],
                           'line_height': lh, 'text': text})
        pages.append({'w': round(rect.width, 2), 'h': round(rect.height, 2), 'blocks': blocks})
    return pages, used


def main(argv) -> int:
    apply = '--apply' in argv
    code = [a for a in argv if not a.startswith('-')][0]
    import pymupdf
    tdir = ROOT / 'data' / 'templates' / code
    vals = load_vars(code)
    long_vals = sorted(((v, k) for k, v in vals.items() if len(v) >= 4), key=lambda x: -len(x[0]))
    pages, used = build_pages(tdir, long_vals, code)
    nblocks = sum(len(p['blocks']) for p in pages)
    print('страниц в образце: %d, строк: %d' % (len(pages), nblocks))
    print('переменных подставлено: %d из %d' % (len(used), len(vals)))
    lost = sorted(set(vals) - used - {'company_country', 'company_link'})
    print('не нашлось места (проверить вручную): %s' % (', '.join(lost) if lost else '—'))
    for b in pages[0]['blocks'][:6]:
        print('  %.1f %.1f %s %s | %s' % (b['left'], b['top'], b['size'], 'bold' if b['bold'] else '    ', b['text'][:70]))
    if apply:
        out = ['<!DOCTYPE html>', '<html lang="en"><head><meta charset="utf-8"><style>',
               '@page { size: %.2fpt %.2fpt; margin: 0; }' % (pages[0]['w'], pages[0]['h']),
               '* { box-sizing: border-box; }',
               'html, body { margin: 0; padding: 0; background: #fff; }',
               'body { font-family: "Arial", "Liberation Sans", sans-serif; color: #000; }',
               '.sheet { position: relative; width: %.2fpt; height: %.2fpt; background: #fff;'
               % (pages[0]['w'], pages[0]['h']),
               '          overflow: hidden; page-break-after: always; }',
               '.sheet:last-of-type { page-break-after: auto; }',
               '.txt { position: absolute; margin: 0; padding: 0; line-height: 1; }',
               '.para { margin: 0; padding: 0; }',
               '</style></head><body>']
        pages_rect_w = pages[0]['w']
        for p in pages:
            out.append('<div class="sheet">')
            flow_prev_bottom = None
            for b in p['blocks']:
                body = b['text']
                span = 'font-family:%s;font-size:%.2fpt;color:#000000%s' % (
                    b['font'], b['size'], ';font-weight:bold' if b['bold'] else '')
                if b['left'] < 200:      # тело документа: потоком, чтобы перенос не налезал
                    lines = body.count('\n') + 1
                    mt = b['top'] if flow_prev_bottom is None else max(0.0, b['top'] - flow_prev_bottom)
                    out.append('<div class="para" style="margin-left:%.2fpt;margin-top:%.2fpt;'
                               'width:%.2fpt;line-height:%.3f"><span style="%s">%s</span></div>'
                               % (b['left'], mt, max(120.0, 539.0 - b['left']),
                                  b.get('line_height', 1.15), span, body))
                    flow_prev_bottom = b['top'] + lines * b['size'] * max(1.0, b.get('line_height', 1.15))
                else:                    # шапка, правые колонки, подписи — на своих местах
                    left = b['left']
                    if left >= 400:
                        # правую колонку позиционируем от правого края: значение может быть
                        # длиннее образца, тогда текст растёт влево, а не за поле
                        right = max(10.0, round(pages_rect_w - (b['left'] + b['width']), 2))
                        out.append('<div class="txt" style="right:%.2fpt;top:%.2fpt;width:%.2fpt;'
                                   'white-space:pre"><span style="%s">%s</span></div>'
                                   % (right, b['top'], b['width'], span, body))
                        continue
                    out.append('<div class="txt" style="left:%.2fpt;top:%.2fpt;width:%.2fpt;'
                               'white-space:pre"><span style="%s">%s</span></div>'
                               % (left, b['top'], b['width'], span, body))
            out.append('</div>')
        out.append('</body></html>')
        p = tdir / 'template.html'
        shutil.copy2(p, p.with_name('template.html.bak_rebuild_%s' % time.strftime('%Y%m%d_%H%M%S')))
        p.write_text('\n'.join(out), encoding='utf-8')
        print('записано: %d страниц, %d строк' % (len(pages), nblocks))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
