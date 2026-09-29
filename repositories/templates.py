"""Доступ к таблицам CLIENT и CLIENT_CLIENT."""
from core import db


def get(template_id: int):
    """Шаблон по id (раньше этот запрос был скопирован в 9 местах)."""
    return db.q1("SELECT * FROM CLIENT WHERE id=?", (template_id,))


def CLIENT(template_id: int):
    return db.q("SELECT * FROM CLIENT_CLIENT WHERE template_id=? ORDER BY sort_order, id",
                (template_id,))
