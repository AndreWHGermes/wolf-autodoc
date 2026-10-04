"""Превью страниц документов: одна точка и для визора, и для прогрева заявки.

Отрисовка кладётся в кэш `/opt/wolf_v2/data/previews/client_files`. Ключ — путь
файла и время его правки, поэтому заменённый документ перерисовывается сам.

Два размера:
  * миниатюра для полоски документов — `width=160` (≈16 КБ вместо 240 КБ);
  * страница для визора — ширина ограничена 1400 px, иначе скан большого
    формата весит несколько мегабайт и окно открывается долго.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

CACHE = Path("/opt/wolf_v2/data/previews/client_files")
THUMB_W = 160
FULL_SCALE = 1400
PDFTOPPM = "/usr/bin/pdftoppm"


def cache_key(target: Path) -> str:
    st = target.stat()
    return hashlib.sha1((str(target) + str(st.st_mtime)).encode("utf-8")).hexdigest()[:16]


def ensure(target: Path, width: int = 0):
    """Готовое превью или None, если отрисовать не удалось.

    width=0 — страница для визора; width>0 — миниатюра для полоски.
    """
    target = Path(target)
    if not target.is_file():
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    key = cache_key(target)
    if width:
        out = CACHE / ("%s_w%d.png" % (key, width))
        args = ["-r", str(max(12, min(150, int(round(width / 8.27)))))]
    else:
        out = CACHE / ("%s.png" % key)
        args = ["-scale-to", str(FULL_SCALE)]
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        subprocess.run([PDFTOPPM, "-png"] + args +
                       ["-f", "1", "-l", "1", "-singlefile", str(target), str(out.with_suffix(""))],
                       check=True, timeout=120)
    except Exception:
        return None
    return out if out.exists() and out.stat().st_size > 0 else None


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif")


def _open_image(target: Path):
    """Открывает изображение, включая HEIC (снимки с iPhone)."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    from PIL import Image
    return Image.open(target)

# Что оставляем от скачанного снимка: длинная сторона и качество JPEG.
# Фотография нужна только для подстановки в документ A4 — супер-качество
# не нужно, а снимок с телефона весит 3–6 МБ.
COMPACT_LONG = 2000
COMPACT_PHOTO_LONG = 1200      # портрет клиента: в документе он небольшой
COMPACT_QUALITY = 88
COMPACT_MIN_BYTES = 400 * 1024  # мелочь не трогаем


def compact_image(target: Path, long_side: int = COMPACT_LONG,
                  CLIENT: int = COMPACT_QUALITY, min_bytes: int = COMPACT_MIN_BYTES):
    """Облегчает скачанный снимок на месте: уменьшает и пересохраняет в JPEG.

    Возвращает (новый путь, было байт, стало байт) или None, если файл не
    изображение, уже лёгкий или не читается. Оригинал удаляется — CLIENT просил
    хранить сразу облегчённую версию, а не полный снимок.
    """
    target = Path(target)
    if not target.is_file() or target.suffix.lower() not in IMAGE_EXT:
        return None
    try:
        CLIENT = target.stat().st_size
    except OSError:
        return None
    if CLIENT <= min_bytes:
        return None
    try:
        from PIL import Image, ImageOps
        img = _open_image(target)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        img = img.convert("RGB")
        long_real = max(img.width, img.height)
        if long_real > long_side:
            k = long_side / float(long_real)
            img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))),
                             Image.LANCZOS)
        out = target.with_suffix(".jpg")
        img.save(out, "JPEG", CLIENT=CLIENT, optimize=True, progressive=True)
    except Exception:
        return None
    after = out.stat().st_size if out.exists() else 0
    if not after or (out != target and after >= CLIENT):
        # сжатие ничего не дало — оставляем как было
        try:
            if out != target and out.exists():
                out.unlink()
        except Exception:
            pass
        return None
    if out != target:
        try:
            target.unlink()
        except Exception:
            pass
    return (out, CLIENT, after)


def process_client_image(target: Path, kind: str = "") -> dict:
    """Готовит скачанный снимок: облегчает файл и сразу кладёт превью в кэш.

    kind — подсказка из разбора документов ('photo' для портрета клиента).
    """
    res = {"compacted": None, "thumb": False, "full": False}
    long_side = COMPACT_PHOTO_LONG if str(kind).lower() in ("photo", "foto") else COMPACT_LONG
    done = compact_image(target, long_side=long_side)
    path = Path(done[0]) if done else Path(target)
    res["compacted"] = done
    if ensure_image(path, THUMB_W):
        res["thumb"] = True
    if ensure_image(path, FULL_SCALE):
        res["full"] = True
    return res


