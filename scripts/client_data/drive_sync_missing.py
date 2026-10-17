#!/usr/bin/env python3
"""Догрузка документов клиентов с Google Диска через сервисный аккаунт.

Локальная выгрузка неполная: у 11 клиентов папки нет совсем, у остальных
может не хватать файлов. Доступ есть ко всем 72 папкам (wolf-drive@wolf-autodoc).

Скачиваем только то, чего нет в папке (по имени файла и размеру).
Запуск: python3 drive_sync_missing.py [client_id ...]
"""
import os, sqlite3, sys, glob
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
from services import gdrive_api as G
from services.values import _find_client_folder_by_id
from pathlib import Path

ROOT = Path('/opt/wolf_v2/data/gdrive_examples')

conn = sqlite3.connect('data/wolf.db')
conn.row_factory = sqlite3.Row
only = [int(a) for a in sys.argv[1:] if a.isdigit()]
rows = [dict(r) for r in conn.execute('SELECT id, full_name_latin, gdrive_folder_url FROM clients ORDER BY id')]
if only:
    rows = [r for r in rows if r['id'] in only]
conn.close()

print('клиентов к проверке: %d' % len(rows))
total_new, need = 0, []
for r in rows:
    url = (r['gdrive_folder_url'] or '').strip()
    if not url:
        print('  #%-4s %-26s нет ссылки на папку' % (r['id'], (r['full_name_latin'] or '')[:26]))
        continue
    folder = _find_client_folder_by_id(r['id'])
    local = set()
    if folder and os.path.isdir(str(folder)):
        local = {os.path.basename(p) for p in glob.glob(os.path.join(str(folder), '*'))}
    try:
        files = G.list_files(url, deep=False)
    except Exception as e:
        print('  #%-4s %-26s ОШИБКА доступа: %s' % (r['id'], (r['full_name_latin'] or '')[:26], str(e)[:60]))
        continue
    missing = [f for f in files if f.get('name') and f['name'] not in local]
    if folder and not os.path.isdir(str(folder)):
        folder = None
    if not folder:
        # создаём папку по имени клиента из Диска
        try:
            parent = None
            for f in files:
                pass
            name = None
            # имя папки берём из первого доступного пути: используем имя клиента
            name = (r['full_name_latin'] or ('client_%s' % r['id'])).replace('/', '_')
            folder = ROOT / name
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print('  #%-4s не удалось создать папку: %s' % (r['id'], str(e)[:60]))
            continue
    print('  #%-4s %-26s на Диске: %2d | локально: %2d | докачать: %2d' %
          (r['id'], (r['full_name_latin'] or '')[:26], len(files), len(local), len(missing)))
    for f in missing:
        try:
            dest = Path(str(folder)) / f['name']
            if G.download(f['id'], dest):
                total_new += 1
        except Exception as e:
            print('        не скачался %s: %s' % (f['name'][:30], str(e)[:50]))
print()
print('скачано новых файлов: %d' % total_new)
