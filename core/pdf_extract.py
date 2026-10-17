"""extract_template_pages.py — PDF → точный HTML-шаблон, ВСЕ страницы.

Отличие от pdf_to_html_template.py: обрабатывает каждую страницу PDF
(1 страница = 1 .sheet = 1 страница A4 в итоговом PDF), а переменные
маппит только в те имена, которые объявлены в конструкторе
(остальные тексты остаются как в оригинале — без висячих {{...}}).

Usage: extract_template_pages.py <pdf> <html> <template_id>
"""
import base64
import io
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image

# какому имени переменной конструктора соответствует распознанный текст
VAR_ALIASES = {
    "doc_number": "doc_number",
    "issue_date": "issue_date",
    "period_from": "period_from_label",
    "period_label_months": "period_label_months",
    "period_label_years": "period_label_months",
    "balance_usd": "balance_usd",
    "income_usd": "balance_usd",
    "client_name": "client_name",
    "client_name_in_text": "client_name_in_text",
    "position_en": "position_en",
    "contractor_name": "client_name",
    "start_date": "start_date",
    "balance_rub_placeholder": "balance_rub_placeholder",
    "ellipsis_placeholder": "balance_rub_placeholder",
}

WITH_IMAGES = True

VAR_PATTERNS = [
    (r"^No\s*([a-z]{1,4}\d{6,12})\s*$", "doc_number"),
    (r"^today.{0,3}s?\s+date\.?$", "issue_date"),
    (r"^before\s+date\.?$", "period_from"),
    (r"^(\d+)\s+months?\s+before\s+date$", "period_label_months"),
    (r"^(\d+)\s+year\s+before\s+date$", "period_label_years"),
    (r"^USD\s*\$?\s*([\d,]+)$", "balance_usd"),
    (r"^income\s+worth\s+at\s+least\s+US\$([\d,]+)\s+per\s+year$", "income_usd"),
    (r"^name\.?$", "client_name"),
    (r"^for\s+name\.?$", "client_name_in_text"),
    (r"^\(profession\)$", "position_en"),
    (r"^random\s+date\s+\d{4}$", "start_date"),
    (r"^random\s+date$", "start_date"),
    (r"^\.\.\.$", "ellipsis_placeholder"),
    (r"^…$", "balance_rub_placeholder"),
]


def find_var(text: str, allowed: set):
    t = text.strip()
    for pat, raw_name in VAR_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            name = VAR_ALIASES.get(raw_name, raw_name)
            return name if name in allowed else None
    return None


def color_to_hex(color: int) -> str:
    return "#{:02x}{:02x}{:02x}".format((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


_XREF_CACHE = {}


def _reencode(data: bytes) -> tuple:
    """PNG/тяжёлые картинки → компактный JPEG (на белом фоне), если это выигрыш."""
    from PIL import Image as PILImage
    try:
        pil = PILImage.open(io.BytesIO(data))
    except Exception:                                  # noqa: BLE001
        return data, "png"
    if pil.mode in ("RGBA", "LA", "P"):
        pil = pil.convert("RGBA")
        bg = PILImage.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[-1])
        pil = bg
    elif pil.mode != "RGB":
        pil = pil.convert("RGB")
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=85, optimize=True, progressive=True)
    jpeg = buf.getvalue()
    if len(jpeg) < len(data):
        return jpeg, "jpeg"
    return data, "png"


def _data_uri(doc, xref: int) -> str:
    """data:-URI картинки по xref (с кэшем, тяжёлые — сжатые)."""
    if xref in _XREF_CACHE:
        return _XREF_CACHE[xref]
    raw = doc.extract_image(xref)
    data, ext = raw["image"], (raw.get("ext") or "png").lower()
    if ext not in ("png", "jpeg", "jpg"):
        data, ext = _reencode(data)
    elif len(data) > 150_000:
        data, ext = _reencode(data)
    mime = "jpeg" if ext in ("jpeg", "jpg") else "png"
    uri = f"data:image/{mime};base64," + base64.b64encode(data).decode("ascii")
    _XREF_CACHE[xref] = uri
    return uri


def _page_render(page):
    """Растр страницы — нужен, чтобы отличить видимые картинки от «спрятанных»."""
    try:
        pix = page.get_pixmap(dpi=72)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img, pix.width / max(page.rect.width, 1)
    except Exception:                                  # noqa: BLE001
        return None, 1.0