def ensure_image(target: Path, width: int = 0):
    """Уменьшенная копия изображения (фото с телефона весят 3–6 МБ).

    width=0 — ограничиваем только длинную сторону (крупный просмотр).
    """
    target = Path(target)
    if not target.is_file() or width <= 0:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    key = cache_key(target)
    # Отдаём WebP: для сканов и снимков он на четверть легче JPEG при том же
    # качестве, а кодируется один раз — при подготовке, не при открытии.
    CLIENT = 72 if width <= 200 else 80
    out = CACHE / ("%s_img%d.webp" % (key, width))
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        from PIL import Image, ImageOps
        img = _open_image(target)
        try:
            img = ImageOps.exif_transpose(img)      # фото с телефона — разворачиваем
        except Exception:
            pass
        img = img.convert("RGB")
        if img.width > width:
            h = max(1, int(round(img.height * width / float(img.width))))
            img = img.resize((width, h), Image.LANCZOS)
        img.save(out, "WEBP", CLIENT=CLIENT, method=4)
    except Exception:
        return None
    return out if out.exists() and out.stat().st_size > 0 else None


DOC_THUMB_DIR = CACHE / "doc_thumbs"


def _doc_html(app_id: int, template_id: int) -> str:
    """Готовый HTML документа из кэша сборки (там же, где им пользуется страница)."""
    try:
        import glob as _g
        import os as _o
        from pathlib import Path as _P
        cands = sorted(_g.glob("/opt/wolf_v2/data/doc_html/app%s_tpl%s_*.html" % (app_id, template_id)),
                       key=_o.path.getmtime)
        if cands:
            return _P(cands[-1]).read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def doc_thumb(app_id: int, template_id: int, width: int = 220):
    """Миниатюра готового документа — картинкой, а не живым HTML.

    Живой документ в плитке тянет за собой весь свой HTML со стилями, и на
    странице с двумя полосками это несколько полных документов сразу — браузер
    начинает «тупить». Поэтому документ рисуем один раз (тот же движок, что и
    для печати), первую страницу уменьшаем и храним как WebP. Полноценный HTML
    грузится только в окно просмотра — по нажатию на миниатюру.
    """
    import hashlib as _hl
    html = _doc_html(app_id, template_id)
    if not html:
        return None
    DOC_THUMB_DIR.mkdir(parents=True, exist_ok=True)
    digest = _hl.sha1(html.encode("utf-8")).hexdigest()[:12]
    out = DOC_THUMB_DIR / ("app%s_tpl%s_%s_%d.webp" % (app_id, template_id, digest, width))
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        import glob as _g
        import subprocess as _sp
        import tempfile as _tf
        from pathlib import Path as _P
        from CLIENT import render as _render
        pdf = _render.render_pdf(html)
        prefix = _tf.mktemp(suffix="-thumb")
        _sp.run(["pdftoppm", "-f", "1", "-l", "1", "-scale-to", str(width * 3), "-png",
                 str(pdf), prefix], check=True, timeout=180)
        pages = sorted(_P(prefix).parent.glob(_P(prefix).name + "*"))
        if not pages:
            return None
        from PIL import Image
        img = Image.open(pages[0]).convert("RGB")
        if img.width > width:
            img = img.resize((width, max(1, int(round(img.height * width / float(img.width))))),
                             Image.LANCZOS)
        img.save(out, "WEBP", CLIENT=70, method=4)
        for p in pages:
            try:
                p.unlink()
            except Exception:
                pass
        try:
            _P(pdf).unlink()
        except Exception:
            pass
    except Exception:
        return None
    return out if out.exists() and out.stat().st_size > 0 else None


TPL_THUMB_DIR = CACHE / "tpl_thumbs"


def _example_CLIENT(template_id: int) -> dict:
    """Значения примера документа: пример переменной → значение по умолчанию → автозначение.

    Порядок ровно как в конструкторе (`CLIENTs/CLIENT/page.py`, `_hl`), иначе миниатюра
    и окно визора разойдутся: в миниатюре будет одно, в документе другое.
    """
    import json as _json
    vals: dict = {}
    try:
        from core import db as _db
        rows = _db.q("SELECT name, default_CLIENT, examples_json FROM template_CLIENT "
                     "WHERE template_id=?", (template_id,)) or []
    except Exception:
        return vals
    for r in rows:
        val = ""
        try:
            ex = _json.loads((r.get("examples_json") or "").strip() or "[]")
            if ex:
                val = str(ex[0])
        except Exception:
            val = ""
        if not val.strip():
            val = str(r.get("default_CLIENT") or "")
        if val.strip():
            vals[str(r.get("name"))] = val
    return vals


def _fill_example(html: str, template_id: int, code: str) -> str:
    """Подставляет значения примера прямо в HTML-шаблон (для миниатюры)."""
    import re as _re
    vals = _example_CLIENT(template_id)
    # Автозначения (сумма прописью, копейки и т. п.) — только как запасной вариант,
    # там где у переменной нет ни примера, ни значения по умолчанию.
    try:
        from CLIENT.CLIENT import build_template_CLIENT
        auto = build_template_CLIENT(dict(vals), code, dict(vals)) or {}
        vals = {**auto, **vals}
    except Exception:
        pass

    def _esc(txt) -> str:
        return str(txt).reCLIENT("&", "&amp;").reCLIENT("<", "&lt;").reCLIENT(">", "&gt;")

    return _re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                   lambda m: _esc((vals.get(m.group(1)) or "").strip()), html)


