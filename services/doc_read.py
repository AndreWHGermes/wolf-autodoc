"""Чтение документов клиента: PDF, сканы, фотографии, iPhone-HEIC.

Правило: из любого документа надо получить ТЕКСТ.
  PDF с текстовым слоем  → берём текст как есть;
  PDF-скан (текста нет)  → рендерим страницы и читаем OCR;
  PNG / JPG / JPEG       → OCR (русский + английский);
  HEIC / HEIF (iPhone)   → конвертируем и читаем OCR.

Распознавание: tesseract, языки rus+eng. Изображения предварительно
увеличиваются и обесцвечиваются — на паспортных сканах это заметно
улучшает точность.
"""
from __future__ import annotations

from pathlib import Path

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
HEIC_EXT = (".heic", ".heif")
OCR_LANGS = "rus+eng"

# Скан паспорта бывает в огромном разрешении (лист PDF на 5000×7300 точек). Рендер
# такого листа в 300 dpi даёт 150 мегапикселей: tesseract захлёбывается, память
# уходит в swap, и распознавание выдаёт мусор вместо даты. Поэтому картинку перед
# OCR приводим к разумному размеру.
OCR_MAX_SIDE = 3000


def _pixmap_for_ocr(page, dpi: int = 300, max_side: int = OCR_MAX_SIDE):
    """Снимок страницы PDF с ограничением размера: длинная сторона ≤ max_side."""
    rect = page.rect
    long_pt = max(rect.width, rect.height)
    if long_pt > 0:
        px = long_pt * dpi / 72.0
        if px > max_side:
            dpi = max(100, int(dpi * max_side / px))
    return page.get_pixmap(dpi=dpi)

# Распознавание не должно тормозить интерфейс: tesseract запускается через
# обёртку с пониженным приоритетом (nice 15) и одним потоком. Настройка живёт
# в самом модуле pytesseract, поэтому действует для всех вызовов ниже.
try:
    import pytesseract as _pt
    if Path("/opt/wolf_v2/scripts/tesseract_nice.sh").is_file():
        _pt.pytesseract.tesseract_cmd = "/opt/wolf_v2/scripts/tesseract_nice.sh"
except Exception:
    pass


def _ocr_image(path: Path) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    img = Image.open(path)
    try:
        img = ImageOps.exif_transpose(img)          # фото с телефона — разворачиваем
    except Exception:
        pass
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.width < 1600:                            # мелкий скан — увеличиваем
        k = 1600 / max(1, img.width)
        img = img.resize((int(img.width * k), int(img.height * k)))
    gray = ImageOps.grayscale(img)
    text = pytesseract.image_to_string(gray, lang=OCR_LANGS)

    # Снимок экрана или фото с телефона часто не поддаётся с первого прохода:
    # серый фон, блики, сжатие. Признак неудачи — в тексте нет ни одной даты в
    # формате «13.06.2012»: печатные поля паспорта («Дата рождения», «Дата выдачи»,
    # «Дата окончания») до первого прохода не доходят, текст обрывается на самой
    # метке — хотя на снимке даты видны крупно и чётко. Тогда читаем ещё раз —
    # с контрастом, увеличенным вдвое и без разбивки на абзацы (psm 6).
    import re as _re
    _has_date = bool(_re.search(r"\d{2}[.,]\d{2}[.,]\d{4}", text))
    if len(text.strip()) < 40 or not _has_date:
        big = ImageOps.grayscale(img)
        big = ImageOps.autocontrast(big, cutoff=2)
        big = big.resize((big.width * 2, big.height * 2), Image.LANCZOS)
        second = pytesseract.image_to_string(big, lang=OCR_LANGS, config="--psm 6")
        if len(second.strip()) > len(text.strip()):
            text = second
    return text


