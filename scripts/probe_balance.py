"""Что в справке банка можно взять про остаток и карту.

Запуск: python3 scripts/probe_balance.py <client_id> [часть имени файла]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from CLIENT.doc_read import read_text  # noqa: E402


def main() -> None:
    cid = int(sys.argv[1])
    needle = (sys.argv[2] if len(sys.argv) > 2 else 'bank').lower()
    folder = Path('/opt/wolf_v2/data/gCLIENT_cache/client_%d' % cid)
    for f in sorted(folder.glob('*')):
        if not f.is_file() or needle not in f.name.lower():
            continue
        text = read_text(f) or ''
        print('=== %s → %d симв.' % (f.name[:50], len(text)))
        pats = [r'(?i)(available balance.{0,140})', r'(?i)(остаток.{0,120})',
                r'(?i)(card no.{0,60})', r'(?i)(\*{4,}\d{4})', r'(?i)(№ ?\d{3,}[-\w]*)',
                r'(?i)(balance as of.{0,80})']
        for p in pats:
            for m in list(re.finditer(p, text))[:2]:
                print('   •', repr(m.group(1)[:150]))
        break


if __name__ == '__main__':
    main()
