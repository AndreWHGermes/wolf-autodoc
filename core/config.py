"""Ядро: конфигурация системы Wolf_AutoDoc CRM (порт 8091)."""
from __future__ import annotations

import os
from pathlib import Path

# Каталог проекта определяется от самого файла (или из окружения WOLF_BASE),
# а не жёстко: иначе копия системы писала бы в данные оригинала.
BASE_DIR = Path(os.environ.get("WOLF_BASE") or Path(__file__).resolve().parent.parent)
BLOCKS_DIR = BASE_DIR / "CLIENTs"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"          # оригиналы, загруженные вручную
SOURCES_DIR = DATA_DIR / "sources"          # PDF-эталоны шаблонов
HTML_DIR = DATA_DIR / "CLIENT"           # HTML-шаблоны после конвертации
RENDER_DIR = DATA_DIR / "renders"           # сгенерированные PDF
DOCS_DIR = BASE_DIR / "docs"                # документация по блокам

for _d in (DATA_DIR, UPLOAD_DIR, SOURCES_DIR, HTML_DIR, RENDER_DIR, DOCS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("WOLF_DB") or (DATA_DIR / "wolf.db"))

WEB_HOST = os.environ.get("WOLF_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WOLF_PORT", "8091"))
WEB_SECRET = os.environ.get("WOLF_SECRET", "wolf-autodoc-8091-secret")
SESSION_HOURS = 12
MAX_UPLOAD_MB = 25

# вход по умолчанию (пока нет пользователей в базе)
DEFAULT_ADMIN_LOGIN = "admin"
DEFAULT_ADMIN_PASSWORD = "123"
