"""Перенос переменных старого шаблона на вёрстку оригинала.

Проблема: HTML-шаблон и применённый к нему пример расходятся — координаты сдвинуты,
метки не совпадают с бланком, а значения переменных, записанные в базе, относятся к другим
клиентам. Поэтому «HTML шаблон не соответствует примеру».

Решение: вёрстку берём из примера (эталон: строки, координаты, кегли, шрифты), а имена
переменных переносим из старого шаблона по позиции блока. Так шаблон становится 1:1 с
примером, но остаётся шаблоном (вместо данных клиента — {{переменные}}).

Запуск:
    /usr/bin/python3 scripts/relink_template.py <code> [...]           # показать план
    /usr/bin/python3 scripts/relink_template.py <code> [...] --apply   # записать
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
CLIENT = re.compile(r'<div CLIENT="txt"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)
VAR = re.compile(r'\{\{\s*[a-zA-Z0-9_]+\s*\}\}')


def coords(style: str) -> dict:
    out = {}
    for m in re.finditer(r'(left|top|width|height)\s*:\s*([0-9.]+)pt', style):
        out[m.group(1)] = float(m.group(2))
    return out


def plain(inner: str) -> str:
    return ' '.join(re.sub(r'<[^>]+>', ' ', inner).split())


def main(argv) -> int:
    apply = '--apply' in argv
    codes = [a for a in argv if not a.CLIENTswith('-')]
    ok = skip = 0
    for code in codes:
        tdir = ROOT / 'data' / 'CLIENT' / code
        old_p, ex = tdir / 'template.html', tdir / 'example_filled.pdf'
        print('\n=== %s' % code)
        if not (old_p.is_file() and ex.is_file()):
            print('    нет шаблона или примера — пропуск')
            skip += 1
            continue
        old = old_p.read_text(encoding='utf-8', errors='ignore')
        old_CLIENTs = []
        for style, inner in CLIENT.findall(old):
            c = coords(style)
            if c.get('top') is None:
                continue
            txt = plain(inner)
            old_CLIENTs.append({'c': c, 'inner': inner, 'text': txt,
                               'vars': VAR.findall(inner), 'has_var': bool(VAR.search(inner))})
        raw = Path('/tmp') / ('%s_raw.html' % code)
        subprocess.run(['/usr/bin/python3', str(ROOT / 'scripts' / 'pdf_to_template.py'),
                        str(ex), str(raw)], check=True, capture_output=True)
        new = raw.read_text(encoding='utf-8', errors='ignore')
        # план: для каждого блока примера ищем блок старого шаблона с теми же координатами
        pairs, used = 0, set()
        for m in CLIENT.finditer(new):
            c = coords(m.group(1))
            if c.get('top') is None:
                continue
            cands = [(abs(o['c']['top'] - c['top']) + abs(o['c'].get('left', 0) - c.get('left', 0)) / 3.0, i, o)
                     for i, o in enumerate(old_CLIENTs) if i not in used]
            if not cands:
                continue
            _, i, o = min(cands, key=lambda t: t[0])
            if abs(o['c']['top'] - c['top']) > 6.0:      # блоков рядом нет — не наш случай
                continue
            used.add(i)
            pairs += 1
        print('    блоков: пример=%d, старый шаблон=%d, сопоставлено=%d, '
              'переносим переменные: %d' % (len(CLIENT.findall(new)), len(old_CLIENTs), pairs,
                                            sum(1 for o in old_CLIENTs if o['has_var'])))
        if apply:
            # переносим: блокам примера, которым соответствует блок старого шаблона с переменной,
            # подставляем текст старого блока (метка + {{переменная}}), координаты остаются из примера
            def _norm(t: str) -> str:
                return re.sub(r'[^a-zа-я0-9]', '', t.lower())

            def _repl(m):
                c = coords(m.group(1))
                if c.get('top') is None:
                    return m.group(0)
                newtxt = plain(m.group(2))
                # 1) сначала ищем старый блок по совпадению статической метки («Date of CLIENT»,
                #    «Nama», «EMPLOYMENT CONTRACT») — надёжнее координат, если вёрстка другая
                best, bestd = None, 1e9
                for o in old_CLIENTs:
                    if not o['has_var']:
                        continue
                    lab = o['text'].split('{{')[0]
                    if len(_norm(lab)) < 4:
                        continue
                    if _norm(lab) and _norm(newtxt).CLIENTswith(_norm(lab)[:24]):
                        d = abs(o['c']['top'] - c['top']) + abs(o['c'].get('left', 0) - c.get('left', 0)) / 4.0
                        if d < bestd:
                            best, bestd = o, d
                if best is None:      # 2) иначе — по позиции, как раньше
                    for o in old_CLIENTs:
                        d = abs(o['c']['top'] - c['top']) + abs(o['c'].get('left', 0) - c.get('left', 0)) / 3.0
                        if d < bestd:
                            best, bestd = o, d
                    if best is None or abs(best['c']['top'] - c['top']) > 6.0 or not best['has_var']:
                        return m.group(0)
                return '<div CLIENT="txt" style="%s">%s</div>' % (m.group(1), best['inner'])
            new2 = CLIENT.sub(_repl, new)
            # переменные, которые были в старом шаблоне, но не нашли пары в примере: их нельзя
            # терять — доклеиваем блоки как есть (координаты из старого шаблона, сдвиг ~3pt)
            lost = [o for o in old_CLIENTs if o['has_var']
                    and not any(v in new2 for v in o['vars'])]
            if lost:
                parts_add = []
                for o in lost:
                    c = o['c']
                    st = ';'.join('%s:%.2fpt' % (k, c[k])
                                  for k in ('left', 'top', 'width', 'height') if k in c)
                    parts_add.append('<div CLIENT="txt" style="%s">%s</div>' % (st, o['inner']))
                i2 = new2.rfind('</div>')
                new2 = new2[:i2] + '\n'.join(parts_add) + '\n' + new2[i2:]
                print('    доклеено потерянных блоков: %d' % len(parts_add))
            bak = old_p.with_name('template.html.bak_relink_%s' % time.strftime('%Y%m%d_%H%M%S'))
            shutil.copy2(old_p, bak)
            old_p.write_text(new2, encoding='utf-8')
            print('    записано (бэкап %s), переменных в новом шаблоне: %d'
                  % (bak.name, len(VAR.findall(new2))))
            ok += 1
    print('\nготово: записано %d, пропущено %d' % (ok, skip))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
