# services/transport/gdrive_write.py
"""Фасад над services.gdrive_write (запись на Google Drive, scope drive.file)."""

from services.gdrive_write import (  # noqa: F401
    _get_service, _read_service, _retry_on_quota,
    resolve_folder_id, list_folder_contents,
    _find_for_write, find_file_in_folder,
    create_folder, ensure_folder,
    upload_file, upload_bytes, upload_html_as_gdoc,
    export_gdoc, download_file,
    _guess_mime, delete_item,
)

__all__ = [
    "resolve_folder_id", "list_folder_contents",
    "find_file_in_folder", "create_folder", "ensure_folder",
    "upload_file", "upload_bytes", "upload_html_as_gdoc",
    "export_gdoc", "download_file", "delete_item",
]