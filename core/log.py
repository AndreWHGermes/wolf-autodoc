"""Логирование Wolf AutoDoc.

Раньше в коде было 136 «глухих» перехватов исключений — ошибки исчезали молча,
и о проблемах узнавали от заказчика. Теперь есть единый логгер: пишем в logs/wolf.log
и в journald, ошибки запросов фиксируются с трассировкой.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import BASE_DIR

LOG_DIR = Path(BASE_DIR) / "logs"
LOG_FILE = LOG_DIR / "wolf.log"
_configured = False


def setup(level: int = logging.INFO) -> logging.Logger:
    """Настраивает корневой логгер проекта (вызывается один раз при старте)."""
    global _configured
    logger = logging.getLogger("wolf")
    if _configured:
        return logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    logger.setLevel(level)
    _configured = True
    logger.info("логирование запущено, файл %s", LOG_FILE)
    return logger


def get_logger(name: str = "wolf") -> logging.Logger:
    return logging.getLogger(name)
