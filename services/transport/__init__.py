# services/transport/__init__.py
"""
Транспорт — единая точка входа для интеграций с Google Drive.

Здесь фасады над существующими модулями:
- services/transport/gdrive_read.py  — services.gdrive_api
- services/transport/gdrive_write.py — services.gdrive_write
- services/transport/gdrive_oauth.py — services.gdrive_oauth
- services/transport/drive.py        — services.drive (высокоуровневая обёртка)
- services/transport/throttle.py     — services.drive_throttle

Этап 4 рефакторинга: фасады. Никаких переездов кода — только единая точка входа.
"""

from .gdrive_read import *  # noqa: F401, F403
from .gdrive_write import * # noqa: F401, F403
from .gdrive_oauth import * # noqa: F401, F403
from .drive import *        # noqa: F401, F403
from .throttle import *     # noqa: F401, F403