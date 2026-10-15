#!/usr/bin/env python3
"""Разбор настоящего резюме клиента: места работы и образование.

Резюме клиента — единственный достоверный источник для второго места работы
и образования. Структура резюме:

    WORK EXPERIENCE
    Head of HR & Technical Administrator          <- должность
    January 2024 — Present                        <- период
    L-TECH LLC | Moscow / Korolev (...)           <- компания | место

    Senior HR Generalist / IT Recruiter           <- второе место
    March 2017 — December 2023
    IT-Systems LLC | Moscow, Russia (...)

    EDUCATION
    Southern Federal University — Bachelor of ...

Запуск: python3 resume_fill.py [--apply]
"""
import json, os, re, sqlite3, sys, glob
sys.path.insert(0, '/opt/wolf_v2')
os.chdir('/opt/wolf_v2')
APPLY = '--apply' in sys.argv

MONTHS = ('January|February|March|April|May|June|July|August|September|October|November|December'
          '|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec')
PERIOD_RE = re.compile(r'^(?:%s)\s+\d{4}\s*[—–-]\s*(?:Present|(?:%s)\s+\d{4})$' % (MONTHS, MONTHS), re.I)

UNIV_RE = re.compile(r'([A-Z][\w&.\'-]*(?:\s+[A-Z][\w&.\'-]*){0,4}\s+'
                     r'(?:University|Universitet|Institute|College|Academy|School|Университет|Институт|Академия))')
DEGREE_RE = re.compile(r'(Bachelor(?:\'s)?(?: of [A-Za-z ]{3,30})?|Master(?:\'s)?(?: of [A-Za-z ]{3,30})?|'
                       r'PhD|MBA|Специалист|Бакалавр|Магистр)')
YEARS_RE = re.compile(r'((?:19|20)\d{2})\s*[—–-]\s*((?:19|20)\d{2}|Present|н\.в\.)')


def find_resume(client_id):
    try:
        from services.values import _find_client_folder_by_id
        folder = _find_client_folder_by_id(client_id)
    except Exception:
        folder = None
    if not folder:
        return None
    for f in sorted(glob.glob(os.path.join(str(folder), '*.pdf'))):
        if re.search(r'resume|cv|резюме', os.path.basename(f), re.I):
            return f
    return None


def _clean(s):
    return re.sub(r'\s+', ' ', (s or '')).strip(' ,;-|')


def parse_resume(path):
    try:
        import pymupdf
        d = pymupdf.open(path)
        text = '\n'.join(p.get_text() for p in d)
        d.close()
    except Exception:
        return {}
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    out, jobs = {}, []

    def idx_of(pattern):
        for i, l in enumerate(lines):
            if re.search(pattern, l, re.I):
                return i
        return -1

    i_work, i_edu = idx_of(r'^(WORK EXPERIENCE|EXPERIENCE|ОПЫТ РАБОТЫ)'), idx_of(r'^(EDUCATION|Образование)')
    end_work = i_edu if i_edu > i_work >= 0 else len(lines)
    if i_work >= 0:
        i = i_work + 1
        while i < end_work:
            # запись: должность → период → «Компания | место»
            if i + 2 < end_work and PERIOD_RE.match(lines[i + 1]) and '|' in lines[i + 2]:
                title, period, comp_line = lines[i], lines[i + 1], lines[i + 2]
                comp = _clean(comp_line.split('|')[0])
                place = _clean(comp_line.split('|', 1)[1])
                bullets = []
                j = i + 3
                while j < end_work and not (j + 2 < end_work and PERIOD_RE.match(lines[j + 1]) and '|' in lines[j + 2]):
                    if lines[j][:1] in ('•', '-', '*', '–'):
                        bullets.append(_clean(lines[j].lstrip('•-*– ')))
                    elif bullets and lines[j][0].islower():
                        bullets[-1] = (bullets[-1] + ' ' + lines[j]).strip()
                    j += 1
                jobs.append({'title': _clean(title), 'period': _clean(period).replace('Present', 'Present'),
                             'company': comp, 'place': place, 'bullets': bullets[:4]})
                i = j
                continue
            i += 1
    if jobs:
        out['job2_title'] = jobs[0]['title']
        out['job2_company'] = jobs[0]['company']
        out['job2_period'] = jobs[0]['period']
        if jobs[0]['bullets']:
            out['job2_bullets'] = '<br>'.join('• ' + b for b in jobs[0]['bullets'])
        if len(jobs) > 1:
            out['job3_title'] = jobs[1]['title']
            out['job3_company'] = jobs[1]['company']
            out['job3_period'] = jobs[1]['period']
    if i_edu >= 0:
        block = '\n'.join(lines[i_edu:i_edu + 12])
        m = UNIV_RE.search(block)
        if m:
            out['education_school'] = _clean(m.group(1))
        m = DEGREE_RE.search(block)
        if m:
            out['education_degree'] = _clean(m.group(1))
        m = YEARS_RE.search(block)
        if m:
            out['education_years'] = '%s — %s' % (m.group(1), m.group(2))
    out['_file'] = os.path.basename(path)
    out['_jobs'] = len(jobs)
    return out


if __name__ == '__main__':
    conn = sqlite3.connect('data/wolf.db')
    conn.row_factory = sqlite3.Row
    have = {r[1] for r in conn.execute('PRAGMA table_info(clients)')}
    for col in ('job3_title', 'job3_company', 'job3_period'):
        if col not in have:
            conn.execute('ALTER TABLE clients ADD COLUMN %s TEXT' % col)
    conn.commit()
    clients = [dict(r) for r in conn.execute("SELECT id, full_name_latin FROM clients ORDER BY id")]
    print('проверяю клиентов: %d' % len(clients))
    plan = []
    for c in clients:
        p = find_resume(c['id'])
        if not p:
            continue
        data = parse_resume(p)
        payload = {k: v for k, v in data.items() if not k.startswith('_') and v}
        plan.append((c, payload))
        print('   #%-4s %-24s %s' % (c['id'], (c['full_name_latin'] or '')[:24], data.get('_file', '')[:36]))
        for k, v in payload.items():
            print('        %-18s %s' % (k, str(v)[:78]))
    print()
    print('резюме найдено: %d | полей извлечено: %d' % (len(plan), sum(len(d) for _, d in plan)))
    if APPLY and plan:
        bak = 'docs/resume_fill_backup_%s.json' % __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')
        json.dump({str(c['id']): d for c, d in plan}, open(bak, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        n = 0
        for c, d in plan:
            if not d:
                continue
            conn.execute('UPDATE clients SET %s, updated_at=datetime(\'now\') WHERE id=?' % ', '.join('%s=?' % k for k in d),
                         list(d.values()) + [c['id']])
            n += 1
        conn.commit()
        print('обновлено карточек: %d | бэкап: %s' % (n, bak))
    conn.close()
