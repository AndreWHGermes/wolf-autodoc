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


MODE_ON, MODE_PAUSE = 'on', 'pause'


def mode() -> str:
    """Режим автоматики: 'on' — заявки уходят в работу сами, 'pause' — стоят.

    Управляется кнопкой «Старт/Пауза» на главной странице сайта.
    """
    try:
        c = conn()
        r = c.execute("SELECT value FROM settings WHERE key='auto_mode'").fetchone()
        c.close()
        return (r['value'] if r else '') or MODE_PAUSE
    except Exception:                                  # noqa: BLE001
        return MODE_PAUSE


def set_mode(value: str) -> str:
    val = MODE_ON if str(value).strip() == MODE_ON else MODE_PAUSE
    c = conn()
    c.execute("INSERT INTO settings (key, value, updated_at) VALUES ('auto_mode',?,datetime('now')) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')", (val,))
    c.commit()
    c.close()
    return val


def latest(app_id: int):
    """Последняя запись очереди по заявке (или None)."""
    c = conn()
    r = c.execute("SELECT * FROM auto_queue WHERE application_id=? ORDER BY id DESC LIMIT 1",
                  (app_id,)).fetchone()
    c.close()
    return r


def set_paused(app_id: int) -> str:
    """Остановить конкретную заявку: она не берётся из очереди, пока её не запустят."""
    ensure_table()
    r = latest(app_id)
    c = conn()
    if r and r['status'] in ('queued', 'running', 'paused'):
        c.execute("UPDATE auto_queue SET status='paused' WHERE id=?", (r['id'],))
    else:
        c.execute("INSERT INTO auto_queue (application_id, status) VALUES (?, 'paused')", (app_id,))
    c.commit()
    c.close()
    return 'paused'


def set_queued(app_id: int) -> str:
    """Поставить заявку в работу (в очередь)."""
    ensure_table()
    r = latest(app_id)
    c = conn()
    if r and r['status'] in ('queued', 'running', 'failed', 'done', 'paused'):
        c.execute("UPDATE auto_queue SET status='queued', last_error=NULL WHERE id=?", (r['id'],))
    else:
        c.execute("INSERT INTO auto_queue (application_id, status) VALUES (?, 'queued')", (app_id,))
    c.commit()
    c.close()
    return 'queued'


def add(app_id: int, quiet: bool = False, force: bool = False) -> bool:
    ensure_table()
    c = conn()
    r = c.execute("SELECT id, status FROM auto_queue WHERE application_id=? "
                  "AND status IN ('queued','running','paused') ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
    if r and not force:
        if not quiet:
            print('заявка %s уже в очереди (%s)' % (app_id, r['status']))
        c.close()
        return False
    if r and force:
        c.execute("UPDATE auto_queue SET status='queued', last_error=NULL WHERE id=?", (r['id'],))
    else:
        c.execute('INSERT INTO auto_queue (application_id) VALUES (?)', (app_id,))
    c.commit()
    c.close()
    if not quiet:
        print('заявка %s поставлена в очередь' % app_id)
    return True


def add_new() -> int:
    """Поставить в очередь все входящие заявки, кроме остановленных руками и архивных."""
    ensure_table()
    c = conn()
    rows = [r['id'] for r in c.execute(
        "SELECT id FROM applications WHERE status='new' "
        "AND COALESCE(record_kind,'') <> 'archive' ORDER BY id")]
    stop = {r['application_id'] for r in c.execute(
        "SELECT application_id FROM auto_queue WHERE status='paused'")}
    wait = {r['application_id'] for r in c.execute(
        "SELECT application_id FROM auto_queue WHERE status IN ('queued','running')")}
    c.close()
    n = 0
    for i in rows:
        if i in stop or i in wait:
            continue
        if add(i, quiet=True):
            n += 1
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


def _notify_manager(app_id: int, text: str) -> None:
    """Сообщение менеджеру, который прислал заявку через бота. Ошибки не роняют очередь."""
    try:
        sys.path.insert(0, str(ROOT))
        from bot.notify import send as _send
        c = conn()
        r = c.execute("SELECT bm.telegram_id FROM applications a "
                      "JOIN bot_managers bm ON bm.id = a.bot_manager_id WHERE a.id=?",
                      (app_id,)).fetchone()
        c.close()
        if r and r['telegram_id']:
            _send(r['telegram_id'], text)
    except Exception:                                  # noqa: BLE001
        pass


def worker() -> int:
    """Взять ровно одну заявку из очереди и обработать её.

    Пока на главной стоит «Пауза», воркер ничего не берёт: новые заявки
    стоят в очереди и ждут кнопки «Старт».
    """
    limit_memory()
    ensure_table()
    if mode() != MODE_ON:
        print('автоматика на паузе — заявки не беру (%s)'
              % time.strftime('%d.%m.%Y %H:%M:%S'))
        return 0
    c = conn()
    busy = c.execute("SELECT application_id FROM auto_queue WHERE status='running' LIMIT 1").fetchone()
    c.close()
    if busy:
        print('заявка %s уже обрабатывается — очередь идёт по одной' % busy['application_id'])
        return 0
    add_new()
    c = conn()
    row = c.execute("""SELECT q.* FROM auto_queue q
                         JOIN applications a ON a.id = q.application_id
                        WHERE q.status='queued'
                          AND a.status='new'
                          AND COALESCE(a.record_kind,'') <> 'archive'
                        ORDER BY q.id LIMIT 1""").fetchone()
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
        _steps.step(app_id, 'taken', 'ok', 'взята из очереди в работу (попытка %s)' % (row['attempts'] + 1))
        _notify_manager(app_id, '⏳ Заявка #%s взята в работу. Сообщу, когда пакет будет готов.' % app_id)
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
    try:
        from services import app_steps as _steps
        if ok:
            _steps.step(app_id, 'done', 'ok', 'цикл завершён (%d сек)' % int(time.time() - t0))
        else:
            _steps.step(app_id, 'done', 'fail', ('сбой: ' + err)[-300:])
    except Exception:                                  # noqa: BLE001
        pass
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
    elif cmd == 'mode':
        print('режим автоматики: %s' % (set_mode(sys.argv[2] if len(sys.argv) > 2 else ''),))
    elif cmd == 'pause' and len(sys.argv) > 2:
        print('заявка %s остановлена (%s)' % (sys.argv[2], set_paused(int(sys.argv[2]))))
    elif cmd == 'start' and len(sys.argv) > 2:
        print('заявка %s поставлена в работу (%s)' % (sys.argv[2], set_queued(int(sys.argv[2]))))
    elif cmd == 'clear':
        clear()
    else:
        print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
