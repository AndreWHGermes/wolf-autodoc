"""Дисковый кэш значений, которые дорого достаются из документов клиента.

Чтение документов клиента с распознаванием занимает 5-9 секунд на клиента.
Прогрев при старте держит это в памяти процесса, но после перезапуска сервиса
кэш пуст, и первый заход снова ждёт. Этот модуль хранит посчитанное на диске —
значение переживает перезапуск и общее для всех процессов.

Ключ — имя значения и идентификатор клиента, плюс подпись папки клиента
(имена, размеры, даты файлов): изменились файлы — значение пересчитается.
"""
import json
import time
from pathlib import Path
from threading import Lock

CACHE_PATH = Path("/opt/wolf_v2/data/value_cache.json")
_lock = Lock()
_data = None
_loaded_at = 0.0
_TTL = 300.0


def _load() -> dict:
    global _data, _loaded_at
    now = time.time()
    if _data is not None and now - _loaded_at < _TTL:
        return _data
    try:
        _data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(_data, dict):
            _data = {}
    except Exception:
        _data = {}
    _loaded_at = now
    return _data


def folder_signature(folder: Path):
    """Подпись папки: какие файлы и какого размера. Нет папки — None."""
    try:
        if not folder.exists():
            return None
        return sorted([f.name, f.stat().st_size, int(f.stat().st_mtime)]
                      for f in folder.iterdir() if f.is_file())
    except Exception:
        return None


def get(kind: str, client_id, signature) -> str:
    """Взять значение из дискового кэша. Пусто, если подпись не совпала."""
    if signature is None:
        return ""
    with _lock:
        data = _load()
    rec = data.get("%s:%s" % (kind, client_id))
    if isinstance(rec, dict) and rec.get("sig") == signature:
        return rec.get("val") or ""
    return ""


def put(kind: str, client_id, signature, value: str) -> None:
    """Сохранить значение вместе с подписью папки."""
    if signature is None:
        return
    with _lock:
        data = _load()
        data["%s:%s" % (kind, client_id)] = {"sig": signature, "val": value or "",
                                             "at": int(time.time())}
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(CACHE_PATH)
        except Exception:
            pass


def flush() -> int:
    """Забыть кэш (например, после полного сканирования Drive)."""
    global _data, _loaded_at
    with _lock:
        _data = {}
        _loaded_at = time.time()
        try:
            CACHE_PATH.unlink(missing_ok=True)
        except Exception:
            pass
    return 0
