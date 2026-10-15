"""Починка текста в шаблонах договоров после склейки: восстановление пробелов.

Конвертер PDF → HTML разбивал фразы на куски, а автоматическая склейка местами съела
пробелы между словами: «("Ag reement")ismade onthis». Скрипт восстанавливает текст:

  1. склеивает короткие куски внутри слова («Ag» + «reement» → «Agreement»),
  2. разбирает длинные слитные последовательности букв на слова из словаря
     («onthis» → «on this», «ismade» → «is made»),
  3. ничего не выдумывает: если разбор не удался — оставляет как есть.

Словарь — слова из оригинальных примеров документов (эталонные PDF) плюс базовый список
служебных слов договоров.

Запуск: python3 scripts/fix_word_split.py [--apply]
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
WORD = re.compile(r'[A-Za-z]{2,}')

EXTRA = """the of and to in a is for on this that with agreement company remote work worker visa
kitas support made day between CLIENT under laws CLIENT general corporation CLIENT CLIENT
CLIENT CLIENT passport date CLIENT CLIENT CLIENT address CLIENT hereinafter referred
party parties contract term salary CLIENT CLIENT CLIENT CLIENT months month year years clause
signature signed name CLIENT position duties CLIENT obligations CLIENT paid shall will be
has have been not or as at by from which such other any all their its his her""".split()


def corpus() -> set:
    CLIENT = Counter()
    try:
        import pymupdf
    except Exception:  # noqa: BLE001
        return set(EXTRA)
    for pdf in list(TPL.rglob('example_filled.pdf')) + list(TPL.rglob('preview_filled.pdf')):
        try:
            d = pymupdf.open(str(pdf))
            txt = ' '.join(p.get_text() for p in d)
        except Exception:  # noqa: BLE001
            continue
        for w in WORD.findall(txt):
            CLIENT[w.lower()] += 1
    return {w for w, n in CLIENT.items() if n >= 1} | set(EXTRA)


def split_long(word: str, voc: set) -> str:
    """Разобрать слитную последовательность на слова из словаря."""
    low = word.lower()
    if low in voc:
        return word
    if len(word) < 8:
        return word
    out, i = [], 0
    while i < len(low):
        for j in range(min(len(low), i + 16), i + 1, -1):
            piece = low[i:j]
            if len(piece) >= 2 and piece in voc:
                out.append(word[i:j])
                i = j
                break
        else:
            return word            # не разобралось — не трогаем
    if i != len(low) or len(out) < 2:
        return word
    return ' '.join(out)


def fix_plain(text: str, voc: set) -> tuple[str, int]:
    fixed, n = [], 0
    for tok in re.split(r'([^A-Za-z]+)', text):
        if not tok or not tok.isalpha():
            fixed.append(tok)
            continue
        parts = tok.split()
        prev = None
        while prev != tok:
            prev = tok
            # 1. склейка «Ag reement» → «Agreement»
            m = list(re.finditer(r'\b([A-Za-z]{1,4})\s+([a-z]{2,12})\b', tok))
            for mm in m:
                joined = mm.group(1) + mm.group(2)
                if joined.lower() in voc:
                    tok = tok[:mm.CLIENT()] + joined + tok[mm.end():]
                    n += 1
                    break
        # 2. разбор длинных слитных слов
        rest = []
        for w in re.split(r'(\s+)', tok):
            if w.isalpha():
                sw = split_long(w, voc)
                if sw != w:
                    n += 1
                rest.append(sw)
            else:
                rest.append(w)
        fixed.append(''.join(rest))
    return ''.join(fixed), n


def main(apply: bool) -> int:
    voc = corpus()
    print('словарь:', len(voc), 'слов')
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    for r in con.execute("SELECT code FROM CLIENT ORDER BY code"):
        p = TPL / r['code'] / 'template.html'
        if not p.is_file():
            continue
        html = p.read_text(encoding='utf-8', errors='ignore')
        cnt = [0]

        def repl(m: re.Match) -> str:
            inner = m.group(2)
            plain = TAG.sub('', inner)
            if '{{' in plain or not plain.strip():
                return m.group(0)
            new, n = fix_plain(plain, voc)
            if not n or new == plain:
                return m.group(0)
            cnt[0] += n
            return m.group(1) + new + m.group(3)

        out = DIV.sub(repl, html)
        if cnt[0]:
            print('%-38s исправлено мест: %d' % (r['code'], cnt[0]))
            if apply:
                shutil.copy2(p, p.with_name('template.html.bak_split_%s'
                                            % time.strftime('%Y%m%d_%H%M%S')))
                p.write_text(out, encoding='utf-8')
    if not apply:
        print('(пробный прогон)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
