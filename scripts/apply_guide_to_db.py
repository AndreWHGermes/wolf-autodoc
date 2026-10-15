"""Перенос инструкции в базу конструктора: способ формирования, варианты, правило.

Добавляет в template_variables поля method (способ формирования), options_json (варианты
подстановки), rule_text (правило словами) и проставляет их по data/guide/guide.json.

Описания на сайте (rule_note) НЕ затираются: они дополняются только там, где пусты или
содержат пометку «не описано / требует уточнения».

Запуск: python3 scripts/apply_guide_to_db.py [--apply]
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
GUIDE = ROOT / 'data' / 'guide' / 'guide.json'
BACKUP = ROOT / 'data' / 'backup'

NEW_COLUMNS = [('method', 'TEXT'), ('options_json', 'TEXT'), ('rule_text', 'TEXT')]


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(template_variables)")]
    to_add = [(c, t) for c, t in NEW_COLUMNS if c not in cols]
    print('новые поля:', to_add or '— уже есть')
    if not GUIDE.is_file():
        print('нет guide.json — сначала запусти scripts/build_guide.py')
        return 1
    guide = json.loads(GUIDE.read_text(encoding='utf-8'))

    BACKUP.mkdir(parents=True, exist_ok=True)
    snap = BACKUP / ('vars_guide_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    snap.write_text(json.dumps([dict(r) for r in con.execute("SELECT * FROM template_variables")],
                               ensure_ascii=False, indent=1), encoding='utf-8')
    print('слепок:', snap)
    if not apply:
        print('(пробный прогон)')
        return 0

    for col, ctype in to_add:
        con.execute("ALTER TABLE template_variables ADD COLUMN %s %s" % (col, ctype))
    upd = note_upd = 0
    for tcode, t in (guide.get('templates') or {}).items():
        row = con.execute("SELECT id FROM templates WHERE code=?", (tcode,)).fetchone()
        if not row:
            continue
        for name, v in (t.get('variables') or {}).items():
            opts = json.dumps(v.get('options') or [], ensure_ascii=False)
            con.execute("""UPDATE template_variables SET method=?, options_json=?, rule_text=?
                           WHERE template_id=? AND name=?""",
                        (v.get('method') or '', opts, v.get('rule') or '', row['id'], name))
            upd += 1
            cur = con.execute("SELECT rule_note FROM template_variables WHERE template_id=? AND name=?",
                              (row['id'], name)).fetchone()
            note = (cur['rule_note'] or '') if cur else ''
            if (not note.strip()) or ('не описано' in note) or ('уточнения' in note):
                if v.get('rule'):
                    con.execute("UPDATE template_variables SET rule_note=? WHERE template_id=? AND name=?",
                                (v['rule'], row['id'], name))
                    note_upd += 1
    con.commit()
    print('обновлено переменных: %d | дописано описаний на сайте: %d' % (upd, note_upd))
    by_method = {}
    for r in con.execute("SELECT method, COUNT(*) n FROM template_variables GROUP BY 1 ORDER BY 2 DESC"):
        by_method[r['method'] or '(пусто)'] = r['n']
    print('способы формирования:', by_method)
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
