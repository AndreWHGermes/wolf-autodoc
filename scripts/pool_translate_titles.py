#!/usr/bin/env python3
"""Перевод названий профессий на русский (бесплатная модель, батчами по 30)."""
import json
import re
import sqlite3
import subprocess

DB = '/opt/wolf_v2/data/wolf.db'
ASK = '/root/scripts/ask_free.py'

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute('SELECT id, title_en, title_ru FROM pool_professions')]
bad = [r for r in rows if not re.search('[А-Яа-яЁё]', r['title_ru'] or '')]
print('к переводу:', len(bad))


def ask(titles: list[str]) -> list[str]:
    prompt = ("Переведи названия должностей на русский язык. Ответь ТОЛЬКО JSON-массивом строк "
              "в том же порядке, без пояснений. Названия: " + json.dumps(titles, ensure_ascii=False))
    out = subprocess.run(['/usr/bin/python3', ASK, prompt], capture_output=True, text=True, timeout=240).stdout
    m = re.search(r'\[.*\]', out, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return [str(x).strip() for x in data]
    except Exception:
        return []


updated = 0
for i in range(0, len(bad), 30):
    chunk = bad[i:i + 30]
    titles = [r['title_en'] for r in chunk]
    got = ask(titles)
    if len(got) != len(chunk):
        got = (got + [''] * len(chunk))[:len(chunk)]
    for r, ru in zip(chunk, got):
        if ru and re.search('[А-Яа-яЁё]', ru):
            c.execute('UPDATE pool_professions SET title_ru=? WHERE id=?', (ru, r['id']))
            updated += 1
    c.commit()
    print(f'  батч {i // 30 + 1}: переведено {updated}/{min(i + 30, len(bad))}')

# добор по одному для пропущенных
left = [dict(r) for r in c.execute('SELECT id, title_en FROM pool_professions')]
left = [r for r in left if not re.search('[А-Яа-яЁё]', r['title_ru'] or '')]
for r in left:
    got = ask([r['title_en']])
    if got and re.search('[А-Яа-яЁё]', got[0]):
        c.execute('UPDATE pool_professions SET title_ru=? WHERE id=?', (got[0], r['id']))
        updated += 1
c.commit()
rest = c.execute("SELECT COUNT(*) FROM pool_professions WHERE title_ru NOT GLOB '*[А-Яа-яЁё]*'").fetchone()[0]
print('обновлено:', updated, '| осталось без русского:', rest)
