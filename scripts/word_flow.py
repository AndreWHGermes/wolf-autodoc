"""PDF-эталон → Word-шаблон ПОТОКОМ (для документов с текстом между линиями).

В отличие от word_template.py (абсолютные фреймы) здесь документ собирается как
обычный поток абзацев: заголовок раздела + линия под ним (нижняя граница абзаца),
текст раздела — абзацы с межстрочным интервалом из эталона. Когда значение
переменной длиннее, текст растёт, и всё, что ниже (следующий заголовок, его
линия, следующие разделы), само сдвигается вниз, сохраняя вид документа.

    word_flow.py <code> [...]        собрать (--check — только сверка)
    word_flow.py --all-flow          все документы потоковой вёрстки
"""
import os
import re
import subprocess
import sys

import docx
import pymupdf
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import word_template as WT          # переиспользуем переменные и разметку из HTML

ROOT = '/opt/wolf_v2'
TEMPLATES = os.path.join(ROOT, 'data', 'templates')
VENDOR = os.path.join(ROOT, '.venv_docs', 'bin', 'python')
PT2EMU = 12700
BODY_LEFT = 46.1          # левое поле эталона резюме (pt)
SPACE_EXTRA = {}          # поправка интервалов по абзацам (idx → pt), подгоняется

FONT_MAP = (('Arial-BoldMT', 'Arial', True), ('ArialMT', 'Arial', False),
            ('Arimo', 'Arial', None), ('TimesNewRomanPSMT', 'Times New CLIENT', False),
            ('TimesNewRomanPS-BoldMT', 'Times New CLIENT', True),
            ('Helvetica', 'Arial', None), ('Calibri', 'Calibri', None))


def font_of(span):
    name = span['font'].split('+')[-1] or 'Arial'
    family, bold = 'Arial', None
    for pat, fam, b in FONT_MAP:
        if pat in name:
            family, bold = fam, b
            break
    if bold is None:
        bold = 'Bold' in name
    return family, bold, 'Italic' in name


def color_of(span):
    c = span.get('color', 0)
    if isinstance(c, int) and c > 0:
        return RGBColor((c >> 16) & 255, (c >> 8) & 255, c & 255)
    return RGBColor(0, 0, 0)


def extract(pdf):
    pg = pymupdf.open(pdf)[0]
    lines = []
    for b in pg.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            spans = [s for s in ln['spans'] if s['text'].strip()]
            if spans:
                lines.append({'bbox': ln['bbox'], 'spans': spans,
                              'text': ''.join(s['text'] for s in ln['spans'])})
    rules = []
    for d in pg.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 1 and abs(p2.x - p1.x) > 40:
                    rules.append(round((p1.y + p2.y) / 2, 1))
            elif it[0] == 're':
                r = it[1]
                if r.height < 2 and r.width > 40:
                    rules.append(round((r.y0 + r.y1) / 2, 1))
    return sorted(lines, key=lambda l: (round(l['bbox'][1], 1), l['bbox'][0])), sorted(set(rules))


def group_paragraphs(lines):
    """Склейка строк в абзацы: продолжение — тот же отступ и малый интервал."""
    paras = []
    for ln in lines:
        y0, x0 = ln['bbox'][1], ln['bbox'][0]
        size = max(s['size'] for s in ln['spans'])
        if paras:
            prev = paras[-1]
            gap = y0 - prev['y_last']
            same_left = abs(x0 - prev['x0']) <= 2.5
            body = not ln['text'].strip().startswith('•')
            if same_left and body and gap < size * 1.45 and not prev['ends_short']:
                prev['lines'].append(ln)
                prev['y_last'] = ln['bbox'][3]
                prev['x1'] = max(prev['x1'], ln['bbox'][2])
                prev['text'] += ' ' + ln['text'].strip()
                prev['ends_short'] = ln['text'].rstrip().endswith(('.', ';', ':')) and False
                continue
        paras.append({'lines': [ln], 'x0': x0, 'y0': y0, 'y_last': ln['bbox'][3],
                      'x1': ln['bbox'][2], 'text': ln['text'].strip(),
                      'ends_short': False,
                      'size': size, 'spans': ln['spans']})
    return paras


