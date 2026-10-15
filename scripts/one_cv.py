"""Одно резюме вместо трёх: в наборе документов остаётся формат Сиваева.

Что установлено анализом архива (05.10.2026):
- в 74 папках клиентов на Google Диске лежат только два резюме, и оба — формата
  «имя + профессия + личные данные» (Resume_CLIENT CLIENT, Resume_Anna_CLIENT),
  то есть форма Сиваева. Третьи формы у клиентов не встречаются;
- при этом каждый продукт ссылался сразу на три формы резюме — отсюда три резюме
  в наборе документов и путаница в конструкторе.

Что делает:
1. Снимает привязки двух лишних форм (краткая и детальная) со всех продуктов;
   состав таблицы сохраняется в JSON на случай отката.
2. Помечает лишние шаблоны как скрытые (status='hidden'), файлы не удаляются.

Запуск: /usr/bin/python3 /opt/wolf_v2/scripts/one_cv.py [--apply]
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

from core import db as D  # noqa: E402

KEEP = "cv__format_CLIENT"
DROP = ("cv__format_short", "cv__format_detailed")
APPLY = "--apply" in sys.argv

print("=== сейчас в наборе ===")
for r in D.q("""SELECT p.code AS product, t.code AS tpl FROM product_documents pd
                JOIN products p ON p.id=pd.product_id JOIN templates t ON t.id=pd.template_id
                WHERE t.code LIKE 'cv__%' ORDER BY p.code, t.code"""):
    print("   %-10s %s" % (r["product"], r["tpl"]))

rows = D.q("SELECT * FROM product_documents")
snapshot = Path("/opt/wolf_v2/data/backup") / ("product_documents_" + datetime.now().strftime("%Y%m%d_%H%M") + ".json")
print("\nвсего привязок в product_documents:", len(rows))
if not APPLY:
    print("черновик: запусти с --apply")
    raise SystemExit(0)

snapshot.parent.mkdir(parents=True, exist_ok=True)
snapshot.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("слепок таблицы сохранён:", snapshot)

ids = [r["id"] for r in D.q("SELECT t.id FROM templates t WHERE t.code IN (?,?)", DROP)]
for tid in ids:
    n = D.exec_sql("DELETE FROM product_documents WHERE template_id=?", (tid,))
    print("   снято привязок у шаблона %s: %s" % (tid, n))
for tid in ids:
    D.exec_sql("UPDATE templates SET status='hidden' WHERE id=?", (tid,))
print("   шаблоны помечены как скрытые:", ids)

print("\n=== осталось в наборе ===")
for r in D.q("""SELECT p.code AS product, t.code AS tpl FROM product_documents pd
                JOIN products p ON p.id=pd.product_id JOIN templates t ON t.id=pd.template_id
                WHERE t.code LIKE 'cv__%' ORDER BY p.code"""):
    print("   %-10s %s" % (r["product"], r["tpl"]))
for r in D.q("SELECT id, code, status FROM templates WHERE code LIKE 'cv__%' ORDER BY id"):
    print("   шаблон %-24s %s" % (r["code"], r["status"]))
