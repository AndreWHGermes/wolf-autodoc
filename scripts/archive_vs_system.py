"""Сверка архива с тем, что система считает пакетом.

Для каждого клиента с заявкой: продукт + какие документы реально лежат в его
папке на Диске (тип определяется по имени файла). Итог — по продуктам: какие
документы реально подавались и как это соотносится с набором product_documents.
"""
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
CACHE = ROOT / "data" / "gdrive_cache"

# тип документа по имени файла: порядок важен (первое совпадение выигрывает)
KINDS = (
    ("форма E-02", ("e-02", "e_02", "e02", "statement letter")),
    ("заявление+гарантия (jaminan)", ("jaminan", "permintaan")),
    ("доверенность (surat kuasa)", ("kuasa",)),
    ("письмо в иммиграцию (permohonan)", ("permohonan", "bridging_visa", "bridging visa",
                                          "conversion", "cover letter", "cover_letter")),
    ("банковская справка", ("bank", "balance", "остатк", "выписк", "movement")),
    ("резюме", ("resume", "cv", "curriculum")),
    ("трудовой договор", ("employment", "work agreement", "remote_work", "remote work",
                          "трудовой")),
    ("спонсорское письмо", ("sponsor", "guarantee")),
    ("паспорт", ("passport", "загран")),
    ("ITK/виза", ("itk", "visa", "viza", "виза")),
    ("фото", ("foto", "photo")),
)

c = sqlite3.connect(str(ROOT / "data" / "wolf.db"), timeout=60)
c.row_factory = sqlite3.Row
rows = list(c.execute("""SELECT a.id AS app_id, a.client_id, p.code AS product, p.name AS pname
                         FROM applications a LEFT JOIN products p ON p.id = a.product_id"""))
c.close()

by_product = defaultdict(lambda: {"apps": 0, "kinds": defaultdict(int), "files": 0})
for r in rows or []:
    cid = r["client_id"]
    folder = CACHE / ("client_%s" % cid)
    if not folder.is_dir():
        continue
    prod = r["product"] or "(продукт не указан)"
    by_product[prod]["apps"] += 1
    for f in folder.rglob("*"):
        if not f.is_file():
            continue
        name = f.name.lower()
        if name.startswith("."):
            continue
        by_product[prod]["files"] += 1
        for label, keys in KINDS:
            if any(k in name for k in keys):
                by_product[prod]["kinds"][label] += 1
                break

print("продукт / заявок / файлов / реально лежащие документы (сколько раз встречаются)")
for prod in sorted(by_product):
    d = by_product[prod]
    kinds = ", ".join("%s×%d" % (k, v) for k, v in
                      sorted(d["kinds"].items(), key=lambda kv: -kv[1]))
    print("\n%-16s заявок=%-4d файлов=%-5d" % (prod, d["apps"], d["files"]))
    print("   %s" % (kinds or "—"))

print("\n=== набор системы (product_documents):")
c = sqlite3.connect(str(ROOT / "data" / "wolf.db"), timeout=60)
c.row_factory = sqlite3.Row
for r in c.execute("""SELECT p.code, t.code AS tpl FROM product_documents pd
                      JOIN products p ON p.id = pd.product_id
                      JOIN templates t ON t.id = pd.template_id
                      ORDER BY p.code, t.code"""):
    print("   %-16s %s" % (r["code"], r["tpl"]))
c.close()
