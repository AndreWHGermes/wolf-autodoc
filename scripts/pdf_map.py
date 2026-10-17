#!/usr/bin/env python3
"""Карта зон подстановки для PDF-оригинала: где в документе стоит каждое значение.

Как работает: берём НАСТОЯЩИЙ заполненный PDF документа (эталон) и значения переменных
шаблона из базы (это те же значения, из которых собран эталон). Для каждой переменной ищем
её текст в PDF:
  • точное совпадение отрезка (span) → это зона значения;
  • если переменная встречается в документе несколько раз — записываем все зоны
    (одна переменная = много зон, это нормально: ФИО и в шапке, и в абзаце);
  • если значение — часть более длинного отрезка (например «No ae32271197»), берём
    подстроку и считаем её прямоугольник по ширине символов.

Результат: data/templates/<code>/fields.json
    { "source_pdf": …, "zones": [ {var, page, bbox, size, font, text, font_xref, font_file} ] }

Запуск:
    python3 scripts/pdf_map.py --code bank_statement_3m__tbank          # посмотреть
    python3 scripts/pdf_map.py --code bank_statement_3m__tbank --apply   # записать fields.json
    python3 scripts/pdf_map.py --all --apply                             # по всем справкам
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

BASE = Path("/opt/wolf_v2")
sys.path.insert(0, str(BASE))
TEMPLATES = BASE / "data" / "templates"
CODES = ["bank_statement_3m__tbank", "bank_statement_3m__sber",
         "bank_statement_12m__tbank", "bank_statement_12m__sber"]


def template_values(code: str) -> dict[str, str]:
    """Образцы значений переменных шаблона из базы (то, чем заполнен эталон)."""
    from app import app
    with app.app_context():
        from core import db
        t = db.q1("SELECT id FROM templates WHERE code=?", (code,))
        if not t:
            return {}
        rows = db.q("SELECT name, COALESCE(default_value,'') AS dv FROM template_variables "
                    "WHERE template_id=? ORDER BY sort_order, name", (t["id"],)) or []
    vals = {}
    for r in rows:
        v = (r["dv"] or "").strip()
        if len(v) >= 2:
            vals[r["name"]] = v
    return vals


def _style_of(span: dict) -> dict:
    """Стиль отрезка: как в оригинале набран текст — регистр, жирность, цвет, точка начала.
    Новое значение печатается тем же кеглем и тем же начертанием, что в оригинале."""
    t = (span.get("text") or "").strip()
    try:
        color = span.get("color", 0)
        rgb = ((color >> 16) & 255, (color >> 8) & 255, color & 255)
    except Exception:
        rgb = (0, 0, 0)
    return {
        "origin": [round(v, 2) for v in (span.get("origin") or (span["bbox"][0], span["bbox"][3]))],
        "upper": bool(t) and t.isupper(),
        "title": bool(t) and t.istitle(),
        "bold": "bold" in str(span.get("font") or "").lower(),
        "color": list(rgb),
    }


def spans_of(page: pymupdf.Page) -> list[dict]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for sp in line["spans"]:
                out.append(sp)
    return out


def font_xref_for(page: pymupdf.Page, font_name: str) -> int | None:
    for f in page.get_fonts(full=True):
        if str(f[3]) == font_name:
            return int(f[0])
    return None


def rect_of_text(page: pymupdf.Page, span: dict, sub: str) -> list[float] | None:
    """Прямоугольник подстроки внутри отрезка (по ширине символов тем же кеглем)."""
    text = span["text"]
    i = text.find(sub)
    if i < 0:
        return None
    font = pymupdf.Font(fontfile=span.get("_fontfile") or None) if span.get("_fontfile") else None
    if font is None:
        try:
            font = pymupdf.Font(fontname=span["font"].split("-")[0].lower())
        except Exception:
            font = pymupdf.Font("helv")
    before = font.text_length(text[:i], fontsize=span["size"])
    width = font.text_length(sub, fontsize=span["size"])
    x0, y0, x1, y1 = span["bbox"]
    return [round(x0 + before, 2), y0, round(x0 + before + width, 2), y1]


def build_map(code: str) -> dict:
    src = TEMPLATES / code / "example_filled.pdf"
    if not src.exists():
        return {"error": "нет эталона example_filled.pdf"}
    vals = template_values(code)
    if not vals:
        return {"error": "в базе нет значений переменных"}
    doc = pymupdf.open(str(src))
    zones, used = [], set()
    for name, value in vals.items():
        needle = value.strip()
        found = 0
        for page in doc:
            for span in spans_of(page):
                text = span["text"]
                if not text.strip():
                    continue
                if needle == text.strip():
                    rect = [round(v, 2) for v in span["bbox"]]
                elif needle.lower() in text.lower():
                    rect = rect_of_text(page, span, needle)
                else:
                    continue
                if not rect:
                    continue
                key = (page.number, tuple(round(v, 1) for v in rect), name)
                if key in used:
                    continue
                used.add(key)
                fx = font_xref_for(page, span["font"])
                zones.append({"var": name, "page": page.number + 1, "bbox": rect,
                              "size": round(span["size"], 2), "font": span["font"],
                              "font_xref": fx, "text": needle[:60],
                              **_style_of(span)})
                found += 1
        if not found:
            # Второй проход: значение может быть разбито по строкам (адрес) или заменено
            # другой формулировкой (сумма прописью). Ищем по частям.
            parts = [p.strip() for p in needle.replace(",", " , ").split("  ") if len(p.strip()) >= 8]
            sub_found = 0
            if len(needle) >= 12:
                for page in doc:
                    for span in spans_of(page):
                        t = span["text"].strip()
                        if len(t) < 8:
                            continue
                        if t and (t in needle or (name == "balance_words" and "kopecks" in t.lower())):
                            rect = [round(v, 2) for v in span["bbox"]]
                            key = (page.number, tuple(round(v, 1) for v in rect), name)
                            if key in used:
                                continue
                            used.add(key)
                            zones.append({"var": name, "page": page.number + 1, "bbox": rect,
                                          "size": round(span["size"], 2), "font": span["font"],
                                          "font_xref": font_xref_for(page, span["font"]),
                                          "text": t[:60], "note": "зона найдена по части строки",
                                          **_style_of(span)})
                            sub_found += 1
                            if sub_found >= 3:
                                break
            if not sub_found:
                zones.append({"var": name, "page": 0, "bbox": None, "size": None,
                              "font": None, "font_xref": None, "text": needle[:60],
                              "note": "не найдено в эталоне"})
    doc.close()
    return {"source_pdf": str(src), "code": code, "zones": zones}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    codes = CODES if args.all else ([args.code] if args.code else [])
    if not codes:
        print("укажи --code или --all")
        return 1
    for code in codes:
        res = build_map(code)
        if res.get("error"):
            print("%-28s ОШИБКА: %s" % (code, res["error"]))
            continue
        ok = [z for z in res["zones"] if z["bbox"]]
        bad = [z for z in res["zones"] if not z["bbox"]]
        multi = len(ok) - len({z["var"] for z in ok})
        print("%-28s зон найдено %-3s (переменных %s, доп. мест %s) · не найдено: %s"
              % (code, len(ok), len({z["var"] for z in ok}), multi,
                 ", ".join(z["var"] for z in bad) or "нет"))
        if args.apply:
            out = TEMPLATES / code / "fields.json"
            out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            print("%-28s карта записана: %s" % ("", out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
