"""Сторож системы: находит ступоры сам и ставит задачи агенту.

Запуск:  python3 scripts/stupor_watch.py            — разовый обход
         python3 scripts/stupor_watch.py --loop 120  — обход каждые 2 минуты

Что считается ступором:

  * документ заявки не прошёл проверку качества и отправка не состоялась;
  * в документе остались пустые обязательные переменные;
  * разбор заявки стартовал, но этап не завершился (пауза);
  * были ошибки доступа к Google Диску клиента;
  * в логах появилось исключение на этапе.

Каждый ступор превращается в задачу в agent_tasks (services/agent_bridge):
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
from datetime import datetime, timedelta
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


def _rebuild(app_id: int, timeout: int = 180) -> bool:
    """Пересобрать документы заявки тем же путём, что и обычный прогон."""
    import subprocess
    try:
        r = subprocess.run(['/usr/bin/python3', '-m', 'services.pipeline', str(app_id)],
                           cwd=str(BASE), capture_output=True, timeout=timeout,
                           env={**__import__('os').environ, 'PYTHONPATH': str(BASE)})
        return r.returncode == 0
    except Exception:                                                 # noqa: BLE001
        return False


def scan_quality(conn) -> int:
    """Документы, которые проверка не пропускает."""
    from services import pdf_quality
    made = 0
    apps = [r['id'] for r in conn.execute(
        "SELECT id FROM applications WHERE status IN ('new','in_work','filled') "
        "ORDER BY id DESC LIMIT 5")]
    for app_id in apps:
        if not _files(app_id):
            continue
        try:
            res = pdf_quality.check_app(app_id, save=False)
        except Exception as e:                                        # noqa: BLE001
            from services import agent_bridge
            agent_bridge.raise_task('code_error', 'проверка качества упала: %s' % str(e)[:200],
                                    application_id=app_id, stage='проверка')
            made += 1
            continue
        bad = []
        for d in res.get('docs') or []:
            for f in d.get('finds') or []:
                if f.get('level') == 'BLOCK':
                    bad.append('%s: %s' % (d.get('code'), f.get('msg')))
        # «Файл собран раньше правки шаблона» лечится сам: пересобираем заявку и
        # проверяем заново. Без этого любая правка шаблона вешала заявку в ступор
        # до прихода агента, хотя системе достаточно пересобрать документ
        # (задача #21, 17.10.2026). Задача ставится только если после пересбора
        # замечания остались.
        if bad and all('раньше последней правки шаблона' in b for b in bad):
            if _rebuild(app_id):
                try:
                    res = pdf_quality.check_app(app_id, save=False)
                except Exception:                                     # noqa: BLE001
                    res = {}
                bad = []
                for d in res.get('docs') or []:
                    for f in d.get('finds') or []:
                        if f.get('level') == 'BLOCK':
                            bad.append('%s: %s' % (d.get('code'), f.get('msg')))
                if not bad:
                    continue
        if bad:
            from services import agent_bridge
            agent_bridge.raise_task(
                'quality_block',
                'проверка не пропускает отправку: ' + ' | '.join(bad[:3]),
                application_id=app_id, stage='проверка',
                context={'files': _files(app_id), 'findings': bad[:10]})
            made += 1
    return made


def scan_empty_vars(conn) -> int:
    """Пустые переменные в уже собранных документах."""
    from services import agent_bridge
    made = 0
    apps = [r for r in conn.execute(
        "SELECT id, client_id FROM applications WHERE status IN ('new','in_work','filled') "
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
            r'(birth|passport_no|surname|name_latin|full_name|address|salary|position)', n or '')]
        if critical:
            agent_bridge.raise_task(
                'no_value', 'не заполнены важные переменные: %s' % ', '.join(critical[:8]),
                application_id=app_id, client_id=client_id, stage='данные',
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
        "SELECT id, application_id, note, docs_done, docs_total FROM drive_scans "
        "WHERE status='running' AND datetime(created_at) < datetime('now', ?)",
        ('-%d minutes' % STALE_MIN,)).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE drive_scans SET status='fail', note=? WHERE id=?",
            ('прервано: разбор не завершился (%s, сделано %s из %s)'
             % (r['note'] or 'без пояснения', r['docs_done'] or 0, r['docs_total'] or 0), r['id']))
    if rows:
        conn.commit()
    return len(rows)


def scan_stuck(conn) -> int:
    """Разбор заявки начался, но этап не двигается."""
    from services import agent_bridge
    made = 0
    fresh = (datetime.now() - timedelta(minutes=STALE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute(
        "SELECT application_id, client_id, status, docs_total, docs_done, note, created_at "
        "FROM drive_scans WHERE status='running'").fetchall()
    for r in rows:
        # Всё, что старше STALE_MIN, уже закрыто reap_stale (там сравнение в UTC):
        # сюда попадают только живые разборы — им даём время, задачи не плодим.
        if (r['created_at'] or '') < fresh:
            continue
        # «0 из 0» — разбор только начался, файлы ещё не сосчитаны
        if not r['docs_total'] and not r['docs_done']:
            continue
        agent_bridge.raise_task(
            'stuck_stage', 'разбор документов висит: «%s» (сделано %s из %s)'
            % (r['note'], r['docs_done'], r['docs_total']),
            application_id=r['application_id'], client_id=r['client_id'], stage='разбор Диска')
        made += 1
    # заявки, которые долго не двигаются
    limit = (datetime.now() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
    for a in conn.execute(
            "SELECT id, client_id, status, created_at FROM applications WHERE status='new'"):
        if (a['created_at'] or '') < limit and not _files(a['id']):
            agent_bridge.raise_task(
                'stuck_stage', 'заявка принята, но документы так и не собраны (статус new)',
                application_id=a['id'], client_id=a['client_id'], stage='сборка',
                context={'created_at': a['created_at']})
            made += 1
    return made


def scan_logs() -> int:
    """Свежие исключения в логах системы."""
    from services import agent_bridge
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
            if 'MethodNotAllowed' in tail or 'drive-scan' in tail:
                agent_bridge.raise_task('drive_error', 'ошибка запроса к Диску: %s' % tail,
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
    for name, fn in (('проверка', scan_quality), ('данные', scan_empty_vars),
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
        from services import agent_bridge
        print('обход %s: поставлено задач — %s' % (datetime.now().strftime('%H:%M:%S'), stat))
        s = agent_bridge.summary()
        print('задачи по статусам:', s)
        for t in agent_bridge.open_tasks(5):
            print('  #%d заявка %s [%s] %s' % (t['id'], t['application_id'], t['kind'],
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
