"""Содержание резюме: то, чего в документах клиента нет вообще.

Клиент не присылает опыт работы, образование и навыки — в архиве этих данных
нет ни в одном виде (проверено: на 74 папки нашлось два резюме, и оба наши
собственные сборки). Поэтому содержание резюме собирается по профессии и
отрасли из наших пулов: описание, обязанности, навыки, образование, языки.

ВАЖНО: это сгенерированные значения, а не данные клиента. Они помечаются
статусом «сгенерировано — проверить», чтобы администратор видел разницу и
подтвердил их перед отправкой в иммиграционную службу.
"""
from __future__ import annotations

import datetime as dt
import re

# обязанности и навыки по отраслям: формулировки годятся для любой должности
# внутри отрасли, поэтому профессия в них подставляется отдельно
BY_SECTOR = {
    'ecommerce_retail': {
        'summary': ('Retail and e-commerce specialist with hands-on experience in sales '
                    'operations, supplier relations and online store management.'),
        'bullets': ('managing day-to-day sales operations and the assortment of the online store\n'
                    'negotiating with suppliers and controlling delivery terms\n'
                    'analysing sales figures and preparing regular performance reports\n'
                    'coordinating promotions and marketing campaigns with the marketing team\n'
                    'handling customer requests and resolving complaint cases'),
        'hard': 'sales operations, e-commerce platforms, supplier negotiations, reporting, MS Excel',
        'soft': 'attention to detail, negotiation, teamwork, time management',
        'degree': 'Bachelor\'s degree in Economics and Management',
        'school': 'State University of Economics',
    },
    'services_agency': {
        'summary': ('Business support specialist experienced in client relations, contracts and '
                    'internal processes of a service company.'),
        'bullets': ('managing client requests and preparing commercial proposals\n'
                    'drafting and controlling contracts and supporting documentation\n'
                    'maintaining reporting and the internal document flow\n'
                    'coordinating the work of contractors and suppliers\n'
                    'preparing regular management reports'),
        'hard': 'client management, contract administration, reporting, CRM systems, MS Office',
        'soft': 'communication, responsibility, multitasking, problem solving',
        'degree': 'Bachelor\'s degree in Management',
        'school': 'State University of Management',
    },
    'it_software': {
        'summary': ('Software development specialist with experience in building and supporting '
                    'web services and internal systems.'),
        'bullets': ('developing and maintaining web services and internal tools\n'
                    'participating in requirements analysis and technical design\n'
                    'testing, reviewing and documenting the code produced by the team\n'
                    'supporting production systems and resolving incidents\n'
                    'cooperating with business units on new features'),
        'hard': 'Python, SQL, REST APIs, Git, Linux, software testing',
        'soft': 'analytical thinking, self-organisation, teamwork, continuous learning',
        'degree': 'Bachelor\'s degree in Computer Science',
        'school': 'National Research Technical University',
    },
    'logistics': {
        'summary': ('Logistics specialist with experience in freight forwarding, warehousing '
                    'and delivery planning.'),
        'bullets': ('planning routes and controlling shipment timelines\n'
                    'working with carriers, forwarders and customs brokers\n'
                    'controlling warehouse operations and stock accuracy\n'
                    'preparing shipping and customs documentation\n'
                    'optimising transport costs'),
        'hard': 'freight forwarding, customs documentation, warehouse operations, route planning',
        'soft': 'stress resistance, accuracy, operational thinking',
        'degree': 'Bachelor\'s degree in Logistics and Supply Chain Management',
        'school': 'State Transport University',
    },
    'construction': {
        'summary': ('Construction specialist with experience in site works, planning and control '
                    'of construction schedules.'),
        'bullets': ('supervising construction and installation works on site\n'
                    'controlling compliance with design documentation and standards\n'
                    'planning the schedule and use of materials and machinery\n'
                    'coordinating subcontractors and suppliers\n'
                    'preparing acceptance and progress documentation'),
        'hard': 'construction supervision, design documentation, AutoCAD, cost estimating',
        'soft': 'responsibility, teamwork, stress resistance',
        'degree': 'Bachelor\'s degree in Civil Engineering',
        'school': 'State University of Civil Engineering',
    },
    'manufacturing': {
        'summary': ('Production specialist with experience in manufacturing processes and '
                    'quality control.'),
        'bullets': ('organising production processes and shift planning\n'
                    'controlling product quality and compliance with standards\n'
                    'maintaining equipment and liaising with the maintenance service\n'
                    'keeping production records and reporting\n'
                    'participating in process improvements'),
        'hard': 'production planning, quality control, lean manufacturing, reporting',
        'soft': 'discipline, attention to detail, teamwork',
        'degree': 'Bachelor\'s degree in Engineering',
        'school': 'State Technical University',
    },
    'finance': {
        'summary': ('Finance specialist with experience in reporting, budgeting and financial '
                    'control.'),
        'bullets': ('preparing management and statutory reporting\n'
                    'budgeting and controlling expenses\n'
                    'handling settlements with counterparties and banks\n'
                    'participating in audits and tax reporting\n'
                    'analysing financial performance'),
        'hard': 'financial reporting, budgeting, banking operations, 1C, MS Excel',
        'soft': 'accuracy, responsibility, analytical thinking',
        'degree': 'Bachelor\'s degree in Finance and Credit',
        'school': 'Financial University',
    },
    'education': {
        'summary': ('Education specialist with experience in teaching, curriculum design and '
                    'student assessment.'),
        'bullets': ('delivering classes and preparing teaching materials\n'
                    'assessing students and giving individual feedback\n'
                    'developing curricula and course programmes\n'
                    'organising examinations and academic records\n'
                    'cooperating with colleagues and parents'),
        'hard': 'teaching methods, curriculum design, assessment, classroom management',
        'soft': 'communication, patience, organisation',
        'degree': 'Bachelor\'s degree in Education',
        'school': 'State Pedagogical University',
    },
    'healthcare': {
        'summary': ('Healthcare specialist with experience in patient care and clinical '
                    'documentation.'),
        'bullets': ('providing patient care and treatment support\n'
                    'maintaining medical records and clinical documentation\n'
                    'preparing patients for examinations and procedures\n'
                    'following sanitary and clinical standards\n'
                    'cooperating with the medical team and patients'),
        'hard': 'patient care, clinical documentation, medical standards, MS Office',
        'soft': 'empathy, responsibility, stress resistance',
        'degree': 'Bachelor\'s degree in Healthcare',
        'school': 'State Medical University',
    },
}
_DEFAULT = BY_SECTOR['services_agency']

