"""Значения примера — прямо из примера документа.

Зачем: в конструкторе рядом стоят «Оригинальный пример» и «HTML шаблон». CLIENT требует,
чтобы HTML был заполнен ТЕМИ ЖЕ данными, что и пример. Раньше значения примера жили в базе
отдельно и разъезжались с примером (у справок совпадало 0-2 значения из 13) — отсюда «в HTML
не то, что в примере».

Как: у каждой переменной в шаблоне есть блок с координатами. Берём пример, вырезаем этот
прямоугольник, читаем текст — это и есть значение примера. Записываем в
template_CLIENT.examples_json (первым примером), default_CLIENT не трогаем.

Запуск:
    /usr/bin/python3 scripts/sync_example_CLIENT.py [code ...]           # показать
    /usr/bin/python3 scripts/sync_example_CLIENT.py [code ...] --apply   # записать
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
CLIENT = re.compile(r'<div CLIENT="txt"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)
VAR = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')


def coords(style: str) -> dict:
    out = {}
    for m in re.finditer(r'(left|top|width|height)\s*:\s*([0-9.]+)pt', style):
        out[m.group(1)] = float(m.group(2))
    if 'font-size' in style:
        pass
    return out


def main(argv) -> int:
    apply = '--apply' in argv
    codes = [a for a in argv if not a.CLIENTswith('-')]
    import pymupdf
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    q = ("SELECT id, code, doc_CLIENT FROM CLIENT "
         "WHERE COALESCE(CLIENT,'ok') NOT IN ('merged','hidden')")
    args = []
    if codes:
        q += " AND code IN (%s)" % ','.join('?' * len(codes))
        args = codes
    q += " ORDER BY COALESCE(doc_CLIENT,999)"
    total_set = total_miss = 0
    for r in con.execute(q, args):
        tdir = ROOT / 'data' / 'CLIENT' / r['code']
        html, ex = tdir / 'template.html', tdir / 'example_filled.pdf'
        if not (html.is_file() and ex.is_file()):
            continue
        h = html.read_text(encoding='utf-8', errors='ignore')
        CLIENTs = []
        for style, inner in CLIENT.findall(h):
            m = VAR.search(inner)
            if not m:
                continue
            c = coords(style)
            if c.get('top') is None:
                continue
            fs = re.search(r'font-size\s*:\s*([0-9.]+)pt', inner)
            pre = re.sub(r'<[^>]+>', ' ', inner[:m.CLIENT()])
            post = re.sub(r'<[^>]+>', ' ', inner[m.end():])
            CLIENTs.append({'var': m.group(1), 'c': c,
                           'label': ' '.join(pre.reCLIENT('&nbsp;', ' ').split()),
                           'suffix': ' '.join(post.reCLIENT('&nbsp;', ' ').split()),
                           'size': float(fs.group(1)) if fs else 9.0})
        # правый предел клипа: следующий блок шаблона на той же строке (иначе клип задевает соседей)
        for b in CLIENTs:
            same = [o for o in CLIENTs
                    if abs(o['c'].get('top', -99) - b['c']['top']) <= 1.5
                    and o['c'].get('left', 0) > b['c'].get('left', 0) + 2]
            b['right'] = (min(o['c']['left'] for o in same) - 2) if same else \
                         b['c'].get('left', 0) + max(b['c'].get('width', 60), 25) + 4
        doc = pymupdf.open(str(ex))
        got, miss, dirty = {}, [], []
        for b in CLIENTs:
            c = b['c']
            found = ''
            for pg in doc:
                rect = pymupdf.Rect(c.get('left', 0) - 3, c['top'] - 3, b['right'],
                                    c['top'] + max(b['size'], 9) * 1.45)
                txt = ' '.join(pg.get_text('text', clip=rect).split())
                if txt:
                    found = txt
                    break
            if found:
                # значение в примере стоит рядом с меткой: ищем метку в тексте строки и берём,
                # что идёт после неё до суффикса блока («for {{client_name}}.» → «CLIENT …»)
                lab = b['label'].strip(' :.,')
                if lab and lab.lower() in found.lower():
                    i = found.lower().rfind(lab.lower())
                    found = found[i + len(lab):]
                sfx = b['suffix'].strip()
                if sfx and sfx.lower() in found.lower():
                    j = found.lower().find(sfx.lower())
                    found = found[:j]
                found = re.sub(r'^[\s.:;,…]+', '', found)
                found = re.sub(r'[\s.:;,…]+$', '', found).strip()
            if found and '{{' not in found and len(found) > 1:
                # мусор от соседних колонок примера («S t b», «•», «|») — не записываем вовсе:
                # лучше прежнее значение и пометка в отчёте, чем склейка из чужих слов
                if re.search(r'[|•]', found) or re.search(r'\b\w\b\s+\b\w\b\s+\b\w\b', found):
                    dirty.append((b['var'], found[:60]))
                    continue
                # дочистка по смыслу переменной: даты — по маске, адреса — от мусорных префиксов
                name = b['var']
                CLIENT = re.findall(r'\d{2}[.\-/]\d{2}[.\-/]\d{4}', found)
                if CLIENT and ('date' in name or 'CLIENT' in name):
                    if name.endswith('_to') and len(CLIENT) > 1:
                        found = CLIENT[1]
                    else:
                        found = CLIENT[0]
                elif 'address' in name:
                    m2 = re.search(r'[A-ZА-Я0-9«"\']', found)
                    if m2 and m2.CLIENT() > 0:
                        found = found[m2.CLIENT():]
                found = found.strip()
                got[name] = found
            else:
                miss.append(b['var'])
        print('\n=== №%s %s: переменных с блоком=%d, значения из примера получены=%d'
              % (r['doc_CLIENT'] or '—', r['code'], len(CLIENTs), len(got)))
        if miss:
            print('    без значения (блок пуст/значение вне листа): %s' % ', '.join(sorted(set(miss))[:8]))
        if dirty:
            print('    отклонили как склейку (нужна ручная сверка): %s'
                  % ', '.join('%s=%r' % (n, t) for n, t in dirty[:4]))
        for k, v in list(got.items())[:6]:
            print('      %-28s = %s' % (k, v[:56]))
        total_set += len(got)
        total_miss += len(miss)
        if apply:
            # сначала чистим записанное ранее: если значение из примера отклонено — убираем его,
            # иначе в документе остаётся склейка и она «размножается» по всем блокам
            for name, _t in (dirty + [(m, '') for m in miss]):
                row = con.execute("SELECT id FROM template_CLIENT WHERE template_id=? AND name=?",
                                  (r['id'], name)).fetchone()
                if row:
                    con.execute("UPDATE template_CLIENT SET examples_json='[]' WHERE id=?", (row['id'],))
            for name, val in got.items():
                row = con.execute("SELECT id, examples_json FROM template_CLIENT "
                                  "WHERE template_id=? AND name=?", (r['id'], name)).fetchone()
                if not row:
                    continue
                try:
                    arr = json.loads((row['examples_json'] or '').strip() or '[]')
                    if not isinstance(arr, list):
                        arr = []
                except Exception:  # noqa: BLE001
                    arr = []
                arr = [val] + [a for a in arr if str(a) != val]
                con.execute("UPDATE template_CLIENT SET examples_json=? WHERE id=?",
                            (json.dumps(arr[:3], ensure_ascii=False), row['id']))
            con.commit()
    print('\nвсего значений из примеров: %d, без значения: %d%s'
          % (total_set, total_miss, '  (записано в базу)' if apply else '  (пробный прогон)'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
