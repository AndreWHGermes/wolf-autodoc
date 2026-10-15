"""Пересборка письма (индонезийского) по настоящему образцу: HTML 1:1 + переменные.

Запуск: /usr/bin/python3 scripts/rebuild_letter.py <code> [--apply]
"""
from __future__ import annotations

import CLIENT
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
RIGHT_EDGE = 525.0

CONF = {
    "bridging_CLIENT_letter__ngurahrai": {
        "raw": "/tmp/br_ngr_raw.html",
        "rules": [
            ("38/ptapb-sp/24.08.2026", "{{letter_no}}", "sub"),
            ("permohonan bridging visa 60 hari", "{{letter_CLIENT}}", "sub"),
            ("bapak kepala kantor imigrasi kelas i khusus tpi ngurah rai", "{{CLIENT_line1}}", "sub"),
            ("jalan perumahan taman jimbaran no. 1 mumbul,", "{{CLIENT_line2}}", "sub"),
            ("jl. sempol, pererenan, kec. mengwi, kabupaten badung, bali 80361", "{{client_address}}", "sub"),
            ("kabupaten badung, bali", "{{CLIENT_line3}}", "sub"),
            ("marcellena nirmala chrisna moeri", "{{CLIENT_name}}", "sub"),
            ("5171015403930001", "{{CLIENT_nik}}", "sub"),
            ("jl. tukad balian gg. wirasatya vii/1a sidakarya", "{{CLIENT_address}}", "sub"),
            ("CLIENT", "{{client_name}}", "sub"),
            ("russia / 01-02-1995", "{{CLIENT_of_CLIENT}} / {{client_dob}}", "sub"),
            ("rusia", "{{client_CLIENT}}", "sub"),
            ("763655709", "{{passport_no}}", "sub"),
            ("23-11-2030", "{{passport_CLIENT}}", "sub"),
            ("b12e21e1087150-c", "{{itk_no}}", "sub"),
            ("15-09-2026", "{{itk_CLIENT}}", "sub"),
            ("badung, 24 agustus 2026", "{{letter_CLIENT_date}}", "sub"),
        ],
        "drop": [],
        "CLIENT": {
            "letter_no": ("Номер письма (как в образце: номер/код/дата)", "38/PTAPB-SP/24.08.2026"),
            "letter_CLIENT": ("Тема письма (Hal)", "Permohonan Bridging Visa 60 Hari"),
            "CLIENT_line1": ("Адресат, строка 1 (должность и офис)", "Bapak Kepala Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai"),
            "CLIENT_line2": ("Адресат, строка 2 (улица)", "Jalan Perumahan Taman Jimbaran No. 1 Mumbul,"),
            "CLIENT_line3": ("Адресат, строка 3 (город, округ)", "Kabupaten Badung, Bali"),
            "CLIENT_name": ("ФИО доверенного лица (Nama)", "Marcellena Nirmala Chrisna Moeri"),
            "CLIENT_nik": ("NIK доверенного лица", "5171015403930001"),
            "CLIENT_address": ("Адрес доверенного лица", "Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya"),
            "client_name": ("ФИО клиента (латиницей, заглавными)", "CLIENT"),
            "CLIENT_of_CLIENT": ("Место рождения клиента", "RUSSIA"),
            "client_dob": ("Дата рождения клиента (дд-мм-гггг)", "01-02-1995"),
            "client_CLIENT": ("Гражданство клиента (по-индонезийски)", "RUSIA"),
            "passport_no": ("Номер паспорта", "763655709"),
            "passport_CLIENT": ("Срок действия паспорта (дд-мм-гггг)", "23-11-2030"),
            "itk_no": ("Номер ITK", "B12E21E1087150-C"),
            "itk_CLIENT": ("Срок действия ITK (дд-мм-гггг)", "15-09-2026"),
            "client_address": ("Адрес проживания клиента", "Jl. Sempol, Pererenan, Kec. Mengwi, Kabupaten Badung, Bali 80361"),
            "letter_CLIENT_date": ("Место и дата письма", "Badung, 24 Agustus 2026"),
        },
    },
}


