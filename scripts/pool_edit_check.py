#!/usr/bin/env python3
"""Проверка редактирования базы значений через тестовый клиент (админ и просмотр)."""
import sys

sys.path.insert(0, '/opt/wolf_v2')

from blocks.pool.page import _db  # noqa: E402
from app import create_app  # noqa: E402

app = create_app()
admin = app.test_client()
with admin.session_transaction() as s:
    s.update({'user_id': 1, 'role': 'admin', 'user_role': 'admin', 'user_name': 'Проверка'})

with _db() as c:
    row = c.execute("SELECT id, director, city FROM pool_organizations WHERE COALESCE(director,'')='' LIMIT 1").fetchone()
    pid = c.execute("SELECT id FROM pool_professions LIMIT 1").fetchone()['id']
print('организация без директора:', row['id'])

r = admin.get('/pool?tab=organizations')
print('страница организаций:', r.status_code, '| форм редактирования:', r.get_data(as_text=True).count('edit'))
r = admin.get('/pool?tab=professions')
print('страница профессий:', r.status_code, '| форм редактирования:', r.get_data(as_text=True).count('/pool/prof/'))

r = admin.post(f"/pool/org/{row['id']}/edit", data={
    'name': 'ТЕСТ ОРГ', 'name_en': 'TEST ORG LLC', 'city': 'Москва',
    'address': 'Москва, ул. Тестовая, 1', 'director': 'Иванов Иван Иванович',
    'sector': 'services_agency', 'domain': '', 'description': 'проверка'}, follow_redirects=False)
print('сохранение организации:', r.status_code)
with _db() as c:
    print('  в базе:', dict(c.execute('SELECT name, director, city FROM pool_organizations WHERE id=?', (row['id'],)).fetchone()))
    c.execute('UPDATE pool_organizations SET name=?, director=?, city=? WHERE id=?',
              ('', row['director'] or '', row['city'] or '', row['id']))
    c.commit()

r = admin.post(f'/pool/prof/{pid}/edit', data={
    'title_en': 'Test Profession', 'title_ru': 'Тест', 'sector': 'it_software',
    'duties': 'строка 1\nстрока 2', 'skills': 'skill a, skill b', 'description': 'проверка'},
    follow_redirects=False)
print('сохранение профессии:', r.status_code)
with _db() as c:
    print('  в базе:', dict(c.execute('SELECT title_en, duties FROM pool_professions WHERE id=?', (pid,)).fetchone()))

viewer = app.test_client()
with viewer.session_transaction() as s:
    s.update({'user_id': 2, 'role': 'viewer', 'user_role': 'viewer', 'user_name': 'Просмотр'})
r = viewer.post(f"/pool/org/{row['id']}/edit", data={'name': 'X'})
print('запись под просмотром:', r.status_code, '(ожидается 403)')
