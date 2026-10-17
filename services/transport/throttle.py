# services/transport/throttle.py
"""Фасад над services.drive_throttle (троттлинг запросов к GDrive)."""

from services.drive_throttle import (  # noqa: F401
    _load, _save, _hour_calls, _clock, can_call,
)

__all__ = ["can_call", "_hour_calls", "_clock"]