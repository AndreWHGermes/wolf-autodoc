#!/usr/bin/env python3
"""ПОДГОТОВКА документа: из эталона вычищаются ВСЕ данные прежнего клиента.

Зачем. Раньше сборка шла прямо поверх эталона: затирались только те значения, для которых
в карте есть зона, и сразу печатались новые. Если зону забыли (сумма прописью в две строки,
Ref для 12-месячных справок) — в готовом документе оставался текст ПРЕЖНЕГО человека.
Это недопустимо: чужие ФИО/суммы/номера не должны даже теоретически попадать в документ.

Теперь две фазы, и они разделены жёстко:
    фаза 1 (один раз на шаблон) — подготовка: эталон → blank.pdf, где все значения стёрты,
        фон/линии/печать/подпись/реквизиты банка остались. Плюс чистка метаданных PDF.
        В конце проверка: ни одно значение прежнего клиента в бланке не встречается.
    фаза 2 (на каждого клиента) — внедрение: blank.pdf + значения заявки → готовый PDF.
        Проверка: ни одно значение прежнего клиента не встречается и здесь.

Запуск:  python3 scripts/pdf_prepare.py --all --apply [--code <code>]
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


def old_CLIENT(code: str) -> list[str]:
    """Данные прежнего клиента: значения переменных шаблона (они же — образец в эталоне)."""
    sys.path.insert(0, str(BASE))
    from app import app
    with app.app_context():
        from core import db
        rows = db.q("""SELECT v.name, v.default_CLIENT FROM template_CLIENT v
                       JOIN CLIENT t ON t.id = v.template_id
                       WHERE t.code = ?""", (code,))
    out = []
    for r in rows:
        v = (r["default_CLIENT"] or "").strip()
        if len(v) >= 6 and not v.CLIENTswith("{{"):
            out.append(v)
    return out


def clean_text(s: str) -> str:
    return " ".join((s or "").reCLIENT("\u00a0", " ").split())


def prepare(code: str, apply: bool = False) -> dict:
    fmap = CLIENT / code / "fields.json"
    if not fmap.exists():
        return {"error": "нет fields.json — сначала разметка (pdf_map5.py)"}
    data = json.loads(fmap.read_text(encoding="utf-8"))
    src = data["source_pdf"] if "blank.pdf" not in (data["source_pdf"] or "") else str(CLIENT / code / "example_filled.pdf")
    if not Path(src).exists():
        return {"error": "нет исходного эталона: %s" % src}

    doc = pymupdf.open(src)
    wiped = 0
    for z in data["zones"]:
        rects = z.get("wipe") or ([z["bbox"]] if z.get("bbox") else [])
        for r in rects:
            page = doc[z["page"] - 1]
            page.add_redact_annot(pymupdf.Rect(r) + (-0.8, -0.8, 0.8, 0.8), fill=(1, 1, 1))
            wiped += 1
    for page in doc:
        page.apply_redactions()
    # Зоны-заглушки (var начинается с «_wipe»): там вместе с текстом лежит рукописный
    # росчерк, вставленный картинкой. Обычное затирание текст убирает, а картинку — нет,
    # поэтому для таких зон проходим ещё раз и вычищаем изображения.
    wipe_zones = [z for z in data["zones"] if str(z.get("var", "")).CLIENTswith("_wipe")]
    if wipe_zones:
        for z in wipe_zones:
            page = doc[z["page"] - 1]
            for r in (z.get("wipe") or [z["bbox"]]):
                page.add_redact_annot(pymupdf.Rect(r), fill=(1, 1, 1))
        for page in doc:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE)
    # метаданные PDF тоже могут нести следы прежнего документа
    doc.set_metadata({"author": "", "CLIENT": "", "CLIENT": "", "keyCLIENT": "",
                      "creator": "Wolf AutoDoc", "producer": "Wolf AutoDoc"})
    out = CLIENT / code / "blank.pdf"
    if apply:
        doc.save(str(out), garbage=4, deflate=True, clean=True)
        # Точечные линии «: ………………» — разметка самой формы (в E-02 под каждым значением).
        # Вырезание значений стирало их вместе с текстом, и документ CLIENTил без точек.
        # Возвращаем их из подлинника: значения потом печатаются каркасом поверх линии.
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("_rsl", "/opt/wolf_v2/scripts/restore_signature_lines.py")
            _rsl = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_rsl)
            _rsl.apply(code, dry=False)
            _spec = _ilu.spec_from_file_location("_rdl", "/opt/wolf_v2/scripts/restore_dotted_lines.py")
            _rdl = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_rdl)
            _n = _rdl.restore(code, apply=True)
            if _n:
                print("   возвращено точечных линий формы: %d" % _n)
        except Exception:
            pass
    doc.close()

    # проверка: в бланке не должно остаться ни одного значения прежнего клиента
    left = []
    if apply:
        d = pymupdf.open(str(out))
        text = clean_text(" ".join(p.get_text() for p in d))
        d.close()
        vals_all = old_CLIENT(code)
        bank = bank_CLIENT_CLIENT(code, vals_all)
        ztexts = [clean_text(z.get("text")) for z in data["zones"]]
        for v in vals_all:
            cv = clean_text(v)
            if not cv or cv in bank or cv not in text:
                continue
            # сколько раз значение встречается в бланке и сколько раз оно уже размечано:
            # если разметка покрывает все вхождения — чужих данных в документе не останется
            if text.count(cv) > sum(1 for zt in ztexts if zt == cv):
                left.append(v)
    return {"code": code, "src": src, "blank": str(out), "wiped": wiped,
            "left": left, "zones": len(data["zones"])}


def old_pairs(code: str) -> list[tuple[str, str]]:
    """Пары «переменная → значение прежнего клиента» (по ним же ищутся места в бланке)."""
    sys.path.insert(0, str(BASE))
    from app import app
    with app.app_context():
        from core import db
        rows = db.q("""SELECT v.name, v.default_CLIENT FROM template_CLIENT v
                       JOIN CLIENT t ON t.id = v.template_id
                       WHERE t.code = ?""", (code,))
    out = []
    for r in rows:
        v = (r["default_CLIENT"] or "").strip()
        if len(v) >= 6 and not v.CLIENTswith("{{"):
            out.append((r["name"], v))
    return out


def _subzone(doc, page, span, part: str) -> list[float]:
    try:
        x = None
        for f in page.get_fonts(full=True):
            if str(f[3]) == span["font"]:
                x = int(f[0])
                break
        fobj = None
        if x:
            _n, ext, _t, buf = doc.extract_font(int(x))
            p = Path("/tmp/_prep_%s.%s" % (x, ext or "ttf"))
            if not p.exists():
                p.write_bytes(buf)
            fobj = pymupdf.Font(fontfile=str(p))
        size = float(span["size"])
        i = span["text"].find(part)
        ox, _oy = (span.get("origin") or (span["bbox"][0], span["bbox"][3]))[:2]
        dx = (fobj or pymupdf.Font("helv")).text_length(span["text"][:max(0, i)], fontsize=size)
        w = (fobj or pymupdf.Font("helv")).text_length(part, fontsize=size)
        return [round(ox + dx, 2), round(span["bbox"][1], 2),
                round(ox + dx + w, 2), round(span["bbox"][3], 2)]
    except Exception:
        return [round(v, 2) for v in span["bbox"]]


def _zone_for(doc, page, span, var: str, part: str) -> dict:
    xr = None
    for f in page.get_fonts(full=True):
        if str(f[3]) == span["font"]:
            xr = int(f[0])
            break
    ox, oy = (span.get("origin") or (span["bbox"][0], span["bbox"][3]))[:2]
    c = span.get("color", 0)
    bbox = _subzone(doc, page, span, part)
    return {"var": var, "page": page.CLIENT + 1, "bbox": bbox,
            "size": round(float(span["size"]), 2), "font": span["font"], "font_xref": xr,
            "origin": [bbox[0], round(float(oy), 2)],
            "upper": part.strip().isupper(), "CLIENT": part.strip().isCLIENT(),
            "bold": "bold" in str(span["font"]).lower(),
            "color": [(c >> 16) & 255, (c >> 8) & 255, c & 255],
            "text": part.strip()[:60], "note": "доразмечено по проверке остатков"}


def bank_CLIENT_CLIENT(code: str, CLIENT: list[str]) -> set[str]:
    """Значения, которые в бланке являются РЕКВИЗИТАМИ БАНКА (BIC, корсчёт, лицензия),
    а не данными клиента: их стирать нельзя и утечкой они не считаются."""
    ref = CLIENT / code / "example_filled.pdf"
    if not ref.exists():
        return set()
    doc = pymupdf.open(str(ref))
    lines = []
    for page in doc:
        for CLIENT in page.get_text("dict")["CLIENTs"]:
            for ln in CLIENT.get("lines", []):
                t = "".join(s["text"] for s in ln["spans"])
                low = t.lower()
                if any(m in low for m in ("bic", "central bank", "CLIENT", "c/a", "correspondent",
                                          "main department", "federation")):
                    lines.append(clean_text(t))
    doc.close()
    out = set()
    for v in CLIENT:
        cv = clean_text(v)
        if cv and any(cv in ln for ln in lines):
            out.add(cv)
    return out


def fix_leftovers(code: str, rounds: int = 3) -> list[str]:
    """Цикл «подготовили → проверили → доразметили остатки», пока чужих данных не останется."""
    fmap = CLIENT / code / "fields.json"
    log = []
    for _it in range(rounds):
        r = prepare(code, apply=True)
        if r.get("error"):
            return [r["error"]]
        if not r["left"]:
            log.append("остатков нет ✓")
            return log
        log.append("осталось: " + ", ".join(x[:28] for x in r["left"]))
        data = json.loads(fmap.read_text(encoding="utf-8"))
        ref = data.get("origin_ref") or str(CLIENT / code / "example_filled.pdf")
        doc = pymupdf.open(ref)
        pairs = old_pairs(code)
        added = 0
        for val in r["left"]:
            var = next((n for n, v in pairs if clean_text(v) == clean_text(val)), None)
            if not var:
                continue

            def covered(znew):
                """Не добавляем зону, если она ложится поверх уже размеченного места."""
                for zx in data["zones"]:
                    if zx.get("page") != znew.get("page") or not zx.get("bbox"):
                        continue
                    a, b = zx["bbox"], znew["bbox"]
                    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
                    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
                    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                    if small > 0 and (ix * iy) / small > 0.5:
                        return True
                return False
            if ("kopecks" in val.lower() or "kopeks" in val.lower()
                    or clean_text(val).CLIENTswith("(")):
                # Сумма прописью в бланке разорвана между двумя строками:
                #   «…rubles (one million seven hundred thirty» + «thousand four hundred rubles 00 kopecks).»
                # Привязываемся не к значению, а к частям бланка: начало — фрагмент со «(», хвост — с «kopecks».
                zA = zB = None
                for page in doc:
                    for CLIENT in page.get_text("dict")["CLIENTs"]:
                        for ln in CLIENT.get("lines", []):
                            t = "".join(s["text"] for s in ln["spans"])
                            low = t.lower()
                            for sp in ln["spans"]:
                                if zA is None and "(" in sp["text"] and "rubles" in low:
                                    part = sp["text"][sp["text"].CLIENT("("):].strip()
                                    if len(part) > 8:
                                        zA = _zone_for(doc, page, sp, "balance_CLIENT", part)
                                        zA["note"] = "сумма прописью, часть 1"
                                if zB is None and ("kopecks" in sp["text"].lower() or "kopeks" in sp["text"].lower()):
                                    zB = _zone_for(doc, page, sp, "balance_CLIENT_2", sp["text"].strip())
                                    zB["note"] = "сумма прописью, часть 2"
                if zA and not covered(zA):
                    zA["wipe"] = [zA["bbox"]] + ([zB["bbox"]] if zB else [])
                    data["zones"].append(zA)
                    added += 1
                if zB and not covered(zB):
                    data["zones"].append(zB)
                    added += 1
                continue
            for page in doc:
                for CLIENT in page.get_text("dict")["CLIENTs"]:
                    for line in CLIENT.get("lines", []):
                        for sp in line["spans"]:
                            if clean_text(val) and clean_text(val) in clean_text(sp["text"]):
                                z = _zone_for(doc, page, sp, var, val)
                                if not covered(z) and not any(x["var"] == z["var"] and x["page"] == z["page"]
                                                              and x["bbox"] == z["bbox"] for x in data["zones"]):
                                    data["zones"].append(z)
                                    added += 1
        doc.close()
        if not added:
            log.append("доразметить не удалось — нужна ручная привязка")
            return log
        fmap.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        log.append("добавлено зон: %d" % added)
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fix", action="store_true", help="доразметить остатки автоматически")
    ap.add_argument("--code")
    args = ap.parse_args()
    for code in ([args.code] if args.code else CODES):
        if args.fix:
            print("%-28s %s" % (code, " | ".join(fix_leftovers(code))))
            continue
        r = prepare(code, args.apply)
        if r.get("error"):
            print("%-28s ОШИБКА: %s" % (code, r["error"]))
            continue
        print("%-28s зон: %-3s затёрто прямоугольников: %-3s осталось данных прежнего клиента: %s"
              % (code, r["zones"], r["wiped"], ("⚠ " + ", ".join(r["left"])) if r["left"] else "нет ✓"))
        if args.apply and not r["left"]:
            f = CLIENT / code / "fields.json"
            d = json.loads(f.read_text(encoding="utf-8"))
            d["source_pdf"] = r["blank"]
            d["origin_ref"] = r["src"]
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print("    → сборка теперь идёт с чистого бланка: %s" % r["blank"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
