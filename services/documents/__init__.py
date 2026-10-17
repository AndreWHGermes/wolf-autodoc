"""
Единая точка входа для работы с документами заявки.

Тонкий фасад над:
- core.db.application_documents / application_doc_set / application_doc_summary /
  application_doc_create / ensure_product_documents
- blocks.dashboard.page.doc_missing_fields

Плюс convenience-функции для типичных операций:
- mark_verified(ad_id)
- mark_rejected(ad_id)
- mark_sent(ad_id)
- mark_filled(ad_id)
- is_ready_to_send(app_id) — все ли документы согласованы для отправки
"""
from typing import List, Dict

from core import db as _core_db  # noqa: F401
from blocks.dashboard.page import doc_missing_fields as _doc_missing_fields  # noqa: F401


def list_(app_id: int) -> List[dict]:
    """Все документы заявки с JOIN на templates."""
    return _core_db.application_documents(app_id)


def summary(app_id: int) -> dict:
    """Сводка по статусам: pending/filled/verified/sent/error/total."""
    return _core_db.application_doc_summary(app_id)


def create(app_id: int, template_id: int) -> int:
    """Создать документ заявки (если ещё нет). Возвращает id."""
    return _core_db.application_doc_create(app_id, template_id)


def ensure_for_product(app_id: int) -> List[str]:
    """Достроить документы заявки по составу продукта. Возвращает коды добавленных."""
    return _core_db.ensure_product_documents(app_id)


def missing_fields(app_id: int, template_id: int) -> List[str]:
    """Список незаполненных полей документа (для блокировки отправки)."""
    return _doc_missing_fields(app_id, template_id)


def all_missing(app_id: int) -> List[Dict[str, str]]:
    """Список всех незаполненных полей по заявке: [{template_id, missing}, ...]."""
    out = []
    for d in list_(app_id):
        if (d.get("status") or "") not in ("verified", "sent", "rejected"):
            miss = missing_fields(app_id, d["template_id"])
            if miss:
                out.append({"template_id": d["template_id"], "code": d.get("code", ""),
                            "missing": miss})
    return out


def mark_filled(ad_id: int) -> None:
    """Пометить документ заполненным (но не проверенным)."""
    _core_db.application_doc_set(ad_id, "filled")


def mark_verified(ad_id: int) -> None:
    """Пометить документ проверенным (после визуальной сверки админом)."""
    _core_db.application_doc_set(ad_id, "verified")


def mark_rejected(ad_id: int, reason: str = "") -> None:
    """Пометить документ отклонённым (не нужен в пакете)."""
    _core_db.application_doc_set(ad_id, "rejected", error=reason)


def mark_sent(ad_id: int) -> None:
    """Пометить документ отправленным (только после успешной загрузки на Диск)."""
    _core_db.application_doc_set(ad_id, "sent")


def set_values(ad_id: int, values_json: str, status: str = "filled") -> None:
    """Записать значения и пометить документ заполненным."""
    _core_db.application_doc_set(ad_id, status, values_json=values_json)


def is_ready_to_send(app_id: int) -> bool:
    """Готова ли заявка к отправке: все документы проверены И нет незаполненных полей."""
    s = summary(app_id)
    total = s.get("total", 0)
    if total == 0:
        return False
    decided = s.get("verified", 0) + s.get("sent", 0) + s.get("rejected", 0)
    if decided < total:
        return False
    # у непроверенных не должно быть незаполненных полей
    miss = all_missing(app_id)
    return len(miss) == 0


__all__ = [
    "list_", "summary", "create", "ensure_for_product", "missing_fields", "all_missing",
    "mark_filled", "mark_verified", "mark_rejected", "mark_sent", "set_values",
    "is_ready_to_send",
]