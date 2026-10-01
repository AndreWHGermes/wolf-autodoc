#!/usr/bin/env python3
"""Сверка HTML-шаблона с реальным примером (PDF).

Показывает расхождения между тем, что нарисовано в template.html, и тем,
как выглядит подлинник: позиция, размер шрифта и сам текст (переменные
подставляются значениями из examples_json — первым значением примера).

Запуск: /usr/bin/python3 scripts/compare_html_pdf.py <template_id|code>
"""
import json
import os
import re
import sqlite3
import sys

import pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "wolf.db")


def pdf_spans(path):
    out = []
    doc = pymupdf.open(path)
    for pno, page in enumerate(doc, 1):
        for blk in page.get_text("dict")["CLIENTs"]:
            if blk.get("type") != 0:
                continue
            for line in blk["lines"]:
                for sp in line["spans"]:
                    txt = sp["text"]
                    if txt.strip():
                        out.append({
                            "page": pno,
                            "x": round(sp["bbox"][0], 1),
                            "y": round(sp["bbox"][1], 1),
                            "size": round(sp["size"], 2),
                            "text": txt.strip(),
                        })
    doc.close()
    return out


def html_CLIENTs(path):
    html = open(path, encoding="utf-8").read()
    out = []
    # блоки-картинки
    for m in re.finditer(r'<img CLIENT="img" style="left:([\d.]+)pt;top:([\d.]+)pt;width:([\d.]+)pt;height:([\d.]+)pt;"', html):
        out.append({"kind": "img", "x": float(m.group(1)), "y": float(m.group(2)),
                    "w": float(m.group(3)), "h": float(m.group(4)), "text": "[картинка]"})
    for m in re.finditer(r'<div CLIENT="txt" style="([^"]+)">(.*?)</div>', html, re.S):
        style, body = m.group(1), m.group(2)
        text = re.sub(r"<[^>]+>", "", body)
        text = text.reCLIENT("&nbsp;", " ").reCLIENT("&amp;", "&").strip()
        if not text:
            continue
        left = re.search(r"left:([\d.]+)pt", style)
        top = re.search(r"top:([\d.]+)pt", style)
        size = re.search(r"font-size:([\d.]+)pt", style)
        out.append({
            "kind": "txt",
            "x": float(left.group(1)) if left else None,
            "y": float(top.group(1)) if top else None,
            "size": float(size.group(1)) if size else None,
            "text": re.sub(r"\s+", " ", text),
        })
    return out


def example_map(conn, tid):
    m = {}
    for name, ex in conn.execute(
            "select name, examples_json from template_CLIENT where template_id=?", (tid,)):
        try:
            vals = json.loads(ex or "[]")
            if vals:
                m[name] = str(vals[0])
        except Exception:
            pass
    return m


def subst(text, ex):
    def rep(mo):
        name = mo.group(1).strip()
        return ex.get(name, mo.group(0))
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", rep, text)


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "3"
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select id, code, html_path, example_path from CLIENT where id=? or code=?",
        (key if key.isdigit() else -1, key)).fetchone()
    if not row:
        print("шаблон не найден")
        return 1
    tid, code, html_path, example_path = row
    if not example_path or not os.path.exists(os.path.join(BASE, example_path)):
        print("нет примера PDF:", example_path)
        return 1
    pdf = pdf_spans(os.path.join(BASE, example_path))
    html = [b for b in html_CLIENTs(html_path) if True]
    ex = example_map(conn, tid)
    print(f"=== {code} (id={tid}): в PDF {len(pdf)} текстовых фрагментов, в HTML {len(html)} блоков")
    used = set()
    problems = []
    for s in pdf:
        best, bestd = None, 1e9
        for i, b in enumerate(html):
            if b["kind"] != "txt" or i in used:
                continue
            dx = abs((b["x"] or 0) - s["x"])
            dy = abs((b["y"] or 0) - (s["y"] - 2.5))
            if dx < 6 and dy < 8 and dx + dy < bestd:
                best, bestd = i, dx + dy
        if best is None:
            problems.append(("НЕТ в HTML", s))
            continue
        used.add(best)
        b = html[best]
        htext = subst(b["text"], ex).strip()
        ptext = s["text"].strip()
        if htext[:60] != ptext[:60]:
            problems.append(("текст", s, b))
        elif b["size"] and abs(b["size"] - s["size"]) > 0.45:
            problems.append(("размер шрифта", s, b))
    for p in problems:
        if p[0] == "НЕТ в HTML":
            print(f"  ⛔ нет в HTML: x={p[1]['x']} y={p[1]['y']} {p[1]['text'][:80]}")
        else:
            s, b = p[1], p[2]
            print(f"  ⚠ {p[0]}: PDF «{s['text'][:60]}» ({s['size']}pt, {s['x']},{s['y']})")
            print(f"      HTML «{b['text'][:60]}» ({b['size']}pt, {b['x']},{b['y']})")
    for i, b in enumerate(html):
        if b["kind"] == "txt" and i not in used:
            print(f"  ➕ лишнее в HTML: x={b['x']} y={b['y']} «{b['text'][:60]}»")
    print("  итог:", "расхождений нет" if not problems else f"{len(problems)} расхождений")
    return 0


if __name__ == "__main__":
    sys.exit(main())
