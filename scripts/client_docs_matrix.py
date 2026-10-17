"""Что клиент даёт по каждому продукту и что из этих документов система берёт.

Для каждого продукта собираем:

  • обязательный минимум документов клиента (без него система не собирает пакет);
  • дополнительные документы (нужны по ситуации: продление, семья, есть у клиента);
  • какие переменные берём из каждого документа клиента и в какие наши документы они идут.

Результат: data/guide/client_docs_matrix.json (для конструктора) и
docs/CLIENT_DOCS_MATRIX.md (текстом для чтения).
"""
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
OUT_JSON = ROOT / 'data' / 'guide' / 'client_docs_matrix.json'
OUT_MD = ROOT / 'docs' / 'CLIENT_DOCS_MATRIX.md'

# какой документ клиента за какие переменные отвечает (по имени переменной)
DOC_VARS = [
    ('Загранпаспорт клиента', 'обязательно',
     'фото страницы с данными (может выглядеть по-разному — читаем значения)',
     r'^(passport_|passport|date_of_birth|birth_date|birth_place|place_of_birth|nationality|'
     r'citizenship|client_name|full_name|full_name_latin|employee_full_name|employee_name|'
     r'gender|sex|date_of_issue|date_of_expiry)'),
    ('Фотография клиента', 'обязательно', 'цветное фото, вставляется в документы',
     r'^(client_photo|client_photo_url|photo)'),
    ('Справка банка об остатке', 'обязательно',
     'период по продукту: 12 месяцев — для нового E33G, 3 месяца — для C1, продления и D12',
     r'^(balance_|balance|account_|card_mask|bank_|period_|ref_no|doc_no|statement_)'),
    ('Адрес проживания (документ или карточка)', 'обязательно',
     'адрес в стране гражданства; отдельно — адрес пребывания в Индонезии',
     r'^(address_|client_address|city|postal|zip)'),
    ('Действующий KITAS / ITK', 'по ситуации',
     'нужен для продления (E33G-EXT, C1-EXT) и конверсии (CONV)',
     r'^(itk_|stay_permit|kitas|permit_)'),
    ('Свидетельство о браке / о рождении', 'по ситуации',
     'когда подача с супругом(ой) или детьми',
     r'^(spouse_|wife_|husband_|marriage_|child_|children_|family_)'),
    ('Commitment / guarantee letter', 'по ситуации',
     'для зависимых членов семьи — подписывает основной заявитель',
     r'^(guarantor|commitment|sponsor_)'),
    ('Трудовая книжка (ИТК)', 'если есть',
     'встречается редко; из неё берём профессию и стаж',
     r'^(occupation|position|job_|cv_job|employment_history|experience)'),
]

# ключевые значения, без которых сборка стопорится (по продуктам)
STOP_KEYS = {
    'BRIDGING': ['тип продукта', 'профессия клиента', 'паспорт клиента', 'фотография клиента',
                 'адрес пребывания в Индонезии', 'действующий KITAS/ITK'],
    'CONV': ['тип продукта', 'паспорт клиента', 'фотография клиента',
             'адрес пребывания в Индонезии', 'действующий KITAS/ITK'],
    'C1': ['тип продукта', 'профессия клиента', 'паспорт клиента', 'фотография клиента'],
    'C1-EXT': ['тип продукта', 'паспорт клиента', 'фотография клиента', 'действующий KITAS/ITK'],
    'D12': ['тип продукта', 'паспорт клиента', 'фотография клиента', 'справка банка (3 месяца)'],
    'E33G-NEW': ['тип продукта', 'профессия клиента', 'паспорт клиента', 'фотография клиента',
                 'справка банка (12 месяцев)', 'организация-работодатель вне Индонезии'],
    'E33G-EXT': ['тип продукта', 'паспорт клиента', 'фотография клиента',
                 'действующий KITAS/ITK', 'справка банка (3 месяца)'],
}

MINIMUM = ['Загранпаспорт клиента', 'Фотография клиента', 'Адрес проживания (документ или карточка)']


def main() -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    prods = con.execute('SELECT id, code, name FROM products WHERE active=1 ORDER BY code').fetchall()
    out = {'minimum': MINIMUM, 'products': {}}
    md = ['# Документы клиента по продуктам и переменные из них', '',
          '**Минимум для любой заявки:** %s.' % ', '.join(MINIMUM),
          'Справка банка обязательна: 12 месяцев — для нового E33G, 3 месяца — для C1, продления и D12.',
          '', 'Правило приоритета: **документ клиента сильнее карточки** — при расхождении берём '
          'значение из документа. Данные, которых нет нигде, поле остаётся пустым (не выдумываем).', '']
    for p in prods:
        tpls = con.execute("""SELECT t.id, t.code, t.title FROM product_documents pd
                              JOIN templates t ON t.id=pd.template_id
                              WHERE pd.product_id=? ORDER BY COALESCE(t.doc_index,999)""", (p['id'],)).fetchall()
        tpl_names = {t['code']: (t['title'] or t['code']) for t in tpls}
        per_doc = {}
        for label, need, detail, pat in DOC_VARS:
            rx = re.compile(pat)
            found = {}
            for t in tpls:
                for v in con.execute("""SELECT name, method, rule_text FROM template_variables
                                        WHERE template_id=? AND method='client_doc'""", (t['id'],)):
                    if rx.match(v['name']):
                        found.setdefault(v['name'], []).append(tpl_names[t['code']])
            if found:
                per_doc[label] = {'need': need, 'detail': detail,
                                  'variables': {k: sorted(set(v)) for k, v in sorted(found.items())}}
        out['products'][p['code']] = {'name': p['name'], 'documents': per_doc,
                                      'stop_keys': STOP_KEYS.get(p['code'], [])}
        md += ['## %s — %s' % (p['code'], p['name'] or ''), '',
               '**Обязательно от клиента:** %s.' % ', '.join(MINIMUM),
               '**Стоп, если нет:** %s.' % ', '.join(STOP_KEYS.get(p['code'], [])), '']
        for label, d in per_doc.items():
            md.append('- **%s** (%s) — %s' % (label, d['need'], d['detail']))
            for v, where in list(d['variables'].items())[:12]:
                md.append('  - `%s` → %s' % (v, ', '.join(where)))
            if len(d['variables']) > 12:
                md.append('  - … ещё переменных: %d' % (len(d['variables']) - 12))
        md.append('')
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('матрица:', OUT_JSON)
    for code, d in out['products'].items():
        nv = sum(len(x['variables']) for x in d['documents'].values())
        print('   %-9s документов клиента: %d, переменных из них: %d' % (code, len(d['documents']), nv))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