def build(code, src_pdf, out_docx, vars_map=None):
    if vars_map is None:
        vars_map = WT.vars_from_db(code)
    chunks = WT.markup_from_html(code)
    lines, rules = extract(src_pdf)
    paras = group_paragraphs(lines)
    left = min(p['x0'] for p in paras)
    doc = docx.Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin, sec.right_margin = Cm(left / 28.3465), Cm((595.276 - 549.3) / 28.3465)
    sec.top_margin, sec.bottom_margin = Cm(30 / 28.3465), Cm(1.5)
    prev_bottom = None
    for idx, p in enumerate(paras):
        has_rule = any(0 <= r - p['y_last'] < 12 for r in rules)
        par = doc.add_paragraph()
        pf = par.paragraph_format
        base_gap = max(0.0, p['y0'] - (prev_bottom if prev_bottom else p['y0']))
        pf.space_before = Pt(max(0.0, base_gap + SPACE_EXTRA.get(idx, 0.0)))
        pf.space_after = Pt(0)
        sz = p['size']
        pf.line_spacing = Pt(round(sz * 1.25, 1))
        pf.left_indent = Cm(max(0.0, (p['x0'] - left)) / 28.3465)
        if p['text'].strip().startswith('•'):
            pf.first_line_indent = Cm(-0.32)
        if has_rule:
            pPr = par._p.get_or_add_pPr()
            bdr = OxmlElement('w:pBdr')
            bottom = OxmlElement('w:bottom')
            bottom.set(qn('w:val'), 'single')
            bottom.set(qn('w:sz'), '6')
            bottom.set(qn('w:space'), '2')
            bottom.set(qn('w:color'), '000000')
            bdr.append(bottom)
            pPr.append(bdr)
        # подключение переменных: сначала разметка из HTML, затем значения из базы
        segs = None
        if chunks:
            mk = WT.apply_markup(p['text'], chunks)
            if mk != p['text']:
                segs = mk
        if segs is None and vars_map:
            t2 = p['text']
            for _s, _d in vars_map.items():
                if _s in t2:
                    t2 = t2.replace(_s, _d)
            if t2 != p['text']:
                segs = t2
        if segs is not None:
            r = par.add_run(segs)
            sp0 = p['lines'][0]['spans'][0]
            fam, bold, italic = font_of(sp0)
            r.font.size, r.font.name = Pt(round(sp0['size'], 1)), fam
            r.bold, r.italic = bold, italic
            r.font.color.rgb = color_of(sp0)
            prev_bottom = p['lines'][-1]['bbox'][3]
            continue

        # правый «прижатый к краю» фрагмент (даты, города) → табуляция
        tail = None
        if len(p['lines']) == 1:
            spans = p['lines'][0]['spans']
            if len(spans) > 1:
                last = spans[-1]
                if last['bbox'][0] - (spans[0]['bbox'][0] + spans[0]['bbox'][2]) > 20:
                    tail = last
        for sp in (p['lines'][0]['spans'] if tail is None else
                   [s for s in p['lines'][0]['spans'] if s is not tail]):
            r = par.add_run(sp['text'])
            fam, bold, italic = font_of(sp)
            r.font.size, r.font.name = Pt(round(sp['size'], 1)), fam
            r.bold, r.italic = bold, italic
            r.font.color.rgb = color_of(sp)
        if tail is not None:
            pf.tab_stops.add_tab_stop(Cm((tail['bbox'][0] - left) / 28.3465),
                                      WD_TAB_ALIGNMENT.LEFT)
            r = par.add_run('\t' + tail['text'])
            fam, bold, italic = font_of(tail)
            r.font.size, r.font.name = Pt(round(tail['size'], 1)), fam
            r.bold, r.italic = bold, italic
            r.font.color.rgb = color_of(tail)
        elif len(p['lines']) > 1:
            for ln in p['lines'][1:]:
                pf2 = par.paragraph_format
                r = par.add_run()
                r.add_break()
                for sp in ln['spans']:
                    r = par.add_run(sp['text'])
                    fam, bold, italic = font_of(sp)
                    r.font.size, r.font.name = Pt(round(sp['size'], 1)), fam
                    r.bold, r.italic = bold, italic
        prev_bottom = p['lines'][-1]['bbox'][3]
    doc.save(out_docx)
    return out_docx, paras


