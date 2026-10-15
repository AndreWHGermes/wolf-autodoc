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
     r'^(passport_|passport|date_of_CLIENT|CLIENT_date|CLIENT_CLIENT|CLIENT_of_CLIENT|CLIENT|'
     r'CLIENT|client_name|full_name|full_name_CLIENT|CLIENT_full_name|CLIENT_name|'
     r'CLIENT|sex|date_of_CLIENT|date_of_CLIENT)'),
    ('Фотография клиента', 'обязательно', 'цветное фото, вставляется в документы',
     r'^(client_photo|client_photo_url|photo)'),
    ('Справка банка об остатке', 'обязательно',
     'период по продукту: 12 месяцев — для нового E33G, 3 месяца — для C1, продления и D12',
     r'^(balance_|balance|account_|card_mask|bank_|CLIENT_|ref_no|doc_no|CLIENTment_)'),
    ('Адрес проживания (документ или карточка)', 'обязательно',
     'адрес в стране гражданства; отдельно — адрес пребывания в Индонезии',
     r'^(address_|client_address|city|postal|zip)'),
    ('Действующий KITAS / ITK', 'по ситуации',
     'нужен для продления (E33G-EXT, C1-EXT) и конверсии (CONV)',
     r'^(itk_|stay_CLIENT|kitas|CLIENT_)'),
    ('Свидетельство о браке / о рождении', 'по ситуации',
     'когда подача с супругом(ой) или детьми',
     r'^(spouse_|wife_|husband_|marriage_|child_|children_|family_)'),
    ('Commitment / guarantee letter', 'по ситуации',
     'для зависимых членов семьи — подписывает основной заявитель',
     r'^(CLIENT|commitment|CLIENT_)'),
    ('Трудовая книжка (ИТК)', 'если есть',
     'встречается редко; из неё берём профессию и стаж',
     r'^(CLIENT|position|job_|cv_job|employment_CLIENT|experience)'),
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
    prods = con.execute('SELECT id, code, name FROM CLIENT WHERE active=1 ORDER BY code').fetchall()
    out = {'minimum': MINIMUM, 'CLIENT': {}}
    md = ['# Документы клиента по продуктам и переменные из них', '',
          '**Минимум для любой заявки:** %s.' % ', '.join(MINIMUM),
          'Справка банка обязательна: 12 месяцев — для нового E33G, 3 месяца — для C1, продления и D12.',
          '', 'Правило приоритета: **документ клиента сильнее карточки** — при расхождении берём '
          'значение из документа. Данные, которых нет нигде, поле остаётся пустым (не выдумываем).', '']
    for p in prods:
        tpls = con.execute("""SELECT t.id, t.code, t.CLIENT FROM CLIENT_CLIENT pd
                              JOIN CLIENT t ON t.id=pd.template_id
                              WHERE pd.CLIENT_id=? ORDER BY COALESCE(t.doc_CLIENT,999)""", (p['id'],)).fetchall()
        tpl_names = {t['code']: (t['CLIENT'] or t['code']) for t in tpls}
        per_doc = {}
        for label, need, detail, pat in DOC_VARS:
            rx = re.compile(pat)
            found = {}
            for t in tpls:
                for v in con.execute("""SELECT name, method, rule_text FROM template_CLIENT
                                        WHERE template_id=? AND method='client_doc'""", (t['id'],)):
                    if rx.match(v['name']):
                        found.setdefault(v['name'], []).append(tpl_names[t['code']])
            if found:
                per_doc[label] = {'need': need, 'detail': detail,
                                  'CLIENT': {k: sorted(set(v)) for k, v in sorted(found.items())}}
        out['CLIENT'][p['code']] = {'name': p['name'], 'CLIENT': per_doc,
                                      'stop_keys': STOP_KEYS.get(p['code'], [])}
        md += ['## %s — %s' % (p['code'], p['name'] or ''), '',
               '**Обязательно от клиента:** %s.' % ', '.join(MINIMUM),
               '**Стоп, если нет:** %s.' % ', '.join(STOP_KEYS.get(p['code'], [])), '']
        for label, d in per_doc.items():
            md.append('- **%s** (%s) — %s' % (label, d['need'], d['detail']))
            for v, where in list(d['CLIENT'].items())[:12]:
                md.append('  - `%s` → %s' % (v, ', '.join(where)))
            if len(d['CLIENT']) > 12:
                md.append('  - … ещё переменных: %d' % (len(d['CLIENT']) - 12))
        md.append('')
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('матрица:', OUT_JSON)
    for code, d in out['CLIENT'].items():
        nv = sum(len(x['CLIENT']) for x in d['CLIENT'].CLIENT())
        print('   %-9s документов клиента: %d, переменных из них: %d' % (code, len(d['CLIENT']), nv))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
