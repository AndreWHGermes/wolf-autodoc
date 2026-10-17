#!/usr/bin/env python3
"""Импорт вузов и русских описаний профессий + проверка новой страницы."""
import sys

sys.path.insert(0, '/opt/wolf_v2')

from blocks.pool.page_v2 import import_pools, _db  # noqa: E402

print('импорт:', import_pools())
with _db() as c:
    print('профессий:', c.execute('SELECT COUNT(*) FROM pool_professions').fetchone()[0])
    print('с RU-обязанностями:', c.execute("SELECT COUNT(*) FROM pool_professions WHERE COALESCE(duties_ru,'')<>''").fetchone()[0])
    print('вузов:', c.execute('SELECT COUNT(*) FROM pool_universities').fetchone()[0])
    print('города вузов:', [r[0] for r in c.execute('SELECT city_ru, COUNT(*) FROM pool_universities GROUP BY city_ru ORDER BY 2 DESC')])

from app import create_app  # noqa: E402

app = create_app()
cl = app.test_client()
with cl.session_transaction() as s:
    s.update({'user_id': 1, 'role': 'admin', 'user_role': 'admin', 'user_name': 'Проверка'})
for url in ('/pool', '/pool?tab=organizations', '/pool?tab=universities'):
    r = cl.get(url)
    html = r.get_data(as_text=True)
    print(url, '->', r.status_code, '| вкладок:', html.count('details class="card"'),
          '| групп:', html.count('margin:6px 0'), '| EN/RU:', html.count('grid-template-columns:1fr 1fr'))
print('правило в меню:', '/pool' in cl.get('/').get_data(as_text=True))
