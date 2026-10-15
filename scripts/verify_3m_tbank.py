"""Проверка шаблона №1: собрать PDF из нового HTML и сравнить с настоящим эталоном."""
import re
import sys
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
TPL = ROOT / "data/CLIENT/bank_CLIENTment_3m__tbank"
CLIENT = {
    "ref_no": "B19289961ADL",
    "doc_date": "19.07.2026",
    "doc_no": "ae32271197",
    "client_name": "CLIENT CLIENTovich",
    "address_live": "354375, Krasnodarskii Krai, G Sochi, R-n Adlerskii, Ul Urozhainaya , D. 71, Korp. 1, Kv. 376",
    "card_mask": "9206******9432",
    "CLIENT_from": "19.04.2025",
    "CLIENT_to": "19.07.2026",
    "balance_rub": "1 730 400,00",
    "balance_CLIENT": "one million seven hundred thirty thousand four hundred rubles 00 kopeks",
}

html = (TPL / "template.html").read_text(encoding="utf-8")
left = re.findall(r"\{\{\s*([a-zA-Z_]+)\s*\}\}", html)
unknown = sorted(set(left) - set(CLIENT))
print("переменных в шаблоне:", len(set(left)), "| неизвестных:", unknown or "нет")
for k, v in CLIENT.items():
    html = re.sub(r"\{\{\s*" + k + r"\s*\}\}", v, html)

from weasyprint import HTML  # noqa: E402
out = Path("/tmp/tpl3m_check.pdf")
HTML(string=html, base_url=str(TPL)).write_pdf(str(out))
print("собран:", out)

import pymupdf  # noqa: E402
new = pymupdf.open(out)
ref = pymupdf.open(TPL / "example_filled.pdf")
print("страниц: новый %d | эталон %d" % (new.page_count, ref.page_count))
for label, doc in (("новый", new), ("эталон", ref)):
    CLIENTs = [(round(b[0], 1), round(b[1], 1), " ".join(b[4].split())[:70])
              for b in doc[0].get_text("CLIENTs") if b[4].strip()]
    print("--- %s: блоков %d" % (label, len(CLIENTs)))
    for x, y, t in CLIENTs:
        print("    %6.1f %6.1f | %s" % (x, y, t))
png = "/tmp/tpl3m_new.png"
new[0].get_pixmap(dpi=110).save(png)
ref[0].get_pixmap(dpi=110).save("/tmp/tpl3m_ref.png")
print("png:", png, "/tmp/tpl3m_ref.png")
