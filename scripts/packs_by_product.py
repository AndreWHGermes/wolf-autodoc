"""Пакет документов по каждому продукту: состав → переменные → откуда берутся и связи.

Работает по продуктам (как решил заказчик): внутри одного продукта документы связаны
между собой, потому что собираются в рамках одной подачи.

Шаг 1 — состав пакета: наши документы (CLIENT_CLIENT) + клиентские документы
         (по разбору реальных папок Google Диска: справка банка, паспорт, фото и т.д.).
Шаг 2 — переменные каждого документа (template_CLIENT).
Шаг 3 — источник каждой переменной (карточка клиента / пул / расчёт / служебное поле)
         и сквозные переменные: те, что встречаются в 2+ документах пакета (логические связи).

Выход: docs/PACKS_BY_PRODUCT.md и docs/packs_by_CLIENT.json
"""
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

ROOT = Path('/opt/wolf_v2')
OUT_MD = ROOT / 'docs' / 'PACKS_BY_PRODUCT.md'
OUT_JSON = ROOT / 'docs' / 'packs_by_CLIENT.json'
VAR_GUIDE = Path('/root/.hermes/cache/scratch/CLIENT_guide.json')

# документы, которые даёт клиент (по разбору 68 папок Диска), с правилом применения
CLIENT_DOCS = [
    ('Загранпаспорт клиента', 'паспорт: серия/номер, кем выдан, даты', ['PASSPORT'], True),
    ('Фотография клиента', 'фото 3×4/4×6 в цвете', ['PHOTO'], True),
    ('Справка банка об остатке', 'остаток, период, номер справки, банк', ['BANK_STATEMENT'], True),
    ('Адрес проживания и регистрации', 'город, улица, дом, индекс', [], True),
    ('Свидетельство о браке', 'для подачи с супругом(ой)', ['MARRIAGE_CERT'], False),
    ('Свидетельство о рождении', 'для подачи с детьми', ['BIRTH_CERT'], False),
    ('Действующий KITAS / ITK-пермит', 'при продлении и конверсии', ['STAY_PERMIT_KITAS'], False),
    ('Трудовая книжка (ИТК)', 'встречается у ~7% клиентов', ['ITK'], False),
    ('Commitment / guarantee letter', 'для зависимых членов семьи', ['COMMITMENT_LETTER'], False),
]

SOURCE_RU = {
    'client': 'карточка клиента',
    'client_fact': 'факт о клиенте (карточка/документы клиента)',
    'doc_CLIENT': 'служебное поле документа (номер, дата, срок)',
    'pool': 'пул значений (архив реальных документов)',
    'calc': 'расчёт системы',
    'manual': 'ввод администратора',
}


