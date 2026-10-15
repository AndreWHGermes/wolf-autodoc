"""Сведение писем по офисам к одному шаблону на тип (Bridging, Conversion).

Проблема: к продукту привязаны копии письма по каждому офису иммиграции
(ngurahrai / denpasar / tabanan) в один и тот же слот. Копии расходятся по составу
переменных и требуют правок в трёх местах. Офис задаётся переменными
CLIENT_CLIENT / CLIENT_line1..3 и выбирается по адресу пребывания клиента
(логика уже есть в CLIENT/CLIENT.py).

Что делает:
  1. слепок CLIENT_CLIENT + CLIENT + template_CLIENT → data/backup/letters_merge_<ts>.json
  2. берёт самый полный шаблон группы и переименовывает его в <type>_CLIENT_letter__default
  3. остальные копии помечает CLIENT='merged' (файлы на диске сохраняются)
  4. оставляет в CLIENT_CLIENT одну привязку на слот
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
TPL_DIR = ROOT / 'data' / 'CLIENT'
BACKUP = ROOT / 'data' / 'backup'

GROUPS = [
    {
        'name': 'Bridging',
        'base': 'bridging_CLIENT_letter__denpasar',   # самый полный по переменным
        'new_code': 'bridging_CLIENT_letter__default',
        'new_CLIENT': 'Bridging: письмо в иммиграцию (офис по адресу клиента)',
        'others': ['bridging_CLIENT_letter__ngurahrai', 'bridging_CLIENT_letter__tabanan'],
        'slot': 'bridging_letter',
    },
    {
        'name': 'Conversion',
        'base': 'conversion_CLIENT_letter__ngurahrai',  # 44 переменные против 41
        'new_code': 'conversion_CLIENT_letter__default',
        'new_CLIENT': 'Conversion: письмо в иммиграцию (офис по адресу клиента)',
        'others': ['conversion_CLIENT_letter__denpasar'],
        'slot': 'conversion_letter',
    },
]


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    ts = time.strftime('%Y%m%d_%H%M%S')
    snap = {
        'CLIENT': [dict(r) for r in con.execute("SELECT * FROM CLIENT")],
        'CLIENT_CLIENT': [dict(r) for r in con.execute("SELECT * FROM CLIENT_CLIENT")],
    }
    BACKUP.mkdir(parents=True, exist_ok=True)
    snap_file = BACKUP / ('letters_merge_%s.json' % ts)
    snap_file.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding='utf-8')
    print('слепок:', snap_file)

    CLIENT = {r['code']: dict(r) for r in con.execute("SELECT id, code, CLIENT, CLIENT FROM CLIENT")}
    CLIENT_links = con.execute("SELECT COUNT(*) FROM CLIENT_CLIENT WHERE slot_code IN ('bridging_letter','conversion_letter')").fetchone()[0]

    for g in GROUPS:
        base = con.execute("SELECT * FROM CLIENT WHERE code=?", (g['new_code'],)).fetchone()
        if base:
            print('\n%s: объединённый шаблон уже есть (%s, id=%s) — доводим привязки' %
                  (g['name'], g['new_code'], base['id']))
        else:
            base = con.execute("SELECT * FROM CLIENT WHERE code=?", (g['base'],)).fetchone()
        if not base:
            print('!! нет базового шаблона', g['base'])
            continue
        base = dict(base)
        n_vars = con.execute("SELECT COUNT(*) FROM template_CLIENT WHERE template_id=?", (base['id'],)).fetchone()[0]
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
            con.execute("UPDATE CLIENT SET code=?, CLIENT=?, updated_at=CLIENT('now') WHERE id=?",
                        (g['new_code'], g['new_CLIENT'], base['id']))
            for col in ('html_path', 'source_pdf', 'example_path'):
                if base.get(col):
                    con.execute("UPDATE CLIENT SET %s=REPLACE(%s, ?, ?) WHERE id=?" %
                                (col, col), (g['base'], g['new_code'], base['id']))
        # 3. остальные копии — в архив
        for code in g['others']:
            row = con.execute("SELECT id FROM CLIENT WHERE code=?", (code,)).fetchone()
            if not row:
                print('   нет копии', code)
                continue
            con.execute("UPDATE CLIENT SET CLIENT='merged', updated_at=CLIENT('now') WHERE id=?", (row['id'],))
            print('   %s → CLIENT=merged' % code)
        # 4. привязки: одна на слот, указывает на объединённый шаблон
        ids = [base['id']] + [r['id'] for r in con.execute(
            "SELECT id FROM CLIENT WHERE code IN (%s)" % ','.join('?' * len(g['others'])), g['others'])]
        keep = con.execute("SELECT MIN(id) FROM CLIENT_CLIENT WHERE template_id=? AND slot_code=?",
                           (base['id'], g['slot'])).fetchone()[0]
        con.execute("UPDATE CLIENT_CLIENT SET template_id=? WHERE slot_code=? AND template_id IN (%s)" %
                    ','.join('?' * len(ids)),
                    tuple([base['id'], g['slot']] + ids))
        # лишние строки того же слота (копии) убираем, одну оставляем
        rows = con.execute("SELECT id FROM CLIENT_CLIENT WHERE slot_code=? ORDER BY id", (g['slot'],)).fetchall()
        if len(rows) > 1:
            for r in rows[1:]:
                con.execute("DELETE FROM CLIENT_CLIENT WHERE id=?", (r['id'],))
        con.execute("UPDATE CLIENT_CLIENT SET required=1, sort_order=COALESCE(sort_order, 0), is_default=1 "
                    "WHERE slot_code=?", (g['slot'],))
        print('   привязок в слоте %s: %d' % (g['slot'], con.execute(
            "SELECT COUNT(*) FROM CLIENT_CLIENT WHERE slot_code=?", (g['slot'],)).fetchone()[0]))

    if apply:
        con.commit()
        print('\n--- после:')
        for r in con.execute("""SELECT p.code pcode, t.code tcode, t.CLIENT, pd.slot_code
                                FROM CLIENT_CLIENT pd JOIN CLIENT p ON p.id=pd.CLIENT_id
                                JOIN CLIENT t ON t.id=pd.template_id
                                WHERE pd.slot_code IN ('bridging_letter','conversion_letter','CLIENTment_e02_bridging','CLIENTment_e02_conversion')
                                ORDER BY p.code, pd.slot_code"""):
            print('   %-10s %-40s %-8s %s' % (r['pcode'], r['tcode'], r['CLIENT'], r['slot_code']))
        print('привязок писем было %d, стало %d' % (
            CLIENT_links,
            con.execute("SELECT COUNT(*) FROM CLIENT_CLIENT WHERE slot_code IN ('bridging_letter','conversion_letter')").fetchone()[0]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
