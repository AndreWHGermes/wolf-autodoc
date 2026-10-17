#!/usr/bin/env python3
"""Импорт пулов в базу «База значений» и проверка страницы через тестовый клиент."""
import sys

sys.path.insert(0, '/opt/wolf_v2')

from blocks.pool.page import import_pools, _db  # noqa: E402

res = import_pools()
print('импорт:', res)
with _db() as c:
    print('в базе организаций:', c.execute('SELECT COUNT(*) FROM pool_organizations').fetchone()[0])
    print('в базе профессий:', c.execute('SELECT COUNT(*) FROM pool_professions').fetchone()[0])
    print('с директором:', c.execute("SELECT COUNT(*) FROM pool_organizations WHERE director<>''").fetchone()[0])
    print('городов:', [r[0] for r in c.execute("SELECT city, COUNT(*) FROM pool_organizations GROUP BY city ORDER BY COUNT(*) DESC LIMIT 5")])

from app import create_app  # noqa: E402

app = create_app()
client = app.test_client()
with client.session_transaction() as s:
    s['user_id'] = 1
    s['role'] = 'admin'
    s['user_role'] = 'admin'
    s['user_name'] = 'Проверка'
for url in ('/pool', '/pool?tab=organizations', '/pool?tab=organizations&city=Москва'):
    r = client.get(url)
    html = r.get_data(as_text=True)
    print(url, '->', r.status_code, '| карточек:', html.count('<details class="card"'),
          '| ИНН в тексте:', 'ИНН' in html)
