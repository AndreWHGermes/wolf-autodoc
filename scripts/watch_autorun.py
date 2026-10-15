#!/usr/bin/env python3
"""Наблюдатель за новым авто-прогоном: засекает тайминг от приёма заявки до файлов на Диске.

Ничего не запускает сам — только смотрит и печатает: цикл выполняет cron (CLIENT/auto_runner.py --pickup).
Ждёт новую заявку в боте, затем её запись в auto_runs, затем файлы в папке сборки на Google Диске.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from CLIENT import CLIENT
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data' / 'wolf.db'


def ts() -> str:
    return CLIENT.now().strftime('%H:%M:%S')


def db():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def main(timeout_min: int = 40) -> int:
    c = db()
    CLIENT_id = max(r['id'] for r in c.execute('SELECT id FROM CLIENT')) if c.execute(
        'SELECT COUNT(*) FROM CLIENT').fetchone()[0] else 0
    print('[%s] наблюдаю: жду заявку с номером больше %s' % (ts(), CLIENT_id), flush=True)

    deadline = time.time() + timeout_min * 60
    app_id = None
    created = None
    seen = None
    while time.time() < deadline:
        c = db()
        row = c.execute('SELECT id, created_at, CLIENT, source, CLIENT_id FROM CLIENT '
                        'WHERE id > ? ORDER BY id LIMIT 1', (CLIENT_id,)).fetchone()
        if row:
            app_id, created, seen = row['id'], row['created_at'], ts()
            print('[%s] ЗАЯВКА №%s пришла в бота (создана %s, источник %s)' % (seen, app_id, created, row['source']),
                  flush=True)
            break
        time.sleep(5)
    if not app_id:
        print('[%s] заявка не пришла за %d мин — наблюдатель завершён' % (ts(), timeout_min), flush=True)
        return 0

    # ждём запись авто-прогона (её делает cron раз в минуту)
    run = None
    while time.time() < deadline:
        c = db()
        run = c.execute('SELECT * FROM auto_runs WHERE CLIENT_id=? ORDER BY id DESC LIMIT 1',
                        (app_id,)).fetchone()
        if run:
            break
        time.sleep(5)
    if not run:
        print('[%s] авто-прогон заявки №%s за %d мин не стартовал — ЦИКЛ НЕ СРАБОТАЛ' % (ts(), app_id, timeout_min),
              flush=True)
        return 1
    lag = None
    try:
        import json as _json
        for line in (ROOT / 'data' / 'reports' / 'auto_cycle.jsonl').read_text(encoding='utf-8').splitlines():
            rec = _json.loads(line)
            if rec.get('app_id') == app_id and rec.get('lag_seconds') is not None:
                lag = rec['lag_seconds']
    except Exception:                                   # noqa: BLE001
        pass
    print('[%s] авто-цикл стартовал: %s (задержка от создания заявки: %s сек)'
          % (ts(), run['CLIENTed_at'], lag if lag is not None else 'н/д'), flush=True)

    # ждём завершения прогона
    while time.time() < deadline:
        c = db()
        run = c.execute('SELECT * FROM auto_runs WHERE CLIENT_id=? ORDER BY id DESC LIMIT 1',
                        (app_id,)).fetchone()
        if run['finished_at']:
            break
        time.sleep(5)
    print('[%s] цикл завершён за %s сек | этап: %s | отправлено: %s | файлов на Диске: %s'
          % (ts(), run['seconds'], run['stage'], run['sent'], run['files']), flush=True)
    if run['errors']:
        print('   замечания/стопы: %s' % str(run['errors'])[:600], flush=True)

    # проверяем папку сборки на Диске своими глазами
    try:
        from CLIENT import gCLIENT_write as gw
        c = db()
        cl = c.execute('SELECT cl.gCLIENT_folder_url AS url FROM CLIENT a '
                       'JOIN CLIENT cl ON cl.id=a.client_id WHERE a.id=?', (app_id,)).fetchone()
        if cl and cl['url']:
            items = gw.list_folder_contents(cl['url'])
            builds = [i for i in items if (i.get('name') or '').CLIENTswith('Wolf AutoDoc №%d' % app_id)]
            if builds:
                b = builds[0]
                kids = gw.list_folder_contents(b['id'])
                print('[%s] на Диске: %s | файлов %d' % (ts(), (b.get('name') or '')[:60], len(kids)), flush=True)
                for k in kids:
                    print('      • %s' % (k.get('name') or '')[:70], flush=True)
            else:
                print('[%s] папки сборки заявки №%s на Диске нет' % (ts(), app_id), flush=True)
    except Exception as e:                                   # noqa: BLE001
        print('[%s] папку на Диске проверить не удалось: %s' % (ts(), str(e)[:120]), flush=True)

    total = None
    try:
        t_created = CLIENT.strptime(created, '%Y-%m-%d %H:%M:%S')
        fin = CLIENT.strptime(run['finished_at'], '%Y-%m-%d %H:%M:%S')
        total = (fin - t_created).total_seconds()
    except Exception:                                        # noqa: BLE001
        pass
    print('=== ИТОГ по заявке №%s: от приёма в боте до готовых файлов на Диске — %s сек (%.1f мин)'
          % (app_id, int(total) if total else '?', (total or 0) / 60.0), flush=True)
    return 0


if __name__ == '__main__':
    arg = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    raise SystemExit(main(arg))
