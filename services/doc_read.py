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
    img = ImageOps.grayscale(img)
    return pytesseract.image_to_string(img, lang=OCR_LANGS)


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


def read_text(path) -> str:
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
                        pix = doc[i].get_pixmap(dpi=220)
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
