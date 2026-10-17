# services/pools/employers.py
"""Фасад над services.employer_pool (зарубежные работодатели)."""

from services.employer_pool import (  # noqa: F401
    is_foreign, is_indonesian, city_of, city_in_text, load, ready,
    _pick_from, pick, normalize_title, by_title, by_any,
    values_of, values_for, titles,
)

__all__ = [
    "is_foreign", "is_indonesian", "city_of", "city_in_text",
    "load", "ready", "pick", "normalize_title", "by_title", "by_any",
    "values_of", "values_for", "titles",
]