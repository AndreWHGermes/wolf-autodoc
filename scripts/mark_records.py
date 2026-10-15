#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пометки записей: архивные / тестовые / рабочие.

Зачем: пока система обкатывается, в базе лежат архив (перенесённые тестовые данные)
и тестовые прогоны. Их нужно отличать от рабочих записей, чтобы потом одной командой
убрать и включить нормальный режим.

  applications.record_kind и clients.record_kind: 'archive' | 'test' | NULL (рабочая)
  settings.record_mode: 'test' — всё новое помечается тестовым; '' — рабочий режим

Запуск:
  python3 scripts/mark_records.py status      # что сейчас в базе
  python3 scripts/mark_records.py archive     # привести архив в порядок и пометить
  python3 scripts/mark_records.py mode test   # включить тестовый режим для новых записей
  python3 scripts/mark_records.py mode prod   # рабочий режим (без пометок)
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "wolf.db"
ARCHIVE_STATUSES = {"completed"}          # статус из прежней системы
OUR_STATUS = "closed"                     # как это называется у нас (архив = закрыта)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns(conn: sqlite3.Connection) -> None:
    for table in ("applications", "clients"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        if "record_kind" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN record_kind TEXT")
            print(f"   + {table}.record_kind")
    conn.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.commit()


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?,?,datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value))
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return (row["value"] if row and row["value"] is not None else default)


def price_from_product(conn: sqlite3.Connection, product_id) -> int:
    if not product_id:
        return 0
    row = conn.execute("SELECT description FROM products WHERE id=?", (product_id,)).fetchone()
    if not row or not row["description"]:
        return 0
    m = re.search(r"price_idr\s*=\s*(\d+)", row["description"])
    return int(m.group(1)) if m else 0


def cmd_status(conn: sqlite3.Connection) -> None:
    print("режим новых записей:", get_setting(conn, "record_mode", "") or "рабочий (без пометок)")
    for table in ("applications", "clients"):
        print(f"— {table}:")
        for r in conn.execute(f"SELECT COALESCE(record_kind,'(рабочая)') k, COUNT(*) n "
                              f"FROM {table} GROUP BY COALESCE(record_kind,'(рабочая)')"):
            print(f"     {r['k']:<12} {r['n']}")
    print("— статусы заявок:")
    for r in conn.execute("SELECT status, COUNT(*) n FROM applications GROUP BY status"):
        print(f"     {r['status']:<12} {r['n']}")


def cmd_archive(conn: sqlite3.Connection) -> None:
    """Приводим архив к нашей схеме и помечаем его."""
    ensure_columns(conn)
    # 1) статус прежней системы -> наш
    n = conn.execute("UPDATE applications SET status=? WHERE status IN (%s)"
                     % ",".join("?" * len(ARCHIVE_STATUSES)),
                     (OUR_STATUS, *ARCHIVE_STATUSES)).rowcount
    print(f"   статус {sorted(ARCHIVE_STATUSES)} -> '{OUR_STATUS}': {n} заявок")

    # 2) заполняем недостающее, чтобы архив был сопоставим с рабочими записями
    fixed_price = fixed_drive = 0
    for a in conn.execute("SELECT id, product_id, price_idr, gdrive_url, client_id FROM applications"):
        price = a["price_idr"] or 0
        if not price:
            price = price_from_product(conn, a["product_id"])
            if price:
                conn.execute("UPDATE applications SET price_idr=? WHERE id=?", (price, a["id"]))
                fixed_price += 1
        if not (a["gdrive_url"] or "").strip():
            cl = conn.execute("SELECT gdrive_folder_url FROM clients WHERE id=?", (a["client_id"],)).fetchone()
            url = (cl["gdrive_folder_url"] if cl else "") or ""
            if url.strip():
                conn.execute("UPDATE applications SET gdrive_url=? WHERE id=?", (url, a["id"]))
                fixed_drive += 1
    print(f"   сумма из продукта подставлена: {fixed_price} | ссылка на Drive из карточки клиента: {fixed_drive}")

    # 3) сами пометки
    conn.execute("UPDATE applications SET record_kind='archive'")
    conn.execute("UPDATE clients SET record_kind='archive' WHERE id IN (SELECT DISTINCT client_id FROM applications)")
    conn.commit()
    print("   помечено архивом: заявок", conn.execute(
        "SELECT COUNT(*) FROM applications WHERE record_kind='archive'").fetchone()[0],
        "| клиентов", conn.execute("SELECT COUNT(*) FROM clients WHERE record_kind='archive'").fetchone()[0])


def cmd_mode(conn: sqlite3.Connection, mode: str) -> None:
    ensure_columns(conn)
    value = "" if mode in ("prod", "off", "") else mode
    set_setting(conn, "record_mode", value)
    print("режим новых записей:", value or "рабочий (без пометок)")


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    conn = connect()
    ensure_columns(conn)
    if cmd == "status":
        cmd_status(conn)
    elif cmd == "archive":
        cmd_archive(conn)
    elif cmd == "mode":
        cmd_mode(conn, args[1] if len(args) > 1 else "test")
    else:
        print(__doc__)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
