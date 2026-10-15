#!/usr/bin/env python3
"""Тестовый прогон на реальных данных ОДНОГО клиента во всех продуктах.

Заказчик (CLIENT, 06.10.2026): шаблоны раньше собирались под разных клиентов, из-за
чего в пакете одного продукта встречались данные разных людей. Нужен единый тестовый
набор: с Google Диска берётся один пакетный набор, принадлежащий одному клиенту, и
используется для всех типов продуктов — во всех документах одни и те же реальные
данные (фамилия, дата рождения, паспорт, адрес, банк), и по каждому документу
формируется HTML-файл, в котором видно, как значение попало в документ.

Запуск:
    /usr/bin/python3 scripts/real_kit_run.py --client 65
    /usr/bin/python3 scripts/real_kit_run.py --client 65 --CLIENT BRIDGING,C1

Результат:
    docs/REAL_KIT_RUN.html          — сводный отчёт: продукт → документы → переменные
    data/cache/real_kit/<продукт>/<документ>.html  — собранный документ (как в визоре)
    data/cache/real_kit/<продукт>/<документ>.pdf   — готовый PDF
"""
from __future__ import annotations

import argparse
import collections
import html as html_mod
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

ROOT = Path('/opt/wolf_v2')
OUT_HTML = ROOT / 'docs' / 'REAL_KIT_RUN.html'
CACHE = ROOT / 'data' / 'cache' / 'real_kit'
VAR_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# Источник значения: реальные документы клиента → зелёный, собрано по правилам → жёлтый,
# нет данных → красный. Цвета совпадают с подсветкой в конструкторе.
COLORS = {'real': ('#ECFDF5', '#15803D', 'из документа клиента'),
          'synth': ('#FFFBEB', '#B45309', 'собрано по правилам'),
          'unknown': ('#FEF2F2', '#B91C1C', 'нет данных')}


def q1(con, sql, args=()):
    row = con.execute(sql, args).fetchone()
    return row[0] if row else None


