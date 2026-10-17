"""
Единая точка входа для управления очередью заявок.

Тонкий фасад над функциями blocks/dashboard/page.py:
- _queue_set      → set_state(app_id, action)
- _queue_state    → state(app_id)
- _queue_positions → positions()
- _queue_ensure   → ensure_table()
- _wake_worker    → wake_worker()
- _is_active_elsewhere → is_active_elsewhere(app_id)

Старые вызовы вроде `from blocks.dashboard.page import _queue_set` продолжают
работать (мы их НЕ трогаем). Новый код может звать `from services.queue import ...`.

Точка расширения: добавить приоритеты, несколько воркеров, метрики —
добавляем сюда без правки page.py.
"""
from blocks.dashboard.page import (  # noqa: F401
    _queue_set as set_state,
    _queue_state as state,
    _queue_positions as positions,
    _queue_ensure as ensure_table,
    _wake_worker as wake_worker,
    _is_active_elsewhere as is_active_elsewhere,
    _last_run as last_run,
)


def start(app_id: int, auto_wake: bool = True) -> str:
    """Поставить заявку в очередь и (опционально) разбудить воркер."""
    new_state = set_state(app_id, "start")
    if auto_wake:
        wake_worker()
    return new_state


def pause(app_id: int) -> str:
    """Остановить обработку заявки."""
    return set_state(app_id, "pause")


def is_running(app_id: int) -> bool:
    """Идёт ли обработка прямо сейчас (включая состояние 'running')."""
    return state(app_id) == "running"


__all__ = [
    "set_state", "state", "positions", "ensure_table", "wake_worker",
    "is_active_elsewhere", "last_run", "start", "pause", "is_running",
]