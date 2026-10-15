"""Универсальная сборка документа заявки: python render_doc.py <app_id> <template_code> [out.pdf]

Печатает путь к PDF, число страниц и координаты ключевых блоков (для проверки меток).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pymupdf

DB = "/opt/wolf_v2/data/wolf.db"


def main() -> None:
    app_id = int(sys.argv[1])
    code = sys.argv[2]
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/%s_%d.pdf" % (code.split("__")[0], app_id))

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    row = c.execute(
        """SELECT ad.template_id FROM application_documents ad JOIN templates t ON t.id = ad.template_id
           WHERE ad.application_id = ? AND t.code = ?""", (app_id, code)).fetchone()
    if not row:
        print("нет документа %s в заявке %d" % (code, app_id))
        return
    if out.exists():
        out.unlink()

    from services import render

    res = render.generate(app_id, row["template_id"], out)
    print("собран:", res.get("pdf_path") if isinstance(res, dict) else res)
    if not out.exists():
        print("файл не создан")
        return
    d = pymupdf.open(out)
    print("страниц:", d.page_count)
    for pno in range(d.page_count):
        for b in d[pno].get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                txt = "".join(s["text"] for s in line["spans"]).strip()
                if not txt:
                    continue
                s = line["spans"][0]
                if s["size"] >= 9.0:
                    print("  стр.%d x=%.1f y=%.1f size=%.2f | %s" % (
                        pno + 1, s["bbox"][0], s["bbox"][1], s["size"], txt[:84]))
    png = out.with_suffix(".png")
    d[0].get_pixmap(dpi=140).save(str(png))
    if d.page_count > 1:
        d[1].get_pixmap(dpi=140).save(str(out.with_name(out.stem + "_p2.png")))
    print("png:", png)


main()
