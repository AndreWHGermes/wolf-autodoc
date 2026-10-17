"""Синхронизация архива: папки Google Диска → клиенты, файлы → кэш, документы по правилам.

Запуск: /usr/bin/python3 /root/.hermes/cache/scratch/sync_archive.py
Папки берутся из лога скачивания (gdown печатает id и имя каждой папки).
"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ARCH = Path('/opt/wolf_v2/data/gdrive_archive')
CACHE = Path('/opt/wolf_v2/data/gdrive_cache')
DB = '/opt/wolf_v2/data/wolf.db'
LOG = Path('/tmp/gdrive_archive.log')
DRIVE = 'https://drive.google.com/drive/folders/%s'

log = LOG.read_text(encoding='utf-8', errors='ignore')
pairs = re.findall(r'Retrieving folder ([A-Za-z0-9_\-]{20,}) (.+)', log)
folders = {}
for fid, name in pairs:
    name = name.strip()
    if name and name not in ('work', 'completed'):
        folders.setdefault(fid, name)
print('папок найдено:', len(folders), file=sys.stderr)


def norm(s):
    return set(re.sub(r'[^a-zа-я ]', ' ', (s or '').lower()).split())


c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
clients = [dict(r) for r in c.execute(
    'SELECT id, full_name_latin, surname, name, gdrive_folder_url FROM clients')]

report = {'linked': 0, 'created': 0, 'copied': 0, 'apps': 0, 'no_folder': 0, 'docs': 0}
for fid, fname in sorted(folders.items(), key=lambda x: x[1]):
    src = ARCH / fname
    fw = norm(fname)
    hit = None
    for cl in clients:
        cw = norm(' '.join([cl.get('full_name_latin') or '', cl.get('surname') or '',
                            cl.get('name') or '']))
        if fw and fw <= cw:
            hit = cl
            break
    if not hit:
        # клиента в базе нет — заводим из папки, чтобы архив был полным
        cur = c.execute(
            'INSERT INTO clients (full_name_latin, surname, name, source, record_kind, '
            'gdrive_folder_url, created_at, updated_at) '
            "VALUES (?,?,?,?,?,?, datetime('now'), datetime('now'))",
            (fname, fname.split()[0] if fname.split() else fname, '', 'gdrive_archive',
             'archive', DRIVE % fid)).lastrowid
        c.commit()
        hit = {'id': cur, 'full_name_latin': fname}
        clients.append(dict(hit))
        report['created'] += 1
        # архивная заявка, чтобы её можно было открыть и посмотреть
        aid = c.execute(
            'INSERT INTO applications (client_id, product_id, status, gdrive_url, '
            "record_kind, created_at) VALUES (?,?,?,?,?, datetime('now'))",
            (cur, 1, 'closed', DRIVE % fid, 'archive')).lastrowid
        c.commit()
        report['apps'] += 1
    else:
        c.execute('UPDATE clients SET gdrive_folder_url=? WHERE id=?',
                  (DRIVE % fid, hit['id']))
        c.commit()
        report['linked'] += 1

    # ссылка на папку — во все архивные заявки клиента
    for a in c.execute('SELECT id FROM applications WHERE client_id=?', (hit['id'],)):
        c.execute('UPDATE applications SET gdrive_url=? WHERE id=?', (DRIVE % fid, a['id']))
    c.commit()

    # файлы копируем в кэш клиента: оттуда берутся миниатюры и разбор
    dst = CACHE / ('client_%s' % hit['id'])
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for f in src.rglob('*'):
            if f.is_file() and not f.name.startswith('.'):
                tgt = dst / f.name
                if not tgt.exists():
                    try:
                        shutil.copy2(f, tgt)
                        report['copied'] += 1
                    except Exception as e:
                        print('копирование не удалось:', f.name, e, file=sys.stderr)
    else:
        report['no_folder'] += 1

print(json.dumps(report, ensure_ascii=False))
