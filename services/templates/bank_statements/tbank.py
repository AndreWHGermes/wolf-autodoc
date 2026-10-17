# services/templates/bank_statements/tbank.py
"""
Правила для банковских справок Т‑Банка (3m и 12m).

Покрывает коды:
- bank_statement_3m__tbank
- bank_statement_12m__tbank

Специфика Т‑Банка:
- Сумма: «6 277 000, 00» (разряды через пробел, копейки через запятую).
- Банк: «TBank», лицензия ЦБ РФ № 2673.
- 3m: период за последние 3 месяца.
- 12m: период за последние 12 месяцев.

Что НЕ здесь:
- ФИО Title Case — в _common.py (общее для всех банков).
- Исключение Сбера — в _common.py.
- Координаты бланка — в data/templates/bank_statement_*__tbank/template.html.
"""

from __future__ import annotations
from ._common import name_title_case, normalize_client_name  # noqa: F401

# Коды шаблонов, которые покрывает этот модуль
CODES = ("bank_statement_3m__tbank", "bank_statement_12m__tbank")


def amount_format(value) -> str:
    """Формат суммы для Т‑Банка: «6 277 000, 00».

    Разряды через пробел, копейки через запятую с двумя знаками.
    Пример: amount_format("6277000.00") → "6 277 000, 00"
    """
    s = str(value or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return ""
    # Если есть точка как разделитель копеек — нормализуем в запятую
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
    # Разряды через пробел
    return f"{intpart:,}".replace(",", " ") + f",{cents:02d}"


def license_no() -> str:
    """Номер лицензии Т‑Банка в тексте справки."""
    return "2673"


def bank_name() -> str:
    return "TBank"


def template_codes() -> tuple[str, ...]:
    return CODES