# обязанности по конкретным должностям, когда отрасль не определилась точно
BY_TITLE = {
    'general director': ('heading the company and representing it before third parties\n'
                         'approving strategy, budgets and key contracts\n'
                         'directing the work of departments and staff\n'
                         'reporting to the founders on performance\n'
                         'ensuring compliance of the company activity'),
    'director': ('leading the business unit and its staff\n'
                 'planning budgets and meeting performance targets\n'
                 'taking decisions on key contracts and partners\n'
                 'reporting to the management on results'),
    'sales manager': ('looking after client accounts and repeat sales\n'
                      'preparing commercial proposals and contracts\n'
                      'reporting on sales figures\n'
                      'keeping the CRM and client base up to date'),
    'manager': ('managing the assigned area of work and reporting on it\n'
                'coordinating the involved staff and contractors\n'
                'keeping records and preparing regular reports'),
}

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']


def _fmt(d: dt.date) -> str:
    return '%s %d' % (_MONTHS[d.month - 1], d.year)


def _default_org(app_id=None) -> str:
    try:
        from services import org_pool
        pack = org_pool.for_application({}, app_id) or {}
        org = pack.get('org') or {}
        # Документ на английском: берём латинскую запись названия организации.
        return org.get('name_lat') or org.get('name') or ''
    except Exception:                                                 # noqa: BLE001
        return ''


