# services/values/registry.py
"""
Реестр переменных: какая переменная из какого источника, формат, проверки.

Загружает паспорта из data/variables/<name>.yaml и отдаёт их по запросу.
Используется values/orchestrator.py для решения, какое правило применить
к конкретному шаблону.

Этап 2 рефакторинга: добавление явного слоя описания переменных.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional


_VAR_DIR = Path("/opt/wolf_v2/data/variables")
_CACHE: Dict[str, Dict[str, Any]] = {}


def get_passport(name: str) -> Optional[Dict[str, Any]]:
    """Загрузить паспорт переменной из data/variables/<name>.yaml.

    Возвращает None, если паспорта нет — тогда правило берётся из defaults.
    """
    if name in _CACHE:
        return _CACHE[name]
    p = _VAR_DIR / f"{name}.yaml"
    if not p.exists():
        return None
    try:
        import yaml
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _CACHE[name] = data
        return data
    except Exception:
        return None


def list_known() -> list[str]:
    """Список имён переменных, для которых есть паспорт."""
    if not _VAR_DIR.exists():
        return []
    return sorted(p.stem for p in _VAR_DIR.glob("*.yaml"))


def apply_passport_rules(name: str, value: Any, tpl_code: str = "") -> Any:
    """Применить к значению правила из паспорта (если есть template_overrides).

    Например: client_name в банковской справке → smart_title, в CV → оставить как есть.
    """
    passport = get_passport(name)
    if not passport:
        return value
    fmt = passport.get("format") or {}
    overrides = fmt.get("template_overrides") or {}
    if tpl_code in overrides:
        rule = overrides[tpl_code]
        if rule == "smart_title" and isinstance(value, str):
            from .personal import _smart_title
            return _smart_title(value)
        if rule == "upper" and isinstance(value, str):
            return value.upper()
        if rule == "lower" and isinstance(value, str):
            return value.lower()
    # Default format
    default = fmt.get("default")
    if default == "smart_title" and isinstance(value, str):
        from .personal import _smart_title
        return _smart_title(value)
    return value