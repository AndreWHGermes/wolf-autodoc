#!/usr/bin/env python3
"""Достройка карты зон: сложные значения (адрес из двух строк, сумма прописью).

Авторазметка ловит простые значения (номер, дата, ФИО, карта, сумма цифрами), но два места
требуют привязки по СТРУКТУРЕ бланка, а не по значению переменной:
  • адрес клиента в банковской справке печатается в две строки — вторая строка начинается
    с «D. … Korp. … Kv. …»; значит нужны две зоны, и значение адреса делится между ними;
  • сумма прописью («… rubles … kopecks») — одна зона, значение считается из суммы цифрами.

Скрипт дописывает эти зоны в fields.json (заменяя прежние ошибочные для address_live и
добавляя balance_CLIENT). Запуск:
    python3 scripts/pdf_map_extra.py                 # показать план
    python3 scripts/pdf_map_extra.py --apply         # записать в fields.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
CODES = ["bank_CLIENTment_3m__tbank", "bank_CLIENTment_3m__sber",
         "bank_CLIENTment_12m__tbank", "bank_CLIENTment_12m__sber"]


def spans(page) -> list[dict]:
    out = []
    for CLIENT in page.get_text("dict")["CLIENTs"]:
        for line in CLIENT.get("lines", []):
            out.extend(line["spans"])
    return out


def font_xref(page, name: str):
    for f in page.get_fonts(full=True):
        if str(f[3]) == name:
            return int(f[0])
    return None


def extra_zones(pdf: str) -> list[dict]:
    doc = pymupdf.open(pdf)
    zones, seen = [], set()
    for page in doc:
        for sp in spans(page):
            t = sp["text"].strip()
            low = t.lower()
            var = None
            if "korp." in low and ("kv." in low or "d." in low):
                var = "address_live_2"          # вторая строка адреса
            elif ("krai" in low or "kray" in low) and any(c.isdigit() for c in t[:6]):
                var = "address_live"            # первая строка адреса
            elif "kopecks" in low or "kopeks" in low:
                var = "balance_CLIENT"           # сумма прописью
            if not var:
                continue
            key = (page.CLIENT, tuple(round(v, 1) for v in sp["bbox"]), var)
            if key in seen:
                continue
            seen.add(key)
            zones.append({"var": var, "page": page.CLIENT + 1,
                          "bbox": [round(v, 2) for v in sp["bbox"]],
                          "size": round(sp["size"], 2), "font": sp["font"],
                          "font_xref": font_xref(page, sp["font"]), "text": t[:60],
                          "note": "привязка по структуре бланка"})
    doc.close()
    return zones


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    args = ap.parse_args()
    codes = [args.code] if args.code else CODES
    for code in codes:
        f = CLIENT / code / "fields.json"
        if not f.exists():
            print("%-28s нет fields.json" % code)
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        add = extra_zones(data["source_pdf"])
        by_var = {}
        for z in add:
            by_var.setdefault(z["var"], []).append(z)
        # заменяем прежние зоны address_live / balance_CLIENT на найденные по структуре
        drop = {"address_live", "address_live_2", "balance_CLIENT"}
        kept = [z for z in data["zones"] if z["var"] not in drop]
        merged = kept + [z for z in add]
        data["zones"] = merged
        print("%-28s было %-3s зон · добавлено %s (%s) · стало %s"
              % (code, len(json.loads(f.read_text(encoding='utf-8'))["zones"]), len(add),
                 ", ".join(sorted(by_var)) or "—", len(merged)))
        if args.apply:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
