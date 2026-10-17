# services/transport/gdrive_oauth.py
"""Фасад над services.gdrive_oauth (OAuth-токен владельца)."""

from services.gdrive_oauth import (  # noqa: F401
    _post, _client, main,
)

__all__ = ["_post", "_client", "main"]