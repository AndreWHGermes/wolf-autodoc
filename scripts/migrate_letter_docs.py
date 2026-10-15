"""Миграция писем в заявках после сведения шаблонов по офисам в один.

Если у заявки уже есть документ на объединённом шаблоне — остальные письма
(старые коды офисов) помечаются rejected с пояснением.
Если документа на объединённом шаблоне нет — письмо с нужным офисом переносится
на объединённый шаблон (значения лежат в строке документа, поэтому не теряются),
а лишние письма помечаются rejected; перенесённому документу ставится draft,
чтобы он пересобрался с адресом офиса по адресу клиента.

Запуск: python3 scripts/migrate_letter_docs.py [--apply]
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
BACKUP = ROOT / 'data' / 'backup'

GROUPS = [
    ('bridging_letter', 'bridging_CLIENT_letter__default',
     ['bridging_CLIENT_letter__ngurahrai', 'bridging_CLIENT_letter__denpasar',
      'bridging_CLIENT_letter__tabanan']),
    ('conversion_letter', 'conversion_CLIENT_letter__default',
     ['conversion_CLIENT_letter__ngurahrai', 'conversion_CLIENT_letter__denpasar']),
]
REASON = ('письмо сведено в один шаблон: офис иммиграции подставляется по адресу клиента '
          '(было три копии по офисам)')


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    BACKUP.mkdir(parents=True, exist_ok=True)
    snap = BACKUP / ('letter_docs_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    rows = [dict(r) for r in con.execute(
        "SELECT ad.id, ad.CLIENT_id, ad.template_id, ad.CLIENT, t.code FROM CLIENT_CLIENT ad "
        "JOIN CLIENT t ON t.id=ad.template_id WHERE t.code LIKE '%CLIENT_letter%'")]
    snap.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('слепок документов:', snap, '| строк:', len(rows))

    tpl = {r['code']: r['id'] for r in con.execute("SELECT id, code FROM CLIENT")}
    by_app: dict[int, list] = {}
    for r in rows:
        by_app.setdefault(r['CLIENT_id'], []).append(r)

    moved = marked = kept = 0
    for app_id, docs in sorted(by_app.items()):
        for slot, new_code, old_codes in GROUPS:
            group = [d for d in docs if d['code'] in old_codes or d['code'] == new_code]
            if len(group) <= 1 and all(d['code'] == new_code for d in group):
                kept += 1
                continue
            has_new = [d for d in group if d['code'] == new_code]
            others = [d for d in group if d['code'] != new_code]
            if not others:
                continue
            if has_new:
                target = has_new[0]
            else:
                # берём самое «готовое» письмо и переносим на объединённый шаблон
                rank = {'verified': 0, 'sent': 1, 'filled': 2, 'draft': 3, 'pending': 4}
                target = sorted(others, key=lambda d: rank.get(d['CLIENT'] or '', 9))[0]
                others = [d for d in others if d['id'] != target['id']]
                if apply:
                    con.execute("UPDATE CLIENT_CLIENT SET template_id=?, CLIENT='draft' WHERE id=?",
                                (tpl[new_code], target['id']))
                moved += 1
                print('   заявка %-4s: письмо %s → %s (статус draft, пересобрать)' %
                      (app_id, target['code'].split('__')[-1], new_code))
            for d in others:
                if (d['CLIENT'] or '') != 'rejected':
                    if apply:
                        con.execute("UPDATE CLIENT_CLIENT SET CLIENT='rejected', error=? WHERE id=?",
                                    (REASON, d['id']))
                    marked += 1
            if apply:
                con.execute("UPDATE CLIENT_CLIENT SET error=? WHERE id=? AND CLIENT='rejected'",
                            (REASON, target['id']))
    if apply:
        con.commit()
        left = con.execute("""SELECT COUNT(*) FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id=ad.template_id
                              WHERE t.code LIKE '%CLIENT_letter%' AND t.CLIENT='merged'
                                AND ad.CLIENT NOT IN ('rejected')""").fetchone()[0]
        print('\nперенесено на объединённый шаблон: %d | помечено rejected: %d | осталось активных на архивных шаблонах: %d'
              % (moved, marked, left))
    else:
        print('(пробный прогон: перенесли бы %d, пометили бы %d)' % (moved, marked))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