def _ocr_heic(path: Path) -> str:
    """iPhone-фото: конвертируем в JPEG и читаем."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return _ocr_image(path)
    except Exception:
        pass
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        jpg = Path(td) / (path.stem + ".jpg")
        subprocess.run(["heif-convert", str(path), str(jpg)], capture_output=True, timeout=120)
        if jpg.exists():
            return _ocr_image(jpg)
    return ""


def mrz_text(path) -> str:
    """Машиночитаемая зона паспорта отдельным проходом.

    В паспорте РФ MRZ — самый надёжный источник данных: фамилия и имя латиницей,
    номер паспорта, дата рождения, срок действия. Общее распознавание страницы
    эту полосу портит (мелкий шрифт, голограмма), поэтому читаем низ отдельно,
    с увеличением и белым списком символов.

    Паспорта приходят и фотографией, и сканом внутри PDF — PDF сначала
    разбираем на страницы картинками, иначе PIL его не откроет.
    """
    try:
        import pytesseract
        from PIL import Image, ImageOps

        images = []
        ext = ''
        try:
            ext = sniff_ext(path)
        except Exception:                              # noqa: BLE001
            ext = ''
        low = str(path).lower()
        if ext == '.pdf' or low.endswith('.pdf'):
            import pymupdf
            doc = pymupdf.open(path)
            for pg in doc:
                pm = _pixmap_for_ocr(pg, dpi=300)
                images.append(Image.frombytes('RGB', (pm.width, pm.height), pm.samples))
        else:
            img = Image.open(path)
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:                          # noqa: BLE001
                pass
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            images.append(img)
        if not images:
            return ""

        # полосу MRZ OCR-им по частям: страница целиком «слепнет» на мелком шрифте
        chunks = []
        for img in images:
            w, h = img.size
            for y0, y1 in ((0.78, 1.0), (0.70, 0.95), (0.55, 0.85)):
                crop = img.crop((0, int(h * y0), w, int(h * y1)))
                crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
                crop = ImageOps.grayscale(crop)
                out = pytesseract.image_to_string(
                    crop, lang="eng", config="--psm 6 "
                    "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
                )
                # строки MRZ разделяем переводом строки: склеенные в одну, они дают
                # мусор в разборе (третья часть ФИО захватывает цифры соседней строки)
                for ln in (out or "").splitlines():
                    ln = ln.strip()
                    if len(ln) > 25:                       # похоже на строку MRZ
                        chunks.append(ln)
        return "\n".join(dict.fromkeys(chunks))
    except Exception:
        return ""


def sniff_ext(path) -> str:
    """Определяет тип файла по содержимому, а не по расширению.

    В папках клиентов встречаются файлы вообще без расширения
    («PASSPORT - CLIENT MIKHEEVA») — читаем их по сигнатуре.
    """
    p = Path(path)
    ext = p.suffix.lower()
    try:
        head = p.open("rb").read(16)
    except Exception:
        return ext
    if head[:4] == b"%PDF":
        return ".pdf"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:4] == b"RIFF" and b"WEBP" in head:
        return ".webp"
    if head[:2] == b"II" or head[:2] == b"MM" or b"ftypheic" in p.open("rb").read(64):
        return ".heic"
    return ext


def _read_text_uncached(path) -> str:
    """Текст документа. Пусто — если прочитать не удалось."""
    p = Path(path)
    if not p.exists():
        return ""
    ext = sniff_ext(p)

    if ext == ".pdf":
        try:
            import pymupdf
            doc = pymupdf.open(str(p))
            out = []
            for i in range(min(6, len(doc))):
                t = doc[i].get_text() or ""
                if len(t.strip()) < 40:                     # похоже на скан — читаем OCR
                    try:
                        pix = _pixmap_for_ocr(doc[i], dpi=220)
                        import io
                        from PIL import Image, ImageOps
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        t = _ocr_image_from_pil(img)
                    except Exception:
                        pass
                out.append(t)
            doc.close()
            return "\n".join(out).strip()
        except Exception as e:  # noqa: BLE001
            return f"(не удалось прочитать PDF: {e})"

    if ext in HEIC_EXT:
        try:
            return (_ocr_heic(p) or "").strip()
        except Exception as e:  # noqa: BLE001
            return f"(не удалось прочитать HEIC: {e})"

    if ext in IMAGE_EXT:
        try:
            return (_ocr_image(p) or "").strip()
        except Exception as e:  # noqa: BLE001
            return f"(не удалось распознать изображение: {e})"

    # Word (.docx) — читаем напрямую из XML
    if ext == ".docx":
        try:
            import docx
            d = docx.CLIENT(str(p))
            parts = [par.text for par in d.paragraphs]
            for t in d.tables:                      # данные часто лежат в таблицах
                for row in t.rows:
                    parts.append(" | ".join(cell.text.strip() for cell in row.cells))
            return "\n".join(x for x in parts if x and x.strip()).strip()
        except Exception as e:  # noqa: BLE001
            return f"(не удалось прочитать DOCX: {e})"

    if ext in (".txt", ".csv", ".rtf", ".json", ".xml", ".md"):
        try:
            return p.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""

    # Всё остальное (doc, xls, xlsx, ppt, odt…) — конвертируем в текст LibreOffice
    if ext in (".doc", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"):
        return _via_libreCLIENT(p)

    return ""


def _via_libreCLIENT(path) -> str:
    """Локальная конвертация офисного файла в текст (макрос LibreOffice не нужен).

    Работает без интернета и без LLM: файл -> txt в той же папке.
    """
    import subprocess
    import tempfile
    p = Path(path)
    try:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["sCLIENT", "--headless", "--convert-to", "txt:Text",
                            "--outdir", td, str(p)],
                           capture_output=True, timeout=180)
            got = sorted(Path(td).glob("*.txt"))
            if got:
                return got[0].read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as e:  # noqa: BLE001
        return f"(не удалось прочитать {p.name}: {e})"
    return ""


def _ocr_image_from_pil(img) -> str:
    import pytesseract
    from PIL import ImageOps
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.width < 1600:
        k = 1600 / max(1, img.width)
        img = img.resize((int(img.width * k), int(img.height * k)))
    return pytesseract.image_to_string(ImageOps.grayscale(img), lang=OCR_LANGS)


def doc_kind(path) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in HEIC_EXT:
        return "heic"
    return "image"


def passport_like(path) -> bool:
    """Похоже ли, что это паспорт (по имени файла и по тексту шапки)."""
    name = Path(path).name.lower()
    if "passport" in name or "паспорт" in name:
        return True
    t = (read_text(path)[:600] or "").lower()
    return ("паспорт" in t or "passport" in t or "российская федерация" in t)

# Кэш текста документов: разбор PDF/OCR стоит секунды, одни и те же файлы
# читаются многократно при сборке значений и предпросмотре.
_READ_TEXT_CACHE = {}


def read_text(path) -> str:
    """Текст документа с кэшем по подписи файла (путь, размер, mtime)."""
    try:
        p = Path(path)
        if not p.exists():
            return ""
        st = p.stat()
        key = (str(p), st.st_size, int(st.st_mtime))
        if key in _READ_TEXT_CACHE:
            return _READ_TEXT_CACHE[key]
        val = _read_text_uncached(path)
        if len(_READ_TEXT_CACHE) > 400:
            _READ_TEXT_CACHE.clear()
        _READ_TEXT_CACHE[key] = val
        return val
    except Exception:
        try:
            return _read_text_uncached(path)
        except Exception:
            return ""
