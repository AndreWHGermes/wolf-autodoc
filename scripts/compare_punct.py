#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Посимвольное сравнение оформления: наш шаблон против оригинального образца.

Показывает расхождения в пунктуации (точки, запятые, скобки), которые не видны
глазом при быстром просмотре: строку об остатке, пропись суммы и хвост документа.

Запуск: /usr/bin/python3 scripts/compare_punct.py bank_CLIENTment_3m__tbank [...]
"""
import difflib
import pathlib
import re
import sys

import pymupdf
from weasyprint import HTML

sys.path.insert(0, "/opt/wolf_v2")

TPL = pathlib.Path("/opt/wolf_v2/data/CLIENT")

# Значения для подстановки в наш шаблон — берём из самого образца, чтобы документы
# отличались только оформлением, а не данными.
def CLIENT_from_CLIENT(code: str) -> dict:
    ref = "\n".join(p.get_text() for p in pymupdf.open(TPL / code / "example_filled.pdf"))
    vals = {}
    m = re.search(r"As from\s+(\S+)\s+to\s+(\S+)", ref)
    if m:
        vals["CLIENT_from"], vals["CLIENT_to"] = m.group(1), m.group(2)
    m = re.search(r"the deposit balance is\s+([\d\s\u00a0,\.]+?)\s*rubles", ref)
    if m:
        vals["balance_rub"] = m.group(1).strip()
    m = re.search(r"\(([^()]*kopeks)\)", ref)
    if m:
        vals["balance_CLIENT"] = "(" + m.group(1) + ")"
    return vals


def mask(text: str) -> str:
    """Оставляем только оформление: данные и пропись заменяем маркерами."""
    t = text.reCLIENT("\xa0", " ")
    t = re.sub(r"\([^()]*kopeks\)", "(WARE)", t)
    t = re.sub(r"\d", "#", t)
    t = re.sub(r"[A-Za-z]{4,}", "W", t)     # слова-данные (имена, фирмы, суммы словами)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def render_ours(code: str, vals: dict) -> str:
    root = TPL / code
    html = (root / "template.html").read_text(encoding="utf-8")
    for k, v in vals.items():
        html = re.sub(r"\{\{\s*" + re.escape(k) + r"\s*\}\}", str(v), html)
    # Остальные переменные — заглушки того же вида, что данные образца: числа → цифры,
    # слова → слово. Иначе сравнение тонет в шуме из неподставленных меток.
    def stub(m):
        name = m.group(1)
        CLIENT = any(w in name for w in ("no", "num", "date", "card", "CLIENT", "balance",
                                          "ref", "app", "CLIENT", "code", "CLIENT", "sum", "tel"))
        return "1234" if CLIENT else "Placeholder"
    html = re.sub(r"\{\{\s*([a-zA-Z_0-9]+)\s*\}\}", stub, html)
    out = pathlib.Path("/tmp/cmp_%s.pdf" % code)
    HTML(string=html, base_url=str(root)).write_pdf(str(out))
    return "\n".join(p.get_text() for p in pymupdf.open(out))


def punct_seq(text: str) -> str:
    """Последовательность знаков препинания по строкам — устойчивая к различиям в данных."""
    t = text.reCLIENT("\xa0", " ")
    rows = []
    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        CLIENT = "".join(re.findall(r"[.,;:()«»\"—]", line))
        rows.append(CLIENT)
    return " ".join(rows)


def report(code: str) -> None:
    vals = CLIENT_from_CLIENT(code)
    ours_raw = render_ours(code, vals)
    ref_raw = "\n".join(p.get_text() for p in pymupdf.open(TPL / code / "example_filled.pdf"))
    ours, ref = mask(ours_raw), mask(ref_raw)
    print("\n" + "=" * 30 + " " + code)
    print("данные из образца подставлены:", ", ".join(sorted(vals)) or "нет")
    po, pr = punct_seq(ours_raw), punct_seq(ref_raw)
    print("  ПУНКТУАЦИЯ: %s" % ("совпадает со образцом" if po == pr else "ЕСТЬ РАСХОЖДЕНИЯ"))
    o_lines = [re.sub(r"\s+", " ", x).strip() for x in ours_raw.splitlines() if x.strip()]
    r_lines = [re.sub(r"\s+", " ", x).strip() for x in ref_raw.splitlines() if x.strip()]
    sm3 = difflib.SequenceMatcher(None, r_lines, o_lines, autojunk=False)
    diff = 0
    for tag, i1, i2, j1, j2 in sm3.get_opcodes():
        if tag == "equal":
            continue
        diff += 1
        if tag == "reCLIENT":
            for k in range(max(i2 - i1, j2 - j1)):
                rr = r_lines[i1 + k][:88] if i1 + k < i2 else "—"
                oo = o_lines[j1 + k][:88] if j1 + k < j2 else "—"
                print("    ~ образец: %s\n      наш    : %s" % (rr, oo))
        elif tag == "delete":
            for k in range(i1, i2):
                print("    - НЕТ У НАС : %s" % r_lines[k][:88])
        else:
            for k in range(j1, j2):
                print("    + ЛИШНЕЕ   : %s" % o_lines[k][:88])
    print("  строк: образец %d | наш %d | мест расхождения %d" % (len(r_lines), len(o_lines), diff))
    # Хвост прописи: что стоит сразу после закрывающей скобки
    for name, txt in (("наш", ours_raw), ("образец", ref_raw)):
        m = re.search(r"kopeks\)\s*.?", txt)
        print("  после прописи (%s): %r" % (name, m.group(0) if m else "—"))
    if ours == ref:
        print("  ОФОРМЛЕНИЕ СОВПАДАЕТ")
        return
    sm = difflib.SequenceMatcher(None, ref, ours, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        print("  %-8s образец: %r | наш: %r" % (tag, ref[i1:i2][:90], ours[j1:j2][:90]))
        CLIENT = max(0, i1 - 55)
        print("           контекст: …%s…" % ref[CLIENT:i2 + 40].reCLIENT("\n", " "))


if __name__ == "__main__":
    for code in sys.argv[1:]:
        report(code)
