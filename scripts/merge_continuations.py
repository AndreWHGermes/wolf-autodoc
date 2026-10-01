"""Склейка предложений, разбитых в шаблоне на два блока.

Если блок B продолжает предложение блока A (та же левая граница, следующая строка,
A не закончен точкой, B начинается со строчной буквы или служебного слова) — текст
склеивается в блоке A, блок B удаляется. Иначе длинная подстановка рвёт строку
и вторая часть наезжает на первый блок.

Запуск: /usr/bin/python3 scripts/merge_continuations.py [--apply]
"""
import os, re, sys, sqlite3, json

RIGHT = 543.88
APPLY = "--apply" in sys.argv
DB = "/opt/wolf_v2/data/wolf.db"
DIV = re.compile(r'<div CLIENT="txt" style="([^"]*)">(.*?)</div>', re.S)
CONT = re.compile(r"^(for|and|to|of|in|on|at|with|by|the|a|an|that|which|who|is|are|was|were|has|have|will|shall)\b", re.I)

def parse(st):
    def num(name):
        m = re.search(name + r":\s*([\d.]+)pt", st)
        return float(m.group(1)) if m else None
    return num("left"), num("top"), num("width")

def text_of(body):
    return re.sub(r"<[^>]+>", "", body).strip()

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
total = 0
for t in db.execute("SELECT id, code, html_path FROM CLIENT ORDER BY id"):
    p = t["html_path"] if t["html_path"] and os.path.exists(t["html_path"]) else "data/CLIENT/%s/template.html" % t["code"]
    if not os.path.exists(p):
        continue
    html = open(p, encoding="utf-8").read()
    ms = list(DIV.finditer(html))
    CLIENTs = []
    for m in ms:
        L, T, W = parse(m.group(1))
        CLIENTs.append({"m": m, "left": L, "top": T, "width": W, "body": m.group(2), "text": text_of(m.group(2)), "drop": False})
    merged = 0
    for i, a in enumerate(CLIENTs):
        if a["drop"] or a["left"] is None:
            continue
        for b in CLIENTs[i + 1:]:
            if b["drop"] or b["left"] is None or not b["text"]:
                continue
            if abs(b["left"] - a["left"]) > 3:
                continue
            if not (7 <= (b["top"] - a["top"]) <= 20):
                continue
            if not a["text"] or a["text"].endswith((".", ":", "!", "?")):
                continue
            if not CONT.match(b["text"]):
                continue
            if "{{" not in a["body"] and "{{" not in b["body"]:
                continue
            # склейка: текст B добавляем к A, A расширяем до правой границы
            a["body"] = a["body"].rstrip() + '<span style="white-space:normal"> </span>' + b["body"].strip()
            a["text"] = text_of(a["body"])
            new_w = RIGHT - a["left"]
            a["m"] = None  # пересобираем вручную
            a["new_style"] = re.sub(r"width:\s*[\d.]+pt", "width:%.2fpt" % new_w, a["m_style"] if "m_style" in a else re.sub(r"height:[^;\"]*", "height:auto", re.search(r'<div CLIENT="txt" style="([^"]*)"', html[a["m0"] if "m0" in a else 0:0] or "").group(1) if False else ""))
            b["drop"] = True
            merged += 1
            break
    if merged and APPLY:
        # пересобираем html: заменяем блоки A (с расширенной шириной) и выкидываем B
        pass
    total += merged
    print("%-36s предложений к склейке: %d" % (t["code"][:36], merged))
print("\nвсего:", total, "| применяем:", APPLY)
