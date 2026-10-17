"""Доступ к Google Диску от имени сервисного аккаунта (робота).

Ключ робота лежит в data/google_service_account.json. Пока ключа нет — модуль
сообщает, что доступ не настроен, и система работает по старой схеме (по ссылке).
С ключом система ходит на Диск авторизованно: лимиты в тысячи раз выше,
отказов «many accesses» нет, папки видны все, которым дан доступ роботу.

Права робота:
- Чтение: drive.readonly (текущий SCOPES)
- Запись: drive.file — см. gdrive_write.py для upload/create/update/export
"""
import io
import re
from pathlib import Path

KEY_FILE = Path('/opt/wolf_v2/data/google_service_account.json')
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Для записи используй gdrive_write.py (scope drive.file)
# from services.gdrive_write import upload_file, create_folder, export_gdoc, ...

# что Google отдаёт не файлом, а форматом — экспортируем в понятный вид
GOOGLE_EXPORT = {
    'application/vnd.google-apps.document': ('application/pdf', '.pdf'),
    'application/vnd.google-apps.spreadsheet': ('application/pdf', '.pdf'),
    'application/vnd.google-apps.presentation': ('application/pdf', '.pdf'),
}

_svc = None


def available() -> bool:
    """Настроен ли доступ через робота."""
    return KEY_FILE.is_file()


def email() -> str:
    """Адрес робота — его нужно вписать в доступ к папке на Диске."""
    if not available():
        return ''
    try:
        import json
        return (json.loads(KEY_FILE.read_text(encoding='utf-8')) or {}).get('client_email', '')
    except Exception:
        return ''


def service():
    """Клиент Google Drive API (создаётся один раз)."""
    global _svc
    if _svc is None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            str(KEY_FILE), scopes=SCOPES)
        _svc = build('drive', 'v3', credentials=creds, cache_discovery=False)
    return _svc


def folder_id(url: str) -> str:
    """Идентификатор папки Google Диска — из ссылки или из самого идентификатора.

    Раньше принималась только ссылка: если сюда попадал уже идентификатор папки,
    функция возвращала пустую строку, и папка выглядела пустой — документы клиента
    «исчезали» (список файлов выходил пустым, заявка оставалась без данных).
    """
    m = re.search(r'/folders/([A-Za-z0-9_\-]+)', url or '')
    if m:
        return m.group(1)
    s = (url or '').strip()
    if re.fullmatch(r'[A-Za-z0-9_\-]{10,}', s):
        return s
    return ''


_LIST_CACHE = {}


def list_files(folder_url: str, deep: bool = True) -> list:
    """Файлы папки клиента: [{id, name, mime, size, path}] — с обходом подпапок.

    Список кэшируется на 2 минуты: страница заявки и модалка готовых документов
    запрашивали Диск по несколько раз за открытие, из-за чего страница грузилась
    по 15 секунд (Андрей, 17.10.2026).
    """
    import time as _t
    _key = (folder_url, bool(deep))
    _hit = _LIST_CACHE.get(_key)
    if _hit and (_t.time() - _hit[0]) < 120:
        return [dict(x) for x in _hit[1]]
    _res = _list_files_uncached(folder_url, deep)
    _LIST_CACHE[_key] = (_t.time(), [dict(x) for x in _res])
    return _res


def _list_files_uncached(folder_url: str, deep: bool = True) -> list:
    out = []
    svc = service()
    root = folder_id(folder_url)
    if not root:
        return out

    def walk(fid, prefix=''):
        page = None
        while True:
            resp = svc.files().list(
                q=f"'{fid}' in parents and trashed=false",
                fields='nextPageToken, files(id,name,mimeType,size)',
                pageSize=200, pageToken=page).execute()
            for f in resp.get('files', []):
                if f['mimeType'] == 'application/vnd.google-apps.folder':
                    if deep:
                        walk(f['id'], prefix + f['name'] + '/')
                    continue
                out.append({'id': f['id'], 'name': f['name'], 'mime': f['mimeType'],
                            'size': int(f.get('size') or 0), 'path': prefix + f['name']})
            page = resp.get('nextPageToken')
            if not page:
                break

    walk(root)
    return out


def download(file_id: str, dest: Path) -> bool:
    """Скачивает файл папки клиента (или экспортирует Google-документ в PDF)."""
    from googleapiclient.http import MediaIoBaseDownload
    svc = service()
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = svc.files().get(fileId=file_id, fields='mimeType,name').execute()
    mime = meta.get('mimeType') or ''
    try:
        if mime in GOOGLE_EXPORT:
            exp, ext = GOOGLE_EXPORT[mime]
            data = svc.files().export(fileId=file_id, mimeType=exp).execute()
            dest = dest.with_suffix(ext)
            dest.write_bytes(data)
        else:
            req = svc.files().get_media(fileId=file_id)
            with io.FileIO(str(dest), 'wb') as fh:
                dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
                done = False
                while not done:
                    _, done = dl.next_chunk()
        ok = dest.is_file() and dest.stat().st_size > 0
        if ok:
            # На Диске файлы бывают без расширения: «PASSPORT - VITALII SURKOV» — это PDF.
            # Без расширения парсеры не понимают формат и паспорт не читается, поэтому рядом
            # кладём тот же файл с правильным расширением, определённым по первым байтам.
            try:
                _known = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.docx', '.doc',
                          '.rtf', '.txt', '.zip', '.xlsx', '.svg', '.gif', '.bmp', '.tif', '.tiff')
                if dest.suffix.lower() not in _known:
                    with open(dest, 'rb') as _fh:
                        _head = _fh.read(12)
                    _ext = None
                    if _head[:4] == b'%PDF':
                        _ext = '.pdf'
                    elif _head[:2] == b'\xff\xd8':
                        _ext = '.jpg'
                    elif _head[:4] == b'\x89PNG':
                        _ext = '.png'
                    elif _head[:4] == b'RIFF' and _head[8:12] == b'WEBP':
                        _ext = '.webp'
                    elif _head[:2] == b'PK':
                        _ext = '.docx'
                    if _ext:
                        _twin = dest.with_suffix(_ext)
                        if _twin.exists():
                            # копия уже есть — исходник без расширения лишний
                            try:
                                dest.unlink()
                            except Exception:                  # noqa: BLE001
                                pass
                        else:
                            # Переименовываем, а не копируем: две копии одного
                            # документа (с расширением и без) показывались в заявке
                            # как задвоение файлов клиента.
                            dest.replace(_twin)
                        dest = _twin
            except Exception:                      # noqa: BLE001
                pass
            # Фото с телефона весят 3–6 МБ. Сразу после скачивания облегчаем
            # снимок и готовим превью — тогда заявка открывается мгновенно,
            # и полный снимок на сервере не хранится (см. services/previews.py).
            try:
                from services import previews
                if dest.suffix.lower() in previews.IMAGE_EXT:
                    kind = ""
                    try:
                        from scripts.drive_scan import doc_kind_name
                        kind = doc_kind_name(str(dest), "")
                    except Exception:
                        kind = ""
                    previews.process_client_image(dest, kind)
            except Exception:
                pass
        return ok
    except Exception:
        return False


def sync_folder(folder_url: str, dest_dir: Path) -> int:
    """Скачивает всю папку клиента целиком. Возвращает число файлов."""
    got = 0
    for f in list_files(folder_url):
        safe = f['path'].replace('/', '__')
        if download(f['id'], dest_dir / safe):
            got += 1
    return got
