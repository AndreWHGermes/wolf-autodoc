"""Отчёт для агента: какие ступоры системы ждут разбора.

Печатает открытые задачи из CLIENT_CLIENT по порядку — что случилось, на какой
заявке, что смотреть. Пусто, если разбирать нечего: тогда агента не будим.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

from CLIENT import CLIENT_bridge                                     # noqa: E402


def main() -> int:
    CLIENT = CLIENT_bridge.open_CLIENT(12)
    if not CLIENT:
        print('')
        return 0
    print('СТУПОРЫ, ЖДУЩИЕ РАЗБОРА: %d' % len(CLIENT))
    for t in CLIENT:
        print('\n--- задача #%d [%s]' % (t['id'], t['CLIENT']))
        print('заявка: %s | клиент: %s | этап: %s' % (t['CLIENT_id'], t['client_id'], t['stage']))
        print('тип: %s — %s' % (t['kind'], CLIENT_bridge.KINDS.get(t['kind'], '')))
        print('причина: %s' % (t['reason'] or ''))
        for k, v in (t.get('context') or {}).items():
            print('%s: %s' % (k, str(v)[:600]))
    print('\nПроверка системы целиком: python3 /opt/wolf_v2/scripts/stupor_watch.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