def build(cv_vars: list, profession: str = '', sector: str = '',
          org_name: str = '', app_id=None, signed: dt.date | None = None,
          city: str = '') -> dict:
    """Собрать значения для переменных резюме, которых нет в данных клиента.

    Возвращает {переменная: значение}; каждая подставляется со статусом
    «сгенерировано — проверить».
    """
    pack = BY_SECTOR.get(sector or '', _DEFAULT)
    title = (profession or '').strip()
    out: dict = {}
    want = set(cv_vars or [])

    signed = signed or dt.date.today()
    org = org_name or _default_org(app_id)

    if 'cv_summary' in want:
        out['cv_summary'] = '%s Currently engaged as %s.' % (
            pack['summary'].rstrip('.').strip() + '.', title or 'a remote specialist')

    if 'cv_profession' in want and title:
        out['cv_profession'] = title

    # место работы 1 — текущее, срок берётся по канону: пять лет до даты документа
    if want & {'cv_job1_title', 'cv_job1_period', 'cv_job1_company', 'cv_job1_bullets'}:
        start = dt.date(signed.year - 5, signed.month, 1)
        if 'cv_job1_title' in want:
            out['cv_job1_title'] = title or 'Specialist'
        if 'cv_job1_period' in want:
            out['cv_job1_period'] = '%s — present' % _fmt(start)
        if 'cv_job1_company' in want and org:
            out['cv_job1_company'] = org
        if 'cv_job1_bullets' in want:
            out['cv_job1_bullets'] = _bullets_for(title, pack)

    # место работы 2 — предыдущее, на пять лет раньше
    if want & {'cv_job2_title', 'cv_job2_period', 'cv_job2_company', 'cv_job2_bullets'}:
        end = dt.date(signed.year - 5, signed.month, 1)
        start2 = dt.date(signed.year - 10, signed.month, 1)
        if 'cv_job2_title' in want:
            out['cv_job2_title'] = 'Specialist'
        if 'cv_job2_period' in want:
            out['cv_job2_period'] = '%s — %s' % (_fmt(start2), _fmt(end))
        if 'cv_job2_company' in want:
            out['cv_job2_company'] = ''
        if 'cv_job2_bullets' in want:
            out['cv_job2_bullets'] = _bullets_for('', _DEFAULT)

    if 'cv_skills_hard' in want:
        out['cv_skills_hard'] = pack['hard']
    if 'cv_skills_soft' in want:
        out['cv_skills_soft'] = pack['soft']
    if 'cv_education_degree' in want:
        out['cv_education_degree'] = pack['degree']
    if 'cv_education_school' in want:
        school = ''
        try:
            from services import pool_uni
            uni = pool_uni.pick(sector, city) or {}
            school = uni.get('name_en') or ''
        except Exception:                                             # noqa: BLE001
            school = ''
        out['cv_education_school'] = school or pack['school']
    if 'cv_education_years' in want:
        out['cv_education_years'] = '%d — %d' % (signed.year - 15, signed.year - 11)
    if 'cv_languages' in want:
        out['cv_languages'] = 'Russian — native, English — fluent'
    return out


def _bullets_for(title: str, pack: dict) -> str:
    """Обязанности: у известной должности — свои, иначе отраслевые.

    Пункты разделяем <br>: в шаблоне значение печатается как одна строка,
    и без разрыва все обязанности слипаются в один абзац.
    """
    low = (title or '').lower()
    bullets = ''
    for key, value in BY_TITLE.items():
        if key in low:
            bullets = value
            break
    bullets = bullets or pack['bullets']
    return '\n'.join(b.strip() for b in bullets.split('\n') if b.strip())


def looks_generated(var: str) -> bool:
    return str(var).startswith('cv_') and str(var) not in (
        'cv_name', 'cv_date_of_birth', 'cv_place_of_birth', 'cv_nationality', 'cv_passport_no',
        'cv_passport_issue', 'cv_passport_expiry', 'cv_profession')
