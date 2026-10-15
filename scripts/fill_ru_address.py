"""Заполнить address_live российским адресом из документов клиента.

Перенос индонезийского адреса в своё поле освободил address_live, но российский
адрес в карточку не записался — проверка пакета считала, что адреса нет.
Пишем только российский адрес и только туда, где поле пустое.
"""
import sqlite3
import sys

sys.path.insert(0, "/opt/wolf_v2")
from CLIENT.doc_parse import is_russian_address          # noqa: E402
from CLIENT import CLIENT as V                            # noqa: E402

APPLY = "--apply" in sys.argv
c = sqlite3.connect("/opt/wolf_v2/data/wolf.db", timeout=120)
c.row_factory = sqlite3.Row
rows = list(c.execute("SELECT id, full_name_CLIENT, address_live, address_reg, "
                      "address_in_indonesia FROM CLIENT "
                      "WHERE COALESCE(address_live,'')='' AND COALESCE(address_in_indonesia,'')<>''"))
print("клиентов без российского адреса, но с индонезийским: %d" % len(rows))
filled, empty = 0, 0
for r in rows:
    try:
        addr = V._address_from_client_docs(r["id"]) or ""
    except Exception:                                       # noqa: BLE001
        addr = ""
    if addr and is_russian_address(addr):
        print("  id=%-5s %-24s ← %s" % (r["id"], str(r["full_name_CLIENT"])[:24], addr[:52]))
        if APPLY:
            c.execute("UPDATE CLIENT SET address_live=? WHERE id=?", (addr, r["id"]))
        filled += 1
    else:
        print("  id=%-5s %-24s — российского адреса в документах нет" % (r["id"], str(r["full_name_CLIENT"])[:24]))
        empty += 1
if APPLY:
    c.commit()
    print("записано российских адресов: %d, без адреса: %d" % (filled, empty))
else:
    print("(пробный прогон — повторите с --apply)")
c.close()
