# services/templates/__init__.py
"""
Реестр правил по шаблонам документов.

Принцип:
- TEMPLATE_RULES[code] указывает на модуль с правилами для конкретного бланка.
- Внешний код запрашивает правила через get_rules(code) — никогда не импортирует
  модуль шаблона напрямую. Это позволяет вынести правила в отдельные файлы без
  правок вызывающего кода.

Добавление нового шаблона:
  1. Создаёшь services/templates/<type>/<code>.py с правилами.
  2. Регистрируешь ниже: "code": import_module(".type.code", __name__)
  3. Готово — автосборка подхватит без правок в values.py/autofill.py.
"""

from __future__ import annotations
from importlib import import_module
from types import ModuleType
from typing import Dict

# ─────────────────────────────────────────────────────────────────────────────
# Реестр: code → модуль с правилами
# Заполняется по мере переноса правил из values.py/других модулей.
# Пусто = правила ещё в старом месте, читаются по старой цепочке.
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATE_RULES: Dict[str, str] = {
    # Банковские справки (после этапа 1 рефакторинга)
    "bank_statement_3m__tbank":   "services.templates.bank_statements.tbank",
    "bank_statement_12m__tbank":  "services.templates.bank_statements.tbank",
    "bank_statement_3m__sber":    "services.templates.bank_statements.sber",
    "bank_statement_12m__sber":   "services.templates.bank_statements.sber",

    # Договоры (после этапа 2)
    "remote_work_agreement__default": "services.templates.contracts.remote_work",
    "employment_contract__default":   "services.templates.contracts.employment",

    # Письма (после этапа 3)
    "bridging_request_letter__ngurahrai": "services.templates.letters.bridging",
    "bridging_request_letter__denpasar":  "services.templates.letters.bridging",
    "bridging_request_letter__tabanan":   "services.templates.letters.bridging",
    "conversion_request_letter__ngurahrai": "services.templates.letters.conversion",
    "conversion_request_letter__denpasar":  "services.templates.letters.conversion",

    # CV (после этапа 4)
    "cv__format_sivaev": "services.templates.cv.sivaev",

    # E-02 (после этапа 5)
    "statement_letter_e02": "services.templates.e02",
}

# Кэш уже загруженных модулей, чтобы не импортировать повторно
_LOADED: Dict[str, ModuleType] = {}


def get_rules(code: str) -> ModuleType | None:
    """Вернуть модуль правил для данного шаблона.

    Возвращает None, если шаблон ещё не перенесён в новый реестр —
    тогда читаем по старой цепочке (services/values.py и т.д.).
    Это позволяет мигрировать правила постепенно, без переключателя.
    """
    if code in _LOADED:
        return _LOADED[code]
    module_path = TEMPLATE_RULES.get(code)
    if not module_path:
        return None
    try:
        mod = import_module(module_path)
        _LOADED[code] = mod
        return mod
    except ImportError as e:
        # Модуль ещё не создан — это нормально в процессе миграции
        return None


def has_new_rules(code: str) -> bool:
    """Есть ли для этого шаблона правила в новом реестре (services/templates/)."""
    return code in TEMPLATE_RULES and get_rules(code) is not None


def register(code: str, module_path: str) -> None:
    """Зарегистрировать правила для нового шаблона.

    Вызывается из модуля шаблона при импорте, если модуль сам знает свой код.
    Это позволяет не править TEMPLATE_RULES при добавлении шаблона —
    достаточно один раз импортировать его через register().
    """
    TEMPLATE_RULES[code] = module_path
    _LOADED.pop(code, None)  # сбросить кэш, чтобы перечитать