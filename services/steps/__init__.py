"""
Единая точка входа для логирования шагов обработки заявки.

Тонкий фасад над services.app_steps. Новый код может звать просто
«from services.steps import step, trail, where_now» без лапок.

Точка расширения: добавить шаги (например, 'kitas_send', 'e02_check'),
добавить группировку шагов по попыткам, метрики — добавляем сюда.
"""
from services.app_steps import (  # noqa: F401
    step as step,
    trail as trail,
    where_now as where_now,
    attempt_of as attempt_of,
    summary as summary,
    timeline as timeline,
    timer as timer,
)


def ok(app_id: int, name: str, note: str = "", actor: str = "система") -> None:
    """Записать успешный шаг."""
    step(app_id, name, "ok", note=note, actor=actor)


def warn(app_id: int, name: str, note: str = "", actor: str = "система") -> None:
    """Записать предупреждение."""
    step(app_id, name, "warn", note=note, actor=actor)


def fail(app_id: int, name: str, note: str = "", actor: str = "система") -> None:
    """Записать ошибку."""
    step(app_id, name, "fail", note=note, actor=actor)


def run(app_id: int, name: str, note: str = "", actor: str = "система") -> None:
    """Записать начало выполнения."""
    step(app_id, name, "run", note=note, actor=actor)


__all__ = [
    "step", "trail", "where_now", "attempt_of", "summary", "timeline", "timer",
    "ok", "warn", "fail", "run",
]