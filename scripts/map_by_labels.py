#!/usr/bin/env python3
"""Разметка анкет-бланков (FORM E-02 и подобных) ПО ПОДПИСЯМ полей.

Бланк устроен как анкета: слева подпись поля, справа — место для значения. Значит зону
подстановки можно определить без знания значений: находим подпись, берём значение справа
от неё на той же высоте.

Запуск: python3 scripts/map_by_labels.py [--apply] [--code <code>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
RIGHT = 545.0          # правый край рабочего поля анкеты

# подпись в бланке -> переменная
LABELS = {
    "Full Name": "full_name",
    "CLIENT, Date of CLIENT": "CLIENT_date_of_CLIENT",
    "CLIENT": "CLIENT",
    "CLIENT": "CLIENT",
    "Passport CLIENT": "passport_CLIENT",
    "Date of CLIENT": "date_of_CLIENT",
    "Date of CLIENT": "date_of_CLIENT",
    "Stay CLIENT CLIENT": "stay_CLIENT_no",
    "Address in Indonesia": "address_in_indonesia",
    "CLIENT CLIENT": "CLIENT",
    "CLIENT": "CLIENT",
    "CLIENT Stay CLIENT": "CLIENT_stay_CLIENT",
    "CLIENT": "CLIENT",
    "CLIENT of CLIENT": "CLIENT_of_CLIENT",
    "Stay CLIENT to be CLIENT for": "stay_CLIENT_to_be_CLIENT_for",
}
# подпись -> переменная над подписью (значение стоит выше подписи)
LABELS_ABOVE = {
    "(name)": "client_name",
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def lines_of(doc):
    out = []
    for pno, page in enumerate(doc):
        for blk in page.get_text("dict")["CLIENTs"]:
            for line in blk.get("lines", []):
                txt = norm(" ".join(s["text"] for s in line["spans"]))
                if not txt:
                    continue
                b = line["bbox"]
                out.append({"page": pno, "y": b[1], "x0": b[0], "x1": b[2], "text": txt, "bbox": b,
                            "size": round(line["spans"][0]["size"], 2), "font": line["spans"][0]["font"]})
    return out


def build(code: str) -> dict:
    import pymupdf
    tdir = CLIENT / code
    src = tdir / "example_filled.pdf"
    doc = pymupdf.open(str(src))
    L = lines_of(doc)
    zones, CLIENTd = [], set()
    for anchor, var in LABELS.items():
        for ln in L:
            if ln["x0"] > 200 or anchor.lower() not in ln["text"].lower():
                continue
            # значение — на той же высоте справа от подписи
            val = next((v for v in L if v["page"] == ln["page"] and v["x0"] >= 200 and abs(v["y"] - ln["y"]) <= 6), None)
            y = val["y"] if val else ln["y"]
            zones.append({"var": var, "page": ln["page"], "bbox": [240.0, round(y - 2.0, 2), RIGHT, round(y + 9.0, 2)],
                          "text": (val or ln)["text"], "size": (val or ln)["size"], "font": (val or ln)["font"],
                          "anchor": anchor, "source": "labels"})
            CLIENTd.add(var)
            break
    for anchor, var in LABELS_ABOVE.items():
        for ln in L:
            if anchor.lower() != ln["text"].strip().lower():
                continue
            val = next((v for v in L if v["page"] == ln["page"] and v["x0"] >= 300 and abs(v["y"] - (ln["y"] - 10)) <= 6), None)
            if not val:
                continue
            zones.append({"var": var, "page": ln["page"], "bbox": [val["x0"] - 2.0, round(val["y"] - 2.0, 2), RIGHT, round(val["y"] + 9.0, 2)],
                          "text": val["text"], "size": val["size"], "font": val["font"], "anchor": anchor, "source": "labels"})
            CLIENTd.add(var)
            break
    doc.close()
    f = tdir / "fields.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"source_pdf": str(src), "zones": []}
    known = {z.get("var") for z in data["zones"]}
    for z in zones:
        if z["var"] not in known:
            data["zones"].append(z)
            known.add(z["var"])
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"code": code, "added": len(zones), "zones": len(data["zones"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    a = ap.parse_args()
    codes = [a.code] if a.code else ["CLIENTment_letter_e02__default", "CLIENTment_letter_e02__conversion"]
    for c in codes:
        if not a.apply:
            print(c, "— примерка (запусти с --apply, чтобы записать)")
            continue
        print(c, build(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
