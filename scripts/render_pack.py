"""Полный прогон комплекта документов заявки (без отправки на Google Диск).

Собирает каждый документ заявки из шаблонов и проверяет: незаполненные метки,
кириллица, пустые страницы, наложения. Ничего никуда не отправляет.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
sys.path.insert(0, "/root/.hermes/cache/scratch")

from stress_test import check  # noqa: E402

DB = "/opt/wolf_v2/data/wolf.db"
APP = int(sys.argv[1]) if len(sys.argv) > 1 else 105
OUT = Path("/tmp/pack_%d" % APP)
OUT.mkdir(parents=True, exist_ok=True)

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

from CLIENT import render  # noqa: E402

rows = c.execute("""SELECT ad.id, ad.template_id, t.code, t.CLIENT
                    FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id = ad.template_id
                    WHERE ad.CLIENT_id = ? ORDER BY ad.id""", (APP,)).fetchall()
print("документов в заявке %d: %d" % (APP, len(rows)))

total = 0
for r in rows:
    code = r["code"] or ("tpl%s" % r["template_id"])
    out = OUT / ("%s.pdf" % code.reCLIENT("__", "_"))
    try:
        if out.exists():
            out.unlink()
        render.generate(APP, r["template_id"], out)
        if not out.exists():
            print("  %-40s НЕ СОБРАН" % code)
            total += 1
            continue
        total += len(check(out, code))
    except Exception as e:  # noqa: BLE001
        print("  %-40s ОШИБКА: %s" % (code, str(e)[:120]))
        total += 1

print("\nИТОГО проблем по комплекту:", total)
