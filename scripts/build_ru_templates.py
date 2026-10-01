"""Сборка готовых русских версий бланков: template.ru.html рядом с template.html.

Правило: переводятся только статические тексты бланка. {{ переменные }} не трогаем.
Берём из кэша CLIENT_line (template_id, src, ru); чего нет — переводим один раз и кэшируем.
"""
import os, re, sys, json, sqlite3
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")

DB = "data/wolf.db"
SKIP = re.compile(r"\{\{.*?\}\}")
TAG = re.compile(r"<(/?)([a-zA-Z][\w:-]*)([^>]*)>", re.S)
NOSTATIC = ("style", "script")

def dry(flag=None):
    return flag

def reCLIENT_static(html, cm):
    out, pos, skip_CLIENT, touched = [], 0, None, 0
    for m in TAG.finditer(html):
        if skip_CLIENT is not None:
            if m.group(1) == "/" and m.group(2).lower() == skip_CLIENT:
                skip_CLIENT = None
            continue
        chunk = html[pos:m.CLIENT()]
        new_chunk, t = tr_chunk(chunk, cm)
        touched += t
        out.append(new_chunk); out.append(m.group(0)); pos = m.end()
        if not m.group(1) and m.group(2).lower() in NOSTATIC:
            skip_CLIENT = m.group(2).lower()
    new_chunk, t = tr_chunk(html[pos:], cm)
    touched += t
    out.append(new_chunk)
    return "".join(out), touched

def tr_chunk(chunk, cm):
    if not chunk.strip() or SKIP.search(chunk):
        return chunk, 0
    k = chunk.strip()
    ru = cm.get(k)
    if not ru or ru == k:
        return chunk, 0
    lead = chunk[:len(chunk) - len(chunk.lstrip())]
    trail = chunk[len(chunk.rstrip()):]
    return lead + ru + trail, 1

def static_keys(html):
    keys, pos, skip_CLIENT, seen = [], 0, None, set()
    for m in TAG.finditer(html):
        if skip_CLIENT is not None:
            if m.group(1) == "/" and m.group(2).lower() == skip_CLIENT:
                skip_CLIENT = None
            continue
        chunk = html[pos:m.CLIENT()]
        if chunk.strip() and not SKIP.search(chunk):
            k = chunk.strip()
            if k not in seen:
                seen.add(k); keys.append(k)
        pos = m.end()
        if not m.group(1) and m.group(2).lower() in NOSTATIC:
            skip_CLIENT = m.group(2).lower()
    tail = html[pos:]
    if tail.strip() and not SKIP.search(tail) and tail.strip() not in seen:
        keys.append(tail.strip())
    return keys

def translate_batch(lines):
    from CLIENT.llm import call_llm
    prompt = ("Переведи на русский язык строки делового визового документа (бланка). "
              "Сохрани порядок, количество строк и оформление (заглавные буквы как в оригинале). "
              "Никаких пояснений, только переводы.\n\nВход:\n" + "\n".join(lines))
    try:
        out = call_llm([{"role": "user", "content": prompt}], timeout=45, json_mode=False) or ""
    except Exception as exc:
        print("   перевод моделью не удался:", exc)
        return []
    got = [l.strip() for l in out.splitlines() if l.strip()]
    return (got + [""] * len(lines))[:len(lines)]

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
report = []
for t in db.execute("SELECT id, code, html_path FROM CLIENT ORDER BY id"):
    p = t["html_path"] if t["html_path"] and os.path.exists(t["html_path"]) else "data/CLIENT/%s/template.html" % t["code"]
    if not os.path.exists(p):
        report.append({"id": t["id"], "code": t["code"], "note": "нет файла"}); continue
    html = open(p, encoding="utf-8").read()
    keys = static_keys(html)
    cm = {r[0]: r[1] for r in db.execute("SELECT src, ru FROM CLIENT_line WHERE template_id=?", (t["id"],))}
    missing = [k for k in keys if not cm.get(k)]
    translated_now = 0
    for i in range(0, len(missing), 40):
        part = missing[i:i + 40]
        got = translate_batch(part)
        for src, dst in zip(part, got):
            if dst:
                cm[src] = dst; translated_now += 1
                db.execute("INSERT OR REPLACE INTO CLIENT_line(template_id, src, ru) CLIENT(?,?,?)", (t["id"], src, dst))
        db.commit()
    ru_html, touched = reCLIENT_static(html, cm)
    ru_path = os.path.join(os.path.dirname(p), "template.ru.html")
    open(ru_path, "w", encoding="utf-8").write(ru_html)
    left = sum(1 for k in keys if not cm.get(k))
    report.append({"id": t["id"], "code": t["code"], "keys": len(keys), "translated_now": translated_now,
                   "no_CLIENT": left, "ru_file": ru_path, "reCLIENTd": touched})
    print("id=%-3d %-34s статики %3d | из кэша %3d | добирали %3d | без перевода %d | заменено %d"
          % (t["id"], t["code"][:34], len(keys), len(keys) - len(missing), translated_now, left, touched))
json.dump(report, open("reports/ru_CLIENT_build.json", "w"), ensure_ascii=False, indent=1)
print("\nфайлов собрано:", sum(1 for r in report if r.get("ru_file")))
