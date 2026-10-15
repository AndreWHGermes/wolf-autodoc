"""Второй проход разметки: чистим мусорные атрибуты и не даём предложениям рваться по словам.

1) Убираем лишние ; в конце style и «висячие» атрибуты после закрывающей кавычки,
   которые появились в первом проходе.
2) Блок, который стоит на строке один (справа на том же уровне ничего нет), получает
   ширину до служебной правой границы — иначе длинное значение рвётся по одному слову.
"""
import os, re, sqlite3, json

RIGHT = 543.88
DB = "data/wolf.db"
DB_ABS = "/opt/wolf_v2/data/wolf.db"
DIV = re.compile(r'<div class="txt" style="([^"]*)">(.*?)</div>', re.S)

def clean_style(st):
    st = re.sub(r";\s*;+", ";", st)                 # двойные ;;
    st = st.rstrip(";")
    if "white-space" not in st:
        st += ";white-space:normal"
    return st

def clean_body(body):
    # убрать висячие атрибуты, вставленные первым проходом после закрывающей кавычки
    body = re.sub(r'"\s*;white-space:normal\s*;?\s*overflow-wrap:break-word(?=\s*>)', '"', body)
    body = re.sub(r'"\s*;white-space:normal(?=\s*>)', '"', body)
    body = re.sub(r'"\s*;overflow-wrap:break-word(?=\s*>)', '"', body)
    # и добавить эти свойства внутрь style у span
    def fix_span(m):
        attrs, inner = m.group(1), m.group(2)
        st = re.search(r'style="([^"]*)"', attrs)
        if not st:
            return m.group(0)
        cur = st.group(1)
        add = ""
        if "white-space" not in cur:
            add += ";white-space:normal"
        if "overflow-wrap" not in cur:
            add += ";overflow-wrap:break-word"
        if not add:
            return m.group(0)
        return '<span style="%s%s">%s' % (cur.rstrip(";"), add, inner)
    body = re.sub(r"<span([^>]*)>(.*?)(?=</span>|$)", fix_span, body, flags=re.S)
    return body

db = sqlite3.connect(DB_ABS); db.row_factory = sqlite3.Row
rep = []
for t in db.execute("SELECT id, code, html_path FROM templates ORDER BY id"):
    p = t["html_path"] if t["html_path"] and os.path.exists(t["html_path"]) else "data/templates/%s/template.html" % t["code"]
    if not os.path.exists(p):
        continue
    html = open(p, encoding="utf-8").read()
    blocks = []
    for m in DIV.finditer(html):
        st = m.group(1)
        L = re.search(r"left:\s*([\d.]+)pt", st); T = re.search(r"top:\s*([\d.]+)pt", st)
        W = re.search(r"width:\s*([\d.]+)pt", st)
        if not (L and T and W):
            blocks.append(None); continue
        blocks.append({"left": float(L.group(1)), "top": float(T.group(1)), "width": float(W.group(1))})
    cnt = [0, 0]   # [расширено, почищено]
    counter = [0]
    def rebuild(m):
        b = blocks[counter[0]]; counter[0] += 1
        if b is None:
            return m.group(0)
        body = clean_body(m.group(2))
        st = clean_style(m.group(1))
        left, width = b["left"], b["width"]
        has_right_neighbour = any(
            o and o is not b and abs(o["top"] - b["top"]) <= 6 and o["left"] > left + width - 1
            for o in blocks)
        new_w = width
        if "{{" in m.group(2):
            if left + width > RIGHT + 0.5 and left < RIGHT - 20:
                new_w = RIGHT - left
            elif not has_right_neighbour and left < 200 and width < 480:
                new_w = RIGHT - left
        if abs(new_w - width) > 0.5:
            st = re.sub(r"width:\s*[\d.]+pt", "width:%.2fpt" % new_w, st, count=1)
            cnt[0] += 1
        if body != m.group(2) or st != m.group(1):
            cnt[1] += 1
        return '<div class="txt" style="%s">%s</div>' % (st, body)
    html2 = DIV.sub(rebuild, html)
    if html2 != html:
        open(p, "w", encoding="utf-8").write(html2)
    rep.append({"id": t["id"], "code": t["code"], "widened": cnt[0], "cleaned": cnt[1]})
    print("id=%-3d %-34s расширено %3d  почищено %3d" % (t["id"], t["code"][:34], cnt[0], cnt[1]))
json.dump(rep, open("reports/columns_pass2.json", "w"), ensure_ascii=False, indent=1)
