#!/usr/bin/env python3
"""HTML-сборка документа с потоковым поведением «как в Word» + автоматическая проверка.

Что делает этот шаг (после каркаса build_html_frame.py):
  1. Берёт значения заявки тем же способом, что PDF-подстановка (одна правда о данных).
  2. Раскладывает длинные значения по строкам внутри их места (жадный перенос по словам).
  3. Если из-за переноса блок стал выше — СДВИГАЕТ ВНИЗ блоки, стоящие под ним в той же
     колонке (шапка: номер → ФИО → адрес → вторая строка адреса). Так длинное ФИО толкает
     адрес вниз, а не налезает на него. Кегль НЕ уменьшается никогда.
  4. Собирает PDF (weasyprint) из: A4-листа + подложка бланка из оригинала + текстовые блоки.
  5. Автопроверки: пересечения блоков (наложения), выход за пределы рабочего поля,
     выход за лист, пиксельное расхождение с оригиналом вне зон, остатки чужих данных.

Запуск:
    python3 scripts/build_html_flow.py <code> <app_id> [--test] [--save]
"""
from __future__ import annotations

import shutil

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

BASE = Path("/opt/wolf_v2")
TEMPLATES = BASE / "data" / "templates"
OUT = BASE / "data" / "cache" / "html_flow"
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

A4_W, A4_H = 595.28, 841.89
LEFT_EDGE, RIGHT_EDGE = 40.0, 555.0
TOP_EDGE, BOTTOM_EDGE = 30.0, 812.0
LINE_FACTOR = 1.18          # интерлиньяж как в Word: 1.18 от кегля
ASCENT = 0.905

TEST_SETS = {
    "короткие": {"client_name": "Li Wu", "address_live": "12, Moscow, ul. Tverskaya,",
                 "address_live_2": "D. 1, Kv. 2"},
    "длинные": {"client_name": "Aleksandra Valentinovna Konstantinopolskaya",
                "address_live": "628404, Khanty-Mansiyskiy Avtonomnyy Okrug, G Surgut, Ul Pervoprokhodtsev,",
                "address_live_2": "D. 115/2, Korp. 3, Kv. 456"},
    "предельные": {"client_name": "Bartolomeo Kristoforovich Maksimilianovskiy-Shvedovskiy",
                   "address_live": "693000, Sakhalinskaya Oblast, G Yuzhno-Sakhalinsk, Ul Imeni Kosmonavta Very Fedorovny Belovoy,",
                   "address_live_2": "D. 128/4, Korp. 12, Str. 3, Kv. 1024"},
}


