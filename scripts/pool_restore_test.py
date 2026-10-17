#!/usr/bin/env python3
"""Восстановление записей, изменённых проверкой редактирования."""
import json
import sqlite3
from pathlib import Path

DATA = Path('/opt/wolf_v2/data')
c = sqlite3.connect(DATA / 'wolf.db')
c.row_factory = sqlite3.Row

org = c.execute('SELECT * FROM pool_organizations WHERE name=? OR name=?',
                ('ТЕСТ ОРГ', '')).fetchone()
pools = []
for name in ('orgs_pool.json', 'orgs_web_cities.json', 'orgs_web_moscow.json', 'organizations.json'):
    d = json.loads((DATA / name).read_text(encoding='utf-8'))
    items = d.get('organizations') if isinstance(d, dict) else d
    if isinstance(items, dict):
        items = list(items.values())
    pools.extend(items or [])

if org:
    src = next((o for o in pools if str(o.get('inn')) == str(org['inn'])), None)
    if src:
        c.execute("""UPDATE pool_organizations SET name=?, name_en=?, city=?, address=?,
                     director=?, sector=?, domain=?, updated_at=? WHERE id=?""",
                  (src.get('name') or '', src.get('name_en') or '', src.get('city') or '',
                   src.get('address') or '', src.get('director') or '', src.get('sector') or '',
                   src.get('domain') or '', '2026-10-17T11:05:00', org['id']))
        print('восстановлена организация:', src.get('name'), org['inn'])
    else:
        print('источник для организации не найден:', org['inn'])

prof = c.execute("SELECT * FROM pool_professions WHERE title_en='Test Profession'").fetchone()
if prof:
    pos = json.loads((DATA / 'cv_positions.json').read_text(encoding='utf-8')).get('positions') or []
    src = next((p for p in pos if p.get('code') == prof['code']), None)
    if src:
        blocks = src.get('blocks') or {}
        c.execute("""UPDATE pool_professions SET title_en=?, title_ru=?, sector=?, duties=?, skills=? WHERE id=?""",
                  (src.get('en') or '', src.get('ru') or '', src.get('sector') or '',
                   blocks.get('long') or blocks.get('medium') or blocks.get('short') or '',
                   ', '.join(src.get('skills') or []) if isinstance(src.get('skills'), list) else (src.get('skills') or ''),
                   prof['id']))
        print('восстановлена профессия:', src.get('en'))
    else:
        remote = json.loads((DATA / 'remote_professions.json').read_text(encoding='utf-8')).get('sectors') or {}
        for sector, titles in remote.items():
            for t in titles or []:
                if t == prof['title_ru'] or t.lower().replace(' ', '_') == prof['code']:
                    c.execute('UPDATE pool_professions SET title_en=?, title_ru=?, sector=? WHERE id=?',
                              (t, t, sector, prof['id']))
                    print('восстановлена профессия из пула:', t)
c.commit()
print('пустых названий организаций:', c.execute("SELECT COUNT(*) FROM pool_organizations WHERE COALESCE(name,'')=''").fetchone()[0])
