"""Сверка: текст нашего HTML-шаблона против текста настоящего оригинала.

Задача: HTML должен содержать тот же реальный текст, что и заполненный образец,
а данные клиента — только через {{переменные}}. Печатаем расхождения по шаблонам.
"""
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

ROOT = Path("/opt/wolf_v2/data/templates")


def norm(s: str) -> str:
    s = s.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def pdf_lines(path: Path) -> list:
    out = []
    d = pymupdf.open(path)
    for p in d:
        for b in p.get_text("blocks"):
            t = norm(b[4])
            if t:
                out.append(t)
    d.close()
    return out


def html_lines(path: Path) -> list:
    s = path.read_text(encoding="utf-8")
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<img[^>]*>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "\n", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return [norm(x) for x in s.split("\n") if norm(x)]


rows = D.q("""SELECT id, code, title FROM templates
              WHERE status NOT IN ('hidden','merged') ORDER BY COALESCE(doc_index, 999), id""")
print("шаблонов к проверке:", len(rows))
report = []
for r in rows:
    code = r["code"]
    tpl = ROOT / code / "template.html"
    ex = ROOT / code / "example_filled.pdf"
    if not tpl.exists() or not ex.exists():
        report.append((code, r["title"], "нет файла", 0, []))
        continue
    ref = pdf_lines(ex)
    ours = html_lines(tpl)
    our_text = " || ".join(ours)
    missing = [x for x in ref if x not in our_text and len(x) > 12]
    # строки шаблона, которых нет в оригинале (выдуманный текст), без учёта переменных
    extra = [x for x in ours if "{{" in x]
    extra = [re.sub(r"\{\{[^}]+\}\}", "…", x) for x in extra]
    extra = [x for x in extra if x.replace("…", "").strip(" .,:;") and x not in " || ".join(ref)]
    share = 100.0 * (len(ref) - len(missing)) / max(1, len(ref))
    report.append((code, r["title"], len(ref), share, missing[:3]))

print()
for code, title, total, share, samples in report:
    if total == "нет файла":
        print("%-38s %s" % (code, "нет template.html или example_filled.pdf"))
        continue
    flag = "OK " if share >= 97 else "!! "
    print("%s%-38s блоков эталона %3d | совпало %5.1f%%" % (flag, code, total, share))
    for s in samples:
        print("        нет в шаблоне: %s" % s[:96])