def render_pdf(docx_path):
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', docx_path,
                    '--outdir', os.path.dirname(docx_path)], capture_output=True, timeout=300)
    return os.path.splitext(docx_path)[0] + '.pdf'


def norm(t):
    return re.sub(r'\s+', ' ', t).strip().lower()


def compare(orig, our):
    def rows(f):
        out = []
        for b in pymupdf.open(f)[0].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(s['text'] for s in l['spans']).strip()
                if t:
                    out.append((round(l['bbox'][0], 1), round(l['bbox'][1], 1), t))
        return out
    a, b = rows(orig), rows(our)
    ka = {norm(t): (x, y) for x, y, t in a}
    kb = {norm(t): (x, y) for x, y, t in b}
    miss = [t for k, t in ((norm(t), t) for _, _, t in a) if k not in kb]
    extra = [t for k, t in ((norm(t), t) for _, _, t in b) if k not in ka]
    worst = []
    for k in set(ka) & set(kb):
        dx = ka[k][0] - kb[k][0]
        dy = ka[k][1] - kb[k][1]
        if abs(dx) > 2 or abs(dy) > 2:
            worst.append((round(abs(dx)), round(dy), k[:40]))
    worst.sort(key=lambda w: -(w[0] + abs(w[1])))
    return len(a), len(b), miss, extra, worst


def _rows(pdf):
    out = []
    for b in pymupdf.open(pdf)[0].get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip()
            if t:
                out.append((round(l['bbox'][0], 1), round(l['bbox'][1], 1), t))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if '--all-flow' in flags:
        import sqlite3
        con = sqlite3.connect(os.path.join(ROOT, 'data', 'wolf.db'))
        args = [r[0] for r in con.execute(
            "SELECT code FROM templates WHERE COALESCE(status,'ok') NOT IN ('hidden','merged')"
            " ORDER BY COALESCE(doc_index,0), id")]
    for code in args:
        d = os.path.join(TEMPLATES, code)
        src = os.path.join(d, 'example_filled.pdf')
        if not os.path.exists(src):
            print('  %-40s НЕТ эталона' % code)
            continue
        out = os.path.join('/tmp', 'flow_%s.docx' % code)
        SPACE_EXTRA.clear()
        for _ in range(4):                      # подгонка интервалов по абзацам
            _, paras = build(code, src, out)
            pdf = render_pdf(out)
            na, nb, miss, extra, worst = compare(src, pdf)
            if not worst:
                break
            a = {norm(t): y for _, y, t in _rows(src)}
            b = {norm(t): y for _, y, t in _rows(pdf)}
            changed = False
            for idx, p in enumerate(paras):
                key = norm(p['text'])[:24]
                if len(key) < 6:
                    continue
                hit = next((k for k in a if k.startswith(key) and k in b), None)
                if hit is None:
                    continue
                dy = a[hit] - b[hit]
                if abs(dy) > 1.5:
                    SPACE_EXTRA[idx] = SPACE_EXTRA.get(idx, 0.0) + dy
                    changed = True
            if not changed:
                break
        ov = '/tmp/wordflow_%s_overlay.png' % code
        subprocess.run([VENDOR, os.path.join(ROOT, 'scripts', 'overlay_diff.py'),
                        src, pdf, ov, '100'], capture_output=True, timeout=240)
        print('  %-40s строк %d/%d | не найдено %d | лишних %d | сдвинуто %d  (%s)'
              % (code, nb, na, len(miss), len(extra), len(worst), ov))
        for w in worst[:5]:
            print('        Δx=%s Δy=%s | %r' % w)
        for m in miss[:3]:
            print('        НЕТ: %r' % m[:60])


if __name__ == '__main__':
    main()
