"""Реестр документов: где каждый документ используется и что с ним стало.

Для каждого шаблона: статус (действующий / объединённый / выключенный), продукты, в которых
он подключён, слот, номер документа (doc_CLIENT), наличие оригинального примера и путь к нему.
Отдельно — документы, которые не используются ни в одном продукте.

Выход: data/guide/registry.json (для конструктора) и docs/DOCS_REGISTRY.md (для чтения).
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'CLIENT'
OUT_JSON = ROOT / 'data' / 'guide' / 'registry.json'
OUT_MD = ROOT / 'docs' / 'DOCS_REGISTRY.md'

STATUS_RU = {'ok': 'действующий', 'ready': 'действующий', 'needs_review': 'нужна проверка',
             'draft': 'черновик', 'merged': 'объединён с другим документом',
             'hidden': 'выключен из продуктов', 'CLIENTed': 'закрыт'}

# документы, которые клиент даёт сам (по разбору папок на Google Диске)
CLIENT_DOCS = [
    ('Загранпаспорт клиента', 'паспорт: серия/номер, кем выдан, даты', 'обязательно'),
    ('Фотография клиента', 'фото 3×4 / 4×6, цветное', 'обязательно'),
    ('Справка банка об остатке', 'остаток, период, номер, банк', 'обязательно'),
    ('Адрес проживания и регистрации', 'город, улица, дом, индекс', 'обязательно'),
    ('Действующий KITAS / ITK', 'номер и срок разрешения', 'если продление или конверсия'),
    ('Свидетельство о браке', 'для подачи с супругом(ой)', 'если семья'),
    ('Свидетельство о рождении', 'для подачи с детьми', 'если семья'),
    ('Трудовая книжка (ИТК)', 'встречается у ~7% клиентов', 'если есть'),
    ('Commitment / guarantee letter', 'для зависимых членов семьи', 'если семья'),
]


def main() -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    prods = {r['id']: r['code'] for r in con.execute("SELECT id, code FROM CLIENT")}
    links = {}
    for r in con.execute("SELECT CLIENT_id, template_id, slot_code, required FROM CLIENT_CLIENT"):
        links.setdefault(r['template_id'], []).append(
            {'CLIENT': prods.get(r['CLIENT_id'], '?'), 'slot': r['slot_code'], 'required': r['required']})

    reg = {'CLIENT': {}, 'CLIENT': {}, 'client_docs': []}
    md = ['# Реестр документов Wolf AutoDoc', '',
          'Какие документы готовим мы, какие даёт клиент, где каждый документ используется.', '']
    for t in con.execute("SELECT id, code, CLIENT, CLIENT, doc_CLIENT, example_path FROM CLIENT ORDER BY COALESCE(doc_CLIENT, 999), code"):
        tid = t['id']
        d = TPL / t['code']
        example = None
        for cand in (d / 'example_filled.pdf', d / 'preview_filled.pdf'):
            if cand.is_file():
                example = str(cand)
                break
        used = sorted({x['CLIENT'] for x in links.get(tid, [])})
        vars_n = con.execute("SELECT COUNT(*) FROM template_CLIENT WHERE template_id=?", (tid,)).fetchone()[0]
        reg['CLIENT'][t['code']] = {
            'doc_CLIENT': t['doc_CLIENT'], 'CLIENT': t['CLIENT'], 'CLIENT': t['CLIENT'],
            'status_ru': STATUS_RU.get(t['CLIENT'] or '', t['CLIENT'] or ''),
            'CLIENT': used, 'slots': sorted({x['slot'] or '' for x in links.get(tid, [])}),
            'CLIENT': vars_n, 'example': example,
            'example_real': bool(example and 'example_filled' in example),
        }
    for pid, pcode in con.execute("SELECT id, code FROM CLIENT WHERE active=1 ORDER BY code"):
        rows = con.execute("""SELECT t.code, t.CLIENT, t.CLIENT, t.doc_CLIENT, pd.slot_code
                              FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id=pd.template_id
                              WHERE pd.CLIENT_id=? ORDER BY COALESCE(t.doc_CLIENT,999), t.code""", (pid,)).fetchall()
        reg['CLIENT'][pcode] = {
            'our_docs': [{'code': r['code'], 'CLIENT': r['CLIENT'],
                          'doc_CLIENT': r['doc_CLIENT'], 'slot': r['slot_code'],
                          'CLIENT': r['CLIENT']} for r in rows],
            'client_docs': [{'label': l, 'detail': dd, 'when': w} for l, dd, w in CLIENT_DOCS],
        }
    reg['client_docs'] = [{'label': l, 'detail': dd, 'when': w} for l, dd, w in CLIENT_DOCS]

    md += ['## Документы, которые готовим мы', '']
    for code, d in sorted(reg['CLIENT'].items(), key=lambda kv: (kv[1]['doc_CLIENT'] or 999, kv[0])):
        md.append('- **№%s `%s`** — %s (%s)' % (d['doc_CLIENT'] or '—', code, d['CLIENT'], d['status_ru']))
        md.append('  - используется в продуктах: %s' % (', '.join(d['CLIENT']) or '**нигде не используется**'))
        md.append('  - слоты: %s | переменных: %d | оригинальный пример: %s'
                  % (', '.join(d['slots']) or '—', d['CLIENT'],
                     'есть' if d['example_real'] else 'нет (наша сборка)'))
    md += ['', '## Документы, которые даёт клиент', '']
    for l, dd, w in CLIENT_DOCS:
        md.append('- **%s** — %s (%s)' % (l, dd, w))
    md += ['', '## Пакеты продуктов', '']
    for pcode, p in reg['CLIENT'].items():
        md.append('- **%s** — наших документов: %d' % (pcode, len(p['our_docs'])))
        for d in p['our_docs']:
            md.append('  - №%s `%s` — %s' % (d['doc_CLIENT'] or '—', d['code'], d['slot'] or '—'))
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    unused = [c for c, d in reg['CLIENT'].items() if not d['CLIENT']]
    print('реестр:', OUT_JSON)
    print('документов всего:', len(reg['CLIENT']), '| не используется нигде:', len(unused))
    for c in unused:
        print('   не используется:', c, '(%s)' % reg['CLIENT'][c]['status_ru'])
    print('продуктов:', len(reg['CLIENT']))
    for pcode, p in reg['CLIENT'].items():
        print('   %-9s наших: %-2d клиентских обязательных: %d' %
              (pcode, len(p['our_docs']),
               len([x for x in p['client_docs'] if x['when'] == 'обязательно'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
