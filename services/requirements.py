"""Требования продукта — источник истины для легенды и для цифр в документах.

Принцип заказчика: легенда строится ОТ ТРЕБОВАНИЙ ПРОДУКТА, а не от того, какие
данные случайно удалось распознать у клиента.

  - спрашивает ли иммиграция место работы и доход — только тогда эти поля
    попадают в легенду и в пакет;
  - не спрашивает адрес проживания в Индонезии (например, для части продуктов) —
    значит в легенде его нет и требовать его у клиента нельзя;
  - банковская справка собирается системой под ПРОХОДНЫЕ цифры: реальная справка
    клиента с недостатком средств не подаётся, вместо неё готовится справка
    с суммой, которая проходит регламент.

Отсюда два следствия, которые важно не путать:
  1. `fields`  — что проверяем и показываем клиенту (легенда);
  2. `min_balance_usd` — под какой порог подгоняем сумму в банковской справке.

Файл намеренно без зависимостей от остального проекта: его читают легенда,
подстановка значений и финальная проверка.
"""
from __future__ import annotations

# Курс для пересчёта порога в рубли. Требование выражено в USD
# (imigrasi.go.id: proof of funds minimum USD 2 000), справка — в рублях.
USD_RUB_DEFAULT = 100.0

# ─── требования по продуктам ──────────────────────────────────────────────────
# `fields` — поля легенды, без которых пакет не собирается.
# `optional` — поля, которые в легенду попадают ТОЛЬКО если у клиента они есть,
#              но их отсутствие не дефицит и не блокер.
# `not_needed` — поля, которые для этого продукта не спрашивают: в легенде их
#              быть не должно, чтобы клиент не читал лишнее и не путался.
PRODUCTS = {
    "C1-EXT": {
        "label": "Продление визы C1 (B211A)",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "indonesia.permit_no",
            "indonesia.permit_expiry",
            "finance.balance",
        ],
        "optional": ["identity.citizenship", "indonesia.address", "home.address"],
        "not_needed": ["work.organization", "work.position", "work.annual_amount",
                       "identity.birth_place"],
        "min_balance_usd": 2000,
        "min_statement_months": 3,
        "needs_contract": False,
        "needs_cv": False,
        "needs_e02": False,
        "note": "Виза визита: работа запрещена, договор и резюме не подаются.",
    },
    "C1": {
        "label": "Виза C1 (B211A)",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "finance.balance",
        ],
        "optional": ["identity.citizenship", "indonesia.address"],
        "not_needed": ["work.organization", "work.position", "work.annual_amount"],
        "min_balance_usd": 2000,
        "min_statement_months": 3,
        "needs_contract": False,
        "needs_cv": False,
        "needs_e02": False,
        "note": "Подтверждение средств — выписка за 3 месяца, остаток на счёте от 190 000 до 800 000 руб.",
    },
    "E33G-NEW": {
        "label": "Remote Worker KITAS (E33G), новая подача",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "work.organization",
            "work.position",
            "work.annual_amount",
            "home.address",
        ],
        "optional": ["identity.citizenship"],
        "not_needed": [],
        "min_balance_usd": 2000,
        "min_annual_usd": 60000,
        "needs_contract": True,
        "needs_cv": True,
        "needs_e02": True,
        "note": "Рабочая виза: нужны договор, резюме, подтверждение дохода.",
    },
    "E33G-EXT": {
        "label": "Remote Worker KITAS (E33G), продление",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "work.organization",
            "work.position",
            "work.annual_amount",
            "indonesia.permit_no",
            "indonesia.permit_expiry",
            "home.address",
        ],
        "optional": ["identity.citizenship"],
        "not_needed": [],
        "min_balance_usd": 2000,
        "min_annual_usd": 60000,
        "needs_contract": True,
        "needs_cv": True,
        "needs_e02": True,
        "note": "Продление рабочего KITAS: договор и доход подтверждаются заново.",
    },
    "BRIDGING": {
        "label": "Bridging visa (Izin Tinggal Peralihan)",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "indonesia.permit_no",
            "indonesia.permit_expiry",
            "indonesia.address",
            "home.address",
            "finance.balance",
        ],
        "optional": ["identity.citizenship"],
        "not_needed": ["work.organization", "work.position", "work.annual_amount"],
        "min_balance_usd": 2000,
        "needs_contract": False,
        "needs_cv": False,
        "needs_e02": True,
        "note": "60 дней, не продлевается, только на территории Индонезии.",
    },
    "CONV": {
        "label": "Конверсия визы (переход на ITAS)",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "indonesia.permit_no",
            "indonesia.address",
            "home.address",
            "finance.balance",
        ],
        "optional": ["identity.citizenship"],
        "not_needed": ["work.annual_amount"],
        "min_balance_usd": 2000,
        "needs_contract": False,
        "needs_cv": False,
        "needs_e02": True,
        "note": "Нужен адрес проживания и Surat Keterangan Domisili.",
    },
    "D12": {
        "label": "Виза D12",
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
            "home.address",
            "finance.balance",
        ],
        "optional": ["identity.citizenship"],
        "not_needed": ["work.annual_amount"],
        "min_balance_usd": 5000,
        "needs_contract": False,
        "needs_cv": True,
        "needs_e02": False,
        "note": "Остаток от 5 000 USD (у C1/E33G — 2 000). Обязательны CV и itinerary.",
    },
}