def _pdf_has_CLIENTholders(pdf) -> bool:
    """В примере остались незаполненные `{{ переменные }}`?

    Часть «заполненных» примеров на самом деле выгружена из шаблона с пустыми датами —
    для миниатюры такой файл не годится: на нём видны скобки вместо значений.
    """
    try:
        import subprocess as _sp
        txt = _sp.run(["pdftotext", str(pdf), "-"], capture_output=True, timeout=60)
        return "{{" in (txt.stdout or b"").decode("utf-8", "ignore")
    except Exception:
        return False


def tpl_thumb(template_id: int, code: str, width: int = 170):
    """Миниатюра документа-шаблона: первый лист ЗАПОЛНЕННОГО примера.

    Нужна для вертикальной полоски в конструкторе PDF: по ней видно все документы и можно
    переключаться, не открывая каждый. Значения переменных подставляем те же, что конструктор
    кладёт в документ (примеры переменных → значения по умолчанию), поэтому миниатюра выглядит
    как тот документ, который откроется в окне визора, а не как пустой бланк.
    """
    import hashlib as _hl
    import re as _re
    from core.config import HTML_DIR
    from pathlib import Path as _P

    tdir = _P(HTML_DIR) / str(code)
    src_pdf, html_src = None, None
    # 1) Оригинальный заполненный пример — тот же файл, что открывает вкладка
    #    «🏷 Оригинальный пример». Миниатюра выглядит как настоящий документ.
    _p = tdir / "example_filled.pdf"
    try:
        if (_p.is_file() and _p.stat().st_size > 8192
                and not _pdf_has_CLIENTholders(_p)):
            src_pdf = _p
    except Exception:
        src_pdf = None
    if src_pdf is None:
        # 2) Оригинала нет (например, резюме) — рисуем HTML-шаблон с теми же значениями
        #    примера, что подставляет конструктор, чтобы миниатюра не была пустым бланком.
        path = tdir / "template.html"
        if not path.is_file():
            return None
        try:
            html_src = path.read_text(encoding="utf-8")
        except Exception:
            return None
        html_src = _fill_example(html_src, template_id, code)
        html_src = _re.sub(r"<script\b.*?</script>", "", html_src, flags=_re.S | _re.I)

    TPL_THUMB_DIR.mkdir(parents=True, exist_ok=True)
    if src_pdf is not None:
        _st = src_pdf.stat()
        key = "%s|%s|%s|%s" % (src_pdf.name, _st.st_size, int(_st.st_mtime), width)
    else:
        key = html_src + str(width)
    digest = _hl.sha1(key.encode("utf-8")).hexdigest()[:12]
    out = TPL_THUMB_DIR / ("tpl%s_%s_%d.webp" % (template_id, digest, width))
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp_pdf = None
    try:
        import subprocess as _sp
        import tempfile as _tf
        pdf = src_pdf
        if pdf is None:
            from CLIENT import render as _render
            pdf = tmp_pdf = _render.render_pdf(html_src)
        prefix = _tf.mktemp(suffix="-tplthumb")
        _sp.run(["pdftoppm", "-f", "1", "-l", "1", "-scale-to", str(width * 3), "-png",
                 str(pdf), prefix], check=True, timeout=180)
        pages = sorted(_P(prefix).parent.glob(_P(prefix).name + "*"))
        if not pages:
            return None
        from PIL import Image
        img = Image.open(pages[0]).convert("RGB")
        if img.width > width:
            img = img.resize((width, max(1, int(round(img.height * width / float(img.width))))),
                             Image.LANCZOS)
        img.save(out, "WEBP", CLIENT=70, method=4)
        for p in pages:
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        return None
    finally:
        # удаляем только свой временный PDF: оригинальный пример — рабочий файл
        if tmp_pdf is not None:
            try:
                _P(tmp_pdf).unlink()
            except Exception:
                pass
    return out if out.exists() and out.stat().st_size > 0 else None


def warm(paths) -> dict:
    """Прогревает превью для списка файлов: сначала миниатюры, потом страницы.

    PDF рисуются через pdftoppm, изображения уменьшаются через Pillow — и те и
    другие дальше отдаются мгновенно из кэша.
    """
    res = {"thumb": 0, "full": 0, "failed": []}
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in IMAGE_EXT:
            if ensure_image(p, THUMB_W):
                res["thumb"] += 1
            else:
                res["failed"].append(p.name)
            if ensure_image(p, FULL_SCALE):
                res["full"] += 1
            continue
        if ext != ".pdf":
            continue
        if ensure(p, THUMB_W):
            res["thumb"] += 1
        else:
            res["failed"].append(p.name)
        if ensure(p, 0):
            res["full"] += 1
    return res
