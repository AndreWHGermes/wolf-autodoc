"""Отчёт для агента: какие ступоры системы ждут разбора.

Печатает открытые задачи из agent_tasks по порядку — что случилось, на какой
заявке, что смотреть. Пусто, если разбирать нечего: тогда агента не будим.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

from services import agent_bridge                                     # noqa: E402


def main() -> int:
    tasks = agent_bridge.open_tasks(12)
    if not tasks:
        print('')
        return 0
    print('СТУПОРЫ, ЖДУЩИЕ РАЗБОРА: %d' % len(tasks))
    for t in tasks:
        print('\n--- задача #%d [%s]' % (t['id'], t['status']))
        print('заявка: %s | клиент: %s | этап: %s' % (t['application_id'], t['client_id'], t['stage']))
        print('тип: %s — %s' % (t['kind'], agent_bridge.KINDS.get(t['kind'], '')))
        print('причина: %s' % (t['reason'] or ''))
        for k, v in (t.get('context') or {}).items():
            print('%s: %s' % (k, str(v)[:600]))
    print('\nПроверка системы целиком: python3 /opt/wolf_v2/scripts/stupor_watch.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
