"""Инструкция для каждой переменной обычными словами — четырьмя блоками.

Для каждой переменной каждого шаблона собираем текст:

  Что это            — что за значение и как выглядит
  Откуда берётся     — источник (документ клиента / карточка заявки / справочник / правило / расчёт / модель)
  По каким правилам  — как формируется, какие варианты, границы, формы
  Связи              — в каких ещё документах пакета встречается та же переменная
                       (куда передаётся значение) и какие переменные зависят от неё (созависимые)

Текст пишется в template_variables.rule_text, прежнее описание сохраняется в rule_note,
чтобы ничего не потерять. Запуск: python3 scripts/var_instructions.py [--apply]
"""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
BACKUP = ROOT / 'data' / 'backup'

SOURCE_RU = {
    'client_doc': 'документ клиента с Google Диска (паспорт, справка банка, KITAS, резюме) — '
                  'сильнее карточки: при расхождении берём значение из документа',
    'client_card': 'карточка заявки (данные, которые ввёл администратор при приёме клиента)',
    'manual': 'вводит администратор вручную в конструкторе',
    'service': 'служебное поле системы (номер, дата, идентификатор формируются автоматически)',
    'options': 'фиксированный список вариантов — выбирает администратор или правило продукта',
    'pool': 'справочник-пул (организации, должности, суммы): значение берётся из общего списка',
    'product_rule': 'правило типа продукта — зависит от выбранного продукта заявки',
    'llm': 'подбирает модель по описанию (уникальный текст)',
    'random_bounds': 'подставляется случайно, но строго в заданных границах',
    'computed': 'считается из других переменных',
    'derived': 'производное — берётся из связанного значения',
}

DEFAULT_RULES = {
    'random_bounds': 'Значение выбирается случайно внутри границ пула сумм (год: 4 980 000–7 680 000 ₽, '
                     'месяц: 415 000–640 000 ₽, шаг 1 000 ₽, без копеек). Сумма прописью считается '
                     'из того же числа — цифры и пропись всегда совпадают.',
    'computed': 'Считается из других переменных документа; при изменении исходного значения '
                'пересчитывается автоматически.',
    'derived': 'Производное значение — берётся из уже сформированного связанного значения.',
    'service': 'Формируется системой автоматически при сборке документа.',
    'manual': 'Значение вводит администратор; если поле пустое — в документе остаётся пустое место '
              '(данные не выдумываем).',
    'llm': 'Текст подбирает модель по данным резюме; администратор может отредактировать вручную.',
}


def hue(method: str) -> str:
    m = (method or '').lower()
    if m in ('client_doc',):
        return 'зелёный'
    if m.startswith('random'):
        return 'красный'
    return 'оранжевый'


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    tpls = {r['id']: (r['code'], r['title']) for r in con.execute('SELECT id, code, title FROM templates')}
    # где ещё встречается та же переменная: имя → список шаблонов
    where = {}
    for r in con.execute('SELECT template_id, name FROM template_variables'):
        where.setdefault(r['name'], set()).add(tpls.get(r['template_id'], ('?', '?'))[0])
    pool_vars = {}
    for r in con.execute('SELECT template_id, name FROM template_variables'):
        pre = r['name'].split('_')[0]
        if len(pre) >= 3:
            pool_vars.setdefault((r['template_id'], pre), set()).add(r['name'])

    backup = []
    done = 0
    for r in con.execute('SELECT * FROM template_variables ORDER BY template_id, name'):
        tid, name = r['template_id'], r['name']
        method = (r['method'] or 'client_card').strip()
        if method == 'заявка / вручную':
            method = 'manual'
        opts = []
        try:
            opts = json.loads(r['options_json'] or '[]') or []
        except Exception:  # noqa: BLE001
            opts = []
        rule = (r['rule_text'] or '').strip() or DEFAULT_RULES.get(method, '')
        _keys = r.keys()
        _desc_col = next((c for c in ('description', 'descr', 'note', 'title', 'label') if c in _keys), None)
        desc = (r[_desc_col] if _desc_col else '') or ''
        desc = str(desc).strip()
        others = sorted(x for x in where.get(name, set()) if x != tpls.get(tid, ('?',))[0])
        siblings = sorted(pool_vars.get((tid, name.split('_')[0]), set()) - {name})
        lines = []
        lines.append('Что это: %s' % (desc or ('переменная «%s» в документе «%s»'
                                               % (name, tpls.get(tid, ('', ''))[1] or ''))))
        lines.append('Откуда берётся: %s' % SOURCE_RU.get(method, 'источник не определён — уточнить'))
        lines.append('По каким правилам формируется: %s' % (rule or 'правило не задано — значение берётся как есть'))
        if opts:
            lines.append('Варианты подстановки: %s' % '; '.join(str(o) for o in opts[:12]))
        lines.append('Цвет в конструкторе: %s (%s)'
                     % (hue(method), {'client': 'из документа клиента', 'random': 'случайно по правилам'}
                        .get('client' if method == 'client_doc' else 'random' if method.startswith('random') else 'x',
                             'собрано логически')))
        if others:
            lines.append('Связи: та же переменная используется в документах пакета — %s (значение передаётся '
                         'без изменений, правится в одном месте)' % ', '.join(others))
        else:
            lines.append('Связи: встречается только в этом документе')
        if siblings:
            lines.append('Созависимые переменные: %s (меняются вместе с этой)' % ', '.join(siblings[:10]))
        text = '\n'.join(lines)
        backup.append({'template_id': tid, 'name': name, 'rule_text': r['rule_text'],
                       'rule_note': r['rule_note'] if 'rule_note' in r.keys() else None,
                       'method': r['method']})
        if apply:
            cols = [c[1] for c in con.execute('PRAGMA table_info(template_variables)')]
            if 'rule_note' in cols:
                con.execute("""UPDATE template_variables SET rule_text=?, method=?,
                               rule_note=COALESCE(rule_note, rule_text) WHERE template_id=? AND name=?""",
                            (text, method, tid, name))
            else:
                con.execute('UPDATE template_variables SET rule_text=?, method=? WHERE template_id=? AND name=?',
                            (text, method, tid, name))
        done += 1
    if apply:
        BACKUP.mkdir(parents=True, exist_ok=True)
        p = BACKUP / ('var_instructions_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
        p.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding='utf-8')
        con.commit()
        print('инструкции записаны для', done, 'переменных; слепок:', p)
    else:
        print('(пробный прогон) переменных:', done)
        row = con.execute("SELECT name, rule_text FROM template_variables LIMIT 1").fetchone()
        print('пример текста для', row['name'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
