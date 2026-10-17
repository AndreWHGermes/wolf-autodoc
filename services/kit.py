"""Комплект документов под тип визы: доделываем всё, что можем доделать.

Логика, которую задал заказчик:

    клиент присылает то, что у него есть (фото паспорта, ВНЖ, иногда свою
    справку банка) → мы определяем тип продукта → понимаем, какие документы
    для этого типа визы нужны иммиграционной службе → и ДОДЕЛЫВАЕМ весь
    комплект своими шаблонами из тех данных, что у нас есть.

То есть отсутствие документа у клиента — это не «стоп», а задача: справку
банка, договор, письма, резюме, спонсорские письма мы выпускаем сами.

Документы делятся на два вида:
  * ОТ КЛИЕНТА — то, что изготовить нельзя: загранпаспорт, фотография,
    действующий ВНЖ/виза, адрес пребывания. Их наличие проверяем;
  * НАШИ — всё, что стоит в наборе продукта (product_documents): письма,
    форма E-02, договоры, справка банка, резюме, спонсорские письма.
    Их собираем автоматически, добирая недостающие данные.

Запуск:
    python3 -m services.kit <application_id> [--llm]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

DB = '/opt/wolf_v2/data/wolf.db'

# то, что клиент обязан предоставить: наши шаблоны тут не помогут
CLIENT_INPUTS = {
    'passport': 'Загранпаспорт клиента',
    'photo': 'Фотография клиента',
    'kitas': 'Действующий ВНЖ / виза (ITK, eVisa)',
    'address': 'Адрес пребывания в Индонезии',
    'profession': 'Профессия / должность',
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def product_kit(product_id: int) -> dict:
    """Что входит в комплект для продукта: наши документы по слотам."""
    conn = _db()
    rows = list(conn.execute(
        'SELECT pd.slot_code, pd.required, pd.sort_order, t.code AS tpl, t.title, t.id AS tpl_id '
        'FROM product_documents pd LEFT JOIN templates t ON t.id=pd.template_id '
        'WHERE pd.product_id=? ORDER BY pd.sort_order', (product_id,)))
    return {'docs': [dict(r) for r in rows]}


def build_kit(application_id: int, use_llm: bool = False, render: bool = True) -> dict:
    """Собрать полный комплект: входные данные клиента + наши документы."""
    from services import intake_gate, pipeline

    conn = _db()
    app = conn.execute('SELECT * FROM applications WHERE id=?', (application_id,)).fetchone()
    if not app:
        return {'error': 'заявка %s не найдена' % application_id}
    app = dict(app)

    gate = {}
    try:
        gate = intake_gate.gate(application_id) or {}
        if not isinstance(gate, dict):
            gate = {}
    except Exception as e:                                            # noqa: BLE001
        gate = {'error': str(e)[:200]}

    product_code = gate.get('product') or ''
    product_id = app.get('product_id')
    if not product_id and product_code:
        row = conn.execute('SELECT id FROM products WHERE code=?', (product_code,)).fetchone()
        product_id = row['id'] if row else None
    kit = product_kit(product_id) if product_id else {'docs': []}

    # что реально пришло от клиента — это входные данные, их не изготовить
    # что реально пришло от клиента — это входные данные, их не изготовить.
    # Наличие проверяем не «по имени файла», а по значениям: у паспорта это
    # номер и серия, привязанные к самому заявителю, а не к родственнику
    inputs, missing_inputs = [], []
    st = {}
    try:
        st = intake_gate.client_docs_status(application_id) or {}
    except Exception:                                                 # noqa: BLE001
        st = {}
    pool_rows = list(conn.execute(
        'SELECT variable_name, value, person FROM client_values_pool WHERE client_id=?',
        (app['client_id'],)))
    own = [r for r in pool_rows if (r['person'] or 'main') == 'main']
    own_vars = {r['variable_name'] for r in own if (r['value'] or '').strip()}
    st['passport'] = bool(own_vars & {'passport_no', 'passport_number'} and
                          own_vars & {'passport_series', 'passport_issue_date', 'birth_date',
                                      'passport_expiry'})
    for key, title in CLIENT_INPUTS.items():
        have = bool(st.get(key))
        inputs.append({'что': title, 'есть': have,
                       'статус': 'получено' if have else 'ждём от клиента'})
        if not have:
            missing_inputs.append(title)

    # наши документы: собираем весь набор, включая те, которых у клиента нет
    result = pipeline.run(application_id, use_llm=use_llm, render=render, verbose=False)
    built = {b['документ']: b for b in (result.get('built') or [])}

    ours = []
    for d in kit['docs']:
        code = d['tpl'] or d['slot_code'] or '?'
        b = built.get(code, {})
        ours.append({
            'документ': d['title'] or code,
            'код': code,
            'слот': d['slot_code'],
            'обязательный': bool(d['required']),
            'собран нами': bool(b.get('собран')),
            'файл': b.get('файл') or '',
            'ошибка': b.get('ошибка') or '',
        })

    # чего не хватает по данным в каждом нашем документе: берём из отчёта
    # конвейера, там подробно по каждому документу
    gaps = {}
    try:
        full = json.loads(Path(result.get('report') or '').read_text(encoding='utf-8'))
        for g in full.get('gaps') or []:
            gaps[g['документ']] = {'нет данных': g.get('нет данных') or [],
                                   'на проверке': g.get('на проверке') or []}
    except Exception:                                                 # noqa: BLE001
        pass

    out_total = sum(1 for o in ours if o['собран нами'])
    return {
        'application_id': application_id,
        'client_id': app.get('client_id'),
        'product': product_code,
        'product_name': gate.get('product_name') or '',
        'inputs_from_client': inputs,
        'inputs_missing': missing_inputs,
        'ours': ours,
        'ours_total': len(ours),
        'ours_built': out_total,
        'data_gaps': gaps,
        'pipeline': {'pool': result.get('pool'), 'assign': result.get('assign'),
                     'built': result.get('built'), 'verdict': result.get('verdict'),
                     'report': result.get('report')},
        'report': result.get('report'),
    }


def main() -> None:
    args = sys.argv[1:]
    app_id = int([a for a in args if a.isdigit()][0])
    kit = build_kit(app_id, use_llm='--llm' in args)

    if kit.get('error'):
        print('ошибка:', kit['error'])
        return

    print('заявка %d — %s (%s)' % (kit['application_id'], kit['product'], kit['product_name']))
    print('\nчто пришло от клиента:')
    for i in kit['inputs_from_client']:
        print('   %-6s %s' % ('есть' if i['есть'] else 'НЕТ', i['что']))
    if kit.get('inputs_missing'):
        print('   ⚠ не хватает от клиента: %s' % ', '.join(kit['inputs_missing']))
    print('\nчто делаем сами (%d из %d собрано):' % (kit['ours_built'], kit['ours_total']))
    for o in kit['ours']:
        mark = 'собран' if o['собран нами'] else ('ошибка' if o['ошибка'] else 'НЕ СОБРАН')
        print('   %-8s %-40s %s' % (mark, o['документ'], o['файл'] or o['ошибка']))

    p = kit.get('pipeline') or {}
    a = p.get('assign') if isinstance(p.get('assign'), dict) else {}
    if a:
        print('\nданные: из пула %s, вычислено %s, пусто %s, на проверке %s'
              % (len(a.get('pool_used') or []), len(a.get('derived_used') or []),
                 a.get('missing_total'), a.get('check_total')))

    verdict = (p.get('verdict') or {}).get('checked') if isinstance(p.get('verdict'), dict) else None
    if verdict:
        bad = [c for c in verdict if c.get('замечаний')]
        print('проверка: %d документов, чисто %d, замечания %d' % (len(verdict), len(verdict) - len(bad), len(bad)))
        for c in bad[:5]:
            print('   %s: %s' % (c['документ'], '; '.join(c['замечания'][:2])))
    print('\nотчёт: %s' % kit.get('report'))


if __name__ == '__main__':
    main()
