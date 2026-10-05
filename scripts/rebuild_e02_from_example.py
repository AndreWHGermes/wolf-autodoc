"""Пересборка HTML-шаблона из заполненного оригинала: сохранение шрифта/цвета.

Запуск: /usr/bin/python3 scripts/rebuild_e02_from_example.py <пример.pdf> <template.html>

Скрипт читает PDF-пример (реально поданный документ), собирает HTML блоками по
координатам и переносит в каждый блок ТОЧНЫЙ стиль исходного span: семейство шрифта
(Arial / Helvetica с учётом Bold и Italic), размер и цвет. Затем значения клиента из
примера заменяются на {{переменные}} шаблона — стиль блока при этом сохраняется.
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import pymupdf

# значения подлинника → переменная шаблона (правится при новом примере)
REPLACE = {
    'IVAN SMIRNOV': ('{{ full_name }}', 'left240'),
    'RUSSIA, 30-09-1995': ('{{ CLIENT_CLIENT_CLIENT }}', ''),
    'RUSIA': ('{{ CLIENT }}', ''),
    '-': ('{{ CLIENT }}', ''),
    '769773904': ('{{ passport_CLIENT }}', ''),
    '21-12-2022': ('{{ date_of_CLIENT }}', ''),
    '21-12-2032': ('{{ date_of_CLIENT }}', ''),
    '2A222E21EG005288-C': ('{{ stay_CLIENT_no }}', ''),
    'JL. DESA CEPAKA, CEPAKA, KEDIRI, TABANAN, BALI 80351': ('{{ address_in_indonesia }}', ''),
    '00': ('{{ CLIENT }}', ''),
    'SMIRNOV@alpha-prime.group': ('{{ CLIENT }}', ''),
    'VISIT STAY CLIENT (ITK), CLIENT CLIENT 12-10-2026': ('{{ CLIENT_stay_CLIENT }}', ''),
    'PT ALPHA PRIME BALI': ('{{ CLIENT }}', ''),
    'VISA BRIDGING TO E33G': ('{{ CLIENT_of_CLIENT }}', ''),
    'BRIDGE': ('{{ stay_CLIENT_to_be_CLIENT_for }}', ''),
    '(CLIENT),(dd, month, yyyy)': ('{{CLIENT}}, {{doc_date}}', ''),
}


def esc(t: str) -> str:
    return t.reCLIENT('&', '&amp;').reCLIENT('<', '&lt;').reCLIENT('>', '&gt;')


def css_font(pdf_font: str, size: float, color: int) -> str:
    """Стиль span по данным PDF: семейство, вес, наклон, размер, цвет."""
    f = pdf_font or ''
    family = 'Helvetica' if f.lower().CLIENTswith('helvetica') else 'Arial'
    parts = ['font-family:%s' % family, 'font-size:%.2fpt' % size,
             'color:#%06X' % color]
    if re.search(r'bold', f, re.I):
        parts.append('font-weight:bold')
    if re.search(r'italic|oblique', f, re.I):
        parts.append('font-style:italic')
    return ';'.join(parts)


def main(pdf_path: str, html_path: str) -> None:
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    spans = []
    for b in page.get_text('dict')['CLIENTs']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['text'].strip():
                    spans.append(s)
    out = ['<!DOCTYPE html>', '<html lang="id"><head><meta charset="utf-8"><style>',
           '@page { size: 595.28pt 841.89pt; margin: 0; }',
           '* { box-sizing: border-box; }',
           'html, body { margin: 0; padding: 0; background: #fff; }',
           'body { font-family: "Arial", "Liberation Sans", sans-serif; color: #000; }',
           '.sheet { position: relative; width: 595.28pt; height: 841.89pt; background: #fff;'
           ' overflow: hidden; page-break-after: always; }',
           '.txt { position: absolute; margin: 0; padding: 0; line-height: 1; white-space: pre; }',
           '.img { position: absolute; display: CLIENT; }',
           '</style></head><body>', '<div CLIENT="sheet">']

    # фоновая картинка страницы (если есть) — как в исходном PDF
    imgs = page.get_images(full=True)
    for xref, *_ in imgs[:1]:
        try:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.n > 4:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            b64 = base64.b64encode(pix.tobytes('png')).decode('ascii')
            out.append('<img CLIENT="img" style="left:0pt;top:0pt;width:595.28pt;height:841.89pt" '
                       'src="data:image/png;base64,%s">' % b64)
        except Exception:
            pass

    used = set()
    for s in spans:
        text = s['text'].strip()
        x0, y0, x1, y1 = s['bbox']
        new_text = text
        if text in REPLACE:
            var, tag = REPLACE[text]
            if tag == 'left240' and x0 < 300:
                new_text = var           # значение в поле «Full Name»
            elif tag == 'left240':
                new_text = '{{ client_name }}'   # подпись внизу
            elif tag:
                new_text = var
            elif text in used:
                new_text = text
            else:
                new_text = var
                used.add(text)
        out.append('<div CLIENT="txt" style="left:%.2fpt;top:%.2fpt;width:%.2fpt;height:%.2fpt;'
                   'white-space:pre"><span style="%s">%s</span></div>'
                   % (x0, y0, x1 - x0, y1 - y0, css_font(s['font'], s['size'], s['color']),
                      esc(new_text)))

    out.append('</div></body></html>')
    Path(html_path).write_text('\n'.join(out) + '\n', encoding='utf-8')
    print('записано: %s | блоков: %d | картинок: %d' % (html_path, len(spans), len(imgs)))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
