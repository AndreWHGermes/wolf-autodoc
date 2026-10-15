"""constructor/convert.py — PDF → HTML-шаблон с автопоиском переменных и самопроверкой.

Пайплайн одного прогона:
  1. разбор PDF (все страницы, 1 страница = 1 лист) через extract_template_pages;
  2. автопоиск переменных: правила по данным (даты, суммы, маски карт, ИНН/КПП/ОГРН,
     паспорт, номер документа, ФИО, компания, срок) + подписи-метки рядом со значением;
  3. замена значений на {{переменные}}, значение сохраняется как default и sample;
  4. рендер шаблона с дефолтами и сверка с оригиналом (страницы, потерянные слова,
     лишняя заливка, незаполненные {{}});
  5. если сверка нашла проблемы — второй прогон с коррекцией (строгий фильтр
     видимости картинок, при необходимости без картинок) и выбор лучшего результата.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import re
import time
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent            # /opt/wolf_v2/core
DATA_DIR = Path("/opt/wolf_v2/data")
TEMPLATES_DIR = CORE_DIR
DOCS_DIR = DATA_DIR / "templates"
PREVIEW_DIR = DATA_DIR / "previews"
EXTRACTOR_PATH = CORE_DIR / "pdf_extract.py"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extractor():
    if not EXTRACTOR_PATH.exists():
        raise RuntimeError(f"нет экстрактора: {EXTRACTOR_PATH}")
    return _load_module("extract_template_pages_run", EXTRACTOR_PATH)


# ------------------------------------------------------------------ детект

# (имя правила, регулярка, тип переменной, уверенность)
RULES = [
    ("date_words", r"\b\d{1,2}(?:st|nd|rd|th)\s+(?:day\s+of\s+)?[A-Z][a-z]+\s+\d{4}\b", "date_words", "high"),
    ("date_iso", r"\b\d{2}-\d{2}-\d{4}\b", "date", "high"),
    ("date", r"\b\d{2}\.\d{2}\.\d{4}\b", "date", "high"),
    ("card_mask", r"\b\d{4,6}\s?\*{4,12}\s?\d{4}\b", "card", "high"),
    ("money_words", r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
                    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
                    r"seventy|eighty|ninety|hundred|thousand|million|billion|and)[\s-]+(?:[a-z]+[\s-]+)*"
                    r"[a-z]+\s+\d{2}\s+kopeks\b", "money_words", "high"),
    ("money_rubles", r"\b\d[\d\s,]{3,}[,.]?\s?\d{0,2}\s+rubles\b", "money", "high"),
    ("money_rub", r"\bRUB\s?[\d][\d,\s]{3,}\b", "money", "high"),
    ("money_usd", r"\bUS?\$\s?[\d][\d,\.]{2,}\b", "money", "high"),
    ("money_usd2", r"\bUSD\s?\$?\s?[\d][\d,\.]{2,}\b", "money", "high"),
    ("inn", r"\bINN\s*\d{10}\b", "inn", "high"),
    ("kpp", r"\bKPP\s*\d{9}\b", "kpp", "high"),
    ("ogrn", r"\bOGRN\s*\d{13}\b", "ogrn", "high"),
    ("passport", r"\b\d{2}\s\d{7}\b|\b[A-Z]\s?\d{8}\b", "passport", "medium"),
    ("company", r"\bLLC\s*\"[A-Z][^\"\n]{1,40}\"|\b[A-Z][A-Z&\.\- ]{3,40}\sLLC\b", "company", "high"),
    ("months", r"\b\d{1,3}\s+months?\b|\b\d{1,2}\s+years?\s+before\s+date\b", "period", "high"),
    ("doc_no", r"\b[a-z]{1,4}\d{7,12}\b", "doc_number", "medium"),
    ("name_upper", r"\b[A-Z]{4,}(?:\s+[A-Z]{4,}){1,3}\b", "name", "low"),
]

# «пустые» бланки: подписи-заглушки из оригинального шаблона
BLANK_RULES = [
    (r"^No\s*([a-z]{1,4}\d{6,12})$", "doc_number", "Номер документа"),
    (r"^today.{0,3}s? date\.?$", "issue_date", "Дата выдачи"),
    (r"^before date\.?$", "period_from", "Период с"),
    (r"^name\.?$", "client_name", "Имя клиента"),
    (r"^for name\.?$", "client_name_in_text", "Имя клиента в тексте"),
    (r"^\(profession\)$", "position_en", "Должность"),
    (r"^random date( \d{4})?$", "start_date", "Дата начала"),
    (r"^USD\s*\$?\s*([\d,]+)$", "income_usd", "Сумма USD"),
]

_SPAN_RE = re.compile(r'<span style="([^"]*)">(.*?)</span>', re.S)
_DIV_RE = re.compile(
    r'<div class="txt" style="left:([-\d.]+)pt;top:([-\d.]+)pt;'
    r'width:([-\d.]+)pt;height:([-\d.]+)pt;">(.*?)</div>', re.S)


def _find_matches(text: str):
    """Все значения-кандидаты в строке; пересечения разрешает приоритет правил."""
    found = []
    for kind, pat, vtype, conf in RULES:
        for m in re.finditer(pat, text):
            if m.group(0).strip():
                found.append({"start": m.start(), "end": m.end(), "kind": kind,
                              "type": vtype, "conf": conf, "value": m.group(0)})
    found.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
    out, last = [], -1
    for f in found:
        if f["start"] >= last:
            out.append(f)
            last = f["end"]
    return out


def _slice(spans, a: int, b: int):
    """Куски текста из списка span'ов между абсолютными смещениями [a, b)."""
    out, pos = [], 0
    for style, text in spans:
        s, e = pos, pos + len(text)
        pos = e
        lo, hi = max(s, a), min(e, b)
        if lo < hi:
            out.append([style, text[lo - s:hi - s]])
    return out


