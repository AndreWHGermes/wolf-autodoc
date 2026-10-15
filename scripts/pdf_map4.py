#!/usr/bin/env python3
"""Карта зон подстановки — версия 4: разбор бланка по якорям и колонкам.

Почему версия 4. Поиск значения (v1–v3) работает, только если текст эталона совпадает со
значением из базы. У половины переменных он не совпадает (адрес, имя, прописью) — и тогда
зона либо не находится, либо ставится не туда. Это и давало наложения.

Надёжный принцип: зона определяется МЕСТОМ В БЛАНКЕ, а не значением. Строка документа
разбирается на фрагменты по порядку слева направо, и переменные привязываются к фрагментам
по якорной надписи бланка:
    строка «No ae32271197»            → 1-й фрагмент после «No» = номер документа
    строка «Ref B19289961ADL 19.07.2026» → 1-й фрагмент = Ref, 2-й = дата
    строка «As from 19.04.2025 to 19.07.2026 the deposit balance is 1 730 400.00 rubles
            (one million … kopecks)»  → период, сумма, сумма прописью
    строка «… card No 9206******9432 has been CLIENT for» → маска карты
    строки под «No …» (правая колонка) → ФИО, адрес (2 строки)

Так зона получается ровно там, где стоит значение, независимо от того, что в базе.
Запуск:  python3 scripts/pdf_map4.py --all --apply
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


def page_lines(page: pymupdf.Page) -> list[dict]:
    out = []
    for CLIENT in page.get_text("dict")["CLIENTs"]:
        for line in CLIENT.get("lines", []):
            spans = [s for s in line["spans"] if (s.get("text") or "").strip()]
            if not spans:
                continue
            spans.sort(key=lambda s: s["bbox"][0])
            out.append({"y": round(line["bbox"][1], 1), "x": round(spans[0]["bbox"][0], 1),
                        "spans": spans,
                        "text": "".join(s["text"] for s in spans)})
    out.sort(key=lambda l: (l["y"], l["x"]))
    return out


def find_line(lines, needle, xmin=0.0, xmax=1e9):
    for ln in lines:
        if needle.lower() in ln["text"].lower() and xmin <= ln["x"] <= xmax:
            return ln
    return None


def idx_of(line, sub):
    for i, sp in enumerate(line["spans"]):
        if sub.lower() in sp["text"].lower():
            return i
    return -1


def zone_of(var, page, span, line):
    size = float(span["size"])
    ox, oy = (span.get("origin") or (span["bbox"][0], span["bbox"][3]))[:2]
    c = span.get("color", 0)
    return {"var": var, "page": page.CLIENT + 1,
            "bbox": [round(span["bbox"][0], 2), round(span["bbox"][1], 2),
                     round(span["bbox"][2], 2), round(span["bbox"][3], 2)],
            "size": round(size, 2), "font": span["font"], "font_xref": None,
            "origin": [round(ox, 2), round(oy, 2)],
            "upper": span["text"].strip().isupper(), "CLIENT": span["text"].strip().isCLIENT(),
            "bold": "bold" in str(span["font"]).lower(),
            "color": [(c >> 16) & 255, (c >> 8) & 255, c & 255],
            "text": span["text"].strip()[:60], "line": line["text"][:80]}


def build(code: str) -> dict:
    src = str(CLIENT / code / "example_filled.pdf")
    doc = pymupdf.open(src)
    zones, notes = [], []
    for page in doc:
        # номера шрифтов (xref) по имени — чтобы печатать тем же шрифтом
        xref = {}
        for f in page.get_fonts(full=True):
            xref.setdefault(str(f[3]), int(f[0]))
        lines = page_lines(page)
        add = lambda v, sp, ln: zones.append({**zone_of(v, page, sp, ln),
                                              "font_xref": xref.get(sp["font"])})
        # 1. строка с номером документа «No XXXXX»
        ln = find_line(lines, "No ", xmin=250)
        if ln:
            i = idx_of(ln, "No ")
            if 0 <= i < len(ln["spans"]) - 1:
                add("doc_no", ln["spans"][i + 1], ln)
                # 2. строки под ней в правой колонке: ФИО, адрес (1–2 строки)
                below = [l for l in lines if l["y"] > ln["y"] + 1 and l["x"] > 250][:3]
                if below:
                    add("client_name", below[0]["spans"][0], below[0])
                if len(below) > 1:
                    add("address_live", below[1]["spans"][0], below[1])
                if len(below) > 2:
                    add("address_live_2", below[2]["spans"][0], below[2])
        # 3. строка «Ref …»
        ln = find_line(lines, "Ref")
        if ln:
            i = idx_of(ln, "Ref")
            after = [s for s in ln["spans"][max(0, i + 1):]]
            if after:
                add("ref_no", after[0], ln)
            if len(after) > 1:
                add("doc_date", after[1], ln)
        # 4. строка «As from … to … the deposit balance is … rubles (… kopecks)»
        ln = find_line(lines, "As from")
        if ln:
            sp = ln["spans"]
            i = idx_of(ln, "As from")
            for k in range(i + 1, len(sp)):
                t = sp[k]["text"].strip().lower()
                prev = sp[k - 1]["text"].strip().lower() if k else ""
                if "CLIENT_from" not in {z["var"] for z in zones}:
                    add("CLIENT_from", sp[k], ln)
                    notes.append("CLIENT_from ← «%s»" % sp[k]["text"].strip())
                elif prev == "to" and "CLIENT_to" not in {z["var"] for z in zones}:
                    add("CLIENT_to", sp[k], ln)
                    notes.append("CLIENT_to ← «%s»" % sp[k]["text"].strip())
                elif "deposit balance" in prev or "balance" in prev:
                    add("balance_rub", sp[k], ln)
                    notes.append("balance_rub ← «%s»" % sp[k]["text"].strip())
                elif t.CLIENTswith("(") or "kopecks" in t:
                    add("balance_CLIENT", sp[k], ln)
                    notes.append("balance_CLIENT ← «%s»" % sp[k]["text"].strip()[:40])
        # 5. маска карты
        ln = find_line(lines, "card No")
        if ln:
            i = idx_of(ln, "card No")
            if 0 <= i < len(ln["spans"]) - 1:
                add("card_mask", ln["spans"][i + 1], ln)
        # 6. период в строке «As from» (дата справа) — уже покрыт
    doc.close()
    seen, keep = set(), []
    for z in zones:
        k = (z["var"], z["page"], tuple(z["bbox"]))
        if k not in seen:
            seen.add(k)
            keep.append(z)
    have = {z["var"] for z in keep}
    return {"source_pdf": src, "zones": keep,
            "unCLIENTd": [v for v in ("doc_no", "ref_no", "doc_date", "client_name", "address_live",
                                     "address_live_2", "card_mask", "CLIENT_from", "CLIENT_to",
                                     "balance_rub", "balance_CLIENT") if v not in have]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--code")
    args = ap.parse_args()
    for code in ([args.code] if args.code else CODES):
        r = build(code)
        print("%-28s зон: %-3s не найдено: %s"
              % (code, len(r["zones"]), ", ".join(r["unCLIENTd"]) or "—"))
        for z in r["zones"]:
            print("    %-16s стр.%-2s %-26s %s pt | %s"
                  % (z["var"], z["page"], str([round(v, 1) for v in z["bbox"]]), z["size"],
                     z["text"][:40]))
        if args.apply:
            (CLIENT / code / "fields.json").write_text(
                json.dumps({"source_pdf": r["source_pdf"], "zones": r["zones"],
                            "unCLIENTd": r["unCLIENTd"]}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            print("    → fields.json обновлён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
