#!/usr/bin/env python3
"""Проверка сборки письма Bridging через тот же путь, что у сайта."""
import sys
import sqlite3

sys.path.insert(0, '/opt/wolf_v2')
from services.values import build_template_values
from services import doc_engine

APP = 107
CODE = 'bridging_request_letter__default'

c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row
a = dict(c.execute('SELECT * FROM applications WHERE id=?', (APP,)).fetchone())
cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone())
vals = build_template_values(cl, CODE, {}, APP) or {}
print('itk_no =', vals.get('itk_no'))
print('itk_expiry =', vals.get('itk_expiry'))
print('gender =', vals.get('client_gender'))
res = doc_engine.build_document(CODE, vals, '/opt/wolf_v2/data/renders', engine='word')
print('build_document ->', str(res)[:300])
