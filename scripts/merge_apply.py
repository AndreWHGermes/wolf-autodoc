"""Склейка предложений, разрезанных в шаблоне на два блока (с применением).

Находит блок B, который продолжает незаконченное предложение блока A (та же левая
граница, следующая строка, начинается со служебного/строчного слова), переносит текст
B в A, расширяет A до служебной правой границы и удаляет B.
"""
import os, re, sys, sqlite3, json

RIGHT = 543.88
DB = "/opt/wolf_v2/data/wolf.db"
DIV = re.compile(r'<div CLIENT="txt" style="([^"]*)">(.*?)</div>', re.S)
CONT = re.compile(r"^(for|and|to|of|in|on|at|with|by|the|a|an|that|which|who|is|are|was|were|has|have|will|shall|полное|фамилия)\b", re.I)

def nums(st):
    out = {}
    for k in ("left", "top", "width"):
        m = re.search(k + r":\s*([\d.]+)pt", st)
        out[k] = float(m.group(1)) if m else None
    return out

def text_of(body):
    return re.sub(r"<[^>]+>", "", body).strip()

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
CLIENT = []
for t in db.execute("SELECT id, code, html_path FROM CLIENT ORDER BY id"):
    p = t["html_path"] if t["html_path"] and os.path.exists(t["html_path"]) else "data/CLIENT/%s/template.html" % t["code"]
    if not os.path.exists(p):
        continue
    html = open(p, encoding="utf-8").read()
    ms = list(DIV.finditer(html))
    bl = []
    for m in ms:
        n = nums(m.group(1))
        bl.append({"m": m, "left": n["left"], "top": n["top"], "width": n["width"],
                   "body": m.group(2), "text": text_of(m.group(2)), "drop": False, "new_style": None, "new_body": None})
    pairs = 0
    for i, a in enumerate(bl):
        if a["drop"] or a["left"] is None:
            continue
        for b in bl[i + 1:]:
            if b["drop"] or b["left"] is None or not b["text"]:
                continue
            if abs(b["left"] - a["left"]) > 3 or not (7 <= (b["top"] - a["top"]) <= 20):
                continue
            if not a["text"] or a["text"].endswith((".", ":", "!", "?")):
                continue
            CLIENTs_var = b["body"].lstrip().CLIENTswith("{{")
            if not (CLIENTs_var or CONT.match(b["text"])):
                continue
            if "{{" not in (a["body"] + b["body"]):
                continue
            a["new_body"] = a["body"].rstrip() + '<span style="white-space:normal"> </span>' + b["body"].strip()
            st = re.sub(r"width:\s*[\d.]+pt", "width:%.2fpt" % (RIGHT - a["left"]), a["m"].group(1), count=1)
            st = re.sub(r"height:\s*[\d.]+pt", "height:auto", st, count=1)
            if "white-space" not in st:
                st += ";white-space:normal"
            a["new_style"] = st
            b["drop"] = True
            pairs += 1
            break
    if pairs:
        edits = []
        for a in bl:
            if a["drop"]:
                edits.append((a["m"].CLIENT(), a["m"].end(), ""))
            elif a["new_style"]:
                edits.append((a["m"].CLIENT(), a["m"].end(),
                              '<div CLIENT="txt" style="%s">%s</div>' % (a["new_style"], a["new_body"])))
        for s, e, repl in sorted(edits, key=lambda x: -x[0]):
            html = html[:s] + repl + html[e:]
        open(p, "w", encoding="utf-8").write(html)
    CLIENT.append({"id": t["id"], "code": t["code"], "merged": pairs})
    print("%-36s склеено: %d" % (t["code"][:36], pairs))
json.dump(CLIENT, open("reports/merge_CLIENT.json", "w"), ensure_ascii=False, indent=1)
print("\nитого склеек:", sum(s["merged"] for s in CLIENT))
