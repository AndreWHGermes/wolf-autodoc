# services/templates/bank_statements/__init__.py
"""Реестр банковских справок: tbank (3m/12m), sber (3m/12m).

Все справки делят общие правила (ФИО Title Case, исключение чужого банка),
но различаются форматом суммы и текстом «hereby informs».

Правило для ФИО (Title Case) действует на ВСЕ справки одинаково —
это требование заказчика от 17.10.2026.

Структура:
  tbank.py  — 3m и 12m Т‑Банка
  sber.py   — 3m и 12m Сбера
  _common.py — общая логика: ФИО, exclude_other_bank, проверки пакета
"""

from services.templates.bank_statements import tbank, sber  # noqa: F401

__all__ = ["tbank", "sber"]