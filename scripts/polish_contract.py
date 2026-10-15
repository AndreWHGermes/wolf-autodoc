"""Точечная доводка текста договора: склейка разорванных слов образца (плохой текстовый слой).

В образце встречаются «The Company hereby employ s  t h e», «po s ition», «otherwi s e sp ecified»
— из-за текстового слоя исходного PDF. В шаблоне эти фразы приводим к нормальному виду.

Запуск: /usr/bin/python3 scripts/polish_contract.py [code]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
FIXES = [
    (r'employ\s+s\s+t\s+h\s+e', 'employs the'),
    (r'po\s+s\s+ition', 'position'),
    (r'Po\s+s\s+ition\s+a\s+nd\s+D\s+u\s+tie\s+s', 'Position and Duties'),
    (r'otherwi\s+s\s+e\s+sp\s+ecified\s+a\s+s', 'otherwise specified as'),
    (r'i\s+s\s+s\s+pecified,\s+thi\s+s\s+Agreement\s+s\s+hall', 'is specified, this Agreement shall'),
    (r'Non-Com\s+p\s+ete\s+a\s+nd\s+No\s+n\s*-\s*S\s+olicitatio\s+n', 'Non-Compete and Non-Solicitation'),
    (r'S\s+tart\s+Date', 'Start Date'),
    (r'P\s+a\s+ss\s+port', 'Passport'),
    (r'F\s+ix\s+ed\s+Term', 'Fixed Term'),
    (r's\s+hall\b', 'shall'),
    (r's\s+uch\b', 'such'),
    (r'\bPartie\s+s\b', 'Parties'),
    (r'\bS\s+e\s+ction\b', 'Section'),
    (r'Pro\s+ducer', 'Producer'),
    (r'\bdutie\s+s\b', 'duties'),
    (r'\bterm\s+s\b', 'terms'),
    (r'\bcondition\s+s\b', 'conditions'),
]


def main(argv) -> int:
    code = (argv or ['employment_contract__default'])[0]
    p = ROOT / 'data' / 'templates' / code / 'template.html'
    h = p.read_text(encoding='utf-8')
    total = 0
    for rx, repl in FIXES:
        h, n = re.subn(rx, repl, h)
        if n:
            total += n
            print('  %-46s → %-34s %d' % (rx[:46], repl[:34], n))
    p.write_text(h, encoding='utf-8')
    print('правок: %d' % total)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
