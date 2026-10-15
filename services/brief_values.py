"""Свободный комментарий заявки как логическое значение при сборке документов.

Менеджер вписывает в карточку заявки текст вида

    Должность: артист-продюсер (Artist / Producer)
    Сфера: кинопроизводство, музыка

и сборка документов берёт из него должность клиента и подбирает организацию
подходящей сферы деятельности (вместо компании из общего списка).

Правило: то, что вписано руками в заявку, главнее автоподбора — но только если
значение не закреплено в самом документе (там его правил человек).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

DB = Path("/opt/wolf_v2/data/wolf.db")
POOL = Path("/opt/wolf_v2/data/employer_pool.json")

# Сфера деятельности → ключевые слова, по которым ищем организацию в пуле.
# Организация для договора обязана быть вне Индонезии (правило заказчика).
SPHERE_HINTS: dict[str, list[str]] = {
    "продюс": ["pickup film", "unit five", "super mario"],
    "артист": ["pickup film", "unit five"],
    "кино": ["pickup film", "unit five"],
    "музык": ["pickup film", "super mario"],
    "медиа": ["pickup film", "unit five", "technopetchat"],
    "видео": ["pickup film", "unit five"],
    "сми": ["pickup film", "unit five"],
    "креатив": ["pickup film", "unit five"],
}

# Английские названия должностей: как их печатать в документах.
POSITION_EN = {
    "артист-продюсер": "Artist / Producer",
    "артист продюсер": "Artist / Producer",
    "продюсер": "Producer",
    "креативный продюсер": "Creative Producer",
    "артист": "Artist",
    "музыкант": "Musician",
    "режиссер": "Director",
    "режиссёр": "Director",
    "дизайнер": "Designer",
    "маркетолог": "Marketing Specialist",
}

FIELD_RE = re.compile(r"(должность|профессия|position)\s*[:\-]\s*([^\n;.]+)", re.IGNORECASE)
SPHERE_RE = re.compile(r"(сфера|отрасль|sphere|industry)\s*[:\-]\s*([^\n;.]+)", re.IGNORECASE)


def read_brief(app_id: int) -> str:
    """Комментарий заявки для сборки: поле brief, затем текст заявки, затем профессия.

    Источники по старшинству:
      1) отдельное поле комментария сборки (brief) — его правит менеджер в карточке;
      2) текст заявки (comment) — то, что написал менеджер в боте;
      3) профессия заявки: поле position, а если его нет — из пометок (notes) и карточки клиента.
    Должность, указанная в заявке, должна работать без ручного переноса в отдельное поле.
    """
    if not app_id:
        return ""
    try:
        c = sqlite3.connect(str(DB))
        c.row_factory = sqlite3.Row
        row = c.execute("""SELECT a.brief, a.comment, a.raw_payload, cl.position AS cpos
                             FROM applications a LEFT JOIN clients cl ON cl.id = a.client_id
                            WHERE a.id=?""", (app_id,)).fetchone()
        c.close()
        if not row:
            return ""
        brief = str(row["brief"] or "").strip()
        comment = str(row["comment"] or "").strip()
        # Заявка может содержать и текст, и отдельное поле профессии: в тексте должности
        # часто нет («ITK до 11 октября»), а в поле position — есть. Поэтому источники
        # объединяем, а не заменяем друг другом.
        parts = [p for p in (brief, comment) if p]
        try:
            rp = json.loads(row["raw_payload"] or "{}")
        except Exception:
            rp = {}
        for val in (str(rp.get("position") or rp.get("profession") or "").strip(),
                    str(rp.get("notes") or "").strip(),
                    str(row["cpos"] or "").strip()):
            if val and all(val not in p for p in parts):
                parts.append(val)
        return "; ".join(parts)
    except Exception:
        return ""


def parse_position(brief: str) -> tuple[str, str]:
    """Из комментария — должность: (как вписал менеджер, как печатать по-английски)."""
    m = FIELD_RE.search(brief or "")
    if not m:
        return "", ""
    raw = m.group(2).strip(" .,;")
    # в скобках менеджер обычно уже даёт английский вариант — берём его
    inside = re.search(r"\(([^)]+)\)", raw)
    en = inside.group(1).strip() if inside else ""
    ru = re.sub(r"\([^)]*\)", "", raw).strip(" .,;")
    if not en:
        low = ru.lower()
        for key, val in POSITION_EN.items():
            if key in low:
                en = val
                break
    return ru, en


def parse_sphere(brief: str) -> str:
    m = SPHERE_RE.search(brief or "")
    return m.group(2).strip(" .,;") if m else ""


def _pool_items() -> list[dict]:
    try:
        data = json.loads(POOL.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data if isinstance(data, list) else (data.get("employers") or data.get("items") or [])
    return [x for x in items if isinstance(x, dict)]


def pick_employer_by_sphere(brief: str) -> dict:
    """Организация подходящей сферы из пула: для артиста-продюсера — кинопродакшн."""
    text = (brief or "").lower()
    if not text:
        return {}
    want: list[str] = []
    for key, names in SPHERE_HINTS.items():
        if key in text:
            for n in names:
                if n not in want:
                    want.append(n)
    if not want:
        return {}
    items = _pool_items()
    for needle in want:
        for rec in items:
            title = str(rec.get("name") or "").lower()
            if needle in title:
                return rec
    return {}


def employer_variables(rec: dict) -> dict:
    """Реквизиты организации в переменные договора (шапка и подвал — одна запись)."""
    if not rec:
        return {}
    from services import employer_pool as _emp
    try:
        return _emp.values_of(rec) or {}
    except Exception:
        return {}
