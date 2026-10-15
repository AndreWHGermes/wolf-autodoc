#!/usr/bin/env python3
"""Самопроверка документов Wolf AutoDoc: система сама генерирует и сама оценивает результат.

Что делает по каждой заявке:
  1) берёт пакет документов продукта (product_documents) и шаблоны;
  2) собирает значения (карточка клиента + сохранённые значения + архив);
  3) формирует HTML и PDF каждого документа;
  4) проверяет: какие переменные остались незаполненными, нет ли русского текста
     в англоязычном документе, нет ли подозрения на данные другого клиента;
  5) пишет отчёт (для человека — .md, для машины — .json).

Запуск:
  /usr/bin/python3 scripts/selfcheck.py --app 66
  /usr/bin/python3 scripts/selfcheck.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from core import db  # noqa: E402
from services import render as doc_render  # noqa: E402
from services import values as values_service  # noqa: E402

CYR = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
REPORTS = BASE / 'reports'
REPORTS.mkdir(exist_ok=True)

# Поля, которые обязаны браться из карточки клиента.
# Значение переменной сравниваем с её источниками в карточке (с учётом транслита):
# если источник заполнен — значит это свои данные, а не чужие.
PERSONAL = {
    'passport_number': ['passport_number', 'passport_no', 'passport'],
    'passport_no': ['passport_number', 'passport_no', 'passport'],
    'surname': ['surname'],
    'name': ['name'],
    'patronymic': ['patronymic'],
    'full_name_latin': ['full_name_latin', 'surname', 'name'],
    'birth_date': ['birth_date'],
    'account_no': ['account_no'],
    'balance_rub': ['balance_rub'],
    'card_mask': ['card_mask'],
    'contract_no': ['contract_no'],
    'doc_no': ['doc_no'],
    'client_address': ['client_address', 'address_reg', 'address_live', 'address_registration'],
    'address_registration': ['address_registration', 'address_reg', 'address_live'],
}


def own_value(client: dict, sources: list) -> str:
    for s in sources:
        v = str(client.get(s) or '').strip()
        if v:
            return v
    return ''


def cyr_words(text: str) -> list:
    return [c for c in text if c.lower() in CYR]


def check_document(app_id: int, client: dict, tpl: dict, stored: dict) -> dict:
    code = tpl['code']
    res = {'template': code, 'template_id': tpl['id'], 'status': 'ok',
           'unfilled': [], 'cyrillic': 0, 'pdf': '', 'pdf_kb': 0, 'suspicious': []}
    try:
        vals = values_service.build_template_values(client, code, doc_values=stored)
        vals.update({k: v for k, v in (stored or {}).items() if v and k not in vals})
        html = doc_render.fill(tpl['_html'], vals, keep_unfilled=False)
        left = doc_render.unfilled(html)
        res['unfilled'] = left
        res['cyrillic'] = len(cyr_words(html))
        # подозрение: личное поле заполнено, но в карточке клиента его нет ни в одном источнике
        for field, sources in PERSONAL.items():
            got = (vals.get(field) or '').strip()
            if got and not own_value(client, sources):
                res['suspicious'].append(f'{field}={got[:28]}')
        out = REPORTS / 'pdf' / f'app{app_id}_{code}_{datetime.now():%Y%m%d_%H%M%S}.pdf'
        out.parent.mkdir(parents=True, exist_ok=True)
        pdf = doc_render.render_pdf(html, base_dir=tpl['_dir'], out_path=out)
        res['pdf'] = str(pdf)
        res['pdf_kb'] = round(Path(pdf).stat().st_size / 1024, 1)
        if res['cyrillic']:
            res['status'] = 'внимание'
        if res['unfilled'] or res['suspicious']:
            res['status'] = 'требует заполнения'
        if res['pdf_kb'] < 5:
            res['status'] = 'ошибка'
            res['suspicious'].append('PDF подозрительно мал')
    except Exception as e:  # noqa: BLE001
        res['status'] = 'ошибка'
        res['error'] = str(e)[:200]
    return res


def check_application(app_id: int) -> dict:
    app = db.q1('SELECT * FROM applications WHERE id=?', (app_id,))
    if not app:
        return {'application': app_id, 'error': 'заявка не найдена'}
    client = dict(db.q1('SELECT * FROM clients WHERE id=?', (app['client_id'],)) or {})
    product = db.q1('SELECT * FROM products WHERE id=?', (app['product_id'],)) or {}
    tpls = db.q('''SELECT t.* FROM product_documents pd JOIN templates t ON t.id = pd.template_id
                   WHERE pd.product_id=? ORDER BY pd.sort_order, t.id''', (app['product_id'],))
    docs = []
    for t in tpls:
        t = dict(t)
        try:
            tpl = doc_render.load_template(t['id'])
        except Exception as e:  # noqa: BLE001
            docs.append({'template': t['code'], 'status': 'ошибка', 'error': str(e)[:120]})
            continue
        stored = doc_render.stored_values(app_id, t['id'])
        docs.append(check_document(app_id, client, tpl, stored))
    done = [d for d in docs if d.get('status') == 'ok']
    total_empty = sum(len(d.get('unfilled') or []) for d in docs)
    return {'application': app_id, 'client': f"{client.get('surname', '')} {client.get('name', '')}".strip(),
            'product': product.get('code') or '—', 'documents': docs,
            'summary': {'documents': len(docs), 'ok': len(done), 'empty_fields': total_empty,
                        'with_cyrillic': len([d for d in docs if d.get('cyrillic')]),
                        'suspicious': len([d for d in docs if d.get('suspicious')])}}


def to_markdown(rep: dict) -> str:
    lines = [f"# Самопроверка документов — заявка {rep.get('application')}",
             f"Клиент: {rep.get('client')} · Продукт: {rep.get('product')}",
             f"Дата проверки: {datetime.now():%d.%m.%Y %H:%M}", '']
    s = rep.get('summary', {})
    lines += [f"**Итог:** документов {s.get('documents', 0)}, без замечаний {s.get('ok', 0)}, "
              f"незаполненных полей {s.get('empty_fields', 0)}, документов с русским текстом {s.get('with_cyrillic', 0)}, "
              f"с подозрением на чужие данные {s.get('suspicious', 0)}", '']
    for d in rep.get('documents', []):
        mark = {'ok': '✅', 'внимание': '⚠️', 'требует заполнения': '📝', 'ошибка': '❌'}.get(d.get('status'), '•')
        lines.append(f"## {mark} {d.get('template')} — {d.get('status')}")
        if d.get('error'):
            lines.append(f"Ошибка: {d['error']}")
        if d.get('pdf_kb'):
            lines.append(f"PDF: {d['pdf_kb']} КБ")
        if d.get('unfilled'):
            lines.append('Незаполненные переменные: ' + ', '.join(d['unfilled'][:30]))
        if d.get('suspicious'):
            lines.append('Подозрительные значения (нет в карточке клиента): ' + ', '.join(d['suspicious'][:10]))
        lines.append('')
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--app', type=int, help='номер заявки')
    ap.add_argument('--all', action='store_true', help='проверить все заявки')
    args = ap.parse_args()

    if args.all:
        ids = [r['id'] for r in db.q('SELECT id FROM applications ORDER BY id')]
    elif args.app:
        ids = [args.app]
    else:
        ap.error('укажите --app <id> или --all')

    reports = [check_application(i) for i in ids]
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    (REPORTS / f'selfcheck_{stamp}.json').write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    md = '\n\n---\n\n'.join(to_markdown(r) for r in reports if 'summary' in r)
    (REPORTS / f'selfcheck_{stamp}.md').write_text(md, encoding='utf-8')

    print(f'проверено заявок: {len(reports)}')
    for r in reports:
        s = r.get('summary')
        if s:
            print(f"  заявка {r['application']} ({r.get('client', '')[:24]}): документов {s['documents']}, "
                  f"без замечаний {s['ok']}, пустых полей {s['empty_fields']}, "
                  f"с русским текстом {s['with_cyrillic']}, подозрительных {s['suspicious']}")
    print(f'отчёт: {REPORTS}/selfcheck_{stamp}.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
