#!/usr/bin/env python3
"""Очередь заявок: принимаем мгновенно, обрабатываем строго по одной.

Заявка получает номер и подтверждение сразу при приёме, а тяжёлая обработка
идёт через очередь: воркер берёт ровно одну заявку, доводит до конца и только
потом берёт следующую. Параллельные прогоны запрещены — именно наложение
циклов (три штуки по 0,5 ГБ плюс OCR) вешало сервер 07.10.2026.

Запуск:
  queue.py add <app_id>   — поставить заявку в очередь
  queue.py add-new        — поставить все заявки со статусом new
  queue.py list           — показать очередь
  queue.py worker         — взять одну заявку и обработать (для крона)
  queue.py clear          — убрать завершённые записи из очереди
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
PY = '/usr/bin/python3'
CG = Path('/sys/fs/cgroup/wolf-cycle/cgroup.procs')   # лимит памяти на процесс


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=60000')
    return c


def limit_memory() -> None:
    """Поместить себя в cgroup с лимитом памяти (systemd-run в кроне недоступен)."""
    try:
        if CG.parent.is_dir():
            CG.write_text(str(os.getpid()))
    except OSError:
        pass


def ensure_table() -> None:
    c = conn()
    c.execute('''CREATE TABLE IF NOT EXISTS auto_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        started_at TEXT, finished_at TEXT,
        last_error TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_auto_queue_status ON auto_queue(status, id)')
    c.commit()
    c.close()


def add(app_id: int, quiet: bool = False) -> bool:
    ensure_table()
    c = conn()
    r = c.execute("SELECT id, status FROM auto_queue WHERE application_id=? "
                  "AND status IN ('queued','running') ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
    if r:
        if not quiet:
            print('заявка %s уже в очереди (%s)' % (app_id, r['status']))
        c.close()
        return False
    c.execute('INSERT INTO auto_queue (application_id) VALUES (?)', (app_id,))
    c.commit()
    c.close()
    if not quiet:
        print('заявка %s поставлена в очередь' % app_id)
    return True


def add_new() -> int:
    c = conn()
    rows = [r['id'] for r in c.execute("SELECT id FROM applications WHERE status='new' ORDER BY id")]
    c.close()
    n = sum(1 for i in rows if add(i, quiet=True))
    print('в очередь добавлено новых заявок: %d (всего новых: %d)' % (n, len(rows)))
    return n


def listing() -> None:
    ensure_table()
    c = conn()
    rows = c.execute('SELECT * FROM auto_queue ORDER BY id DESC LIMIT 12').fetchall()
    if not rows:
        print('очередь пуста')
    for r in rows:
        print('  запись %-4s заявка %-5s %-9s попыток %s %s'
              % (r['id'], r['application_id'], r['status'], r['attempts'],
                 (r['last_error'] or '').replace('\n', ' ')[:70]))
    c.close()


def clear() -> None:
    c = conn()
    n = c.execute("DELETE FROM auto_queue WHERE status IN ('done','failed')").rowcount
    c.commit()
    c.close()
    print('из очереди убрано завершённых: %d' % n)


def worker() -> int:
    """Взять ровно одну заявку из очереди и обработать её."""
    limit_memory()
    ensure_table()
    c = conn()
    row = c.execute("SELECT * FROM auto_queue WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if not row:
        c.close()
        print('очередь пуста — ждём заявок')
        return 0
    qid, app_id = row['id'], row['application_id']
    c.execute("UPDATE auto_queue SET status='running', started_at=datetime('now'), "
              "attempts=attempts+1 WHERE id=?", (qid,))
    c.commit()
    c.close()
    t0 = time.time()
    print('беру из очереди заявку %s (запись %s), старт %s'
          % (app_id, qid, time.strftime('%H:%M:%S')))
    try:
        sys.path.insert(0, str(ROOT))
        from services import app_steps as _steps
        _steps.step(app_id, 'queue', 'ok', 'взята из очереди (попытка %s)' % (row['attempts'] + 1))
    except Exception:                                  # noqa: BLE001
        pass
    try:
        rc = subprocess.run([PY, str(ROOT / 'services' / 'auto_runner.py'), str(app_id)],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
        ok = rc.returncode == 0
        err = ((rc.stdout or '') + (rc.stderr or ''))[-400:]
    except subprocess.TimeoutExpired:
        ok, err = False, 'цикл не уложился в 30 минут'
    c = conn()
    if ok:
        c.execute("UPDATE auto_queue SET status='done', finished_at=datetime('now'), "
                  "last_error=NULL WHERE id=?", (qid,))
    else:
        c.execute("""UPDATE auto_queue
                        SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'queued' END,
                            last_error=? WHERE id=?""", (err, qid))
    c.commit()
    c.close()
    print('заявка %s: %s (%d сек)' % (app_id, 'обработана' if ok else 'сбой, вернётся в очередь',
                                      int(time.time() - t0)))
    # Работа над ошибками: после заявки разбираем сбои. Если правило и инструкция
    # не помогли — администратору уходит текстовое объяснение, что не вышло.
    try:
        from services import postmortem as _pm
        _rep = _pm.report(app_id)
        _unres = _rep['unresolved']
        print('разбор ошибок: всего %s, разобрано само %s, требуют человека %s'
              % (len(_rep['analysis']['all']), len(_rep['analysis']['auto']), len(_unres)))
        if _unres and not ok:
            from bot.notify import send as _send
            from core.db import q as _q
            _msg = _pm.message_for_admin(app_id)
            if _msg:
                for _adm in _q("SELECT telegram_id FROM bot_managers "
                               "WHERE role IN ('admin','both')"):
                    try:
                        _send(_adm['telegram_id'], _msg)
                    except Exception:              # noqa: BLE001
                        pass
                print('администратору отправлено объяснение по заявке %s' % app_id)
    except Exception as _e_pm:                         # noqa: BLE001
        print('разбор ошибок не удался: %s' % str(_e_pm)[:120])
    return 0


def main() -> int:
    ensure_table()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if cmd == 'add' and len(sys.argv) > 2:
        add(int(sys.argv[2]))
    elif cmd == 'add-new':
        add_new()
    elif cmd == 'list':
        listing()
    elif cmd == 'worker':
        worker()
    elif cmd == 'clear':
        clear()
    else:
        print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
