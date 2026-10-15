"""Доступ к клиентам."""
from core import db


def get(client_id: int):
    return db.q1("SELECT * FROM clients WHERE id=?", (client_id,))


def photo_path(client_id: int):
    """Путь к фото клиента (запрос дублировался в app.py)."""
    return db.q1("SELECT photo_path FROM clients WHERE id=?", (client_id,))


def by_telegram(tg_id: int):
    return db.q1("SELECT * FROM clients WHERE telegram_id=?", (tg_id,))


def list_latest(limit: int = 50):
    return db.q("SELECT * FROM clients ORDER BY id DESC LIMIT ?", (limit,))
