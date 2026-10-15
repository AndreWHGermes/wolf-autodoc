"""Разделить адреса клиентов: российский — address_live, индонезийский — address_in_indonesia.

Правило: у клиента два разных адреса. Без --apply — только показывает план.
"""
import sqlite3
import sys

sys.path.insert(0, "/opt/wolf_v2")
from CLIENT.doc_parse import is_indonesia_address          # noqa: E402

DB = "/opt/wolf_v2/data/wolf.db"
APPLY = "--apply" in sys.argv

c = sqlite3.connect(DB, timeout=120)
c.row_factory = sqlite3.Row
cols = [r[1] for r in c.execute("PRAGMA table_info(CLIENT)")]
if "address_in_indonesia" not in cols:
    if APPLY:
        c.execute("ALTER TABLE CLIENT ADD COLUMN address_in_indonesia TEXT")
        c.commit()
    print("колонка address_in_indonesia: %s" % ("добавлена" if APPLY else "будет добавлена"))

rows = list(c.execute("SELECT id, full_name_CLIENT, full_name_CLIENT, address_live, "
                      "address_reg, address_in_indonesia FROM CLIENT"))
plan = []
for r in rows:
    al = str(r["address_live"] or "").strip()
    ai = str(r["address_in_indonesia"] or "").strip()
    if al and is_indonesia_address(al):
        plan.append((r["id"], r["full_name_CLIENT"] or r["full_name_CLIENT"], al, ai))

print("клиентов с индонезийским адресом в address_live: %d" % len(plan))
for cid, name, al, ai in plan:
    print("  id=%-5s %-28s | %s%s" % (cid, str(name)[:28], al[:58],
                                      "  [уже есть в своём поле]" if ai else ""))

if APPLY and plan:
    for cid, name, al, ai in plan:
        c.execute("UPDATE CLIENT SET address_in_indonesia=?, address_live='' WHERE id=?",
                  (al, cid))
    c.commit()
    print("перенесено в address_in_indonesia: %d" % len(plan))
c.close()
