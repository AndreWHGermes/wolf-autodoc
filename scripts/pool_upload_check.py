#!/usr/bin/env python3
"""Импорт пулов + проверка загрузки логотипа и печати через тестовый клиент."""
import io
import sys

sys.path.insert(0, '/opt/wolf_v2')

from PIL import Image  # noqa: E402

from blocks.pool.page import import_pools, _db  # noqa: E402

print('импорт:', import_pools())
with _db() as c:
    print('организаций:', c.execute('SELECT COUNT(*) FROM pool_organizations').fetchone()[0])
    print('без города:', c.execute("SELECT COUNT(*) FROM pool_organizations WHERE city=''").fetchone()[0])
    print('города:', c.execute("SELECT city, COUNT(*) FROM pool_organizations GROUP BY city ORDER BY 2 DESC").fetchall())
    oid, inn = c.execute("SELECT id, inn FROM pool_organizations WHERE director<>'' ORDER BY id LIMIT 1").fetchone()
print('тестовая организация:', oid, inn)

from app import create_app  # noqa: E402

app = create_app()
client = app.test_client()
with client.session_transaction() as s:
    s.update({'user_id': 1, 'role': 'admin', 'user_role': 'admin', 'user_name': 'Проверка'})


def png(color):
    buf = io.BytesIO()
    Image.new('RGB', (120, 120), color).save(buf, 'PNG')
    buf.seek(0)
    return buf


for kind in ('logo', 'seal'):
    r = client.post(f'/pool/org/{oid}/upload/{kind}',
                    data={'file': (png('red' if kind == 'logo' else 'blue'), f'{kind}.png')},
                    content_type='multipart/form-data')
    print('upload', kind, '->', r.status_code)
    g = client.get(f'/pool/asset/{oid}/{kind}')
    print('asset', kind, '->', g.status_code, len(g.get_data()), 'байт')

r = client.get('/pool?tab=organizations&city=Москва')
print('страница Москвы:', r.status_code, '| картинок:', r.get_data(as_text=True).count('<img'))
