#!/usr/bin/env python3
"""Проверка покрытия: у скольких клиентов есть документ ИТК (номер/срок разрешения)."""
import glob, os, re, sqlite3, sys
import pymupdf

sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')


def norm(s):
    return ' '.join(''.join(ch for ch in (s or '').lower() if ch.isalnum() or ch.isspace()).split())


c = sqlite3.connect('data/wolf.db')
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT id, full_name_CLIENT, CLIENT, name FROM CLIENT "
    "WHERE full_name_CLIENT IS NOT NULL AND full_name_CLIENT<>'' LIMIT 40")]

found = miss = nofolder = 0
for r in rows:
    toks = set(norm(r['full_name_CLIENT']).split())
    folder = None
    for d in glob.glob('data/gCLIENT_examples/*'):
        if not os.path.isdir(d):
            continue
        dn = set(norm(os.path.basename(d)).split())
        if toks and (toks <= dn or dn <= toks
                     or (r['CLIENT'] and norm(r['CLIENT']) in dn and r['name'] and norm(r['name']) in dn)):
            folder = d
            break
    if not folder:
        nofolder += 1
        continue
    itk = None
    for f in glob.glob(os.path.join(folder, '*.pdf')):
        try:
            doc = pymupdf.open(f)
            t = doc[0].get_text() if doc.page_count else ''
            doc.close()
        except Exception:
            continue
        u = t.upper()
        if 'CLIENT CLIENT' in u or 'STAY CLIENT' in u:
            itk = f
            break
    if itk:
        found += 1
        if found <= 6:
            print('   ✓ %-30s %s' % ((r['full_name_CLIENT'] or '')[:30], os.path.basename(itk)[:42]))
    else:
        miss += 1

print()
print('клиентов с документом ИТК: %d | папка есть, ИТК нет: %d | папки нет: %d' % (found, miss, nofolder))
