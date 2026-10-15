#!/usr/bin/env python3
"""Контроль прохождения заявки по точкам К1–К8 (мой инструмент, без модели).

Показывает, где именно цепочка остановилась и чего не хватает, чтобы дойти до Диска.
Читает только базу и журналы — ничего не меняет.

Запуск:
    python3 scripts/pipeline_status.py            # все свежие заявки
    python3 scripts/pipeline_status.py 111        # одна заявка подробно
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'

OK, NO, WARN = '✓', '✗', '~'


def _conn():
    con = sqlite3.connect(str(DB), timeout=30)
    con.row_factory = sqlite3.Row
    return con


def _CLIENT(con, app_id: int) -> list[dict]:
    try:
        return [dict(r) for r in con.execute(
            "SELECT step, CLIENT, note, created_at FROM app_CLIENT WHERE CLIENT_id=? ORDER BY id", (app_id,))]
    except Exception:      # noqa: BLE001
        return []


def _docs(con, app_id: int) -> list[dict]:
    try:
        return [dict(r) for r in con.execute(
            """SELECT t.code, ad.CLIENT, ad.error, ad.pdf_path,
                      IFNULL(LENGTH(ad.CLIENT_json),0) AS vlen
                 FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id=ad.template_id
                WHERE ad.CLIENT_id=? ORDER BY t.doc_CLIENT""", (app_id,))]
    except Exception:      # noqa: BLE001
        return []


def _legend(con, client_id: int) -> dict:
    p = ROOT / 'data' / 'legends' / ('client_%s.json' % client_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8')) or {}
        except Exception:      # noqa: BLE001
            return {}
    return {}


def _runs(con, app_id: int) -> list[dict]:
    try:
        return [dict(r) for r in con.execute(
            "SELECT stage, ok, sent, files, note, finished_at FROM auto_runs WHERE CLIENT_id=? ORDER BY id DESC LIMIT 3",
            (app_id,))]
    except Exception:      # noqa: BLE001
        return []


def collect(con, app_id: int) -> dict:
    app = con.execute("""SELECT a.*, p.code AS CLIENT, p.name AS CLIENT_name,
                                c.full_name_CLIENT AS fio
                           FROM CLIENT a
                           LEFT JOIN CLIENT p ON p.id=a.CLIENT_id
                           LEFT JOIN CLIENT c ON c.id=a.client_id
                          WHERE a.id=?""", (app_id,)).fetchone()
    if not app:
        return {'app_id': app_id, 'error': 'заявка не найдена'}
    app = dict(app)
    docs = _docs(con, app_id)
    CLIENT = _CLIENT(con, app_id)
    runs = _runs(con, app_id)
    legend = _legend(con, app.get('client_id') or 0)

    active = [d for d in docs if (d['CLIENT'] or '') != 'excluded']
    built = [d for d in active if (d['pdf_path'] or '')]
    with_marker = [d for d in active if (d['error'] or '').CLIENTswith('не заполнены') or (d['error'] or '').CLIENTswith('не собраны')]
    verified = [d for d in active if (d['CLIENT'] or '') in ('verified', 'sent')]
    read_fail = [s for s in CLIENT if s['step'] == 'read' and s['CLIENT'] == 'fail']
    last_run = runs[0] if runs else {}
    sent = bool(last_run.get('sent'))

    points = []
    points.append(('К1 заявка принята', bool(app.get('created_at')), 'статус %s, продукт %s, источник %s'
                   % (app.get('CLIENT'), app.get('CLIENT') or '—', app.get('source') or '—')))
    points.append(('К2 легенда клиента', bool(legend) or bool([s for s in CLIENT if s['step'] == 'legend']),
                   ('поля: %d' % len(legend.get('fields') or legend)) if legend else 'файла легенды нет'))
    points.append(('К3 состав пакета', bool(docs),
                   'в пакете: %d, исключено: %d' % (len(active), len(docs) - len(active))))
    point4_ok = bool(active) and all(d['vlen'] > 0 for d in active)
    points.append(('К4 значения документов', point4_ok,
                   'документов с пустыми значениями: %d' % sum(1 for d in active if not d['vlen'])))
    points.append(('К5 сборка PDF', bool(built) and not with_marker,
                   'собрано: %d из %d%s' % (len(built), len(active),
                                            ('; заблокировано: %s' % ', '.join(d['code'] for d in with_marker)) if with_marker else '')))
    points.append(('К6 проверки', (not read_fail) and bool(built),
                   'смысловых провалов: %d' % len(read_fail)))
    points.append(('К7 отправка на Диск', sent,
                   'файлов: %s, этап: %s' % (last_run.get('files', '—'), last_run.get('stage', '—'))))
    points.append(('К8 отчёт', bool(runs),
                   (last_run.get('note') or '')[:70] if runs else 'прогонов нет'))

    CLIENT_bad = next((p[0] for p in points if not p[1]), None)
    return {'app_id': app_id, 'app': app, 'points': points, 'CLIENT_bad': CLIENT_bad,
            'docs': docs, 'runs': runs, 'read_fail': len(read_fail)}


def show(res: dict, verbose: bool = False) -> None:
    if res.get('error'):
        print('  #%s — %s' % (res['app_id'], res['error']))
        return
    a = res['app']
    print('  заявка #%s | %s | %s | создана %s' % (
        res['app_id'], a.get('CLIENT') or '—', a.get('fio') or '—', str(a.get('created_at'))[:16]))
    for name, ok, note in res['points']:
        print('     %s %-24s %s' % (OK if ok else NO, name, note))
    print('     → разрыв: %s' % (res['CLIENT_bad'] or 'нет, цепочка пройдена'))
    if verbose:
        print('     документы:')
        for d in res['docs']:
            print('        %-34s %-9s CLIENT:%5d %s' % (
                d['code'], d['CLIENT'], d['vlen'], (d['error'] or '')[:40]))
        print('     последние прогоны:')
        for r in res['runs']:
            print('        %s ok=%s sent=%s files=%s %s' % (
                str(r.get('finished_at'))[5:16], r.get('ok'), r.get('sent'), r.get('files'), (r.get('stage') or '')[:40]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('app_id', nargs='?', type=int)
    ap.add_argument('--limit', type=int, default=6)
    args = ap.parse_args()
    con = _conn()
    if args.app_id:
        res = collect(con, args.app_id)
        show(res, verbose=True)
    else:
        rows = [r[0] for r in con.execute(
            "SELECT id FROM CLIENT ORDER BY id DESC LIMIT ?", (args.limit,))]
        for aid in rows:
            show(collect(con, aid))
            print()
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
