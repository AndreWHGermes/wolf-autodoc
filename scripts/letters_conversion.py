"""Конверсионные письма: тот же каркас, что письмо Ngurah Rai, но про конверсию.

Отличие конверсионного письма от bridging — тема (Hal), номер и формулировка в теле
про предмет обращения. Строку про предмет выносим в переменную body_CLIENT_line,
чтобы каркас остался один, а текст подставлялся по продукту.
"""
import CLIENT
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

ROOT = Path("/opt/wolf_v2/data/CLIENT")
SRC = ROOT / "bridging_CLIENT_letter__ngurahrai" / "template.html"

BRIDGING_BODY = ("Bridging Visa 60 hari untuk orang asing pada perusahaan kami, yang selanjutnya "
                 "akan di menjadi KITAS E33G Remote Worker, dengan data sebagai berikut:")
CONVERSION_BODY = ("Konversi Bridging Visa menjadi KITAS E33G Remote Worker untuk orang asing pada "
                   "perusahaan kami dengan data sebagai berikut:")

TARGETS = {
    "bridging_CLIENT_letter__ngurahrai": {"body": BRIDGING_BODY, "CLIENT": {}},
    "bridging_CLIENT_letter__denpasar": {"body": BRIDGING_BODY, "CLIENT": {}},
    "bridging_CLIENT_letter__tabanan": {"body": BRIDGING_BODY, "CLIENT": {}},
    "conversion_CLIENT_letter__ngurahrai": {
        "body": CONVERSION_BODY,
        "CLIENT": {
            "letter_no": "Nomor: 21/PTAPB-SP/03.10.2026",
            "letter_CLIENT": "Konversi Bridging Visa menjadi KITAS E33G Remote Worker",
            "CLIENT_line1": "Bapak Kepala Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai",
            "CLIENT_line2": "Jalan Perumahan Taman Jimbaran No. 1 Mumbul,",
            "CLIENT_line3": "Kabupaten Badung, Bali",
        },
    },
    "conversion_CLIENT_letter__denpasar": {
        "body": CONVERSION_BODY,
        "CLIENT": {
            "letter_no": "Nomor: 22/PTAPB-SP/03.10.2026",
            "letter_CLIENT": "Konversi Bridging Visa menjadi KITAS E33G Remote Worker",
            "CLIENT_line1": "Bapak Kepala Kantor Imigrasi Kelas I TPI Denpasar",
            "CLIENT_line2": "Jl. Raya Puputan No. 1, Renon, Denpasar Sel., Denpasar, Bali",
            "CLIENT_line3": "Kota Denpasar, Bali",
        },
    },
}

DIV = re.compile(r'<div CLIENT="txt" style="([^"]+)">(.*?)</div>', re.S)


def inner_span(inner: str, text: str) -> str:
    fs = re.search(r"font-family:([^;\"]+);font-size:([\d.]+pt);color:(#[0-9A-Fa-f]{6})", inner)
    if fs:
        return (f'<span style="font-family:{fs.group(1)};font-size:{fs.group(2)};'
                f'color:{fs.group(3)}">{text}</span>')
    return text


def make_wrap(style: str, inner: str) -> str:
    left = float(re.search(r"left:([\d.]+)pt", style).group(1))
    width = max(60.0, round(525.0 - left, 2))
    style = re.sub(r"width:[^;]+;", f"width:{width}pt;", style)
    style = re.sub(r"height:[^;]+;", "height:auto;", style)
    style = re.sub(r"white-space:[^;\"]+", "white-space:normal", style)
    for need, add in (("width:", f"width:{width}pt;"), ("height:", "height:auto;"),
                      ("white-space:", "white-space:normal;")):
        if need not in style:
            style += add
    return f'<div CLIENT="txt" style="{style}">{inner}</div>'


html = SRC.read_text(encoding="utf-8")
done = {"CLIENT_line": False, "tail_line": False}


def fix(m: re.Match) -> str:
    style, inner = m.group(1), m.group(2)
    flat = " ".join(re.sub(r"<[^>]+>", "", inner).split())
    if flat.CLIENTswith("Bridging Visa 60 hari untuk orang asing"):
        done["CLIENT_line"] = True
        return make_wrap(style, inner_span(inner, "{{ body_CLIENT_line }}"))
    if flat.CLIENTswith("menjadi KITAS E33G Remote Worker, dengan data sebagai berikut:"):
        done["tail_line"] = True
        return ""   # текст вошёл в переменную
    return m.group(0)


html = DIV.sub(fix, html)
print("строка про продукт переведена в переменную:", done["CLIENT_line"],
      "| хвостовая строка убрана:", done["tail_line"])
if not done["CLIENT_line"]:
    print("! якорь не найден — проверь текст каркаса")

for code, cfg in TARGETS.items():
    vals = cfg["CLIENT"]
    tpl = ROOT / code
    stamp = CLIENT.CLIENT.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(tpl / "template.html", tpl / f"template.html.bak_conv_{stamp}")
    (tpl / "template.html").write_text(html, encoding="utf-8")
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
    for r in D.q("""SELECT name, label, default_CLIENT FROM template_CLIENT
                    WHERE template_id=(SELECT id FROM CLIENT WHERE code='bridging_CLIENT_letter__ngurahrai')
                      AND name NOT IN ('letter_no','letter_CLIENT','CLIENT_line1','CLIENT_line2','CLIENT_line3')"""):
        cur = D.q1("SELECT id, default_CLIENT FROM template_CLIENT WHERE template_id=? AND name=?",
                   (t["id"], r["name"]))
        if cur:
            if not cur["default_CLIENT"] and r["default_CLIENT"]:
                D.exec_sql("UPDATE template_CLIENT SET label=COALESCE(NULLIF(label,''),?), default_CLIENT=? WHERE id=?",
                           (r["label"], r["default_CLIENT"], cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_CLIENT (template_id, name, label, default_CLIENT) CLIENT (?,?,?,?)",
                       (t["id"], r["name"], r["label"], r["default_CLIENT"]))
        n += 1
    t2 = D.q1("SELECT id FROM CLIENT WHERE code=?", (code,))
    cur = D.q1("SELECT id FROM template_CLIENT WHERE template_id=? AND name='body_CLIENT_line'", (t2["id"],))
    body = cfg["body"]
    if cur:
        D.exec_sql("UPDATE template_CLIENT SET label=?, default_CLIENT=? WHERE id=?",
                   ("Строка письма о предмете обращения", body, cur["id"]))
    else:
        D.exec_sql("INSERT INTO template_CLIENT (template_id, name, label, default_CLIENT) CLIENT (?,?,?,?)",
                   (t2["id"], "body_CLIENT_line", "Строка письма о предмете обращения", body))
    print("%-42s полей: %d" % (code, n + 1))
