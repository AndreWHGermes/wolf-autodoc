# services/pools/selector.py
"""
Единая точка выбора пула по клиенту.

Фасад над services.pool_assign. Новый код может звать просто
«from services.pools.selector import pick_pool_for» вместо того, чтобы
лезть в низкоуровневый pool_assign.
"""

from services.pool_assign import (  # noqa: F401
    pick_value, assign,
)

__all__ = ["pick_value", "assign"]