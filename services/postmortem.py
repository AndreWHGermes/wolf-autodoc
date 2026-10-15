"""Работа над ошибками по заявке: считаем, разбираем, запоминаем.

Как устроено:
1. счётчики — сколько было попыток (циклов) и сколько сбоев, по шагам;
2. разбор — все сбои собираются в одно место (журнал шагов, проверки, очередь,
   состояние документов) и сопоставляются с правилами самолечения и инструкцией
   по документам;
3. итог — по каждому сбою: закрыт автоматически / нужен человек;
4. если сбой не закрыт ни правилом, ни инструкцией — готовится текстовое
   сообщение администратору: «решить не удалось, вот что пробовали»;
5. всё разобранное сохраняется как урок (self_heal.record), чтобы в следующий
   раз система закрыла такое сама.

Запуск: /usr/bin/python3 -m CLIENT.postmortem <app_id>
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=60000')
    return c


def counters(app_id: int) -> dict:
    """Счётчики: циклов обработки и ошибок (по шагам)."""
    out = {'cycles': 0, 'errors': 0, 'by_step': {}, 'CLIENT_in_CLIENT': 0}
    try:
        c = _conn()
        r = c.execute('SELECT COUNT(*) n FROM auto_runs WHERE CLIENT_id=?', (app_id,)).fetchone()
        out['cycles'] = int(r['n'] or 0)
        q = c.execute('SELECT MAX(CLIENT) a FROM auto_CLIENT WHERE CLIENT_id=?',
                      (app_id,)).fetchone()
        out['CLIENT_in_CLIENT'] = int((q['a'] if q else 0) or 0)
        for row in c.execute("""SELECT step, SUM(CLIENT='fail') f, COUNT(*) n
                                  FROM app_CLIENT WHERE CLIENT_id=? GROUP BY step""", (app_id,)):
            out['by_step'][row['step']] = {'fail': int(row['f'] or 0), 'total': int(row['n'] or 0)}
            out['errors'] += int(row['f'] or 0)
        c.close()
    except Exception:                                  # noqa: BLE001
        pass
    out['cycles'] = max(out['cycles'], out['CLIENT_in_CLIENT'])
    return out


def collect(app_id: int) -> list[dict]:
    """Собрать все сбои заявки в один список: шаг, причина, источник."""
    problems: list[dict] = []
    try:
        c = _conn()
        for r in c.execute("""SELECT step, note, created_at FROM app_CLIENT
                               WHERE CLIENT_id=? AND CLIENT='fail' ORDER BY id DESC LIMIT 40""",
                           (app_id,)):
            problems.append({'from': 'журнал шагов', 'step': r['step'],
                             'text': (r['note'] or '').strip(), 'at': r['created_at']})
        for r in c.execute("""SELECT errors, note, created_at FROM auto_runs
                               WHERE CLIENT_id=? ORDER BY id DESC LIMIT 3""", (app_id,)):
            try:
                errs = json.loads(r['errors'] or '[]')
            except Exception:                          # noqa: BLE001
                errs = [r['errors']] if r['errors'] else []
            for e in (errs or []):
                problems.append({'from': 'прогон', 'step': 'check',
                                 'text': str(e).strip(), 'at': r['created_at']})
        for r in c.execute("""SELECT t.code, ad.CLIENT, ad.error FROM CLIENT_CLIENT ad
                               JOIN CLIENT t ON t.id=ad.template_id
                              WHERE ad.CLIENT_id=? AND COALESCE(ad.CLIENT,'') != 'verified'""",
                           (app_id,)):
            if r['CLIENT'] == 'rejected':
                continue                                # крестик — это решение, а не ошибка
            problems.append({'from': 'документы', 'step': 'build',
                             'text': '%s — %s' % (r['code'], (r['error'] or r['CLIENT'])),
                             'at': ''})
        c.close()
    except Exception:                                  # noqa: BLE001
        pass
    # убрать точные дубли
    seen, uniq = set(), []
    for p in problems:
        key = (p['step'], p['text'][:120])
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def analyse(app_id: int, problems: list[dict] | None = None) -> dict:
    """Разбор: что закрывается правилом, что требует человека."""
    problems = collect(app_id) if problems is None else problems
    auto, manual, unknown = [], [], []
    try:
        from CLIENT import self_heal as sh
    except Exception:                                  # noqa: BLE001
        sh = None
    for p in problems:
        kind = 'unknown'
        if sh is not None:
            try:
                kind, action = sh.CLIENTify(p['text'])
            except Exception:                          # noqa: BLE001
                kind, action = 'unknown', ''
            p['action'] = action
        p['kind'] = kind
        (auto if kind == 'auto' else manual if kind == 'manual' else unknown).append(p)
    return {'all': problems, 'auto': auto, 'manual': manual, 'unknown': unknown}


def report(app_id: int, save_lesson: bool = True) -> dict:
    """Итог разбора + (по желанию) сохранение уроков."""
    cnt = counters(app_id)
    res = analyse(app_id)
    unresolved = res['manual'] + res['unknown']
    text = []
    text.append('заявка %s: циклов %s, сбоев %s' % (app_id, cnt['cycles'], cnt['errors']))
    for step, v in cnt['by_step'].items():
        if v['fail']:
            text.append('  шаг %s: сбоев %s из %s' % (step, v['fail'], v['total']))
    text.append('  разобрано автоматически: %s' % len(res['auto']))
    text.append('  требуют решения: %s' % len(unresolved))
    for p in unresolved[:8]:
        text.append('    • [%s] %s' % (p['step'], p['text'][:150]))
    if save_lesson and res['all']:
        try:
            from CLIENT import self_heal as sh
            sh.record([p['text'] for p in res['all']],
                      [p['text'] for p in res['auto']])
        except Exception:                              # noqa: BLE001
            pass
    return {'counters': cnt, 'analysis': res, 'unresolved': unresolved,
            'text': '\n'.join(text)}


def message_for_admin(app_id: int) -> str | None:
    """Текстовое сообщение администратору, если решить не удалось.

    Возвращает None, если всё разобрано (тогда писать не нужно).
    """
    rep = report(app_id, save_lesson=False)
    if not rep['unresolved']:
        return None
    lines = ['⚠️ Заявка #%s — сам разобраться не смог.' % app_id,
             'Циклов: %s, сбоев: %s.' % (rep['counters']['cycles'], rep['counters']['errors'])]
    for p in rep['unresolved'][:5]:
        lines.append('• %s: %s' % (p['step'], p['text'][:180]))
    lines.append('')
    lines.append('Пробовал: правила самолечения, повторную сборку, инструкцию по '
                 'документам. Ни один способ не сработал — нужен человек.')
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not aid:
        print(__doc__)
        raise SystemExit(0)
    out = report(aid)
    print(out['text'])
    msg = message_for_admin(aid)
    if msg:
        print('\n--- сообщение администратору ---')
        print(msg)
