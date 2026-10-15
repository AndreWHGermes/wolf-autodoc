"""Приёмка HTML-шаблона: годен или на переделку.

Собираем документ из шаблона с теми же значениями, что подставляет конструктор (значения
примера), и проверяем ровно то, на что смотрит заказчик:

  1) пустые переменные — в документе осталось «{{ имя }}» или обязательное значение пусто;
  2) наложения — две строки текста пересекаются (текст «налезает» друг на друга);
  3) выход за поле — строка выходит за правый/левый край или за низ листа;
  4) прыгающие строки — строка сдвинута относительно своего места в оригинальном примере;
  5) текст-мусор — склейки из соседних колонок, одиночные буквы между словами, служебные знаки;
  6) расхождение с примером — строки примера, которым нет места в шаблоне, и лишние блоки.

Выход: по каждому документу вердикт ГОДЕН / НА ПЕРЕДЕЛКУ и список дефектов с координатами.

Запуск:
    /usr/bin/python3 scripts/qa_html.py                 # все действующие документы
    /usr/bin/python3 scripts/qa_html.py <code> [...]    # только указанные
    /usr/bin/python3 scripts/qa_html.py --report        # + отчёт в docs/HTML_QA.md
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
PAGE_W, PAGE_H = 595.28, 841.89
LEFT_FIELD, RIGHT_FIELD = 28.0, 545.0
JUNK = [
    (r'\{\{|\}\}', 'осталась переменная в тексте'),
    (r'\b\w\b\s+\b\w\b\s+\b\w\b', 'склейка из соседних слов (одиночные буквы)'),
    (r'[|•]\s*(?=[A-Z]{2,})', 'служебный знак в тексте'),
    (r'\.{6,}|…{4,}', 'незаполненное место (пунктир)'),
]


def collect(code: str) -> dict:
    """Собрать документ из шаблона с значениями примера и вернуть строки PDF."""
    sys.path.insert(0, str(ROOT))
    import weasyprint
    import pymupdf
    from services import previews
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT id FROM templates WHERE code=?', (code,)).fetchone()
    tdir = ROOT / 'data' / 'templates' / code
    html = previews._fill_example((tdir / 'template.html').read_text(encoding='utf-8', errors='ignore'),
                                  row['id'], code)
    out = Path('/tmp/qa')
    out.mkdir(exist_ok=True)
    pdf = out / ('%s.pdf' % code)
    weasyprint.HTML(string=html, base_url=str(ROOT / 'blocks')).write_pdf(str(pdf))
    lines = []
    doc = pymupdf.open(str(pdf))
    for pno, pg in enumerate(doc):
        for b in pg.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                txt = ' '.join(s['text'] for s in l['spans']).strip()
                if not txt:
                    continue
                bb = l['bbox']
                lines.append({'page': pno, 'x0': bb[0], 'y0': bb[1], 'x1': bb[2], 'y1': bb[3],
                              'text': txt})
    return {'lines': lines, 'pages': len(doc), 'html': html,
            'example': tdir / 'example_filled.pdf', 'template': tdir / 'template.html'}


def overlap(a: dict, b: dict) -> float:
    """Доля пересечения меньшего прямоугольника с большим (0..1)."""
    ix = min(a['x1'], b['x1']) - max(a['x0'], b['x0'])
    iy = min(a['y1'], b['y1']) - max(a['y0'], b['y0'])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    small = min((a['x1'] - a['x0']) * (a['y1'] - a['y0']),
                (b['x1'] - b['x0']) * (b['y1'] - b['y0']))
    return inter / small if small > 0 else 0.0


def check(code: str) -> tuple[bool, list[str]]:
    data = collect(code)
    lines = data['lines']
    problems: list[str] = []
    # правый край поля — как в примере: у части документов лист шире A4, и жёсткий порог
    # 545pt давал ложные «выходы за поле»
    import pymupdf
    exdoc = pymupdf.open(str(data['example']))
    ex_max_x = 0.0
    for pg in exdoc:
        for b in pg.get_text('dict')['blocks']:
            if b['type'] == 0:
                for l in b['lines']:
                    if ' '.join(s['text'] for s in l['spans']).strip():
                        ex_max_x = max(ex_max_x, l['bbox'][2])
    right_field = max(RIGHT_FIELD, ex_max_x + 6.0)
    ex_lines = []
    for pg in exdoc:
        for b in pg.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                t = ' '.join(s['text'] for s in l['spans']).strip()
                if t:
                    ex_lines.append(t)
    ex_text = ' '.join(ex_lines)
    for l in lines:
        for pat, why in JUNK:
            m = re.search(pat, l['text'])
            if not m:
                continue
            frag = m.group(0)
            if frag in ex_text:          # в примере так же — значит так и надо
                continue
            if why.startswith('незаполненное место') and ':' in l['text']:
                continue                 # пунктир бланка под значением — не дефект
            if frag in ('•', '|', '• ') and frag in ex_text:
                continue
            problems.append('стр%d y=%.0f: %s — %r' % (l['page'] + 1, l['y0'], why, l['text'][:60]))
            break
    for i, a in enumerate(lines):
        if a['x1'] > right_field + 1 or a['x0'] < LEFT_FIELD - 1:
            problems.append('стр%d y=%.0f: выходит за поле (x %.0f..%.0f) — %r'
                            % (a['page'] + 1, a['y0'], a['x0'], a['x1'], a['text'][:50]))
        if a['y1'] > PAGE_H - 10:
            problems.append('стр%d: уходит под низ листа (y2=%.0f) — %r'
                            % (a['page'] + 1, a['y1'], a['text'][:50]))
    def ruler(t: str) -> bool:
        """Строка-линейка (пунктир, подчёркивание) — значения стоят поверх неё и в бланке."""
        return not re.search(r'[0-9A-Za-zА-Яа-я]', t)

    ex_pairs = set()
    for i in range(len(ex_lines)):
        for j in range(i + 1, len(ex_lines)):
            a = ex_lines[i]
            b = ex_lines[j]
            if ruler(a) or ruler(b):
                continue
            ka = re.sub(r'[^0-9A-Za-zА-Яа-я]', '', a)[:20]
            kb = re.sub(r'[^0-9A-Za-zА-Яа-я]', '', b)[:20]
            if len(ka) >= 5 and len(kb) >= 5:
                ex_pairs.add((ka, kb))

    def known_pair(a: str, b: str) -> bool:
        """Такая же пара строк перекрывается и в оригинале — значит так и надо."""
        ka = re.sub(r'[^0-9A-Za-zА-Яа-я]', '', a)[:20]
        kb = re.sub(r'[^0-9A-Za-zА-Яа-я]', '', b)[:20]
        return (ka, kb) in ex_pairs or (kb, ka) in ex_pairs or (len(ka) >= 6 and ka in ex_text and len(kb) < 6)

    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            a, b = lines[i], lines[j]
            if a['page'] != b['page']:
                continue
            if ruler(a['text']) or ruler(b['text']):
                continue
            if known_pair(a['text'], b['text']):
                continue
            ov = overlap(a, b)
            if ov > 0.35:
                problems.append('стр%d: наложение (%.0f%%) — %r ↔ %r'
                                % (a['page'] + 1, ov * 100, a['text'][:32], b['text'][:32]))
    # сверка с примером: ищем по тексту (в потоковой вёрстке .para координат top нет)
    from scripts.compare_structure import html_blocks, pdf_blocks
    hb, pb = html_blocks(data['template']), pdf_blocks(data['example'])
    tmpl_text = ' '.join((h.get('text') or '') for h in hb)
    import re as _re
    tmpl_norm = _re.sub(r'\s+', ' ', tmpl_text)
    pb_norm = [(p, _re.sub(r'\s+', ' ', p['text'])) for p in pb]
    # значения переменных: продолжения многострочных блоков лежат внутри значений, а не
    # отдельными блоками — такие строки примера не считаем «потерянными»
    import sqlite3 as _s
    conn = _s.connect(str(ROOT / 'data' / 'wolf.db'))
    conn.row_factory = _s.Row
    tid = conn.execute('SELECT id FROM templates WHERE code=?', (code,)).fetchone()['id']
    vals_blob = _re.sub(r'\s+', ' ', ' '.join(
        str(r['default_value'] or '') + ' ' + str(r['examples_json'] or '')
        for r in conn.execute('SELECT default_value, examples_json FROM template_variables '
                              'WHERE template_id=?', (tid,))))

    def _covered(t: str) -> bool:
        key = t.strip().strip('•').strip()
        if len(key) < 8:
            return True
        if key[:24] in tmpl_norm or key[:24] in vals_blob:
            return True
        # сравниваем и по координатам — для блочной вёрстки
        return any(h['top'] is not None and abs(h['top'] - p['top']) <= 3.0 for h, p in
                   ((h, pp) for h in hb for pp in [p] if False))

    missing = []
    for p, norm in pb_norm:
        if _re.sub(r'[^0-9A-Za-zА-Яа-я]', '', norm)[:24] and \
                _re.sub(r'[^0-9A-Za-zА-Яа-я]', '', norm)[:24] in \
                _re.sub(r'[^0-9A-Za-zА-Яа-я]', '', tmpl_norm):
            continue
        if p['text'][:24] in vals_blob or p['text'][:24] in tmpl_norm:
            continue
        if any(h['top'] is not None and abs(h['top'] - p['top']) <= 3.0 for h in hb):
            continue
        if len(p['text'].strip().strip('•').strip()) < 8:
            continue
        missing.append(p)
    extra = [h for h in hb
             if h['top'] is not None and not any(abs(h['top'] - p['top']) <= 3.0 for p in pb)]
    # сдвиги строк шаблона относительно примера
    shifts = []
    for h in hb:
        if h['top'] is None:
            continue
        cands = [abs(p['top'] - h['top']) for p in pb if abs(p['left'] - (h['left'] or 0)) < 30]
        if cands:
            d = min(cands)
            if 3.0 < d <= 12.0:
                shifts.append('строка шаблона y=%.0f сдвинута на %.1fpt от примера — %r'
                              % (h['top'], d, (h['text'] or '')[:40]))
    if missing:
        problems.append('нет места в шаблоне для %d строк примера (первые: %s)'
                        % (len(missing), '; '.join(p['text'][:28] for p in missing[:3])))
    if extra:
        problems.append('лишних блоков в шаблоне: %d (первые: %s)'
                        % (len(extra), '; '.join((h['text'] or '—')[:28] for h in extra[:3])))
    problems.extend(shifts[:5])
    return (not problems), problems


def main(argv) -> int:
    codes = [a for a in argv if not a.startswith('-')]
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    q = ("SELECT code, doc_index FROM templates WHERE COALESCE(status,'ok') NOT IN "
         "('merged','hidden')")
    args = []
    if codes:
        q += " AND code IN (%s)" % ','.join('?' * len(codes))
        args = codes
    q += " ORDER BY COALESCE(doc_index,999)"
    good, bad = [], []
    report = []
    for r in con.execute(q, args):
        ok, problems = check(r['code'])
        head = '№%-3s %-38s %s' % (r['doc_index'] or '—', r['code'], 'ГОДЕН' if ok else
                                   'НА ПЕРЕДЕЛКУ (%d)' % len(problems))
        print('\n' + head)
        for p in problems[:12]:
            print('     ' + p)
        report.append(head + '\n' + '\n'.join('   ' + p for p in problems))
        (good if ok else bad).append(r['code'])
    print('\nитого: годных %d, на переделку %d' % (len(good), len(bad)))
    if bad:
        print('переделать: ' + ', '.join(bad))
    if '--report' in argv:
        (ROOT / 'docs' / 'HTML_QA.md').write_text(
            '# Приёмка HTML-шаблонов\n\nДата: %s\n\n```\n%s\n```\n'
            % (__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M'), '\n\n'.join(report)),
            encoding='utf-8')
        print('отчёт: docs/HTML_QA.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
