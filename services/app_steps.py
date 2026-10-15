"""Журнал шагов заявки — единая лента того, что с ней происходило.

Зачем: без журнала непонятно, на каком шаге заявка встала и почему (именно так
было с заявкой 107 — работа сделана, а следов нет). Каждый шаг конвейера пишет
сюда строку: приём, очередь, скачивание, значения, сборка, проверка, отправка.
По журналу видно: где чаще встают заявки, сколько идёт каждый шаг, какая попытка.

Журнал никогда не должен ронять сам конвейер: любые ошибки записи глушатся.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'

# Порядок шагов конвейера — для картинки «где мы сейчас».
ORDER = ['accept', 'queue', 'scan', 'wait_data', 'values', 'build', 'check', 'fix', 'send', 'done']


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=60000')
    return c


def ensure_table() -> None:
    c = _conn()
    c.execute('''CREATE TABLE IF NOT EXISTS app_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 1,
        step TEXT NOT NULL,
        status TEXT NOT NULL,
        seconds REAL,
        note TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_app_steps ON app_steps(application_id, id)')
    c.commit()
    c.close()


def attempt_of(app_id: int) -> int:
    """Номер текущей попытки обработки заявки (из очереди)."""
    try:
        c = _conn()
        r = c.execute("SELECT attempts FROM auto_queue WHERE application_id=? "
                      "ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
        c.close()
        return int(r['attempts'] or 1) if r else 1
    except Exception:                                  # noqa: BLE001
        return 1


def step(app_id: int, name: str, status: str = 'ok', note: str | None = None,
         seconds: float | None = None, attempt: int | None = None) -> None:
    """Записать шаг. Ошибки записи глушим — журнал не важнее самой работы."""
    try:
        ensure_table()
        c = _conn()
        c.execute('INSERT INTO app_steps (application_id, attempt, step, status, seconds, note) '
                  'VALUES (?,?,?,?,?,?)',
                  (app_id, attempt if attempt is not None else attempt_of(app_id),
                   name, status, None if seconds is None else round(float(seconds), 2),
                   (note or '')[:600] or None))
        c.commit()
        c.close()
    except Exception:                                  # noqa: BLE001
        pass


class timer:
    """Замер шага: `with timer(app_id, 'build'): ...` — сам запишет длительность."""

    def __init__(self, app_id: int, name: str):
        self.app_id, self.name = app_id, name

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        secs = time.time() - self.t0
        step(self.app_id, self.name, 'fail' if exc_type else 'ok',
             note=str(exc)[:300] if exc else None, seconds=secs)
        return False


def trail(app_id: int, limit: int = 40) -> list[dict]:
    """Лента шагов заявки: что происходило и когда."""
    try:
        ensure_table()
        c = _conn()
        rows = [dict(r) for r in c.execute(
            'SELECT * FROM app_steps WHERE application_id=? ORDER BY id DESC LIMIT ?',
            (app_id, limit))]
        c.close()
        return list(reversed(rows))
    except Exception:                                  # noqa: BLE001
        return []


def where_now(app_id: int) -> dict:
    """Где заявка сейчас: последний успешный шаг, идущий шаг, есть ли ошибки."""
    rows = trail(app_id)
    last_ok = next((r['step'] for r in reversed(rows) if r['status'] in ('ok', 'warn')), None)
    failed = [r for r in rows if r['status'] == 'fail']
    idx = ORDER.index(last_ok) if last_ok in ORDER else -1
    return {
        'last_ok': last_ok,
        'next': ORDER[idx + 1] if 0 <= idx < len(ORDER) - 1 else None,
        'failures': len(failed),
        'last_error': (failed[-1]['note'] if failed else None),
        'steps': len(rows),
    }


def summary(hours: int = 24) -> list[dict]:
    """Сводка по шагам за сутки: сколько раз, среднее и худшее время, сбои."""
    try:
        ensure_table()
        c = _conn()
        rows = [dict(r) for r in c.execute(
            """SELECT step,
                      COUNT(*) AS times,
                      SUM(status='fail') AS fails,
                      ROUND(AVG(seconds), 1) AS avg_s,
                      ROUND(MAX(seconds), 1) AS max_s
                 FROM app_steps
                WHERE created_at >= datetime('now', ?)
                GROUP BY step ORDER BY times DESC""", ('-%d hours' % hours,))]
        c.close()
        return rows
    except Exception:                                  # noqa: BLE001
        return []
