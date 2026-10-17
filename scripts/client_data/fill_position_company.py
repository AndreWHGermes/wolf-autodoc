#!/usr/bin/env python3
"""Заполнение должности и компании клиента из его документов (договор, резюме).

У 53 клиентов из 72 поле «Должность» пустое, хотя в папке лежат документы.
Из договора берём: должность («The Employee is hired as X», метка Position/Jabatan)
и компанию («LLC "..."», «PT ...»). Ничего не выдумываем: чего нет — остаётся пустым.

Запуск: python3 fill_position_company.py [--apply]
"""
import json, os, re, sqlite3, sys, glob
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
APPLY = '--apply' in sys.argv

sys.path.insert(0, '/root/.hermes/cache/scratch')
from services.values import _find_client_folder_by_id

COMPANY_RE = re.compile(r'\(((?:LLC|LTD|JSC|OJSC|CJSC|Inc|GmbH|PT|Pte)[^)]{2,70})\)')


def clean_company(s):
    """Компания из договора: «LLC "Inter RAO — Information Technologies", an IT company» → до конца названия."""
    s = re.sub(r'\s+', ' ', (s or '')).strip(' ,;')
    m = re.match(r'^((?:LLC|LTD|JSC|OJSC|CJSC|Inc|GmbH|PT|Pte)\s*[«"].*?[»"])', s)
    if m:
        return m.group(1).strip()
    return re.split(r'\s*,\s*(?:an?|the)\b', s)[0].strip(' ,;')
POS_LABEL_RE = re.compile(r'(?:Position|Jabatan|Должность|Job Title|Posisi)\s*[:\-]\s*([^\n]{3,60})', re.I)
ENGAGE_RE = re.compile(r'engages the Contractor as (?:an?|the)\s+(.+?)\s+to\s+provide', re.I | re.S)
HIRED_RE = re.compile(r'hired\s+as\s+([A-Z][^\n.,;]{2,45})', re.I)


def clean(s):
    s = re.sub(r'\s+', ' ', (s or '')).strip(' .,;:-"\'«»')
    s = re.split(r'\s+(?:on a|on the|for |with |and |at |to |based|under|in accordance)\b', s)[0]
    return ' '.join(s.split()[:5]).strip()


def from_docs(client_id):
    try:
        folder = _find_client_folder_by_id(client_id)
    except Exception:
        folder = None
    if not folder or not os.path.isdir(str(folder)):
        return {}
    pdfs = sorted(glob.glob(os.path.join(str(folder), '*.pdf')))
    pdfs.sort(key=lambda f: (0 if re.search(r'agreement|contract|договор', os.path.basename(f), re.I) else 1))
    try:
        import pymupdf
    except Exception:
        return {}
    pos, comp = '', ''
    for f in pdfs[:6]:
        try:
            d = pymupdf.open(f)
            text = '\n'.join(p.get_text() for p in d)
            d.close()
        except Exception:
            continue
        if not pos:
            for rx in (POS_LABEL_RE, ENGAGE_RE, HIRED_RE):
                m = rx.search(text)
                if m:
                    v = clean(m.group(1))
                    if v and len(v) > 2 and not re.search(r'employee|employer|company', v, re.I):
                        pos = v
                        break
        if not comp:
            m = COMPANY_RE.search(text)
            if m:
                v = clean_company(m.group(1))
                if len(v) > 3:
                    comp = v
        if pos and comp:
            break
    out = {}
    if pos:
        out['position'] = pos
    if comp:
        out['company_name'] = comp
    return out


conn = sqlite3.connect('data/wolf.db')
conn.row_factory = sqlite3.Row
clients = [dict(r) for r in conn.execute(
    "SELECT id, full_name_latin, position, company_name FROM clients ORDER BY id")]
targets = [c for c in clients if not (c['position'] or '').strip()]
print('клиентов без должности: %d' % len(targets))
plan = []
for c in targets:
    got = from_docs(c['id'])
    if got:
        plan.append((c, got))
        print('   #%-4s %-26s → %s' % (c['id'], (c['full_name_latin'] or '')[:26],
                                       ' | '.join('%s: %s' % (k, v[:38]) for k, v in got.items())))
print()
print('удалось заполнить: %d из %d' % (len(plan), len(targets)))
if APPLY and plan:
    bak = 'docs/position_company_backup_%s.json' % __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')
    json.dump({str(c['id']): got for c, got in plan}, open(bak, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for c, got in plan:
        conn.execute('UPDATE clients SET %s, updated_at=datetime(\'now\') WHERE id=?' % ', '.join('%s=?' % k for k in got),
                     list(got.values()) + [c['id']])
    conn.commit()
    print('обновлено карточек: %d | бэкап: %s' % (len(plan), bak))
conn.close()
