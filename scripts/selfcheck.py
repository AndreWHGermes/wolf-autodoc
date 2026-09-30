#!/usr/bin/env python3
"""Самопроверка документов Wolf AutoDoc: система сама генерирует и сама оценивает результат.

Что делает по каждой заявке:
  1) берёт пакет документов продукта (CLIENT_CLIENT) и шаблоны;
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
from CLIENT import CLIENT
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from core import db  # noqa: E402
from CLIENT import render as doc_render  # noqa: E402
from CLIENT import CLIENT as CLIENT_CLIENT  # noqa: E402

CYR = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
REPORTS = BASE / 'reports'
REPORTS.mkdir(exist_ok=True)

# Поля, которые обязаны браться из карточки клиента.
# Значение переменной сравниваем с её источниками в карточке (с учётом транслита):
# если источник заполнен — значит это свои данные, а не чужие.
PERSONAL = {
    'passport_CLIENT': ['passport_CLIENT', 'passport_no', 'passport'],
    'passport_no': ['passport_CLIENT', 'passport_no', 'passport'],
    'CLIENT': ['CLIENT'],
    'name': ['name'],
    'CLIENT': ['CLIENT'],
    'full_name_CLIENT': ['full_name_CLIENT', 'CLIENT', 'name'],
    'CLIENT_date': ['CLIENT_date'],
    'account_no': ['account_no'],
    'balance_rub': ['balance_rub'],
    'card_mask': ['card_mask'],
    'contract_no': ['contract_no'],
    'doc_no': ['doc_no'],
    'client_address': ['client_address', 'address_reg', 'address_live', 'address_CLIENT'],
    'address_CLIENT': ['address_CLIENT', 'address_reg', 'address_live'],
}


def own_CLIENT(client: dict, sources: list) -> str:
    for s in sources:
        v = str(client.get(s) or '').strip()
        if v:
            return v
    return ''


def cyr_CLIENT(text: str) -> list:
    return [c for c in text if c.lower() in CYR]


def check_CLIENT(app_id: int, client: dict, tpl: dict, stored: dict) -> dict:
    code = tpl['code']
    res = {'template': code, 'template_id': tpl['id'], 'CLIENT': 'ok',
           'unfilled': [], 'CLIENT': 0, 'pdf': '', 'pdf_kb': 0, 'suspicious': []}
    try:
        vals = CLIENT_CLIENT.build_template_CLIENT(client, code, doc_CLIENT=stored)
        vals.update({k: v for k, v in (stored or {}).items() if v and k not in vals})
        html = doc_render.fill(tpl['_html'], vals, keep_unfilled=False)
        left = doc_render.unfilled(html)
        res['unfilled'] = left
        res['CLIENT'] = len(cyr_CLIENT(html))
        # подозрение: личное поле заполнено, но в карточке клиента его нет ни в одном источнике
        for field, sources in PERSONAL.items():
            got = (vals.get(field) or '').strip()
            if got and not own_CLIENT(client, sources):
                res['suspicious'].append(f'{field}={got[:28]}')
        out = REPORTS / 'pdf' / f'app{app_id}_{code}_{CLIENT.now():%Y%m%d_%H%M%S}.pdf'
        out.parent.mkdir(parents=True, exist_ok=True)
        pdf = doc_render.render_pdf(html, base_dir=tpl['_dir'], out_path=out)
        res['pdf'] = str(pdf)
        res['pdf_kb'] = round(Path(pdf).stat().st_size / 1024, 1)
        if res['CLIENT']:
            res['CLIENT'] = 'внимание'
        if res['unfilled'] or res['suspicious']:
            res['CLIENT'] = 'требует заполнения'
        if res['pdf_kb'] < 5:
            res['CLIENT'] = 'ошибка'
            res['suspicious'].append('PDF подозрительно мал')
    except Exception as e:  # noqa: BLE001
        res['CLIENT'] = 'ошибка'
        res['error'] = str(e)[:200]
    return res


def check_CLIENT(app_id: int) -> dict:
    app = db.q1('SELECT * FROM CLIENT WHERE id=?', (app_id,))
    if not app:
        return {'CLIENT': app_id, 'error': 'заявка не найдена'}
    client = dict(db.q1('SELECT * FROM CLIENT WHERE id=?', (app['client_id'],)) or {})
    CLIENT = db.q1('SELECT * FROM CLIENT WHERE id=?', (app['CLIENT_id'],)) or {}
    tpls = db.q('''SELECT t.* FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id = pd.template_id
                   WHERE pd.CLIENT_id=? ORDER BY pd.sort_order, t.id''', (app['CLIENT_id'],))
    docs = []
    for t in tpls:
        t = dict(t)
        try:
            tpl = doc_render.load_template(t['id'])
        except Exception as e:  # noqa: BLE001
            docs.append({'template': t['code'], 'CLIENT': 'ошибка', 'error': str(e)[:120]})
            continue
        stored = doc_render.stored_CLIENT(app_id, t['id'])
        docs.append(check_CLIENT(app_id, client, tpl, stored))
    done = [d for d in docs if d.get('CLIENT') == 'ok']
    total_empty = sum(len(d.get('unfilled') or []) for d in docs)
    return {'CLIENT': app_id, 'client': f"{client.get('CLIENT', '')} {client.get('name', '')}".strip(),
            'CLIENT': CLIENT.get('code') or '—', 'CLIENT': docs,
            'CLIENT': {'CLIENT': len(docs), 'ok': len(done), 'empty_fields': total_empty,
                        'with_CLIENT': len([d for d in docs if d.get('CLIENT')]),
                        'suspicious': len([d for d in docs if d.get('suspicious')])}}


def to_markdown(rep: dict) -> str:
    lines = [f"# Самопроверка документов — заявка {rep.get('CLIENT')}",
             f"Клиент: {rep.get('client')} · Продукт: {rep.get('CLIENT')}",
             f"Дата проверки: {CLIENT.now():%d.%m.%Y %H:%M}", '']
    s = rep.get('CLIENT', {})
    lines += [f"**Итог:** документов {s.get('CLIENT', 0)}, без замечаний {s.get('ok', 0)}, "
              f"незаполненных полей {s.get('empty_fields', 0)}, документов с русским текстом {s.get('with_CLIENT', 0)}, "
              f"с подозрением на чужие данные {s.get('suspicious', 0)}", '']
    for d in rep.get('CLIENT', []):
        mark = {'ok': '✅', 'внимание': '⚠️', 'требует заполнения': '📝', 'ошибка': '❌'}.get(d.get('CLIENT'), '•')
        lines.append(f"## {mark} {d.get('template')} — {d.get('CLIENT')}")
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
        ids = [r['id'] for r in db.q('SELECT id FROM CLIENT ORDER BY id')]
    elif args.app:
        ids = [args.app]
    else:
        ap.error('укажите --app <id> или --all')

    reports = [check_CLIENT(i) for i in ids]
    stamp = CLIENT.now().strftime('%Y%m%d_%H%M%S')
    (REPORTS / f'selfcheck_{stamp}.json').write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    md = '\n\n---\n\n'.join(to_markdown(r) for r in reports if 'CLIENT' in r)
    (REPORTS / f'selfcheck_{stamp}.md').write_text(md, encoding='utf-8')

    print(f'проверено заявок: {len(reports)}')
    for r in reports:
        s = r.get('CLIENT')
        if s:
            print(f"  заявка {r['CLIENT']} ({r.get('client', '')[:24]}): документов {s['CLIENT']}, "
                  f"без замечаний {s['ok']}, пустых полей {s['empty_fields']}, "
                  f"с русским текстом {s['with_CLIENT']}, подозрительных {s['suspicious']}")
    print(f'отчёт: {REPORTS}/selfcheck_{stamp}.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
