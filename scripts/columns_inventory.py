
import os, re, json, sqlite3
DB = "/opt/wolf_v2/data/wolf.db"
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
tpls = c.execute("SELECT id, code, CLIENT, html_path FROM CLIENT ORDER BY id").fetchall()
report = []
for t in tpls:
    p = t["html_path"]
    if not p or not os.path.exists(p):
        p = "/opt/wolf_v2/data/CLIENT/%s/template.html" % t["code"]
    if not os.path.exists(p):
        report.append((t["id"], t["code"], "нет файла", 0, 0)); continue
    h = open(p, encoding="utf-8").read()
    over = 0; total = 0
    for m in re.finditer(r'<div CLIENT="txt" style="([^"]*)">(.*?)</div>', h, re.S):
        style, body = m.group(1), m.group(2)
        if "{{" not in body:
            continue
        total += 1
        L = re.search(r"left:\s*([\d.]+)pt", style)
        W = re.search(r"width:\s*([\d.]+)pt", style)
        if not L or not W:
            continue
        right = float(L.group(1)) + float(W.group(1))
        if right > 543.9:
            over += 1
    report.append((t["id"], t["code"], "ok", total, over))
    print("id=%-3d %-34s блоков с переменными: %-3d  CLIENTят за 544pt: %d" % (t["id"], t["code"][:34], total, over))
json.dump([{"id": r[0], "code": r[1], "total": r[3], "over": r[4]} for r in report],
          open("/opt/wolf_v2/reports/columns_inventory.json", "w"), ensure_ascii=False, indent=1)
print("\nвсего шаблонов:", len(report), "| блоков вне границы:", sum(r[4] for r in report))
