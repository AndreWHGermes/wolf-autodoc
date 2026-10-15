"""Пользователи админки и менеджеры бота."""
from core import db


def by_telegram_id(tg_id: int):
    """Пользователь по telegram id (запрос дублировался в core/auth.py)."""
    return db.q1("SELECT * FROM users WHERE telegram_id=?", (str(tg_id),))


def managers():
    return db.q("SELECT * FROM bot_managers WHERE is_active=1 ORDER BY id")
