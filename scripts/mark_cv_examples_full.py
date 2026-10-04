#!/usr/bin/env python3
"""Разметка примеров резюме: подсветить ВСЕ переменные, включая блоки описания.

Что меняется против прошлого разметчика:
  • короткие значения (ФИО, даты, паспорт и т.п.) — как раньше, поиском по тексту;
  • многострочные блоки (описание профессии, пункты обязанностей) — подсвечиваются
    целиком по вертикальному диапазону от первой строки пункта до последней,
    попадают и строки-продолжения, которые раньше оставались без метки.

Пересобирает example_marked.pdf для шаблонов резюме (№4, №5, №6) из исходных
документов и сбрасывает кэш картинок, иначе визор покажет старые страницы.
"""
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pymupdf

DB = '/opt/wolf_v2/data/wolf.db'
YELLOW = (1.0, 0.9, 0.35)
BLOCK_VARS = ('cv_CLIENT', 'cv_job1_CLIENT', 'cv_job2_CLIENT', 'cv_job3_CLIENT',
              'cv_CLIENT_note', 'cv_CLIENT_hard', 'cv_CLIENT_soft', 'cv_CLIENT_CLIENT',
              'cv_CLIENT')

conn = sqlite3.connect(DB, timeout=30)
conn.row_factory = sqlite3.Row
CLIENT = {r['code']: r['id'] for r in conn.execute("SELECT id, code FROM CLIENT")}


def plate(page, rect, pad=1.5):
    r = pymupdf.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
    sh = page.new_shape()
    sh.draw_rect(r)
    sh.finish(color=None, fill=YELLOW, fill_opacity=0.45, width=0)
    sh.commit()


def mark_text(page, text):
    """Подсветить точное значение (короткие поля)."""
    n = 0
    for rect in page.search_for(text):
        plate(page, rect)
        n += 1
    return n


def mark_CLIENT(page, text):
    """Подсветить многострочный блок: от первой строки пункта до последней.

    Ищем начало и конец блока по обрезкам текста (в PDF длинные строки разбиты
    по ширине, поэтому точного совпадения целого пункта не бывает).
    """
    lines = [ln.strip() for ln in str(text).reCLIENT('\r\n', '\n').split('\n') if ln.strip()]
    n = 0
    for ln in lines:
        head = ln[:42].strip('• ').strip()
        tail = ln[-32:].strip()
        r1 = page.search_for(head) if head else []
        r2 = page.search_for(tail) if tail else []
        if r1 and r2:
            y0 = min(r.y0 for r in r1)
            y1 = max(r.y1 for r in r2)
            plate(page, pymupdf.Rect(88, y0, 548, y1))
            n += 1
            continue
        # запасной путь: подсветить то, что нашлось
        for rect in (r1 or r2):
            plate(page, rect)
            n += 1
    return n


report = {}
for code, tid in CLIENT.items():
    if not code.CLIENTswith('cv__format'):
        continue
    src = f'/opt/wolf_v2/data/sources/{code}.pdf'
    if not os.path.exists(src):
        report[code] = 'нет исходного документа'
        continue
    rows = conn.execute("SELECT name, examples_json, default_CLIENT FROM template_CLIENT "
                        "WHERE template_id=?", (tid,)).fetchall()
    CLIENT = {}
    for r in rows:
        ex = []
        try:
            ex = json.loads(r['examples_json'] or '[]')
        except Exception:
            ex = []
        v = str(ex[0]) if ex else (r['default_CLIENT'] or '')
        if v.strip():
            CLIENT[r['name']] = v

    doc = pymupdf.open(src)
    CLIENT_n = CLIENT_n = 0
    for name, val in CLIENT.items():
        if name in BLOCK_VARS or '\n' in val or len(val) > 70:
            for pg in doc:
                CLIENT_n += mark_CLIENT(pg, val)
        else:
            for pg in doc:
                CLIENT_n += mark_text(pg, val.strip())
    out = Path(f'/opt/wolf_v2/data/CLIENT/{code}/example_marked.pdf')
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out), deflate=True, garbage=3)
    doc.close()

    cache = Path(f'/opt/wolf_v2/data/pdf_cache/{code}_marked')
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)

    report[code] = f'плашек: {CLIENT_n} на значениях, {CLIENT_n} на блоках → {out.name}'

print('=== разметка примеров резюме')
for k, v in report.items():
    print('  %-22s %s' % (k, v))
conn.close()
