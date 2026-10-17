"""Перевод статического текста документа на русский.

Правила (заказчик): данные клиента не переводятся никогда; переводится только бланк;
берём из построчного кэша; исключение — описание должности/профессии.
Кэш: таблица translation_line (template_id, src, ru).
"""
from __future__ import annotations

import json
import re
from typing import Iterable

from core import db

_TABLE_SQL = """CREATE TABLE IF NOT EXISTS translation_line(
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
            row = db.q1("SELECT ru FROM translation_line WHERE template_id=? AND src=?",
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
                if line.startswith(name + "="):
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
    import urllib.request
    key = _env_key("DEEPSEEK_API_KEY_ANDREYL") or _env_key("DEEPSEEK_API_KEY")
    if not key or not lines:
        return [""] * len(lines)
    out = []
    for i in range(0, len(lines), 12):
        chunk = lines[i:i + 12]
        body = _json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": PROMPT_FULL},
                         {"role": "user", "content": "\n".join(chunk)}],
            "temperature": 0,
        }, ensure_ascii=False).encode("utf-8")
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=120) as r:
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
    import urllib.request
    key = _env_key("DEEPSEEK_API_KEY_ANDREYL") or _env_key("DEEPSEEK_API_KEY")
    if not key or not lines:
        return [""] * len(lines)
    prompt = ("Переведи на английский язык строки из резюме. Сохрани порядок и количество строк: "
              "каждая строка входа — ровно одна строка выхода. Без пояснений и нумерации. "
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
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=120) as r:
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
        out = _call_llm([{"role": "user", "content": PROMPT_FULL + "\n".join(missing)}],
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
            db.exec_sql("INSERT OR REPLACE INTO translation_line(template_id, src, ru) VALUES(?,?,?)",
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


# ─── полный перевод документа целиком ────────────────────────────────────────
# Требование заказчика (06.10.2026): по кнопке должен переводиться ВЕСЬ документ
# (а не отдельные заготовки), чтобы его можно было прочитать по-русски целиком,
# и чтобы перевод не ломал вёрстку: разметка, координаты, шрифты остаются как есть,
# меняется только текст.

PROMPT_FULL = (
    "Ты переводишь документ на русский язык целиком — так, чтобы администратор прочитал его "
    "по-русски полностью. На входе — фрагменты документа, по одному на строку. Верни переводы "
    "в том же порядке и в том же количестве, каждая строка — с новой строки, без пояснений. "
    "ПЕРЕВОДИТСЯ ВСЁ: заголовки и названия полей, значения переменных, должности, даты (October 13, 1990 "
    "→ 13 октября 1990 г.), периоды (2022 – Present → 2022 – настоящее время), страны и города "
    "(Russian Federation → Российская Федерация, KAZAKHSTAN → Казахстан), вуз (Russian State University "
    "for the Humanities → Российский государственный гуманитарный университет), названия организаций "
    "(LLC \"PICKUP FILM\" → ООО «ПИКАП ФИЛЬМ»), имена людей латиницей → кириллицей (BUDKO OLEG → БУДКО ОЛЕГ), "
    "должности и описания, ссылки на разделы и пункты. "
    "БЕЗ ИЗМЕНЕНИЙ оставляй только то, что является идентификатором или кодом: номера паспортов, "
    "номер ИТК/KITAS, номера счетов и телефоны, адреса электронной почты, а также коды виз и продуктов "
    "(E33G, E-02, KITAS, ITAS, FORM E-02, METERAI) — их пиши латиницей как есть. "
    "НАЗВАНИЯ ПОЛЕЙ переводи коротко (2–4 слова): они печатаются в узкой колонке слева, и длинный "
    "перевод наезжает на значение справа. Например: «Stay permit number» → «Номер разрешения», "
    "«Current stay permit» → «Текущее разрешение». "
    "Сокращение «METERAI» и слово «FORM» не переводи. "
    "Абзацы внизу документа (заявления, заверения) переводи полностью, без сокращений.")
PROMPT_FULL_NO_NAMES = PROMPT_FULL

# Служебные блоки, которые не переводятся никогда.
_SKIP_TAGS = ("style", "script")
_ONLY_SYMBOLS = re.compile(r"^[\W\d_]+$", re.UNICODE)


def translate_lines_full(lines: list, template_id: int = 0, use_llm: bool = True) -> list:
    """Перевод списка строк: сначала кэш, затем модель (DeepSeek) — целиком, без потерь.

    Многострочные значения (перечень обязанностей в резюме) переводим ПОСТРОЧНО:
    если отдать модели строку с переводами строк внутри, она вернёт больше строк,
    чем дано, и переводы сдвигаются — часть текста уезжает в чужие блоки документа.
    """
    src = [str(x) for x in (lines or [])]
    out = list(src)
    if not src:
        return out
    ensure_table()
    # разбиваем каждое значение на строки и запоминаем, кому какая строка принадлежит
    parts, owner = [], []
    for i, s in enumerate(src):
        for p in s.split("\n"):
            parts.append(p)
            owner.append(i)
    idx = [j for j, p in enumerate(parts) if p.strip() and not _ONLY_SYMBOLS.match(p.strip())]
    if not idx:
        return out
    uniq, seen = [], set()
    for j in idx:
        p = parts[j]
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    got, missing = cached(template_id, uniq)
    pairs = {u: (g or "") for u, g in zip(uniq, got)}
    todo = [u for u in uniq if not pairs.get(u)]
    if todo and use_llm:
        got2 = translate_by_reserve(todo)
        for u, g in zip(todo, got2):
            if g:
                pairs[u] = g
                try:
                    db.exec_sql("INSERT OR REPLACE INTO translation_line (template_id, src, ru) VALUES (?,?,?)",
                                (template_id, u, g))
                except Exception:
                    pass
    # склейка обратно: строки каждого значения — на своём месте, в прежнем порядке
    res = ["\n".join(pairs.get(parts[j], parts[j]) if j in idx else parts[j]
                     for j in range(len(parts)) if owner[j] == i)
           for i in range(len(src))]
    return res


def translate_html_full(html: str, template_id: int = 0, use_llm: bool = True) -> dict:
    """Перевести документ целиком: весь видимый текст → русский, вёрстка без изменений.

    Разметка, координаты блоков, шрифты и цвета остаются прежними — меняются только
    текстовые узлы, поэтому печатный вид документа сохраняется 1:1.
    """
    import re as _re
    html = str(html or "")
    if not html:
        return {"ok": False, "error": "документ пуст", "html": "", "translated": 0, "total": 0}

    pieces = _re.split(r"(<[^>]+>)", html)
    skip_depth = 0
    texts, slots = [], []
    for i, part in enumerate(pieces):
        if part.startswith("<"):
            tag = _re.match(r"<\s*/?\s*([A-Za-z0-9]+)", part)
            name = (tag.group(1).lower() if tag else "")
            if name in _SKIP_TAGS:
                if part.startswith("</"):
                    skip_depth = max(0, skip_depth - 1)
                elif not part.endswith("/>"):
                    skip_depth += 1
            continue
        if skip_depth or not part.strip():
            continue
        texts.append(part)
        slots.append(i)

    if not texts:
        return {"ok": True, "html": html, "translated": 0, "total": 0}

    translated = translate_lines_full(texts, template_id=template_id, use_llm=use_llm)
    n = 0
    for slot, ru in zip(slots, translated):
        src = pieces[slot]
        if ru and ru != src:
            # сохраняем ведущие/замыкающие пробелы — они держат интервалы в вёрстке
            lead = src[:len(src) - len(src.lstrip())]
            tail = src[len(src.rstrip()):]
            pieces[slot] = lead + ru.strip() + tail
            n += 1
    out_html = "".join(pieces)
    # Жёсткое правило вёрстки: после перевода строки длиннее — блоки, вышедшие за
    # печатное поле листа, сужаются и переносятся автоматически (render.fit_width).
    try:
        from services.render import fit_width as _fit_width
        out_html = _fit_width(out_html)
    except Exception:
        pass
    return {"ok": True, "html": out_html, "translated": n, "total": len(texts)}
