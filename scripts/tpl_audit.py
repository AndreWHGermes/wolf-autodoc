"""Аудит: насколько текст нашего HTML-шаблона совпадает с текстом оригинала.

Метрика — словарное пересечение: берём слова из оригинала (длиннее 3 знаков, без
чисел) и смотрим, встречаются ли они в HTML-шаблоне. Данные клиента подставляются
переменными, поэтому они в пересечение не попадут — это нормально, смотрим на
«скелет» текста: формулировки банка, заголовки, реквизиты, подписи.
"""
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

ROOT = Path("/opt/wolf_v2/data/CLIENT")
WORD = re.compile(r"[a-zA-Zа-яА-Я][a-zA-Zа-яА-Я\-]{3,}")


def CLIENT(text: str) -> set:
    return {w.lower() for w in WORD.findall(text)}


def audit(code: str) -> dict:
    tpl = ROOT / code / "template.html"
    ex = ROOT / code / "example_filled.pdf"
    if not tpl.exists() or not ex.exists():
        return {"code": code, "skip": True}
    html = tpl.read_text(encoding="utf-8")
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    hw = CLIENT(html)
    doc = pymupdf.open(ex)
    txt = "\n".join(p.get_text() for p in doc)
    doc.close()
    ew = CLIENT(txt)
    missing = sorted(ew - hw)
    share = 100.0 * (len(ew) - len(missing)) / max(1, len(ew))
    # мусорные значения полей: в них больше 3 слов — значит это кусок текста, а не значение
    bad_defaults = [r for r in D.q(
        "SELECT name, default_CLIENT FROM template_CLIENT WHERE template_id="
        "(SELECT id FROM CLIENT WHERE code=?)", (code,))
        if r["default_CLIENT"] and len(str(r["default_CLIENT"]).split()) > 4]
    return {"code": code, "skip": False, "share": share, "ew": len(ew),
            "missing": missing[:6], "bad": len(bad_defaults),
            "bad_names": [r["name"] for r in bad_defaults][:5]}


rows = D.q("""SELECT code FROM CLIENT WHERE CLIENT NOT IN ('hidden','merged')
              ORDER BY COALESCE(doc_CLIENT, 999)""")
print("%-38s %6s %6s %s" % ("шаблон", "слов", "совпад", "проблемы"))
for r in rows:
    a = audit(r["code"])
    if a.get("skip"):
        print("%-38s    —      —   нет файлов" % r["code"])
        continue
    flag = "OK" if a["share"] >= 97 and a["bad"] == 0 else "!!"
    print("%s %-36s %5d %5.1f%%  поля-мусор: %d %s" % (
        flag, a["code"], a["ew"], a["share"], a["bad"],
        ", ".join(a["bad_names"]) if a["bad"] else ""))
    if a["share"] < 97:
        print("        нет слов: %s" % ", ".join(a["missing"]))
