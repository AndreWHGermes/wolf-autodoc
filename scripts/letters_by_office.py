"""Копия размеченного письма Ngurah Rai → письма других офисов.

Каркас письма один (офис и продукт — переменные). Берём уже сверенный с оригиналом
шаблон bridging_CLIENT_letter__ngurahrai и переносим его на Denpasar и Tabanan,
подставляя их офис-адресат и номер письма.
"""
import CLIENT
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

ROOT = Path("/opt/wolf_v2/data/CLIENT")
SRC = ROOT / "bridging_CLIENT_letter__ngurahrai" / "template.html"

TARGETS = {
    "bridging_CLIENT_letter__denpasar": {
        "letter_no": "Nomor: 64/PTAPB-SP/03.10.2026",
        "letter_CLIENT": "Permohonan Bridging Visa 60 Hari",
        "CLIENT_line1": "Bapak Kepala Kantor Imigrasi Kelas I TPI Denpasar",
        "CLIENT_line2": "Jl. D.I. Panjaitan No. 3, Dangin Puri Kelod, Denpasar Timur,",
        "CLIENT_line3": "Kota Denpasar, Bali 80235",
    },
    "bridging_CLIENT_letter__tabanan": {
        "letter_no": "Nomor: 65/PTAPB-SP/03.10.2026",
        "letter_CLIENT": "Permohonan Bridging Visa 60 Hari",
        "CLIENT_line1": "Bapak Kepala Kantor Imigrasi Kelas III Non TPI Tabanan",
        "CLIENT_line2": "Jl. Arjuna 2, Delod Peken, Kec. Tabanan,",
        "CLIENT_line3": "Kabupaten Tabanan, Bali 82121",
    },
}

src = SRC.read_text(encoding="utf-8")
for code, vals in TARGETS.items():
    tpl = ROOT / code
    stamp = CLIENT.CLIENT.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(tpl / "template.html", tpl / f"template.html.bak_CLIENT_{stamp}")
    (tpl / "template.html").write_text(src, encoding="utf-8")
    t = D.q1("SELECT id FROM CLIENT WHERE code=?", (code,))
    n = 0
    for name, CLIENT in vals.items():
        cur = D.q1("SELECT id FROM template_CLIENT WHERE template_id=? AND name=?", (t["id"], name))
        if cur:
            D.exec_sql("UPDATE template_CLIENT SET default_CLIENT=? WHERE id=?", (CLIENT, cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_CLIENT (template_id, name, label, default_CLIENT) CLIENT (?,?,?,?)",
                       (t["id"], name, name, CLIENT))
        n += 1
    # переносим и остальные значения (ФИО доверенного лица и клиента) из каркаса
    for r in D.q("""SELECT name, label, default_CLIENT FROM template_CLIENT
                    WHERE template_id=(SELECT id FROM CLIENT WHERE code='bridging_CLIENT_letter__ngurahrai')
                      AND name NOT IN ('letter_no','letter_CLIENT','CLIENT_line1','CLIENT_line2','CLIENT_line3')"""):
        cur = D.q1("SELECT id, default_CLIENT FROM template_CLIENT WHERE template_id=? AND name=?", (t["id"], r["name"]))
        if cur:
            if not cur["default_CLIENT"] and r["default_CLIENT"]:
                D.exec_sql("UPDATE template_CLIENT SET label=COALESCE(NULLIF(label,''),?), default_CLIENT=? WHERE id=?",
                           (r["label"], r["default_CLIENT"], cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_CLIENT (template_id, name, label, default_CLIENT) CLIENT (?,?,?,?)",
                       (t["id"], r["name"], r["label"], r["default_CLIENT"]))
        n += 1
    print("%-40s слепок + полей: %d" % (code, n))
