# services/pools/universities.py
"""Фасад над services.pool_uni (вузы по профилю)."""

from services.pool_uni import (  # noqa: F401
    majors_of, build_links, professions_for, all_titles, count_for, pick,
)

__all__ = ["majors_of", "build_links", "professions_for", "all_titles", "count_for", "pick_university"]
# Алиас для будущего унифицированного имени
pick_university = pick