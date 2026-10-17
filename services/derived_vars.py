"""Переменные, которых нет в документах клиента — они выводятся из заявки.

Часть переменных невозможно «прочитать» ни из паспорта, ни из справки: дата
документа, адресат письма, офис иммиграции, данные поверенного, строка просьбы.
Их нужно вычислять по заявке и продукту, иначе документы уходят с пустыми полями.

Правила (по договорённостям с заказчиком):
  * дата документа — не «сегодня», а от даты заявки: документ считается
    подписанным за несколько дней до неё (для старых заявок это критично);
  * офис иммиграции выбирается по адресу клиента в Индонезии
    (Canggu/Badung/Kuta → Ngurah Rai, Denpasar → Denpasar, Tabanan → Tabanan);
  * строка просьбы берётся из продукта, а не сочиняется каждый раз.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

DB_PATH = '/opt/wolf_v2/data/wolf.db'

# сколько дней «назад» подписан документ от даты заявки
SIGN_BACK_DAYS = 6

MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
             'August', 'September', 'October', 'November', 'December']

# офис иммиграции по адресу клиента в Индонезии
OFFICES = (
    ('ngurahrai', ('canggu', 'badung', 'kuta', 'padang linjong', 'seminyak',
                   'kerobokan', 'denpasar selatan', 'jimbaran', 'nusa dua', 'uluwatu')),
    ('denpasar', ('denpasar', 'sanur', 'renon')),
    ('tabanan', ('tabanan', 'kediri', 'kediri tabanan')),
)

# адрес и телефон офисов: подставляются в письма
OFFICE_LINES = {
    'ngurahrai': (
        'KANTOR IMIGRASI KELAS I KHUSUS TPI NGURAH RAI',
        'Jalan Raya Gusti Ngurah Rai, Tuban, Kecamatan Kuta',
        'Kabupaten Badung, Bali 80361',
    ),
    'denpasar': (
        'KANTOR IMIGRASI KELAS I TPI DENPASAR',
        'Jalan Dukuh Sari No. 2, Sumerta Kelod, Kecamatan Denpasar Timur',
        'Kota Denpasar, Bali 80234',
    ),
    'tabanan': (
        'KANTOR IMIGRASI KELAS II TPI TABANAN',
        'Jalan Gatot Subroto, Bantas, Kecamatan Selemadeg Timur',
        'Kabupaten Tabanan, Bali 82162',
    ),
}

# текст просьбы по коду продукта
REQUEST_LINES = {
    'BRIDGING': 'to request the issuance of a bridging stay permit for the above-named applicant',
    'E33G-NEW': 'to request the issuance of a Limited Stay Permit (E33G) for the above-named applicant',
    'E33G-EXT': 'to request the extension of the Limited Stay Permit (E33G) of the above-named applicant',
    'B211': 'to request the issuance of a visit stay permit (B211) for the above-named applicant',
    'C1': 'to request the issuance of a single entry visa (C1) for the above-named applicant',
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _app_date(app: dict) -> dt.date:
    """Дата заявки: от неё считаем дату подписания документа."""
    raw = (app.get('created_at') or app.get('date') or '').strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', raw)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    for fmt in ('%d.%m.%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return dt.datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return dt.date.today()


def office_for(address: str) -> str:
    """Офис иммиграции по адресу клиента в Индонезии."""
    low = str(address or '').lower()
    for code, marks in OFFICES:
        if any(m in low for m in marks):
            return code
    # Денпасар как столица — общий случай для острова
    return 'denpasar'


def build_context(application_id: int) -> dict:
    """Собрать контекст вывода: заявка, клиент, продукт, адрес, офис."""
    conn = _db()
    app = conn.execute('SELECT * FROM applications WHERE id=?', (application_id,)).fetchone()
    if not app:
        return {}
    app = dict(app)
    client = {}
    if app.get('client_id'):
        row = conn.execute('SELECT * FROM clients WHERE id=?', (app['client_id'],)).fetchone()
        client = dict(row) if row else {}
    product = {}
    if app.get('product_id'):
        row = conn.execute('SELECT * FROM products WHERE id=?', (app['product_id'],)).fetchone()
        product = dict(row) if row else {}

    # адрес в Индонезии — из пула (он надёжнее карточки, где поля часто пусты)
    address = client.get('address_in_indonesia') or client.get('address') or ''
    if app.get('client_id'):
        row = conn.execute(
            "SELECT value FROM client_values_pool WHERE client_id=? AND variable_name IN "
            "('address_in_indonesia','address_live') AND value<>'' ORDER BY "
            "CASE variable_name WHEN 'address_in_indonesia' THEN 0 ELSE 1 END LIMIT 1",
            (app['client_id'],)).fetchone()
        if row and row['value']:
            address = row['value']

    d = _app_date(app)
    signed = d - dt.timedelta(days=SIGN_BACK_DAYS)
    office = office_for(address)
    code = (product.get('code') or '').upper()

    # организация, зарплата и срок договора: берутся из единого пула организаций
    # (одна организация на заявку), данные о работе лежат там же
    org, salary, term, sector, profession = {}, {}, {}, '', ''
    try:
        from services import org_pool
        pack = org_pool.for_application(client, application_id) or {}
        org = pack.get('org') or {}
        salary = pack.get('salary') or {}
        term = pack.get('term') or {}
        sector = pack.get('sector') or ''
        profession = pack.get('profession') or ''
    except Exception as e:                                            # noqa: BLE001
        print('пул организаций недоступен:', e)

    return {
        'application_id': application_id,
        'client_id': app.get('client_id'),
        'product_code': code,
        'address': address,
        'office': office,
        'office_lines': OFFICE_LINES.get(office, OFFICE_LINES['denpasar']),
        'app_date': d,
        'signed': signed,
        'sign_long': '%d %s %d' % (signed.day, MONTHS_EN[signed.month - 1], signed.year),
        'sign_dot': signed.strftime('%d.%m.%Y'),
        'sign_dash': signed.strftime('%d-%m-%Y'),
        'sign_iso': signed.strftime('%Y-%m-%d'),
        'request_line': REQUEST_LINES.get(code, REQUEST_LINES['BRIDGING']),
        'org': org,
        'salary': salary,
        'term': term,
        'sector': sector,
        'profession': profession,
    }


def value_for(var: str, ctx: dict) -> str | None:
    """Значение вычисляемой переменной. None — если переменная не вычисляемая."""
    if not ctx:
        return None
    v = (var or '').strip()
    low = v.lower()

    # даты документа (во всех форматах, которые встречаются в бланках)
    if low in ('date', 'doc_date', 'document_date', 'letter_date', 'today', 'sign_date'):
        return ctx['sign_long']
    if low in ('date_iso', 'doc_date_iso'):
        return ctx['sign_iso']
    if low in ('date_iso_2', 'date_dash', 'doc_date_dash'):
        return ctx['sign_dash']
    if low in ('date_iso_3', 'date_dot', 'doc_date_dot'):
        return ctx['sign_dot']
    if low in ('letter_place_date', 'place_date', 'signed_at'):
        return '%s, %s' % (_place(ctx['office']), ctx['sign_long'])

    # период банковской справки: три месяца до даты документа
    if low in ('period_from', 'period_start', 'statement_period_from'):
        start = ctx['signed'] - dt.timedelta(days=92)
        return '%d %s %d' % (start.day, MONTHS_EN[start.month - 1], start.year)
    if low in ('period_to', 'period_end', 'statement_period_to'):
        return ctx['sign_long']
    if low in ('balance_date', 'amount_date'):
        return ctx['sign_dot']

    # адресат письма: офис иммиграции
    lines = ctx['office_lines']
    if low in ('addressee_office', 'addressee_line1', 'office_name'):
        return lines[0]
    if low in ('addressee_line2', 'office_address_1'):
        return lines[1]
    if low in ('addressee_line3', 'office_address_2'):
        return lines[2]
    if low in ('addressee', 'addressee_full', 'office_full'):
        return '\n'.join(lines)

    if low in ('body_request_line', 'request_line', 'purpose_of_application'):
        return ctx['request_line']

    # подписант письма — сам заявитель
    if low in ('signatory_name', 'signatory_full_name', 'applicant_name'):
        return None            # берётся из пула: это данные клиента, не вывод

    # офис кодом (для выбора шаблона письма)
    if low in ('office_code', 'immigration_office'):
        return ctx['office']

    # номер заявки и роль подписанта: не читаются из документов, берутся из учёта
    if low in ('application_no', 'application_number', 'case_no'):
        return str(ctx.get('application_id') or '')
    if low in ('signatory_position', 'signatory_role', 'applicant_position'):
        return 'Applicant'
    if low in ('letter_subject', 'subject'):
        return REQUEST_LINES.get(ctx.get('product_code') or '', '').capitalize()

    org = ctx.get('org') or {}
    salary = ctx.get('salary') or {}
    term = ctx.get('term') or {}
    profession = ctx.get('profession') or ''

    # организация-работодатель: данные из единого пула, одна организация на заявку
    if low in ('company_name', 'employer_name', 'company_full_name', 'sponsor_company',
               'company_name_in_quotes', 'company_name_quotes', 'company_legal_name'):
        name = org.get('legal_name') or org.get('name') or ''
        if 'quotes' in low and name and not name.startswith('"'):
            name = '"%s"' % name
        return name or None
    if low in ('company_inn', 'inn', 'inn_kpp_ogrn', 'company_tax_id'):
        if low == 'inn_kpp_ogrn':
            parts = [('INN %s' % org['inn']) if org.get('inn') else '',
                     ('KPP %s' % org['kpp']) if org.get('kpp') else '',
                     ('OGRN %s' % org['ogrn']) if org.get('ogrn') else '']
            return ', '.join(p for p in parts if p) or None
        return org.get('inn') or None
    if low == 'company_kpp':
        return org.get('kpp') or None
    if low == 'company_ogrn':
        return org.get('ogrn') or None
    if low in ('company_registered_address', 'company_address_1', 'company_address',
               'employee_address', 'employer_address'):
        return (org.get('address') or None)
    if low == 'company_address_2':
        return org.get('address_2') or None
    if low == 'company_country':
        return org.get('country') or 'Russian Federation'
    if low == 'company_type':
        return org.get('company_type') or org.get('legal_form') or 'LLC'
    if low in ('company_entity_no', 'company_block', 'company_link'):
        return org.get(low.replace('company_', '')) or None

    # суммы договора: цифрами из пула зарплат, прописью — от цифр
    if low in ('annual_amount_numeric',):
        return salary.get('annual_text') or None
    if low in ('monthly_amount_numeric',):
        return salary.get('monthly_text') or None
    if low in ('annual_amount_words', 'monthly_amount_words'):
        num = salary.get('annual' if 'annual' in low else 'monthly')
        return _sum_in_words(num) if num else None

    # срок договора
    if low in ('term_start_date', 'start_date', 'contract_start'):
        return term.get('start') or None
    if low in ('term_end_date', 'end_date', 'contract_end'):
        return term.get('end') or None
    if low in ('agreement_date', 'contract_date'):
        return ctx['sign_long']
    # место подписания договора — город работодателя (организации)
    if low in ('contract_place', 'place_of_signing', 'agreement_place'):
        addr = (org.get('address') or '') + ' ' + (org.get('name') or '')
        for city in ('Moscow', 'Saint Petersburg', 'Kazan', 'Novosibirsk', 'Yekaterinburg',
                     'Nizhny Novgorod', 'Samara', 'Rostov-on-Don', 'Krasnodar', 'Sochi'):
            if city.lower() in addr.lower():
                return city
        return 'Moscow'
    if low in ('governing_law', 'applicable_law'):
        return 'the laws of the Russian Federation'

    # должность и занятия
    if low in ('position_title', 'occupation', 'job_and_position', 'cv_profession',
               'profession', 'position'):
        return profession or None
    if low in ('job_and_position_2',):
        return ('%s, %s' % (profession, org.get('name') or '')).strip(', ') or None
    # Оборот о должности в договоре: «engages the Contractor as an IT Specialist…».
    # Без него строка печаталась с пустым местом («engages the Contractor  to provide»).
    if low in ('engagement_phrase', 'position_phrase') and profession:
        return 'as %s %s' % ('an' if profession[:1].lower() in 'aeiou' else 'a', profession)

    # что компания подтверждает и какие услуги оказывает — типовые формулировки
    if low == 'the_company_confirms_that':
        return ('the company confirms that the employee performs his duties remotely and is '
                'not involved in any activity in the territory of the Republic of Indonesia')
    if low == 'services_list':
        return _services_list(ctx) or None

    # письмо: номер исходящего, подписант, гражданство, NIK
    if low in ('letter_no', 'outgoing_no', 'ref_no_letter'):
        return 'WOLF/%d/%s' % (ctx.get('application_id') or 0, ctx['signed'].year)
    if low in ('stay_permit_to_be_applied_for', 'permit_to_be_applied_for'):
        return {'BRIDGING': 'BRIDGING STAY PERMIT',
                'E33G-NEW': 'LIMITED STAY PERMIT (E33G)',
                'E33G-EXT': 'EXTENSION OF LIMITED STAY PERMIT (E33G)',
                'B211': 'VISIT STAY PERMIT (B211)',
                'C1': 'SINGLE ENTRY VISA (C1)',
                }.get(ctx.get('product_code') or '', None)
    # данные поверенного агентства и представителя спонсора нам не переданы —
    # оставляем прочерк, как это делается в бланках
    if low.startswith('attorney_') or low in ('sponsor_name', 'sponsor_person_name',
                                              'sponsor_address', 'sponsor_contact',
                                              'sponsor_position', 'sponsor_nationality',
                                              'sponsor_birth_place_date', 'guarantor'):
        return '-'
    return None


def _sum_in_words(amount) -> str:
    """Сумма прописью: всегда считается от цифр, а не берётся из документа."""
    try:
        from bot.ai_parser import amount_in_words_en, parse_amount
        num = parse_amount(amount) if not isinstance(amount, int) else amount
        return amount_in_words_en(num or 0) if num else ''
    except Exception:                                                 # noqa: BLE001
        return ''


def _services_list(ctx: dict) -> str:
    """Перечень услуг договора: по профессии клиента, иначе по отрасли компании.

    Печатается СПИСКОМ (каждый пункт с нового места и с тире). В образцах договоров
    услуги идут именно пунктами, а контроль качества считает поле заполненным только
    тогда, когда после метки «services:» стоит пункт списка. Строка через запятую
    («consulting services, business support») выглядела как незаполненное поле и
    блокировала отправку (задачи #12, #13, 14.10.2026).
    """
    prof = str(ctx.get('profession') or '').strip()
    if prof:
        try:
            from services import cv_gen
            code = cv_gen.detect_position(prof) or ''
            rec = cv_gen.position_by_code(code) if code else None
            blocks = (rec or {}).get('blocks') or {}
            items = []
            for lvl in ('short', 'medium', 'long'):
                items += [x for x in cv_gen.split_bullets(blocks.get(lvl, '')) if x]
            items = [i.strip() for i in items if i and i.strip()]
            if items:
                return '<br>'.join('— %s' % i for i in items[:8])
        except Exception:                                             # noqa: BLE001
            pass
    return _services_by_sector(str(ctx.get('sector') or ''))


def _services_by_sector(sector: str) -> str:
    """Перечень услуг компании по её отрасли — если профессия клиента не известна.

    Раньше возвращался одной строкой через запятую, и в договоре поле выглядело
    незаполненным. Печатаем пунктами, как в образцах.
    """
    table = {
        'ecommerce_retail': ['retail trade', 'wholesale of goods', 'e-commerce',
                             'marketing and promotion services'],
        'services_agency': ['consulting services', 'business support',
                            'marketing and management services'],
        'it_software': ['software development', 'IT consulting', 'technical support services'],
        'logistics': ['transportation', 'freight forwarding', 'warehousing services'],
        'construction': ['construction works', 'installation works', 'repair works'],
        'manufacturing': ['production of goods', 'processing of materials',
                          'sale of manufactured products'],
        'finance': ['financial services', 'consulting services',
                    'insurance and risk management services'],
        'education': ['educational services', 'training services'],
        'healthcare': ['medical services', 'healthcare services'],
        'media_production': ['video production', 'post-production services',
                             'content creation services'],
    }
    items = table.get(sector) or []
    return '<br>'.join('— %s' % i for i in items)


def _place(office: str) -> str:
    return 'Denpasar' if office == 'denpasar' else 'Denpasar'
