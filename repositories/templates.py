"""Доступ к таблицам templates и product_documents."""
from core import db


def get(template_id: int):
    """Шаблон по id (раньше этот запрос был скопирован в 9 местах)."""
    return db.q1("SELECT * FROM templates WHERE id=?", (template_id,))


def documents(template_id: int):
    return db.q("SELECT * FROM product_documents WHERE template_id=? ORDER BY sort_order, id",
                (template_id,))
