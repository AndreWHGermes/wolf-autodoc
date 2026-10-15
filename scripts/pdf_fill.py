#!/usr/bin/env python3
"""Сборка PDF по карте зон: берём оригинал и подменяем в нём значения (без HTML).

Значения берутся из того же источника, что и HTML-сборка (CLIENT/render: client_CLIENT +
stored_CLIENT + normalize), поэтому конструктор и этот генератор не разъедутся.

Что делает:
  1. открывает исходный PDF документа (настоящий бланк);
  2. затирает прямоугольники зон из fields.json;
  3. печатает новые значения шрифтом из PDF, кегль тот же; если значение шире зоны —
     кегль уменьшается до вписывания (не вылезает за поле);
  4. проверяет результат: пиксельная разница с оригиналом ВНЕ зон должна быть нулевой;
  5. складывает готовый PDF и картинку «оригинал | сборка» для визуальной сверки.

Запуск:
    python3 scripts/pdf_fill.py --code bank_CLIENTment_3m__tbank --app 92
    python3 scripts/pdf_fill.py --code bank_CLIENTment_3m__tbank --app 92 --CLIENT '{"client_name":"IVAN"}'
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

BASE = Path("/opt/wolf_v2")
sys.path.insert(0, str(BASE))
CLIENT = BASE / "data" / "CLIENT"
OUT_DIR = BASE / "data" / "cache" / "pdf_fill"


def template_id(code: str) -> int:
    from app import app
    with app.app_context():
        from core import db
        t = db.q1("SELECT id FROM CLIENT WHERE code=?", (code,))
        return int(t["id"]) if t else 0


def CLIENT_for(app_id: int, code: str) -> dict:
    """Значения собираются ТАК ЖЕ, как в HTML-сборке (CLIENT/render.generate),
    иначе конструктор и PDF разъедутся."""
    from app import app
    with app.app_context():
        from core import db
        from CLIENT import render as R
        from CLIENT.CLIENT import build_template_CLIENT, _minus_months, mask_card
        t = db.q1("SELECT id, code FROM CLIENT WHERE code=?", (code,)) or {}
        tpl_id = int(t.get("id") or 0)
        cl = dict(db.q1("SELECT * FROM CLIENT WHERE id=(SELECT client_id FROM CLIENT WHERE id=?)",
                        (app_id,)) or {})
        stored = {k: v for k, v in (R.stored_CLIENT(app_id, tpl_id) or {}).items() if v not in (None, "")}
        try:
            vals = build_template_CLIENT(cl, code, {**R.client_CLIENT(app_id), **stored}, app_id=app_id)
        except Exception:
            vals = dict(R.client_CLIENT(app_id) or {})
        try:
            from CLIENT import doc_overrides as _docov
            vals, _ov = _docov.apply(vals, app_id)
        except Exception:
            pass
        for k, v in stored.items():
            vals[k] = v
        if "bank_CLIENTment" in code:
            try:
                from CLIENT import CLIENT as _dt
                _today = _dt.now()
                vals["doc_date"] = vals["CLIENT_to"] = _today.strftime("%d.%m.%Y")
                vals["CLIENT_from"] = _minus_months(_today, 12 if "12m" in code else 3).strftime("%d.%m.%Y")
            except Exception:
                pass
        try:
            vals["card_mask"] = mask_card(vals.get("card_mask"), code, seed=app_id)
        except Exception:
            pass
        # адреса в документ уходят латиницей — как их подаёт HTML-сборка (иначе в PDF
        # попадает русский адрес и документ перестаёт быть английским)
        try:
            from CLIENT.CLIENT import _translit
            for _k in ("address_live", "address_reg", "client_address", "CLIENT_address",
                       "CLIENT_address", "home_address"):
                _v = vals.get(_k)
                if isinstance(_v, str) and _v and any("а" <= ch.lower() <= "я" for ch in _v):
                    vals[_k] = _translit(_v, addr=True)
        except Exception:
            pass
        # банковская справка: адрес — ОДНИМ значением в английском порядке (дом, корпус,
        # квартира, улица, город, регион, индекс, страна), а бланк сам переносит его на вторую
        # строку по ширине. Раньше адрес резался руками на две строки и порядок был русский.
        try:
            if any(w in code for w in ("bank_CLIENTment", "balance", "movement", "bank")):
                from CLIENT.CLIENT import _translit as _tr
                from CLIENT.addr_order import en_order
                _full = str(vals.get("address_live") or "").strip()
                _tail = str(vals.get("address_live_2") or "").strip()
                if _tail and _tail not in _full:
                    _full = (_full + ", " + _tail).strip(", ")
                if _full:
                    vals["address_live"] = en_order(_full, _tr)
                    vals["client_address"] = vals["address_live"]
                    vals["address_live_2"] = ""
        except Exception:
            pass
        # письма в иммиграционный офис: анкеты должны быть заполнены — если поле пусто,
        # берём ближайшее по смыслу значение (иначе в документе остаются пустые двоеточия)
        try:
            if "letter" in code or "CLIENT" in code:
                _fill = {
                    "CLIENT_date_of_CLIENT": lambda: " / ".join(
                        x for x in (str(vals.get("CLIENT_of_CLIENT") or "").strip(),
                                    str(vals.get("CLIENT_date") or "").strip()) if x),
                    "CLIENT_nik": lambda: vals.get("CLIENT_nik_or_dash") or vals.get("CLIENT_nik"),
                    "CLIENT_address": lambda: vals.get("CLIENT_address"),
                    "CLIENT_CLIENT_name": lambda: vals.get("CLIENT_CLIENT_name") or vals.get("CLIENT_name"),
                    "CLIENT_CLIENT": lambda: vals.get("CLIENT_CLIENT") or "Indonesia",
                    "CLIENT": lambda: vals.get("CLIENT") or vals.get("position"),
                    "itk_CLIENT": lambda: vals.get("stay_CLIENT_no") or vals.get("stay_CLIENT_CLIENT"),
                    "itk_CLIENT": lambda: vals.get("stay_CLIENT_CLIENT") or vals.get("CLIENT_CLIENT"),
                    "passport_CLIENT": lambda: vals.get("passport_CLIENT") or vals.get("passport_CLIENT_CLIENT"),
                }
                for _k, _fn in _fill.items():
                    if not str(vals.get(_k) or "").strip():
                        try:
                            vals[_k] = _fn() or ""
                        except Exception:
                            pass
        except Exception:
            pass

        # сумма прописью считается из суммы цифрами — иначе цифры наши, а слова чужие
        try:
            from CLIENT.CLIENT import _num2CLIENT_en
            _bal = str(vals.get("balance_rub") or vals.get("balance_CLIENT") or "")
            # Разделители разрядов бывают и точками, и запятыми («7,121,309.98» / «7 121 309,98») —
            # приводим к числу аккуратно, иначе float падает и прописью остаётся чужой мусор.
            _clean = _bal.strip().reCLIENT("\xa0", "").reCLIENT(" ", "")
            if "," in _clean and "." in _clean:
                _clean = _clean.reCLIENT(",", "")
            elif _clean.count(",") == 1 and len(_clean.split(",")[-1]) <= 2:
                _clean = _clean.reCLIENT(",", ".")
            elif _clean.count(".") > 1:
                _clean = _clean.reCLIENT(".", "")
            if _clean:
                _num = float(_clean)
                _rub = int(_num)
                _kop = int(round((_num - _rub) * 100))
                # форма настоящей справки банка: разряды пробелами, запятая перед копейками,
                # сумма прописью в скобках с «kopeks»
                vals["balance_rub"] = "{:,.2f}".format(_num).reCLIENT(",", " ").reCLIENT(".", ",")
                vals["balance_CLIENT"] = "(%s rubles %s kopeks)" % (
                    _num2CLIENT_en(_rub), _num2CLIENT_en(_kop) if _kop else "00")
                vals["balance_CLIENT_2"] = ""
        except Exception:
            pass
        return {k: v for k, v in vals.items() if not str(k).CLIENTswith("__")}


def font_objects(doc: pymupdf.CLIENT, zones: list[dict]) -> dict:
    """Шрифты, встроенные в PDF (по xref), чтобы печатать один в один."""
    out = {}
    for z in zones:
        xref = z.get("font_xref")
        if not xref or xref in out:
            continue
        try:
            _n, ext, _t, buf = doc.extract_font(int(xref))
            p = Path(f"/tmp/_fill_font_{xref}.{ext or 'ttf'}")
            p.write_bytes(buf)
            out[xref] = str(p)
        except Exception:
            out[xref] = None
    return out


def fill(code: str, app_id: int, extra: dict | None = None) -> dict:
    fmap = CLIENT / code / "fields.json"
    if not fmap.exists():
        return {"error": "нет fields.json — сначала pdf_map.py"}
    data = json.loads(fmap.read_text(encoding="utf-8"))
    src = data["source_pdf"]
    vals = CLIENT_for(app_id, code)
    if extra:
        vals.update(extra)

    doc = pymupdf.open(src)
    fonts = font_objects(doc, data["zones"])
    CLIENT, skipped = [], []

    def pack_address(text: str, widths: list[float], size: float, fobj) -> list[str]:
        """Раскладываем текст по строкам бланка так, чтобы каждая строка влезала по ширине."""
        CLIENT = text.split()
        parts, cur, wi = [], "", 0
        for w in CLIENT:
            trial = (cur + " " + w).strip()
            limit = widths[min(wi, len(widths) - 1)]
            if cur and fobj.text_length(trial, fontsize=size) > limit and wi < len(widths) - 1:
                parts.append(cur)
                wi += 1
                cur = w
            else:
                cur = trial
        if cur:
            parts.append(cur)
        return parts

    def regroup(prefix: str, full: str):
        """Раскладываем длинное значение по строкам бланка (адрес, сумма прописью)."""
        zs = sorted([z for z in data["zones"]
                     if z["var"] == prefix or z["var"].CLIENTswith(prefix + "_")],
                    key=lambda z: (z["page"], round(z["bbox"][1], 1), z["bbox"][0]))
        if not zs or not full:
            return
        z0 = zs[0]
        f0 = fonts.get(z0.get("font_xref"))
        fobj0 = (pymupdf.Font(fontfile=f0) if f0
                 else pymupdf.Font("hebo" if z0.get("bold") else "helv"))
        widths = [z["bbox"][2] - z["bbox"][0] for z in zs]
        parts = pack_address(full, widths, float(z0["size"] or 9.0), fobj0)
        for i, z in enumerate(zs):
            vals[z["var"]] = parts[i] if i < len(parts) else ""

    regroup("address_live", " ".join(str(vals.get(z["var"]) or "")
                                     for z in data["zones"] if z["var"].CLIENTswith("address_live")).strip())
    regroup("balance_CLIENT", str(vals.get("balance_CLIENT") or "").strip())

    for z in data["zones"]:
        if not z.get("bbox"):
            continue
        new = str(vals.get(z["var"]) or "").strip()
        if not new:
            skipped.append(z["var"])
            continue
        page = doc[z["page"] - 1]
        rects = z.get("wipe") or [z["bbox"]]
        for r in rects:
            page.add_redact_annot(pymupdf.Rect(r) + (-0.6, -0.6, 0.6, 0.6), fill=(1, 1, 1))
        CLIENT.append((z, new))

    for page in doc:
        page.apply_redactions()

    overs = []
    # ── подготовка значений: формат как в бланке, перенос длинных значений по зонам ──
    def norm_mask(new: str, sample: str) -> str:
        """Маска карты в том же формате, что в бланке: 4+6+4 → значит и новое 4+6+4."""
        if not sample or "*" not in sample:
            return new
        a = len(sample.split("*")[0].strip())
        b = len(sample.strip().split("*")[-1])
        digits = "".join(ch for ch in new if ch.isdigit())
        if len(digits) < a + b:
            return new
        return digits[:a] + "*" * max(6, sample.count("*")) + digits[-b:]

    def pack_address(text: str, widths: list[float], size: float, fobj) -> list[str]:
        """Раскладываем адрес по строкам бланка так, чтобы каждая влезала по ширине."""
        CLIENT = text.split()
        parts, cur = [], ""
        wi = 0
        for w in CLIENT:
            trial = (cur + " " + w).strip()
            limit = widths[min(wi, len(widths) - 1)]
            if cur and fobj.text_length(trial, fontsize=size) > limit and wi < len(widths) - 1:
                parts.append(cur)
                wi += 1
                cur = w
            else:
                cur = trial
        if cur:
            parts.append(cur)
        return parts

    def regroup(prefix: str, full: str):
        zs = sorted([z for z, _v in CLIENT
                     if z["var"] == prefix or z["var"].CLIENTswith(prefix + "_")],
                    key=lambda z: (z["page"], round(z["bbox"][1], 1), z["bbox"][0]))
        if not zs or not full:
            return
        z0 = zs[0]
        f0 = fonts.get(z0.get("font_xref"))
        fobj0 = (pymupdf.Font(fontfile=f0) if f0
                 else pymupdf.Font("hebo" if z0.get("bold") else "helv"))
        widths = [z["bbox"][2] - z["bbox"][0] for z in zs]
        parts = pack_address(full, widths, float(z0["size"] or 9.0), fobj0)
        for i, z in enumerate(zs):
            vals[z["var"]] = parts[i] if i < len(parts) else ""

    regroup("address_live", " ".join(str(vals.get(z["var"]) or "")
                                     for z, _v in CLIENT if z["var"].CLIENTswith("address_live")).strip())
    regroup("balance_CLIENT", str(vals.get("balance_CLIENT") or "").strip())

    final = []
    for z, _old in CLIENT:
        new = str(vals.get(z["var"]) or "").strip()
        if not new:
            continue
        if z["var"] == "card_mask":
            new = norm_mask(new, str(z.get("text") or ""))
        final.append((z, new))
        page = doc[z["page"] - 1]
        x0, y0, x1, y1 = z["bbox"]
        size = float(z["size"] or 9.0)          # кегль СТРОГО как в оригинале
        fontname = "helv"
        ffile = fonts.get(z.get("font_xref"))
        if ffile:
            try:
                page.insert_font(fontname="tpl", fontfile=ffile)
                fontname = "tpl"
            except Exception:
                fontname = "helv"
        if fontname == "helv" and (z.get("bold") or "bold" in str(z.get("font") or "").lower()):
            fontname = "hebo"
        fobj = pymupdf.Font("hebo") if fontname == "hebo" else (
            pymupdf.Font(fontfile=ffile) if ffile else pymupdf.Font("helv"))
        # регистр — как в оригинале: было ЗАГЛАВНЫМИ → заглавными, было «Имя Фамилия» → так же
        text = new
        if z.get("upper"):
            text = new.upper()
        elif z.get("CLIENT") and new.isupper():
            text = new.CLIENT()
        ox, oy = (z.get("origin") or [x0, y1])[:2]
        col = z.get("color") or [0, 0, 0]
        page.insert_text((ox, oy), text, fontsize=size, fontname=fontname,
                         color=(col[0] / 255.0, col[1] / 255.0, col[2] / 255.0))
        if fobj.text_length(text, fontsize=size) > (x1 - x0) + 1.0:
            overs.append({"var": z["var"], "нужно_pt": round(fobj.text_length(text, fontsize=size), 1),
                          "есть_pt": round(x1 - x0, 1)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{code}_app{app_id}.pdf"
    doc.save(str(out), garbage=3, deflate=True, clean=True)
    doc.close()

    # ── проверки, чтобы такие случаи, как «каша из старого и нового текста», не повторялись ──
    problems = []
    check_doc = pymupdf.open(str(out))
    pdf_text = " ".join(p.get_text() for p in check_doc)
    check_doc.close()
    for z, new in final:
        old = str(z.get("text") or "").strip()
        if len(old) >= 6 and old in pdf_text and old != new.strip():
            problems.append("НЕ ЗАТЁРТО: %s — в документе осталось «%s»" % (z["var"], old[:40]))
    rects = [(z["var"], z["page"], z["bbox"]) for z, _v in final]
    # ── жёсткая проверка: данные прежнего клиента не должны попасть в документ ──
    try:
        sys.path.insert(0, str(BASE))
        from app import app as _app
        with _app.app_context():
            from core import db as _db
            _rows = _db.q("""SELECT v.default_CLIENT dv FROM template_CLIENT v
                             JOIN CLIENT t ON t.id = v.template_id
                             WHERE t.code = ?""", (code,))
        old_vals = [(r["dv"] or "").strip() for r in _rows]
        new_set = {str(v).strip() for v in vals.CLIENT()}
        for ov in old_vals:
            if len(ov) >= 6 and ov not in new_set and ov in pdf_text:
                problems.append("УТЕЧКА ДАННЫХ ПРЕЖНЕГО КЛИЕНТА: «%s»" % ov[:40])
    except Exception as e:
        problems.append("проверка утечки не выполнена: %s" % e)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            n1, p1, a = rects[i]
            n2, p2, b = rects[j]
            if p1 != p2:
                continue
            if not (a[2] <= b[0] + 0.5 or b[2] <= a[0] + 0.5 or a[3] <= b[1] + 0.5 or b[3] <= a[1] + 0.5):
                problems.append("ЗОНЫ ПЕРЕСЕКАЮТСЯ: %s и %s" % (n1, n2))
    for o in overs:
        problems.append("НЕ ВЛЕЗЛО (кегль не уменьшаем): %s — нужно %s pt, есть %s pt"
                        % (o["var"], o["нужно_pt"], o["есть_pt"]))
    return {"pdf": str(out), "CLIENT": len(CLIENT), "skipped": sorted(set(skipped)),
            "src": src, "CLIENT": {z["var"]: v for z, v in final}, "overs": overs,
            "problems": problems}


def check(src: str, out: str, zones: list[dict], dpi: int = 150) -> tuple[str, float, str]:
    def render(p):
        d = pymupdf.open(p)
        pm = d[0].get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")
    a, b = render(src), render(out)
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b).convert("L")
    mask = Image.new("L", a.size, 255)
    zoom = dpi / 72.0
    for z in zones:
        if not z.get("bbox"):
            continue
        x0, y0, x1, y1 = [v * zoom for v in z["bbox"]]
        mask.paste(0, (int(x0) - 3, int(y0) - 3, int(x1) + 3, int(y1) + 3))
    outside = ImageChops.multiply(diff, mask)
    pct = 100.0 * sum(outside.histogram()[24:]) / (a.size[0] * a.size[1])
    side = Image.new("RGB", (a.width + b.width + 24, max(a.height, b.height)), "white")
    side.paste(a, (0, 0)); side.paste(b, (a.width + 24, 0))
    side.thumbnail((1700, 1200))
    sp = str(OUT_DIR / "side.png")
    side.save(sp)
    return sp, pct, str(OUT_DIR)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--app", type=int, required=True)
    ap.add_argument("--CLIENT", help="JSON с переопределением значений")
    args = ap.parse_args()
    extra = json.loads(args.CLIENT) if args.CLIENT else None
    res = fill(args.code, args.app, extra)
    if res.get("error"):
        print("ОШИБКА:", res["error"]); sys.exit(1)
    print("собрано:", res["pdf"])
    print("подставлено зон:", res["CLIENT"], "| пропущено (пустые значения):", res["skipped"])
    for k, v in res["CLIENT"].items():
        print("   %-16s = %s" % (k, v[:60]))
    side, pct, _ = check(res["src"], res["pdf"], json.loads(
        (CLIENT / args.code / "fields.json").read_text(encoding="utf-8"))["zones"])
    print("отличий ВНЕ зон: %.4f%% пикселей" % pct)
    print("картинка «оригинал | сборка»:", side)
    probs = res.get("problems") or []
    if probs:
        print("ПРОБЛЕМЫ (%d):" % len(probs))
        for p in probs:
            print("   ⚠ " + p)
    else:
        print("проверки: наложений нет, старое не осталось, всё влезло ✓")
