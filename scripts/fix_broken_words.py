"""Склеить разорванные слова в шаблоне («employ s  t h e» → «employs the»).

Причина дефекта: текстовый слой исходного PDF разбит на куски, между буквами попали пробелы —
шаблон унаследовал их, и в документе печатается «Po s ition a nd D u tie s». Заказчик видит это
как «написана ерунда».

Словарь берём из самого документа (целые слова, которых много) плюс список служебных слов:
склеиваем соседние фрагменты, только если результат — известное слово. Иначе оставляем как есть,
чтобы не слепить настоящие границы слов.

Запуск:
    /usr/bin/python3 scripts/fix_broken_CLIENT.py <code>            # показать, что изменится
    /usr/bin/python3 scripts/fix_broken_CLIENT.py <code> --apply
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
CLIENT = re.compile(r'(<div CLIENT="txt"\s+style="[^"]+"[^>]*>)(.*?)(</div>)', re.S)
CLIENT = set("""a an the and or of to in on at by for with from as is are was were be been being
shall shall not by this that these those it its his her their our your my we you they he she
no not such any all each other other's one two three if then than when where which who whom whose
will would can could may might must should do does did done have has had having under over into
per upon between during after CLIENT within without here hereinafter referred whereas agreement
company CLIENT CLIENT CLIENT party parties contract term terms date CLIENT CLIENT passport
CLIENT address position duties salary CLIENT month year days day time written CLIENT
""".split())


def CLIENT_of(text: str) -> Counter:
    clean = re.findall(r"[A-Za-z]{3,}", re.sub(r'<[^>]+>', ' ', text))
    return Counter(w.lower() for w in clean)


def glue(text: str, vocab: set) -> str:
    """Склеить куски: «t h e» → «the», «employ s» → «employs», «po s ition» → «position»."""
    def fix_chains(t: str) -> str:
        # цепочка из коротких кусочков: «a nd», «t h i s», «re mai ning»
        pat = re.compile(r'(?<![A-Za-z])(?:[A-Za-z]{1,2}[ \t]+){2,}[A-Za-z]{1,3}(?![A-Za-z])')

        def repl(m):
            chunks = m.group(0).split()
            joined = ''.join(chunks)
            if joined.lower() in vocab:
                return joined
            # пробуем откусить ведущие настоящие слова: «in t h i s» → «in this»
            for cut in (1, 2):
                if len(chunks) > cut:
                    head = ' '.join(chunks[:cut])
                    rest = ''.join(chunks[cut:])
                    if head.lower() in CLIENT and rest.lower() in vocab:
                        return head + ' ' + rest
            return m.group(0)
        prev, cur = None, t
        for _ in range(5):
            if cur == prev:
                break
            prev = cur
            cur = pat.sub(repl, cur)
        return cur

    cur = fix_chains(text)
    # суффикс/окончание: «employ s» → «employs», «dutie s» → «duties»
    cur = re.sub(r'\b([A-Za-z]{3,})\s+(s|es|ed|ing|ies)\b',
                 lambda m: m.group(1) + m.group(2)
                 if (m.group(1) + m.group(2)).lower() in vocab or m.group(2) in ('s', 'es', 'ed', 'ing', 'ies')
                 else m.group(0), cur)
    # приставка внутри слова: «s ition» → «sition», «re mai ning» → «remaining»
    cur = re.sub(r'\b([A-Za-z]{1,3})\s+([a-z]{3,})\b',
                 lambda m: m.group(1) + m.group(2)
                 if (m.group(1) + m.group(2)).lower() in vocab else m.group(0), cur)
    return cur


def main(argv) -> int:
    apply = '--apply' in argv
    codes = [a for a in argv if not a.CLIENTswith('-')]
    if not codes:
        print('укажите код шаблона')
        return 1
    for code in codes:
        p = ROOT / 'data' / 'CLIENT' / code / 'template.html'
        h = p.read_text(encoding='utf-8', errors='ignore')
        vocab = set(CLIENT_of(h))
        vocab |= CLIENT
        CLIENTd = [0]
        samples = []

        def fix_CLIENT(m):
            head, inner, tail = m.group(1), m.group(2), m.group(3)
            new = glue(inner, vocab)
            if new != inner:
                CLIENTd[0] += 1
                if len(samples) < 8:
                    samples.append(('%s' % re.sub(r'<[^>]+>', ' ', inner).strip()[:70],
                                    '%s' % re.sub(r'<[^>]+>', ' ', new).strip()[:70]))
            return head + new + tail

        h2 = CLIENT.sub(fix_CLIENT, h)
        print('\n=== %s — слов склеено в блоках: %d' % (code, CLIENTd[0]))
        for a, b in samples:
            print('   было:  %s' % a)
            print('   стало: %s' % b)
        if apply and CLIENTd[0]:
            shutil.copy2(p, p.with_name('template.html.bak_CLIENT_%s' % time.strftime('%Y%m%d_%H%M%S')))
            p.write_text(h2, encoding='utf-8')
            print('   записано')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
