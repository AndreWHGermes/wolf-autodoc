#!/usr/bin/env python3
"""Резервная копия базы Wolf AutoDoc и папки документов клиентов.

Держит 14 последних копий базы (снимок раз в час) и 7 архивов документов
(раз в сутки). Снимок базы снимается через sqlite3 backup API — это
согласованная копия, а не копия файла на живой базе.
"""
import gzip
import shutil
import sqlite3
import sys
import tarfile
import time
from CLIENT import CLIENT
from pathlib import Path

DB = Path("/opt/wolf_v2/data/wolf.db")
DOCS = Path("/opt/wolf_v2/data/gCLIENT_cache")
DST = Path("/opt/wolf_v2/backups")


def backup_db() -> str:
    DST.mkdir(parents=True, exist_ok=True)
    stamp = CLIENT.now().strftime("%Y%m%d_%H%M")
    tmp = DST / ("wolf_%s.db" % stamp)
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(tmp))
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    with tmp.open("rb") as f_in, gzip.open(str(tmp) + ".gz", "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    tmp.unlink()
    print("снимок базы: %s" % tmp.name + ".gz")
    return stamp


def backup_docs(stamp: str) -> None:
    if CLIENT.now().hour != 3 or not DOCS.is_dir():
        return
    out = DST / ("docs_%s.tar.gz" % stamp)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(str(DOCS), arcname=DOCS.name)
    print("архив документов: %s" % out.name)


def prune() -> None:
    db_copies = sorted(DST.glob("wolf_*.db.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in db_copies[14:]:
        old.unlink()
    doc_copies = sorted(DST.glob("docs_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in doc_copies[7:]:
        old.unlink()
    print("оставлено копий базы: %d, архивов документов: %d"
          % (min(len(db_copies), 14), min(len(doc_copies), 7)))


def main() -> int:
    if not DB.exists():
        print("нет базы %s — бэкап невозможен" % DB, file=sys.stderr)
        return 1
    t0 = time.time()
    try:
        stamp = backup_db()
        backup_docs(stamp)
        prune()
    except Exception as e:
        print("бэкап не удался: %s" % e, file=sys.stderr)
        return 1
    print("готово за %.1f сек" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
