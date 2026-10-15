
import os, re, json, sqlite3
RIGHT_LIMIT = 543.88      # служебная правая граница текстовой колонки (лист 595.92 - поле 52.04)
LEFT_LIMIT = 52.04        # служебная левая граница
DB = "/opt/wolf_v2/data/wolf.db"
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
res = []
for t in c.execute("SELECT id, code, html_path FROM templates ORDER BY id"):
    p = t["html_path"] if t["html_path"] and os.path.exists(t["html_path"]) else "/opt/wolf_v2/data/templates/%s/template.html" % t["code"]
    if not os.path.exists(p):
        res.append({"id": t["id"], "code": t["code"], "changed": 0, "note": "нет файла"}); continue
    h = open(p, encoding="utf-8").read()
    changed = 0
    def fix(m):
        global changed
        whole, style, body = m.group(0), m.group(1), m.group(2)
        if "{{" not in body:
            return whole
        L = re.search(r"left:\s*([\d.]+)pt", style)
        W = re.search(r"width:\s*([\d.]+)pt", style)
        if not L or not W:
            return whole
        left, width = float(L.group(1)), float(W.group(1))
        new_style, touched = style, False
        # правый край не должен уходить за служебную границу
        if left + width > RIGHT_LIMIT and left < RIGHT_LIMIT - 20:
            new_style = re.sub(r"width:\s*[\d.]+pt", "width:%.2fpt" % (RIGHT_LIMIT - left), new_style, count=1)
            touched = True
        # высота — по содержимому (иначе перенос обрежется)
        if re.search(r"height:\s*[\d.]+pt", new_style):
            new_style = re.sub(r"height:\s*[\d.]+pt", "height:auto", new_style, count=1)
            touched = True
        # переносим текст по словам вместо запрета переносов
        if "white-space" not in new_style:
            new_style += ";white-space:normal"
            touched = True
        new_body = body
        if "white-space" not in body:
            new_body = re.sub(r"(<span[^>]*?)(>)", r"\1;white-space:normal\2", new_body, count=1)
        if "overflow-wrap" not in new_body:
            new_body = re.sub(r"(<span[^>]*?)(>)", r"\1;overflow-wrap:break-word\2", new_body, count=1)
        if new_body != body:
            touched = True
        if touched:
            changed += 1
        return "<div class=\"txt\" style=\"%s\">%s</div>" % (new_style, new_body)
    h2 = re.sub(r'<div class="txt" style="([^"]*)">(.*?)</div>', fix, h, flags=re.S)
    if h2 != h:
        open(p, "w", encoding="utf-8").write(h2)
    res.append({"id": t["id"], "code": t["code"], "changed": changed})
    print("id=%-3d %-36s поправлено блоков: %d" % (t["id"], t["code"][:36], changed))
json.dump(res, open("/opt/wolf_v2/reports/columns_applied.json", "w"), ensure_ascii=False, indent=1)
print("\nитого поправлено блоков:", sum(r.get("changed", 0) for r in res))