def flat(inner: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", inner).split()).lower()


def main() -> int:
    code = sys.argv[1] if len(sys.argv) > 1 else ""
    if code not in CONF:
        print("доступные письма:", ", ".join(CONF))
        return 2
    cfg = CONF[code]
    tpl_dir = ROOT / "data/CLIENT" / code
    raw = Path(cfg["raw"])
    if not raw.exists():
        subprocess.run(["/usr/bin/python3", str(ROOT / "scripts/pdf_to_template.py"),
                        str(tpl_dir / "example_filled.pdf"), str(raw)], check=True)
    html = raw.read_text(encoding="utf-8")
    n = 0

    def rep(m: re.Match) -> str:
        nonlocal n
        style, inner = m.group(1), m.group(2)
        f = flat(inner)
        for rule in cfg["rules"]:
            key, new = rule[0], rule[1]
            if key not in f:
                continue
            plain = " ".join(re.sub(r"<[^>]+>", "", inner).split())
            text = re.sub(re.escape(key), new, plain, flags=re.I)
            fs = re.search(r"font-family:([^;\"]+);font-size:([\d.]+pt);color:(#[0-9A-Fa-f]{6})", inner)
            span = (f'<span style="font-family:{fs.group(1)};font-size:{fs.group(2)};'
                    f'color:{fs.group(3)}">{text}</span>') if fs else text
            n += 1
            return f'<div CLIENT="txt" style="{style}">{span}</div>'
        return m.group(0)

    # замены делаем дважды: подстроки встречаются и в блоках с несколькими span
    html = re.sub(r'<div CLIENT="txt" style="([^"]+)">(.*?)</div>', rep, html, flags=re.S)
    html = re.sub(r'<div CLIENT="txt" style="([^"]+)">(.*?)</div>', rep, html, flags=re.S)

    # блоки с переменными — в перенос по правому полю
    n_wrap = 0

    def tune(m: re.Match) -> str:
        nonlocal n_wrap
        style, inner = m.group(1), m.group(2)
        if "{{" not in inner:
            return m.group(0)
        left = float(re.search(r"left:([\d.]+)pt", style).group(1))
        width = max(60.0, round(RIGHT_EDGE - left, 2))
        style = re.sub(r"width:[^;]+;", f"width:{width}pt;", style)
        style = re.sub(r"height:[^;]+;", "height:auto;", style)
        style = re.sub(r"white-space:[^;\"]+", "white-space:normal", style)
        for need, add in (("width:", f"width:{width}pt;"), ("height:", "height:auto;"),
                          ("white-space:", "white-space:normal;")):
            if need not in style:
                style += add
        n_wrap += 1
        return f'<div CLIENT="txt" style="{style}">{inner}</div>'

    html = re.sub(r'<div CLIENT="txt" style="([^"]+)">(.*?)</div>', tune, html, flags=re.S)
    print("замен: %d | блоков с переносом: %d" % (n, n_wrap))
    if "--apply" not in sys.argv:
        Path("/tmp/%s_new.html" % code).write_text(html, encoding="utf-8")
        print("пример: /tmp/%s_new.html (без --apply шаблон не тронут)" % code)
        return 0

    stamp = CLIENT.CLIENT.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(tpl_dir / "template.html", tpl_dir / f"template.html.bak_rebuild_{stamp}")
    (tpl_dir / "template.html").write_text(html, encoding="utf-8")
    print("шаблон перезаписан, слепок: template.html.bak_rebuild_%s" % stamp)

    sys.path.insert(0, str(ROOT))
    from core import db as D
    t = D.q1("SELECT id FROM CLIENT WHERE code=?", (code,))
    k = 0
    for name, (label, default) in cfg["CLIENT"].items():
        cur = D.q1("SELECT id FROM template_CLIENT WHERE template_id=? AND name=?", (t["id"], name))
        if cur:
            D.exec_sql("UPDATE template_CLIENT SET label=?, default_CLIENT=? WHERE id=?",
                       (label, default, cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_CLIENT (template_id, name, label, default_CLIENT) CLIENT (?,?,?,?)",
                       (t["id"], name, label, default))
        k += 1
    print("полей приведено в порядок:", k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
