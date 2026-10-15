"""Склейка разбитого текста в шаблонах (артефакт конвертации PDF → HTML).

Конвертер разбивал фразы на куски по 1–2 символа: «RE M OTE WO RK A G R EE M E N T».
Из-за этого шаблон визуально расходится с оригиналом (лишние пробелы), а сверка и перевод
не работают.

Скрипт внутри каждого блока текста (`div.txt`) склеивает подряд идущие span'ы в один,
если у них совпадают семейство шрифта, цвет и насыщенность — различаться может только
размер кегля (это и есть артефакт конвертера). Куски разной роли (например «Passport:»
и значение переменной) не склеиваются.

Запуск: python3 scripts/fix_char_spans.py [--apply]
"""
import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'templates'
BACKUP = ROOT / 'data' / 'backup'

DIV = re.compile(r'(<div class="txt"[^>]*>)(.*?)(</div>)', re.S)
SPAN = re.compile(r'<span([^>]*)>([^<>]*)</span>')


def key_of(attrs: str) -> tuple:
    """Свойства, которые должны совпадать, чтобы куски считались одним текстом."""
    fam = re.search(r'font-family:([^;"]+)', attrs)
    color = re.search(r'color:([^;"]+)', attrs)
    weight = re.search(r'font-weight:([^;"]+)', attrs)
    style = re.search(r'font-style:([^;"]+)', attrs)
    return ((fam.group(1).strip() if fam else ''),
            (color.group(1).strip() if color else ''),
            (weight.group(1).strip() if weight else ''),
            (style.group(1).strip() if style else ''))


PAIR = re.compile(r'<span([^>]*)>([^<>]*)</span>(\s*)<span([^>]*)>([^<>]*)</span>')


def merge_block(inner: str) -> tuple[str, int]:
    """Склеить соседние span'ы с одинаковым стилем: короткие куски — без пробела,
    длинные — с пробелом (чтобы не сломать настоящие разделители слов)."""
    merged = 0

    def rep(m: re.Match) -> str:
        nonlocal merged
        a1, t1, ws, a2, t2 = m.groups()
        if key_of(a1) != key_of(a2):
            return m.group(0)
        s1, s2 = t1.strip(), t2.strip()
        if not s1 or not s2:
            return m.group(0)
        sep = '' if (len(s1) <= 2 or len(s2) <= 2) else ' '
        merged += 1
        return '<span%s>%s%s%s</span>' % (a1, t1.rstrip(), sep, t2.lstrip())

    prev = None
    while prev != inner:
        prev = inner
        inner = PAIR.sub(rep, inner)
    return inner, merged


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    BACKUP.mkdir(parents=True, exist_ok=True)
    report = {}
    for r in con.execute("SELECT code, status FROM templates ORDER BY code"):
        p = TPL / r['code'] / 'template.html'
        if not p.is_file():
            continue
        html = p.read_text(encoding='utf-8', errors='ignore')
        merged_count = [0]

        def repl_div(m: re.Match) -> str:
            inner, n = merge_block(m.group(2))
            merged_count[0] += n
            return m.group(1) + inner + m.group(3)

        new = DIV.sub(repl_div, html)
        if merged_count[0]:
            report[r['code']] = merged_count[0]
            print('%-38s склеено кусков: %d' % (r['code'], merged_count[0]))
            if apply:
                shutil.copy2(p, p.with_name('template.html.bak_spans_%s'
                                            % time.strftime('%Y%m%d_%H%M%S')))
                p.write_text(new, encoding='utf-8')
    if not report:
        print('разбитого текста не найдено — шаблоны чистые')
    elif not apply:
        print('(пробный прогон) всего к склейке:', sum(report.values()))
    else:
        print('всего склеено кусков:', sum(report.values()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
