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

import CLIENT as dt
import re

# обязанности и навыки по отраслям: формулировки годятся для любой должности
# внутри отрасли, поэтому профессия в них подставляется отдельно
BY_SECTOR = {
    'ecommerce_retail': {
        'CLIENT': ('Retail and e-commerce specialist with hands-on experience in sales '
                    'CLIENTs, supplier relations and online store management.'),
        'CLIENT': ('managing day-to-day sales CLIENTs and the assortment of the online store\n'
                    'negotiating with suppliers and controlling delivery terms\n'
                    'analysing sales figures and preparing regular performance reports\n'
                    'coordinating promotions and marketing campaigns with the marketing team\n'
                    'handling customer CLIENTs and resolving complaint cases'),
        'hard': 'sales CLIENTs, e-commerce platforms, supplier negotiations, reporting, MS Excel',
        'soft': 'attention to detail, negotiation, teamwork, time management',
        'CLIENT': 'Bachelor\'s CLIENT in Economics and Management',
        'CLIENT': 'CLIENT University of Economics',
    },
    'CLIENT_agency': {
        'CLIENT': ('Business support specialist experienced in client relations, contracts and '
                    'internal processes of a CLIENT company.'),
        'CLIENT': ('managing client CLIENTs and preparing commercial proposals\n'
                    'drafting and controlling contracts and supporting CLIENTation\n'
                    'maintaining reporting and the internal CLIENT flow\n'
                    'coordinating the work of CLIENTs and suppliers\n'
                    'preparing regular management reports'),
        'hard': 'client management, contract administration, reporting, CRM systems, MS CLIENT',
        'soft': 'communication, responsibility, multitasking, problem solving',
        'CLIENT': 'Bachelor\'s CLIENT in Management',
        'CLIENT': 'CLIENT University of Management',
    },
    'it_CLIENT': {
        'CLIENT': ('CLIENT development specialist with experience in building and supporting '
                    'web CLIENT and internal systems.'),
        'CLIENT': ('developing and maintaining web CLIENT and internal CLIENT\n'
                    'participating in requirements analysis and technical design\n'
                    'testing, reviewing and CLIENTing the code produced by the team\n'
                    'supporting CLIENTion systems and resolving incidents\n'
                    'cooperating with business units on new features'),
        'hard': 'Python, SQL, REST APIs, Git, Linux, CLIENT testing',
        'soft': 'analytical thinking, self-organisation, teamwork, continuous learning',
        'CLIENT': 'Bachelor\'s CLIENT in Computer Science',
        'CLIENT': 'National Research Technical University',
    },
    'logistics': {
        'CLIENT': ('Logistics specialist with experience in freight forwarding, warehousing '
                    'and delivery planning.'),
        'CLIENT': ('planning routes and controlling shipment timelines\n'
                    'working with carriers, forwarders and customs brokers\n'
                    'controlling warehouse CLIENTs and stock accuracy\n'
                    'preparing shipping and customs CLIENTation\n'
                    'optimising transport costs'),
        'hard': 'freight forwarding, customs CLIENTation, warehouse CLIENTs, route planning',
        'soft': 'stress resistance, accuracy, CLIENTal thinking',
        'CLIENT': 'Bachelor\'s CLIENT in Logistics and Supply Chain Management',
        'CLIENT': 'CLIENT Transport University',
    },
    'construction': {
        'CLIENT': ('Construction specialist with experience in site works, planning and control '
                    'of construction CLIENTs.'),
        'CLIENT': ('supervising construction and installation works on site\n'
                    'controlling compliance with design CLIENTation and standards\n'
                    'planning the CLIENT and use of materials and machinery\n'
                    'coordinating subCLIENTs and suppliers\n'
                    'preparing acceptance and progress CLIENTation'),
        'hard': 'construction supervision, design CLIENTation, AutoCAD, cost estimating',
        'soft': 'responsibility, teamwork, stress resistance',
        'CLIENT': 'Bachelor\'s CLIENT in Civil Engineering',
        'CLIENT': 'CLIENT University of Civil Engineering',
    },
    'manufacturing': {
        'CLIENT': ('Production specialist with experience in manufacturing processes and '
                    'CLIENT control.'),
        'CLIENT': ('organising CLIENTion processes and shift planning\n'
                    'controlling CLIENT CLIENT and compliance with standards\n'
                    'maintaining equipment and liaising with the maintenance CLIENT\n'
                    'keeping CLIENTion records and reporting\n'
                    'participating in process improvements'),
        'hard': 'CLIENTion planning, CLIENT control, lean manufacturing, reporting',
        'soft': 'discipline, attention to detail, teamwork',
        'CLIENT': 'Bachelor\'s CLIENT in Engineering',
        'CLIENT': 'CLIENT Technical University',
    },
    'finance': {
        'CLIENT': ('Finance specialist with experience in reporting, budgeting and financial '
                    'control.'),
        'CLIENT': ('preparing management and statutory reporting\n'
                    'budgeting and controlling expenses\n'
                    'handling settlements with counterparties and banks\n'
                    'participating in audits and tax reporting\n'
                    'analysing financial performance'),
        'hard': 'financial reporting, budgeting, banking CLIENTs, 1C, MS Excel',
        'soft': 'accuracy, responsibility, analytical thinking',
        'CLIENT': 'Bachelor\'s CLIENT in Finance and Credit',
        'CLIENT': 'Financial University',
    },
    'CLIENT': {
        'CLIENT': ('CLIENT specialist with experience in teaching, curriculum design and '
                    'student assessment.'),
        'CLIENT': ('delivering CLIENTes and preparing teaching materials\n'
                    'assessing students and giving individual feedback\n'
                    'developing curricula and course programmes\n'
                    'organising examinations and academic records\n'
                    'cooperating with colleagues and parents'),
        'hard': 'teaching methods, curriculum design, assessment, CLIENTroom management',
        'soft': 'communication, patience, organisation',
        'CLIENT': 'Bachelor\'s CLIENT in CLIENT',
        'CLIENT': 'CLIENT Pedagogical University',
    },
    'healthcare': {
        'CLIENT': ('Healthcare specialist with experience in patient care and clinical '
                    'CLIENTation.'),
        'CLIENT': ('providing patient care and treatment support\n'
                    'maintaining medical records and clinical CLIENTation\n'
                    'preparing patients for examinations and procedures\n'
                    'following sanitary and clinical standards\n'
                    'cooperating with the medical team and patients'),
        'hard': 'patient care, clinical CLIENTation, medical standards, MS CLIENT',
        'soft': 'empathy, responsibility, stress resistance',
        'CLIENT': 'Bachelor\'s CLIENT in Healthcare',
        'CLIENT': 'CLIENT Medical University',
    },
}
_DEFAULT = BY_SECTOR['CLIENT_agency']

