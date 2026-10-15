#!/usr/bin/env python3
"""Пробная генерация документов с подсветкой полей.

Цвета:
  зелёный  — значение взято из карточки клиента (точные данные клиента);
  жёлтый   — значение взято из архива/памяти системы (предположение, стоит проверить);
  красный  — система не знает, чем заполнить (пустое поле).

Результат: готовые PDF в reports/preview_highlight/ + отчёт, какие поля в каком состоянии.

Запуск: /usr/bin/python3 scripts/preview_highlight.py --app 66
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from core import db  # noqa: E402
from services import render as doc_render  # noqa: E402
from services import values as values_service  # noqa: E402

OUT = BASE / 'reports' / 'preview_highlight'
OUT.mkdir(parents=True, exist_ok=True)

STYLE = {
    'own': 'background:#c9f2c0;border-bottom:1px solid #3f8f3f;',        # из карточки клиента
    'archive': 'background:#ffe9a8;border-bottom:1px solid #b58a00;',    # из архива/памяти
    'empty': 'background:#ffc9c9;border-bottom:1px solid #c0392b;color:#8b1a1a;font-weight:bold;',
}

VAR_RE = re.compile(r'\{\{\s*([a-zA-Z_]\w*)\s*\}\}')
OPT_RE = re.compile(r'<!--optional-->(.*?)<!--/optional-->', re.S)


def classify(app_id: int, client: dict, code: str, vals: dict) -> dict:
    """Откуда взялось каждое значение: из карточки клиента или из архива."""
    own = {}
    for k, v in (db.q1('SELECT * FROM clients WHERE id=?', (client['id'],)) or {}).items():
        if v not in (None, ''):
            own[str(k)] = str(v)
    # значения, сохранённые в документе заявки, и архив считаем «памятью»
    result = {}
    for name, value in vals.items():
        if value in (None, ''):
            result[name] = 'empty'
            continue
        marker = 'archive'
        sval = str(value)
        for k, ov in own.items():
            if sval and (sval.lower() in ov.lower() or ov.lower() in sval.lower()) and len(sval) > 2:
                marker = 'own'
                break
        result[name] = marker
    return result


def highlight(html: str, vals: dict, kinds: dict) -> tuple:
    stats = {'own': 0, 'archive': 0, 'empty': 0}

    def repl(m):
        name = m.group(1)
        value = vals.get(name)
        if value in (None, ''):
            stats['empty'] += 1
            return f'<span style="{STYLE["empty"]}">[не заполнено: {html_mod.escape(name)}]</span>'
        kind = kinds.get(name, 'archive')
        stats[kind] = stats.get(kind, 0) + 1
        return f'<span style="{STYLE[kind]}">{html_mod.escape(str(value))}</span>'

    # необязательные строки: если все значения пусты — строку убираем
    def drop(m):
        body = m.group(1)
        names = VAR_RE.findall(body)
        if names and all(not str(vals.get(n) or '').strip() for n in names):
            return ''
        return body

    html = OPT_RE.sub(drop, html)
    return VAR_RE.sub(repl, html), stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--app', type=int, required=True)
    ap.add_argument('--only', help='только один шаблон (код)')
    args = ap.parse_args()

    app = db.q1('SELECT * FROM applications WHERE id=?', (args.app,))
    client = dict(db.q1('SELECT * FROM clients WHERE id=?', (app['client_id'],)) or {})
    tpls = db.q('''SELECT t.* FROM product_documents pd JOIN templates t ON t.id=pd.template_id
                   WHERE pd.product_id=? ORDER BY pd.sort_order, t.id''', (app['product_id'],))
    if args.only:
        tpls = [t for t in tpls if dict(t)['code'] == args.only]

    files, all_stats = [], {}
    for t in tpls:
        t = dict(t)
        tpl = doc_render.load_template(t['id'])
        vals = values_service.build_template_values(client, t['code'])
        vals.update({k: v for k, v in (doc_render.stored_values(args.app, t['id']) or {}).items()
                     if v and not vals.get(k)})
        kinds = classify(args.app, client, t['code'], vals)
        html, stats = highlight(tpl['_html'], vals, kinds)
        all_stats[t['code']] = stats
        out = OUT / f"app{args.app}_{t['code']}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        try:
            doc_render.render_pdf(html, base_dir=tpl['_dir'], out_path=out)
            files.append((t['code'], str(out), out.stat().st_size // 1024))
        except Exception as e:  # noqa: BLE001
            files.append((t['code'], f'ошибка: {str(e)[:80]}', 0))

    print(f'клиент: {client.get("surname", "")} {client.get("name", "")} · заявка {args.app}')
    for code, path, kb in files:
        s = all_stats.get(code, {})
        print(f'  {code:34} {kb:>5} КБ  из карточки: {s.get("own", 0):>3}  из архива: {s.get("archive", 0):>3}  '
              f'не заполнено: {s.get("empty", 0):>3}')
    (BASE / 'reports' / f'highlight_app{args.app}.json').write_text(
        json.dumps({'files': files, 'stats': all_stats}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\nфайлы:')
    for code, path, _ in files:
        print(f'  {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
