#!/usr/bin/env python3
"""Привести три резюме к их оригиналам: значения, состав переменных, чистка мусора.

Источники (реальные документы клиентов):
  №5 cv__format_short    — Artur Balabaev, Personal Assistant
  №6 cv__format_detailed — Viktoriia Korchagina, Senior Sales Manager (значения уже стоят)
  №7 cv__format_CLIENT   — IVAN CLIENT, Executive Director

Что делаем:
  1) удаляем мусорные переменные (дубли из старых версий), кроме служебной cv_profession;
  2) добавляем переменные, которые документ использует, а в базе их нет;
  3) записываем значения примера строго из оригинала своего документа.
"""
import json, sqlite3

DB = '/opt/wolf_v2/data/wolf.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ---------- значения из оригиналов ----------
SHORT = {
    'cv_profession': 'Personal Assistant',
    'cv_name': 'Artur Balabaev',
    'full_name_latin': 'Artur Balabaev',
    'cv_place_of_birth': 'Khabarovsk Krai, Russia',
    'cv_date_of_birth': '29 July 2002',
    'cv_nationality': 'Russian Federation',
    'cv_passport_no': '77 2829709',
    'cv_passport_issue': '15 March 2024',
    'cv_passport_expiry': '15 March 2034',
    'cv_job1_title': 'Personal Assistant',
    'cv_job1_period': 'Jun 2025 – Present',
    'cv_job1_company': 'LLC ROBUSTA',
    'cv_job1_bullets': ('\u2022  Provide personal and administrative assistance to the client, including '
                        'calendar management, correspondence, and travel arrangements\n'
                        '\u2022  Coordinate and administer the client\'s personal and business-related affairs '
                        'as instructed\n'
                        '\u2022  Coordinate remote operations and provide administrative support\n'
                        '\u2022  Ensure compliance with internal confidentiality and administrative policies'),
    'cv_job2_title': 'Manager Assistant',
    'cv_job2_period': 'Sep 2023 – Aug 2025',
    'cv_job2_company': 'Avito',
    'cv_job2_bullets': ('\u2022  Successfully managed and coordinated calendars for 15 executives, optimizing '
                        'scheduling efficiency by 20% and eliminating conflicts\n'
                        '\u2022  Spearheaded the transition from paper-based to digital document management, '
                        'cutting administrative overhead by 30% and improving team collaboration\n'
                        '\u2022  Organized and executed 5 corporate events, conferences, and team-building '
                        'activities, with attendance rates exceeding 95% and positive feedback from participants'),
    'cv_education_school': 'Khabarovsk State University of Economics and Law (KSUEL)',
    'cv_education_degree': 'Business Management',
    'cv_languages': 'Russian – Native  |  English – B1–B2 (Intermediate–Upper-Intermediate)',
}

CLIENT = {
    'cv_profession': 'Executive Director',
    'cv_name': 'IVAN CLIENT',
    'full_name_latin': 'IVAN CLIENT',
    'cv_place_of_birth': 'Moscow, Russia',
    'cv_date_of_birth': '08.01.1999',
    'cv_nationality': 'Russian Federation',
    'cv_passport_no': '77 0139869',
    'cv_summary': ('Executive Director with a degree in Business Management from Lomonosov Moscow State '
                   'University. Experienced in managing company operations, business strategy, sales and '
                   'supplier relations, budgeting and team leadership. Works fully remotely and independently '
                   'for a Russian company.'),
    'cv_job1_title': 'Executive Director',
    'cv_job1_period': 'September 2025 – Present',
    'cv_job1_company': 'LLC "INGREDIENTTRADE", Zelenograd, Moscow, Russia | samsebesamogonshik.ru',
    'cv_job1_bullets': ('\u2022  Managing the day-to-day operations of the Company and ensuring the achievement '
                        'of its business objectives.\n'
                        '\u2022  Developing and implementing the Company\'s business strategy, annual plans and '
                        'budgets.\n'
                        '\u2022  Overseeing sales, procurement, supply chain and customer relations; negotiating '
                        'with key partners and suppliers.\n'
                        '\u2022  Supervising staff, monitoring financial performance and ensuring compliance with '
                        'applicable laws and internal policies.'),
    'cv_education_school': 'Lomonosov Moscow State University',
    'cv_education_years': '2017 – 2022',
    'cv_education_degree': 'Business Management – Bachelor Degree',
    'cv_skills_hard': ('\u2022  Strategic planning and business development\n'
                       '\u2022  Operations, sales and supply chain management\n'
                       '\u2022  Budgeting, financial planning and performance analysis\n'
                       '\u2022  Team leadership and negotiations\n'
                       '\u2022  MS Office, CRM systems, remote collaboration tools'),
    'cv_languages': 'Russian – Native  |  English – B2 (Upper-Intermediate)',
}

PLAN = {
    'cv__format_short': {'vals': SHORT, 'drop': ['date_of_birth', 'passport_no'],
                         'add': [('cv_education_degree', 'Специальность (образование)'),
                                 ('cv_education_school', 'Учебное заведение'),
                                 ('cv_languages', 'Языки')]},
    'cv__format_CLIENT': {'vals': CLIENT,
                          'drop': ['company', 'date_of_birth', 'passport', 'cv_job2_title', 'cv_job2_period',
                                   'cv_job2_company', 'cv_job2_bullets', 'cv_passport_issue',
                                   'cv_passport_expiry'],
                          'add': [('cv_languages', 'Языки')]},
    'cv__format_detailed': {'vals': {}, 'drop': [], 'add': []},
}

for code, cfg in PLAN.items():
    t = conn.execute("SELECT id, doc_index FROM templates WHERE code=?", (code,)).fetchone()
    if not t:
        print('%s: шаблон не найден' % code)
        continue
    tid = t['id']
    print('=' * 58)
    print('%s (документ №%s)' % (code, t['doc_index']))

    # 1) мусор
    for name in cfg['drop']:
        cur = conn.execute("DELETE FROM template_variables WHERE template_id=? AND name=?", (tid, name))
        if cur.rowcount:
            print('  убрана лишняя переменная: %s' % name)

    # 2) недостающие переменные
    for name, label in cfg['add']:
        row = conn.execute("SELECT id FROM template_variables WHERE template_id=? AND name=?",
                           (tid, name)).fetchone()
        if not row:
            conn.execute("""INSERT INTO template_variables
                            (template_id, name, label, vtype, format, source_kind, source_ref,
                             default_value, sort_order, rule_note, approved, examples_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (tid, name, label, 'text', '', 'документы клиента', '', '', 50,
                          'Заполняется из документов клиента / выбирается администратором', 1, '[]'))
            print('  добавлена переменная: %s (%s)' % (name, label))
    conn.commit()

    # 3) значения примера
    saved = skipped = 0
    for name, val in cfg['vals'].items():
        row = conn.execute("SELECT id FROM template_variables WHERE template_id=? AND name=?",
                           (tid, name)).fetchone()
        if not row:
            skipped += 1
            continue
        conn.execute("UPDATE template_variables SET examples_json=?, default_value=? WHERE id=?",
                     (json.dumps([val], ensure_ascii=False), val if '\n' not in val else '', row['id']))
        saved += 1
    conn.commit()
    print('  значений из оригинала записано: %d%s' % (saved, (' (пропущено: %d)' % skipped) if skipped else ''))

conn.close()
print()
print('готово')
