"""Дать расширение файлам клиента, скачанным с Диска без него.

На Диске встречаются «PASSPORT - ANNA KOBLIKOVA» (это PDF) и «FOTO - ...» (JPEG).
Без расширения парсеры не понимают формат. Раньше рядом клали копию — и документ
показывался в заявке дважды. Правильно — переименовать сам файл и поправить
ссылку в базе. Без --apply — только показывает план.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
CACHE = ROOT / "data" / "gdrive_cache"
DB = ROOT / "data" / "wolf.db"
APPLY = "--apply" in sys.argv
EXT = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".doc", ".rtf",
       ".txt", ".zip", ".xlsx", ".svg", ".gif", ".bmp", ".tif", ".tiff", ".heic")

SIG = ((b"%PDF", ".pdf"), (b"\xff\xd8", ".jpg"), (b"\x89PNG", ".png"),
       (b"RIFF", ".webp"), (b"PK", ".docx"))

plan = []
for f in sorted(CACHE.glob("client_*/*")):
    if not f.is_file() or f.suffix.lower() in EXT or f.stat().st_size == 0:
        continue
    if any(f.with_suffix(e).exists() for e in EXT):
        continue                                   # пара есть — это дело dedupe
    with open(f, "rb") as fh:
        head = fh.read(12)
    ext = next((e for sig, e in SIG if head.startswith(sig)), None)
    if ext:
        plan.append((f, f.with_suffix(ext)))

print("файлов без расширения и без копии: %d" % len(plan))
for f, t in plan:
    print("  %-52s → %s" % (f.name[:52], t.suffix))

c = sqlite3.connect(DB, timeout=120)
c.row_factory = sqlite3.Row
done, links = 0, 0
for f, t in plan:
    if APPLY:
        for r in c.execute("SELECT id, path FROM client_documents WHERE path LIKE ?",
                           ("%" + f.name, )):
            c.execute("UPDATE client_documents SET path=? WHERE id=?", (str(t), r["id"]))
            links += 1
        shutil.move(str(f), str(t))
        done += 1
if APPLY:
    c.commit()
    print("переименовано: %d, ссылок в базе поправлено: %d" % (done, links))
else:
    print("(пробный прогон — повторите с --apply)")
c.close()
