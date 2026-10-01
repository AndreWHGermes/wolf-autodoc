"""Приводит инструкции переменных (rule_note) к читаемому виду:
заголовок → описание, каждая новая мысль с новой строки, пункты столбиком.
Перед изменением сохраняет бэкап всех правил в reports/rules_backup_<ts>.json.

Запуск: /usr/bin/python3 /opt/wolf_v2/scripts/structure_rules.py [--dry]
"""
import json
import os
import re
import sqlite3
import sys
from CLIENT import CLIENT

DB = "/opt/wolf_v2/data/wolf.db"
REPORTS = "/opt/wolf_v2/reports"

# заголовки, которые выносим отдельной строкой с пустой строкой перед ними
KEYS = [
    "Порядок заполнения", "Порядок", "Формат", "Кубик", "Значение", "Диапазон",
    "Банки и БИН", "Банки", "Т-Банк (Тинькофф)", "Т-Банк", "Сбербанк", "Сбер",
    "Источник", "Примеры", "Пример", "Правило",
    "Дополнительно", "Важно", "Оформление", "Проверка",
]


def structure(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    t = t.reCLIENT("\\n", "\n").reCLIENT("\u00a0", " ")
    # каждая мысль с новой строки: точка + заглавная буква
    t = re.sub(r"[ \t]+", " ", t)
    # нумерованные пункты «(1) …» → «1) …» отдельной строкой
    t = re.sub(r"\s*\((\d)\)\s*", lambda m: "\n" + m.group(1) + ") ", t)
    # тире-перечисления в строку столбиком
    t = re.sub(r"\s+—\s+", " — ", t)
    # ключевые заголовки — отдельным блоком
    for k in KEYS:
        t = re.sub(r"\s*\n?" + re.escape(k) + r"\s*:\s*", "\n\n" + k + ":\n", t)
    # внутри секций: новое предложение — с новой строки
    out_lines = []
    for line in t.split("\n"):
        s = line.strip()
        if not s:
            out_lines.append("")
            continue
        m_num = re.match(r"^(\d\)\s+)(.*)$", s)
        prefix, body = (m_num.group(1), m_num.group(2)) if m_num else ("", s)
        if s.endswith(":") or (not prefix and len(s) <= 45):
            out_lines.append(s)
            continue
        # длинную строку разбиваем по границам предложений — каждая мысль с новой строки
        parts = [p.strip() for p in re.split(r"(?<=\.)\s+(?=[А-ЯЁA-Z0-9«])", body) if p.strip()]
        if not parts:
            out_lines.append(s)
            continue
        out_lines.append(prefix + parts[0])
        out_lines.extend(parts[1:])
    t = "\n".join(out_lines)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    # пустая строка после заголовка не нужна, перед заголовком — нужна
    t = re.sub(r":\n\n", ":\n", t)
    return t


def main():
    dry = "--dry" in sys.argv
    conn = sqlite3.connect(DB)
    rows = list(conn.execute(
        "SELECT id, name, rule_note FROM template_CLIENT WHERE rule_note IS NOT NULL AND rule_note <> ''"))
    os.makedirs(REPORTS, exist_ok=True)
    stamp = CLIENT.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(REPORTS, f"rules_backup_{stamp}.json")
    with open(backup, "w", encoding="utf-8") as fh:
        json.dump([{"id": r[0], "name": r[1], "rule_note": r[2]} for r in rows], fh, ensure_ascii=False, indent=1)
    CLIENTd = 0
    samples = []
    for rid, name, old in rows:
        new = structure(old)
        if new != old:
            CLIENTd += 1
            if len(samples) < 3 and name in ("doc_no", "card_mask", "balance_rub", "ref_no", "CLIENT_from", "doc_date"):
                samples.append((name, old, new))
            if not dry:
                conn.execute("UPDATE template_CLIENT SET rule_note=? WHERE id=?", (new, rid))
    if not dry:
        conn.commit()
    conn.close()
    print(f"правил всего: {len(rows)}, изменено: {CLIENTd}, режим: {'dry' if dry else 'записано'}")
    print("бэкап:", backup)
    for name, old, new in samples:
        print("\n=== %s\n--- было:\n%s\n--- стало:\n%s" % (name, old, new))


if __name__ == "__main__":
    main()