# Как падение продукта из заявки приводится к записи выше.
ALIASES = {
    "C1-EXT": "C1-EXT",
    "C1EXT": "C1-EXT",
    "C1": "C1",
    "B211A": "C1",
    "E33G-NEW": "E33G-NEW",
    "E33G-NEW-NEW": "E33G-NEW",
    "E33G-EXT": "E33G-EXT",
    "E33GEXT": "E33G-EXT",
    "E33G": "E33G-NEW",
    "BRIDGING": "BRIDGING",
    "BRIDGE": "BRIDGING",
    "CONV": "CONV",
    "CONVERSION": "CONV",
    "D12": "D12",
}


def for_product(product_code: str | None) -> dict:
    """Требования продукта. Для неизвестного продукта — безопасный минимум.

    Безопасный минимум: только личность. Так неизвестный код продукта не заставит
    систему требовать у клиента договор или доход, которых иммиграция не просит.
    """
    code = (product_code or "").strip().upper()
    key = ALIASES.get(code) or code
    req = PRODUCTS.get(key)
    if req:
        return dict(req, code=key)
    return {
        "code": code or "?",
        "label": "Продукт не опознан (%s)" % (code or "—"),
        "fields": [
            "identity.full_name_latin",
            "identity.birth_date",
            "identity.passport_no",
            "identity.passport_expiry",
        ],
        "optional": [],
        "not_needed": ["work.organization", "work.position", "work.annual_amount"],
        "min_balance_usd": 0,
        "needs_contract": False,
        "needs_cv": False,
        "needs_e02": False,
        "note": "Требования не заданы: ничего лишнего у клиента не спрашиваем.",
    }


def needed_fields(product_code: str | None) -> set:
    return set(for_product(product_code).get("fields") or [])


def is_needed(product_code: str | None, layer_field: str) -> bool:
    """Нужно ли это поле продукту (для фильтра легенды)."""
    req = for_product(product_code)
    return layer_field in set(req.get("fields") or []) | set(req.get("optional") or [])


def min_balance_rub(product_code: str | None, usd_rub: float | None = None) -> float:
    """Порог остатка в рублях для этого продукта (0 — порога нет)."""
    req = for_product(product_code)
    usd = float(req.get("min_balance_usd") or 0)
    if usd <= 0:
        return 0.0
    rate = float(usd_rub or USD_RUB_DEFAULT)
    return usd * rate


def statements_needed(product_code: str | None) -> int:
    """Сколько банковских справок (по числу разных банков) требует продукт.

    Справка об остатке — одна: дублировать её из разных банков нельзя, лишняя
    справка в пакете является замечанием иммиграции.
    """
    return 1 if for_product(product_code).get("min_balance_usd") else 0
