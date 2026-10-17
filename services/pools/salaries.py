# services/pools/salaries.py
"""Фасад над services.salary_pool (оклады по должности и отрасли)."""

from services.salary_pool import (  # noqa: F401
    load, limits, in_range, pick, gen, words_en, values_for,
)

__all__ = ["load", "limits", "in_range", "pick", "gen", "words_en", "values_for"]