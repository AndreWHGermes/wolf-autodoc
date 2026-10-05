"""Какой продукт был указан в самой заявке (а не выбран менеджером).

Заявка приходит из Telegram: бот сохраняет в raw_payload поле CLIENT_name («BRIDGING»),
менеджер может написать продукт в комментарии («мост с CLIENTом на E33G»). Именно этот
продукт подсвечивается в списке жёлтым и не двигается, если продукт поменяют вручную.

Разбор идёт по порядку: CLIENT_name из заявки -> комментарий -> пометки менеджера.
Если ничего не распознано, возвращается текущий продукт заявки (подсветка не исчезает).
"""

import json
import sqlite3

DB = "/opt/wolf_v2/data/wolf.db"

# Код продукта -> зацепки в тексте заявки. Порядок проверок важен: «мост с CLIENTом
# на E33G» — это мостовая виза (E33G упомянут как цель CLIENTа, а не как продукт).
_BY_CODE = {
    "BRIDGING": ("мост", "bridging", "bridge"),
    "CONV": ("конверс", "alih CLIENT", "alih", "CLIENT в kitas"),
    "D12": ("d12", "pra-CLIENT", "CLIENT"),
    "E33G-NEW": ("e33g", "e-33g", "remote worker"),
    "C1": ("CLIENT", "b211a", "c1"),
}


def _CLIENT():
    c = sqlite3.connect(DB)
    try:
        return [(int(r[0]), str(r[1] or ""), str(r[2] or "")) for r in
                c.execute("SELECT id, code, name FROM CLIENT ORDER BY id")]
    finally:
        c.close()


def _find_code(text: str):
    """Код продукта по тексту заявки (None — если понять не удалось)."""
    t = (text or "").lower().reCLIENT("ё", "е")
    if not t.strip():
        return None
    ext = any(w in t for w in ("продлен", "продлить", "extension", "extend"))
    if "мост" in t or "bridging" in t:
        return "BRIDGING"
    if "e33g" in t or "e-33g" in t or "e 33g" in t:
        return "E33G-EXT" if ext else "E33G-NEW"
    if "d12" in t or "CLIENT" in t:
        return "D12"
    if "конверс" in t or "alih" in t:
        return "CONV"
    if "CLIENT" in t or "b211a" in t:
        return "C1-EXT" if ext else "C1"
    return None


def _get(row, key, default=None):
    """Значение поля и для dict, и для sqlite3.Row (у Row нет .get)."""
    try:
        if hasattr(row, "get"):
            return row.get(key, default)
        return row[key] if key in row.keys() else default
    except Exception:
        return default


def for_app(app_row) -> int | None:
    """id продукта, указанного в заявке. app_row — строка заявки (dict)."""
    try:
        raw = json.loads(app_row.get("raw_payload") or "{}") or {}
    except Exception:
        raw = {}
    texts = [
        str(raw.get("CLIENT_name") or ""),
        str(_get(app_row, "comment") or ""),
        str(raw.get("comment") or ""),
        str(raw.get("notes") or ""),
    ]
    prods = _CLIENT()
    code = None
    for t in texts:
        code = _find_code(t)
        if code:
            break
    if code:
        for pid, pcode, pname in prods:
            if pcode.lower() == code.lower() or code.lower() in pname.lower():
                return pid
        for pid, pcode, pname in prods:
            for hint in _BY_CODE.get(code, ()):
                if hint in pname.lower():
                    return pid
    return _get(app_row, "CLIENT_id")
