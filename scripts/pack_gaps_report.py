"""Сверка системы с реальностью: чего не хватает в пакетах заявок.

Прогоняет services/pack_check по всем заявкам и пишет отчёт:
  docs/PACK_GAPS.md — сводка по продуктам и топ недостающих документов.

Запуск: /usr/bin/python3 scripts/pack_gaps_report.py
"""
import collections
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

from services import pack_check  # noqa: E402

OUT = Path('/opt/wolf_v2/docs/PACK_GAPS.md')


def main() -> int:
    con = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
    con.row_factory = sqlite3.Row
    ids = [r['id'] for r in con.execute("SELECT id FROM applications ORDER BY id")]
    full = 0
    by_prod = collections.defaultdict(lambda: [0, 0])
    miss_doc = collections.Counter()
    miss_cli = collections.Counter()
    rows = []
    for i in ids:
        try:
            r = pack_check.check(i)
        except Exception:
            continue
        if not r.get('ok'):
            continue
        by_prod[r['product']][1] += 1
        if r['complete']:
            full += 1
            by_prod[r['product']][0] += 1
        for m in r['missing']:
            miss_doc[(r['product'], m)] += 1
        for m in r['missing_client']:
            miss_cli[(r['product'], m)] += 1
        rows.append((r['application_id'], r['product'], r['progress'], r['complete'],
                     ', '.join(r['missing']) or '—', ', '.join(r['missing_client']) or '—'))

    L = ['# Пакеты заявок: чего не хватает', '',
         'Проверено заявок: **%d**, пакет собран полностью: **%d**.' % (len(rows), full), '',
         '## По продуктам (полных / всего)', '']
    for p, (f, t) in sorted(by_prod.items()):
        L.append('- **%s**: %d / %d' % (p, f, t))
    L += ['', '## Топ недостающих документов, которые генерируем мы', '']
    for (p, m), n in miss_doc.most_common(15):
        L.append('- %s → `%s` — %d заявок' % (p, m, n))
    L += ['', '## Топ недостающего от клиента', '']
    for (p, m), n in miss_cli.most_common(15):
        L.append('- %s → %s — %d заявок' % (p, m, n))
    L += ['', '## По каждой заявке', '', '| заявка | продукт | прогресс | полный | нет нашего | нет от клиента |',
          '|---|---|---|---|---|---|']
    for r in rows:
        L.append('| %s | %s | %s | %s | %s | %s |' % r)
    OUT.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('отчёт:', OUT, '| заявок:', len(rows), '| полных:', full)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
