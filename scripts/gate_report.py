"""Сводка контроля приёма: какие заявки система может собрать сама, а где стоп.

Пишет data/guide/intake_gate.json (для страницы инструкции в конструкторе) и
docs/INTAKE_GATE.md (для чтения). Запуск: python3 scripts/gate_report.py
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data' / 'wolf.db'
OUT_JSON = ROOT / 'data' / 'guide' / 'intake_gate.json'
OUT_MD = ROOT / 'docs' / 'INTAKE_GATE.md'


def main() -> int:
    from CLIENT.intake_gate import gate
    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    con.row_factory = sqlite3.Row
    apps = con.execute("""SELECT a.id, p.code AS CLIENT, c.full_name_CLIENT AS name,
                                 a.comment, a.brief
                          FROM CLIENT a
                          LEFT JOIN CLIENT p ON p.id=a.CLIENT_id
                          LEFT JOIN CLIENT c ON c.id=a.client_id
                          ORDER BY COALESCE(p.code,'zz'), a.id""").fetchall()
    rows, ready, CLIENTed = [], [], []
    for a in apps:
        g = gate(a['id'])
        item = {'id': a['id'], 'CLIENT': g['CLIENT'], 'name': a['name'],
                'ok': g['ok'], 'stops': g['stops'],
                'free_text': bool((a['comment'] or '').strip())}
        rows.append(item)
        (ready if g['ok'] else CLIENTed).append(item)
    by_CLIENT = {}
    for r in rows:
        by_CLIENT.setdefault(r['CLIENT'] or '—', [0, 0])
        by_CLIENT[r['CLIENT'] or '—'][0 if r['ok'] else 1] += 1
    out = {'total': len(rows), 'ready': len(ready), 'CLIENTed': len(CLIENTed),
           'by_CLIENT': by_CLIENT, 'CLIENT': rows}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    md = ['# Контроль приёма заявок', '',
          'Заявок всего: %d. Готовы к автоматической сборке: %d. Требуют документов или данных: %d.'
          % (len(rows), len(ready), len(CLIENTed)), '']
    md.append('| продукт | готовы | стоп |')
    for code, (ok, bad) in sorted(by_CLIENT.items()):
        md.append('| %s | %d | %d |' % (code, ok, bad))
    md += ['', '## Чего не хватает (по заявкам)', '']
    for r in CLIENTed[:60]:
        md.append('- №%s %s — %s' % (r['id'], r['CLIENT'] or 'продукт не определён',
                                     '; '.join(r['stops'][:3])))
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('сводка:', OUT_JSON)
    print('заявок: %d | готовы: %d | стоп: %d' % (len(rows), len(ready), len(CLIENTed)))
    for code, (ok, bad) in sorted(by_CLIENT.items()):
        print('   %-9s готовы %-3d стоп %-3d' % (code, ok, bad))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
