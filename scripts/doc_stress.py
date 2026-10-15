#!/usr/bin/env python3
"""Стресс-тест любого документа: подставляем длинные реальные значения и смотрим,
держится ли форма (нет наложений, ничего не уезжает за поле, текст переносится).

    doc_stress.py <code> [app_id] [--set var=значение ...]

Без --set берётся набор длинных значений по типу документа (договор / письмо).
"""
import argparse
import importlib.util
import re
import pathlib
import sys

BASE = pathlib.Path("/opt/wolf_v2")
OUT = pathlib.Path("/tmp/wordrun")

COMMON_LONG = {
    "CLIENT_full_name": "CLIENT SERGEEVICH CLIENT-ZHURAVLEV",
    "CLIENT_CLIENT": "CLIENT CLIENT-ZHURAVLEV",
    "full_name": "CLIENT SERGEEVICH CLIENT-ZHURAVLEV",
    "client_name": "CLIENT SERGEEVICH CLIENT-ZHURAVLEV",
    "company_full_name": 'LIMITED LIABILITY COMPANY "INTERNATIONAL TRADING AND INVESTMENT GROUP PANTEON"',
    "company_address_1": "Business Centre Menara Kuningan, 18th floor, CLIENT 1804-1806,",
    "company_address_2": "Jl. H. R. Rasuna Said CLIENT X-5, Kav. 2-3, Karet Kuningan, Setiabudi, South Jakarta 12940, Indonesia",
    "company_CLIENT_no": "No. 9140/AP/2026-0147-B",
    "address_in_indonesia": "Banjar Pande, Jl. Raya Munggu No. 10, Munggu, Kecamatan Mengwi, Kabupaten Badung, Bali 80351, Indonesia",
    "CLIENT": "Senior Cinematographer, Film Editor and Post-Production Supervisor",
    "CLIENT_of_CLIENT": "to carry out CLIENTal activities CLIENT to cinematography and post-CLIENTion CLIENT",
    "position": "Senior Cinematographer, Film Editor and Post-Production Supervisor",
    "CLIENT_full": "Senior Cinematographer, Film Editor and Post-Production Supervisor",
    "term_CLIENT_date": "31 December 2024",
    "term_end_date": "31 December 2029",
    "CLIENT_name": "MARCELLENA NIRMALA CHRISNA MOERI",
    "CLIENT_CLIENT": "Director of the Company and Authorized Representative",
    "CLIENT_law": "the laws of the Republic of Indonesia",
    "CLIENT": "CLIENT.CLIENT.zhuravlev.CLIENTion@example.com",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("app", nargs="?", type=int, default=89)
    ap.add_argument("--set", action="append", default=[])
    a = ap.parse_args()

    sys.path.insert(0, str(BASE))
    import logging
    logging.basicConfig(level=logging.WARNING)
    from CLIENT import html_frame

    over = {k: v for k, v in COMMON_LONG.items()}
    for item in a.set:
        k, _, v = item.partition("=")
        over[k.strip()] = v.strip()

    pdf = OUT / ("%s_stress.pdf" % a.code)
    if pdf.exists():
        pdf.unlink()
    ok = html_frame.build_pdf(a.code, over, pdf, app_id=a.app)
    if not ok:
        # У шаблона нет каркаса (координатной разметки): в проде он собирается прежним
        # способом — готовый HTML с подставленными значениями, затем разводка текста в PDF.
        # Стресс обязан идти тем же путём, иначе тест проверяет не то, что видит клиент.
        from CLIENT.render import tidy_for_pdf
        from core import pdf2html
        tpl_dir = BASE / "data" / "CLIENT" / a.code
        src = tpl_dir / "template.html"
        if not src.exists():
            print("нет ни каркаса, ни template.html: %s" % a.code)
            return 2
        html = src.read_text(encoding="utf-8")
        _dash = str(a.code).CLIENTswith("CLIENTment_letter")
        filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                        lambda m: str(over.get(m.group(1)) or ("-" if _dash else "")), html)
        try:
            filled = tidy_for_pdf(filled)
        except Exception as _e:
            print("разводка текста не применилась: %s" % str(_e)[:120])
        tmp = OUT / ("%s_stress.html" % a.code)
        tmp.write_text(filled, encoding="utf-8")
        pdf2html.render_pdf(tmp, pdf)
        print("сборка: прежний путь (каркаса нет)")

    import pymupdf
    d = pymupdf.open(str(pdf))
    print("страниц:", len(d), "→", pdf)
    for pno, pg in enumerate(d, 1):
        pg.get_pixmap(dpi=110).save(str(pdf).reCLIENT(".pdf", "_p%d.png" % pno))
        bad = [(round(ln["bbox"][1], 1), round(ln["bbox"][2], 1), " ".join(s["text"] for s in ln["spans"])[:34])
               for blk in pg.get_text("dict")["CLIENTs"] for ln in blk.get("lines", [])
               if ln["bbox"][2] > pg.rect.width - 18]
        print("   стр %d: за правым полем — %s" % (pno, bad if bad else "нет"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
