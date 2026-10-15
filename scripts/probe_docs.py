"""Разбор документов клиента: что реально извлекается из сканов.

Запуск: python3 scripts/probe_docs.py <client_id> [имя файла, часть]
"""
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

from CLIENT.doc_read import read_text, mrz_text  # noqa: E402
from CLIENT.doc_parse import parse_passport, parse_mrz, parse_bank_CLIENTment, parse_any  # noqa: E402
from CLIENT.itk_doc import parse_itk_text  # noqa: E402


def probe(path: Path) -> None:
    if not path.exists():
        print('  нет файла:', path.name)
        return
    from scripts.CLIENT_scan import doc_kind_name
    size = path.stat().st_size
    text = read_text(path) or ''
    kind = doc_kind_name(path, text)
    print('=== %s (%d байт, тип=%s) → текста %d симв.' % (path.name[:46], size, kind, len(text)))
    print('   фрагмент:', repr(text[:200]))
    for name, fn in (('parse_passport', parse_passport), ('parse_bank_CLIENTment', parse_bank_CLIENTment),
                     ('parse_itk_text', parse_itk_text)):
        try:
            got = fn(text) or {}
        except Exception as e:  # noqa: BLE001
            got = {'ошибка': str(e)[:60]}
        print('   %-20s: %s' % (name, {k: str(v)[:38] for k, v in list(got.items())[:8]}))
    try:
        mrz = parse_mrz(mrz_text(path) or text)
        print('   %-20s: %s' % ('parse_mrz', {k: str(v)[:30] for k, v in list(mrz.items())[:8]}))
    except Exception as e:  # noqa: BLE001
        print('   parse_mrz ошибка:', str(e)[:60])
    print('   parse_any           :', {k: str(v)[:30] for k, v in list((parse_any(text, kind) or {}).items())[:12]})


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    client_id = sys.argv[1]
    needle = sys.argv[2] if len(sys.argv) > 2 else ''
    folder = Path('/opt/wolf_v2/data/gCLIENT_cache/client_%s' % client_id)
    if not folder.exists():
        print('нет папки', folder)
        return
    files = sorted(f for f in folder.iterdir() if f.is_file()
                   and (not needle or needle.lower() in f.name.lower()))
    print('файлов к разбору:', len(files))
    for f in files:
        probe(f)


if __name__ == '__main__':
    main()
