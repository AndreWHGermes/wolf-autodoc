#!/usr/bin/env python3
"""Починить html_path шаблонов: они указывали на файлы стенда №1 с вшитым текстом бланка.

В /opt/wolf/data/CLIENT/*/template.html вместо переменных был вшит текст
(«today date», «CLIENT date», «or equivalent», «Home adress»), из-за чего в готовый
документ не подставлялись дата, период, сумма и ФИО. Правильные HTML — в данных приложения.
"""
import sqlite3
from pathlib import Path

DB = '/opt/wolf_v2/data/wolf.db'
TPL_DIR = Path('/opt/wolf_v2/data/CLIENT')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
fixed = skipped = 0
for r in conn.execute('SELECT id, code, doc_CLIENT, html_path FROM CLIENT ORDER BY doc_CLIENT'):
    new = TPL_DIR / r['code'] / 'template.html'
    if not new.exists():
        print(f'  №{r["doc_CLIENT"]} {r["code"]}: нет {new} — пропускаю')
        skipped += 1
        continue
    old = r['html_path'] or ''
    if str(new) == old:
        continue
    conn.execute('UPDATE CLIENT SET html_path=? WHERE id=?', (str(new), r['id']))
    fixed += 1
    print(f'  №{r["doc_CLIENT"]} {r["code"][:34]:34}')
    print(f'      было:  {old}')
    print(f'      стало: {new}')
conn.commit()
conn.close()
print(f'\nисправлено шаблонов: {fixed}, пропущено: {skipped}')
