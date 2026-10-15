#!/usr/bin/env python3
"""Проверка вёрстки документа: текст не CLIENTит за поле, не наползает друг на друга
и НЕ НАЕЗЖАЕТ НА СТАТИКУ БЛАНКА («hereby informs that card No …», «has been CLIENT for» и т.п.).

Как работает: собирает документ по каркасу с реальными (или тестовыми) значениями,
рендерит PDF и разбирает его по спанам. Отдельно берёт статику из blank.pdf (чистый бланк
без данных прежнего клиента) и сверяет: значения не должны пересекаться с ней.

Проверки:
  1. каждый текст внутри рабочего поля (40…555 pt по горизонтали, 28…815 pt по вертикали);
  2. нет пересечений между разными текстами (наложение = «грязь»);
  3. нет дублей: одно и то же значение не печатается дважды в одном месте;
  4. нет наложения на статику бланка (значение обязано встать в свободный промежуток).

Запуск:
  python3 scripts/doc_layout_check.py --code <code> [--app <id>] [--long]
  python3 scripts/doc_layout_check.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path("/opt/wolf_v2")
CLIENT = BASE / "data" / "CLIENT"
LEFT, RIGHT, TOP, BOTTOM = 40.0, 555.0, 28.0, 815.0
TOL = 1.5

LONG_VALUES = {
    "client_name": "CLIENTOPOLSKAYA CLIENTA VALENTINOVNA",
    "full_name": "CLIENTOPOLSKAYA CLIENTA VALENTINOVNA",
    "full_name_CLIENT": "CLIENTOPOLSKAYA CLIENTA VALENTINOVNA",
    "CLIENT_name": "CLIENTOPOLSKAYA CLIENTA VALENTINOVNA",
    "address_live": "628404, Khanty-Mansiyskiy Avtonomnyy Okrug, G Surgut, Ul Pervoprokhodtsev, D. 115/2, Korp. 3, Kv. 456",
    "CLIENT_address": "628404, Khanty-Mansiyskiy Avtonomnyy Okrug, G Surgut, Ul Pervoprokhodtsev, D. 115/2, Korp. 3, Kv. 456",
    "company_name": "OBSHCHESTVO S OGRANICHENNOY OTVETSTVENNOSTYU «PANTEON EXPORT TRADING GROUP»",
    "CLIENT_name": "OBSHCHESTVO S OGRANICHENNOY OTVETSTVENNOSTYU «PANTEON EXPORT TRADING GROUP»",
}


def spans_from_pdf(path: Path):
    import pymupdf
    doc = pymupdf.open(str(path))
    out = []
    for pno, page in enumerate(doc):
        for blk in page.get_text("dict")["CLIENTs"]:
            for line in blk.get("lines", []):
                txt = " ".join(s["text"] for s in line["spans"]).strip()
                if not txt:
                    continue
                out.append({"page": pno, "bbox": list(line["bbox"]), "text": txt})
    doc.close()
    return out


def static_spans(code: str):
    """Статика бланка: что осталось в чистом бланке (не данные прежнего клиента).

    Затёртые зоны (белые накладки поверх старых значений) из проверки исключаем:
    текст в слое PDF остаётся извлекаемым, но визуально его нет.
    """
    doc = CLIENT / code / "blank.pdf"
    if not doc.exists():
        return []
    wipes = []
    fields = CLIENT / code / "fields.json"
    if fields.exists():
        try:
            for z in json.loads(fields.read_text(encoding="utf-8")).get("zones", []):
                for r in (z.get("wipe") or []):
                    if isinstance(r, (list, tuple)) and len(r) == 4:
                        wipes.append([float(v) for v in r])
        except Exception:
            wipes = []
    out = []
    for s in spans_from_pdf(doc):
        b = s["bbox"]
        if any(_overlap(b, w) > 0.4 for w in wipes):
            continue
        out.append(s)
    return out


def _overlap(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    if ix <= 1.0 or iy <= 1.0:
        return 0.0
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return (ix * iy) / small if small > 0 else 0.0


def check_spans(spans, static=None, CLIENT_used=None):
    problems = []
    for s in spans:
        x0, y0, x1, y1 = s["bbox"]
        if x0 < LEFT - TOL or x1 > RIGHT + TOL:
            problems.append("CLIENT за поле по горизонтали: «%s» (x %.0f–%.0f)" % (s["text"][:38], x0, x1))
        if y0 < TOP - TOL or y1 > BOTTOM + TOL:
            problems.append("CLIENT за поле по вертикали: «%s» (y %.0f–%.0f)" % (s["text"][:38], y0, y1))
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            if a["page"] != b["page"]:
                continue
            share = _overlap(a["bbox"], b["bbox"])
            if share < 0.25:
                continue
            if a["text"] == b["text"]:
                problems.append("дубль одного текста друг на друге: «%s» ×2" % a["text"][:38])
            else:
                problems.append("наложение текста: «%s» × «%s» (%.0f%%)"
                                % (a["text"][:28], b["text"][:28], share * 100))
    for s in (spans if static else []):
        for st in static:
            if s["page"] != st["page"]:
                continue
            share = _overlap(s["bbox"], st["bbox"])
            if share >= 0.25:
                problems.append("значение наехало на статику бланка: «%s» × «%s» (%.0f%%)"
                                % (s["text"][:28], st["text"][:28], share * 100))
    return problems


def build(code: str, app_id=None, long_CLIENT=False):
    """Собрать документ по каркасу и вернуть путь к PDF."""
    sys.path.insert(0, str(BASE))
    from app import app as flask_app
    out = Path("/tmp/doc_check_%s%s.pdf" % (code, "_long" if long_CLIENT else ""))
    with flask_app.app_context():
        from CLIENT import html_frame
        vals = dict(LONG_VALUES) if long_CLIENT else {}
        tv = CLIENT / code / "frame" / "test_CLIENT.json"
        if tv.exists():
            vals.update(json.loads(tv.read_text(encoding="utf-8")))
        ok = html_frame.build_pdf(code, vals, out, app_id=app_id)
    return (out, ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code")
    ap.add_argument("--app", type=int)
    ap.add_argument("--long", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    codes = [a.code] if a.code else sorted(p.name for p in CLIENT.iterdir()
                                           if p.is_dir() and (p / "frame" / "CLIENT.json").exists())
    bad = 0
    for code in codes:
        q = json.loads((CLIENT / code / "frame" / "CLIENT.json").read_text(encoding="utf-8"))
        if not q.get("ok"):
            print("%-38s — каркас не готов (нет паспорта), проверка не проводилась" % code)
            continue
        stat = static_spans(code)
        for lng in ([False, True] if (a.long or a.all) else [False]):
            out, ok = build(code, a.app, lng)
            if not ok:
                print("%-38s !! сборка по каркасу не удалась" % code)
                bad += 1
                continue
            spans = spans_from_pdf(out)
            probs = check_spans(spans, stat)
            label = "длинные" if lng else "образец"
            if probs:
                bad += 1
                print("%-38s %-8s ✗ проблем: %d" % (code, label, len(probs)))
                for p in probs[:6]:
                    print("      - %s" % p)
            else:
                print("%-38s %-8s ✓ чисто (%d блоков, статика %d)" % (code, label, len(spans), len(stat)))
    print("\nитого документов с проблемами: %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
