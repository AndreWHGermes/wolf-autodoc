"""Слепок всех шаблонов Wolf: template.html + образец + манифест с хэшами.

Перед новой заявкой фиксируем состояние шаблонов — если что-то поедет, откат делается
копированием из слепка.
"""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

TPL = Path("/opt/wolf_v2/data/templates")
BKP = Path("/opt/wolf_v2/data/backups/template_snapshots")

stamp = time.strftime("%Y%m%d_%H%M%S")
snap = BKP / ("all_%s" % stamp)
snap.mkdir(parents=True, exist_ok=True)

files = 0
for d in sorted(TPL.iterdir()):
    if not d.is_dir() or not (d / "template.html").exists():
        continue
    dst = snap / d.name
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(d / "template.html", dst / "template.html")
    files += 1
    ex = d / "example_filled.pdf"
    if ex.exists():
        shutil.copy2(ex, dst / "example_filled.pdf")
        files += 1

lines = []
for p in sorted(snap.rglob("*")):
    if p.is_file() and p.name != "MANIFEST.sha256":
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append("%s  %s" % (h, p.relative_to(snap)))
(snap / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

print("снапшот:", snap)
print("файлов:", files, "| в манифесте:", len(lines))
print("шаблонов в системе:", len([d for d in TPL.iterdir() if (d / "template.html").exists()]))
