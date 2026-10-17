"""Способ формирования переменной — для цветовой идентификации в конструкторе.

Цвета (правило заказчика 06.10.2026):
  • зелёный  — значение реально взято из документа клиента (паспорт, справка банка, KITAS, резюме);
  • оранжевый — собрано логически (карточка заявки, справочник, правило продукта, расчёт, связь);
  • красный  — подставлено случайно по правилам (суммы и их суммы прописью).
"""
import sqlite3
from pathlib import Path

DB = Path('/opt/wolf_v2/data/wolf.db')

CLIENT_METHODS = {'client_doc', 'doc', 'client_document', 'from_client_doc'}
RANDOM_METHODS = {'random', 'rand', 'random_bounds', 'random_range'}


def src_kind(method: str) -> str:
    m = (method or '').strip().lower()
    if m in CLIENT_METHODS:
        return 'client'
    if m in RANDOM_METHODS or m.startswith('random'):
        return 'random'
    return 'logic'


def src_ru(kind: str) -> str:
    return {'client': 'из документа клиента', 'random': 'подставлено случайно по правилам',
            'logic': 'собрано логически'}.get(kind, 'собрано логически')


def methods_for_template(template_id) -> dict:
    """{имя переменной: способ формирования} для шаблона."""
    out = {}
    try:
        con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
        con.row_factory = sqlite3.Row
        for r in con.execute('SELECT name, method FROM template_variables WHERE template_id=?',
                             (template_id,)):
            out[r['name']] = r['method'] or ''
        con.close()
    except Exception:  # noqa: BLE001
        return out
    return out


def legend() -> list:
    """Легенда цветов для панели конструктора."""
    return [
        ('client', 'зелёный', 'значение реально взято из документа клиента'),
        ('logic', 'оранжевый', 'значение собрано логически (карточка, справочник, правило продукта, расчёт)'),
        ('random', 'красный', 'значение подставлено случайно по правилам (суммы)'),
    ]
