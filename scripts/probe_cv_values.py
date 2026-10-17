#!/usr/bin/env python3
"""Что генератор резюме отдаёт по заявке: где пусто и почему."""
import sqlite3
import sys

sys.path.insert(0, '/opt/wolf_v2')
from services.values import build_template_values

APP = 109
c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row
a = dict(c.execute('SELECT * FROM applications WHERE id=?', (APP,)).fetchone())
cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone())
print('карточка: position=', cl.get('position'), '| company_name=', cl.get('company_name'),
      '| sector=', cl.get('sector'))
v = build_template_values(cl, 'cv__format_sivaev', {}, APP) or {}
for k in ('cv_profession', 'cv_job1_title', 'cv_job1_company', 'cv_job1_period', 'cv_job1_bullets',
          'cv_job2_title', 'cv_job2_company', 'cv_job2_period', 'cv_job2_bullets',
          'cv_skills_hard', 'cv_skills_soft', 'cv_summary', 'cv_education_degree'):
    x = str(v.get(k) or '')
    print(f'  {k:<20} {"ЕСТЬ " if x.strip() else "ПУСТО"} {x[:70]!r}')
