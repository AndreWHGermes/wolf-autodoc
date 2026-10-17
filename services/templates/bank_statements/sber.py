# services/templates/bank_statements/sber.py
"""
Правила для банковских справок Сбера (3m и 12m).

Покрывает коды:
- bank_statement_3m__sber
- bank_statement_12m__sber

Специфика Сбера (отличия от Т‑Банка):
- Сумма: «17621.29» (разряды БЕЗ пробелов, копейки через точку) — как в подлиннике.
- Банк: «SberBank», лицензия ЦБ РФ № 9441.
- 3m: тот же период, другая форма числа.
- 12m: тот же период, другая форма числа.

ФИО Title Case — в _common.py (общее для всех банков, требование 17.10.2026).

Что НЕ здесь:
- ФИО Title Case — в _common.py.
- Исключение Сбера из пакета Т‑Банк-клиента — в _common.py.
"""

from __future__ import annotations
from ._common import name_title_case, normalize_client_name  # noqa: F401

CODES = ("bank_statement_3m__sber", "bank_statement_12m__sber")


def amount_format(value) -> str:
    """Формат суммы для Сбера: «17621.29» (без пробелов, точка).

    Раньше Сбер уходил с форматом Т‑Банка — расхождение с подлинником.
    """
    s = str(value or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return ""
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return str(value)
    intpart = int(v)
    cents = int(round((v - intpart) * 100))
    # Без пробелов в разрядах — это особенность Сбера
    return f"{intpart}.{cents:02d}"


def license_no() -> str:
    return "9441"


def bank_name() -> str:
    return "SberBank"


def template_codes() -> tuple[str, ...]:
    return CODES