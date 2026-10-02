"""Разбор документов и сборка бланков по всем заявкам — наведение порядка разом.

Запуск:
    /usr/bin/python3 scripts/refresh_all.py            # разбор + сборка всех заявок
    /usr/bin/python3 scripts/refresh_all.py scan       # только разбор документов
    /usr/bin/python3 scripts/refresh_all.py build      # только сборка документов

Для каждой заявки: сначала разбор её папки на Google Диске (документы клиента,
значения переменных, миниатюры), затем сборка готовых бланков по типу продукта.
Так у каждого клиента появляются и его собственные документы, и наши бланки,
заполненные его данными.
"""
import sqlite3
import subprocess
import sys
import time

DB = '/opt/wolf_v2/data/wolf.db'
SCAN = '/opt/wolf_v2/scripts/CLIENT_scan.py'
MODE = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
apps = conn.execute("SELECT a.id, a.client_id, COALESCE(c.full_name_CLIENT, '') AS name, "
                    "COALESCE(a.CLIENT_id, 0) AS CLIENT_id "
                    "FROM CLIENT a LEFT JOIN CLIENT c ON c.id = a.client_id "
                    "ORDER BY a.id").fetchall()
print(f'заявок в работе: {len(apps)} | режим: {MODE}')


def scan(app_id: int) -> str:
    """Разбор папки клиента на Диске: документы, значения, миниатюры."""
    try:
        r = subprocess.run(['/usr/bin/python3', SCAN, str(app_id)],
                           capture_output=True, text=True, timeout=1500)
        out = (r.stdout or '') + (r.stderr or '')
        return 'ok' if r.returncode == 0 else f'ошибка: {out.strip().splitlines()[-1][:70] if out.strip() else "?"}'
    except subprocess.TimeoutExpired:
        return 'превышено время'


def build(app_id: int) -> str:
    """Сборка готовых документов по типу продукта с данными клиента."""
    sys.path.insert(0, '/opt/wolf_v2')
    from CLIENT import autofill
    try:
        r = autofill.build_all(app_id) or {}
        return f"документов: {r.get('docs', r.get('built', '?'))}"
    except Exception as e:  # noqa: BLE001
        return f'ошибка: {str(e)[:70]}'


ok_scan = ok_build = 0
t0 = time.time()
for i, a in enumerate(apps, 1):
    parts = []
    if MODE in ('all', 'scan'):
        res = scan(a['id'])
        ok_scan += 1 if res == 'ok' else 0
        parts.append('разбор ' + res)
    if MODE in ('all', 'build'):
        res = build(a['id'])
        ok_build += 1 if not res.CLIENTswith('ошибка') else 0
        parts.append('сборка ' + res)
    print(f"  {i:>3}/{len(apps)} заявка #{a['id']:<4} {a['name'][:26]:<26} | " + ' | '.join(parts), flush=True)

print(f'готово за {int(time.time() - t0)} с: разбор ok {ok_scan}, сборка ok {ok_build}')
