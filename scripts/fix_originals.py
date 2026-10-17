"""Фиксация эталонов документов: настоящий пример защищается от подмены.

Что делает:
1. Для каждого шаблона читает data/templates/<code>/example_filled.pdf.
2. Определяет, наш это файл или настоящий (по producer PDF).
3. Настоящие: копирует в data/originals/<code>.pdf (только чтение, 444) и пишет
   хэш в манифест data/originals/MANIFEST.json.
4. Для наших файлов помечает «нет настоящего эталона» — они в манифест не попадают.
5. Проверка: `--check` сверяет хэши и сообщает о подмене или потере эталона.

Запуск: /usr/bin/python3 /opt/wolf_v2/scripts/fix_originals.py [--check]
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

import pymupdf

from core import db as D

BASE = Path("/opt/wolf_v2")
ORIG_DIR = BASE / "data" / "originals"
MANIFEST = ORIG_DIR / "MANIFEST.json"
OUR_MARKERS = ("WeasyPrint", "ReportLab", "Skia", "Chromium")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def producer(path: Path) -> str:
    try:
        d = pymupdf.open(path)
        p = (d.metadata or {}).get("producer") or ""
        d.close()
        return p
    except Exception:
        return ""


def is_ours(path: Path) -> bool:
    p = producer(path)
    return any(m in p for m in OUR_MARKERS)


def main(check_only: bool) -> int:
    ORIG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = D.q("SELECT id, code, title, doc_index FROM templates ORDER BY COALESCE(doc_index,999)")
    missing, fixed, ours = [], [], []
    for r in rows:
        code = r["code"]
        ex = BASE / "data" / "templates" / code / "example_filled.pdf"
        if not ex.exists():
            missing.append((code, "нет файла примера"))
            continue
        if is_ours(ex):
            ours.append(code)
            continue
        dst = ORIG_DIR / (code + ".pdf")
        digest = sha(ex)
        if check_only:
            rec = manifest.get(code)
            if not rec:
                missing.append((code, "не зафиксирован"))
            elif rec.get("sha256") != digest or not dst.exists() or sha(dst) != rec["sha256"]:
                missing.append((code, "ПОДМЕНА или потеря эталона"))
            continue
        shutil.copy2(ex, dst)
        dst.chmod(0o444)
        manifest[code] = {"sha256": digest, "fixed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                          "pages": pymupdf.open(ex).page_count, "producer": producer(ex),
                          "index": r["doc_index"], "title": r["title"]}
        fixed.append(code)
    if not check_only:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        MANIFEST.chmod(0o444)
    print("=== зафиксировано настоящих эталонов:", len(fixed) if not check_only else len(manifest))
    for c in (fixed if not check_only else sorted(manifest)):
        print("   ✓", c)
    print("=== наши сборки вместо эталона (%d) — нужен настоящий документ:" % len(ours))
    for c in ours:
        print("   ✗", c)
    if missing:
        print("=== проблемы:", len(missing))
        for c, why in missing:
            print("   !", c, "—", why)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(BASE))
    sys.exit(main("--check" in sys.argv))
