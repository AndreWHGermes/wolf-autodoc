# services/templates/bank_statements/_common.py
"""
Общая логика для ВСЕХ банковских справок (tbank + sber, 3m + 12m).

Что здесь живёт:
- Форматирование ФИО клиента (Title Case) — единое правило для всех банков
  (требование заказчика от 17.10.2026, см. data/variables/client_name.yaml).
- Исключение справок «чужого» банка из пакета (если клиент TBank, Сбер уходит в excluded).
- Чтение эталонного образца для сверки.

Сюда НЕ входит:
- Формат суммы (он разный у TBank и Сбера, см. tbank.py / sber.py).
- Конкретные координаты и тексты бланка (это в data/templates/<code>/template.html).

Когда правка:
- Если меняется правило ФИО для всех справок → только этот файл.
- Если меняется формат суммы для TBank → tbank.py.
- Если меняется формат суммы для Сбера → sber.py.
"""

from __future__ import annotations
from typing import Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# ФИО клиента — единое правило Title Case для всех банковских справок
# ─────────────────────────────────────────────────────────────────────────────

def name_title_case(value: str) -> str:
    """Title Case для ФИО: «TOVPEKO EGOR» → «Tovpeko Egor».

    Каждое слово с заглавной, остальные строчные. Дефисы и апострофы не ломаем.
    Используется и для шапки (справа сверху), и для текста справки — переменная
    одна и та же, поэтому обе подстановки получают одинаковый регистр.
    """
    import re
    if not value:
        return ""
    out = []
    for word in value.split():
        chunks = re.split(r"([\-'])", word)
        out.append("".join(
            c if c in "-'" else (c[:1].upper() + c[1:].lower())
            for c in chunks if c
        ))
    return " ".join(out)


def normalize_client_name(value: str | None) -> str:
    """Прогнать значение client_name через Title Case.

    Используется autofill.force для переписывания старого кэша TOVPEKO EGOR
    на Tovpeko Egor при каждой пересборке.
    """
    return name_title_case(str(value or "").strip())


# ─────────────────────────────────────────────────────────────────────────────
# Исключение чужого банка
# ─────────────────────────────────────────────────────────────────────────────

def exclude_other_bank_codes(app_id: int) -> list[str]:
    """Вернуть список tpl.code, которые надо пометить status='excluded'.

    Логика: если у клиента в пакете есть и Т‑Банк и Сбер, оставляем только
    банк клиента, остальные → excluded. Иначе пакет «согласовано 1 из 2»
    и проверка пакета блокирует отправку.
    """
    # Импорт внутри функции, чтобы не тянуть core/db на старте модуля
    from core import db
    rows = db.q(
        "SELECT t.code FROM application_documents ad "
        "JOIN templates t ON t.id = ad.template_id "
        "WHERE ad.application_id = ?",
        (app_id,),
    )
    codes = {str(r["code"]) for r in rows}
    has_t = any("__tbank" in c for c in codes)
    has_s = any("__sber" in c for c in codes)
    if has_t and has_s:
        # Исключаем Сбер (предполагаем, что Т‑Банк — основной у текущего клиента)
        # В будущем: брать bank_of_client из bank_choice.
        return [c for c in codes if "__sber" in c]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Паспорт переменной (загружается из data/variables/<name>.yaml, если есть)
# ─────────────────────────────────────────────────────────────────────────────

def load_variable_passport(name: str) -> Dict[str, Any] | None:
    """Прочитать паспорт переменной из data/variables/<name>.yaml.

    Используется values/orchestrator.py для решения, какое правило применить
    в каком шаблоне. Если паспорта нет — берём правила из TEMPLATE_RULES[code].
    """
    from pathlib import Path
    import yaml
    p = Path("/opt/wolf_v2/data/variables") / f"{name}.yaml"
    if not p.exists():
        return None
    try:
        with p.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None