#!/usr/bin/env python3
"""Абзацная сборка документа: строка целиком (статика + переменные) печатается как один блок.

Зачем: когда каждое значение — отдельный абсолютный span, длинное значение «прыгает» и наползает
на слова бланка. В оригинале иначе: абзац набран одной строкой (««TBank», universal license of
Bank of Russia No 9441, hereby informs that card No 553691******4644 has been issued for ANNA
CLIENT.»). Поэтому храним целый абзац: статичные фразы + {{переменные}}, и печатаем его
целиком с начала строки, а старые слова бланка в этой полосе закрываем белой плашкой.

Что делает:
  1. берёт эталон (example_filled.pdf) и зоны из fields.json;
  2. для каждой строки эталона подставляет значения эталона вместо {{переменных}} — «понимает»,
     какие значения где стоят, по координатам зон;
  3. строки, которые длиннее порога или содержат 2+ значения, становятся абзацами;
     короткие одиночные значения остаются точками (шапка: номер, имя, адрес);
  4. строит HTML: подложка + белые плашки под абзацами + абзацы и точки;
  5. пишет template.html (с {{переменными}}) и отчёт: какие абзацы собраны.

Запуск: python3 scripts/paragraph_flow.py <code> [--apply] [--right-edge 539]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
TEMPLATES = BASE / "data" / "templates"


def zone_value(page, bbox):
    """Текст эталона внутри зоны (значение, которое там напечатано)."""
    x0, y0, x1, y1 = bbox
    words = page.get_text("words")
    picked = [w[4] for w in words if w[0] >= x0 - 2.5 and w[2] <= x1 + 3.0
              and w[1] >= y0 - 3.0 and w[3] <= y1 + 3.0]
    return " ".join(picked).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--right-edge", type=float, default=549.0)
    ap.add_argument("--min-para", type=float, default=190.0)
    a = ap.parse_args()
    import pymupdf

    tdir = TEMPLATES / a.code
    fields = json.loads((tdir / "fields.json").read_text(encoding="utf-8"))
    zones = [z for z in fields["zones"] if z.get("bbox")]
    page = pymupdf.open(str(tdir / "example_filled.pdf"))[0]

    # значения эталона по зонам: какие тексты подменяются переменными
    repl: list[tuple[str, dict]] = []                  # (текст эталона, зона)
    # сначала — по строкам: если строка целиком принадлежит зоне (адрес, имя, сумма),
    # заменяем строку целиком, иначе значение обрезается и в абзац попадает хвост
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            b = ln["bbox"]
            txt = " ".join(s["text"] for s in ln["spans"]).strip()
            if not txt:
                continue
            best, best_ov = None, 0.0
            for z in zones:
                zx0, zy0, zx1, zy1 = z["bbox"]
                ox = max(0.0, min(zx1, b[2]) - max(zx0, b[0]))
                oy = max(0.0, min(zy1, b[3]) - max(zy0, b[1]))
                if oy <= 2.0 or ox <= 2.0:
                    continue
                ov = ox / max(1.0, b[2] - b[0])
                if ov > best_ov:
                    best, best_ov = z, ov
            if best and best_ov >= 0.75 and not re.fullmatch(r"[\s\.\,\u2026]+", txt.lstrip(": ").strip()):
                repl.append((re.sub(r"\s*[\.\,]\s*$", "", txt).strip(), best))
    for z in zones:
        val = zone_value(page, z["bbox"])
        # заполнитель бланка («: ……………») — не значение: иначе многоточие из шапки
        # подставляется во все строки со «………» и ломает нижние пункты анкеты
        if val and not re.fullmatch(r"[\s\.\,\u2026]+", val):
            repl.append((re.sub(r"\s*[\.\,]\s*$", "", val).strip(), z))
    # дубли убираем по паре (текст, зона): одинаковые тексты у РАЗНЫХ зон (в шапке doc_date,
    # в строке остатка period_to) нужны обе, иначе подменяется не то поле
    seen = set()
    repl = [r for r in repl if r[0] and (len(r[0]) > 1 or r[0] in ("-", "\u2013", "\u2014"))
            and not ((r[0], id(r[1])) in seen or seen.add((r[0], id(r[1]))))]
    repl.sort(key=lambda r: -len(r[0]))

    def to_template(ln, bbox):
        """Замена в пределах строки: значения эталона, встречающиеся в этой строке, → {{ переменные }}.

        Так различаются одинаковые тексты в разных строках («19.07.2026» — это и period_to в строке
        остатка, и doc_date в шапке), и абзац собирается целиком: статика + переменные.
        """
        text = ln
        used = []
        hits = []
        lcy = (bbox[1] + bbox[3]) / 2.0
        # сначала зоны, которые стоят в этой же строке (иначе «19.07.2026» подменилось бы
        # не тем полем: в шапке это doc_date, в строке остатка — period_to), потом остальные
        near = [(v, z) for v, z in repl
                if abs((z["bbox"][1] + z["bbox"][3]) / 2.0 - lcy) <= 6.0]
        far = [(v, z) for v, z in repl if (v, z) not in near]
        for val, z in near + far:
            if not val or val not in text:
                continue
            # значение из одних цифр заменяем только как отдельное число: иначе «00» внутри
            # суммы «10,000» превратило бы строку метерай в мусор («10,000» → «10,{{ phone }}0»)
            if val.isdigit():
                _pat = r"(?<![\d.,])" + re.escape(val) + r"(?![\d.,])"
                if not re.search(_pat, text):
                    continue
                text = re.sub(_pat, "{{ %s }}" % z["var"], text, count=1)
            else:
                text = text.replace(val, "{{ %s }}" % z["var"], 1)
            used.append(z["var"])
            hits.append(z)
        text = re.sub(r"\s+([,\.\)])", r"\1", text)
        return text, used, hits

    lines = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            b = ln["bbox"]
            txt = " ".join(s["text"] for s in ln["spans"]).strip()
            if not txt:
                continue
            # кегль и жирность берём у ДОМИНИРУЮЩЕГО спана (самый длинный текст): в строке адреса
            # первым идёт пустой жирный спан 9pt, и по нему адрес печатался жирным не тем кеглем
            _sp = max((s for s in ln["spans"] if s["text"].strip()), key=lambda s: len(s["text"]), default=ln["spans"][0])
            if int(_sp.get("color") or 0) == 0xFFFFFF:
                # белый «водяной знак» бланка (в E-02 это «FORM E-02» 24pt) — не текст:
                # если его обработать, он попадает в блоки и ломает пункт Occupation
                continue
            size = round(_sp["size"], 2)
            bold = bool(_sp["flags"] & 2 ** 4)
            color = "#%06x" % (int(_sp.get("color") or 0) & 0xFFFFFF)
            tpl_text, used, hits = to_template(txt, list(b))
            # «{{ address_live }},» — запятая в конце значения лишняя, когда строка и есть значение
            if re.fullmatch(r"\{\{\s*\w+\s*\}\}[,\.]?", tpl_text.strip()):
                tpl_text = re.sub(r"[,\\.]$", "", tpl_text.strip())
            # анкета E-02 («Full Name : ………»): двоеточие оставляем в строке, иначе пункт
            # выглядит незаполненным — подпись есть, а данных при ней нет
            if txt.lstrip().startswith(":") and not tpl_text.lstrip().startswith(":"):
                tpl_text = ": " + tpl_text.lstrip()
            # координаты — из оригинала (строка-в-строку); единственное исключение — поле dy
            # у зоны (отступ строки после номера справки у конкретного банка)
            dy_line = 0.0
            for z in zones:
                if not z.get("dy"):
                    continue
                zx0, zy0, zx1, zy1 = z["bbox"]
                ox = max(0.0, min(zx1, b[2]) - max(zx0, b[0]))
                oy = max(0.0, min(zy1, b[3]) - max(zy0, b[1]))
                if ox > 4.0 and oy > 4.0:
                    dy_line = float(z["dy"])
                    break
            x, top = float(b[0]), float(b[1]) + dy_line
            # точка (одиночное значение в строке) печатается на месте СВОЕЙ зоны: слева от него
            # в бланке стоит статика («No », «Ref.») — начало строки занято ею
            def _ov(zz):
                return (min(zz["bbox"][3], b[3]) - max(zz["bbox"][1], b[1])) \
                    * (min(zz["bbox"][2], b[2]) - max(zz["bbox"][0], b[0]))
            z0 = max(hits, key=_ov) if hits else None
            if z0 is not None and not (len(used) >= 2 or (b[2] - b[0]) >= a.min_para):
                x = float(z0["bbox"][0])
                top = float(z0["bbox"][1]) + float(z0.get("dy") or 0.0)
            # цвет и жирность берём у самого значения в бланке (в E-02 данные синие и жирные,
            # а подпись пункта — обычная): иначе значения выглядят чёрными
            if z0 is not None:
                for _s in ln["spans"]:
                    if not _s["text"].strip():
                        continue
                    _sb = _s["bbox"]
                    if (min(_sb[2], z0["bbox"][2]) - max(_sb[0], z0["bbox"][0]) > 2.0
                            and min(_sb[3], z0["bbox"][3]) - max(_sb[1], z0["bbox"][1]) > 2.0):
                        color = "#%06x" % (int(_s.get("color") or 0) & 0xFFFFFF)
                        bold = bool(_s.get("flags", 0) & 2 ** 4)
                        break
            lines.append({"x": round(x, 2), "top": round(top, 2), "w": round(b[2] - b[0], 2),
                          "size": size, "bold": bold, "color": color, "text": tpl_text, "vars": used,
                          "src": txt, "bbox": [round(v, 2) for v in b]})
    for ln in lines:
        ln["is_para"] = bool(ln["vars"]) and (len(ln["vars"]) >= 2 or ln["w"] >= a.min_para)

    # Одну и ту же строку могли разметить дважды — зоной (значение под «:») и абзацем
    # (строка целиком). Плюс расширенная зона адреса ловит вторую строку — и адрес
    # печатался дважды. Оставляем по одному блоку на текст в пределах строки листа.
    _sorted = sorted(lines, key=lambda x: x["top"])
    _last: dict = {}
    _keep = []
    for ln in _sorted:
        _k = (tuple(sorted(ln["vars"])), ln["text"])
        if ln["vars"] and _k in _last and abs(ln["top"] - _last[_k]) <= 30.0:
            continue
        _last[_k] = ln["top"]
        _keep.append(ln)
    lines = _keep

    # Строка, целиком попавшая в зону (2-я и следующие строки многострочного поля:
    # summary, обязанности, навыки), уже печатается блоком самой зоны. Без этой чистки
    # один и тот же текст выводился несколько раз в разных координатах.
    def _in_zone(ln):
        if not ln.get("bbox") or not ln["vars"]:
            return False
        for z in zones:
            zb = z.get("bbox")
            if not zb:
                continue
            if (zb[1] - 1.0 <= ln["bbox"][1] and ln["bbox"][3] <= zb[3] + 1.0
                    and set(ln["vars"]) == {z["var"]} and abs(ln["x"] - zb[0]) > 1.0):
                return True
        return False

    lines = [ln for ln in lines if not _in_zone(ln)]

    paras = [ln for ln in lines if ln["is_para"]]
    points = [ln for ln in lines if ln["vars"] and not ln["is_para"]]
    static_left = [ln["src"] for ln in lines if not ln["vars"]]

    # HTML: подложка + шрифты ВНУТРИ файла (base64), белые плашки под абзацами, абзацы и точки.
    # Так логотип, линии, печать и подпись видны в любом окне — путь к картинке не нужен.
    import base64

    def _b64(p: Path, mime: str) -> str:
        return "data:%s;base64,%s" % (mime, base64.b64encode(p.read_bytes()).decode())

    fr = tdir / "frame"
    reg_b64 = _b64(fr / "fonts" / "LiberationSans-Regular.ttf", "font/ttf")
    bold_b64 = _b64(fr / "fonts" / "LiberationSans-Bold.ttf", "font/ttf")
    # Подложка готовится ЗАРАНЕЕ: из бланка стираются ровно те полосы строк, которые мы
    # переписываем абзацами. Плашки в момент вывода не нужны — они закрывали соседние элементы
    # бланка («TBANK» под строкой Ref.). Здесь же два слоя текста превращаются в один: наш.
    import pymupdf as _fitz
    blank_src = tdir / "blank.pdf"
    bg_para = fr / "bg_para.png"
    if blank_src.exists():
        doc = _fitz.open(str(blank_src))
        pg = doc[0]
        for p in paras + [z for z in zones if z.get("bbox")]:
            bx = p.get("bbox") or [p["x"], p["top"], a.right_edge, p["top"] + p["size"]]
            h = max(float(p.get("size") or 0) * 1.25, 10.5, float(bx[3]) - float(bx[1]) + 2.0)
            # стираем ТОЛЬКО полосу самого абзаца (по координатам строки оригинала):
            # иначе затирается соседняя статика бланка («TBANK» под строкой Ref.)
            # Абзац — это статика + значения: наш текст может быть длиннее исходного,
            # поэтому полосу абзаца вырезаем до правого поля, иначе справа остаётся
            # хвост старой строки («...PRIME BALI» под нашим текстом)
            _x2 = min(560.0, max(float(bx[2]) + 6.0, a.right_edge if p.get("is_para") else 0.0))
            # Адресные поля: в бланке строка адреса шла до правого края, у нас значение
            # короче — без широкой полосы справа торчит хвост старого адреса («'ATEN B»)
            if re.search(r"address|alamat|passport|issued|date_of_birth", str(p.get("var") or ""), re.I):
                _x2 = 620.0
            pg.draw_rect(_fitz.Rect(max(34.0, bx[0] - 0.5), float(bx[1]) - 2.5,
                                    _x2, float(bx[1]) + h),
                         color=None, fill=(1, 1, 1), width=0)
        pg.get_pixmap(dpi=300).save(str(bg_para))
        doc.close()
    bg_file = bg_para if bg_para.exists() else (fr / "bg.png")
    bg_b64 = _b64(bg_file, "image/png")
    # Размер листа берём из оригинала: E-02 печатается на 612.5×936.5 pt, а не на A4 —
    # если растянуть подложку в A4, все подписи в бланке съезжают относительно значений
    _pgrect = None
    for _cand in (tdir / "blank.pdf", tdir / "example_filled.pdf"):
        if _cand.exists():
            _d = _fitz.open(str(_cand))
            _pgrect = _d[0].rect
            _d.close()
            break
    pw = round(float(_pgrect.width), 2) if _pgrect else 595.28
    ph = round(float(_pgrect.height), 2) if _pgrect else 841.89
    css = ("@font-face{font-family:'Doc';src:url(%s)}"
           "@font-face{font-family:'Doc';font-weight:700;src:url(%s)}\n"
           "@page{size:%.2fpt %.2fpt;margin:0}*{box-sizing:border-box}html,body{margin:0;padding:0}\n"
           ".sheet{position:relative;width:%.2fpt;height:%.2fpt;overflow:hidden;background:#fff}\n"
           ".bg{position:absolute;left:0;top:0;width:%.2fpt;height:%.2fpt}\n"
           ".v{position:absolute;font-family:'Doc';color:#000;white-space:pre-wrap;overflow-wrap:normal;line-height:1.3}\n"
           % (reg_b64, bold_b64, pw, ph, pw, ph, pw, ph))
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">', "<style>%s</style></head>" % css,
             '<body><div class="sheet">', '<img class="bg" src="%s" alt="">' % bg_b64]
    for b in points + paras:
        style = "left:%.2fpt;top:%.2fpt;font-size:%.2fpt;color:%s" % (
            b["x"], b["top"] - round(0.092 * b["size"], 2), b["size"], b.get("color") or "#000")
        if b["bold"]:
            style += ";font-weight:700"
        if b["is_para"]:
            style += ";width:%.2fpt" % (a.right_edge - b["x"])
        else:
            # Точки (одиночные значения) тоже получают ширину до правого поля: иначе
            # длинный адрес или ФИО не переносится и налезает на соседний текст
            _avail = a.right_edge - b["x"]
            if _avail > 40.0:
                style += ";width:%.2fpt" % _avail
        # Подпись внизу листа (ФИО у подписи): места справа мало, длинное имя переносилось
        # вниз и налезало на подсказки «(signature)»/METERAI. Печатаем строку шире влево
        # и прижимаем к правому полю — перенос не нужен, вид как у подписи от руки.
        if b["x"] > 250.0 and b["top"] > 0.80 * ph and "client_name" in (b.get("vars") or []):
            _left = 240.0
            style = "left:%.2fpt;top:%.2fpt;font-size:%.2fpt;color:%s;width:%.2fpt;text-align:right" % (
                _left, b["top"] - round(0.092 * b["size"], 2), b["size"],
                b.get("color") or "#000", a.right_edge - _left)
        # Точка, попавшая в абзац той же строки, уже напечатана внутри абзаца — иначе
        # значение выводится дважды (в E-02 зоны и абзацы размечают одни и те же строки)
        if not b["is_para"] and b.get("bbox"):
            if any(q.get("bbox") and abs(b["bbox"][1] - q["bbox"][1]) < 4.0
                   and q["bbox"][0] - 8.0 <= b["bbox"][0] <= q["bbox"][2] + 8.0 for q in paras):
                continue
        # текст абзаца/точки уже содержит {{ переменные }} — второй раз оборачивать нельзя
        parts.append('<span class="v" style="%s">%s</span>' % (style, b["text"]))
    parts.append("</div></body></html>")
    html = "".join(parts)

    print("абзацев: %d, точек: %d, статики вне шаблона: %d" % (len(paras), len(points), len(static_left)))
    for p in paras:
        print("   АБЗАЦ y%-6.1f x%-6.1f sz%-5.2f %s" % (p["top"], p["x"], p["size"], p["text"][:88]))
    for p in points:
        print("   точка y%-6.1f x%-6.1f %s" % (p["top"], p["x"], p["text"][:60]))
    if a.apply:
        tpl = tdir / "template.html"
        if tpl.exists():
            shutil.copy2(tpl, tdir / "template.html.bak_para")
        if "cv__format" in a.code:
            # В резюме разделители «|» между полями личных данных не сохраняются при
            # разборе строки — возвращаем их и подставляем номер паспорта переменной.
            html = html.replace(
                "Date of Birth: {{ cv_date_of_birth }} Nationality: {{ cv_nationality }} Passport:",
                "Date of Birth: {{ cv_date_of_birth }} | Nationality: {{ cv_nationality }} | Passport: {{ cv_passport_no }}")
            # В эталонной строке номер паспорта не был размечен, поэтому после переменной
            # остался его прежний текст — убираем остаток из блока.
            html = re.sub(r"(Passport: \{\{ cv_passport_no \}\})[0-9 ]+", r"\1", html)
        tpl.write_text(html, encoding="utf-8")
        print("установлено:", tpl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
