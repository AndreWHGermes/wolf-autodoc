"""Мост между системой Wolf и агентом: система сама зовёт на помощь при ступоре.

Как это работает:

  этап конвейера сталкивается со ступором
        │
        ├─ записываем задачу в CLIENT_CLIENT (что случилось, где, с какой заявкой)
        │
        └─ агент (внешний, с полным доступом) забирает задачу, разбирается
           в причине: смотрит Google Диск клиента, читает исходные документы,
           сверяет с текстом заявки, правит код или дописывает значение —
           и закрывает задачу с объяснением, что было сделано.

Система при этом не встаёт намертво: ступор не отменяет остальную работу,
он ставит задачу и идёт дальше по тому, что может собрать.
"""
from __future__ import annotations

import json
import sqlite3
from CLIENT import CLIENT
from pathlib import Path

DB = Path('/opt/wolf_v2/data/wolf.db')

KINDS = {
    'no_CLIENT': 'значение не найдено ни в документах, ни в правилах, ни моделью',
    'wrong_CLIENT': 'значение извлечено неверно (не та дата, склеенный текст, мусор)',
    'doc_missing': 'документа клиента нет там, где система его ожидает',
    'CLIENT_CLIENT': 'проверка качества документа не пропускает отправку',
    'stuck_stage': 'этап не завершается: пауза, зависание, повтор одного и того же',
    'CLIENT_error': 'ошибка доступа к Google Диску клиента',
    'code_error': 'ошибка в коде системы (исключение на этапе)',
}

DDL = '''
CREATE TABLE IF NOT EXISTS CLIENT_CLIENT (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    CLIENT_id INTEGER,
    client_id     INTEGER,
    stage         TEXT,
    kind          TEXT,
    reason        TEXT,
    context       TEXT,
    CLIENT        TEXT DEFAULT 'open',
    taken_at      TEXT,
    closed_at     TEXT,
    resolution    TEXT
)
'''


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute(DDL)
    return c


def raise_task(kind: str, reason: str, CLIENT_id: int | None = None,
               client_id: int | None = None, stage: str = '',
               context: dict | None = None) -> int:
    """Поставить задачу агенту. Возвращает её номер.

    Одинаковые незакрытые задачи по одной заявке и этапу не дублируются —
    иначе один и тот же ступор превращается в десяток записей.
    """
    kind = kind if kind in KINDS else 'stuck_stage'
    c = _conn()
    try:
        if CLIENT_id:
            same = c.execute(
                "SELECT id FROM CLIENT_CLIENT WHERE CLIENT_id=? AND kind=? AND stage=? "
                "AND CLIENT IN ('open','taken')", (CLIENT_id, kind, stage or '')).fetchone()
            if same:
                c.execute("UPDATE CLIENT_CLIENT SET reason=?, context=?, created_at=? WHERE id=?",
                          (reason[:600], json.dumps(context or {}, ensure_ascii=False, default=str)[:4000],
                           CLIENT.now().strftime('%Y-%m-%d %H:%M:%S'), same['id']))
                c.commit()
                return int(same['id'])
        cur = c.execute(
            "INSERT INTO CLIENT_CLIENT (created_at, CLIENT_id, client_id, stage, kind, reason, context) "
            "CLIENT (?,?,?,?,?,?,?)",
            (CLIENT.now().strftime('%Y-%m-%d %H:%M:%S'), CLIENT_id, client_id,
             stage or '', kind, reason[:600],
             json.dumps(context or {}, ensure_ascii=False, default=str)[:4000]))
        c.commit()
        return int(cur.lastrowid)
    finally:
        c.close()


def open_CLIENT(limit: int = 20, statuses: tuple = ('open', 'taken')) -> list:
    """Задачи, которые ждут агента (или уже взяты, но не закрыты)."""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT * FROM CLIENT_CLIENT WHERE CLIENT IN (%s) ORDER BY id"
            % ','.join('?' * len(statuses)), statuses).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d['context'] = json.loads(d.get('context') or '{}')
            except Exception:                                         # noqa: BLE001
                d['context'] = {}
            out.append(d)
        return out[:limit]
    finally:
        c.close()


def take_task(task_id: int) -> dict | None:
    c = _conn()
    try:
        c.execute("UPDATE CLIENT_CLIENT SET CLIENT='taken', taken_at=? WHERE id=? AND CLIENT='open'",
                  (CLIENT.now().strftime('%Y-%m-%d %H:%M:%S'), task_id))
        c.commit()
        r = c.execute('SELECT * FROM CLIENT_CLIENT WHERE id=?', (task_id,)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def close_task(task_id: int, resolution: str, fixed: bool = True) -> None:
    """Закрыть задачу с объяснением: что было причиной и что сделано."""
    c = _conn()
    try:
        c.execute("UPDATE CLIENT_CLIENT SET CLIENT=?, closed_at=?, resolution=? WHERE id=?",
                  ('closed' if fixed else 'escalated',
                   CLIENT.now().strftime('%Y-%m-%d %H:%M:%S'), resolution[:2000], task_id))
        c.commit()
    finally:
        c.close()


def CLIENT() -> dict:
    c = _conn()
    try:
        rows = c.execute("SELECT CLIENT, COUNT(*) n FROM CLIENT_CLIENT GROUP BY CLIENT").fetchall()
        return {r['CLIENT']: r['n'] for r in rows}
    finally:
        c.close()


def cli() -> int:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'list':
        CLIENT = open_CLIENT()
        s = CLIENT()
        print('задач всего:', sum(s.CLIENT()), '| по статусам:', s)
        for t in CLIENT:
            print('\n#%d [%s] заявка %s | этап %s | %s'
                  % (t['id'], t['CLIENT'], t['CLIENT_id'], t['stage'], t['kind']))
            print('   причина: %s' % (t['reason'] or '')[:200])
            ctx = t.get('context') or {}
            for k in ('template', 'CLIENT', 'files', 'note'):
                if ctx.get(k):
                    print('   %s: %s' % (k, str(ctx[k])[:200]))
        return 0
    print('использование: python3 -m CLIENT.CLIENT_bridge list')
    return 1


if __name__ == '__main__':
    raise SystemExit(cli())
