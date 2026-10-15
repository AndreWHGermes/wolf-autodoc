#!/usr/bin/env python3
"""Что вообще есть по клиентам: папка, документы, извлекаемая должность.

Нужно, чтобы понять, где система может заполнить должность/компанию/образование
из документов клиента, а где нужен администратор.
"""
import os, re, sys, glob, sqlite3
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')

conn = sqlite3.connect('data/wolf.db')
conn.row_factory = sqlite3.Row
clients = [dict(r) for r in conn.execute("SELECT id, full_name_latin, position, company_name FROM clients ORDER BY id")]
conn.close()

from services.values import _find_client_folder_by_id

stat = {'нет папки': 0, 'папка без pdf': 0, 'есть pdf': 0}
can_pos, need_adm, rows = 0, 0, []
for c in clients:
    try:
        folder = _find_client_folder_by_id(c['id'])
    except Exception:
        folder = None
    if not folder or not os.path.isdir(str(folder)):
        stat['нет папки'] += 1
        continue
    pdfs = glob.glob(os.path.join(str(folder), '*.pdf'))
    if not pdfs:
        stat['папка без pdf'] += 1
    else:
        stat['есть pdf'] += 1
    has_pos = bool((c['position'] or '').strip())
    if not has_pos and pdfs:
        can_pos += 1
    if not has_pos:
        need_adm += 1
    rows.append((c, os.path.basename(str(folder)), len(pdfs), has_pos))

print('всего клиентов: %d' % len(clients))
for k, v in stat.items():
    print('   %-16s %d' % (k, v))
print('   с заполненной должностью: %d | без должности: %d (в т.ч. с документами: %d)'
      % (sum(1 for _, _, _, h in rows if h), need_adm, can_pos))
print()
print('— клиенты без должности, но с документами в папке (кандидаты на автозаполнение):')
for c, folder, n, has_pos in rows:
    if not has_pos and n:
        print('   #%-4s %-26s %s | pdf: %d' % (c['id'], (c['full_name_latin'] or '')[:26], folder[:34], n))
