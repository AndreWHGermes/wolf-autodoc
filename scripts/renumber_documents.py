#!/usr/bin/env python3
"""Сквозная нумерация документов по порядку их показа в «Все документы по типу».

Номер = позиция документа в списке: сначала группы (в порядке появления), внутри
группы — по id. Банковские справки получают №1-4 (3 мес Т-Банк, 3 мес Сбер,
12 мес Т-Банк, 12 мес Сбер), дальше — резюме, договор, письма и т.д.
Номер пишется в templates.doc_index — его показывают все места (конструктор,
продукты, карточка заявки).
"""
import sqlite3
import sys

sys.path.insert(0, '/opt/wolf_v2')

DB = '/opt/wolf_v2/data/wolf.db'


def key(code: str) -> str:
    """Точно та же группировка, что в blocks/templates/page.py:_group_by_type."""
    if code.startswith('bank_statement'):
        return 'Банковские справки'
    if code.startswith('cv'):
        return 'Резюме (CV)'
    if code.startswith('remote_work_agreement'):
        return 'Remote Work Agreement'
    if code.startswith('d12'):
        return 'D12 (ходатайства)'
    if code.startswith('statement_letter_e02'):
        return 'Statement Letter (E-02)'
    if code.startswith('bridging_') or code.startswith('conversion_'):
        if code.endswith('__ngurahrai'):
            return 'Bridging / Conversion — Ngurah Rai (Бартош)'
        if code.endswith('__denpasar'):
            return 'Bridging / Conversion — Denpasar (Арине)'
        return 'Bridging / Conversion (Индонезия)'
    return 'Прочее'


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute('SELECT id, code, title, doc_index FROM templates ORDER BY id')]

groups, order = {}, []
for r in rows:
    if r['code'] == 'test_sber':
        continue                      # тестовый шаблон в нумерацию не берём
    k = key(r['code'])
    groups.setdefault(k, []).append(r)
    if k not in order:
        order.append(k)

print('порядок нумерации:')
n = 0
for k in order:
    for r in groups[k]:
        n += 1
        conn.execute('UPDATE templates SET doc_index=? WHERE id=?', (n, r['id']))
        print(f'  №{n:<3} {r["title"][:44]:44} ({r["code"]})  было: {r["doc_index"]}')
conn.commit()
print(f'\nпронумеровано документов: {n}')
conn.close()
