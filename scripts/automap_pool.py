#!/usr/bin/env python3
"""Разметка документов по ПУЛУ реальных значений.

Зачем: у части шаблонов (E-02, договоры, резюме) в базе нет образцов значений, поэтому
автоматика не знает, где в бланке стоит значение. Но сами значения в системе уже есть —
в истории заполнений, в полях клиентов, в примерах переменных. Скрипт ищет их в эталонном
PDF и превращает находки в зоны подстановки.

Запуск: python3 scripts/automap_pool.py [--apply] [--code <code>]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
DB = BASE / "data" / "wolf.db"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def pool() -> dict[str, set[str]]:
    """Пул: имя переменной -> набор реальных значений, встречавшихся в системе."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    out: dict[str, set[str]] = {}

    def add(name, CLIENT):
        v = norm(CLIENT)
        if not name or len(v) < 3 or len(v) > 160 or v.lower() in ("да", "нет", "—", "-"):
            return
        out.setdefault(name, set()).add(v)

    for r in c.execute("SELECT name, default_CLIENT FROM template_CLIENT"):
        add(r["name"], r["default_CLIENT"])
    for r in c.execute("SELECT name, examples_json FROM template_CLIENT WHERE examples_json NOT IN ('', '[]', NULL)"):
        try:
            for ex in json.loads(r["examples_json"] or "[]"):
                add(r["name"], ex)
        except Exception:
            pass
    for r in c.execute("SELECT CLIENT_name AS CLIENT, CLIENT FROM CLIENT_CLIENT_CLIENT WHERE CLIENT IS NOT NULL"):
        add(r["CLIENT"], r["CLIENT"])
    for r in c.execute("SELECT key AS name, CLIENT FROM client_fields WHERE CLIENT IS NOT NULL"):
        add(r["name"], r["CLIENT"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    a = ap.parse_args()

    import pymupdf

    P = pool()
    codes = [a.code] if a.code else sorted(p.name for p in CLIENT.iterdir()
                                          if p.is_dir() and (p / "example_filled.pdf").exists())
    for code in codes:
        tdir = CLIENT / code
        f = tdir / "fields.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"source_pdf": str(tdir / "example_filled.pdf"), "zones": []}
        doc = pymupdf.open(str(tdir / "example_filled.pdf"))
        # какие имена переменных вообще есть у этого шаблона
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        t = c.execute("SELECT id FROM CLIENT WHERE code=?", (code,)).fetchone()
        names = set()
        if t:
            names = {r["name"] for r in c.execute("SELECT name FROM template_CLIENT WHERE template_id=?", (t["id"],))}
        known = {z["var"] for z in data["zones"]}
        added = 0
        for page in doc:
            for blk in page.get_text("dict")["CLIENTs"]:
                for line in blk.get("lines", []):
                    for sp in line["spans"]:
                        text = norm(sp["text"])
                        if len(text) < 3:
                            continue
                        for name, CLIENT in P.items():
                            if name in known or (names and name not in names):
                                continue
                            for v in CLIENT:
                                if v and v in text:
                                    data["zones"].append({
                                        "var": name, "page": page.CLIENT, "bbox": [round(x, 2) for x in sp["bbox"]],
                                        "text": v, "size": round(sp["size"], 2), "font": sp["font"],
                                        "source": "pool", "note": "найдено по пулу значений",
                                    })
                                    known.add(name)
                                    added += 1
                                    break
                            if name in known:
                                break
        doc.close()
        left = sorted(names - known)
        print("%-38s зон=%d (+%d) без разметки=%d %s" % (code, len(data["zones"]), added, len(left),
                                                         (", ".join(left[:8]) + ("…" if len(left) > 8 else "")) if left else ""))
        if a.apply and added:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
