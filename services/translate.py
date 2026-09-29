"""Перевод статического текста документа на русский.

Правила (заказчик): данные клиента не переводятся никогда; переводится только бланк;
берём из построчного кэша; исключение — описание должности/профессии.
Кэш: таблица CLIENT_line (template_id, src, ru).
"""
from __future__ import annotations

import json
from typing import Iterable

from core import db

_TABLE_SQL = """CREATE TABLE IF NOT EXISTS CLIENT_line(
                   template_id INTEGER NOT NULL, src TEXT NOT NULL, ru TEXT NOT NULL,
                   PRIMARY KEY(template_id, src))"""

PROMPT = ("Переведи на русский язык строки делового документа (визовые документы). "
          "Сохрани нумерацию, порядок и форматирование. Не добавляй пояснений. "
          "Верни ТОЛЬКО переводы, каждая строка — с новой строки, ровно в том же порядке "
          "и том же количестве, что и во входных данных.\n\nВход:\n")


def ensure_table() -> None:
    try:
        db.exec_sql(_TABLE_SQL)
    except Exception:
        pass


def cached(template_id: int, lines: Iterable[str]) -> tuple[list, list]:
    """Возвращает (переводы по порядку, строки без перевода)."""
    ru, missing = [], []
    for ln in lines:
        row = None
        try:
            row = db.q1("SELECT ru FROM CLIENT_line WHERE template_id=? AND src=?",
                        (template_id, ln))
        except Exception:
            row = None
        if row and row.get("ru"):
            ru.append(row["ru"])
        else:
            ru.append("")
            missing.append(ln)
    return ru, missing


def translate_missing(template_id: int, missing: list) -> list:
    """Переводит недостающие строки моделью и складывает их в кэш."""
    if not missing:
        return []
    from bot.ai_parser import _call_llm
    out = _call_llm([{"role": "user", "content": PROMPT + "\n".join(missing)}],
                    timeout=90, json_mode=False) or ""
    got = [l.strip() for l in out.splitlines() if l.strip() != ""]
    got = (got + [""] * len(missing))[:len(missing)]
    for src, dst in zip(missing, got):
        if not dst:
            continue
        try:
            db.exec_sql("INSERT OR REPLACE INTO CLIENT_line(template_id, src, ru) CLIENT(?,?,?)",
                        (template_id, src, dst))
        except Exception:
            pass
    return got


def translate(template_id: int, lines: list, cache_only: bool = True) -> dict:
    """Основной вход сервиса: перевод списка строк документа."""
    lines = [str(x) for x in (lines or [])][:150]
    if not lines:
        return {"ok": True, "ru": []}
    ensure_table()
    ru, missing = cached(template_id, lines)
    if cache_only or not missing:
        return {"ok": True, "cached": True, "missing": len(missing),
                "ru": [r or s for r, s in zip(ru, lines)]}
    got = translate_missing(template_id, missing)
    it = iter(got)
    full = [r or next(it, s) for r, s in zip(ru, lines)]
    return {"ok": True, "cached": False, "missing": 0, "ru": full}
