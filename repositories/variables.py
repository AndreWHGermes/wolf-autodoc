"""Доступ к переменным шаблонов: значения, реестр, пул, классификация."""
from core import db


def names(template_id: int):
    """Имена переменных шаблона (запрос дублировался в 5 местах)."""
    return db.q("SELECT name FROM template_variables WHERE template_id=?", (template_id,))


def set_rule_note(template_id: int, name: str, note: str):
    db.exec_sql("UPDATE template_variables SET rule_note=? WHERE template_id=? AND name=?",
                (note, template_id, name))


def scope(name: str) -> str:
    """individual — данные клиента, common — типовое значение документа."""
    row = db.q1("SELECT scope FROM variable_scope WHERE name=?", (name,))
    return (row["scope"] if row else "common")


def pool(variable_name: str, limit: int = 15):
    """Значения, которыми поле заполняли раньше (память архива)."""
    return db.q("""SELECT value, used_count FROM variable_value_history
                   WHERE variable_name=? AND value != ''
                   ORDER BY used_count DESC LIMIT ?""", (variable_name, limit))


def pool_add(variable_name: str, value: str):
    row = db.q1("SELECT id FROM variable_value_history WHERE variable_name=? AND value=?",
                (variable_name, value))
    if row:
        db.exec_sql("UPDATE variable_value_history SET used_count=used_count+1, "
                    "last_used=datetime('now') WHERE id=?", (row["id"],))
    else:
        db.exec_sql("INSERT INTO variable_value_history(variable_name, value, used_count, last_used) "
                    "VALUES(?,?,1,datetime('now'))", (variable_name, value))
