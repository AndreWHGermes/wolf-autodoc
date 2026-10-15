"""Сквозной конвейер: от файлов на Диске до проверенных документов.

Повторяет то, как это должно работать на уровне заявки:

  1. приёмка     — что за продукт нужен и что вообще лежит в папке клиента;
  2. сбор         — читаем ВСЕ файлы Диска, разбираем по блокам, складываем
                    значения в пул клиента (повторно — только новые и изменённые);
  3. подстановка  — по продукту определяем нужные документы и наполняем их
                    переменные из пула, недостающее выводим из заявки;
  4. полнота      — чего не хватает: каких документов нет в папке и какие поля
                    документа нечем заполнить (это же попадает администратору);
  5. сборка       — рендер документов набора в PDF;
  6. проверка     — контроль собранных PDF: чужие имена, русский текст там,
                    где его быть не должно, пустые поля, устаревший шаблон.

Запуск:
    python3 -m services.pipeline <application_id> [--llm] [--force] [--no-render]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

OUT_DIR = Path('/opt/wolf_v2/data/out')


def run(application_id: int, use_llm: bool = False, force: bool = False,
        render: bool = True, verbose: bool = True) -> dict:
    import sqlite3

    from services import intake_gate, pool_assign, pool_builder

    t0 = time.time()
    res = {'application_id': application_id, 'steps': []}

    def step(name: str, data: dict) -> None:
        res['steps'].append({'step': name, **data})
        if verbose:
            for k, v in data.items():
                print('   %-16s %s' % (k, v))

    conn = sqlite3.connect('/opt/wolf_v2/data/wolf.db', timeout=60)
    conn.row_factory = sqlite3.Row
    app = conn.execute('SELECT * FROM applications WHERE id=?', (application_id,)).fetchone()
    if not app:
        return {'error': 'заявка %s не найдена' % application_id}
    app = dict(app)
    res['client_id'] = app['client_id']
    res['application'] = {'id': application_id, 'client_id': app['client_id'],
                          'status': app.get('status'), 'gdrive': app.get('gdrive_url') or ''}

    # 1. приёмка: продукт и что лежит в папке клиента
    print('\n[1] приёмка')
    try:
        gate = intake_gate.gate(application_id) or {}
        if not isinstance(gate, dict):
            gate = {'result': str(gate)[:200]}
    except Exception as e:                                            # noqa: BLE001
        gate = {'error': str(e)[:200]}
    res['gate'] = gate
    step('приёмка', {'продукт': gate.get('product') or gate.get('product_code') or '?',
                     'документов у клиента': (gate.get('docs') or {}).get('total')
                     if isinstance(gate.get('docs'), dict) else gate.get('docs_total'),
                     'ошибка': gate.get('error') or ''})

    # 2. сбор пула: все файлы, повторно — только новые
    print('\n[2] сбор значений')
    pool = pool_builder.build_for_client(app['client_id'], application_id,
                                         use_llm=use_llm, force=force, verbose=False)
    res['pool'] = pool
    step('сбор', {'документов': pool.get('docs'), 'новых': pool.get('new'),
                  'пропущено (уже читали)': pool.get('skipped'),
                  'значений в пуле': pool.get('values')})

    # 3. подстановка по продукту
    print('\n[3] подстановка в документы')
    assign = pool_assign.assign(application_id)
    res['assign'] = {k: v for k, v in assign.items() if k != 'docs'}
    step('подстановка', {'продукт': assign.get('product'),
                         'источник продукта': assign.get('product_from'),
                         'документов в наборе': len(assign.get('docs') or []),
                         'значений из пула': len(assign.get('pool_used') or []),
                         'вычислено': len(assign.get('derived_used') or []),
                         'пусто': assign.get('missing_total'),
                         'на проверке': assign.get('check_total')})

    # 4. полнота: чего не хватает по документам и по данным
    print('\n[4] полнота')
    gaps = []
    for d in assign.get('docs') or []:
        if d['missing'] or d['to_check']:
            gaps.append({'документ': d['template'],
                         'нет данных': [m['var'] for m in d['missing']][:12],
                         'на проверке': [m['var'] for m in d['to_check']][:8]})
    res['gaps'] = gaps
    step('полнота', {'документов с пробелами': len(gaps),
                     'всего пусто': assign.get('missing_total'),
                     'всего на проверке': assign.get('check_total')})

    # 5. сборка PDF и 6. проверка собранного
    if render:
        print('\n[5] сборка')
        from services import html_frame
        from services import render as render_mod
        out_dir = OUT_DIR / str(application_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        built = []
        for d in assign.get('docs') or []:
            code = d['template']
            target = out_dir / ('%s.pdf' % code)
            try:
                # часть шаблонов собрана по каркасу (flow), часть рендерится
                # напрямую из своего HTML — пробуем оба пути
                ok = html_frame.build_pdf(code, d['values'], target, application_id)
                if not ok:
                    html = render_mod.render_html(code=code, values=d['values'])
                    if html:
                        render_mod.render_pdf(html, out_path=target)
                        ok = target.exists()
                built.append({'документ': code, 'собран': bool(ok),
                              'файл': str(target) if ok else ''})
            except Exception as e:                                    # noqa: BLE001
                built.append({'документ': code, 'собран': False, 'ошибка': str(e)[:160]})
        res['built'] = built
        step('сборка', {'собрано': sum(1 for b in built if b['собран']),
                        'всего': len(built),
                        'папка': str(out_dir)})

        print('\n[6] проверка')
        checked, bad = [], []
        try:
            from services import pdf_quality
            # проверяем именно то, что сейчас собрали: check_app смотрит документы
            # заявки в базе, а нам нужен вердикт по свежим файлам
            checked, bad = [], []
            for b in built:
                if not b['собран']:
                    continue
                try:
                    finds = pdf_quality.check_pdf(Path(b['файл']), b['документ'],
                                                  foreign_names=pdf_quality.foreign_names_for(application_id))
                except Exception as e:                                # noqa: BLE001
                    finds = [{'code': 'check_error', 'msg': str(e)[:120]}]
                checked.append({'документ': b['документ'], 'замечаний': len(finds),
                                'замечания': [(f.get('msg') or f.get('code')) for f in finds][:6]})
                if finds:
                    bad.append(b['документ'])
            res['verdict'] = {'checked': checked, 'bad': bad}
            step('проверка', {'проверено документов': len(checked),
                              'прошли чисто': len(checked) - len(bad),
                              'с замечаниями': len(bad),
                              'документы с замечаниями': bad[:5],
                              'замечания': [m for c in checked for m in c['замечания']][:6]})
        except Exception as e:                                        # noqa: BLE001
            res['verdict'] = {'error': str(e)[:200]}
            step('проверка', {'ошибка': str(e)[:200]})

        # Подтверждение документов — автоматическое. Раньше галочку «Ок» ставил
        # менеджер, и заявка могла стоять неограниченно долго, даже когда все
        # документы были готовы. Теперь подтверждает сама система: чисто собранный
        # и прошедший проверку документ считается подтверждённым. Документы с
        # замечаниями остаются неподтверждёнными — их разбирает агент.
        try:
            from core import db as _db
            _bad = set(bad or [])
            _auto = []
            for b in built:
                if b.get('собран') and b['документ'] in _bad:
                    # документ с замечаниями не подтверждаем и снимаем прежнее
                    # подтверждение: подтверждённым считается только проверенный
                    _tpl = _db.q1('SELECT id FROM templates WHERE code=?', (b['документ'],))
                    if _tpl:
                        _r = _db.q1('SELECT id FROM application_documents WHERE application_id=? AND template_id=?',
                                    (application_id, _tpl['id']))
                        if _r:
                            _db.exec_sql("UPDATE application_documents SET status='draft' WHERE id=?", (_r['id'],))
                    continue
                if not b.get('собран'):
                    continue
                tpl = _db.q1('SELECT id FROM templates WHERE code=?', (b['документ'],))
                if not tpl:
                    continue
                tid = tpl['id']
                row = _db.q1('SELECT id FROM application_documents WHERE application_id=? AND template_id=?',
                             (application_id, tid))
                if row:
                    _db.exec_sql("UPDATE application_documents SET status='verified' WHERE id=?", (row['id'],))
                else:
                    _db.exec_sql("INSERT INTO application_documents (application_id, template_id, status) "
                                 "VALUES (?,?,'verified')", (application_id, tid))
                _auto.append(b['документ'])
            res['auto_verified'] = _auto
            if _auto:
                step('подтверждение', {'подтверждено автоматически': len(_auto),
                                       'ожидают разбора': sorted(_bad)[:5]})
        except Exception as e:                                        # noqa: BLE001
            res['auto_verified_error'] = str(e)[:200]

    res['seconds'] = round(time.time() - t0, 1)
    out = Path('/tmp/pipeline_%d.json' % application_id)
    out.write_text(json.dumps(res, ensure_ascii=False, default=str)[:600000], encoding='utf-8')
    res['report'] = str(out)
    return res


def main() -> None:
    args = [a for a in sys.argv[1:]]
    app_id = int([a for a in args if a.isdigit()][0])
    r = run(app_id, use_llm='--llm' in args, force='--force' in args,
            render='--no-render' not in args)
    if r.get('error'):
        print('ошибка:', r['error'])
        return
    print('\nготово за %s с. Отчёт: %s' % (r.get('seconds'), r.get('report')))


if __name__ == '__main__':
    main()