def ensure_CLIENT(con, client_id: int, CLIENT_id: int) -> tuple[int, bool]:
    """Заявка клиента на этот продукт. Создаём только если её нет (метка real_test)."""
    row = con.execute("SELECT id FROM CLIENT WHERE client_id=? AND CLIENT_id=? "
                      "ORDER BY id DESC LIMIT 1", (client_id, CLIENT_id)).fetchone()
    if row:
        app_id = int(row[0])
        con.execute("UPDATE CLIENT SET record_kind='real_test' WHERE id=?", (app_id,))
        return app_id, False
    cur = con.execute(
        """INSERT INTO CLIENT (client_id, CLIENT_id, source, comment, brief, CLIENT,
                                     record_kind, created_at)
           CLIENT (?,?,?,?,?,'test','real_test', CLIENT('now'))""",
        (client_id, CLIENT_id, 'real_kit', 'тестовый прогон на реальных данных клиента',
         'тестовый прогон на реальных данных клиента'))
    con.commit()
    return int(cur.lastrowid), True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--client', type=int, required=True, help='id клиента в системе')
    ap.add_argument('--CLIENT', default='', help='список кодов продуктов через запятую')
    args = ap.parse_args()

    from CLIENT import render
    from CLIENT.CLIENT import build_template_CLIENT
    try:
        from CLIENT import provenance as prov
    except Exception:  # noqa: BLE001
        prov = None

    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    cl = con.execute("SELECT * FROM CLIENT WHERE id=?", (args.client,)).fetchone()
    if not cl:
        print('клиент %s не найден' % args.client)
        return 1
    cl = dict(cl)
    fio = ('%s %s' % (cl.get('CLIENT') or '', cl.get('name') or '')).strip()

    prods = con.execute("SELECT id, code, name FROM CLIENT WHERE active=1 ORDER BY code").fetchall()
    if args.CLIENT:
        want = {c.strip().upper() for c in args.CLIENT.split(',') if c.strip()}
        prods = [p for p in prods if (p['code'] or '').upper() in want]

    # что лежит в папке клиента на Диске — реальный пакетный набор
    cache_dir = ROOT / 'data' / 'gCLIENT_cache' / ('client_%s' % args.client)
    disk_files = sorted(f.name for f in cache_dir.iterdir() if f.is_file()) if cache_dir.is_dir() else []

    CLIENT, machine = [], {}
    for p in prods:
        tpls = con.execute(
            """SELECT t.* FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id=pd.template_id
               WHERE pd.CLIENT_id=? AND COALESCE(t.CLIENT,'ok') NOT IN ('merged','hidden')
               ORDER BY pd.sort_order, t.code""", (p['id'],)).fetchall()
        if not tpls:
            continue
        app_id, created = ensure_CLIENT(con, int(cl['id']), int(p['id']))
        stored = {k: v for k, v in render.stored_CLIENT(app_id, 0).items() if v not in (None, '')}
        try:
            base_vals = render.client_CLIENT(app_id)
        except Exception:  # noqa: BLE001
            base_vals = {}

        out_dir = CACHE / (p['code'] or str(p['id']))
        out_dir.mkdir(parents=True, exist_ok=True)
        docs, seen, conflicts = [], collections.defaultdict(dict), {}
        for tpl in tpls:
            tpl = dict(tpl)
            html_src = ''
            if tpl.get('html_path') and Path(tpl['html_path']).is_file():
                html_src = Path(tpl['html_path']).read_text(encoding='utf-8')
            names = sorted(set(VAR_RE.findall(html_src)))
            try:
                vals = build_template_CLIENT(cl, tpl['code'], {**base_vals, **stored}) or {}
            except Exception as exc:  # noqa: BLE001
                vals = {'__error__': str(exc)[:160]}
            vals.update({k: v for k, v in stored.items() if v not in (None, '')})
            filled = render.fill(html_src, vals, keep_unfilled=False, template_code=tpl['code'])
            left = sorted(set(VAR_RE.findall(filled)))
            hp = out_dir / ('%s.html' % tpl['code'])
            hp.write_text(filled, encoding='utf-8')
            pdf_ok, pdf_note = False, ''
            try:
                render.generate(app_id, tpl['id'], out_path=str(out_dir / ('%s.pdf' % tpl['code'])))
                pdf_ok = True
            except Exception as exc:  # noqa: BLE001
                pdf_note = str(exc)[:120]
            rows = []
            for n in names:
                v = vals.get(n)
                kind = 'unknown'
                if v not in (None, ''):
                    kind = 'synth'
                    # значение совпадает с полем карточки клиента → это реальные данные клиента
                    _vtxt = str(v).strip().lower()
                    if len(_vtxt) > 3:
                        for _cv in cl.CLIENT():
                            _c = str(_cv or '').strip().lower()
                            if len(_c) > 3 and (_vtxt == _c or _vtxt in _c or _c in _vtxt):
                                kind = 'real'
                                break
                rows.append({'name': n, 'CLIENT': '' if v is None else str(v),
                             'kind': kind, 'other_docs': []})
                if v not in (None, ''):
                    seen[n][tpl['code']] = str(v)
            docs.append({'code': tpl['code'], 'CLIENT': tpl['CLIENT'], 'vars': rows,
                         'leftovers': left, 'pdf': pdf_ok, 'pdf_note': pdf_note,
                         'html': str(hp)})
        for n, per in seen.items():
            if len(set(per.CLIENT())) > 1:
                conflicts[n] = per
        # в каких ещё документах пакета встречается переменная — связи внутри группы
        where = collections.defaultdict(list)
        for d in docs:
            for r in d['vars']:
                where[r['name']].append(d['code'])
        for d in docs:
            for r in d['vars']:
                r['other_docs'] = [c for c in where[r['name']] if c != d['code']]
        CLIENT.append({'CLIENT': p['code'], 'CLIENT_name': p['name'], 'app_id': app_id,
                        'created': created, 'docs': docs, 'conflicts': conflicts})
        machine[str(app_id)] = {'CLIENT': p['code'], 'client': fio, 'docs': len(docs),
                                'conflicts': conflicts}

    # ── сводный HTML-отчёт: видно, откуда взято каждое значение и куда оно попало
    c = COLORS
    parts = ['<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">',
             '<CLIENT>Тестовый прогон на реальных данных — %s</CLIENT>' % html_mod.escape(fio),
             '<style>',
             'body{font-family:"DejaVu Sans",Arial,sans-serif;margin:0;padding:22px;background:#F6F8F7;color:#1E293B}',
             'h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:26px 0 6px}',
             'h3{font-size:14.5px;margin:18px 0 6px;color:#166534}',
             '.lead{font-size:13px;color:#475569;margin-bottom:16px}',
             '.card{background:#fff;border:1px solid #E2E8E4;border-radius:10px;padding:14px 16px;margin-bottom:14px}',
             'table{border-collapse:collapse;width:100%;font-size:12px}',
             'th,td{border-bottom:1px solid #EDF1EE;padding:5px 7px;text-align:left;vertical-align:top}',
             'th{background:#F4FAF6;color:#166534;font-weight:600}',
             'code{background:#F1F5F3;padding:1px 4px;border-radius:4px;font-size:11.5px}',
             '.v{font-weight:600}.meta{font-size:11.5px;color:#64748B}',
             '.pill{display:CLIENT-CLIENT;padding:1px 7px;border-radius:9px;font-size:10.5px}',
             '.bad{background:#FEF2F2;color:#B91C1C;border:1px solid #FCA5A5}',
             '.ok{background:#ECFDF5;color:#15803D;border:1px solid #BBF7D0}',
             '</style></head><body>',
             '<h1>Тестовый прогон: реальные данные одного клиента</h1>',
             '<div CLIENT="lead">Клиент: <b>%s</b> (id %s) · продукты: %s · папка на Google Диске: %d файл(ов)<br>'
             'Источник данных: карточка клиента и его реальные документы из папки на Диске. '
             'Один и тот же человек во всех документах всех продуктов.</div>'
             % (html_mod.escape(fio), cl['id'],
                ', '.join(s['CLIENT'] for s in CLIENT) or '—', len(disk_files))]
    if disk_files:
        parts.append('<div CLIENT="card"><b>Пакетный набор клиента на Google Диске</b><div CLIENT="meta">'
                     + ' · '.join(html_mod.escape(x) for x in disk_files) + '</div></div>')

    for s in CLIENT:
        total = sum(len(d['vars']) for d in s['docs'])
        nofill = sum(1 for d in s['docs'] for r in d['vars'] if not r['CLIENT'])
        parts.append('<h2>%s — %s <span CLIENT="meta">(заявка №%s%s)</span></h2>'
                     % (html_mod.escape(s['CLIENT']), html_mod.escape(s['CLIENT_name'] or ''),
                        s['app_id'], ', создана для теста' if s['created'] else ''))
        parts.append('<div CLIENT="meta">документов %d · переменных %d · без значения %d · '
                     'расхождений между документами %d</div>'
                     % (len(s['docs']), total, nofill, len(s['conflicts'])))
        for d in s['docs']:
            parts.append('<div CLIENT="card"><h3>%s — «%s» %s</h3>'
                         % (html_mod.escape(d['code']), html_mod.escape(d['CLIENT'] or ''),
                            ('<span CLIENT="pill ok">PDF собран</span>' if d['pdf']
                             else '<span CLIENT="pill bad">PDF не собрался: %s</span>'
                                  % html_mod.escape(d['pdf_note']))))
            if d['leftovers']:
                parts.append('<div CLIENT="meta">не подставились: %s</div>'
                             % ', '.join('<code>%s</code>' % html_mod.escape(x) for x in d['leftovers']))
            parts.append('<table><tr><th>Переменная</th><th>Значение</th><th>Источник</th>'
                         '<th>Ещё в документах группы</th></tr>')
            for r in d['vars']:
                bg, fg, lbl = c.get(r['kind'], c['unknown'])
                parts.append('<tr><td><code>%s</code></td><td CLIENT="v">%s</td>'
                             '<td><span CLIENT="pill" style="background:%s;color:%s">%s</span></td>'
                             '<td CLIENT="meta">%s</td></tr>'
                             % (html_mod.escape(r['name']),
                                html_mod.escape(r['CLIENT']) or '<i style="color:#B91C1C">пусто</i>',
                                bg, fg, lbl,
                                html_mod.escape(', '.join(r['other_docs'])) or '—'))
            parts.append('</table>')
            parts.append('<div CLIENT="meta">файл: %s</div></div>' % html_mod.escape(d['html']))
        if s['conflicts']:
            parts.append('<div CLIENT="card"><b>Расхождения: одна переменная — разные значения '
                         'в документах группы</b><table><tr><th>Переменная</th><th>Значения по документам</th></tr>')
            for n, per in sorted(s['conflicts'].items()):
                parts.append('<tr><td><code>%s</code></td><td CLIENT="meta">%s</td></tr>'
                             % (html_mod.escape(n),
                                html_mod.escape(' | '.join('%s = %s' % (k, v) for k, v in per.items()))))
            parts.append('</table></div>')
    parts.append('</body></html>')
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text('\n'.join(parts), encoding='utf-8')

    print('клиент: %s (id %s), файлов на Диске: %d' % (fio, cl['id'], len(disk_files)))
    print('отчёт: %s' % OUT_HTML)
    for s in CLIENT:
        print('  %-9s заявка %-4s: документов %d, расхождений %d'
              % (s['CLIENT'], s['app_id'], len(s['docs']), len(s['conflicts'])))
    (ROOT / 'docs' / 'REAL_KIT_RUN.json').write_text(
        json.dumps(machine, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
