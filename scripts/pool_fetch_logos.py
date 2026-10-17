#!/usr/bin/env python3
"""Логотипы организаций с их сайтов: og:image → link rel=icon → /favicon.ico."""
import io
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

DATA = Path('/opt/wolf_v2/data')
DB = DATA / 'wolf.db'
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 40
HDR = {'User-Agent': 'Mozilla/5.0 (compatible; WolfAutoDoc/1.0)'}

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = c.execute("""SELECT id, inn, domain, name FROM pool_organizations
                    WHERE COALESCE(logo_path,'')='' AND COALESCE(domain,'')<>''
                    ORDER BY id LIMIT ?""", (LIMIT,)).fetchall()
print('к обработке:', len(rows))


def fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=8, headers=HDR)
        if r.ok and len(r.content) > 800:
            return r.content
    except Exception:
        return None
    return None


def find_logo(domain: str) -> bytes | None:
    base = 'https://' + domain.strip().strip('/')
    html = None
    for start in (base, 'http://' + domain.strip().strip('/')):
        try:
            r = requests.get(start, timeout=10, headers=HDR)
            if r.ok:
                html, base = r.text, start
                break
        except Exception:
            continue
    if html:
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
        if not m:
            m = re.search(r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]+href=["\']([^"\']+)', html, re.I)
        if m:
            data = fetch(urljoin(base, m.group(1)))
            if data:
                return data
    for path in ('/favicon.ico', '/favicon.png', '/logo.png'):
        data = fetch(urljoin(base, path))
        if data:
            return data
    return None


ok = 0
for r in rows:
    data = find_logo(r['domain'])
    if not data:
        continue
    try:
        im = Image.open(io.BytesIO(data)).convert('RGBA')
    except Exception:
        continue
    if min(im.size) < 32:
        continue
    im.thumbnail((400, 400))
    folder = DATA / 'pool_assets' / str(r['inn'])
    folder.mkdir(parents=True, exist_ok=True)
    im.save(folder / 'logo.png')
    c.execute('UPDATE pool_organizations SET logo_path=? WHERE id=?',
              (f'pool_assets/{r["inn"]}/logo.png', r['id']))
    ok += 1
    print('  +', r['name'], '←', r['domain'], im.size)
c.commit()
print('скачано логотипов:', ok)
print('всего с логотипом:', c.execute("SELECT COUNT(*) FROM pool_organizations WHERE COALESCE(logo_path,'')<>''").fetchone()[0])
