"""Очистка исходников клиентов: значения остаются, файлы с Диска не копим.

Логика системы: у себя мы держим то, чем работаем —
  • значения переменных (в базе, values_json заявок и история значений);
  • наши готовые бланки (PDF);
  • карточки клиентов и миниатюры.
Исходные документы клиента (паспорта, справки) нужны только на время разбора:
из них вытаскиваются значения. После этого их можно не хранить — при
необходимости система забирает папку с Google Диска снова за секунды.

Запуск:
    /usr/bin/python3 scripts/clean_cache.py            # старше 30 дней
    /usr/bin/python3 scripts/clean_cache.py 14         # старше 14 дней
    /usr/bin/python3 scripts/clean_cache.py 30 dry     # только показать, что удалится
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

CACHE = Path('/opt/wolf_v2/data/gdrive_cache')
DB = '/opt/wolf_v2/data/wolf.db'

days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
dry = 'dry' in [a.lower() for a in sys.argv[2:]]

conn = sqlite3.connect(DB)
# заявки, по которым значения уже вытащены: их исходники точно не нужны
ready = {r[0] for r in conn.execute(
    "SELECT DISTINCT application_id FROM application_documents "
    "WHERE COALESCE(values_json, '') <> '' AND values_json <> '{}'")}
client_of = dict(conn.execute("SELECT id, client_id FROM applications"))

cutoff = time.time() - days * 86400
removed = skipped = 0
size = 0

for folder in sorted(CACHE.glob('client_*')):
    try:
        cid = int(folder.name.split('_')[1])
    except Exception:
        continue
    newest = max([f.stat().st_mtime for f in folder.rglob('*') if f.is_file()] or [0])
    has_ready = any(client_of.get(a) == cid for a in ready)
    old_enough = newest and newest < cutoff
    if not (has_ready and old_enough):
        skipped += 1
        continue
    weight = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
    size += weight
    if dry:
        print(f'  удалили бы client_{cid}: {weight // 1024} КБ')
    else:
        shutil.rmtree(folder, ignore_errors=True)
    removed += 1

print(f'{"проверка" if dry else "очистка"} (старше {days} дней): '
      f'{"к удалению" if dry else "удалено"} {removed}, оставлено {skipped}, '
      f'освободилось бы {size // 1024 // 1024} МБ')
print('значения переменных и готовые бланки не затрагиваются — они хранятся в базе и renders')
