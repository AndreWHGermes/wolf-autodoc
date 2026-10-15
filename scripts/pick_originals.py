"""Подбор и установка настоящих эталонов для шаблонов Wolf.

Ищет в data/gdrive_cache/client_*/ настоящие документы клиентов и раскладывает их
как эталоны (data/templates/<code>/example_filled.pdf) с фиксацией в data/originals.

Запуск:
  /usr/bin/python3 /opt/wolf_v2/scripts/pick_originals.py            # показать кандидатов
  /usr/bin/python3 /opt/wolf_v2/scripts/pick_originals.py --apply    # установить
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

import pymupdf  # noqa: E402

BASE = Path("/opt/wolf_v2")
CACHE = BASE / "data" / "gdrive_cache"
TPL = BASE / "data" / "templates"

# Кандидаты: шаблон → (подстрока банка, признак периода, тип)
RULES = {
    # (банк, сколько страниц считать «своим» форматом, тип)
    "bank_statement_3m__tbank": ("tbank", "short", "bank"),
    "bank_statement_12m__tbank": ("tbank", "long", "bank"),
    "bank_statement_3m__sber": ("sber", "short", "bank"),
    "bank_statement_12m__sber": ("sber", "long", "bank"),
    "cv__format_short": (None, "short", "cv_short"),
    "cv__format_detailed": (None, "long", "cv_long"),
}


def pages_of(path: Path) -> int:
    try:
        d = pymupdf.open(path)
        n = d.page_count
        d.close()
        return n
    except Exception:
        return 0


def text_of(path: Path, pages: int = 2) -> str:
    try:
        d = pymupdf.open(path)
        t = "\n".join((d[i].get_text() or "") for i in range(min(pages, d.page_count)))
        d.close()
        return t
    except Exception:
        return ""


def scan():
    docs = []
    for f in sorted(CACHE.glob("client_*/*.pdf")):
        t = text_of(f, 3)
        low = t.lower()
        docs.append({"path": f, "text": t, "low": low,
                     "name": f.name.lower(),
                     "bank": "tbank" if ("tbank" in low or "t-bank" in low or "khutorskaya" in low) else
                             ("sber" if ("sber" in low or "vavilova" in low) else ""),
                     "pages": pages_of(f)})
    return docs


def candidates(code: str, docs: list) -> list:
    bank, size, kind = RULES[code]
    out = []
    for d in docs:
        low, name, pages = d["low"], d["name"], d["pages"]
        if kind == "bank":
            if bank and d["bank"] != bank:
                continue
            if size == "short" and pages > 2:
                continue
            if size == "long" and pages < 3:
                continue
            out.append(d)
        elif kind == "cv_short":
            if ("resume" in name or "cv" in name) and len(d["text"]) > 400 and pages <= 2:
                out.append(d)
        elif kind == "cv_long":
            if ("resume" in name or "cv" in name) and pages >= 2:
                out.append(d)
    # «короткие» справки — сначала те, где стоит доступный остаток за 3 месяца
    if size == "short" and kind == "bank":
        out.sort(key=lambda d: (0 if "available balance" in d["low"] or "3 month" in d["low"] else 1,
                                d["pages"]))
    else:
        out.sort(key=lambda d: -d["pages"] if kind == "bank" else 0)
    return out


APPLY = "--apply" in sys.argv
docs = scan()
print("просмотрено настоящих PDF в папках клиентов:", len(docs))
for code in RULES:
    cands = candidates(code, docs)
    cur = TPL / code / "example_filled.pdf"
    print("\n=== %s" % code)
    print("    сейчас: %s" % ("есть" if cur.exists() else "нет"))
    if not cands:
        print("    настоящих кандидатов не найдено")
        continue
    for d in cands[:4]:
        print("    кандидат: %s" % d["path"].relative_to(CACHE))
    if APPLY:
        src = cands[0]["path"]
        if cur.exists():
            shutil.copy2(cur, cur.with_suffix(".pdf.bak_" + datetime.now().strftime("%H%M%S")))
        shutil.copy2(src, cur)
        print("    установлен эталон: %s" % src.relative_to(CACHE))
print("\nрежим:", "применено" if APPLY else "только показ (добавь --apply)")
