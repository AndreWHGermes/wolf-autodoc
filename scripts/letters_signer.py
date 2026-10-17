"""Подпись офиса в письмах: добавляет в HTML письма строку подписанта.

Канон агентства: письмо офиса Denpasar подписывает Arine Fadillah (Komisaris),
Ngurah Rai — Bartosz Pawel Nafalski (Direktur). Значение подставляется переменной
{{signatory_name}}, поэтому один каркас обслуживает все офисы.

Запуск: /usr/bin/python3 scripts/letters_signer.py [--apply]
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")
from core import db as D  # noqa: E402

ROOT = Path("/opt/wolf_v2/data/templates")
SIGNERS = {
    "denpasar": ("Arine Fadillah, Komisaris", "Komisaris"),
    "ngurahrai": ("Bartosz Pawel Nafalski, Direktur", "Direktur"),
}
LETTERS = [
    "bridging_request_letter__ngurahrai",
    "bridging_request_letter__denpasar",
    "bridging_request_letter__tabanan",
    "conversion_request_letter__ngurahrai",
    "conversion_request_letter__denpasar",
]
MARK = "{{signatory_name}}"
apply = "--apply" in sys.argv


def signer_for(code: str):
    key = "denpasar" if "denpasar" in code else ("tabanan" if "tabanan" in code else "ngurahrai")
    if key == "tabanan":
        key = "ngurahrai"
    return SIGNERS[key]


for code in LETTERS:
    tpl = ROOT / code
    src = tpl / "template.html"
    if not src.exists():
        print("нет шаблона:", code)
        continue
    html = src.read_text(encoding="utf-8")
    name, pos = signer_for(code)
    t = D.q1("SELECT id FROM templates WHERE code=?", (code,))
    if MARK in html:
        print("%-38s строка подписи уже есть" % code)
    else:
        # ставим подпись сразу под «Hormat kami,» (top=690.66pt в каркасе письма)
        top = 724.0
        block = (
            '\n<div class="txt" style="left:70.87pt;top:%.2fpt;width:300.00pt;height:auto;white-space:normal">'
            '<span style="font-family:Helvetica;font-size:10.50pt;color:#000000">%s</span></div>\n'
            % (top, MARK)
        )
        html = html.replace("</body>", block + "</body>") if "</body>" in html else html + block
        print("%-38s добавлена строка подписи на top=%.2f" % (code, top))
        if apply:
            shutil.copy2(src, src.with_name("template.html.bak_signer_%s" % datetime.now().strftime("%Y%m%d_%H%M%S")))
            src.write_text(html, encoding="utf-8")

    for var, val, label in (("signatory_name", name, "Подписант письма (имя, должность)"),
                            ("signatory_position", pos, "Должность подписанта")):
        cur = D.q1("SELECT id, default_value FROM template_variables WHERE template_id=? AND name=?", (t["id"], var))
        if cur and cur["default_value"] != val:
            D.exec_sql("UPDATE template_variables SET default_value=? WHERE id=?", (val, cur["id"]))
        elif not cur:
            print("   (переменной %s ещё нет — добавить вручную)" % var)
    print("   %-38s подписант: %s" % (code, name))

print("\nрежим:", "ПРИМЕНЕНО" if apply else "просмотр (без --apply ничего не менялось)")
