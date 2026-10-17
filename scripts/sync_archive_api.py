"""Выкачка архивных папок через Drive API (робот) — вместо анонимной качалки.

Запуск (после того как папки расшарены на адрес робота):
    /usr/bin/python3 scripts/sync_archive_api.py            # все клиенты со ссылкой
    /usr/bin/python3 scripts/sync_archive_api.py 5          # только первые 5 (проверка)

Скачивает папку каждого клиента в data/gdrive_cache/client_<id> — туда же, куда
складывал разбор, поэтому дальше документы заводятся и переменные собираются
той же системой, что и раньше. Роботу дано право только на чтение.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from services import gdrive_api as api   # noqa: E402

DB = '/opt/wolf_v2/data/wolf.db'
CACHE = Path('/opt/wolf_v2/data/gdrive_cache')

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0

if not api.available():
    print('доступ через робота не настроен: нет ключа google_service_account.json')
    sys.exit(1)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, COALESCE(full_name_latin, 'клиент ' || id) AS name, "
                    "gdrive_folder_url AS url FROM clients "
                    "WHERE COALESCE(gdrive_folder_url, '') <> '' ORDER BY id").fetchall()
if limit:
    rows = rows[:limit]

print(f'папок к выкачке: {len(rows)}')
total_files = total_ok = 0
for r in rows:
    dest = CACHE / f"client_{r['id']}"
    try:
        got = api.sync_folder(r['url'], dest)
    except Exception as e:  # noqa: BLE001
        print(f"  {r['id']:>3} {r['name'][:28]:<28} ошибка: {str(e)[:70]}")
        continue
    total_files += got
    total_ok += 1 if got else 0
    print(f"  {r['id']:>3} {r['name'][:28]:<28} файлов: {got}")

print(f'итог: папок с файлами {total_ok} из {len(rows)}, скачано файлов {total_files}')
print('дальше: разбор заявок подтянет значения и миниатюры — scripts/drive_scan.py <id заявки>')
