"""Реестр ошибок Wolf AutoDoc: нумерованный журнал проблем по заявкам.

Каждая запись: дата, номер заявки, этап, текст ошибки, статус (open/fixed/wontfix),
комментарий агента и комментарий заказчика. Одинаковые ошибки не дублируются:
у записи есть repeat_key, при повторе растёт счётчик и обновляется дата.
"""
from __future__ import annotations

import hashlib
import json
import re

from core import db

DDL = """
CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now')),
    application_id INTEGER,
    stage TEXT,
    source TEXT,
    text TEXT,
    repeat_key TEXT,
    repeats INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'open',
    agent_note TEXT,
    user_comment TEXT,
    fixed_at TEXT
)
"""


def _key(text: str) -> str:
    norm = re.sub(r"\d+", "N", str(text or ""))[:200]
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def ensure() -> None:
    db.exec_sql(DDL)


def log(application_id: int, stage: str, errors, source: str = "прогон") -> int:
    """Записать ошибки прогона. Возвращает число новых записей."""
    if not errors:
        return 0
    ensure()
    if isinstance(errors, str):
        try:
            errors = json.loads(errors)
        except Exception:                                          # noqa: BLE001
            errors = [errors]
    added = 0
    for e in errors or []:
        text = str(e or "").strip()
        if not text:
            continue
        key = _key(text)
        row = db.q1("SELECT id, status FROM error_log WHERE repeat_key=? ORDER BY id DESC LIMIT 1", (key,))
        if row:
            db.exec_sql("UPDATE error_log SET repeats=repeats+1, last_seen=datetime('now'), "
                        "application_id=?, stage=? WHERE id=?",
                        (application_id, stage, row["id"]))
            # закрытая ранее ошибка, которая повторилась, снова открыта — это регресс
            if (row.get("status") or "open") == "fixed":
                db.exec_sql("UPDATE error_log SET status='open', fixed_at=NULL WHERE id=?", (row["id"],))
        else:
            db.exec_sql("INSERT INTO error_log (application_id, stage, source, text, repeat_key) "
                        "VALUES (?,?,?,?,?)", (application_id, stage, source, text[:2000], key))
            added += 1
    return added


def entries(status: str = "") -> list[dict]:
    ensure()
    if status in ("open", "fixed", "wontfix"):
        return db.q("SELECT * FROM error_log WHERE status=? ORDER BY last_seen DESC, id DESC", (status,))
    return db.q("SELECT * FROM error_log ORDER BY (status='open') DESC, last_seen DESC, id DESC")


def set_status(entry_id: int, status: str, note: str = "") -> None:
    ensure()
    if status not in ("open", "fixed", "wontfix"):
        return
    db.exec_sql("UPDATE error_log SET status=?, agent_note=COALESCE(NULLIF(?,''), agent_note), "
                "fixed_at=CASE WHEN ?='fixed' THEN datetime('now') ELSE NULL END WHERE id=?",
                (status, note, status, entry_id))


def set_comment(entry_id: int, comment: str) -> None:
    ensure()
    db.exec_sql("UPDATE error_log SET user_comment=? WHERE id=?", (comment, entry_id))


def stats() -> dict:
    ensure()
    rows = db.q("SELECT status, COUNT(*) AS n FROM error_log GROUP BY status")
    out = {"open": 0, "fixed": 0, "wontfix": 0}
    for r in rows:
        out[r["status"]] = r["n"]
    out["total"] = sum(out.values())
    return out
