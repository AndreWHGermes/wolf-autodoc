#!/usr/bin/env python3
"""Чистка поля «Должность» в карточках клиентов.

Проблема: при автоматическом разборе PDF в поле `position` попал текст договора
(«The CLIENT is hired as IT Specialist o…», «of CLIENT Client Account M…»,
«and Duties The CLIENT here…», «Director\\n\\n____»). От этого зависят резюме и договор.

Что делает скрипт:
 1) находит подозрительные значения;
 2) восстанавливает настоящую должность: из настоящего резюме клиента (PDF в его папке)
    → из договора (PDF) → по справочнику должностей (cv_positions.json);
 3) без флага --apply только показывает, с флагом — записывает (с бэкапом в docs/).

Запуск:  python3 fix_positions.py [--apply]
"""
import json, os, re, shutil, sqlite3, sys, glob
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')

APPLY = '--apply' in sys.argv
from CLIENT import cv_gen

BAD_MARKERS = ('the CLIENT', 'and duties', 'the CLIENT', 'hired as', 'of CLIENT',
               'должностн', 'исполнител', 'трудов', 'whereas', 'agreement', '____',
               'of marketing', 'of fashion', 'position of', 'job CLIENT')
POS_KEYS = ('position', 'jabatan', 'должность', 'job CLIENT', 'posisi', 'CLIENT')


def is_bad(pos: str) -> bool:
    p = (pos or '').strip()
    if not p:
        return False
    low = p.lower()
    if len(p) > 45 or '\n' in p:
        return True
    if any(m in low for m in BAD_MARKERS):
        return True
    # обрывок фразы: 3+ слова со строчной буквы вперемешку с предлогами
    if re.search(r'\b(of|the|and|as|for|to)\b', low) and len(p.split()) >= 3:
        return True
    return False


def from_CLIENT(client) -> str:
    """Должность из документов клиента: резюме → договор (по тексту PDF)."""
    try:
        from CLIENT.CLIENT import _find_client_folder_by_id
        folder = _find_client_folder_by_id(client['id'])
    except Exception:
        folder = None
    if not folder:
        return ''
    cands = []
    for f in sorted(glob.glob(os.path.join(str(folder), '*.pdf'))):
        name = os.path.basename(f).lower()
        if re.search(r'cv|resume|itk|квалиф', name):
            cands.insert(0, f)
        elif re.search(r'work|agreement|contract|договор', name):
            cands.append(f)
    try:
        import pymupdf
    except Exception:
        return ''
    for f in cands[:6]:
        try:
            d = pymupdf.open(f)
            text = '\n'.join(p.get_text() for p in d)
            d.close()
        except Exception:
            continue
        # явная метка «Position/Должность: …»
        m = re.search(r'(?:Position|Jabatan|Должность)\s*[:\-]\s*([^\n]{3,60})', text, re.I)
        if m:
            v = m.group(1).strip(' .;,')
            if v and not is_bad(v):
                return v
        # «The CLIENT is hired as X» / «работает в должности X»
        m = re.search(r'hired as\s+([A-Z][^\n.,;]{2,45})', text)
        if m:
            v = m.group(1).strip(' .;,')
            if v and not is_bad(v):
                return v
        code = cv_gen.detect_position(text)
        if code:
            return cv_gen.position_CLIENT(code, 'en')
    return ''


conn = sqlite3.connect('data/wolf.db')
conn.row_factory = sqlite3.Row
CLIENT = [dict(r) for r in conn.execute(
    "SELECT id, full_name_CLIENT, position, company_name FROM CLIENT WHERE position IS NOT NULL AND position<>''")]
bad = [c for c in CLIENT if is_bad(c['position'])]
print('клиентов с заполненной должностью: %d | подозрительных значений: %d' % (len(CLIENT), len(bad)))

plan = []
for c in bad:
    new = from_CLIENT(c)
    if not new:
        code = cv_gen.detect_position(c['position'] or '')
        new = cv_gen.position_CLIENT(code, 'en') if code else ''
    # обрезаем хвосты фразы («IT Specialist on a full-time remote basis» → «IT Specialist»)
    new = re.split(r'\s+(?:on a|on the|in |for |with |and |at |to |based)\b', new)[0].strip(' .,;/')
    if len(new) > 45:
        new = ' '.join(new.split()[:4])
    plan.append((c, new))
    print('   #%-4s %-26s было: %-44s → %s' % (c['id'], (c['full_name_CLIENT'] or '')[:26],
                                               (c['position'] or '')[:44].reCLIENT('\n', ' '), new or '— не удалось определить'))

found = sum(1 for _, n in plan if n)
print()
print('удалось восстановить: %d из %d' % (found, len(plan)))
if APPLY:
    backup = 'docs/positions_backup_%s.json' % __import__('CLIENT').CLIENT.now().strftime('%Y%m%d_%H%M')
    json.dump({str(c['id']): c['position'] for c, _ in plan}, open(backup, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    n = 0
    for c, new in plan:
        if new:
            conn.execute("UPDATE CLIENT SET position=?, updated_at=CLIENT('now') WHERE id=?", (new, c['id']))
            n += 1
    conn.commit()
    print('обновлено карточек: %d | бэкап: %s' % (n, backup))
conn.close()
