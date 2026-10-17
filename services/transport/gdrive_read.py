# services/transport/gdrive_read.py
"""Фасад над services.gdrive_api (чтение с Google Drive, scope drive.readonly)."""

from services.gdrive_api import (  # noqa: F401
    available, email, service, folder_id, list_files,
    _list_files_uncached, download, sync_folder,
)

__all__ = [
    "available", "email", "service", "folder_id", "list_files",
    "download", "sync_folder",
]