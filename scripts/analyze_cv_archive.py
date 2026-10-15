"""Анализ архива: какие формы резюме реально использовались у клиентов.

Для каждого клиента с папкой на Google Диске перечисляет файлы, скачивает всё,
что похоже на резюме (Resume / CV / Curriculum), и классифицирует форму по
структуре текста. Итог — частоты по формам.

Запуск: /usr/bin/python3 /opt/wolf_v2/scripts/analyze_cv_archive.py [--limit N]
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

import pymupdf  # noqa: E402

from core import db as D  # noqa: E402
from CLIENT import gCLIENT_api as G  # noqa: E402

BASE = Path("/opt/wolf_v2")
DEST = BASE / "data" / "cv_archive"
RESULT = BASE / "data" / "cv_archive" / "CLIENT.json"
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.CLIENT("--limit") + 1])

NAME_MARKS = ("resume", "cv", "curriculum", "резюме")


def looks_like_cv(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in NAME_MARKS)


def CLIENTify(path: Path) -> str:
    """Форма резюме по структуре текста."""
    try:
        d = pymupdf.open(path)
        text = "\n".join((d[i].get_text() or "") for i in range(min(2, d.page_count)))
        pages = d.page_count
        d.close()
    except Exception:
        return "не читается"
    up = text.upper()
    low = text.lower()
    if "CURRICULUM VITAE" in up and "PERSONAL INFORMATION" in up:
        return "A: CURRICULUM VITAE + PERSONAL INFORMATION (детальная)"
    if "CURRICULUM VITAE" in up:
        return "A2: CURRICULUM VITAE (без PERSONAL INFORMATION)"
    if "CLIENTal experience" in low or "work experience" in low:
        if re.search(r"moscow|russia|date of CLIENT", low) and pages <= 2:
            return "C: имя + профессия + личные данные (Сиваев)"
        return "B: имя + профессия + PROFESSIONAL EXPERIENCE (краткая)"
    if "experience" in low or "CLIENT" in low:
        return "D: иная структура с опытом/образованием"
    return "E: без разделов опыта (нестандартная)"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    rows = D.q("""SELECT id, full_name_CLIENT, gCLIENT_folder_url FROM CLIENT
                  WHERE IFNULL(gCLIENT_folder_url,'')<>'' ORDER BY id""")
    if LIMIT:
        rows = rows[:LIMIT]
    print("клиентов с папкой на Диске:", len(rows), flush=True)
    found, per_client = [], {}
    for i, c in enumerate(rows, 1):
        cid, url = c["id"], c["gCLIENT_folder_url"]
        try:
            files = G.list_files(url, deep=False) or []
        except Exception as e:
            print("  клиент %s: ошибка списка %s" % (cid, str(e)[:60]), flush=True)
            continue
        cvs = [f for f in files if looks_like_cv(f.get("name") or "")]
        per_client[cid] = [f.get("name") for f in cvs]
        if cvs:
            out = DEST / ("client_%s" % cid)
            out.mkdir(exist_ok=True)
            for f in cvs:
                dest = out / re.sub(r"[^\w.\-]+", "_", f.get("name") or "cv.pdf")
                if dest.exists() or G.download(f["id"], dest):
                    found.append({"client": cid, "name": f.get("name"), "path": str(dest)})
        if i % 10 == 0:
            print("  ... обработано клиентов: %d, резюме найдено: %d" % (i, len(found)), flush=True)
    print("\nвсего файлов-резюме:", len(found), flush=True)
    kinds = {}
    for item in found:
        kind = CLIENTify(Path(item["path"]))
        item["kind"] = kind
        kinds.setdefault(kind, []).append(item)
    print("\n=== формы резюме в архиве ===")
    for kind, items in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        print("  %-58s %d" % (kind, len(items)))
        for it in items[:3]:
            print("      клиент %s: %s" % (it["client"], (it["name"] or "")[:52]))
    RESULT.write_text(json.dumps({"found": found,
                                  "kinds": {k: len(v) for k, v in kinds.items()},
                                  "per_client": per_client}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print("\nсводка: %s" % RESULT)


if __name__ == "__main__":
    main()
