#!/usr/bin/env python3
"""Сборка резюме по правилу и проверка: пусто/плейсхолдеры/картинка."""
import sqlite3
import sys

sys.path.insert(0, '/opt/wolf_v2')
import pymupdf

from services.values import build_template_values
from services import doc_engine

APP = int(sys.argv[1]) if len(sys.argv) > 1 else 109
c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row
a = dict(c.execute('SELECT * FROM applications WHERE id=?', (APP,)).fetchone())
cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone()) if a.get('client_id') else {}
v = build_template_values(cl, 'cv__format_sivaev', {}, APP) or {}
res = doc_engine.build_document('cv__format_sivaev', v, '/opt/wolf_v2/data/renders',
                               engine='word', name='cv_check')
d = pymupdf.open(res['pdf'])
print('заявка', APP, '| страниц', len(d), '| пусто', res['missing'], '| ph', res['placeholders'])
print('профиль:', str(v.get('cv_summary'))[:170])
print('место 1:', v.get('cv_job1_title'), '|', v.get('cv_job1_company'), '|', v.get('cv_job1_period'))
print('место 2:', v.get('cv_job2_title'), '|', v.get('cv_job2_company'), '|', v.get('cv_job2_period'))
d[0].get_pixmap(dpi=110).save('/opt/wolf_v2/data/renders/cv_check.png')
print('png: data/renders/cv_check.png')
