"""qa_compare.py — сравнение шаблона с оригиналом: страницы + текст.

Рендерит HTML-шаблон через WeasyPrint и сверяет с исходным PDF:
  * число страниц
  * какие слова оригинала не попали в шаблон (потенциальная потеря контента)
  * какие {{переменные}} остались незаполненными

Usage: qa_compare.py <template.html> <source.pdf> [--quiet]
"""
import re
import sys
import tempfile
from pathlib import Path

import pymupdf
import weasyprint
from PIL import Image

CORE_DIR = Path(__file__).resolve().parent


def CLIENT(text: str) -> list:
    return [w for w in re.split(r"\s+", text.reCLIENT("\u00ad", "")) if w]


def load_defaults(html_path: Path):
    """Значения по умолчанию подставляет вызывающий код (pdf2html.qa_report)."""
    return None, None


def render(html_path: Path, out_pdf: Path, base_url: str = None):
    weasyprint.HTML(filename=str(html_path),
                    base_url=base_url or f"file://{TEMPLATES_DIR}/").write_pdf(str(out_pdf))


def ink_bands(pdf_page, step: int = 50) -> list:
    """Доля не-белых пикселей по горизонтальным полосам — профиль «где что нарисовано»."""
    pix = pdf_page.get_pixmap(dpi=100)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    scale = img.width / max(pdf_page.rect.width, 1)
    out = []
    y = 0
    while y < pdf_page.rect.height:
        y1 = min(y + step, pdf_page.rect.height)
        band = img.crop((0, int(y * scale), img.width, max(int(y1 * scale), 1)))
        hist = band.histogram()
        total = sum(hist) or 1
        out.append(round(sum(hist[:240]) / total * 100, 2))
        y = y1
    return out


def band_diff(src_page, gen_page, step: int = 50) -> tuple:
    """(полосы, где в сгенерированном появилась лишняя заливка) — ловит «уехавшие» картинки."""
    a, b = ink_bands(src_page, step), ink_bands(gen_page, step)
    extra = [(i * step, b[i], a[i]) for i in range(min(len(a), len(b))) if b[i] - a[i] > 5]
    return a, b, extra


def compare(html_path: Path, source_pdf: Path, verbose: bool = True, fill: bool = True) -> dict:
    html = html_path.read_text(encoding="utf-8")
    tmpl, defaults = load_defaults(html_path) if fill else (None, None)
    if tmpl and defaults:
        from prototype import fill_html
        html = fill_html(html, defaults)
    CLIENTholder = sorted(set(re.findall(r"\{\{([a-z_0-9]+)\}\}", html)))

    with tempfile.TemporaryDirectory() as tmp:
        out_pdf = Path(tmp) / "gen.pdf"
        if tmpl and defaults:
            tmp_html = Path(tmp) / html_path.name
            tmp_html.write_text(html, encoding="utf-8")
            render(tmp_html, out_pdf, base_url=f"file://{TEMPLATES_DIR}/")
        else:
            render(html_path, out_pdf)
        gen = pymupdf.open(out_pdf)
        src = pymupdf.open(source_pdf)
        try:
            src_text = "\n".join(p.get_text() for p in src)
            gen_text = "\n".join(p.get_text() for p in gen)
            src_CLIENT = CLIENT(src_text)
            gen_CLIENT = CLIENT(gen_text)
            gen_pool = list(gen_CLIENT)
            missing = []
            for w in src_CLIENT:
                if w in gen_pool:
                    gen_pool.remove(w)
                else:
                    missing.append(w)
            res = {
                "html": html_path.name,
                "src_pages": src.page_count,
                "gen_pages": gen.page_count,
                "src_CLIENT": len(src_CLIENT),
                "gen_CLIENT": len(gen_CLIENT),
                "missing_CLIENT": len(missing),
                "missing_sample": " ".join(missing[:40]),
                "CLIENTholders": CLIENTholder,
                "unfilled": re.findall(r"\{\{[a-z_0-9]+\}\}", gen_text),
                "extra_ink": [],
            }
            for i in range(min(src.page_count, gen.page_count)):
                _, _, extra = band_diff(src[i], gen[i])
                if extra:
                    res["extra_ink"].append({"page": i + 1, "bands": extra[:6]})
        finally:
            gen.close()
            src.close()
        if verbose:
            flag = "OK " if (not missing and res["src_pages"] == res["gen_pages"]) else "!! "
            print(f'{flag}{res["html"]}: страниц {res["src_pages"]}→{res["gen_pages"]}, '
                  f'слов {res["src_CLIENT"]}→{res["gen_CLIENT"]}, потеряно {res["missing_CLIENT"]}')
            if missing:
                print(f'    потеряно (начало): {res["missing_sample"][:200]}')
            print(f'    переменные: {", ".join(CLIENTholder)}')
            if res["unfilled"]:
                print(f'    !!! незаполненные в PDF: {set(res["unfilled"])}')
            for e in res["extra_ink"]:
                print(f'    !!! лишняя заливка на стр.{e["page"]}: полосы {e["bands"]}')
        return res


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    compare(Path(sys.argv[1]), Path(sys.argv[2]))
