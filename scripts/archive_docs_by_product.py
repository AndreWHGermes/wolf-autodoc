"""Что реально готовилось клиентам: разбор архива по продуктам.

Часть 1 — Word-документы, переданные заказчиком (data/word_templates/imported_*):
тип документа по заголовку.
Часть 2 — папки клиентов: продукт из базы + какие готовые документы в папке.
"""
import re
import sqlite3
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path("/opt/wolf_v2")

# документы, которые готовит система (в отличие от документов, которые приносит клиент)
OURS = (
    ("Remote Work Agreement", ("remote_work", "remote work")),
    ("Employment Contract", ("employment agreement", "employment_contract", "employment")),
    ("Resume/CV", ("resume", "_cv", "cv_", "cv.")),
    ("Form E-02", ("e-02", "e02", "form_e")),
    ("Bridging Visa letter", ("bridging",)),
    ("Permohonan/письмо", ("permohonan", "cover letter", "cover_letter")),
    ("Surat pernyataan / kuasa", ("surat", "kuasa", "jaminan", "pernyataan")),
)
# документы клиента
CLIENT = (
    ("банковская справка", ("bank", "balance", "остатк", "выписк", "personal-3m", "personal_3m")),
    ("паспорт", ("passport", "загран")),
    ("ITK/виза", ("itk", "visa", "viza", "виза")),
    ("фото", ("foto", "photo", "фото")),
)


def kind_of(name: str):
    low = name.lower()
    for label, keys in OURS:
        if any(k in low for k in keys):
            return "НАШ: " + label
    for label, keys in CLIENT:
        if any(k in low for k in keys):
            return "клиент: " + label
    return ""


print("=== ЧАСТЬ 1. Word-документы от заказчика: тип по заголовку")
for p in sorted(Path(ROOT / "data" / "word_templates").glob("imported_*/**/*.docx")):
    if p.name.startswith("~$"):
        continue
    try:
        z = zipfile.ZipFile(p)
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
        z.close()
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
    except Exception as exc:                                   # noqa: BLE001
        txt = "ошибка чтения: %s" % str(exc)[:40]
    print("  %-58s %s" % (p.name[:58], txt[:110]))

print()
print("=== ЧАСТЬ 2. Готовые документы в папках клиентов (по продуктам)")
conn = sqlite3.connect(str(ROOT / "data" / "wolf.db"), timeout=60)
conn.row_factory = sqlite3.Row
prod_of = {}
for r in conn.execute("""SELECT a.client_id, p.code FROM applications a
                         LEFT JOIN products p ON p.id = a.product_id
                         WHERE a.client_id IS NOT NULL"""):
    prod_of.setdefault(r["client_id"], r["code"])
conn.close()

by_prod = defaultdict(set)
rows_out = []
for folder in sorted((ROOT / "data" / "gdrive_cache").glob("client_*")):
    try:
        cid = int(folder.name.split("_")[1])
    except (IndexError, ValueError):
        continue
    found = []
    for f in folder.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            k = kind_of(f.name)
            if k.startswith("НАШ:"):
                found.append(k[5:])
                by_prod[prod_of.get(cid, "?")].add(k[5:])
    if found:
        rows_out.append((cid, prod_of.get(cid, "?"), sorted(set(found))))

for cid, prod, docs in sorted(rows_out):
    print("  клиент %-4s %-10s %s" % (cid, prod, ", ".join(docs)))

print()
print("=== ИТОГ: какие наши документы встречаются по продуктам")
for prod in sorted(by_prod):
    print("  %-10s %s" % (prod, ", ".join(sorted(by_prod[prod]))))
print()
print("=== для сравнения — что сейчас привязано в системе:")
conn = sqlite3.connect(str(ROOT / "data" / "wolf.db"), timeout=60)
conn.row_factory = sqlite3.Row
for r in conn.execute("""SELECT p.code, t.code FROM product_documents pd
                         JOIN products p ON p.id = pd.product_id
                         JOIN templates t ON t.id = pd.template_id
                         ORDER BY p.code, t.code"""):
    print("  %-10s %s" % (r["code"], r["code" if False else "code"] if False else r[1]))
conn.close()