def load_values(code: str, app_id: int) -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location("pdf_fill_mod", str(BASE / "scripts" / "pdf_fill.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.values_for(app_id, code)


def font_paths(code: str) -> dict:
    """Шрифты для каркаса.

    Важно: шрифты, извлечённые из PDF, — это ПОДМНОЖЕСТВА (subset) с внутренней кодировкой
    PDF. В HTML такие файлы отдают не те глифы: буквы пропадали и текст выглядел «A A A KA VA».
    Поэтому для каркаса берём полный шрифт, метрически совпадающий с Arial (Liberation Sans),
    а PDF-шрифт оставляем только как запасной.
    """
    d = TEMPLATES / code / "frame" / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    lib_reg = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
    lib_bold = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
    out = {"regular": None, "bold": None}
    if lib_reg.exists():
        dst = d / "LiberationSans-Regular.ttf"
        if not dst.exists():
            shutil.copy2(lib_reg, dst)
        out["regular"] = dst
    if lib_bold.exists():
        dst = d / "LiberationSans-Bold.ttf"
        if not dst.exists():
            shutil.copy2(lib_bold, dst)
        out["bold"] = dst
    if out["regular"] and out["bold"]:
        return out
    for f in sorted(d.glob("*")):
        n = f.name.lower()
        if "bold" in n and not out["bold"]:
            out["bold"] = f
        elif "bold" not in n and not out["regular"]:
            out["regular"] = f
    if not out["regular"]:
        out["regular"] = out["bold"]
    return out


def text_lines(text: str, width: float, size: float, ffile) -> list[str]:
    """Жадный перенос по словам — как Word: в строку влезает столько слов, сколько влезает."""
    try:
        fobj = pymupdf.Font(fontfile=str(ffile)) if ffile else pymupdf.Font("helv")
        tw = lambda s: fobj.text_length(s, fontsize=size)
    except Exception:
        tw = lambda s: len(s) * size * 0.5
    words = (text or "").split()
    if not words:
        return [""]
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and tw(trial) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    lines.append(cur)
    return lines


def blank_static(code: str) -> list[tuple[float, float, float]]:
    """Статика бланка: (x0, x1, y) по строкам чистого бланка.

    Нужна, чтобы значения вставали в свободные промежутки между словами бланка
    («hereby informs that card No … has been issued for») и не наезжали на них.
    """
    import pymupdf
    blank = TEMPLATES / code / "blank.pdf"
    if not blank.exists():
        return []
    out = []
    d = pymupdf.open(str(blank))
    for page in d:
        for blk in page.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                t = " ".join(s["text"] for s in ln["spans"]).strip()
                if t:
                    b = ln["bbox"]
                    out.append((float(b[0]), float(b[2]), float(b[1])))
    d.close()
    return out


def blank_gap(static, y: float, x: float, tol: float = 3.0) -> float:
    """Свободное место справа от x в той же строке бланка (до следующего слова статики)."""
    limit = RIGHT_EDGE
    for sx0, sx1, sy in static:
        if abs(sy - y) > 11.0:          # допуск покрывает межстрочный интервал бланка
            continue
        if sx0 >= x - tol and sx0 < limit:
            limit = sx0
    return max(0.0, limit - x)


def build_layout(code: str, values: dict) -> dict:
    """Считает блоки: текст, число строк, итоговые координаты (со сдвигами как в Word)."""
    tpl_dir = TEMPLATES / code
    fields = json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8"))
    # у части зон задан сдвиг печати (dy): так держим отступ строки после номера справки,
    # не ломая координаты эталона, по которым читаются значения
    for _z in fields.get("zones", []):
        if _z.get("bbox") and _z.get("dy"):
            _d = float(_z["dy"])
            _z["bbox"] = [_z["bbox"][0], _z["bbox"][1] + _d, _z["bbox"][2], _z["bbox"][3] + _d]
    fz = font_paths(code)
    static = blank_static(code)
    zones = [z for z in fields["zones"] if z.get("bbox")]

    # Сумма прописью в бланке разорвана на две строки — распределяем по ширине её зон
    if values.get("balance_words") and any(z["var"] == "balance_words_2" for z in zones):
        z1 = next(z for z in zones if z["var"] == "balance_words")
        z2 = next(z for z in zones if z["var"] == "balance_words_2")
        size = float(z1.get("size") or 9.0)
        w1 = RIGHT_EDGE - float(z1["bbox"][0])
        fobj = pymupdf.Font(fontfile=str(fz["regular"])) if fz["regular"] else pymupdf.Font("helv")
        words = str(values["balance_words"]).split()
        head, cur = [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if cur and fobj.text_length(trial, fontsize=size) > w1:
                break
            cur = trial
        head = cur
        tail = " ".join(words[len(head.split()):])
        values["balance_words"] = head
        values["balance_words_2"] = tail

    # колонки: блоки с близким левым краем и идущие друг под другом
    zones = sorted(zones, key=lambda z: (round(z["bbox"][0] / 10.0), z["bbox"][1]))
    cols: list[list[dict]] = []
    for z in zones:
        placed = False
        for col in cols:
            if abs(col[-1]["bbox"][0] - z["bbox"][0]) <= 12 and 0 < z["bbox"][1] - col[-1]["bbox"][3] < 60:
                col.append(z)
                placed = True
                break
        if not placed:
            cols.append([z])

    blocks = []
    for col in cols:
        shift = 0.0
        for z in sorted(col, key=lambda z: z["bbox"][1]):
            size = float(z.get("size") or 9.0)
            _para = z.get("para")
            if _para:
                _txt = str(_para)
                for _v in sorted(set(re.findall(r"\{\{\s*([a-z_0-9]+)\s*\}\}", _txt))):
                    _txt = re.sub(r"\{\{\s*%s\s*\}\}" % _v, lambda m, v=_v: str(values.get(v) or ""), _txt)
                _txt = _txt.replace("[[b]]", "<b>").replace("[[/b]]", "</b>")
                _w = float(z["bbox"][2]) - float(z["bbox"][0])
                blocks.append({"var": z["var"], "page": z.get("page") or 1, "text": _txt, "lines": 1,
                               "x": round(max(float(z["bbox"][0]), LEFT_EDGE), 2),
                               "top": round(float(z["bbox"][1]) - 0.15 * size, 2), "size": size,
                               "w": round(_w, 2), "tw": 0.0, "nowrap": False, "para": True,
                               "h": round(size * LINE_FACTOR * (1 + len(_txt) // max(20, int(_w / max(1.0, size * 0.5)))), 2),
                               "htext": round(size * 2, 2), "bold": bool(z.get("bold")),
                               "color": z.get("color") or [0, 0, 0]})
                continue
            w_zone = float(z["bbox"][2]) - float(z["bbox"][0])
            ffile = fz["bold"] if z.get("bold") else fz["regular"]
            text = str(values.get(z["var"]) or "").strip()
            x = min(max(float(z["bbox"][0]), LEFT_EDGE), RIGHT_EDGE - 20)
            nowrap = z["var"] in ("doc_no", "ref_no", "doc_date", "card_mask",
                                  "period_from", "period_to", "balance_rub")
            w_avail = RIGHT_EDGE - x                     # место до правого поля
            # свободный промежуток в этой строке бланка: значение обязано встать в него,
            # иначе наезжает на статику («hereby informs that card No … has been issued for»)
            gap = 0.0 if z.get("source") == "manual" else blank_gap(static, float(z["bbox"][1]), x)
            if gap > 6.0:
                w_avail = min(w_avail, gap - 2.0)
            if nowrap:
                lines = [text]
                w = w_avail
            else:
                try:
                    _fo = pymupdf.Font(fontfile=str(ffile)) if ffile else pymupdf.Font("helv")
                    _need = _fo.text_length(text, fontsize=size)
                except Exception:
                    _need = len(text) * size * 0.5
                # не влезает в исходную зону — переносим на всю доступную ширину до правого поля
                w_cap = min(w_zone, w_avail)
                w = w_zone if _need <= w_cap else max(w_cap, w_avail)
                lines = text_lines(text, w, size, ffile)
            # не влезает даже так (узкий промежуток бланка, например маска карты) — подбираем кегль
            # шагами не более 15 % вниз: наложение текста недопустимо
            try:
                fo_ = pymupdf.Font(fontfile=str(ffile)) if ffile else pymupdf.Font("helv")
                need_ = fo_.text_length(text, fontsize=size)
                if need_ > w_avail + 0.5 and size > 6.0:
                    k = 0
                    while need_ > w_avail + 0.5 and k < 10 and size > 6.0:
                        k += 1
                        size = round(size * 0.97, 2)
                        need_ = fo_.text_length(text, fontsize=size)
                    if nowrap:
                        w = w_avail
                    else:
                        lines = text_lines(text, w, size, ffile)
            except Exception:
                pass
            try:
                fo = pymupdf.Font(fontfile=str(ffile)) if ffile else pymupdf.Font("helv")
                tw = max([fo.text_length(ln, fontsize=size) for ln in lines] + [0.0])
            except Exception:
                tw = len(text) * size * 0.5
            line_h = size * LINE_FACTOR
            extra = max(0.0, (len(lines) - 1)) * line_h
            _org = z.get("origin")
            if _org:
                top_base = float(_org[1]) - ASCENT * size
            else:
                # У зон, размеченных по подписям, базовой линии нет: берём верх полосы строки
                # из эталона (bbox[1] — это начало строки значения) с обычным запасом.
                top_base = float(z["bbox"][1]) - 0.15 * size
            # в потоковых документах (договоры) двигаем и «форменные» строки: если абзац
            # выше перенёсся, иначе значение налезет на статику бланка
            _flowdoc = False
            try:
                _flowdoc = bool(json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8")).get("flow"))
            except Exception:
                _flowdoc = False
            _fixed = bool(z.get("source") == "labels" or (z.get("anchor") and not _flowdoc))
            blocks.append({"var": z["var"], "page": z.get("page") or 1,
                           "text": "\n".join(lines), "lines": len(lines),
                           "x": round(x, 2), "top": round(top_base + shift, 2),
                           "size": size, "w": round(w, 2), "tw": round(tw, 2),
                           "nowrap": nowrap,
                           "h": round(line_h * len(lines), 2), "htext": round(size * len(lines), 2),
                           "bold": bool(z.get("bold")), "fixed": _fixed,
                           "color": z.get("color") or [0, 0, 0]})
            # Значения печатаем строго на своих местах. Накопительный сдвиг нижестоящих строк
            # («как в Word») для форм недопустим: подписи бланка неподвижны, и значение уезжало
            # от своей надписи (Full Name пустой, ФИО напротив «Place, Date of Birth»).
            shift += 0.0
    # Потоковые документы (договоры: реквизиты, подписи идут сплошным списком) требуют сдвига:
    # если значение перенеслось на лишнюю строку, всё, что ниже в той же колонке, уезжает вниз.
    # Формы (анкеты, заявления) так двигать нельзя: подписи бланка неподвижны.
    try:
        _flow = bool(json.loads((tpl_dir / "fields.json").read_text(encoding="utf-8")).get("flow"))
    except Exception:
        _flow = False
    if _flow:
        for _pno in sorted({b.get("page") or 1 for b in blocks}):
            _pb = sorted([b for b in blocks if (b.get("page") or 1) == _pno], key=lambda b: b["top"])
            for _i in range(len(_pb)):
                _a = _pb[_i]
                if _a.get("fixed"):
                    continue
                _abot = _a["top"] + max(_a.get("h") or 0.0, 14.0)
                for _j in range(_i + 1, len(_pb)):
                    _o = _pb[_j]
                    if _o.get("fixed") or _o["top"] >= _abot:
                        continue
                    if _a["x"] + _a["w"] <= _o["x"] + 2 or _o["x"] + _o["w"] <= _a["x"] + 2:
                        continue
                    _o["top"] = round(_abot + 1.5, 2)
    # Наложения больше не «расталкиваем» сдвигом: длинное значение переносится внутри своей
    # полосы, а полосы вырезаются с запасом по высоте.
    #
    # Исключение — многострочные группы одного адреса (addressee_line1/2/3 и подобные): это не
    # самостоятельные поля формы, а продолжение одного блока. Если значение длиннее и
    # переносится, следующие строки должны уехать вниз, иначе они накладываются друг на друга.
    _groups: dict = {}
    for _b in blocks:
        _k = re.sub(r"_line\d+$", "", str(_b.get("var") or ""))
        if _k:
            _groups.setdefault(_k, []).append(_b)
    for _k, _grp in _groups.items():
        if len(_grp) < 2:
            continue
        _grp.sort(key=lambda b: b["top"])
        for _prev, _cur in zip(_grp, _grp[1:]):
            _want = round(_prev["top"] + _prev["h"] + 6.0, 2)
            if _cur["top"] < _want:
                _cur["top"] = _want
    for _ in range(40):
        _moved = False
        for _b in blocks:
            if _b.get("fixed") or _b.get("para"):
                continue
            for _o in blocks:
                if _o is _b or _o.get("fixed") or _o.get("para"):
                    continue
                if _b["x"] + _b["tw"] <= _o["x"] + 1.5 or _o["x"] + _o["tw"] <= _b["x"] + 1.5:
                    continue
                if _b["top"] + _b["h"] <= _o["top"] + 1.5 or _o["top"] + _o["h"] <= _b["top"] + 1.5:
                    continue
                if _o["top"] < _b["top"]:
                    continue
                _o["top"] = round(_b["top"] + _b["h"] + 1.0, 2)
                _moved = True
        if not _moved:
            break
    return {"blocks": blocks, "fields": fields, "fonts": fz}


def render_html(code: str, layout: dict) -> str:
    tpl_dir = TEMPLATES / code
    fr = font_paths(code)
    fz = layout["fonts"]
    reg = (fz["regular"] or Path("x")).name
    bold = (fz["bold"] or fz["regular"] or Path("x")).name
    sheet_w, sheet_h = A4_W, A4_H
    _bg = tpl_dir / "frame" / "bg.png"
    if _bg.exists():
        try:
            _b = pymupdf.open(str(_bg))
            sheet_w, sheet_h = float(_b[0].rect.width), float(_b[0].rect.height)
        except Exception:
            pass
    css = f"""@font-face {{ font-family:'Doc'; src:url('fonts/{reg}'); }}
@font-face {{ font-family:'Doc'; font-weight:700; src:url('fonts/{bold}'); }}
@page {{ size:{sheet_w}pt {sheet_h}pt; margin:0; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; }}
.sheet {{ position:relative; width:{sheet_w}pt; height:{sheet_h}pt; overflow:hidden; background:#fff; }}
.bg {{ position:absolute; left:0; top:0; width:{sheet_w}pt; height:{sheet_h}pt; }}
.guide {{ position:absolute; left:{LEFT_EDGE}pt; top:{TOP_EDGE}pt;
          width:{RIGHT_EDGE-LEFT_EDGE}pt; height:{BOTTOM_EDGE-TOP_EDGE}pt; }}
.v {{ position:absolute; line-height:{LINE_FACTOR}; white-space:pre-wrap;
      overflow-wrap:normal; word-break:keep-all; font-family:'Doc'; color:#000; }}
.v.nowrap {{ white-space:pre; }}
.v.para {{ white-space:normal; }}
"""
    # Листов столько, сколько подложек: договоры занимают 2-3 страницы, и каждая должна
    # попасть в документ со своими значениями (bg-1.png, bg-2.png, ...).
    _pages = sorted(int(m.group(1)) for m in
                    (re.match(r"bg-(\d+)\.png$", x.name) for x in (tpl_dir / "frame").glob("bg-*.png")) if m) or [1]
    _head = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{code}</title>',
             f'<style>{css}</style></head><body>']
    _by_page = {pno: [] for pno in _pages}
    parts = []
    for b in layout["blocks"]:
        if not b["text"]:
            continue
        _dst = _by_page.get(b.get("page") or 1, _by_page[_pages[0]])
        c = b["color"]
        # печатаем КАЖДУЮ вычисленную строку отдельно и запрещаем движку переносить текст:
        # перенос считаем мы (как Word), иначе браузер рвёт слова по буквам
        if b.get("para"):
            _dst.append('<span class="v para" style="left:%.2fpt; top:%.2fpt; font-size:%.2fpt;'
                         'width:%.2fpt; color:#%02X%02X%02X;%s">%s</span>'
                         % (b["x"], b["top"], b["size"], b["w"], c[0], c[1], c[2],
                            "font-weight:700;" if b["bold"] else "", b["text"]))
            continue
        for i, ln in enumerate(b["text"].split("\n")):
            top = b["top"] + i * b["size"] * LINE_FACTOR
            _dst.append('<span class="v nowrap" style="left:%.2fpt; top:%.2fpt; font-size:%.2fpt;'
                         'color:#%02X%02X%02X;%s">%s</span>'
                         % (b["x"], top, b["size"], c[0], c[1], c[2],
                            "font-weight:700;" if b["bold"] else "",
                            ln.replace("&", "&amp;").replace("<", "&lt;")))
    parts = list(_head)
    for _pno in _pages:
        parts.append('<div class="sheet">')
        _bgname = 'bg-%d.png' % _pno
        if not (tpl_dir / 'frame' / _bgname).exists():
            _bgname = 'bg.png'      # подложка ещё не разложена по страницам
        parts.append('<img class="bg" src="%s" alt="">' % _bgname)
        parts.append('<div class="guide"></div>')
        parts.extend(_by_page[_pno])
        parts.append('</div>')
    parts.append("</body></html>")
    return "\n".join(parts)


def render_img(p: str, dpi: int = 300) -> Image.Image:
    d = pymupdf.open(p)
    pm = d[0].get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")
    d.close()
    return img


def diff_pct(a: Image.Image, b: Image.Image, mask=None) -> float:
    if a.size != b.size:
        b = b.resize(a.size)
    d = ImageChops.difference(a, b).convert("L")
    if mask is not None:
        d = ImageChops.multiply(d, mask)
    return 100.0 * sum(d.histogram()[24:]) / (a.size[0] * a.size[1])


def mask_for(img: Image.Image, blocks: list[dict], dpi: int = 300) -> Image.Image:
    m = Image.new("L", img.size, 255)
    k = dpi / 72.0
    for b in blocks:
        if not b["text"]:
            continue
        x0, y0 = b["x"] * k, b["top"] * k
        x1, y1 = (b["x"] + max(b.get("tw", b["w"]), 6.0)) * k, (b["top"] + b["h"] + 2) * k
        m.paste(0, (max(0, int(x0) - 3), max(0, int(y0) - 3),
                    min(img.width, int(x1) + 3), min(img.height, int(y1) + 3)))
    return m


def problems_of(blocks: list[dict]) -> list[str]:
    pr = []
    for b in blocks:
        if not b["text"]:
            continue
        if b["x"] < LEFT_EDGE - 0.6 or b["x"] + b["tw"] > RIGHT_EDGE + 0.6:
            pr.append("вышло за рабочее поле по ширине: %s" % b["var"])
        if b["top"] < TOP_EDGE - 0.6 or b["top"] + b.get("htext", b["h"]) > BOTTOM_EDGE + 0.6:
            pr.append("вышло за рабочее поле по высоте: %s" % b["var"])
        if b["top"] + b.get("htext", b["h"]) > A4_H or b["x"] + b["tw"] > A4_W:
            pr.append("вышло за лист A4: %s" % b["var"])
    # наложение считаем только между блоками ОДНОЙ страницы: иначе «налезают» друг на друга
    # блоки разных листов (например, строка сторон на стр.1 и дата подписи на стр.3)
    vis = [b for b in blocks if b["text"]]
    vis.sort(key=lambda b: (b.get("page") or 1, b["top"], b["x"]))
    for i in range(len(vis)):
        for j in range(i + 1, len(vis)):
            a, b = vis[i], vis[j]
            if (a.get("page") or 1) != (b.get("page") or 1):
                continue
            # допуск 1.5 pt: значения могут стоять вплотную (номер и дата в справке) — это не наложение
            if not (a["x"] + a["tw"] <= b["x"] + 1.5 or b["x"] + b["tw"] <= a["x"] + 1.5
                    or a["top"] + a.get("htext", a["h"]) <= b["top"] + 0.8 or b["top"] + b.get("htext", b["h"]) <= a["top"] + 0.8):
                pr.append("наложение блоков: %s (x%.0f-%.0f y%.0f-%.0f) и %s (x%.0f-%.0f y%.0f-%.0f)" % (a["var"], a["x"], a["x"]+a["tw"], a["top"], a["top"]+a.get("htext",a["h"]), b["var"], b["x"], b["x"]+b["tw"], b["top"], b["top"]+b.get("htext",b["h"])))
    return pr


def run(code: str, app_id: int, overrides: dict | None = None, tag: str = "",
        save: bool = False) -> dict:
    vals = load_values(code, app_id)
    if overrides:
        vals.update(overrides)
    layout = build_layout(code, vals)
    html = render_html(code, layout)
    OUT.mkdir(parents=True, exist_ok=True)
    out_pdf = OUT / ("%s%s.pdf" % (code, tag))
    from services.render import render_pdf
    render_pdf(html, base_dir=str(TEMPLATES / code / "frame"), out_path=out_pdf)

    pr = problems_of(layout["blocks"])
    ref = str(TEMPLATES / code / "example_filled.pdf")
    a, b = render_img(ref), render_img(str(out_pdf))
    mask = mask_for(a, layout["blocks"])
    outside = diff_pct(a, b, mask)
    total = diff_pct(a, b)
    if not overrides and outside > 0.45:
        pr.append("бланк изменился вне зон: %.2f%%" % outside)

    if save and not pr:
        (TEMPLATES / code / "frame" / "flow.html").write_text(html, encoding="utf-8")

    return {"pdf": str(out_pdf), "html": html, "blocks": layout["blocks"],
            "total": total, "outside": outside, "problems": pr, "values": vals}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("app", type=int)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    r = run(a.code, a.app, save=a.save)
    print("=== HTML-каркас (поток как в Word): %s ===" % a.code)
    print("блоков: %d | отличий всего %.2f%% | вне зон %.2f%%"
          % (len([b for b in r["blocks"] if b["text"]]), r["total"], r["outside"]))
    for b in r["blocks"]:
        if b["text"]:
            print("   %-15s строк:%d  x=%.0f y=%.0f w=%.0f кегль=%s%s"
                  % (b["var"], b["lines"], b["x"], b["top"], b["w"], b["size"],
                     " ЖИРНЫЙ" if b["bold"] else ""))
    print("PDF: %s" % r["pdf"])
    print("  " + ("⚠ " + "; ".join(r["problems"]) if r["problems"]
                  else "✓ наложений нет · за поле и за лист не вышло · бланк не тронут"))
    if a.test:
        print("\n=== тестовые значения ===")
        for name, ov in TEST_SETS.items():
            rr = run(a.code, a.app, ov, tag="_" + name)
            print("%-11s строк у ФИО: %d, у адреса: %d → %s"
                  % (name,
                     next(b["lines"] for b in rr["blocks"] if b["var"] == "client_name"),
                     next(b["lines"] for b in rr["blocks"] if b["var"] == "address_live"),
                     "OK" if not rr["problems"] else "ПРОБЛЕМЫ: " + "; ".join(rr["problems"])[:120]))
            print("            %s" % rr["pdf"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
