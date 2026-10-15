"""Убрать задвоение файлов клиента в кэше Диска.

Раньше качалка клала рядом копию с расширением, и в заявке документ показывался
дважды. Теперь документ хранится один — с расширением. Скрипт чинит уже
скачанное: ссылки в базе переводит на файл с расширением, файл без расширения
удаляет. Без --apply — только показывает план.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
CACHE = ROOT / "data" / "gdrive_cache"
DB = ROOT / "data" / "wolf.db"
APPLY = "--apply" in sys.argv
EXT = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".doc", ".rtf",
       ".txt", ".zip", ".xlsx", ".svg", ".gif", ".bmp", ".tif", ".tiff", ".heic")

pairs = []
for f in sorted(CACHE.glob("client_*/*")):
    if not f.is_file() or f.suffix.lower() in EXT:
        continue
    twin = next((f.with_suffix(e) for e in EXT if f.with_suffix(e).exists()), None)
    if twin and twin.stat().st_size == f.stat().st_size:
        pairs.append((f, twin))

print("пар «файл без расширения + копия»: %d" % len(pairs))
for f, t in pairs:
    print("  %s  →  %s" % (f.name, t.name))

c = sqlite3.connect(DB, timeout=120)
c.row_factory = sqlite3.Row
fixed, drops, failed = 0, 0, 0
for f, t in pairs:
    rows = [dict(r) for r in c.execute("SELECT id, path FROM client_documents WHERE path LIKE ?",
                                       ("%" + f.name,))]
    if APPLY:
        for r in rows:
            c.execute("UPDATE client_documents SET path=? WHERE id=?",
                      (str(t), r["id"]))
        if rows:
            fixed += len(rows)
        try:
            f.unlink()
            drops += 1
        except Exception as exc:                                   # noqa: BLE001
            failed += 1
            print("  не удалилось: %s (%s)" % (f.name, str(exc)[:60]))

if APPLY:
    c.commit()
    print("ссылок в базе переведено на файл с расширением: %d" % fixed)
    print("файлов-двойников удалено: %d, ошибок: %d" % (drops, failed))
else:
    print("(пробный прогон — повторите с --apply)")
c.close()
