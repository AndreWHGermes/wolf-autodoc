# services/pools/builder.py
"""Фасад над services.pool_builder (построение пулов из архива)."""

from services.pool_builder import (  # noqa: F401
    expand_archives, build_for_client, main,
)

# Алиасы для унифицированного имени
build_pools = build_for_client
refresh_pools = expand_archives

def pool_stats():
    """Заглушка статистики пулов — реальная реализация требует чтения БД."""
    return {"orgs": 0, "salaries": 0, "note": "см. services.pool_builder"}

__all__ = ["build_pools", "refresh_pools", "pool_stats"]