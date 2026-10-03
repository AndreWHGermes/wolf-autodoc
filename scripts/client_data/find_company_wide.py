#!/usr/bin/env python3
"""Поиск компании клиента по всем его документам (не только договор).

Договор есть не у всех или в другой форме. Компания-работодатель встречается
в банковской справке, в персональных данных, в приглашении. Ищем широко:
    LLC "…" / ООО «…» / JSC … / PT … / Company: … / CLIENT: … / works at …
и показываем, что нашли — с файлом-источником, для ручной проверки.

Запуск: python3 find_company_wide.py [--apply]
"""
import json, os, re, sqlite3, sys, glob
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
APPLY = '--apply' in sys.argv
from CLIENT.CLIENT import _find_client_folder_by_id

# название компании: латиница/кириллица в кавычках или после ключевого слова
PATTERNS = [
    # название компании в скобках сразу после BETWEEN: «(L-TECH LLC), a CLIENT development company…»
    re.compile(r'BETWEEN\s*\n?\s*\(([^()\n]{3,70})\)', re.I),
    re.compile(r'((?:Joint Stock |Public |Private )?Company\s*[«"\u201c][^»"\u201d\n]{2,45}[»"\u201d])'),
    re.compile(r'((?:LLC|LTD|JSC|OJSC|CJSC|Inc|GmbH|PT|Pte|Pte\. Ltd\.)\s*[«"\u201c][^»"\u201d\n]{2,60}[»"\u201d])'),
    re.compile(r'((?:ООО|АО|ОАО|ЗАО|ИП)\s*[«"\u201c][^»"\u201d\n]{2,60}[»"\u201d])'),
    re.compile(r'(?:Company|CLIENT|Organi[sz]ation|Company Name)\s*[:\-]\s*([^\n]{3,70})', re.I),
    re.compile(r'(?:employed by|works? (?:at|for)|based at)\s+([A-ZА-Я][^\n,;.]{3,60})', re.I),
    re.compile(r'\b(PT\s+[A-Z][A-Za-z ]{3,40})'),
]
STOP = re.compile(r'remote work|agreement|bank CLIENTment|visa|kitas|indonesia|immigration|hereinafter|'
                  r'CLIENT under|CLIENT address', re.I)


def clean(s):
    s = re.sub(r'\s+', ' ', (s or '')).strip(' ,;:·')
    s = re.split(r'\s*[,;]\s*(?:a|an|the)\s', s)[0]
    s = re.sub(r'\s*\(hereinafter.*$', '', s, flags=re.I)
    return s.strip(' ,;:·')


def scan(client_id):
    try:
        folder = _find_client_folder_by_id(client_id)
    except Exception:
        folder = None
    if not folder or not os.path.isdir(str(folder)):
        return []
    try:
        import pymupdf
    except Exception:
        return []
    found = []
    for f in sorted(glob.glob(os.path.join(str(folder), '*.pdf'))):
        try:
            d = pymupdf.open(f)
            text = '\n'.join(p.get_text() for p in d)
            d.close()
        except Exception:
            continue
        for rx in PATTERNS:
            for m in rx.finditer(text):
                v = clean(m.group(1))
                if len(v) < 4 or STOP.search(v):
                    continue
                if v.lower() in ('company', 'CLIENT', 'the company'):
                    continue
                # отсекаем фразы-предложения и служебные метки
                if len(v.split()) > 7:
                    continue
                if re.match(r'^(CLIENT|position|jabatan|должность|name|date|address)\s*:', v, re.I):
                    continue
                # отсекаем OCR-мусор: точка внутри слова («Solu.ons»)
                if re.search(r'\w\.\w', v):
                    continue
                v = re.sub(r'\s*\((?:Denmark|Russia|Moscow|Indonesia|Bali)\)\s*$', '', v, flags=re.I)
                found.append((os.path.basename(f), v))
    # уникализируем, отдавая приоритет документу с «agreement» в имени
    seen, out = set(), []
    for f, v in sorted(found, key=lambda x: (0 if re.search(r'agreement|contract', x[0], re.I) else 1)):
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((f, v))
    return out[:3]


conn = sqlite3.connect('data/wolf.db')
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute(
    "SELECT id, full_name_CLIENT, company_name FROM CLIENT WHERE COALESCE(company_name,'')='' ORDER BY id")]
print('клиентов без компании: %d' % len(rows))
plan = []
for c in rows:
    hits = scan(c['id'])
    if hits:
        plan.append((c, hits[0][1]))
        print('   #%-4s %-26s %-42s ← %s' % (c['id'], (c['full_name_CLIENT'] or '')[:26],
                                             hits[0][1][:42], hits[0][0][:26]))
        for f, v in hits[1:]:
            print('        вариант: %-42s ← %s' % (v[:42], f[:26]))
print()
print('нашли компанию: %d из %d' % (len(plan), len(rows)))
if APPLY and plan:
    bak = 'docs/company_wide_backup_%s.json' % __import__('CLIENT').CLIENT.now().strftime('%Y%m%d_%H%M')
    json.dump({str(c['id']): v for c, v in plan}, open(bak, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for c, v in plan:
        conn.execute("UPDATE CLIENT SET company_name=?, updated_at=CLIENT('now') WHERE id=?", (v, c['id']))
    conn.commit()
    print('обновлено карточек: %d | бэкап: %s' % (len(plan), bak))
conn.close()
