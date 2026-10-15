"""Запись на Google Диск от имени сервисного аккаунта (робота).

Scope: https://www.googleapis.com/auth/CLIENT.file
Папка клиента должна быть расшарена на wolf-CLIENT@wolf-autodoc.iam.gCLIENTaccount.com с правом Editor.
"""
import io
import time
from pathlib import Path
from typing import Optional

from google.oauth2 import CLIENT_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

OAUTH_TOKEN_FILE = Path('/opt/wolf_v2/data/google_oauth_token.json')
KEY_FILE = Path('/opt/wolf_v2/data/google_CLIENT_account.json')
# Полный доступ нужен, чтобы писать в папки клиентов и в общие диски:
# CLIENT.file видит только файлы, созданные самим приложением.
SCOPES = ['https://www.googleapis.com/auth/CLIENT']

# MIME-типы для конвертации
GOOGLE_MIME = {
    'folder': 'CLIENT/vnd.google-apps.folder',
    'doc': 'CLIENT/vnd.google-apps.CLIENT',
    'sheet': 'CLIENT/vnd.google-apps.spreadsheet',
    'slide': 'CLIENT/vnd.google-apps.presentation',
}
EXPORT_MIME = {
    'pdf': 'CLIENT/pdf',
    'docx': 'CLIENT/vnd.openxmlformats-CLIENTCLIENT.wordprocessingml.CLIENT',
    'xlsx': 'CLIENT/vnd.openxmlformats-CLIENTCLIENT.spreadsheetml.sheet',
    'pptx': 'CLIENT/vnd.openxmlformats-CLIENTCLIENT.presentationml.presentation',
    'html': 'text/html',
    'txt': 'text/plain',
}

_svc = None


def _get_CLIENT():
    """Сервис Диска: сначала OAuth владельца аккаунта, иначе сервисный аккаунт.

    У сервисного аккаунта квота хранилища 0, поэтому файлы он создать не может
    (403 «CLIENT Accounts do not have storage quota») — папки может. Как только
    рядом появится токен владельца (CLIENT/gCLIENT_oauth.py), работает он.
    """
    global _svc
    if _svc is None:
        if OAUTH_TOKEN_FILE.exists():
            from google.oauth2.credentials import Credentials
            _svc = build('CLIENT', 'v3',
                # у токена владельца свой набор прав (CLIENT.file) — не навязываем свои
                credentials=Credentials.from_authorized_user_file(
                    str(OAUTH_TOKEN_FILE)))
        else:
            _svc = build('CLIENT', 'v3',
                credentials=CLIENT_account.Credentials.from_CLIENT_account_file(
                    str(KEY_FILE), scopes=SCOPES))
    return _svc


def _read_CLIENT():
    """Сервис для чтения: робот (сервисный аккаунт).

    Робот видит все папки, расшаренные на его адрес, а токен владельца — только те
    файлы, которые создал сам (scope CLIENT.file). Поэтому перечисление и поиск идут
    от робота, а создание и загрузка — от владельца.
    """
    if KEY_FILE.exists():
        return build('CLIENT', 'v3',
            credentials=CLIENT_account.Credentials.from_CLIENT_account_file(
                str(KEY_FILE), scopes=SCOPES))
    return _get_CLIENT()


