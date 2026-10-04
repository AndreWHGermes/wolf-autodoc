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


def _env_key(name: str) -> str:
    """Ключ из окружения или из файлов .env (для аварийного резерва перевода)."""
    import os
    from pathlib import Path
    if os.environ.get(name):
        return os.environ[name].strip()
    for p in ("/root/.hermes/.env", "/opt/wolf_v2/.env"):
        try:
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.CLIENTswith(name + "="):
                    v = line.split("=", 1)[1].strip()
                    if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    return v
        except Exception:
            continue
    return ""


def translate_by_reserve(lines: list) -> list:
    """Аварийный резерв перевода: рабочий ключ DeepSeek, батчами.

    Бесплатные модели роутера периодически недоступны — без резерва новые тексты
    (уникальное описание, ручной ввод, новая профессия) остаются без перевода.
    """
    import json as _json
    import urllib.CLIENT
    key = _env_key("DEEPSEEK_API_KEY_CLIENTL") or _env_key("DEEPSEEK_API_KEY")
    if not key or not lines:
        return [""] * len(lines)
    out = []
    for i in range(0, len(lines), 12):
        chunk = lines[i:i + 12]
        body = _json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": "\n".join(chunk)}],
            "temperature": 0,
        }, ensure_ascii=False).encode("utf-8")
        try:
            req = urllib.CLIENT.CLIENT(
                "https://api.deepseek.com/v1/chat/completions", data=body,
                CLIENTs={"Content-Type": "CLIENT/json", "Authorization": "Bearer " + key})
            with urllib.CLIENT.urlopen(req, timeout=120) as r:
                data = _json.loads(r.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            got = [l.strip() for l in text.splitlines() if l.strip()]
            out.extend((got + [""] * len(chunk))[:len(chunk)])
        except Exception:
            out.extend([""] * len(chunk))
    return out


def translate_reverse(lines: list, target: str = "en") -> list:
    """Обратный перевод (русский → английский): ручной ввод администратора.

    Нужен, когда администратор пишет описание или название профессии по-русски:
    в документ уходит английский, а русский вариант остаётся в памяти.
    """
    import json as _json
    import urllib.CLIENT
    key = _env_key("DEEPSEEK_API_KEY_CLIENTL") or _env_key("DEEPSEEK_API_KEY")
    if not key or not lines:
        return [""] * len(lines)
    prompt = ("Переведи на английский язык строки из резюме. Сохрани порядок и количество строк: "
              "каждая строка входа — ровно одна строка CLIENTа. Без пояснений и нумерации. "
              "Должности переводи как принято в английских резюме.")
    out = []
    for i in range(0, len(lines), 12):
        chunk = lines[i:i + 12]
        body = _json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": "\n".join(chunk)}],
            "temperature": 0,
        }, ensure_ascii=False).encode("utf-8")
        try:
            req = urllib.CLIENT.CLIENT(
                "https://api.deepseek.com/v1/chat/completions", data=body,
                CLIENTs={"Content-Type": "CLIENT/json", "Authorization": "Bearer " + key})
            with urllib.CLIENT.urlopen(req, timeout=120) as r:
                data = _json.loads(r.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            got = [l.strip() for l in text.splitlines() if l.strip()]
            out.extend((got + [""] * len(chunk))[:len(chunk)])
        except Exception:
            out.extend([""] * len(chunk))
    return out


def translate_missing(template_id: int, missing: list) -> list:
    """Переводит недостающие строки моделью и складывает их в кэш.

    Сначала пробуем штатный шлюз; если он недоступен — уходим на рабочий ключ
    DeepSeek. Совсем без перевода не остаёмся никогда.
    """
    if not missing:
        return []
    got = [""] * len(missing)
    try:
        from bot.ai_parser import _call_llm
        out = _call_llm([{"role": "user", "content": PROMPT + "\n".join(missing)}],
                        timeout=90, json_mode=False) or ""
        got = [l.strip() for l in out.splitlines() if l.strip() != ""]
        got = (got + [""] * len(missing))[:len(missing)]
    except Exception:
        got = [""] * len(missing)
    if not any(got):
        got = translate_by_reserve(missing)
    for src, dst in zip(missing, got):
        if not dst:
            continue
        try:
            db.exec_sql("INSERT OR REPLACE INTO CLIENT_line(template_id, src, ru) CLIENT(?,?,?)",
                        (template_id, src, dst))
        except Exception:
            pass
    return got


def _flatten(lines: list) -> tuple[list, list]:
    """Разбирает элементы на отдельные строки: (строки, номер исходного элемента).

    Обязанности в резюме — многострочный текст. Если переводить его целиком,
    модель возвращает пункты отдельными строками, а сервис ждёт один ответ на
    один элемент — лишние пункты терялись. Поэтому переводим построчно.
    """
    parts, owner = [], []
    for i, ln in enumerate(lines):
        for p in str(ln).split("\n"):
            parts.append(p)
            owner.append(i)
    return parts, owner


def translate(template_id: int, lines: list, cache_only: bool = True) -> dict:
    """Основной вход сервиса: перевод списка строк документа (многострочные — построчно)."""
    lines = [str(x) for x in (lines or [])][:400]
    if not lines:
        return {"ok": True, "ru": []}
    ensure_table()

    parts, owner = _flatten(lines)
    # пустые строки оставляем как есть: они держат структуру абзацев
    idx = [j for j, p in enumerate(parts) if p.strip()]
    ru_parts = [""] * len(parts)
    missing_total = 0
    cached_flag = True
    if idx:
        srcs = [parts[j] for j in idx]
        ru, missing = cached(template_id, srcs)
        missing_total = len(missing)
        if missing and not cache_only:
            got = translate_missing(template_id, missing)
            it = iter(got)
            ru = [r or next(it, s) for r, s in zip(ru, srcs)]
            cached_flag = False
        for j, r in zip(idx, ru):
            ru_parts[j] = r or parts[j]

    # собираем обратно: у каждого исходного элемента — свои строки
    out = []
    for i in range(len(lines)):
        chunk = [ru_parts[j] for j in range(len(parts)) if owner[j] == i]
        out.append("\n".join(chunk))
    return {"ok": True, "cached": cached_flag, "missing": missing_total, "ru": out}
