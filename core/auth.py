"""Ядро: вход, сессии, роли.

Источник истины для пользователей сайта — bot_managers (Telegram).
Старая запись admin/123 в users остаётся как аварийный вход.
"""
from __future__ import annotations

from functools import wraps
from datetime import datetime, timedelta

from flask import redirect, request, session, url_for

from core import db
from repositories import users as users_repo


def _user_row(uid: int):
    """Получает пользователя Wolf c присоединением данных из bot_managers."""
    return db.q1(
        """SELECT u.id, u.login, u.name, u.role, u.active, u.telegram_id,
                  bm.full_name AS bm_full_name, bm.username AS bm_username,
                  bm.role AS bm_role
             FROM users u
             LEFT JOIN bot_managers bm ON bm.telegram_id=u.telegram_id
            WHERE u.id=? AND u.active=1""",
        (uid,))


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    row = _user_row(uid)
    if not row:
        return None
    # Если есть Telegram-привязка — реальное имя и роль оттуда.
    if row["telegram_id"]:
        row["name"] = row["bm_full_name"] or row["name"]
        if row["bm_role"] in ("admin", "both"):
            row["role"] = "admin"
        elif row["bm_role"] == "manager":
            row["role"] = "manager"
    return row


def login_user(user) -> None:
    """Логин по логину/паролю (аварийный путь)."""
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"] or user["login"]
    session["user_role"] = user["role"]
    session["role"] = user["role"]
    session.permanent = True


def login_via_telegram(telegram_id: str, full_name: str = "", username: str = "") -> bool:
    """Логин по Telegram: находит/создаёт users, пишет в сессию."""
    if not telegram_id:
        return False
    bm = db.q1(
        "SELECT * FROM bot_managers WHERE telegram_id=?",
        (telegram_id,))
    if not bm or bm["role"] not in ("admin", "both"):
        return False
    # Реальное имя и username берём из bot_managers
    real_name = full_name or bm["full_name"] or ""
    real_username = username or bm["username"] or ""
    user = users_repo.by_telegram_id(telegram_id,)
    if not user:
        login_name = f"tg_{telegram_id}"
        db.exec_sql(
            "INSERT INTO users (login, name, role, active, telegram_id, created_at) "
            "VALUES (?,?,?,?,?,datetime('now'))",
            (login_name, real_name or login_name, "admin", 1, telegram_id))
        user = users_repo.by_telegram_id(telegram_id,)
    else:
        # обновляем имя если оно есть в bot_managers
        if real_name and real_name != user["name"]:
            db.exec_sql("UPDATE users SET name=? WHERE id=?",
                        (real_name, user["id"]))
        db.exec_sql("UPDATE users SET active=1 WHERE id=?", (user["id"],))
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = real_name or user["name"] or user["login"]
    session["user_role"] = "admin"
    session["role"] = "admin"
    session["telegram_id"] = telegram_id
    session["telegram_username"] = real_username
    session.permanent = True
    db.log_event("user", user["id"], "login_telegram", actor=str(telegram_id))
    return True


def create_login_code(telegram_id: str, ttl_seconds: int = 120) -> str:
    """Генерирует одноразовый код входа для telegram_id. Действует ttl секунд."""
    import secrets
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now()
    expires = now + timedelta(seconds=ttl_seconds)
    db.exec_sql(
        "INSERT INTO login_codes (code, telegram_id, created_at, expires_at) "
        "VALUES (?,?,?,?)",
        (code, telegram_id, now.isoformat(timespec="seconds"),
         expires.isoformat(timespec="seconds")))
    return code


def consume_login_code(code: str) -> str | None:
    """Возвращает telegram_id если код валидный, иначе None."""
    row = db.q1(
        "SELECT * FROM login_codes WHERE code=?",
        (code.strip(),))
    if not row:
        return None
    if row["used_at"]:
        return None
    if datetime.now() > datetime.fromisoformat(row["expires_at"]):
        return None
    db.exec_sql(
        "UPDATE login_codes SET used_at=datetime('now') WHERE code=?",
        (code,))
    return row["telegram_id"]


def request_login_code(telegram_id: str) -> str:
    """Публичный метод: вызывается из бота, шлёт код пользователю."""
    code = create_login_code(telegram_id, ttl_seconds=180)
    # Шлём напрямую через notify
    try:
        from bot.notify import send
        send(telegram_id,
             f"🔑 Код входа на Wolf AutoDoc: {code}\n"
             f"Действует 3 минуты.\n"
             f"Откройте сайт и введите этот код.")
    except Exception:
        pass
    return code


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login.page", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login.page", next=request.path))
        if user["role"] != "admin":
            return "Доступ только для администратора", 403
        return view(*args, **kwargs)
    return wrapper