def _style_at(spans, offset: int) -> str:
    pos = 0
    for style, text in spans:
        if pos <= offset < pos + len(text):
            return style
        pos += len(text)
    return spans[-1][0] if spans else ""


def _replace_ranges(spans, matches):
    out, pos = [], 0
    for m in matches:
        out.extend(_slice(spans, pos, m["start"]))
        out.append([_style_at(spans, m["start"]), "{{" + m["var"] + "}}"])
        pos = m["end"]
    out.extend(_slice(spans, pos, 10 ** 9))
    return out


_SIZE_RE = re.compile(r"font-size:([\d.]+)pt")

# слова, которые почти всегда стоят рядом со значением как подпись поля
LABEL_WORDS = ("name", "ref", "no", "number", "date", "address", "adress", "passport",
               "title", "signature", "position", "inn", "kpp", "ogrn", "account",
               "bank", "company", "period", "amount", "salary", "contractor", "client",
               "signed", "issued", "valid", "termination", "duties", "status", "tourist")


def _label_for(page_lines, line, match):
    """Подпись-метка рядом со значением.

    Метка — короткая строка без цифр: слева на той же строке, строкой выше или
    под значением. Заголовки (крупный кегль) и служебные разделители вроде
    «AND»/«BETWEEN» метками не считаются.
    """
    value_size = line.get("size") or 0
    # подпись прямо в строке: «Date: 14-09-2026» → метка «Date»
    prefix = line["text"][:match["start"]].strip()
    inline = re.match(r"^([A-Za-z][A-Za-z ./-]{1,28}?)\s*:\s*$", prefix)
    if inline:
        return inline.group(1).lower()
    best, best_score, best_name = None, 0, None
    for other in page_lines:
        if other is line or other["matched"]:
            continue
        txt = other["text"].strip()
        if not txt or len(txt) > 48 or any(ch.isdigit() for ch in txt):
            continue
        if value_size and (other.get("size") or 0) > value_size + 1.0:
            continue                                   # это заголовок, не подпись
        low = txt.lower().strip(" .:")
        if low.startswith("(") or ")" in low or "(" in low:
            continue                                   # «(Passport:» и прочие заглушки-скобки
        words = [w for w in re.split(r"[^A-Za-z]+", txt) if w]
        all_caps = txt.upper() == txt and any(c.isalpha() for c in txt)
        if all_caps and (len(words) > 1 or len(txt) < 4):
            continue                                   # «REMOTE WORK AGREEMENT», «AND»
        if other["left"] + other["width"] <= line["left"] + 2 and abs(other["top"] - line["top"]) < 8:
            side = 3
        elif 0 < line["top"] - other["top"] < 42 and abs(other["left"] - line["left"]) < 220:
            side = 2
        elif line["top"] < other["top"] < line["top"] + 26 and abs(other["left"] - line["left"]) < 220:
            side = 1
        else:
            continue
        score = side
        if txt.endswith(":"):
            score += 2
        if any(w in low or low in w for w in LABEL_WORDS):
            score += 1
        if match["start"] > len(line["text"]) * 0.45 and side < 3:
            score -= 1
        if score > best_score:
            best, best_score, best_name = txt, score, low
    if best_score < 3:
        return None
    return best_name


