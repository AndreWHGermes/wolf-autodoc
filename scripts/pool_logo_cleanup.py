#!/usr/bin/env python3
"""Чистка логотипов: убирает одинаковые картинки и заглушки с мусорных доменов."""
import hashlib
import sqlite3
from pathlib import Path

DATA = Path('/opt/wolf_v2/data')
DB = DATA / 'wolf.db'
BAD_DOMAINS = {'www.ru', 'ru', 'www.com', 'com', 'example.com', 'yandex.ru', 'vk.com'}

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT id, inn, domain, logo_path FROM pool_organizations WHERE COALESCE(logo_path,'')<>''")]

seen: dict[str, int] = {}
removed = 0
for r in rows:
    rel = r['logo_path']
    if str(rel).startswith(('http://', 'https://')):
        continue
    p = DATA / rel
    if not p.exists():
        continue
    h = hashlib.md5(p.read_bytes()).hexdigest()
    bad_domain = (r['domain'] or '').strip().lower() in BAD_DOMAINS
    if bad_domain or h in seen:
        c.execute('UPDATE pool_organizations SET logo_path=NULL WHERE id=?', (r['id'],))
        try:
            p.unlink()
        except OSError:
            pass
        removed += 1
    else:
        seen[h] = r['id']
c.commit()
print('убрано логотипов:', removed, '| осталось локальных уникальных:', len(seen))
print('всего с логотипом:', c.execute(
    "SELECT COUNT(*) FROM pool_organizations WHERE COALESCE(logo_path,'')<>''").fetchone()[0])
