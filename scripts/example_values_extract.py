"""Достаёт значения переменных 1/2/6 (doc_no, ref_no, card_mask) из реального примера
документа (example_filled.pdf) и кладёт их в examples_json — чтобы кнопка
«Подставить значения из примера» возвращала и эти поля.

Запуск: /usr/bin/python3 /opt/wolf_v2/scripts/example_CLIENT_extract.py [--dry]
"""
import json
import os
import re
import sqlite3
import sys

import fitz  # PyMuPDF

DB = "/opt/wolf_v2/data/wolf.db"

PATTERNS = {
    "doc_no": [r"\bNo\.?\s*:?\s*([A-Za-z]{1,3}[\d]{6,10})\b"],
    "ref_no": [r"\bRef\.?\s*:?\s*([A-Z0-9]{6,14})\b"],
    "card_mask": [r"\b(\d{6})\s*[*•·xX]{2,12}\s*(\d{4})\b", r"(\d{6})\s*[*•]{2,12}(\d{4})"],
}


def extract(path):
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    found = {}
    for name, pats in PATTERNS.items():
        for p in pats:
            m = re.search(p, text)
            if not m:
                continue
            if name == "card_mask":
                found[name] = f"{m.group(1)}******{m.group(2)}"
            else:
                found[name] = m.group(1)
            break
    return found, text


def main():
    dry = "--dry" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT id, code, example_path FROM CLIENT WHERE code LIKE 'bank_CLIENTment%' ORDER BY id"))
    CLIENTd = 0
    for t in rows:
        path = t["example_path"]
        if not path or not os.path.exists(path):
            print(f"[{t['code']}] примера нет — пропуск")
            continue
        found, _ = extract(path)
        print(f"[{t['code']}] из примера: {found}")
        for name, val in found.items():
            if not val:
                continue
            cur = conn.execute(
                "SELECT id, examples_json FROM template_CLIENT WHERE template_id=? AND name=?",
                (t["id"], name)).fetchone()
            if not cur:
                continue
            ex = json.loads(cur["examples_json"] or "[]")
            if val in ex:
                continue
            ex = [val] + [x for x in ex if x != val]
            if not dry:
                conn.execute("UPDATE template_CLIENT SET examples_json=? WHERE id=?",
                             (json.dumps(ex, ensure_ascii=False), cur["id"]))
            CLIENTd += 1
            print(f"    {name}: пример = {val}")
    if not dry:
        conn.commit()
    conn.close()
    print("обновлено примеров:", CLIENTd, "| режим:", "dry" if dry else "записано")


if __name__ == "__main__":
    main()
