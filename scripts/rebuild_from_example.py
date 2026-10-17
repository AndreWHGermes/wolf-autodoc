"""Пересборка HTML-шаблона строго по его оригинальному примеру.

Идея: HTML шаблона должен повторять пример 1:1 (все строки, координаты, кегли), а данные
клиента в нём заменяются на {{переменные}}. Поэтому:

  1. берём example_filled.pdf (настоящий поданный документ) → raw HTML (pdf_to_template);
  2. значения примера (пример переменной → значение по умолчанию) ищем в тексте raw HTML
     и заменяем на {{имя переменной}};
  3. сохраняем как template.html (старый — в .bak_rebuild_<дата>).

Ничего не додумываем: чего нет в примере — в шаблоне не появляется.

Запуск:
    /usr/bin/python3 scripts/rebuild_from_example.py <code> [...]        # показать план
    /usr/bin/python3 scripts/rebuild_from_example.py <code> --apply      # записать
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
TXT_DIV = re.compile(r'<div class="txt"[^>]*>(.*?)</div>', re.S)
SPAN = re.compile(r'(<span[^>]*>)(.*?)(</span>)', re.S)


def example_values(con, template_id: int) -> dict:
    vals = {}
    for r in con.execute("SELECT name, default_value, examples_json FROM template_variables "
                         "WHERE template_id=?", (template_id,)):
        v = ''
        try:
            ex = json.loads((r['examples_json'] or '').strip() or '[]')
            if ex:
                v = str(ex[0])
        except Exception:  # noqa: BLE001
            v = ''
        if not v.strip():
            v = str(r['default_value'] or '')
        if v.strip():
            vals[r['name']] = v.strip()
    return vals


def replace_in_html(html: str, value: str, var: str) -> tuple[str, int]:
    """Замена значения внутри отдельного span'а (значение целиком или его часть)."""
    hits = 0

    def esc(t: str) -> str:
        return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _sub_plain(t: str) -> str:
        nonlocal hits
        if value and value.lower() in t.lower():
            i = t.lower().index(value.lower())
            hits += 1
            return t[:i] + '{{ ' + var + ' }}' + t[i + len(value):]
        return t

    def _sub_line(m):
        inner = m.group(0)
        inner = _sub_plain(inner)
        return inner

    # сначала по тексту span'ов (там данные), затем по остаткам
    def _span(m):
        open_t, body, close_t = m.group(1), m.group(2), m.group(3)
        return open_t + _sub_plain(body) + close_t

    html = TXT_DIV.sub(_sub_line, html)
    html = SPAN.sub(_span, html)
    return html, hits


def main(argv) -> int:
    apply = '--apply' in argv
    codes = [a for a in argv if not a.startswith('-')]
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    ok = bad = 0
    for code in codes:
        r = con.execute("SELECT id, code, doc_index FROM templates WHERE code=?", (code,)).fetchone()
        if not r:
            print('!! нет шаблона', code)
            bad += 1
            continue
        tdir = ROOT / 'data' / 'templates' / code
        ex, html_p = tdir / 'example_filled.pdf', tdir / 'template.html'
        print('\n=== №%s %s' % (r['doc_index'] or '—', code))
        if not ex.is_file():
            print('    пример отсутствует — нечего пересобирать')
            bad += 1
            continue
        raw = Path('/tmp') / ('%s_raw.html' % code)
        subprocess.run(['/usr/bin/python3', str(ROOT / 'scripts' / 'pdf_to_template.py'),
                        str(ex), str(raw)], check=True, capture_output=True)
        html = raw.read_text(encoding='utf-8', errors='ignore')
        vals = example_values(con, r['id'])
        repl, miss = 0, []
        # длинные значения — раньше, чтобы короткие не «съели» их части
        for name, val in sorted(vals.items(), key=lambda kv: -len(kv[1])):
            if len(val) < 3:
                continue
            html, n = replace_in_html(html, val, name)
            repl += n
            if n == 0:
                miss.append(name)
        print('    переменных с примером: %d, подставлено вхождений: %d' % (len(vals), repl))
        if miss:
            print('    не найдено в примере (%d): %s' % (len(miss), ', '.join(miss[:8])))
        if apply:
            bak = html_p.with_name('template.html.bak_rebuild_%s' % time.strftime('%Y%m%d_%H%M%S'))
            if html_p.is_file():
                shutil.copy2(html_p, bak)
            html_p.write_text(html, encoding='utf-8')
            print('    записано: template.html (бэкап %s)' % bak.name)
            ok += 1
    print('\nготово: записано %d, проблем %d' % (ok, bad))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
