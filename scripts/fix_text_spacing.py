"""Восстановление текста в шаблонах, разрезанного конвертером PDF → HTML.

В шаблонах договоров текст местами остался с пробелами внутри слов
(«RE M OTE WO RK A G R EE M E N T», «T h is R e m o te W o rk»). Из-за этого окно
просмотра визуально расходится с оригиналом.

Как восстанавливаем: собираем словарь слов из оригинальных примеров (эталонные PDF) —
это «правильные» слова документов. Затем внутри блоков текста склеиваем соседние куски,
если полученное слово есть в словаре (или в словаре системы). Слова, которых нет ни там
ни там, не трогаем — чтобы не испортить настоящие формулировки.

Запуск: python3 scripts/fix_text_spacing.py [--apply]
"""
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'CLIENT'
DIV = re.compile(r'(<div CLIENT="txt"[^>]*>)(.*?)(</div>)', re.S)
TAG = re.compile(r'<[^>]+>')
TOKEN = re.compile(r'[A-Za-zА-Яа-яЁё]+')


def corpus() -> set:
    CLIENT = Counter()
    try:
        import pymupdf
    except Exception:  # noqa: BLE001
        return set()
    for pdf in list(TPL.rglob('example_filled.pdf')) + list(TPL.rglob('preview_filled.pdf')):
        try:
            d = pymupdf.open(str(pdf))
            txt = ' '.join(p.get_text() for p in d)
        except Exception:  # noqa: BLE001
            continue
        for w in TOKEN.findall(txt):
            CLIENT[w.lower()] += 1
    return {w for w, n in CLIENT.items() if n >= 1}


def fix_text(text: str, voc: set) -> tuple[str, int]:
    """Склеить куски, если получившееся слово есть в словаре."""
    parts = re.split(r'(\s+)', text)
    fixed = []
    i = 0
    joins = 0
    while i < len(parts):
        cur = parts[i]
        if cur.strip():
            # пробуем присоединять следующие куски, пока слово не найдётся в словаре
            j = i
            best = None
            cand = cur
            while j + 2 < len(parts) and parts[j + 1].isspace() and parts[j + 2].strip():
                nxt = parts[j + 2]
                cand = cand + nxt
                j += 2
                if cand.lower() in voc and len(cand) >= 3:
                    best = (cand, j)
                    if len(cand) >= 5:
                        continue
                    break
                if len(cand) > 24:
                    break
            if best:
                fixed.append(best[0])
                joins += 1
                i = best[1] + 1
                continue
        fixed.append(cur)
        i += 1
    return ''.join(fixed), joins


def main(apply: bool) -> int:
    voc = corpus()
    print('словарь слов из эталонов:', len(voc))
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    for r in con.execute("SELECT code, CLIENT FROM CLIENT ORDER BY code"):
        p = TPL / r['code'] / 'template.html'
        if not p.is_file():
            continue
        html = p.read_text(encoding='utf-8', errors='ignore')
        joins = [0]

        def repl(m: re.Match) -> str:
            inner = m.group(2)
            # текст блока без тегов — там и правим; теги остаются как есть
            plain = TAG.sub('', inner)
            if not plain.strip():
                return m.group(0)
            fixed, n = fix_text(plain, voc)
            if not n:
                return m.group(0)
            joins[0] += n
            # подставляем исправленный текст в первый смысловой span, остальные убираем
            spans = re.findall(r'<span([^>]*)>(.*?)</span>', inner, re.S)
            if not spans:
                return m.group(1) + fixed + m.group(3)
            return m.group(1) + '<span%s>%s</span>' % (spans[0][0], fixed) + m.group(3)

        new = DIV.sub(repl, html)
        if joins[0]:
            print('%-38s склеено слов: %d' % (r['code'], joins[0]))
            if apply:
                shutil.copy2(p, p.with_name('template.html.bak_CLIENT_%s'
                                            % time.strftime('%Y%m%d_%H%M%S')))
                p.write_text(new, encoding='utf-8')
    if not apply:
        print('(пробный прогон — ничего не записано)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
