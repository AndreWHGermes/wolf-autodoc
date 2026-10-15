"""Докачка файлов архива: по одному, через ограничитель обращений к Диску.

Все заходы идут через services/drive_throttle — он держит паузу между
запросами, ограничивает число заходов в час и при отказе Google ставит
длинную паузу. Поэтому скрипт можно запускать как угодно часто: лишнего
он на Диск не пойдёт.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from services import drive_throttle as thr   # noqa: E402

ARCH = Path('/opt/wolf_v2/data/gdrive_archive')
LOG = Path('/tmp/gdrive_archive.log')

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40


def items_from_log():
    """Список файлов папок: (id, имя, папка) — из журнала скачивания."""
    text = LOG.read_text(encoding='utf-8', errors='ignore') if LOG.exists() else ''
    cur, out = '', []
    for line in text.splitlines():
        m = re.match(r'Retrieving folder ([A-Za-z0-9_\-]{15,}) (.+)', line)
        if m:
            cur = m.group(2).strip()
            continue
        m2 = re.match(r'Processing file ([A-Za-z0-9_\-]{15,}) (.+)', line)
        if m2 and cur:
            out.append((m2.group(1), m2.group(2).strip(), cur))
    return out


calls = 0
fetched = 0
blocked = 0
for fid, name, folder in items_from_log():
    if calls >= limit:
        break
    out = ARCH / folder / name
    if out.exists() and out.stat().st_size > 0:
        continue
    if not thr.acquire(wait=True, max_wait=1200):
        st = thr.state()
        print(f'Диск на паузе (ещё ~{st["wait_min"]} мин) — останавливаюсь', flush=True)
        break
    calls += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(['/usr/bin/python3', '-m', 'gdown', fid, '-O', str(out), '--quiet'],
                       timeout=180, check=False, capture_output=True)
    except Exception:
        pass
    if out.exists() and out.stat().st_size > 0:
        fetched += 1
        thr.report_ok()
        print(f'получено: {name}', flush=True)
    else:
        blocked += 1
        note = thr.report_fail('Google не отдал файл')
        print(f'не отдал: {name} — {note}', flush=True)

print(f'итог: получено {fetched}, не отдано {blocked}, заходов {calls}', flush=True)
st = thr.state()
print(f'ограничитель: заходов за час {st["calls_last_hour"]}/{st["max_per_hour"]}, '
      f'пауза {st["wait_min"]} мин, отказов подряд {st["fails"]}', flush=True)
