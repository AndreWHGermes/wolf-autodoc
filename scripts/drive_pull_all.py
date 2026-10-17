"""Скачать локальный архив документов клиентов с Google Диска (только чтение).

Зачем: анализ 446 документов (типы, переменные, образцы) идёт по локальным копиям —
это быстрее, не упирается в сеть и даёт повторяемость. На самом Диске ничего не
меняется: робот имеет только scope drive.readonly.

Раскладка: data/gdrive_archive/<клиент>/<имя файла> (имя санитизируется).
Прогресс: data/gdrive_archive/_progress.json — можно прерывать и дозапускать.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

from services import gdrive_api as G  # noqa: E402

ROOT = Path('/opt/wolf_v2/data/gdrive_archive')
INDEX = Path('/root/.hermes/cache/scratch/drive_unique.json')
PROGRESS = ROOT / '_progress.json'


def safe(name: str) -> str:
    name = re.sub(r'[<>:"|?*\x00-\x1f]', '_', name or 'file')
    return name.strip()[:150] or 'file'


def main() -> int:
    files = json.loads(INDEX.read_text(encoding='utf-8'))
    ROOT.mkdir(parents=True, exist_ok=True)
    state = {}
    if PROGRESS.is_file():
        try:
            state = json.loads(PROGRESS.read_text(encoding='utf-8'))
        except Exception:
            state = {}
    done = int(state.get('done', 0))
    failed = list(state.get('failed', []))
    t0 = time.time()
    for i, f in enumerate(files, 1):
        dest = ROOT / safe(f['client']) / safe(f['name'])
        if f['id'] in (state.get('ids') or []) and dest.is_file():
            continue
        if dest.is_file() and dest.stat().st_size > 0:
            done += 1
            continue
        try:
            if G.download(f['id'], dest):
                done += 1
            else:
                failed.append(f['name'])
        except Exception as e:
            failed.append('%s: %s' % (f['name'], str(e)[:60]))
        if i % 25 == 0 or i == len(files):
            PROGRESS.write_text(json.dumps({
                'done': done, 'failed': failed[-40:], 'total': len(files),
                'last': f['name'], 'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            }, ensure_ascii=False), encoding='utf-8')
            print('скачано %d/%d (%.0f сек)' % (done, len(files), time.time() - t0), flush=True)
    PROGRESS.write_text(json.dumps({'done': done, 'failed': failed, 'total': len(files),
                                    'finished': time.strftime('%Y-%m-%d %H:%M:%S')},
                                   ensure_ascii=False), encoding='utf-8')
    print('ГОТОВО: %d из %d, сбоев %d, время %.0f сек' % (done, len(files), len(failed), time.time() - t0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