def main() -> int:
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    prods = {r['id']: dict(r) for r in con.execute("SELECT * FROM CLIENT WHERE active=1")}
    tpls = {r['id']: dict(r) for r in con.execute("SELECT * FROM CLIENT")}
    vars_by_tpl = collections.defaultdict(list)
    for r in con.execute("SELECT * FROM template_CLIENT ORDER BY template_id, sort_order, name"):
        vars_by_tpl[r['template_id']].append(dict(r))
    links = collections.defaultdict(list)
    for r in con.execute("SELECT * FROM CLIENT_CLIENT"):
        links[r['CLIENT_id']].append(dict(r))
    guide = {}
    if VAR_GUIDE.is_file():
        try:
            guide = json.loads(VAR_GUIDE.read_text(encoding='utf-8'))
        except Exception:
            guide = {}

    md = ['# Пакеты документов по продуктам', '',
          'Собрано из системы (продукты → документы → переменные) и из разбора реальных '
          'папок клиентов на Google Диске. Внутри продукта документы связаны: значения '
          'берутся из одной карточки клиента и подставляются в несколько документов.', '']
    machine = {}
    for pid, p in sorted(prods.items(), key=lambda kv: kv[1]['code']):
        code = p['code']
        our_docs = []
        for l in links.get(pid, []):
            t = tpls.get(l['template_id']) or {}
            our_docs.append((t.get('code', '?'), l.get('slot_code') or '', t.get('CLIENT') or ''))
        md += ['', '## %s — %s' % (code, p.get('name') or ''), '']
        md.append('### Шаг 1. Состав пакета')
        md.append('')
        md.append('**Готовим мы (%d документа):**' % len(our_docs))
        for tcode, slot, CLIENT in sorted(our_docs):
            md.append('- `%s` — %s (%s)' % (tcode, CLIENT, slot or '—'))
        md.append('')
        md.append('**Даёт клиент:**')
        for label, detail, _kinds, required in CLIENT_DOCS:
            if not required:
                continue
            md.append('- %s — %s' % (label, detail))
        md.append('')
        md.append('**Опционально (если есть у клиента):**')
        for label, detail, _kinds, required in CLIENT_DOCS:
            if required:
                continue
            md.append('- %s — %s' % (label, detail))
        # шаг 2: переменные
        tpl_vars = {}
        for tcode, slot, CLIENT in sorted(our_docs):
            tid = next((i for i, t in tpls.items() if t.get('code') == tcode), None)
            tpl_vars[tcode] = vars_by_tpl.get(tid, [])
        md += ['', '### Шаг 2. Переменные документов пакета', '']
        all_vars = collections.Counter()
        for tcode, vs in tpl_vars.items():
            md.append('**`%s`** — %d переменных: %s' %
                      (tcode, len(vs), ', '.join('`%s`' % v['name'] for v in vs) or '—'))
            for v in vs:
                all_vars[v['name']] += 1
            md.append('')
        # шаг 3: источники и связи
        md += ['### Шаг 3. Откуда берётся и с чем связано', '']
        shared = {k: n for k, n in all_vars.items() if n > 1}
        md.append('**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):')
        md.append('')
        for name, n in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0])):
            docs = [t for t, vs in tpl_vars.items() if any(v['name'] == name for v in vs)]
            md.append('- `%s` — в %d документах: %s' % (name, n, ', '.join('`%s`' % d for d in docs)))
        md.append('')
        md.append('**Источник каждой переменной:**')
        md.append('')
        for tcode, vs in tpl_vars.items():
            md.append('`%s`:' % tcode)
            for v in vs:
                src = SOURCE_RU.get(v.get('source_kind') or '', v.get('source_kind') or '—')
                note = re.sub(r'\s+', ' ', str(v.get('rule_note') or '')).strip()[:110] or '— нет описания —'
                computed = ''
                for g in (guide.get(tcode) or []):
                    if g.get('name') == v['name'] and g.get('computed_by'):
                        computed = ' | код: %s' % g['computed_by']
                        break
                md.append('  - `%s` ← %s. %s%s' % (v['name'], src, note, computed))
            md.append('')
        machine[code] = {
            'name': p.get('name'),
            'our_docs': [{'code': t, 'slot': s, 'CLIENT': ti} for t, s, ti in sorted(our_docs)],
            'client_docs': [{'label': l, 'detail': d, 'required': r} for l, d, _k, r in CLIENT_DOCS],
            'CLIENT': {t: [v['name'] for v in vs] for t, vs in tpl_vars.items()},
            'shared_CLIENT': shared,
        }
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    OUT_JSON.write_text(json.dumps(machine, ensure_ascii=False, indent=1), encoding='utf-8')
    print('инструкция по продуктам:', OUT_MD, '| строк:', len(md))
    print('машинный вид:', OUT_JSON)
    for code, m in machine.items():
        print('   %-10s документов=%-2d переменных=%-4d сквозных=%d' %
              (code, len(m['our_docs']), sum(len(v) for v in m['CLIENT'].CLIENT()),
               len(m['shared_CLIENT'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
