"""Объединение E-02: два шаблона (Bridging и Conversion) → один каркас.

Почему: бланк FORM E-02 один и тот же; различаются только значения полей
Purpose of application и Stay Permit to be applied for — а они в системе
вычисляются по типу продукта заявки. Два шаблона одного бланка = путаница
в конструкторе и расхождение вёрсток.

Что делает:
1. Берёт поле Occupation из шаблона Conversion (в Bridging его не было) и
   добавляет в объединяемый каркас на те же координаты.
2. Переименовывает каркас: код statement_letter_e02__default, папка — так же.
3. Переводит документ продукта CONV на объединённый каркас.
4. Помечает шаблон Conversion как merged (из набора исключён, файлы сохранены).

Запуск: /usr/bin/python3 /opt/wolf_v2/scripts/merge_e02.py [--apply]
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

from core import db as D  # noqa: E402

BASE = Path("/opt/wolf_v2")
TPL_DIR = BASE / "data" / "templates"
KEEP_ID, MERGE_ID = 9, 17          # 9 — Bridging (остаётся каркасом), 17 — Conversion
NEW_CODE = "statement_letter_e02__default"
APPLY = "--apply" in sys.argv

keep = D.q1("SELECT * FROM templates WHERE id=?", (KEEP_ID,))
merge = D.q1("SELECT * FROM templates WHERE id=?", (MERGE_ID,))
keep_dir = TPL_DIR / keep["code"]
merge_dir = TPL_DIR / merge["code"]
print("каркас:     %s (%s)" % (keep["code"], keep["title"]))
print("объединяем: %s (%s)" % (merge["code"], merge["title"]))
print("новый код:  %s" % NEW_CODE)

src = keep_dir.joinpath("template.html").read_text(encoding="utf-8")
other = merge_dir.joinpath("template.html").read_text(encoding="utf-8")

# 1) поле Occupation из Conversion (по координатам блока)
BLOCK_SAFE = r'<div class="txt"[^>]*?style="[^"]*"[^>]*>(?:(?!<div).)*?</div>'


def find_block(src: str, marker: str):
    """Блок .txt, внутри которого стоит метка (без захвата соседних блоков)."""
    for m in re.finditer(BLOCK_SAFE, src, re.S):
        if re.search(r"\{\{\s*%s\s*\}\}" % marker, m.group(0)):
            return m
    return None


occ = find_block(other, "occupation")
print("\nполе Occupation в Conversion:", "найдено" if occ else "НЕ найдено")
if occ and "occupation" not in src:
    print("  → переносим в каркас: %s" % occ.group(0)[:150])
    if APPLY:
        # ставим сразу после блока, где стоит Purpose of application (там же, где в бланке)
        anchor = find_block(src, "purpose_of_application")
        if anchor:
            src = src[:anchor.end()] + "\n" + occ.group(0) + src[anchor.end():]
            print("  → вставлено после блока Purpose of application")
        else:
            idx = src.rfind("</div>")
            src = src[:idx] + "\n" + occ.group(0) + "\n" + src[idx:]
            print("  → вставлено в конец листа")

if not APPLY:
    print("\nчерновик: запусти с --apply")
    raise SystemExit(0)

# 2) переименование кода и папки
shutil.copy2(keep_dir / "template.html", keep_dir / ("template.html.bak_merge_" + datetime.now().strftime("%H%M%S")))
new_dir = TPL_DIR / NEW_CODE
if new_dir.exists():
    print("\nпапка %s уже есть — переименование пропущено" % NEW_CODE)
elif keep_dir != new_dir:
    shutil.move(str(keep_dir), str(new_dir))
    print("\nпапка шаблона переименована: %s → %s" % (keep["code"], NEW_CODE))
(new_dir / "template.html").write_text(src, encoding="utf-8")
print("template.html записан в %s" % new_dir)

# 3) БД: код, привязка CONV, статус объединённого
D.exec_sql("UPDATE templates SET code=? WHERE id=?", (NEW_CODE, KEEP_ID))
D.exec_sql("UPDATE product_documents SET template_id=? WHERE template_id=?", (KEEP_ID, MERGE_ID))
D.exec_sql("UPDATE templates SET status='merged' WHERE id=?", (MERGE_ID,))
print("БД: код каркаса обновлён, документ CONV переведён на каркас, шаблон Conversion помечен merged")

print("\n=== привязки продуктов ===")
for r in D.q("""SELECT p.code AS product, pd.template_id, t.code AS tpl, t.status
                FROM product_documents pd LEFT JOIN products p ON p.id=pd.product_id
                LEFT JOIN templates t ON t.id=pd.template_id
                WHERE pd.slot_code LIKE 'statement_e02%' ORDER BY p.code"""):
    print("   %-10s -> %-34s %s" % (r["product"], r["tpl"], r["status"]))
print("=== документы заявок по объединённому шаблону ===")
for r in D.q("SELECT application_id, status FROM application_documents WHERE template_id=?", (MERGE_ID,)):
    print("   заявка %s: %s" % (r["application_id"], r["status"]))