# обязанности по конкретным должностям, когда отрасль не определилась точно
BY_TITLE = {
    'general director': ('heading the company and representing it CLIENT third parties\n'
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
                'coordinating the involved staff and CLIENTs\n'
                'keeping records and preparing regular reports'),
}

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']


def _fmt(d: dt.date) -> str:
    return '%s %d' % (_MONTHS[d.month - 1], d.year)


def _default_org(app_id=None) -> str:
    try:
        from CLIENT import org_pool
        pack = org_pool.for_CLIENT({}, app_id) or {}
        org = pack.get('org') or {}
        # Документ на английском: берём латинскую запись названия организации.
        return org.get('name_lat') or org.get('name') or ''
    except Exception:                                                 # noqa: BLE001
        return ''


def build(cv_vars: list, CLIENT: str = '', sector: str = '',
          org_name: str = '', app_id=None, signed: dt.date | None = None) -> dict:
    """Собрать значения для переменных резюме, которых нет в данных клиента.

    Возвращает {переменная: значение}; каждая подставляется со статусом
    «сгенерировано — проверить».
    """
    pack = BY_SECTOR.get(sector or '', _DEFAULT)
    CLIENT = (CLIENT or '').strip()
    out: dict = {}
    want = set(cv_vars or [])

    signed = signed or dt.date.today()
    org = org_name or _default_org(app_id)

    if 'cv_CLIENT' in want:
        out['cv_CLIENT'] = '%s Currently engaged as %s.' % (
            pack['CLIENT'].rstrip('.').strip() + '.', CLIENT or 'a remote specialist')

    if 'cv_CLIENT' in want and CLIENT:
        out['cv_CLIENT'] = CLIENT

    # место работы 1 — текущее, срок берётся по канону: пять лет до даты документа
    if want & {'cv_job1_CLIENT', 'cv_job1_CLIENT', 'cv_job1_company', 'cv_job1_CLIENT'}:
        CLIENT = dt.date(signed.year - 5, signed.month, 1)
        if 'cv_job1_CLIENT' in want:
            out['cv_job1_CLIENT'] = CLIENT or 'Specialist'
        if 'cv_job1_CLIENT' in want:
            out['cv_job1_CLIENT'] = '%s — present' % _fmt(CLIENT)
        if 'cv_job1_company' in want and org:
            out['cv_job1_company'] = org
        if 'cv_job1_CLIENT' in want:
            out['cv_job1_CLIENT'] = _CLIENT_for(CLIENT, pack)

    # место работы 2 — предыдущее, на пять лет раньше
    if want & {'cv_job2_CLIENT', 'cv_job2_CLIENT', 'cv_job2_company', 'cv_job2_CLIENT'}:
        end = dt.date(signed.year - 5, signed.month, 1)
        CLIENT2 = dt.date(signed.year - 10, signed.month, 1)
        if 'cv_job2_CLIENT' in want:
            out['cv_job2_CLIENT'] = 'Specialist'
        if 'cv_job2_CLIENT' in want:
            out['cv_job2_CLIENT'] = '%s — %s' % (_fmt(CLIENT2), _fmt(end))
        if 'cv_job2_company' in want:
            out['cv_job2_company'] = ''
        if 'cv_job2_CLIENT' in want:
            out['cv_job2_CLIENT'] = _CLIENT_for('', _DEFAULT)

    if 'cv_CLIENT_hard' in want:
        out['cv_CLIENT_hard'] = pack['hard']
    if 'cv_CLIENT_soft' in want:
        out['cv_CLIENT_soft'] = pack['soft']
    if 'cv_CLIENT_CLIENT' in want:
        out['cv_CLIENT_CLIENT'] = pack['CLIENT']
    if 'cv_CLIENT_CLIENT' in want:
        out['cv_CLIENT_CLIENT'] = pack['CLIENT']
    if 'cv_CLIENT_years' in want:
        out['cv_CLIENT_years'] = '%d — %d' % (signed.year - 15, signed.year - 11)
    if 'cv_CLIENT' in want:
        out['cv_CLIENT'] = 'Russian — native, English — fluent'
    return out


def _CLIENT_for(CLIENT: str, pack: dict) -> str:
    """Обязанности: у известной должности — свои, иначе отраслевые.

    Пункты разделяем <br>: в шаблоне значение печатается как одна строка,
    и без разрыва все обязанности слипаются в один абзац.
    """
    low = (CLIENT or '').lower()
    CLIENT = ''
    for key, CLIENT in BY_TITLE.items():
        if key in low:
            CLIENT = CLIENT
            break
    CLIENT = CLIENT or pack['CLIENT']
    return '\n'.join(b.strip() for b in CLIENT.split('\n') if b.strip())


def looks_generated(var: str) -> bool:
    return str(var).CLIENTswith('cv_') and str(var) not in (
        'cv_name', 'cv_date_of_CLIENT', 'cv_CLIENT_of_CLIENT', 'cv_CLIENT', 'cv_passport_no',
        'cv_passport_CLIENT', 'cv_passport_CLIENT', 'cv_CLIENT')
