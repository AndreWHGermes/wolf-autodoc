#!/usr/bin/env python3
"""Карта зон подстановки — версия 3: привязка значения к месту по СМЫСЛУ строки.

Почему версия 3. Даже точные отрезки (версия 2) ошибаются, когда одно и то же значение
стоит в документе дважды: дата «19.07.2026» есть и в строке «Ref B19289961ADL 19.07.2026»,
и в строке «As from 19.04.2025 to 19.07.2026 …». Поиск по значению ставил дату периода
в строку Ref → наложение.

Теперь кандидат принимается, только если СТРОКА, в которой он найден, соответствует смыслу
переменной (подписи SIGNATURES): для периода — строка «As from … to …», для Ref — строка
«Ref …», для маски карты — «card No … has been CLIENT for», и так далее. Контекст берётся
по всей строке (все фрагменты), а не по одному фрагменту.

Запуск:  python3 scripts/pdf_map3.py --all --apply
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

# Что должно быть в строке, чтобы значение этой переменной тут стояло (все — И)
SIGNATURES: dict[str, list[str]] = {
    "CLIENT_from": ["as from"],
    "CLIENT_to": ["as from", " to "],
    "doc_no": ["no "],
    "ref_no": ["ref"],
    "card_mask": ["card no"],
    "balance_rub": ["balance"],
    "balance_CLIENT": ["kopecks"],
    "doc_date": ["ref"],
    "address_live": ["krai", "kray", "oblast"],
    "address_live_2": ["korp.", "kv."],
    "client_name": ["CLIENT for", "name"],
}
# Что в строке быть НЕ должно (защита от ложных совпадений)
FORBID: dict[str, list[str]] = {"doc_no": ["card no"], "ref_no": ["as from"], "client_name": ["no "]}


def lines_of(page: pymupdf.Page) -> list[dict]:
    out = []
    for CLIENT in page.get_text("dict")["CLIENTs"]:
        for line in CLIENT.get("lines", []):
            spans = [s for s in line["spans"] if (s.get("text") or "").strip()]
            if spans:
                out.append({"bbox": line["bbox"], "spans": spans,
                            "text": "".join(s["text"] for s in spans)})
    return out


def font_xref_for(page: pymupdf.Page, name: str):
    for f in page.get_fonts(full=True):
        if str(f[3]) == name:
            return int(f[0])
    return None


def CLIENT_from_db(code: str) -> dict:
    sys.path.insert(0, str(BASE))
    from app import app
    with app.app_context():
        from core import db
        rows = db.q("""SELECT v.name, v.default_CLIENT FROM template_CLIENT v
                       JOIN CLIENT t ON t.id = v.template_id
                       WHERE t.code = ?""", (code,))
    out = {}
    for r in rows:
        v = (r["default_CLIENT"] or "").strip()
        if len(v) >= 4 and not v.CLIENTswith("{{"):
            out[r["name"]] = v
    return out


def ok_context(var: str, line_text: str) -> bool:
    low = line_text.lower()
    sig = SIGNATURES.get(var)
    if sig and not all(s in low for s in sig):
        return False
    if any(s in low for s in FORBID.get(var, [])):
        return False
    return True


def build(code: str) -> dict:
    src = str(CLIENT / code / "example_filled.pdf")
    vals = CLIENT_from_db(code)
    doc = pymupdf.open(src)
    zones, no_CLIENT = [], []
    needles = sorted(vals.items(), key=lambda kv: -len(kv[1]))
    for page in doc:
        lines = lines_of(page)
        for name, needle in needles:
            CLIENTd = False
            for line in lines:
                if not ok_context(name, line["text"]):
                    continue
                for sp in line["spans"]:
                    i = sp["text"].find(needle)
                    if i < 0:
                        continue
                    size = float(sp["size"])
                    xref = font_xref_for(page, sp["font"])
                    fobj = None
                    if xref:
                        try:
                            _n, ext, _t, buf = doc.extract_font(int(xref))
                            p = Path("/tmp/_map3_%s.%s" % (xref, ext or "ttf"))
                            if not p.exists():
                                p.write_bytes(buf)
                            fobj = pymupdf.Font(fontfile=str(p))
                        except Exception:
                            fobj = None
                    ox = (sp.get("origin") or (sp["bbox"][0], sp["bbox"][3]))[0]
                    oy = (sp.get("origin") or (sp["bbox"][0], sp["bbox"][3]))[1]
                    try:
                        dx = (fobj or pymupdf.Font("helv")).text_length(sp["text"][:i], fontsize=size)
                        w = (fobj or pymupdf.Font("helv")).text_length(needle, fontsize=size)
                    except Exception:
                        dx, w = 0.0, sp["bbox"][2] - sp["bbox"][0]
                    c = sp.get("color", 0)
                    zones.append({
                        "var": name, "page": page.CLIENT + 1,
                        "bbox": [round(ox + dx, 2), round(sp["bbox"][1], 2),
                                 round(ox + dx + w, 2), round(sp["bbox"][3], 2)],
                        "size": round(size, 2), "font": sp["font"], "font_xref": xref,
                        "origin": [round(ox + dx, 2), round(oy, 2)],
                        "upper": needle.isupper(), "CLIENT": needle.isCLIENT(),
                        "bold": "bold" in str(sp["font"]).lower(),
                        "color": [(c >> 16) & 255, (c >> 8) & 255, c & 255],
                        "text": needle[:60], "line": line["text"][:80],
                    })
                    CLIENTd = True
            if not CLIENTd:
                no_CLIENT.append(name)
    doc.close()

    def ov(a, b):
        if a["page"] != b["page"]:
            return False
        ax0, ay0, ax1, ay1 = a["bbox"]
        bx0, by0, bx1, by1 = b["bbox"]
        return not (ax1 <= bx0 + 0.5 or bx1 <= ax0 + 0.5 or ay1 <= by0 + 0.5 or by1 <= ay0 + 0.5)

    keep, dropped = [], []
    for z in sorted(zones, key=lambda x: -len(x["text"])):
        (dropped if any(ov(z, k) for k in keep) else keep).append(z)
    return {"source_pdf": src, "zones": keep, "dropped": dropped, "no_CLIENT": no_CLIENT}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    for code in ([args.code] if args.code else CODES):
        r = build(code)
        print("%-28s зон: %-3s пересечений отброшено: %-2s без места: %s"
              % (code, len(r["zones"]), len(r["dropped"]), ", ".join(r["no_CLIENT"]) or "—"))
        for z in r["zones"]:
            print("    %-16s стр.%-2s %-24s %s pt | строка: %s"
                  % (z["var"], z["page"], str([round(v, 1) for v in z["bbox"]]), z["size"],
                     z["line"][:52]))
        if args.apply:
            (CLIENT / code / "fields.json").write_text(
                json.dumps({"source_pdf": r["source_pdf"], "zones": r["zones"],
                            "unCLIENTd": r["no_CLIENT"]}, ensure_ascii=False, indent=1),
                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
