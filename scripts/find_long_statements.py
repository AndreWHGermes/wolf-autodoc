"""Поиск настоящих банковских справок за длинный период (около 12 месяцев) в кэше клиентов."""
import re
import sys
from datetime import datetime
from pathlib import Path

import pymupdf

CACHE = Path("/opt/wolf_v2/data/gdrive_cache")
rows = []
for f in sorted(CACHE.rglob("*.pdf")):
    try:
        d = pymupdf.open(f)
        if d.page_count > 3:          # многостраничные выписки движений не нужны
            d.close()
            continue
        t = "\n".join(p.get_text() or "" for p in d)
        prod = (d.metadata or {}).get("producer") or ""
        d.close()
    except Exception:
        continue
    low = t.lower()
    if "deposit balance" not in low and "available balance" not in low:
        continue
    dates = re.findall(r"(\d{2}\.\d{2}\.\d{4})", t)
    days = None
    if len(dates) >= 2:
        try:
            a = datetime.strptime(dates[-2], "%d.%m.%Y")
            b = datetime.strptime(dates[-1], "%d.%m.%Y")
            days = abs((b - a).days)
        except Exception:
            pass
    bank = "tbank" if "tbank" in low else ("sber" if "sberbank" in low or "sber" in low else "?")
    rows.append((bank, days, f.name, str(f.parent.name), prod[:28], t.count("\n")))

print("кандидаты (справки об остатке, до 3 страниц):")
for bank, days, name, folder, prod, lines in sorted(rows, key=lambda r: -(r[1] or 0)):
    print("  %-6s период ~%s дн | %-38s %-12s %s" % (bank, days, name[:38], folder, prod))
