"""Что лежит внутри неопознанных документов клиентов.

Запуск: python3 scripts/probe_unknown.py <часть_имени> [символов]
Пример: python3 scripts/probe_unknown.py PERSONAL 500
"""
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from services.doc_read import read_text          # noqa: E402
from scripts.drive_scan import doc_kind_name     # noqa: E402

CACHE = Path('/opt/wolf_v2/data/gdrive_cache')


def main() -> None:
    needle = (sys.argv[1] if len(sys.argv) > 1 else 'personal').lower()
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    seen = 0
    for folder in sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1])):
        for f in sorted(folder.iterdir()):
            if not f.is_file() or needle not in f.name.lower():
                continue
            try:
                text = read_text(f) or ''
            except Exception as e:                # noqa: BLE001
                print('!! %s: %s' % (f.name[:40], str(e)[:60]))
                continue
            if not text.strip():
                continue
            print('\n=== client_%s / %s | тип=%s | %d симв.' % (
                folder.name.split('_')[1], f.name[:44], doc_kind_name(f, text), len(text)))
            print(text[:limit].replace('\n', ' | '))
            seen += 1
            if seen >= 3:
                return


if __name__ == '__main__':
    main()