def _slug(text: str, limit: int = 28) -> str:
    """Имя переменной из подписи: латиница/цифры/подчёркивания, без мусора."""
    import re as _re
    s = (text or "").strip().lower()
    s = _re.sub(r"[^a-zа-я0-9]+", "_", s).strip("_")
    s = _re.sub(r"[^a-z0-9_]+", "_", s.translate(str.maketrans(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя", "abvgdeejzijklmnoprstufhc4ww_y_eua")))
    s = _re.sub(r"_+", "_", s).strip("_")[:limit]
    if not s or not s[0].isalpha():
        s = f"v_{s}" if s else "var"
    return s


def anonymize(html: str, used_names=None):
    """HTML → HTML с {{переменными}} + список переменных (name/label/type/default)."""
    variables, log = {}, []
    used = used_names or set()

    def build(sheet_html: str, page_lines: list):
        def sub_div(m):
            left, top, width, height, inner = (float(m.group(1)), float(m.group(2)),
                                               float(m.group(3)), float(m.group(4)), m.group(5))
            spans = [[sm.group(1), sm.group(2)] for sm in _SPAN_RE.finditer(inner)]
            if not spans:
                return m.group(0)
            text = "".join(t for _, t in spans)
            sizes = [float(x) for x in _SIZE_RE.findall(inner)]
            line = {"text": text, "left": left, "top": top, "width": width,
                    "size": max(sizes) if sizes else 0.0, "matched": False}

            matches = []
            for f in _find_matches(text):
                key = (f["kind"], f["value"])
                label = _label_for(page_lines, line, f)
                if f["conf"] == "low" and not label:
                    continue      # «низкая уверенность без подписи» — обычно заголовок, не переменная
                name = variables.get(key, {}).get("name")
                if not name:
                    base = _slug(label or f["kind"])
                    base = re.sub(r"[^a-z0-9_]", "_", base).strip("_") or f["kind"]
                    while not re.match(r"^[a-z_][a-z0-9_]*$", base):
                        base = "v_" + base
                    name, n = base, 2
                    while name in used:
                        name, n = f"{base}_{n}", n + 1
                    used.add(name)
                    variables[key] = {
                        "name": name, "label": label or f["kind"], "type": f["type"],
                        "default": f["value"], "sample": f["value"],
                        "auto": True, "confidence": f["conf"],
                        "kind": f["kind"], "occurrences": 0,
                    }
                variables[key]["occurrences"] += 1
                label_src = "label" if label else "тип"
                m2 = dict(f)
                m2["var"] = name
                matches.append(m2)
                line["matched"] = True
                log.append(f"{f['value']} → {{{{{name}}}}} ({label_src}: {label or f['kind']})")
            if not matches:
                return m.group(0)
            new_spans = _replace_ranges(spans, matches)
            inner_new = "".join(f'<span style="{st}">{tx}</span>' for st, tx in new_spans if tx)
            return (f'<div class="txt" style="left:{left:.2f}pt;top:{top:.2f}pt;'
                    f'width:{width:.2f}pt;height:{height:.2f}pt;">{inner_new}</div>')

        return _DIV_RE.sub(sub_div, sheet_html)

    def per_sheet(m):
        sheet = m.group(0)
        lines = []
        for dm in _DIV_RE.finditer(sheet):
            left, top, width, height, inner = (float(dm.group(1)), float(dm.group(2)),
                                               float(dm.group(3)), float(dm.group(4)), dm.group(5))
            txt = "".join(sm.group(2) for sm in _SPAN_RE.finditer(inner))
            sizes = [float(x) for x in _SIZE_RE.findall(inner)]
            lines.append({"text": txt, "left": left, "top": top, "width": width,
                          "size": max(sizes) if sizes else 0.0, "matched": False})
        return build(sheet, lines)

    html = re.sub(r'<div class="sheet">.*?</div>\s*(?=<div class="sheet">|</body>)',
                  per_sheet, html, flags=re.S)
    return html, list(variables.values()), log


# ------------------------------------------------------------------ самопроверка

def _norm_words(text: str) -> list:
    return [w for w in re.split(r"\s+", text.replace("\u00ad", "")) if w]


def render_pdf(html_path: Path, out_pdf: Path):
    import weasyprint
    html_path = Path(html_path)
    html = html_path.read_text(encoding="utf-8")
    # Картинки шаблонов (логотипы банков и т.п.) лежат в статике веб-приложения и в HTML
    # подключены как /static/tpl_assets/... — weasyprint по таким адресам не ходит,
    # поэтому для сборки PDF подставляем путь к файлам на диске (в копии HTML, не в шаблоне).
    if "/static/tpl_assets/" in html:
        assets = str(Path(__file__).resolve().parent.parent / "blocks" / "static" / "tpl_assets") + "/"
        html = html.replace("/static/tpl_assets/", assets)
        tmp = html_path.with_name(html_path.stem + "__pdf.html")
        tmp.write_text(html, encoding="utf-8")
        html_path = tmp
    weasyprint.HTML(filename=str(html_path),
                    base_url=f"file://{TEMPLATES_DIR}/").write_pdf(str(out_pdf))


def get_client_photo_data_uri(client_id: int) -> str:
    """Возвращает data URI с base64 фото клиента (или пустую строку).
    Используется при рендере PDF — мыasyprint не может загрузить http://,
    поэтому встраиваем base64.
    """
    import sqlite3, base64
    db_path = DB_PATH if 'DB_PATH' in globals() else None
    try:
        from core.config import DB_PATH
        c = sqlite3.connect(str(DB_PATH))
        row = c.execute("SELECT photo_path FROM clients WHERE id=?", (client_id,)).fetchone()
        c.close()
        if not row or not row[0]:
            return ""
        photo_file = BASE_DIR / "data" / "client_photos" / row[0]
        if not photo_file.exists():
            return ""
        ext = photo_file.suffix.lstrip('.').lower()
        mime = "image/jpeg" if ext in ('jpg', 'jpeg') else f"image/{ext}"
        b64 = base64.b64encode(photo_file.read_bytes()).decode('ascii')
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


def substitute_values(html: str, values: dict, client_id: int = None) -> str:
    """Подставляет {{ var }} плейсхолдеры. Спец-случай client_photo:
    если в values есть client_photo_url — ставит её (для img src),
    иначе если client_photo — конвертирует в base64 для weasyprint.
    """
    # Сначала обычная подстановка
    def _repl(m):
        var = m.group(1)
        v = values.get(var)
        if v is None:
            return m.group(0)
        s = str(v)
        # Защита от инъекции HTML
        return s.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    html = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _repl, html)

    # client_photo / client_photo_url — без HTML-эскейпа (для <img src>)
    if client_id is not None:
        photo_uri = get_client_photo_data_uri(client_id)
    else:
        photo_uri = ""

    html = html.replace("{{ client_photo }}", photo_uri)
    html = html.replace("{{ client_photo_url }}", photo_uri)

    return html


def qa_report(html_path: Path, src_pdf: Path, ignore=(), values=None):
    """Сверка отрендеренного шаблона с оригиналом. Возвращает отчёт и оценку.

    ``ignore`` — слова исходного бланка, которые шаблон заменяет переменными
    (заглушки вроде «today date», «Name»): они отсутствуют в выводе законно.
    """
    import pymupdf
    ignore_lc = {str(w).lower() for w in (ignore or [])}
    tmp = html_path.with_suffix(".qa.pdf")
    report = {"pages_src": None, "pages_out": None, "missing_words": [],
              "extra_ink": [], "leftover_vars": 0, "images_dropped": [], "ok": False,
              "score": 10 ** 6}
    render_src = html_path
    tmp_html = None
    if values:
        try:
            tmp_html = html_path.with_suffix(".qa.html")
            client_id = values.get('_client_id') if isinstance(values, dict) else None
            filled = substitute_values(html_path.read_text(encoding="utf-8"), values, client_id=client_id)
            tmp_html.write_text(filled, encoding="utf-8")
            render_src = tmp_html
        except Exception as exc:                        # noqa: BLE001
            report["error"] = f"подстановка значений не удалась: {exc}"
            return report
    try:
        render_pdf(render_src, tmp)
    except Exception as exc:                            # noqa: BLE001
        report["error"] = f"рендер не удался: {exc}"
        return report
    try:
        src = pymupdf.open(str(src_pdf))
        out = pymupdf.open(str(tmp))
        report["pages_src"], report["pages_out"] = src.page_count, out.page_count
        src_words = {}
        for page in src:
            for w in _norm_words(page.get_text()):
                src_words[w] = src_words.get(w, 0) + 1
        out_text = "\n".join(p.get_text() for p in out)
        out_words = {}
        for w in _norm_words(out_text):
            out_words[w] = out_words.get(w, 0) + 1
        missing = []
        for w, n in src_words.items():
            if len(w) < 3 or w.lower() in ignore_lc:
                continue
            if out_words.get(w, 0) < n:
                missing.append(w)
        report["missing_words"] = sorted(set(missing))[:40]
        report["ignored"] = sorted(ignore_lc)[:40]
        report["leftover_vars"] = len(re.findall(r"\{\{[^}\n]{0,80}\}\}", out_text))

        import sys as _sys
        if str(TEMPLATES_DIR) not in _sys.path:
            _sys.path.insert(0, str(TEMPLATES_DIR))
        from qa_compare import ink_bands
        for i in range(min(src.page_count, out.page_count)):
            a = ink_bands(src[i])
            b = ink_bands(out[i])
            extra = [round(y - x, 2) for x, y in zip(a, b)]
            if max(extra or [0]) > 4:
                report["extra_ink"].append({"page": i + 1, "bands": extra})
        report["ok"] = (report["pages_src"] == report["pages_out"]
                        and not report["missing_words"]
                        and not report["extra_ink"]
                        and report["leftover_vars"] == 0)
        report["score"] = ((0 if report["pages_src"] == report["pages_out"] else 100)
                           + len(report["missing_words"])
                           + sum(1 for e in report["extra_ink"] if max(e["bands"]) > 8) * 3)
    finally:
        tmp.unlink(missing_ok=True)
        if tmp_html is not None:
            tmp_html.unlink(missing_ok=True)
    return report


def make_previews(doc_id: str, pdf_path: Path, prefix: str = "") -> list:
    """WebP-превью страниц исходника (и результата) для панели «оригинал»."""
    import pymupdf
    from PIL import Image
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    doc = pymupdf.open(str(pdf_path))
    try:
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            out = PREVIEW_DIR / f"{doc_id}{prefix}_p{i}.webp"
            img.save(out, "WEBP", quality=80, method=4)
            made.append(out.name)
    finally:
        doc.close()
    return made


# ------------------------------------------------------------------ прогон

def _strict_visibility(mod, cache):
    """Строгий фильтр: картинка видна, только если её чернила реально есть на странице."""
    from PIL import Image

    def visible(render, scale, bbox, page_rect):
        if render is None:
            return True
        x0, y0, x1, y1 = bbox
        x0, y0 = max(x0, page_rect.x0), max(y0, page_rect.y0)
        x1, y1 = min(x1, page_rect.x1), min(y1, page_rect.y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return False
        box = (int(x0 * scale), int(y0 * scale), int(x1 * scale), int(y1 * scale))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            return False
        crop = render.crop(box).convert("L")
        hist = crop.histogram()
        page_ink = sum(hist[:235]) / (sum(hist) or 1)
        return page_ink > 0.045
    return visible


def _strict_images_of_page(mod, page, doc):
    """Картинки, чьи чернила реально видны на странице.

    Берём пиксели самой картинки, накладываем их область на растр страницы и
    оставляем только те картинки, у которых тёмные точки совпадают с тёмными
    точками страницы. Так отсекаются «нарисованные, но закрытые фоном» штампы,
    которые иначе встают поверх подписей.
    """
    import io as _io
    from PIL import Image

    images = []
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:                                   # noqa: BLE001
        return images
    render, scale = mod._page_render(page)
    for info in infos:
        xref = info.get("xref")
        if not xref:
            continue
        bbox = info["bbox"]
        try:
            uri = mod._data_uri(doc, xref)
        except Exception:                               # noqa: BLE001
            continue
        if render is None:
            images.append({"bbox": bbox, "uri": uri})
            continue
        x0, y0, x1, y1 = bbox
        x0, y0 = max(x0, page.rect.x0), max(y0, page.rect.y0)
        x1, y1 = min(x1, page.rect.x1), min(y1, page.rect.y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        try:
            pil = Image.open(_io.BytesIO(doc.extract_image(xref)["image"])).convert("L")
        except Exception:                               # noqa: BLE001
            continue
        w = max(int((x1 - x0) * scale), 1)
        h = max(int((y1 - y0) * scale), 1)
        try:
            small = pil.resize((w, h))
            region = render.crop((int(x0 * scale), int(y0 * scale),
                                  int(x0 * scale) + w, int(y0 * scale) + h)).convert("L")
        except Exception:                               # noqa: BLE001
            continue
        px_img, px_page = list(small.getdata()), list(region.getdata())
        dark = [i for i, v in enumerate(px_img) if v < 200]
        if len(dark) < 20:
            continue
        hit = sum(1 for i in dark if px_page[i] < 210) / len(dark)
        if hit < 0.45:
            continue
        images.append({"bbox": bbox, "uri": uri})
    return images


def run_conversion(doc: dict) -> dict:
    """Полный прогон конвертации PDF → HTML-шаблон. Возвращает обновлённый документ."""
    doc_id = doc["id"]
    src_pdf = Path(doc["source_pdf"])
    if not src_pdf.is_absolute():
        src_pdf = Path("/opt/wolf_v2/data/sources") / src_pdf
    if not src_pdf.exists():
        raise FileNotFoundError(f"нет исходного PDF: {src_pdf}")

    folder = DOCS_DIR / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    log = [f"исходник: {doc['source_pdf']} ({src_pdf.stat().st_size // 1024} КБ)"]
    best = None

    attempts = [("обычный фильтр видимости", False), ("с коррекцией: строгий фильтр видимости", True)]
    for title, strict in attempts:
        mod = extractor()
        if strict:
            mod._is_visible = _strict_visibility(mod, {})
            mod._images_of_page = lambda page, doc, _m=mod: _strict_images_of_page(_m, page, doc)
        mod.WITH_IMAGES = True
        html = mod.extract_html(str(src_pdf), set())
        html, variables, vlog = anonymize(html)
        attempt_html = folder / ("template.html" if not strict else "template_attempt2.html")
        attempt_html.write_text(html, encoding="utf-8")
        qa = qa_report(attempt_html, src_pdf, ignore=doc.get("qa_ignore") or (),
                       values={v["name"]: v.get("default") for v in variables})
        log.append(f"[{title}] картинок в шаблоне: {html.count('<img')}, переменных: {len(variables)}, "
                   f"страниц {qa.get('pages_out')}/{qa.get('pages_src')}, "
                   f"потерянных слов: {len(qa.get('missing_words', []))}, "
                   f"полос с лишней заливкой: {len(qa.get('extra_ink', []))}")
        cand = {"strict": strict, "html": html, "variables": variables, "qa": qa,
                "vlog": vlog, "path": attempt_html}
        if best is None or qa["score"] < best["qa"]["score"]:
            best = cand
        if qa["ok"]:
            break

    final_html = folder / "template.html"
    final_html.write_text(best["html"], encoding="utf-8")
    (folder / "template_attempt2.html").unlink(missing_ok=True)
    log.extend(best["vlog"][:60])
    if best["strict"]:
        log.append("применена коррекция: строгий фильтр видимости картинок")

    make_previews(doc_id, src_pdf)

    out_pdf = folder / "preview_filled.pdf"
    out_pages = []
    try:
        render_pdf(final_html, out_pdf)
        out_pages = make_previews(doc_id, out_pdf, prefix="_out")
    except Exception as exc:                            # noqa: BLE001
        log.append(f"предпросмотр результата не собрался: {exc}")

    doc = {
        **doc,
        "html": f"docs/{doc_id}/template.html",
        "doc_type": doc_id,
        "filled_sample": doc["source_pdf"],
        "variables": best["variables"],
        "qa": best["qa"],
        "status": "ok" if best["qa"]["ok"] else "needs_review",
        "converted_at": int(time.time()),
        "convert_log": log[-80:],
        "pages": best["qa"].get("pages_src"),
        "out_pages": out_pages,
    }
    return doc