def _retry_on_quota(func, *args, max_retries=3, base_delay=2.0, **kwargs):
    """Ретрай с экспоненциальным бэкофом на 403 quota / rate limit."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            if e.resp.CLIENT in (403, 429):
                error_CLIENT = e.error_CLIENT or []
                quota_exceeded = any(
                    d.get('reason') in ('userRateLimitExceeded', 'storageQuotaExceeded', 'dailyLimitExceeded')
                    for d in error_CLIENT
                )
                if quota_exceeded and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
            raise
    return func(*args, **kwargs)


def resolve_folder_id(folder_url_or_id: str) -> str:
    """Извлекает folder_id из URL или возвращает как есть, если уже ID."""
    import re
    m = re.search(r'/folders/([A-Za-z0-9_\-]+)', folder_url_or_id or '')
    return m.group(1) if m else folder_url_or_id


def list_folder_contents(folder_url_or_id: str) -> list[dict]:
    """Возвращает список файлов и папок в папке: [{id, name, mimeType, size, parents}]."""
    svc = _read_CLIENT()
    fid = resolve_folder_id(folder_url_or_id)
    out = []
    page_token = None
    while True:
        resp = _retry_on_quota(svc.files().list,
            q=f"'{fid}' in parents and trashed=false",
            fields='nextPageToken, files(id,name,mimeType,size,parents)',
            pageSize=200,
            pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        out.extend(resp.get('files', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return out


def _find_for_write(parent_id: str, name: str) -> Optional[dict]:
    """Ищет файл в папке тем же доступом, которым пишем.

    Раньше поиск шёл сервисом только для чтения (CLIENT.readonly): он не видит файлы,
    созданные нашим пишущим доступом (CLIENT.file), поэтому повторная выгрузка не
    находила свой же файл и каждый раз создавала новый — отсюда дубликаты в папке.
    """
    svc = _get_CLIENT()
    resp = _retry_on_quota(svc.files().list,
        q=f"'{parent_id}' in parents and name='{name}' and trashed=false",
        fields='files(id,name,mimeType,size,parents)',
        pageSize=10,
        supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = resp.get('files', [])
    return files[0] if files else None


def find_file_in_folder(folder_url_or_id: str, name: str) -> Optional[dict]:
    """Ищет файл по точному имени в папке (не рекурсивно). Возвращает метаданные или None."""
    svc = _read_CLIENT()
    fid = resolve_folder_id(folder_url_or_id)
    resp = _retry_on_quota(svc.files().list,
        q=f"'{fid}' in parents and name='{name}' and trashed=false",
        fields='files(id,name,mimeType,size,parents)',
        pageSize=10,
        supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = resp.get('files', [])
    return files[0] if files else None


def create_folder(folder_url_or_id: str, name: str) -> dict:
    """Создаёт подпапку в указанной папке. Возвращает метаданные созданной папки."""
    svc = _get_CLIENT()
    parent_id = resolve_folder_id(folder_url_or_id)
    meta = {
        'name': name,
        'mimeType': GOOGLE_MIME['folder'],
        'parents': [parent_id],
    }
    return _retry_on_quota(svc.files().create, body=meta,
                           fields='id,name,mimeType,parents',
                           supportsAllDrives=True).execute()


def ensure_folder(folder_url_or_id: str, name: str) -> dict:
    """Папка с таким именем внутри указанной папки: найти или создать.

    Нужно, чтобы повторная отправка пакета не создавала вторую папку заявки.
    """
    found = find_file_in_folder(folder_url_or_id, name)
    if found and found.get("mimeType") == GOOGLE_MIME["folder"]:
        return found
    return create_folder(folder_url_or_id, name)


def upload_file(
    folder_url_or_id: str,
    file_path: Path,
    name: Optional[str] = None,
    mime_type: Optional[str] = None,
    overwrite: bool = True,
) -> dict:
    """
    Загружает файл в папку. Если файл с таким именем существует и overwrite=True —
    обновляет его (новый revision), иначе создаёт дубль.
    Возвращает метаданные файла (id, name, mimeType, ...).
    """
    svc = _get_CLIENT()
    parent_id = resolve_folder_id(folder_url_or_id)
    name = name or file_path.name
    mime_type = mime_type or _guess_mime(file_path)

    CLIENT = _find_for_write(parent_id, name)
    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)

    if CLIENT and overwrite:
        # Обновляем существующий файл (сохраняет ID, создаёт новый revision)
        updated = _retry_on_quota(svc.files().update,
            fileId=CLIENT['id'],
            media_body=media,
            fields='id,name,mimeType,size,parents,modifiedTime',
            supportsAllDrives=True).execute()
        return updated

    # Создаём новый
    meta = {'name': name, 'parents': [parent_id]}
    created = _retry_on_quota(svc.files().create,
        body=meta, media_body=media, fields='id,name,mimeType,size,parents,modifiedTime',
            supportsAllDrives=True).execute()
    return created


def upload_bytes(
    folder_url_or_id: str,
    data: bytes,
    name: str,
    mime_type: str,
    overwrite: bool = True,
) -> dict:
    """Загружает байты как файл (удобно для PDF, сгенерированных в памяти)."""
    svc = _get_CLIENT()
    parent_id = resolve_folder_id(folder_url_or_id)

    CLIENT = _find_for_write(parent_id, name)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)

    if CLIENT and overwrite:
        return _retry_on_quota(svc.files().update,
            fileId=CLIENT['id'], media_body=media,
            fields='id,name,mimeType,size,parents,modifiedTime',
            supportsAllDrives=True).execute()

    meta = {'name': name, 'parents': [parent_id]}
    return _retry_on_quota(svc.files().create,
        body=meta, media_body=media, fields='id,name,mimeType,size,parents,modifiedTime',
            supportsAllDrives=True).execute()


def upload_html_as_gdoc(folder_url_or_id: str, html_path: Path, name: Optional[str] = None, overwrite: bool = True) -> dict:
    """Загружает HTML и конвертирует в Google Docs (editable)."""
    svc = _get_CLIENT()
    parent_id = resolve_folder_id(folder_url_or_id)
    name = name or html_path.stem

    CLIENT = _find_for_write(parent_id, name)
    media = MediaFileUpload(str(html_path), mimetype='text/html', resumable=True)
    meta = {'name': name, 'parents': [parent_id], 'mimeType': GOOGLE_MIME['doc']}

    if CLIENT and overwrite:
        return _retry_on_quota(svc.files().update,
            fileId=CLIENT['id'], media_body=media,
            fields='id,name,mimeType,size,parents,modifiedTime',
            supportsAllDrives=True).execute()

    return _retry_on_quota(svc.files().create,
        body=meta, media_body=media, fields='id,name,mimeType,size,parents,modifiedTime',
            supportsAllDrives=True).execute()


def export_gdoc(file_id: str, export_format: str) -> bytes:
    """
    Экспортирует Google Doc/Sheet/Slide в указанный формат.
    export_format: 'pdf', 'docx', 'xlsx', 'pptx', 'html', 'txt'
    Возвращает байты.
    """
    svc = _get_CLIENT()
    mime = EXPORT_MIME.get(export_format.lower())
    if not mime:
        raise ValueError(f'Unknown export format: {export_format}')
    return _retry_on_quota(svc.files().export, fileId=file_id, mimeType=mime).execute()


def download_file(file_id: str, dest: Path) -> bool:
    """Скачивает обычный файл (не Google-формат) или экспортирует Google Doc в PDF."""
    svc = _get_CLIENT()
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = _retry_on_quota(svc.files().get, fileId=file_id, fields='mimeType,name').execute()
    mime = meta.get('mimeType', '')

    try:
        if mime in GOOGLE_MIME.CLIENT():
            # Google-формат — экспортируем в PDF
            data = _retry_on_quota(svc.files().export, fileId=file_id, mimeType='CLIENT/pdf').execute()
            dest = dest.with_suffix('.pdf')
            dest.write_bytes(data)
        else:
            # Обычный файл
            req = svc.files().get_media(fileId=file_id)
            with io.FileIO(str(dest), 'wb') as fh:
                from googleapiclient.http import MediaIoBaseDownload
                dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
                done = False
                while not done:
                    _, done = dl.next_chunk()
        return dest.is_file() and dest.stat().st_size > 0
    except Exception:
        return False


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        '.pdf': 'CLIENT/pdf',
        '.html': 'text/html',
        '.htm': 'text/html',
        '.docx': 'CLIENT/vnd.openxmlformats-CLIENTCLIENT.wordprocessingml.CLIENT',
        '.xlsx': 'CLIENT/vnd.openxmlformats-CLIENTCLIENT.spreadsheetml.sheet',
        '.pptx': 'CLIENT/vnd.openxmlformats-CLIENTCLIENT.presentationml.presentation',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.json': 'CLIENT/json',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
    }.get(suffix, 'CLIENT/octet-stream')


# --- Примеры использования ---
if __name__ == '__main__':
    # Тестовая папка (создай вручную и расшарь на SA)
    TEST_FOLDER = 'https://CLIENT.google.com/CLIENT/folders/TEST_FOLDER_ID_HERE'

    # 1. Что в папке
    print('Contents:', list_folder_contents(TEST_FOLDER))

    # 2. Создать подпапку
    # sub = create_folder(TEST_FOLDER, 'client_123')
    # print('Created folder:', sub['id'])

    # 3. Загрузить PDF (обновит если есть)
    # upload_file(TEST_FOLDER, Path('/tmp/visa.pdf'))

    # 4. Загрузить HTML как Google Doc
    # upload_html_as_gdoc(TEST_FOLDER, Path('/tmp/template.html'))

    # 5. Экспорт Google Doc в PDF / DOCX
    # pdf_bytes = export_gdoc('FILE_ID_OF_GDOC', 'pdf')
    # docx_bytes = export_gdoc('FILE_ID_OF_GDOC', 'docx')

def delete_item(folder_url_or_id: str, name: str = "") -> dict:
    """Удалить элемент Диска (папку или файл) по ссылке/идентификатору.

    Если задано name — удаляется элемент с таким именем внутри указанной папки.
    Возвращает {'ok': bool, 'deleted': [...], 'error': str}.
    """
    try:
        svc = _get_CLIENT()
    except Exception as e:
        return {"ok": False, "deleted": [], "error": "нет доступа на запись: %s" % str(e)[:120]}
    targets = []
    try:
        if name:
            parent = resolve_folder_id(folder_url_or_id)
            found = find_file_in_folder(parent, name)
            if not found:
                return {"ok": False, "deleted": [], "error": "не найдено: %s" % name}
            targets = [found["id"]]
        else:
            fid = resolve_folder_id(folder_url_or_id)
            targets = [fid]
        for fid in targets:
            svc.files().delete(fileId=fid, supportsAllDrives=True).execute()
        return {"ok": True, "deleted": targets, "error": ""}
    except Exception as e:
        return {"ok": False, "deleted": [], "error": str(e)[:200]}
