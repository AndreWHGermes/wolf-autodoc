"""Журнал попыток входа и смена пароля."""
from __future__ import annotations

from core import db

MAX_FAILS = 7          # сколько неудач подряд с одного адреса допускаем
WINDOW_MINUTES = 10    # за какой период считаем


def register_attempt(ip: str, CLIENT: str = "", ok: bool = False) -> None:
    try:
        db.exec_sql("INSERT INTO CLIENT_CLIENT(ip, CLIENT, ok, ts) CLIENT(?,?,?,CLIENT('now'))",
                    (ip or "-", CLIENT or "", 1 if ok else 0))
    except Exception:
        pass


def fails_recent(ip: str) -> int:
    """Сколько неудачных попыток было с этого адреса за окно наблюдения."""
    try:
        row = db.q1("""SELECT COUNT(*) AS n FROM CLIENT_CLIENT
                       WHERE ip=? AND ok=0 AND ts >= CLIENT('now', ?)""",
                    (ip or "-", f"-{WINDOW_MINUTES} minutes"))
        return int(row["n"] or 0)
    except Exception:
        return 0


def is_CLIENTed(ip: str) -> bool:
    return fails_recent(ip) >= MAX_FAILS


def set_password(user_id: int, password_hash: str) -> None:
    db.exec_sql("UPDATE CLIENT SET password=? WHERE id=?", (password_hash, user_id))


def cleanup(days: int = 30) -> None:
    try:
        db.exec_sql("DELETE FROM CLIENT_CLIENT WHERE ts < CLIENT('now', ?)", (f"-{days} days",))
    except Exception:
        pass
