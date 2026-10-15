"""Копия размеченного письма Ngurah Rai → письма других офисов.

Каркас письма один (офис и продукт — переменные). Берём уже сверенный с оригиналом
шаблон bridging_request_letter__ngurahrai и переносим его на Denpasar и Tabanan,
подставляя их офис-адресат и номер письма.
"""
import datetime
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

ROOT = Path("/opt/wolf_v2/data/templates")
SRC = ROOT / "bridging_request_letter__ngurahrai" / "template.html"

TARGETS = {
    "bridging_request_letter__denpasar": {
        "letter_no": "Nomor: 64/PTAPB-SP/03.10.2026",
        "letter_subject": "Permohonan Bridging Visa 60 Hari",
        "addressee_line1": "Bapak Kepala Kantor Imigrasi Kelas I TPI Denpasar",
        "addressee_line2": "Jl. D.I. Panjaitan No. 3, Dangin Puri Kelod, Denpasar Timur,",
        "addressee_line3": "Kota Denpasar, Bali 80235",
    },
    "bridging_request_letter__tabanan": {
        "letter_no": "Nomor: 65/PTAPB-SP/03.10.2026",
        "letter_subject": "Permohonan Bridging Visa 60 Hari",
        "addressee_line1": "Bapak Kepala Kantor Imigrasi Kelas III Non TPI Tabanan",
        "addressee_line2": "Jl. Arjuna 2, Delod Peken, Kec. Tabanan,",
        "addressee_line3": "Kabupaten Tabanan, Bali 82121",
    },
}

src = SRC.read_text(encoding="utf-8")
for code, vals in TARGETS.items():
    tpl = ROOT / code
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(tpl / "template.html", tpl / f"template.html.bak_office_{stamp}")
    (tpl / "template.html").write_text(src, encoding="utf-8")
    t = D.q1("SELECT id FROM templates WHERE code=?", (code,))
    n = 0
    for name, value in vals.items():
        cur = D.q1("SELECT id FROM template_variables WHERE template_id=? AND name=?", (t["id"], name))
        if cur:
            D.exec_sql("UPDATE template_variables SET default_value=? WHERE id=?", (value, cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_variables (template_id, name, label, default_value) VALUES (?,?,?,?)",
                       (t["id"], name, name, value))
        n += 1
    # переносим и остальные значения (ФИО доверенного лица и клиента) из каркаса
    for r in D.q("""SELECT name, label, default_value FROM template_variables
                    WHERE template_id=(SELECT id FROM templates WHERE code='bridging_request_letter__ngurahrai')
                      AND name NOT IN ('letter_no','letter_subject','addressee_line1','addressee_line2','addressee_line3')"""):
        cur = D.q1("SELECT id, default_value FROM template_variables WHERE template_id=? AND name=?", (t["id"], r["name"]))
        if cur:
            if not cur["default_value"] and r["default_value"]:
                D.exec_sql("UPDATE template_variables SET label=COALESCE(NULLIF(label,''),?), default_value=? WHERE id=?",
                           (r["label"], r["default_value"], cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_variables (template_id, name, label, default_value) VALUES (?,?,?,?)",
                       (t["id"], r["name"], r["label"], r["default_value"]))
        n += 1
    print("%-40s слепок + полей: %d" % (code, n))
