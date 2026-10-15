#!/usr/bin/env python3
"""Карта зон подстановки — версия 5. Разбор бланка по строкам, якорям и под-отрезкам.

Что учтено (это и было причиной наложений):
  • якорь и значение часто лежат в ОДНОМ фрагменте текста («No ae32271197»,
    «…card No 9206******9432 has been issued for») — значит зона = под-отрезок фрагмента,
    а не фрагмент целиком. Иначе затирается соседний текст, и новое значение печатается
    поверх старого (каша «B1952/8766/2026ADL»);
  • Ref и дата стоят на строке НИЖЕ подписи «Ref.» — их надо брать по колонке, а не по строке
    подписи;
  • период и сумма стоят в одной строке («As from … to … balance is … rubles (… kopecks)») —
    зоны берутся по фрагментам этой строки;
  • ФИО и адрес — строки под номером документа в правой колонке (адрес в две строки).

Запуск:  python3 scripts/pdf_map5.py --all --apply [--code <code>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

BASE = Path("/opt/wolf_v2")
TEMPLATES = BASE / "data" / "templates"
CODES = ["bank_statement_3m__tbank", "bank_statement_3m__sber",
         "bank_statement_12m__tbank", "bank_statement_12m__sber"]
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def lines_of(page):
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if (s.get("text") or "").strip()]
            if not spans:
                continue
            spans.sort(key=lambda s: s["bbox"][0])
            out.append({"y": round(line["bbox"][1], 1), "x": round(spans[0]["bbox"][0], 1),
                        "spans": spans, "text": "".join(s["text"] for s in spans)})
    out.sort(key=lambda l: (l["y"], l["x"]))
    return out


class Fonts:
    """Метрики шрифтов: чтобы считать под-отрезок внутри фрагмента."""

    def __init__(self, doc, page):
        self.doc = doc
        self.cache = {}
        self.xref = {}
        for f in page.get_fonts(full=True):
            self.xref.setdefault(str(f[3]), int(f[0]))

    def obj(self, name):
        if name in self.cache:
            return self.cache[name]
        f = None
        x = self.xref.get(name)
        if x:
            try:
                _n, ext, _t, buf = self.doc.extract_font(int(x))
                p = Path("/tmp/_m5_%s.%s" % (x, ext or "ttf"))
                if not p.exists():
                    p.write_bytes(buf)
                f = pymupdf.Font(fontfile=str(p))
            except Exception:
                f = None
        if f is None:
            f = pymupdf.Font("hebo" if "bold" in str(name).lower() else "helv")
        self.cache[name] = f
        return f


def subzone(doc, page, span, part: str, var: str, note: str) -> dict | None:
    """Под-отрезок внутри фрагмента: находим part в тексте фрагмента и считаем его границы."""
    t = span["text"]
    i = t.find(part)
    if i < 0:
        return None
    fonts = Fonts(doc, page)
    fobj = fonts.obj(span["font"])
    size = float(span["size"])
    ox, oy = (span.get("origin") or (span["bbox"][0], span["bbox"][3]))[:2]
    try:
        dx = fobj.text_length(t[:i], fontsize=size)
        w = fobj.text_length(part, fontsize=size)
    except Exception:
        dx, w = 0.0, span["bbox"][2] - span["bbox"][0]
    c = span.get("color", 0)
    return {"var": var, "page": page.number + 1,
            "bbox": [round(ox + dx, 2), round(span["bbox"][1], 2),
                     round(ox + dx + w, 2), round(span["bbox"][3], 2)],
            "size": round(size, 2), "font": span["font"], "font_xref": fonts.xref.get(span["font"]),
            "origin": [round(ox + dx, 2), round(oy, 2)],
            "upper": part.strip().isupper(), "title": part.strip().istitle(),
            "bold": "bold" in str(span["font"]).lower(),
            "color": [(c >> 16) & 255, (c >> 8) & 255, c & 255],
            "text": part.strip()[:60], "note": note}


def build(code: str) -> dict:
    src = str(TEMPLATES / code / "example_filled.pdf")
    doc = pymupdf.open(src)
    zones, unplaced = [], []

    def take(z):
        if z and not any(x["var"] == z["var"] and x["page"] == z["page"]
                         and x["bbox"] == z["bbox"] for x in zones):
            zones.append(z)

    for page in doc:
        lines = lines_of(page)
        # 1. номер документа: «No <значение>» (не путать с «card No» и «license … No 9441»)
        for ln in lines:
            for sp in ln["spans"]:
                m = re.search(r"\bNo\s+(\S+)", sp["text"])
                if not m:
                    continue
                low = sp["text"].lower()
                if "card no" in low or "license" in low or "bank of russia" in low:
                    continue
                if m.group(1).strip(".,;:").isdigit() and len(m.group(1)) < 6:
                    continue                      # «No 9441» — это номер лицензии, не наш
                take(subzone(doc, page, sp, m.group(1), "doc_no", "после «No »"))
        # 2. ФИО и адрес — строки под номером документа в правой колонке
        no_line = None
        for ln in lines:
            if ln["x"] > 250 and re.search(r"\bNo\s+\S", ln["text"]) and "card" not in ln["text"].lower():
                no_line = ln
                break
        if no_line:
            below = [l for l in lines if l["y"] > no_line["y"] + 2 and l["x"] > 250][:3]
            if below:
                take({**subzone(doc, page, below[0]["spans"][0], below[0]["spans"][0]["text"].strip(),
                                "client_name", "строка под «No …»"), "bbox": [round(v, 2) for v in below[0]["spans"][0]["bbox"]]})
            if len(below) > 1:
                sp = below[1]["spans"][0]
                take({**subzone(doc, page, sp, sp["text"].strip(), "address_live", "адрес, строка 1"),
                      "bbox": [round(v, 2) for v in sp["bbox"]]})
            if len(below) > 2:
                sp = below[2]["spans"][0]
                take({**subzone(doc, page, sp, sp["text"].strip(), "address_live_2", "адрес, строка 2"),
                      "bbox": [round(v, 2) for v in sp["bbox"]]})
        # 3. Ref и дата: если в строке с «Ref» нет значения — берём следующую строку в той же колонке
        for ln in lines:
            if ln["text"].strip().lower().startswith("ref"):
                cand = ln
                rest = ln["text"].strip()[3:].strip(" .:«»")
                if not rest:
                    nxt = [l for l in lines if l["y"] > ln["y"] + 1 and abs(l["x"] - ln["x"]) < 25]
                    cand = nxt[0] if nxt else None
                if cand is None:
                    continue
                words = [w for w in cand["text"].strip().split() if w]
                sp_all = cand["spans"][0]
                if words:
                    take(subzone(doc, page, sp_all, words[0], "ref_no", "строка Ref, слово 1"))
                if len(words) > 1 and DATE_RE.match(words[1].strip(".,;")):
                    take(subzone(doc, page, sp_all, words[1], "doc_date", "строка Ref, дата"))
                break
        # 4. период и сумма: строка «As from … to … balance is … rubles (… kopecks)»
        for ln in lines:
            if "as from" not in ln["text"].lower():
                continue
            sp = ln["spans"]
            for i, s in enumerate(sp):
                t = s["text"].strip().lower()
                if "as from" in t and i + 1 < len(sp):
                    take({**subzone(doc, page, sp[i + 1], sp[i + 1]["text"].strip(), "period_from", "после «As from»"),
                          "bbox": [round(v, 2) for v in sp[i + 1]["bbox"]]})
                if t == "to" and i + 1 < len(sp):
                    take({**subzone(doc, page, sp[i + 1], sp[i + 1]["text"].strip(), "period_to", "после «to»"),
                          "bbox": [round(v, 2) for v in sp[i + 1]["bbox"]]})
                if "balance" in t and i + 1 < len(sp):
                    nxt = sp[i + 1]
                    take({**subzone(doc, page, nxt, nxt["text"].strip(" ."), "balance_rub", "после «balance is»"),
                          "bbox": [round(v, 2) for v in nxt["bbox"]]})
                elif ("kopecks" in t or t.startswith("(")) and i and "balance" in sp[i - 1]["text"].lower():
                    if "kopecks" not in t:
                        continue
                if "kopecks" in t and "balance_words" not in {z["var"] for z in zones}:
                    inner = s["text"].strip()
                    take({**subzone(doc, page, s, inner, "balance_words", "сумма прописью"),
                          "bbox": [round(v, 2) for v in s["bbox"]]})
            # строка может быть набрана ОДНИМ фрагментом — тогда вырезаем значения регуляркой
            for s in sp:
                for var, pat, note in (
                        ("period_from", r"As from\s+([\d]{2}\.[\d]{2}\.[\d]{4})", "«As from» → дата"),
                        ("period_to", r"\bto\s+([\d]{2}\.[\d]{2}\.[\d]{4})", "«to» → дата"),
                        ("balance_rub", r"balance is\s+([\d][\d\s\u00a0]*[.,][\d]{2})", "«balance is» → сумма"),
                        ("balance_words", r"(\([^()]*?kopecks?\))", "сумма прописью")):
                    if var in {z["var"] for z in zones}:
                        continue
                    m = re.search(pat, s["text"], re.I)
                    if m:
                        take(subzone(doc, page, s, m.group(1), var, note))
        # 5. страничный проход: сумма прописью может быть набрана несколькими фрагментами
        #    («(one million … thirty thousand» + «four hundred rubles 00 kopecks)»)
        sp_all = []
        for ln in lines:
            sp_all.extend(ln["spans"])
        sp_all.sort(key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))
        if "balance_words" not in {z["var"] for z in zones}:
            for i, s in enumerate(sp_all):
                low = s["text"].lower()
                if "(" not in s["text"] and "kopecks" not in low:
                    continue
                if "kopecks" in low and "(" not in s["text"]:
                    # хвост фразы — присоединяем к началу, если он рядом
                    prev = sp_all[i - 1] if i else None
                    if prev and abs(prev["bbox"][1] - s["bbox"][1]) < 6 and prev["bbox"][2] <= s["bbox"][0] + 2:
                        z = subzone(doc, page, prev, prev["text"].strip(), "balance_words", "сумма прописью (2 фрагмента)")
                        if z:
                            z["wipe"] = [[round(v, 2) for v in prev["bbox"]],
                                         [round(v, 2) for v in s["bbox"]]]
                            take(z)
                elif "kopecks" in low and "(" in s["text"]:
                    take({**subzone(doc, page, s, s["text"].strip(), "balance_words", "сумма прописью"),
                          "bbox": [round(v, 2) for v in s["bbox"]]})

        # 7. ФИО в абзаце: «… issued for <ФИО>» — либо в том же фрагменте, либо в строке ниже
        for ln in lines:
            hit = False
            for s in ln["spans"]:
                m = re.search(r"issued for\s+(.+?)\s*$", s["text"], re.I)
                if m and len(m.group(1).strip().rstrip(".")) > 5 and " " in m.group(1):
                    part = m.group(1).strip().rstrip(".")
                    take(subzone(doc, page, s, part, "client_name", "ФИО в абзаце"))
                    hit = True
            if hit:
                continue
            if "issued for" in ln["text"].lower():
                below = [l for l in lines if l["y"] > ln["y"] + 1 and abs(l["x"] - ln["x"]) < 40]
                if below:
                    sp = below[0]["spans"][0]
                    txt = sp["text"].strip().rstrip(".")
                    if len(txt) > 5 and " " in txt:
                        take({**subzone(doc, page, sp, txt, "client_name", "ФИО, строка под «issued for»"),
                              "bbox": [round(v, 2) for v in sp["bbox"]]})
        # 6. маска карты: между «card No » и «has been issued»
        for ln in lines:
            for s in ln["spans"]:
                m = re.search(r"card\s+No\s+(\S+)", s["text"])
                if m:
                    take(subzone(doc, page, s, m.group(1).rstrip(".,"), "card_mask", "после «card No»"))
    doc.close()

    have = {z["var"] for z in zones}
    unplaced = [v for v in ("doc_no", "ref_no", "doc_date", "client_name", "address_live",
                            "address_live_2", "card_mask", "period_from", "period_to",
                            "balance_rub", "balance_words") if v not in have]
    return {"source_pdf": src, "zones": zones, "unplaced": unplaced}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--code")
    args = ap.parse_args()
    for code in ([args.code] if args.code else CODES):
        r = build(code)
        print("%-28s зон: %-3s не найдено: %s"
              % (code, len(r["zones"]), ", ".join(r["unplaced"]) or "—"))
        for z in r["zones"]:
            print("    %-15s стр.%-2s %-26s %s pt | %-24s | %s"
                  % (z["var"], z["page"], str([round(v, 1) for v in z["bbox"]]), z["size"],
                     z["text"][:22], z["note"]))
        if args.apply:
            (TEMPLATES / code / "fields.json").write_text(
                json.dumps({"source_pdf": r["source_pdf"], "zones": r["zones"],
                            "unplaced": r["unplaced"]}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            print("    → fields.json обновлён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
