#!/usr/bin/env python3
"""Дозаполнение базы организаций: города, адреса, директора, логотипы.

Источники на сервере (без обращения к Google Диску):
  data/orgs_web_cities.json  — ИНН, город, адрес, директор
  data/orgs_web_moscow.json  — ИНН, город, адрес, логотип
  data/organizations.json    — базовый пул
"""
import json
import re
import sqlite3
from pathlib import Path

DATA = Path('/opt/wolf_v2/data')
DB = DATA / 'wolf.db'


def city_of(address: str) -> str:
    a = str(address or '').lower()
    if 'москв' in a or 'moscow' in a:
        return 'Москва'
    if 'петербург' in a or 'petersburg' in a:
        return 'Санкт-Петербург'
    return ''


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
now = '2026-10-17T11:00:00'

cities = {str(o.get('inn')): o for o in (load('orgs_web_cities.json').get('organizations') or [])}
moscow = {str(o.get('inn')): o for o in (load('orgs_web_moscow.json').get('organizations') or [])}

added = filled = 0
for inn, o in {**moscow, **cities}.items():
    if not inn:
        continue
    row = c.execute('SELECT id FROM pool_organizations WHERE inn=?', (inn,)).fetchone()
    vals = dict(o)
    vals['city'] = vals.get('city') or city_of(vals.get('address'))
    if not row:
        c.execute("""INSERT INTO pool_organizations
            (inn,kpp,ogrn,name,name_en,legal_form_en,city,address,director,sector,domain,
             description,logo_path,source,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (inn, vals.get('kpp') or '', vals.get('ogrn') or '', vals.get('name') or '', '', '',
                   vals.get('city') or '', vals.get('address') or '', vals.get('director') or '',
                   vals.get('sector') or '', vals.get('domain') or '', '', vals.get('logo') or '',
                   'orgs_web', now))
        added += 1
        continue
    sets, args = [], []
    for field in ('city', 'address', 'director', 'kpp', 'ogrn', 'domain', 'logo_path'):
        v = vals.get('logo') if field == 'logo_path' else vals.get(field)
        if v:
            sets.append(f'{field}=?')
            args.append(v)
    if sets:
        args.append(row['id'])
        c.execute(f'UPDATE pool_organizations SET {", ".join(sets)} WHERE id=?', args)
        filled += 1

# города по адресу там, где пусто
for r in c.execute("SELECT id, address FROM pool_organizations WHERE COALESCE(city,'')=''").fetchall():
    city = city_of(r['address'])
    if city:
        c.execute('UPDATE pool_organizations SET city=? WHERE id=?', (city, r['id']))
        filled += 1

c.commit()
print('добавлено организаций:', added, '| обновлено:', filled)
for r in c.execute("SELECT COALESCE(NULLIF(city,''),'—') c, COUNT(*) n FROM pool_organizations GROUP BY 1 ORDER BY n DESC"):
    print('  ', r['c'], r['n'])
print('без директора:', c.execute("SELECT COUNT(*) FROM pool_organizations WHERE COALESCE(director,'')=''").fetchone()[0])
print('всего:', c.execute('SELECT COUNT(*) FROM pool_organizations').fetchone()[0])
