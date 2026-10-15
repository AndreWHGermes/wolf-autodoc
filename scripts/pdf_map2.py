#!/usr/bin/env python3
"""Карта зон подстановки для PDF-оригинала — версия 2.

Почему переписано. В первой версии зона = ВЕСЬ фрагмент текста, в котором найдено значение.
Если в одной строке PDF стоят два значения (например «B19289961ADL 19.07.2026» — Ref и дата,
или «card No 9206******9432 has been issued for» — значение и текст бланка), то зона накрывала
соседний текст: затирание шло по чужим символам, а новое значение печаталось поверх старого —
отсюда каша вида «B1952/8766/2026 ADL».

Теперь зона — ТОЧНЫЙ отрезок внутри фрагмента: вычисляется по метрикам шрифта от начала
фрагмента до значения. Соседние значения в той же строке не задеваются. Дополнительно:
  • зоны, пересекающиеся между собой, разрешаются в пользу более длинного (специфичного) значения;
  • в карте сохраняются точка начала (origin), кегль, шрифт, начертание, цвет и регистр оригинала.

Запуск:  python3 scripts/pdf_map.py --all --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

BASE = Path("/opt/wolf_v2")
TEMPLATES = BASE / "data" / "templates"
CODES = ["bank_statement_3m__tbank", "bank_statement_3m__sber",
         "bank_statement_12m__tbank", "bank_statement_12m__sber"]


def spans_of(page: pymupdf.Page) -> list[dict]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for sp in line["spans"]:
                if (sp.get("text") or "").strip():
                    out.append(sp)
    return out


def font_xref_for(page: pymupdf.Page, name: str):
    for f in page.get_fonts(full=True):
        if str(f[3]) == name:
            return int(f[0])
    return None


def style(span: dict, needle: str, origin_x: float) -> dict:
    c = span.get("color", 0)
    rgb = [(c >> 16) & 255, (c >> 8) & 255, c & 255]
    oy = (span.get("origin") or (span["bbox"][0], span["bbox"][3]))[1]
    return {
        "origin": [round(origin_x, 2), round(oy, 2)],
        "upper": needle.isupper(),
        "title": needle.istitle(),
        "bold": "bold" in str(span.get("font") or "").lower(),
        "color": rgb,
    }


def values_from_db(code: str) -> dict:
    """Эталонные значения: default_value переменных шаблона (по ним собран example_filled.pdf)."""
    sys.path.insert(0, str(BASE))
    from app import app
    with app.app_context():
        from core import db
        rows = db.q("""SELECT v.name, v.default_value FROM template_variables v
                       JOIN templates t ON t.id = v.template_id
                       WHERE t.code = ?""", (code,))
    vals = {}
    for r in rows:
        v = (r["default_value"] or "").strip()
        if len(v) >= 4 and not v.startswith("{{"):
            vals[r["name"]] = v
    return vals


def build(code: str) -> dict:
    src = str(TEMPLATES / code / "example_filled.pdf")
    tpl_pdf = TEMPLATES / code / "template.pdf"
    if tpl_pdf.exists():
        src = str(tpl_pdf)
    vals = values_from_db(code)
    doc = pymupdf.open(src)
    # длинные значения — первыми: они важнее при разрешении пересечений
    needles = sorted(vals.items(), key=lambda kv: -len(kv[1]))

    zones: list[dict] = []
    for page in doc:
        sp_list = spans_of(page)
        fobj_cache: dict[str, object] = {}
        for name, needle in needles:
            for sp in sp_list:
                t = sp["text"]
                i = t.find(needle)
                if i < 0:
                    continue
                xref = font_xref_for(page, sp["font"])
                key = "%s|%s" % (sp["font"], xref)
                fobj = fobj_cache.get(key)
                if fobj is None:
                    fobj = None
                    if xref:
                        try:
                            _n, ext, _t, buf = doc.extract_font(int(xref))
                            p = Path("/tmp/_map_font_%s.%s" % (xref, ext or "ttf"))
                            p.write_bytes(buf)
                            fobj = pymupdf.Font(fontfile=str(p))
                        except Exception:
                            fobj = None
                    fobj_cache[key] = fobj
                size = float(sp["size"])
                x0 = (sp.get("origin") or (sp["bbox"][0], sp["bbox"][3]))[0]
                try:
                    dx = (fobj or pymupdf.Font("helv")).text_length(t[:i], fontsize=size)
                    w = (fobj or pymupdf.Font("helv")).text_length(needle, fontsize=size)
                except Exception:
                    dx = 0.0
                    w = sp["bbox"][2] - sp["bbox"][0]
                zx0 = round(x0 + dx, 2)
                zone = {"var": name, "page": page.number + 1,
                        "bbox": [zx0, round(sp["bbox"][1], 2), round(zx0 + w, 2), round(sp["bbox"][3], 2)],
                        "size": round(size, 2), "font": sp["font"], "font_xref": xref,
                        "text": needle[:60], "exact": (i == 0 and len(t) == len(needle))}
                zone.update(style(sp, needle, zx0))
                zones.append(zone)

    # пересечения: оставляем более длинное (специфичное) значение, короткое отбрасываем
    def overlap(a: dict, b: dict) -> bool:
        if a["page"] != b["page"]:
            return False
        ax0, ay0, ax1, ay1 = a["bbox"]
        bx0, by0, bx1, by1 = b["bbox"]
        return not (ax1 <= bx0 + 0.5 or bx1 <= ax0 + 0.5 or ay1 <= by0 + 0.5 or by1 <= ay0 + 0.5)

    keep, dropped = [], []
    for z in sorted(zones, key=lambda x: -len(x["text"])):
        if any(overlap(z, k) for k in keep):
            dropped.append(z)
        else:
            keep.append(z)
    doc.close()
    return {"code": code, "source_pdf": src, "zones": keep, "dropped": dropped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--code")
    args = ap.parse_args()
    codes = [args.code] if args.code else CODES
    for code in codes:
        r = build(code)
        print("%-28s зон: %-3s (отброшено по пересечению: %s)"
              % (code, len(r["zones"]), len(r["dropped"])))
        for z in r["zones"]:
            print("    %-16s стр.%-2s %s  %s pt  %s"
                  % (z["var"], z["page"], [round(v, 1) for v in z["bbox"]], z["size"],
                     "★точно" if z["exact"] else ""))
        if args.apply:
            f = TEMPLATES / code / "fields.json"
            f.write_text(json.dumps({"source_pdf": r["source_pdf"], "zones": r["zones"]},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
            print("    → записано", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
