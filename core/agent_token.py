"""Токен агента (только просмотр) для Wolf AutoDoc.

Зачем: агент BiMax должен сам открывать конструктор и документы в браузере, чтобы
сверять собранные документы с оригиналом. Пароль в чат не передаётся.

Как устроено:
- Токен — случайная строка 40+ символов. Хранится на сервере в файле
  /root/.hermes/secrets/wolf_agent_token (права 600). В базе — только SHA-256 хэш.
- Вход: GET /agent-login?token=... — ставит сессию с ролью viewer (только чтение).
- Роль viewer: GET-запросы разрешены; POST/PUT/DELETE — 403.
- Журнал входов: таблица agent_token_log (время, IP, путь). Отзыв — удаление файла + флаг.
- Токен можно пересоздать: новый файл, старый хэш перестаёт работать.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from flask import request, session, redirect, abort

from core import db

TOKEN_FILE = Path("/root/.hermes/secrets/wolf_agent_token")
HASH_KEY = "agent_token_sha256"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf8")).hexdigest()


def ensure_table() -> None:
    db.exec_sql(
        "CREATE TABLE IF NOT EXISTS agent_token_log ("
        " id INTEGER PRIMARY KEY, at TEXT DEFAULT (datetime('now')),"
        " ip TEXT, path TEXT, ok INTEGER)"
    )
    db.exec_sql(
        "CREATE TABLE IF NOT EXISTS agent_token (k TEXT PRIMARY KEY, v TEXT, created_at TEXT DEFAULT (datetime('now')))"
    )


def issue_token() -> str:
    """Создаёт новый токен, записывает хэш в базу, сам токен — в файл на сервере."""
    ensure_table()
    tok = secrets.token_urlsafe(32)
    db.exec_sql("INSERT OR REPLACE INTO agent_token (k, v) VALUES (?,?)", (HASH_KEY, _sha(tok)))
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(tok)
    os.chmod(TOKEN_FILE, 0o600)
    return tok


def revoke() -> None:
    ensure_table()
    db.exec_sql("DELETE FROM agent_token WHERE k=?", (HASH_KEY,))
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def check(tok: str) -> bool:
    ensure_table()
    row = db.q1("SELECT v FROM agent_token WHERE k=?", (HASH_KEY,))
    if not row or not tok:
        return False
    return hmac.compare_digest(row["v"], _sha(tok))


def log(ok: bool) -> None:
    try:
        db.exec_sql("INSERT INTO agent_token_log (ip, path, ok) VALUES (?,?,?)",
                    (request.remote_addr, request.path, 1 if ok else 0))
    except Exception:
        pass


def viewer_session() -> bool:
    """True, если текущая сессия вошла по токену агента (роль viewer)."""
    return session.get("role") == "viewer"


def guard_write() -> None:
    """Для viewer запрещаем любые записи."""
    if viewer_session() and request.method not in ("GET", "HEAD", "OPTIONS"):
        abort(403)