def _is_visible(render, scale, bbox, page_rect) -> bool:
    """Картинка реально видна на странице (её не перекрыло белым)?

    В исходных PDF бывают image-XObject, которые рисуются, но полностью
    закрыты фоном — в шаблоне им делать нечего.
    """
    if render is None:
        return True
    x0, y0, x1, y1 = bbox
    x0, y0 = max(x0, page_rect.x0), max(y0, page_rect.y0)
    x1, y1 = min(x1, page_rect.x1), min(y1, page_rect.y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return False
    crop = render.crop((int(x0 * scale), int(y0 * scale), int(x1 * scale), int(y1 * scale)))
    if crop.width < 2 or crop.height < 2:
        return False
    grey = crop.convert("L")
    hist = grey.histogram()
    total = sum(hist) or 1
    ink = sum(hist[:235]) / total              # доля не-белых пикселей
    return ink > 0.02


def _images_of_page(page, doc) -> list:
    """Картинки страницы как (bbox, data-URI) — каждая по своему месту на листе."""
    images = []
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:                                  # noqa: BLE001
        return images
    render, scale = _page_render(page)
    for info in infos:
        xref = info.get("xref")
        if not xref:
            continue
        if not _is_visible(render, scale, info["bbox"], page.rect):
            continue
        try:
            uri = _data_uri(doc, xref)
        except Exception as exc:                       # noqa: BLE001
            print(f"img err xref={xref}: {exc}", file=sys.stderr)
            continue
        images.append({"bbox": info["bbox"], "uri": uri})
    return images


def page_sheet_html(page, allowed: set, doc) -> str:
    """Один <div class="sheet"> для одной страницы PDF."""
    tdict = page.get_text("dict")

    lines_data = []
    for block in tdict["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            lines_data.append({"bbox": (x0, y0, x1, y1), "spans": spans})

    out = ['<div class="sheet">']
    for img in (_images_of_page(page, doc) if WITH_IMAGES else []):
        x0, y0, x1, y1 = img["bbox"]
        out.append(
            f'<img class="img" style="left:{x0:.2f}pt;top:{y0:.2f}pt;'
            f'width:{x1 - x0:.2f}pt;height:{y1 - y0:.2f}pt;" '
            f'src="{img["uri"]}" alt=""/>'
        )

    for line in lines_data:
        x0, y0, x1, y1 = line["bbox"]
        spans_html = []
        for span in line["spans"]:
            text = span["text"]
            font = span["font"]
            size = span["size"]
            flags = span["flags"]
            style = (f"font-family:{font};font-size:{size:.2f}pt;"
                     f"color:{color_to_hex(span['color'])};"
                     + ("font-weight:bold;" if flags & 16 else "")
                     + ("font-style:italic;" if flags & 2 else ""))
            var = find_var(text, allowed)
            if var == "doc_number":
                m = re.search(r"^No\s*([a-z]{1,4}\d{6,12})\s*$", text.strip(), re.IGNORECASE)
                if m:
                    number = m.group(1)
                    tail = text[text.index(number) + len(number):]
                    spans_html.append(f'<span style="{style}">No </span>')
                    spans_html.append(f'<span style="{style}">{{{{doc_number}}}}</span>')
                    if tail:
                        spans_html.append(f'<span style="{style}">{tail}</span>')
                    continue
            if var:
                spans_html.append(f'<span style="{style}">{{{{{var}}}}}</span>')
            else:
                esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                spans_html.append(f'<span style="{style}">{esc}</span>')
        out.append(
            f'<div class="txt" style="left:{x0:.2f}pt;top:{y0:.2f}pt;'
            f'width:{x1 - x0:.2f}pt;height:{y1 - y0:.2f}pt;">{"".join(spans_html)}</div>'
        )
    out.append("</div>")
    return "\n".join(out)


def extract_html(pdf_path: str, allowed: set) -> str:
    doc = pymupdf.open(pdf_path)
    try:
        page = doc[0]
        w, h = page.rect.width, page.rect.height
        head = [
            '<!doctype html><html><head><meta charset="utf-8"><style>',
            f'@page {{ size: {w:.2f}pt {h:.2f}pt; margin: 0; }}',
            '* { box-sizing: border-box; }',
            'html, body { margin: 0; padding: 0; background: #fff; }',
            'body { font-family: "Arial", "Liberation Sans", sans-serif; color: #000; }',
            f'.sheet {{ position: relative; width: {w:.2f}pt; height: {h:.2f}pt; '
            'background: #fff; overflow: hidden; page-break-after: always; break-after: page; }}',
            '.sheet:last-of-type { page-break-after: auto; break-after: auto; }',
            '.txt { position: absolute; margin: 0; padding: 0; line-height: 1; white-space: pre; }',
            '.img { position: absolute; display: block; }',
            '.txt span { background: transparent; padding: 0; }',
            '@media print { html, body { background: #fff; } }',
            '</style></head><body>',
        ]
        sheets = [page_sheet_html(p, allowed, doc) for p in doc]
        return "\n".join(head + sheets + ["</body></html>"])
    finally:
        doc.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: pdf_extract.py <pdf_in> <html_out> [--no-images]")
        sys.exit(1)
    WITH_IMAGES = "--no-images" not in sys.argv
    pdf_in, html_out = sys.argv[1], sys.argv[2]
    html = extract_html(pdf_in, set())
    Path(html_out).write_text(html, encoding="utf-8")
    print(f"{html_out}: {len(html)} байт, "
          f"{pymupdf.open(pdf_in).page_count} стр.")
