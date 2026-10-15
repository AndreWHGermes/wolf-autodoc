#!/usr/bin/env python3
"""Паспорт, дата и место рождения из договора / документа ИТК клиента.

В договоре есть строки:
    CLIENT Andreevich CLIENT, Passport No: 51 000000000, Date of Birth: 03.04.1989,
    Nationality: Russian Federation, Place of Birth: Magadan, Russia
В документе ИТК — те же данные плюс срок действия паспорта.

Заполняем только пустые поля карточки; ничего не выдумываем.
Запуск: python3 fill_passport.py [--apply]
"""
import json, os, re, sqlite3, sys, glob
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
APPLY = '--apply' in sys.argv
from services.values import _find_client_folder_by_id

RX = {
    'passport_number': [re.compile(r'Passport\s+No[.:]?\s*([0-9]{2}\s?[0-9]{6,8})', re.I),
                        re.compile(r'Passport Number\s*\n?[^\n:]*[:\s]\s*([0-9]{5,12})', re.I)],
    'birth_date': [re.compile(r'Date of Birth[.:]?\s*([0-9]{2}[./-][0-9]{2}[./-][0-9]{4})', re.I)],
    'birth_place': [re.compile(r'Place of Birth[.:]?\s*([A-Za-z][A-Za-z ,\'-]{2,45})', re.I)],
    'nationality': [re.compile(r'Nationality[.:]?\s*([A-Za-z][A-Za-z ]{3,35})', re.I)],
    'passport_expiry': [re.compile(r'Passport Expiry[.:]?\s*([0-9]{2}[./-][0-9]{2}[./-][0-9]{4})', re.I)],
}
STOP = re.compile(r'^(ussr|ru|n/?a)$', re.I)
BAD_VALUE = re.compile(r'^(kebangsaan|kewarganegaraan|tempat\s+lahir|tempat/tanggal\s+lahir|place\s+of\s+birth|date\s+of\s+birth|'
                       r'nationality|nama|paspor|passport|nomor|jenis\s+kelamin|alamat)\b', re.I)
ALLOWED_NAT = ('russian', 'russia', 'ukraine', 'kazakh', 'belarus', 'uzbek', 'kyrgyz', 'armenian',
               'georgian', 'moldovan', 'tajik', 'turkmen', 'azerbaijan', 'ukrainian', 'indonesia')


def norm_date(v):
    v = v.replace('.', '/').replace('-', '/')
    d, m, y = v.split('/')
    return '%04d-%02d-%02d' % (int(y), int(m), int(d))


def scan(client_id):
    try:
        folder = _find_client_folder_by_id(client_id)
    except Exception:
        folder = None
    if not folder or not os.path.isdir(str(folder)):
        return {}
    pdfs = sorted(glob.glob(os.path.join(str(folder), '*.pdf')))
    pdfs.sort(key=lambda f: (0 if re.search(r'agree|contract|договор', os.path.basename(f), re.I) else
                             1 if re.search(r'personal|itk|итк', os.path.basename(f), re.I) else 2))
    try:
        import pymupdf
    except Exception:
        return {}
    out = {}
    for f in pdfs[:8]:
        if len(out) >= len(RX):
            break
        try:
            d = pymupdf.open(f)
            text = '\n'.join(p.get_text() for p in d)
            d.close()
        except Exception:
            continue
        text = re.sub(r'[ \t]+', ' ', text)
        for key, rxs in RX.items():
            if out.get(key):
                continue
            for rx in rxs:
                m = rx.search(text)
                if not m:
                    continue
                v = re.sub(r'\s+', ' ', m.group(1)).strip(' ,;.')
                if len(v) < 4 or STOP.match(v) or BAD_VALUE.match(v) or looks_like_noise(v):
                    continue
                if key == 'nationality' and not any(a in v.lower() for a in ALLOWED_NAT):
                    continue
                if key in ('birth_date', 'passport_expiry'):
                    try:
                        v = norm_date(v)
                    except Exception:
                        continue
                out[key] = v
                break
    out['_file'] = os.path.basename(pdfs[0]) if pdfs else ''
    return out


conn = sqlite3.connect('data/wolf.db')
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute(
    "SELECT id, full_name_latin, passport_number, birth_date, birth_place, nationality, passport_expiry FROM clients ORDER BY id")]
plan = []
for c in rows:
    got = {k: v for k, v in scan(c['id']).items() if not k.startswith('_')}
    add = {k: v for k, v in got.items() if not (c.get(k) or '').strip()}
    if add:
        plan.append((c, add))
        print('  #%-4s %-26s %s' % (c['id'], (c['full_name_latin'] or '')[:26],
                                    ' | '.join('%s=%s' % (k, str(v)[:28]) for k, v in add.items())))
print()
print('карточек к дополнению: %d из %d' % (len(plan), len(rows)))
if APPLY and plan:
    bak = 'docs/passport_backup_%s.json' % __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')
    json.dump({str(c['id']): a for c, a in plan}, open(bak, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for c, add in plan:
        conn.execute('UPDATE clients SET %s, updated_at=datetime(\'now\') WHERE id=?' % ', '.join('%s=?' % k for k in add),
                     list(add.values()) + [c['id']])
    conn.commit()
    print('обновлено карточек: %d | бэкап: %s' % (len(plan), bak))
conn.close()
