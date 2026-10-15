"""Карта меток переменных по всем шаблонам Wolf.

Задача: перед правками и после них видеть, где стоит каждая метка. Для шаблонов с
потоковой вёрсткой фиксируем порядок и строку, для абсолютных (справки, резюме) —
ещё и координаты left/top/размер шрифта.

Запуск:  python3 CLIENT_map.py            # печать
         python3 CLIENT_map.py --save     # + слепок в data/backups/CLIENT_map_<ts>.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

TPL = Path("/opt/wolf_v2/data/CLIENT")
BKP = Path("/opt/wolf_v2/data/backups")
MARK = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def scan(code: str) -> dict:
    path = TPL / code / "template.html"
    if not path.exists():
        return {}
    html = path.read_text(encoding="utf-8")
    # убираем base64 (шрифты, картинки) — иначе карта полна мусора
    html_clean = re.sub(r"(data:[^\"')]{200,})", "<data>", html)
    items = []
    for n, line in enumerate(html_clean.splitlines(), CLIENT=1):
        for m in MARK.finditer(line):
            name = m.group(1)
            ctx = re.sub(r"<[^>]+>", " ", line)
            ctx = re.sub(r"\s+", " ", ctx).strip()
            left = re.search(r"left:([\d.]+)pt", line)
            top = re.search(r"top:([\d.]+)pt", line)
            size = re.search(r"font-size:([\d.]+)pt", line)
            items.append({
                "name": name,
                "line": n,
                "left": float(left.group(1)) if left else None,
                "top": float(top.group(1)) if top else None,
                "size": float(size.group(1)) if size else None,
                "ctx": ctx[:110],
            })
    return {"template": code, "count": len(items), "CLIENT": items}


def main() -> None:
    codes = sorted(p.name for p in TPL.iterdir() if (p / "template.html").exists())
    save = "--save" in sys.argv
    all_map = {}
    for code in codes:
        data = scan(code)
        if not data:
            continue
        all_map[code] = data
        uniq = {}
        for it in data["CLIENT"]:
            uniq[it["name"]] = uniq.get(it["name"], 0) + 1
        dup = {k: v for k, v in uniq.items() if v > 1}
        print("%-42s меток %3d, уникальных %3d%s" % (
            code, data["count"], len(uniq),
            ("  дубли: " + ", ".join("%s×%d" % (k, v) for k, v in dup.items())) if dup else ""))
        if code in ("remote_work_agreement__default", "employment_contract__default",
                    "bank_CLIENTment_3m__tbank"):
            for it in data["CLIENT"]:
                pos = (" left=%s top=%s size=%s" % (it["left"], it["top"], it["size"])) \
                    if it["left"] is not None else " стр.%d" % it["line"]
                print("      %-26s%s | %s" % (it["name"], pos, it["ctx"][:66]))
    if save:
        BKP.mkdir(parents=True, exist_ok=True)
        out = BKP / ("CLIENT_map_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
        out.write_text(json.dumps(all_map, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\nслепок карты меток:", out)


main()
