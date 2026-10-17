"""Что в папке клиента не читается и что лежит в визовых файлах.

Запуск:
    python3 scripts/probe_unreadable.py            — сводка по нечитаемым файлам
    python3 scripts/probe_unreadable.py visa 400   — текст визовых документов
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from services.doc_read import read_text, sniff_ext          # noqa: E402
from scripts.drive_scan import doc_kind_name                # noqa: E402

CACHE = Path('/opt/wolf_v2/data/gdrive_cache')


def unreadable() -> None:
    bad = defaultdict(list)
    total = 0
    for folder in sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1])):
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            total += 1
            try:
                text = read_text(f) or ''
            except Exception as e:                            # noqa: BLE001
                bad['ошибка чтения: %s' % type(e).__name__].append(f.name[:44])
                continue
            if len(text.strip()) < 40:
                ext = f.suffix.lower() or '(без расширения)'
                try:
                    sniffed = sniff_ext(f)
                except Exception:                             # noqa: BLE001
                    sniffed = ''
                key = '%s → %s' % (ext, sniffed or '?')
                bad[key].append(f.name[:44])
    print('всего файлов:', total)
    print('\nне читаются (нет текста):')
    for key, names in sorted(bad.items(), key=lambda kv: -len(kv[1])):
        print('\n%-28s %d файлов' % (key, len(names)))
        for n in names[:6]:
            print('     ', n)


def visa_text(limit: int = 400) -> None:
    shown = 0
    for folder in sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1])):
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            low = f.name.lower()
            if not any(k in low for k in ('visa', 'виза', 'e33g', 'b211', 'c1', 'bridging')):
                continue
            try:
                text = read_text(f) or ''
            except Exception:                                 # noqa: BLE001
                continue
            if not text.strip():
                continue
            kind = doc_kind_name(f, text)
            print('\n=== client_%s / %s | тип=%s | %d симв.' % (
                folder.name.split('_')[1], f.name[:44], kind, len(text)))
            print(text[:limit].replace('\n', ' | '))
            shown += 1
            if shown >= 4:
                return
    if not shown:
        print('визовых файлов с текстом не найдено')


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == 'visa':
        visa_text(int(sys.argv[2]) if len(sys.argv) > 2 else 400)
    else:
        unreadable()


if __name__ == '__main__':
    main()
