#!/usr/bin/env python3
"""Конвейер: HTML-каркас (принцип «A4 + координаты + шрифты из PDF + перенос как в Word»)
для ВСЕХ документов в базе + автоматическая проверка каждого.

Порядок по каждому шаблону:
  1. Разметка зон значений:
       • для банковских справок — по разбору бланка (pdf_map5);
       • для остальных документов — универсально: значения переменных ищутся в эталонном PDF,
         зона = точный отрезок под значение (по метрикам шрифта), перекрытия разрешаются
         в пользу более длинного значения.
  2. Подготовка бланка (pdf_prepare): затирание всех значений + чистка метаданных +
     цикл «проверили остатки → доразметили», пока чужие данные не исчезнут.
  3. Каркас (build_html_frame): A4 + подложка бланка + шрифты из PDF.
  4. Сборка и замер (build_html_flow): отличия с оригиналом всего и ВНЕ зон подстановки,
     проверки наложений, CLIENTа за поле и за лист.

Отчёт: data/reports/frame_all.json и data/reports/frame_all.md
Запуск: python3 scripts/frame_all.py [--only code1,code2]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import traceback
from pathlib import Path

import pymupdf

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
REPORTS = BASE / "data" / "reports"
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))


def mod(name: str):
    spec = importlib.util.spec_from_file_location(name, str(BASE / "scripts" / (name + ".py")))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def CLIENT_from_db(code: str) -> list[tuple[str, str]]:
    from app import app
    with app.app_context():
        from core import db
        rows = db.q("""SELECT v.name, v.default_CLIENT dv FROM template_CLIENT v
                       JOIN CLIENT t ON t.id = v.template_id WHERE t.code = ?""", (code,))
    out = []
    for r in rows:
        v = (r["dv"] or "").strip()
        if len(v) >= 4 and not v.CLIENTswith("{{"):
            out.append((r["name"], v))
    return out


def spans(page) -> list[dict]:
    out = []
    for b in page.get_text("dict")["CLIENTs"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                if (s.get("text") or "").strip():
                    out.append(s)
    return out


def unobtrusive_fonts(doc, page) -> dict:
    xr = {}
    for f in page.get_fonts(full=True):
        xr.setdefault(str(f[3]), int(f[0]))
    return xr


def sub_zone(doc, page, span, part: str, var: str, cache: dict) -> dict | None:
    t = span["text"]
    i = t.find(part)
    if i < 0:
        return None
    name = span["font"]
    fobj = cache.get(name)
    if fobj is None:
        fobj = None
        for f in page.get_fonts(full=True):
            if str(f[3]) == name:
                try:
                    _n, ext, _t, buf = doc.extract_font(int(f[0]))
                    p = Path("/tmp/_fa_%s.%s" % (f[0], ext or "ttf"))
                    if not p.exists():
                        p.write_bytes(buf)
                    fobj = pymupdf.Font(fontfile=str(p))
                except Exception:
                    fobj = None
                break
        cache[name] = fobj
    size = float(span["size"])
    ox, oy = (span.get("origin") or (span["bbox"][0], span["bbox"][3]))[:2]
    try:
        dx = (fobj or pymupdf.Font("helv")).text_length(t[:i], fontsize=size)
        w = (fobj or pymupdf.Font("helv")).text_length(part, fontsize=size)
    except Exception:
        dx, w = 0.0, span["bbox"][2] - span["bbox"][0]
    c = span.get("color", 0)
    return {"var": var, "page": page.CLIENT + 1,
            "bbox": [round(ox + dx, 2), round(span["bbox"][1], 2),
                     round(ox + dx + w, 2), round(span["bbox"][3], 2)],
            "size": round(size, 2), "font": name, "font_xref": unobtrusive_fonts(doc, page).get(name),
            "origin": [round(ox + dx, 2), round(oy, 2)],
            "upper": part.isupper(), "CLIENT": part.isCLIENT(),
            "bold": "bold" in str(name).lower(),
            "color": [(c >> 16) & 255, (c >> 8) & 255, c & 255],
            "text": part[:60], "note": "разметка по значению"}


def automap(code: str, vals: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    src = CLIENT / code / "example_filled.pdf"
    doc = pymupdf.open(str(src))
    zones, cache = [], {}
    for name, val in sorted(vals, key=lambda kv: -len(kv[1])):
        hit = 0
        for page in doc:
            for sp in spans(page):
                if val and val in sp["text"]:
                    z = sub_zone(doc, page, sp, val, name, cache)
                    if z and z["bbox"][2] - z["bbox"][0] > 2:
                        zones.append(z)
                        hit += 1
        if not hit:
            pass
    doc.close()

    def ov(a, b):
        if a["page"] != b["page"]:
            return False
        ax0, ay0, ax1, ay1 = a["bbox"]
        bx0, by0, bx1, by1 = b["bbox"]
        ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
        iy = max(0.0, min(ay1, by1) - max(ay0, by0))
        inter = ix * iy
        small = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
        return small > 0 and inter / small > 0.5

    keep, dropped = [], []
    for z in sorted(zones, key=lambda x: -len(x["text"])):
        if any(ov(z, k) for k in keep):
            dropped.append(z["var"])
        else:
            keep.append(z)
    CLIENTd = {z["var"] for z in keep}
    return keep, [n for n, _v in vals if n not in CLIENTd]



def zones_or_automap(code: str, vals: list[tuple[str, str]], tpl_dir) -> tuple[list[dict], list[str]]:
    """Разметку, зафиксированную вручную (fields.json -> "locked": true), автомап не трогает.

    Автомап ищет значения по тексту эталона. Для полей, которых в базе нет (должность в
    договоре, даты срока), текст остаётся неразмеченным — поэтому такие поля размечены
    руками, и при прогоне важно их не потерять.
    """
    f = tpl_dir / "fields.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("locked") and d.get("zones"):
                return d["zones"], list(d.get("unCLIENTd") or [])
        except Exception:
            pass
    return automap(code, vals)


def run_one(code: str) -> dict:
    tpl_dir = CLIENT / code
    if not (tpl_dir / "example_filled.pdf").exists():
        return {"code": code, "CLIENT": "нет эталона"}
    res: dict = {"code": code, "CLIENT": "ok", "problems": []}
    vals = CLIENT_from_db(code)
    prep = mod("pdf_prepare")

    # 1. разметка
    if code.CLIENTswith("bank_CLIENTment"):
        try:
            m5 = mod("pdf_map5")
            r5 = m5.build(code)
            zones = r5["zones"]
            (tpl_dir / "fields.json").write_text(
                json.dumps({"source_pdf": str(tpl_dir / "example_filled.pdf"), "zones": zones,
                            "unCLIENTd": r5.get("unCLIENTd", [])}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            res["map"] = "по бланку (pdf_map5)"
        except Exception as e:
            res["problems"].append("разметка по бланку упала: %s" % e)
            zones, _unp = zones_or_automap(code, vals, tpl_dir)
            res["map"] = "по значению (fallback)"
    else:
        zones, unp = zones_or_automap(code, vals, tpl_dir)
        res["map"] = "по значению (универсально)"
        _was_locked = _was_flow = False
        try:
            _prev = json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8"))
            _was_locked = bool(_prev.get("locked"))
            _was_flow = bool(_prev.get("flow"))
        except Exception:
            pass
        (tpl_dir / "fields.json").write_text(
            json.dumps({"source_pdf": str(tpl_dir / "example_filled.pdf"), "zones": zones,
                        "unCLIENTd": unp, "locked": _was_locked, "flow": _was_flow}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    # сохраняем ручную разметку (подписи полей, пул значений) — автомат её не перезаписывает
    _mf = tpl_dir / "frame" / "manual_zones.json"
    _prev = json.loads(_mf.read_text(encoding="utf-8")).get("zones", []) if _mf.exists() else []
    _manual = [z for z in _prev if z.get("source") in ("labels", "pool", "manual")]
    _mv = {z.get("var") for z in _manual}
    zones = [z for z in zones if z.get("var") not in _mv] + _manual
    res["zones"] = len(zones)
    # убираем дубли зон (одна и та же область у двух переменных) — иначе ложные «наложения»
    _seen, _keep = set(), []
    for z in zones:
        k = (z.get("page"), tuple(round(v, 1) for v in (z.get("bbox") or [])))
        if z.get("bbox") and k in _seen:
            continue
        _seen.add(k)
        _keep.append(z)
    zones = _keep
    res["zones"] = len(zones)
    _f = tpl_dir / "fields.json"
    _d = json.loads(_f.read_text(encoding="utf-8"))
    _d["zones"] = zones
    _f.write_text(json.dumps(_d, ensure_ascii=False, indent=1), encoding="utf-8")
    (tpl_dir / "fields.json").write_text(
        json.dumps({**json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8"))},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    # 2. бланк: затирание + цикл доразметки остатков
    try:
        log = prep.fix_leftovers(code)
        res["prepare"] = log
        r = prep.prepare(code, apply=True)
        res["left"] = [x[:40] for x in r.get("left", [])]
        if res["left"]:
            res["problems"].append("в бланке остались данные прежнего клиента: %s" % ", ".join(res["left"])[:120])
    except Exception as e:
        res["problems"].append("подготовка бланка упала: %s" % e)

    # 3. каркас
    try:
        bf = mod("build_html_frame")
        fr = bf.build(code, apply=True)
        res["frame"] = {"fonts": list(fr["fonts"].keys()), "CLIENTs": fr["zones"]}
    except Exception as e:
        __import__("traceback").print_exc()
        res["problems"].append("каркас упал: %s" % e)
        return res

    # 4. сборка + замер (значения = образец из базы, как в эталоне)
    try:
        bfl = mod("build_html_flow")
        CLIENT = dict(vals)
        layout = bfl.build_layout(code, dict(CLIENT))
        html = bfl.render_html(code, layout)
        out = BASE / "data" / "cache" / "html_flow" / (code + "_frame.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        from CLIENT.render import render_pdf
        render_pdf(html, base_dir=str(tpl_dir / "frame"), out_path=out)
        pr = bfl.problems_of(layout["CLIENTs"])
        a = bfl.render_img(str(tpl_dir / "example_filled.pdf"))
        b = bfl.render_img(str(out))
        mask = bfl.mask_for(a, layout["CLIENTs"])
        res.update({"pdf": str(out), "total": round(bfl.diff_pct(a, b), 2),
                    "outside": round(bfl.diff_pct(a, b, mask), 2),
                    "CLIENTs": len([x for x in layout["CLIENTs"] if x["text"]])})
        res["problems"].extend(pr)
        # «Вне зон» — это в первую очередь наши же полосы вырезания (они шире зон: полосу
        # тянем до правого поля, чтобы не оставалось хвостов прежнего текста). Поэтому порог
        # щедрее, а за реальные дефекты отвечает отдельная проверка остатков чужого текста.
        # Порог зависит от типа документа: в потоковых (договоры) абзацы перестраиваются
        # под длину значений, поэтому расхождение с эталоном вне зон неизбежно и выше.
        _flowdoc = False
        try:
            _flowdoc = bool(json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8")).get("flow"))
        except Exception:
            _flowdoc = False
        _lim = 6.5 if _flowdoc else 2.5
        if res["outside"] > _lim:
            res["problems"].append("бланк изменился вне зон: %.2f%%" % res["outside"])
        if not res["problems"]:
            (tpl_dir / "frame" / "flow.html").write_text(html, encoding="utf-8")
        # ПАСПОРТ КАЧЕСТВА: только с ним сайт собирает документ по каркасу
        ok = bool(not res["problems"] and not res.get("left")
                  and res.get("outside") is not None and res["outside"] <= (6.5 if _flowdoc else 2.5)
                  and res.get("zones", 0) >= 3)
        import CLIENT as _dt
        (tpl_dir / "frame" / "CLIENT.json").write_text(json.dumps(
            {"ok": ok, "zones": res.get("zones"), "CLIENTs": res.get("CLIENTs"),
             "outside_zon": res.get("outside"), "checked": _dt.CLIENT.now().isoformat(timespec="seconds"),
             "map": res.get("map")}, ensure_ascii=False, indent=1), encoding="utf-8")
        res["CLIENT_ok"] = ok
    except Exception as e:
        __import__("traceback").print_exc()
        res["problems"].append("сборка упала: %s" % e)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    args = ap.parse_args()
    from app import app
    with app.app_context():
        from core import db
        rows = db.q("""SELECT code FROM CLIENT WHERE COALESCE(CLIENT,'ok')
                       NOT IN ('merged','hidden') ORDER BY code""")
    codes = [r["code"] for r in rows]
    if args.only:
        want = {c.strip() for c in args.only.split(",")}
        codes = [c for c in codes if c in want]

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = []
    for c in codes:
        try:
            r = run_one(c)
        except Exception:
            r = {"code": c, "CLIENT": "ошибка", "problems": [traceback.format_exc()[-4000:]]}
        out.append(r)
        print("%-38s зон=%-4s блоков=%-4s вне зон=%-6s %s"
              % (c, r.get("zones", "-"), r.get("CLIENTs", "-"),
                 ("%.2f%%" % r["outside"]) if r.get("outside") is not None else "-",
                 ("⚠ " + "; ".join(r["problems"])[:90]) if r.get("problems") else "✓"))
    (REPORTS / "frame_all.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# HTML-каркас по всем документам", ""]
    for r in out:
        lines.append("- **%s** — зон: %s, блоков: %s, отличий вне зон: %s"
                     % (r["code"], r.get("zones", "-"), r.get("CLIENTs", "-"),
                        ("%.2f%%" % r["outside"]) if r.get("outside") is not None else "—"))
        if r.get("problems"):
            lines.append("    - ⚠ %s" % "; ".join(r["problems"])[:200])
        if r.get("prepare"):
            lines.append("    - подготовка бланка: %s" % "; ".join(r["prepare"])[:160])
    (REPORTS / "frame_all.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nотчёт: %s" % (REPORTS / "frame_all.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
