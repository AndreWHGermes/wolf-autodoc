"""Границы легенды по архиву: фирмы, должности, доход, стаж, срок контракта.

Читает изготовленные договоры (Remote Work Agreement / Employment Contract)
из кэша Google Диска и из Word-документов заказчика, вытаскивает ключевые
значения и показывает границы, в которых эти значения варьируются.
"""
import re
import zipfile
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
SOURCES = list((ROOT / "data" / "gdrive_cache").rglob("*")) + \
    list((ROOT / "data" / "word_templates").rglob("*"))


def text_of(p: Path) -> str:
    try:
        if p.suffix.lower() == ".docx":
            z = zipfile.ZipFile(p)
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
            z.close()
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))
        if p.suffix.lower() == ".pdf":
            import pymupdf
            d = pymupdf.open(str(p))
            t = "".join(pg.get_text() for pg in d)
            d.close()
            return re.sub(r"\s+", " ", t)
    except Exception:                                          # noqa: BLE001
        return ""
    return ""


def is_contract(txt: str) -> bool:
    low = txt.lower()
    return ("remote work agreement" in low or "employment contract" in low
            or "трудовой договор" in low)


MONEY = re.compile(r"(?:USD|US\$|\$)\s?([\d][\d ,\.]{2,})|([\d][\d ,\.]{3,})\s?(?:USD|US\$)")
PERIOD = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})")
FIRM = re.compile(r"(?:OOO|LLC|LTD|L\.L\.C|JSC|PJSC|ООО|АО|ОАО|ЗАО|Inc\.?|GmbH|B\.?V\.?|S\.?L\.?|Co\.?)[\s\"«»']*[A-ZА-Я][^,.;\n]{2,60}")

# --- поля легенды в изготовленном договоре (формулировки шаблона) -----------
SIGNED = re.compile(r"made on this\s+(\d{1,2})(?:st|nd|rd|th)?\s+day of\s+([A-Za-z]+)\s+(\d{4})")
SERVICE = re.compile(r"incorporating\s+([a-z\-]+|\d+)\s+years? of service", re.I)
VALID = re.compile(r"shall remain valid until\s+(\d{1,2})(?:st|nd|rd|th)?\s+day of\s+"
                   r"([A-Za-z]+)\s+(\d{4})", re.I)
ANNUAL = re.compile(r"RUB\s*([\d][\d ,]{4,}?)\s*\([^)]*\)\s*per annum", re.I)
MONTHLY = re.compile(r"RUB\s*([\d][\d ,]{4,}?)\s*\([^)]*\)\s*per month", re.I)
POSITION = re.compile(r"engages the Contractor as an?\s+([^,.]{3,70}?)(?:,|\s+to provide)", re.I)
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def num(s):
    s = s.strip()
    if s.lower() in NUMWORDS:
        return NUMWORDS[s.lower()]
    try:
        return int(float(s.replace(",", "").replace(" ", "")))
    except ValueError:
        return None


def extract_legend(txt: str) -> dict:
    """Поля легенды из текста изготовленного договора."""
    out = {}
    m = SIGNED.search(txt)
    if m:
        out["подписан"] = "%s.%02d.%s" % (m.group(1), MONTHS.get(m.group(2)[:3].lower(), 0), m.group(3))
    m = SERVICE.search(txt)
    if m:
        out["стаж, лет"] = num(m.group(1))
    m = VALID.search(txt)
    if m:
        out["действует до"] = "%s.%02d.%s" % (m.group(1), MONTHS.get(m.group(2)[:3].lower(), 0), m.group(3))
    m = ANNUAL.search(txt)
    if m:
        out["доход, RUB/год"] = num(m.group(1))
    m = MONTHLY.search(txt)
    if m:
        out["доход, RUB/мес"] = num(m.group(1))
    m = POSITION.search(txt)
    if m:
        out["должность"] = m.group(1).strip()
    return out


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

rows = []
legends = []
for p in SOURCES:
    if not p.is_file() or p.name.startswith("~$") or p.suffix.lower() not in (".pdf", ".docx"):
        continue
    txt = text_of(p)
    if not txt or not is_contract(txt):
        continue
    kind = "RemoteWork" if "remote work agreement" in txt.lower() else "Employment"
    firms = [f.strip() for f in FIRM.findall(txt)][:4]
    leg = extract_legend(txt)
    if leg:
        leg["_file"] = "%s/%s" % (p.parent.name, p.name[:40])
        leg["_kind"] = kind
        legends.append(leg)
    rows.append((p.parent.name if p.parent.name.startswith("client_") else "word",
                 p.name[:44], kind, firms, [], [], []))

print("=== изготовленные договоры в архиве: %d шт." % len(rows))
for folder, name, kind, firms, money, term, dates in rows:
    print("\n  [%s] %s" % (folder, name))
    print("     тип: %s" % kind)
    print("     фирмы: %s" % (" | ".join(firms) if firms else "—"))
    print("     суммы: %s" % (" | ".join(money) if money else "—"))
    print("     срок: %s" % (" | ".join("%s %s" % t for t in term) if term else "—"))
    print("     даты: %s" % (" | ".join(dates) if dates else "—"))

# --- границы легенды ---
print()
print("=== ГРАНИЦЫ ЛЕГЕНДЫ (по %d изготовленным договорам)" % len(legends))
fields = ["стаж, лет", "доход, RUB/год", "доход, RUB/мес", "должность"]
for f in fields:
    vals = [l[f] for l in legends if l.get(f)]
    if not vals:
        continue
    nums = [v for v in vals if isinstance(v, int)]
    if nums:
        print("  %-16s значений %d, диапазон %s … %s" % (f, len(vals), f"{min(nums):,}", f"{max(nums):,}"))
    else:
        from collections import Counter
        print("  %-16s значений %d, топ: %s" % (
            f, len(vals), ", ".join("%s×%d" % (v[:38], n) for v, n in Counter(vals).most_common(4))))

print()
print("=== срок действия (подписан → действует до) у 15 договоров подряд")
shown = 0
for l in legends:
    if "подписан" in l and "действует до" in l and shown < 15:
        print("  %-42s %s → %s  стаж %s, доход %s/год" % (
            l["_file"][:42], l["подписан"], l["действует до"],
            l.get("стаж, лет", "—"), l.get("доход, RUB/год", "—")))
        shown += 1

print()
print("=== фирмы-работодатели в договорах")
from collections import Counter
allfirm = [f for r in rows for f in r[3]]
for f, n in Counter([f.split(" REMOTE")[0].strip()[:52] for f in allfirm]).most_common(20):
    print("  %-52s %d" % (f, n))
