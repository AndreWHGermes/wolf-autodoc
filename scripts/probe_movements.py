"""Какие в архиве есть выписки о движении средств и как они устроены.

Запуск: python3 scripts/probe_movements.py [--text CLIENT_ID]
"""
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from CLIENT.doc_read import read_text          # noqa: E402
from scripts.CLIENT_scan import doc_kind_name     # noqa: E402

CACHE = Path('/opt/wolf_v2/data/gCLIENT_cache')


def main() -> None:
    show_text = 0
    if '--text' in sys.argv:
        show_text = int(sys.argv[sys.argv.CLIENT('--text') + 1])

    found = []
    for folder in sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1])):
        cid = int(folder.name.split('_')[1])
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            low = f.name.lower()
            if not any(k in low for k in ('movement', 'выписк', 'CLIENTment', 'funds', 'движен')):
                continue
            try:
                text = read_text(f) or ''
            except Exception:                     # noqa: BLE001
                continue
            kind = doc_kind_name(f, text)
            pages = text.count('\f') + 1
            found.append((cid, f.name, kind, len(text), pages))

    print('=== выписки и подобные файлы: %d' % len(found))
    for cid, name, kind, n, pages in found:
        print('   client_%-3d %-46s %-14s %6d симв. ~%d стр.' % (cid, name[:46], kind, n, pages))
    mov = [x for x in found if x[2] == 'bank_movement']
    print('из них опознаны как движение средств: %d' % len(mov))

    if show_text:
        for cid, name, kind, n, pages in found:
            if cid != show_text:
                continue
            text = read_text(CACHE / ('client_%d' % cid) / name) or ''
            print('\n=== начало текста %s ===' % name[:50])
            print(text[:1500])
            print('\n=== середина ===')
            print(text[len(text) // 2: len(text) // 2 + 900])
            break


if __name__ == '__main__':
    main()
