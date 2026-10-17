"""
Единая точка входа для работы с карточкой клиента.

Тонкий фасад над:
- core.db.client_get / client_label / client_create / client_set
- repositories.clients (если используется)

Карточка клиента — постоянная сущность: даже если заявка идёт в цикле,
клиент один. Документы могут пересобираться, проверки могут крутиться —
а клиент остаётся.
"""
from typing import Optional, Dict, Any
from core import db as _core_db  # noqa: F401


def get(client_id: int) -> Optional[Dict[str, Any]]:
    """Получить карточку клиента по id или None."""
    return _core_db.client_get(client_id)


def label(row_or_id) -> str:
    """Человекочитаемое имя клиента для отображения в UI."""
    if isinstance(row_or_id, (int, str)):
        row = get(int(row_or_id)) or {}
    else:
        row = row_or_id or {}
    return _core_db.client_label(row)


def drive_folder_url(client_id: int) -> str:
    """Ссылка на папку клиента на Google Диске (если указана)."""
    c = get(client_id)
    if not c:
        return ""
    return (c.get("gdrive_folder_url") or "").strip()


def gdrive_id(client_id: int) -> str:
    """ID папки клиента на Google Диске (если указана)."""
    c = get(client_id)
    if not c:
        return ""
    return (c.get("gdrive_folder_id") or "").strip()


def bank(client_id: int) -> str:
    """Банк клиента ('tbank' или 'sber' или '')."""
    c = get(client_id)
    if not c:
        return ""
    return (c.get("bank_name") or "").strip().lower()


def full_name_latin(client_id: int) -> str:
    """ФИО клиента латиницей (для документов, уходящих в Индонезию)."""
    c = get(client_id)
    if not c:
        return ""
    return (c.get("full_name_latin") or "").strip()


def passport_expiry(client_id: int) -> str:
    """Срок действия паспорта в формате YYYY-MM-DD или ''."""
    c = get(client_id)
    if not c:
        return ""
    return (c.get("passport_expiry") or "").strip()


def set_field(client_id: int, field: str, value: Any) -> None:
    """Обновить одно поле карточки клиента. Запись идёт через core.db.

    Используется редко — основная работа с клиентом идёт через
    forms (поля редактируются человеком).
    """
    try:
        _core_db.exec_sql(
            f"UPDATE clients SET {field}=? WHERE id=?",
            (value, client_id),
        )
    except Exception:
        pass


__all__ = [
    "get", "label", "drive_folder_url", "gdrive_id", "bank",
    "full_name_latin", "passport_expiry", "set_field",
]