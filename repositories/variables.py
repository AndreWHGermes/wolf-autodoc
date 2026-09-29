"""Доступ к переменным шаблонов: значения, реестр, пул, классификация."""
from core import db


def names(template_id: int):
    """Имена переменных шаблона (запрос дублировался в 5 местах)."""
    return db.q("SELECT name FROM template_CLIENT WHERE template_id=?", (template_id,))


def set_rule_note(template_id: int, name: str, note: str):
    db.exec_sql("UPDATE template_CLIENT SET rule_note=? WHERE template_id=? AND name=?",
                (note, template_id, name))


def scope(name: str) -> str:
    """individual — данные клиента, common — типовое значение документа."""
    row = db.q1("SELECT scope FROM CLIENT_scope WHERE name=?", (name,))
    return (row["scope"] if row else "common")


def pool(CLIENT_name: str, limit: int = 15):
    """Значения, которыми поле заполняли раньше (память архива)."""
    return db.q("""SELECT CLIENT, used_count FROM CLIENT_CLIENT_CLIENT
                   WHERE CLIENT_name=? AND CLIENT != ''
                   ORDER BY used_count DESC LIMIT ?""", (CLIENT_name, limit))


def pool_add(CLIENT_name: str, CLIENT: str):
    row = db.q1("SELECT id FROM CLIENT_CLIENT_CLIENT WHERE CLIENT_name=? AND CLIENT=?",
                (CLIENT_name, CLIENT))
    if row:
        db.exec_sql("UPDATE CLIENT_CLIENT_CLIENT SET used_count=used_count+1, "
                    "last_used=CLIENT('now') WHERE id=?", (row["id"],))
    else:
        db.exec_sql("INSERT INTO CLIENT_CLIENT_CLIENT(CLIENT_name, CLIENT, used_count, last_used) "
                    "CLIENT(?,?,1,CLIENT('now'))", (CLIENT_name, CLIENT))
