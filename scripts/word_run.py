#!/usr/bin/env python3
"""Прогон документов заявки через Word-шаблон: DOCX + PDF.

    word_run.py --app 89                     все документы заявки
    word_run.py --app 89 --code X            один документ
    word_run.py --app 89 --list              только список (что есть / чего нет)

Значения берутся тем же кодом, что печатает PDF (scripts/pdf_fill.values_for),
поэтому Word, HTML-визор и PDF показывают одни данные. Пустые переменные
вычищаются, чтобы в документе не оставалось {{...}}.
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys

ROOT = "/opt/wolf_v2"
sys.path.insert(0, ROOT)
OUT = "/tmp/wordrun"

from docxtpl import DocxTemplate  # noqa: E402
import sqlite3  # noqa: E402


def db():
    c = sqlite3.connect(os.path.join(ROOT, "data", "wolf.db"))
    c.row_factory = sqlite3.Row
    return c


def values_for(app_id: int, code: str) -> dict:
    spec = importlib.util.spec_from_file_location("pdf_fill_mod", os.path.join(ROOT, "scripts", "pdf_fill.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.values_for(app_id, code) or {}


def docx_vars(code: str) -> list:
    path = os.path.join(ROOT, "data", "templates", code, "word", "template.docx")
    if not os.path.exists(path):
        return []
    import zipfile
    with zipfile.ZipFile(path) as z:            # переменные лежат в теле DOCX
        xml = z.read("word/document.xml").decode("utf-8")
    # jinja может разорвать {{ var }} на несколько run'ов — склеиваем теги
    xml = re.sub(r"<[^>]+>", "", xml)
    return sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", xml)))


def render(code: str, app_id: int) -> tuple:
    tpl = os.path.join(ROOT, "data", "templates", code, "word", "template.docx")
    if not os.path.exists(tpl):
        return None, None, "нет word/template.docx"
    vals = values_for(app_id, code)
    filled = {k: ("" if v is None else str(v)) for k, v in vals.items()}
    missing = [v for v in docx_vars(code) if not filled.get(v)]
    os.makedirs(OUT, exist_ok=True)
    out_docx = os.path.join(OUT, "%s_app%s.docx" % (code, app_id))
    t = DocxTemplate(tpl)
    t.render(filled)                      # jinja: незнакомые имена → пусто
    t.save(out_docx)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", OUT, out_docx],
                   capture_output=True, timeout=240)
    out_pdf = out_docx.replace(".docx", ".pdf")
    return out_docx, (out_pdf if os.path.exists(out_pdf) else None), missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", type=int, required=True)
    ap.add_argument("--code")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    c = db()
    if a.code:
        codes = [a.code]
    else:
        codes = [r["code"] for r in c.execute(
            """SELECT t.code FROM application_documents d JOIN templates t ON t.id = d.template_id
               WHERE d.application_id = ? ORDER BY t.code""", (a.app,))]
    if not codes:
        print("у заявки %s нет документов" % a.app)
        return
    for code in codes:
        if a.list:
            v = docx_vars(code)
            vals = values_for(a.app, code)
            empty = [x for x in v if not str(vals.get(x) or "").strip()]
            print("%-38s word=%s vars=%2d пусто=%s %s" % (
                code, "да" if v else "НЕТ", len(v), len(empty), ",".join(empty[:6])))
            continue
        docx_path, pdf_path, missing = render(code, a.app)
        print("%-38s %s %s%s" % (code,
                                 "docx ok" if docx_path else "docx НЕТ",
                                 "pdf ok" if pdf_path else "pdf НЕТ",
                                 ("  пусто: " + ",".join(missing[:6])) if missing else ""))


if __name__ == "__main__":
    main()
