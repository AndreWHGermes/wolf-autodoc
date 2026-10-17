"""Сведение писем по офисам к одному шаблону на тип (Bridging, Conversion).

Проблема: к продукту привязаны копии письма по каждому офису иммиграции
(ngurahrai / denpasar / tabanan) в один и тот же слот. Копии расходятся по составу
переменных и требуют правок в трёх местах. Офис задаётся переменными
addressee_office / addressee_line1..3 и выбирается по адресу пребывания клиента
(логика уже есть в services/values.py).

Что делает:
  1. слепок product_documents + templates + template_variables → data/backup/letters_merge_<ts>.json
  2. берёт самый полный шаблон группы и переименовывает его в <type>_request_letter__default
  3. остальные копии помечает status='merged' (файлы на диске сохраняются)
  4. оставляет в product_documents одну привязку на слот
  5. печатает сводку до/после

Запуск: python3 scripts/merge_letters.py [--apply]
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
TPL_DIR = ROOT / 'data' / 'templates'
BACKUP = ROOT / 'data' / 'backup'

GROUPS = [
    {
        'name': 'Bridging',
        'base': 'bridging_request_letter__denpasar',   # самый полный по переменным
        'new_code': 'bridging_request_letter__default',
        'new_title': 'Bridging: письмо в иммиграцию (офис по адресу клиента)',
        'others': ['bridging_request_letter__ngurahrai', 'bridging_request_letter__tabanan'],
        'slot': 'bridging_letter',
    },
    {
        'name': 'Conversion',
        'base': 'conversion_request_letter__ngurahrai',  # 44 переменные против 41
        'new_code': 'conversion_request_letter__default',
        'new_title': 'Conversion: письмо в иммиграцию (офис по адресу клиента)',
        'others': ['conversion_request_letter__denpasar'],
        'slot': 'conversion_letter',
    },
]


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    ts = time.strftime('%Y%m%d_%H%M%S')
    snap = {
        'templates': [dict(r) for r in con.execute("SELECT * FROM templates")],
        'product_documents': [dict(r) for r in con.execute("SELECT * FROM product_documents")],
    }
    BACKUP.mkdir(parents=True, exist_ok=True)
    snap_file = BACKUP / ('letters_merge_%s.json' % ts)
    snap_file.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding='utf-8')
    print('слепок:', snap_file)

    before = {r['code']: dict(r) for r in con.execute("SELECT id, code, title, status FROM templates")}
    before_links = con.execute("SELECT COUNT(*) FROM product_documents WHERE slot_code IN ('bridging_letter','conversion_letter')").fetchone()[0]

    for g in GROUPS:
        base = con.execute("SELECT * FROM templates WHERE code=?", (g['new_code'],)).fetchone()
        if base:
            print('\n%s: объединённый шаблон уже есть (%s, id=%s) — доводим привязки' %
                  (g['name'], g['new_code'], base['id']))
        else:
            base = con.execute("SELECT * FROM templates WHERE code=?", (g['base'],)).fetchone()
        if not base:
            print('!! нет базового шаблона', g['base'])
            continue
        base = dict(base)
        n_vars = con.execute("SELECT COUNT(*) FROM template_variables WHERE template_id=?", (base['id'],)).fetchone()[0]
        print('\n%s: базовый %s (id=%s, %d переменных) → %s' % (g['name'], base['code'], base['id'], n_vars, g['new_code']))
        if not apply:
            print('   (пробный прогон, изменения не применены)')
            continue
        # 1. папка шаблона
        old_dir = TPL_DIR / g['base']
        new_dir = TPL_DIR / g['new_code']
        if old_dir.is_dir() and not new_dir.exists():
            old_dir.rename(new_dir)
            print('   папка: %s → %s' % (old_dir.name, new_dir.name))
        if base['code'] != g['new_code']:
            # 2. сам шаблон
            con.execute("UPDATE templates SET code=?, title=?, updated_at=datetime('now') WHERE id=?",
                        (g['new_code'], g['new_title'], base['id']))
            for col in ('html_path', 'source_pdf', 'example_path'):
                if base.get(col):
                    con.execute("UPDATE templates SET %s=REPLACE(%s, ?, ?) WHERE id=?" %
                                (col, col), (g['base'], g['new_code'], base['id']))
        # 3. остальные копии — в архив
        for code in g['others']:
            row = con.execute("SELECT id FROM templates WHERE code=?", (code,)).fetchone()
            if not row:
                print('   нет копии', code)
                continue
            con.execute("UPDATE templates SET status='merged', updated_at=datetime('now') WHERE id=?", (row['id'],))
            print('   %s → status=merged' % code)
        # 4. привязки: одна на слот, указывает на объединённый шаблон
        ids = [base['id']] + [r['id'] for r in con.execute(
            "SELECT id FROM templates WHERE code IN (%s)" % ','.join('?' * len(g['others'])), g['others'])]
        keep = con.execute("SELECT MIN(id) FROM product_documents WHERE template_id=? AND slot_code=?",
                           (base['id'], g['slot'])).fetchone()[0]
        con.execute("UPDATE product_documents SET template_id=? WHERE slot_code=? AND template_id IN (%s)" %
                    ','.join('?' * len(ids)),
                    tuple([base['id'], g['slot']] + ids))
        # лишние строки того же слота (копии) убираем, одну оставляем
        rows = con.execute("SELECT id FROM product_documents WHERE slot_code=? ORDER BY id", (g['slot'],)).fetchall()
        if len(rows) > 1:
            for r in rows[1:]:
                con.execute("DELETE FROM product_documents WHERE id=?", (r['id'],))
        con.execute("UPDATE product_documents SET required=1, sort_order=COALESCE(sort_order, 0), is_default=1 "
                    "WHERE slot_code=?", (g['slot'],))
        print('   привязок в слоте %s: %d' % (g['slot'], con.execute(
            "SELECT COUNT(*) FROM product_documents WHERE slot_code=?", (g['slot'],)).fetchone()[0]))

    if apply:
        con.commit()
        print('\n--- после:')
        for r in con.execute("""SELECT p.code pcode, t.code tcode, t.status, pd.slot_code
                                FROM product_documents pd JOIN products p ON p.id=pd.product_id
                                JOIN templates t ON t.id=pd.template_id
                                WHERE pd.slot_code IN ('bridging_letter','conversion_letter','statement_e02_bridging','statement_e02_conversion')
                                ORDER BY p.code, pd.slot_code"""):
            print('   %-10s %-40s %-8s %s' % (r['pcode'], r['tcode'], r['status'], r['slot_code']))
        print('привязок писем было %d, стало %d' % (
            before_links,
            con.execute("SELECT COUNT(*) FROM product_documents WHERE slot_code IN ('bridging_letter','conversion_letter')").fetchone()[0]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
