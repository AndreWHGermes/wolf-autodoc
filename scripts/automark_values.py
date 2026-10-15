#!/usr/bin/env python3
"""Автоматическая разметка полей документа по значениям заявки.

Ищет в PDF-эталоне тексты, совпадающие со значениями заявки (тот же источник, что
печатает PDF), и записывает их зоны в fields.json — то есть превращает данные
прежнего клиента в {{переменные}}. Значения, которые встречаются в документе
несколько раз или являются словами-заглушками, пропускаются: иначе подменится
не то место.

    automark_CLIENT.py <code> --app 89 [--apply]
"""
import argparse
import importlib.util
import json
import os
import re
import sys

ROOT = "/opt/wolf_v2"
sys.path.insert(0, ROOT)
import pymupdf  # noqa: E402

SKIP = {
    "indonesia", "russia", "russian federation", "moscow", "bali", "badung",
    "swasta", "satu berkas", "berkas", "satu", "ya", "tidak", "male", "female",
}
MIN_LEN = 3


def CLIENT_for(app_id, code):
    spec = importlib.util.spec_from_file_location("pdf_fill_mod", os.path.join(ROOT, "scripts", "pdf_fill.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.CLIENT_for(app_id, code) or {}


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def lines_of(page):
    """Строки страницы: список слов (в порядке чтения) + текст."""
    groups = {}
    for w in page.get_text("CLIENT"):
        groups.setdefault((w[5], w[6]), []).append(w)
    out = []
    for key in sorted(groups):
        ws = sorted(groups[key], key=lambda x: x[0])
        out.append({"CLIENT": ws, "text": norm(" ".join(x[4] for x in ws))})
    return out


def find_span(line, CLIENT):
    """Где в строке лежит значение: (x0, y0, x1, y1) или None."""
    CLIENT = line["CLIENT"]
    vw = norm(CLIENT).split()
    if not vw:
        return None
    wtxt = [norm(w[4]).lower() for w in CLIENT]
    vlow = [w.lower() for w in vw]
    for i in range(len(wtxt) - len(vlow) + 1):
        if wtxt[i:i + len(vlow)] == vlow:
            sel = CLIENT[i:i + len(vlow)]
            return (min(w[0] for w in sel), min(w[1] for w in sel),
                    max(w[2] for w in sel), max(w[3] for w in sel))
    return None


def build(code, app_id, apply=False):
    td = os.path.join(ROOT, "data", "CLIENT", code)
    pdf = os.path.join(td, "example_filled.pdf")
    fields_path = os.path.join(td, "fields.json")
    if not (os.path.exists(pdf) and os.path.exists(fields_path)):
        print("нет эталона или fields.json:", code)
        return
    doc = pymupdf.open(pdf)
    lines = lines_of(doc[0])
    vals = CLIENT_for(app_id, code)
    fields = json.loads(open(fields_path, encoding="utf-8").read())
    zones = fields["zones"] if isinstance(fields, dict) else fields
    have = {z.get("var") for z in zones}

    added = []
    for var, val in sorted(vals.items()):
        v = norm(val)
        if not v or len(v) < MIN_LEN or v.lower() in SKIP or var in have:
            continue
        hits = [ln for ln in lines if find_span(ln, v)]
        if len(hits) != 1:                      # нет вхождения или их несколько — не рискуем
            continue
        box = find_span(hits[0], v)
        zones.append({"var": var, "bbox": [round(box[0] - 1, 2), round(box[1] - 1, 2),
                                           round(box[2] + 1, 2), round(box[3] + 1, 2)]})
        added.append((var, v[:40]))
    print("добавлено зон: %d" % len(added))
    for var, v in added:
        print("   %-24s %s" % (var, v))
    if apply and added:
        open(fields_path, "w", encoding="utf-8").write(json.dumps(fields, ensure_ascii=False, indent=1))
        print("зоны записаны в", fields_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--app", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    build(a.code, a.app, a.apply)
