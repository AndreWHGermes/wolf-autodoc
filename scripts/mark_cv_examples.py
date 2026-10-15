#!/usr/bin/env python3
"""Разметка реальных примеров CV + запись значений примера в базу.

Для трёх форм CV берём реальные заполненные документы клиентов (сканы из архива),
находим в них значения переменных и подсвечиваем жёлтым, как в остальных документах.
Значения примера сохраняем в variables.examples_json — тогда работает
«📋 Подставить значения из примера» и сверка HTML с реальным документом.
"""
import json
import sqlite3
from pathlib import Path

import pymupdf

DB = '/opt/wolf_v2/data/wolf.db'
YELLOW = (1.0, 0.9, 0.35)

# значения, прочитанные из реальных резюме клиентов (архив Drive)
SOURCE = {
    'cv__format_CLIENT': {
        'pdf': '/opt/wolf_v2/data/sources/cv__format_CLIENT.pdf',
        'vals': {
            'cv_name': 'IVAN CLIENT',
            'cv_job_title': 'Executive Director',
            'cv_location': 'Moscow, Russia',
            'cv_date_of_birth': '08.01.1999',
            'cv_nationality': 'Russian Federation',
            'cv_passport_no': '77 0139869',
            'cv_job1_title': 'Executive Director',
            'cv_job1_period': 'September 2025 – Present',
            'cv_job1_company': 'LLC "INGREDIENTTRADE", Zelenograd, Moscow, Russia',
            'cv_education1_school': 'Lomonosov Moscow State University',
            'cv_education1_period': '2017 – 2022',
            'cv_education1_degree': 'Business Management – Bachelor Degree',
        },
    },
    'cv__format_short': {
        'pdf': '/opt/wolf_v2/data/sources/cv__format_short.pdf',
        'vals': {
            'cv_name': 'Artur Balabaev',
            'cv_job_title': 'Personal Assistant',
            'cv_date_of_birth': '29 July 2002',
            'cv_nationality': 'Russian Federation',
            'cv_place_of_birth': 'Khabarovsk Krai, Russia',
            'cv_passport_no': '77 2829709',
            'cv_passport_issue': '15 March 2024',
            'cv_passport_expiry': '15 March 2034',
            'cv_job1_title': 'Personal Assistant',
            'cv_job1_period': 'Jun 2025 – Present',
            'cv_job1_company': 'LLC ROBUSTA',
            'cv_job2_title': 'Manager Assistant',
            'cv_job2_period': 'Sep 2023 – Aug 2025',
            'cv_job2_company': 'Avito',
            'cv_education1_school': 'Khabarovsk State University of Economics and Law (KSUEL)',
        },
    },
    'cv__format_detailed': {
        'pdf': '/opt/wolf_v2/data/sources/cv__format_detailed.pdf',
        'vals': {
            'cv_name': 'Viktoriia Korchagina',
            'cv_date_of_birth': 'November 3, 1990',
            'cv_place_of_birth': 'Yakutsk, Yakutskaya ASSR, USSR',
            'cv_nationality': 'Russian Federation',
            'cv_passport_no': '77 9937194',
            'cv_passport_issue': 'August 14, 2026',
            'cv_passport_expiry': 'August 14, 2036',
            'cv_job1_title': 'Senior Sales Manager',
            'cv_job1_company': 'TechSolutions LLC, Moscow, Russia',
            'cv_job1_period': 'March 2018 – Present',
        },
    },
}

conn = sqlite3.connect(DB, timeout=30)
conn.row_factory = sqlite3.Row
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
VAR_TABLE = 'variables'
for cand in ('variables', 'template_variables'):
    if cand in tables:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info({cand})')}
        if 'examples_json' in cols and 'template_id' in cols:
            VAR_TABLE = cand
            break
print('таблица переменных:', VAR_TABLE)

for code, cfg in SOURCE.items():
    t = conn.execute('SELECT id FROM templates WHERE code=?', (code,)).fetchone()
    if not t:
        print(f'{code}: шаблон не найден')
        continue
    tid = t['id']
    pdf_in = cfg['pdf']
    vals = cfg['vals']
    if not vals:
        print(f'{code}: значений нет — пропускаю')
        continue

    # 1. жёлтая разметка найденных значений на реальном документе
    doc = pymupdf.open(pdf_in)
    marks = 0
    for var, val in vals.items():
        needle = str(val).strip()
        if not needle or len(needle) > 70:
            continue
        for pg in doc:
            for rect in pg.search_for(needle):
                r = pymupdf.Rect(rect.x0 - 1.5, rect.y0 - 1.5, rect.x1 + 1.5, rect.y1 + 1.5)
                shape = pg.new_shape()
                shape.draw_rect(r)
                shape.finish(color=None, fill=YELLOW, fill_opacity=0.45, width=0)
                shape.commit()
                marks += 1
    out_dir = Path(f'/opt/wolf_v2/data/templates/{code}')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = out_dir / 'example_marked.pdf'
    doc.save(str(out_pdf), deflate=True, garbage=3)
    doc.close()
    print(f'{code}: плашек {marks} → {out_pdf}')

    # 2. значения примера в базу (для подстановки и сверки)
    saved = 0
    for var, val in vals.items():
        row = conn.execute(f'SELECT name FROM {VAR_TABLE} WHERE template_id=? AND name=?',
                           (tid, var)).fetchone()
        if not row:
            continue
        conn.execute(f'UPDATE {VAR_TABLE} SET examples_json=? WHERE template_id=? AND name=?',
                     (json.dumps([val], ensure_ascii=False), tid, var))
        saved += 1
    conn.commit()
    print(f'   значений примера записано: {saved}')
conn.close()
