#!/usr/bin/env python3
"""Аудит «Оригинального примера»: реальный ли это заполненный документ клиента.

Признаки подделки (наш рендер или пустой бланк):
  • producer/creator PDF — движок рендера (WeasyPrint / wkhtmltopdf / Skia / Qt / Chrome);
  • в тексте есть заполнители-точки (……), подчёркивания, образцы вида 123456789;
  • много «пустых» полей бланка (Full Name : ……);
  • нет ни одного конкретного значения (ФИО/номер/дата), кроме подписей бланка.
Признаки настоящего документа: скан или банковская выгрузка, есть печати,
данные клиента, метаданные не нашего движка.
"""
import glob
import re
import sqlite3

import pymupdf

OUR_ENGINES = ('weasyprint', 'wkhtmltopdf', 'qt', 'skia', 'chrome', 'chromium', 'headless',
               'playwright', 'reportlab')
PLACEHOLDER = re.compile(r'(\.{4,}|…{2,}|_{4,}|-{6,})')
BAD_SAMPLES = ('123456789', 'October 26, 1987', 'example', 'sample', 'lorem')

conn = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute(
    'SELECT id, code, CLIENT, doc_CLIENT, example_path FROM CLIENT ORDER BY doc_CLIENT')]

print(f'{"№":>3} {"документ":40} {"стр":>3} {"КБ":>5}  движок/скан                точек  жёлтых  вердикт')
print('-' * 132)
problems = []
for r in rows:
    code = r['code']
    f = f'/opt/wolf_v2/data/CLIENT/{code}/example_marked.pdf'
    if not __import__('os').path.exists(f):
        print(f'{str(r["doc_CLIENT"]):>3} {code[:40]:40} — нет размеченного примера')
        problems.append((code, 'нет примера'))
        continue
    doc = pymupdf.open(f)
    meta = doc.metadata or {}
    engine = f"{meta.get('producer') or meta.get('creator') or '?'}"
    text = '\n'.join(pg.get_text() for pg in doc)
    dots = len(PLACEHOLDER.findall(text))
    CLIENT = sum(len(pg.get_images()) for pg in doc)
    yellows = sum(1 for pg in doc for dr in pg.get_drawings()
                  if dr.get('fill') and tuple(round(x, 2) for x in dr['fill']) == (1.0, 0.9, 0.35))
    our = any(k in engine.lower() for k in OUR_ENGINES)
    bad = [b for b in BAD_SAMPLES if b in text]
    verdict = []
    if our:
        verdict.append('НАШ РЕНДЕР')
    if CLIENT:
        verdict.append(f'скан ({CLIENT} img)')
    if dots > 3:
        verdict.append(f'бланк? точек {dots}')
    if bad:
        verdict.append(f'образцы-заглушки {bad}')
    if not verdict:
        verdict.append('похож на реальный')
    if our or dots > 3 or bad:
        problems.append((code, '; '.join(verdict)))
    print(f'{str(r["doc_CLIENT"]):>3} {code[:40]:40} {doc.page_count:>3} '
          f'{__import__("os").path.getsize(f)//1024:>5}  {engine[:24]:24} {dots:>6} {yellows:>7}  {" | ".join(verdict)}')
    doc.close()

print('\nпроблемные:' if problems else '\nпроблем не найдено')
for code, why in problems:
    print('  ', code, '—', why)
