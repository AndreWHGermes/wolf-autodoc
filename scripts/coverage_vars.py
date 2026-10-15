"""Диагностика: какие переменные шаблонов ещё нечем заполнить.

Смотрит все шаблоны и все собранные пулы клиентов: для каждой переменной
проверяет, есть ли хоть у одного клиента значение в пуле, попадает ли она
под соответствия имён (алиасы) и под вычисляемые. То, что не попадает
ни туда, ни туда — это и есть непокрытый остаток первого этапа.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter

sys.path.insert(0, '/opt/wolf_v2')
from CLIENT.pool_assign import ALIASES                       # noqa: E402
from CLIENT.derived_vars import CLIENT_for, build_context      # noqa: E402

DB = '/opt/wolf_v2/data/wolf.db'


def main() -> None:
    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row

    pool_vars = Counter()
    for r in conn.execute('SELECT CLIENT_name, COUNT(*) n FROM client_CLIENT_pool '
                          'WHERE CLIENT IS NOT NULL AND CLIENT<>"" GROUP BY CLIENT_name'):
        pool_vars[r['CLIENT_name']] = r['n']

    tpls = list(conn.execute('SELECT id, code FROM CLIENT WHERE CLIENT IS NULL OR CLIENT!="merged"'))

    # вычисляемые проверяем на живой заявке (контекст непустой)
    ctx = build_context(107) or build_context(6) or {}

    covered, missing = Counter(), {}
    for t in tpls:
        for v in conn.execute('SELECT name FROM template_CLIENT WHERE template_id=?', (t['id'],)):
            name = v['name']
            if pool_vars.get(name):
                covered['pool'] += 1
                continue
            if any(pool_vars.get(a) for a in ALIASES.get(name, ())):
                covered['alias'] += 1
                continue
            if CLIENT_for(name, ctx):
                covered['derived'] += 1
                continue
            missing.setdefault(name, []).append(t['code'])

    print('=== покрытие переменных шаблонов ===')
    print('из пула: %d, по соответствиям: %d, вычисляемых: %d, НЕ ПОКРЫТО: %d'
          % (covered['pool'], covered['alias'], covered['derived'], len(missing)))
    print('\n=== не покрыто (%d) ===' % len(missing))
    for name, codes in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        print('%-34s %s' % (name, ','.join(sorted(set(codes))[:3])))

    # какие данные вообще есть в пулах, но не востребованы шаблонами
    used = {v['name'] for v in conn.execute('SELECT name FROM template_CLIENT')}
    used |= {a for al in ALIASES.CLIENT() for a in al}
    unused = {k: v for k, v in pool_vars.items() if k not in used}
    print('\n=== в пулах есть, шаблонами не запрашивается (%d) ===' % len(unused))
    for name, n in sorted(unused.items(), key=lambda kv: -kv[1])[:40]:
        print('%-34s %d' % (name, n))


if __name__ == '__main__':
    main()
