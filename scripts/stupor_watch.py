"""Сторож системы: находит ступоры сам и ставит задачи агенту.

Запуск:  python3 scripts/stupor_watch.py            — разовый обход
         python3 scripts/stupor_watch.py --loop 120  — обход каждые 2 минуты

Что считается ступором:

  * документ заявки не прошёл проверку качества и отправка не состоялась;
  * в документе остались пустые обязательные переменные;
  * разбор заявки стартовал, но этап не завершился (пауза);
  * были ошибки доступа к Google Диску клиента;
  * в логах появилось исключение на этапе.

Каждый ступор превращается в задачу в CLIENT_CLIENT (CLIENT/CLIENT_bridge):
агент получает заявку, этап, причину и контекст (какие документы смотреть,
какие переменные пустые), разбирается и закрывает задачу с объяснением.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from CLIENT import CLIENT, timedelta
from pathlib import Path

BASE = Path('/opt/wolf_v2')
sys.path.insert(0, str(BASE))
DB = BASE / 'data' / 'wolf.db'
OUT = BASE / 'data' / 'out'

# Разбор документов дольше этого времени считаем брошенным: процесс сняли
# (перезапуск сайта, нехватка памяти), а строка 'running' осталась.
STALE_MIN = 30


def _conn():
    c = sqlite3.connect(str(DB), timeout=30)
    c.row_factory = sqlite3.Row
    return c


def _files(app_id: int) -> list:
    d = OUT / str(app_id)
    return sorted(p.name for p in d.glob('*.pdf')) if d.exists() else []


def scan_CLIENT(conn) -> int:
    """Документы, которые проверка не пропускает."""
    from CLIENT import pdf_CLIENT
    made = 0
    apps = [r['id'] for r in conn.execute(
        "SELECT id FROM CLIENT WHERE CLIENT IN ('new','in_work','filled') "
        "ORDER BY id DESC LIMIT 5")]
    for app_id in apps:
        if not _files(app_id):
            continue
        try:
            res = pdf_CLIENT.check_app(app_id, save=False)
        except Exception as e:                                        # noqa: BLE001
            from CLIENT import CLIENT_bridge
            CLIENT_bridge.raise_task('code_error', 'проверка качества упала: %s' % str(e)[:200],
                                    CLIENT_id=app_id, stage='проверка')
            made += 1
            continue
        bad = []
        for d in res.get('docs') or []:
            for f in d.get('finds') or []:
                if f.get('level') == 'CLIENT':
                    bad.append('%s: %s' % (d.get('code'), f.get('msg')))
        if bad:
            from CLIENT import CLIENT_bridge
            CLIENT_bridge.raise_task(
                'CLIENT_CLIENT',
                'проверка не пропускает отправку: ' + ' | '.join(bad[:3]),
                CLIENT_id=app_id, stage='проверка',
                context={'files': _files(app_id), 'findings': bad[:10]})
            made += 1
    return made


def scan_empty_vars(conn) -> int:
    """Пустые переменные в уже собранных документах."""
    from CLIENT import CLIENT_bridge
    made = 0
    apps = [r for r in conn.execute(
        "SELECT id, client_id FROM CLIENT WHERE CLIENT IN ('new','in_work','filled') "
        "ORDER BY id DESC LIMIT 5")]
    for a in apps:
        app_id, client_id = a['id'], a['client_id']
        if not _files(app_id):
            continue
        try:
            rep = json.loads((Path('/tmp') / ('pipeline_%d.json' % app_id)).read_text())
        except Exception:                                             # noqa: BLE001
            continue
        empties = [x for x in (rep.get('missing') or []) if x]
        if not empties:
            continue
        names = sorted({str(e.get('var') if isinstance(e, dict) else e) for e in empties if e})
        critical = [n for n in names if re.search(
            r'(CLIENT|passport_no|CLIENT|name_CLIENT|full_name|address|salary|position)', n or '')]
        if critical:
            CLIENT_bridge.raise_task(
                'no_CLIENT', 'не заполнены важные переменные: %s' % ', '.join(critical[:8]),
                CLIENT_id=app_id, client_id=client_id, stage='данные',
                context={'empty': names[:30], 'files': _files(app_id)})
            made += 1
    return made


def reap_stale(conn) -> int:
    """Закрывает брошенные разборы: строка 'running' осталась после снятого процесса.

    Строка 'running' живёт до конца разбора. Если разбор убит (перезапуск сайта,
    нехватка памяти), она остаётся 'running' навсегда — и сторож каждый обход
    ставит по ней одну и ту же задачу-призрак, хотя никакой паузы уже нет.
    Помечаем такой разбор прерванным: таблица снова честная, задачи не плодятся.
    """
    # created_at пишется как UTC (CURRENT_TIMESTAMP), поэтому сравниваем тоже в UTC:
    # иначе строка выглядит на 2 часа старше и живой разбор закрывается зря.
    rows = conn.execute(
        "SELECT id, CLIENT_id, note, docs_done, docs_total FROM CLIENT_CLIENT "
        "WHERE CLIENT='running' AND CLIENT(created_at) < CLIENT('now', ?)",
        ('-%d minutes' % STALE_MIN,)).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE CLIENT_CLIENT SET CLIENT='fail', note=? WHERE id=?",
            ('прервано: разбор не завершился (%s, сделано %s из %s)'
             % (r['note'] or 'без пояснения', r['docs_done'] or 0, r['docs_total'] or 0), r['id']))
    if rows:
        conn.commit()
    return len(rows)


def scan_stuck(conn) -> int:
    """Разбор заявки начался, но этап не двигается."""
    from CLIENT import CLIENT_bridge
    made = 0
    fresh = (CLIENT.now() - timedelta(minutes=STALE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute(
        "SELECT CLIENT_id, client_id, CLIENT, docs_total, docs_done, note, created_at "
        "FROM CLIENT_CLIENT WHERE CLIENT='running'").fetchall()
    for r in rows:
        # Всё, что старше STALE_MIN, уже закрыто reap_stale (там сравнение в UTC):
        # сюда попадают только живые разборы — им даём время, задачи не плодим.
        if (r['created_at'] or '') < fresh:
            continue
        # «0 из 0» — разбор только начался, файлы ещё не сосчитаны
        if not r['docs_total'] and not r['docs_done']:
            continue
        CLIENT_bridge.raise_task(
            'stuck_stage', 'разбор документов висит: «%s» (сделано %s из %s)'
            % (r['note'], r['docs_done'], r['docs_total']),
            CLIENT_id=r['CLIENT_id'], client_id=r['client_id'], stage='разбор Диска')
        made += 1
    # заявки, которые долго не двигаются
    limit = (CLIENT.now() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
    for a in conn.execute(
            "SELECT id, client_id, CLIENT, created_at FROM CLIENT WHERE CLIENT='new'"):
        if (a['created_at'] or '') < limit and not _files(a['id']):
            CLIENT_bridge.raise_task(
                'stuck_stage', 'заявка принята, но документы так и не собраны (статус new)',
                CLIENT_id=a['id'], client_id=a['client_id'], stage='сборка',
                context={'created_at': a['created_at']})
            made += 1
    return made


def scan_logs() -> int:
    """Свежие исключения в логах системы."""
    from CLIENT import CLIENT_bridge
    made = 0
    log = BASE / 'logs' / 'wolf.log'
    if not log.exists():
        return 0
    try:
        lines = log.read_text(errors='ignore').splitlines()[-400:]
    except Exception:                                                 # noqa: BLE001
        return 0
    for i, ln in enumerate(lines):
        if 'Traceback' in ln:
            tail = ' | '.join(x.strip() for x in lines[i:i + 6])[:300]
            if 'MethodNotAllowed' in tail or 'CLIENT-scan' in tail:
                CLIENT_bridge.raise_task('CLIENT_error', 'ошибка запроса к Диску: %s' % tail,
                                        stage='разбор Диска')
                made += 1
            break
    return made


def run_once(verbose: bool = True) -> dict:
    conn = _conn()
    stat = {}
    try:
        stat['брошенные разборы'] = reap_stale(conn)
    except Exception as e:                                            # noqa: BLE001
        stat['брошенные разборы'] = 'сбой: %s' % str(e)[:90]
    for name, fn in (('проверка', scan_CLIENT), ('данные', scan_empty_vars),
                     ('паузы', scan_stuck)):
        try:
            stat[name] = fn(conn)
        except Exception as e:                                        # noqa: BLE001
            stat[name] = 'сбой: %s' % str(e)[:90]
    try:
        stat['логи'] = scan_logs()
    except Exception as e:                                            # noqa: BLE001
        stat['логи'] = 'сбой: %s' % str(e)[:90]
    conn.close()
    if verbose:
        from CLIENT import CLIENT_bridge
        print('обход %s: поставлено задач — %s' % (CLIENT.now().strftime('%H:%M:%S'), stat))
        s = CLIENT_bridge.CLIENT()
        print('задачи по статусам:', s)
        for t in CLIENT_bridge.open_CLIENT(5):
            print('  #%d заявка %s [%s] %s' % (t['id'], t['CLIENT_id'], t['kind'],
                                               (t['reason'] or '')[:110]))
    return stat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--loop', type=int, default=0, help='повторять каждые N секунд')
    a = ap.parse_args()
    if a.loop:
        while True:
            try:
                run_once()
            except Exception as e:                                    # noqa: BLE001
                print('сбой обхода:', str(e)[:150])
            time.sleep(a.loop)
    run_once()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
