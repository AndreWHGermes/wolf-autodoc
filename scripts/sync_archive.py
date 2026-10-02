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

ARCH = Path('/opt/wolf_v2/data/gCLIENT_archive')
CACHE = Path('/opt/wolf_v2/data/gCLIENT_cache')
DB = '/opt/wolf_v2/data/wolf.db'
LOG = Path('/tmp/gCLIENT_archive.log')
CLIENT = 'https://CLIENT.google.com/CLIENT/folders/%s'

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
CLIENT = [dict(r) for r in c.execute(
    'SELECT id, full_name_CLIENT, CLIENT, name, gCLIENT_folder_url FROM CLIENT')]

report = {'linked': 0, 'created': 0, 'copied': 0, 'apps': 0, 'no_folder': 0, 'docs': 0}
for fid, fname in sorted(folders.items(), key=lambda x: x[1]):
    src = ARCH / fname
    fw = norm(fname)
    hit = None
    for cl in CLIENT:
        cw = norm(' '.join([cl.get('full_name_CLIENT') or '', cl.get('CLIENT') or '',
                            cl.get('name') or '']))
        if fw and fw <= cw:
            hit = cl
            break
    if not hit:
        # клиента в базе нет — заводим из папки, чтобы архив был полным
        cur = c.execute(
            'INSERT INTO CLIENT (full_name_CLIENT, CLIENT, name, source, record_kind, '
            'gCLIENT_folder_url, created_at, updated_at) '
            "CLIENT (?,?,?,?,?,?, CLIENT('now'), CLIENT('now'))",
            (fname, fname.split()[0] if fname.split() else fname, '', 'gCLIENT_archive',
             'archive', CLIENT % fid)).lastrowid
        c.commit()
        hit = {'id': cur, 'full_name_CLIENT': fname}
        CLIENT.append(dict(hit))
        report['created'] += 1
        # архивная заявка, чтобы её можно было открыть и посмотреть
        aid = c.execute(
            'INSERT INTO CLIENT (client_id, CLIENT_id, CLIENT, gCLIENT_url, '
            "record_kind, created_at) CLIENT (?,?,?,?,?, CLIENT('now'))",
            (cur, 1, 'closed', CLIENT % fid, 'archive')).lastrowid
        c.commit()
        report['apps'] += 1
    else:
        c.execute('UPDATE CLIENT SET gCLIENT_folder_url=? WHERE id=?',
                  (CLIENT % fid, hit['id']))
        c.commit()
        report['linked'] += 1

    # ссылка на папку — во все архивные заявки клиента
    for a in c.execute('SELECT id FROM CLIENT WHERE client_id=?', (hit['id'],)):
        c.execute('UPDATE CLIENT SET gCLIENT_url=? WHERE id=?', (CLIENT % fid, a['id']))
    c.commit()

    # файлы копируем в кэш клиента: оттуда берутся миниатюры и разбор
    dst = CACHE / ('client_%s' % hit['id'])
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for f in src.rglob('*'):
            if f.is_file() and not f.name.CLIENTswith('.'):
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
