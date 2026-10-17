#!/usr/bin/env python3
"""Сверка шаблона с эталоном: собрать документ с реальными значениями заявки и сравнить построчно.

    verify_template.py <код> [<код> ...] [--app 116]

Печатает сводку по каждому шаблону: сколько строк сошлось по координатам, сколько
сдвинуто, чего не хватает. Сами расхождения разбираются `compare_layout.py`.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from core import db as D  # noqa: E402
from services import doc_engine, values  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith('--')]
app_id = 116
if '--app' in sys.argv:
    app_id = int(sys.argv[sys.argv.index('--app') + 1])

app = D.q1('SELECT * FROM applications WHERE id=?', (app_id,))
client = D.q1('SELECT * FROM clients WHERE id=?', (app['client_id'],))
print('заявка %s, клиент: %s' % (app_id, client.get('full_name_en') or client.get('full_name')))

OUT = Path('/tmp/verify')
OUT.mkdir(parents=True, exist_ok=True)
codes = args or [r['code'] for r in D.q("SELECT code FROM templates ORDER BY id")]

for code in codes:
    tpl = D.q1('SELECT id, code, engine FROM templates WHERE code=?', (code,))
    if not tpl:
        print('%-34s | нет в БД' % code)
        continue
    try:
        vals = values.build_template_values(dict(client), code, {}, app_id=app_id) or {}
    except Exception as e:
        print('%-34s | значения не собрались: %s' % (code, e))
        continue
    try:
        res = doc_engine.build_document(code, vals, OUT, name='verify_' + code)
    except Exception as e:
        print('%-34s | сборка упала: %s' % (code, str(e)[:70]))
        continue
    pdf = res.get('pdf')
    ph = res.get('placeholders') or []
    status = 'ok' if pdf else 'НЕ СОБРАЛСЯ'
    print('%-34s | %-8s | %-12s | значений %3d | остатки меток %s'
          % (code, tpl['engine'], status, len(vals), ph[:4] if ph else 'нет'))
    if pdf:
        subprocess.run(['/usr/bin/python3', '/opt/wolf_v2/scripts/compare_layout.py', code, str(pdf)])
