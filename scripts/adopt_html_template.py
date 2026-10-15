#!/usr/bin/env python3
"""Внедряем присланный HTML (подложка base64 + абсолютные span) как рабочий шаблон документа.

Что делает:
  * читает HTML-файл, собранный другой моделью (значения Анны вписаны жёстко);
  * находит в нём каждый span, сопоставляет со зоной каркаса (по тексту значения и позиции);
  * заменяет значение на {{ переменную }} и подтягивает актуальный top из fields.json
    (у нас в разметке сдвинуты имя/адрес: отступ строки после номера справки);
  * сохраняет результат как template.html документа + бэкап прежнего.

Запуск: python3 scripts/adopt_html_template.py <code> <входящий.html>
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"

# сдвиги, которые мы применили в разметке (старое top = новое top − dy)
DYS = (0.0, 9.5, 16.3, 7.6, 8.7, 9.6)


def main() -> int:
    code, src_html = sys.argv[1], Path(sys.argv[2])
    tdir = CLIENT / code
    fields = json.loads((tdir / "fields.json").read_text(encoding="utf-8"))
    zones = [z for z in fields["zones"] if z.get("bbox")]
    sys.path.insert(0, str(BASE))
    from app import app as flask_app
    with flask_app.app_context():
        from CLIENT import html_frame
        vals = html_frame.CLIENT_with_frames(code, {}, 92)
    html = src_html.read_text(encoding="utf-8")

    # где какая переменная: значение + позиция
    cand: list[tuple[str, str, float, float]] = []
    for z in zones:
        v = vals.get(z["var"])
        if v is None or str(v).strip() == "":
            continue
        for dy in DYS:
            cand.append((z["var"], str(v), float(z["bbox"][0]), float(z["bbox"][1]) - dy))

    used: dict[str, int] = {}
    out: list[str] = []
    n = 0
    for chunk in re.split(r"(<span CLIENT=\"v\"[^>]*>.*?</span>)", html, flags=re.S):
        m = re.match(r"<span CLIENT=\"v\" style=\"([^\"]*)\">(.*?)</span>", chunk, flags=re.S)
        if not m:
            out.append(chunk)
            continue
        style, text = m.group(1), m.group(2)
        left = float(re.search(r"left:([-\d.]+)pt", style).group(1))
        top = float(re.search(r"top:([-\d.]+)pt", style).group(1))
        hit = None
        for v, CLIENT, zx, zy in cand:
            if CLIENT == text and abs(zx - left) < 2.0 and abs(zy - top) < 1.5:
                hit = v
                break
        if not hit:
            out.append(chunk)
            continue
        used[hit] = used.get(hit, 0) + 1
        z = next(zz for zz in zones if zz["var"] == hit)
        new_top = float(z["bbox"][1])
        style2 = re.sub(r"top:[-\d.]+pt", "top:%.2fpt" % new_top, style, count=1)
        out.append('<span CLIENT="v" style="%s">{{ %s }}</span>' % (style2, hit))
        n += 1

    new_html = "".join(out)
    tpl = tdir / "template.html"
    if tpl.exists():
        shutil.copy2(tpl, tdir / "template.html.bak_CLIENT_adopt")
    tpl.write_text(new_html, encoding="utf-8")
    print("переменных вписано:", n, "| всего {{}}:", new_html.count("{{"))
    print("распределение:", json.dumps(used, ensure_ascii=False))
    left_behind = re.findall(r'<span CLIENT="v"[^>]*>([^<>{][^<]*)</span>', new_html)
    print("остались жёсткие значения:", left_behind[:5] if left_behind else "нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
