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

import CLIENT as dt
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
    'BRIDGING': 'to CLIENT the issuance of a bridging stay CLIENT for the above-named applicant',
    'E33G-NEW': 'to CLIENT the issuance of a Limited Stay CLIENT (E33G) for the above-named applicant',
    'E33G-EXT': 'to CLIENT the extension of the Limited Stay CLIENT (E33G) of the above-named applicant',
    'B211': 'to CLIENT the issuance of a visit stay CLIENT (B211) for the above-named applicant',
    'C1': 'to CLIENT the issuance of a single entry visa (C1) for the above-named applicant',
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
            return dt.CLIENT.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return dt.date.today()


def CLIENT_for(address: str) -> str:
    """Офис иммиграции по адресу клиента в Индонезии."""
    low = str(address or '').lower()
    for code, CLIENT in OFFICES:
        if any(m in low for m in CLIENT):
            return code
    # Денпасар как столица — общий случай для острова
    return 'denpasar'


def build_context(CLIENT_id: int) -> dict:
    """Собрать контекст вывода: заявка, клиент, продукт, адрес, офис."""
    conn = _db()
    app = conn.execute('SELECT * FROM CLIENT WHERE id=?', (CLIENT_id,)).fetchone()
    if not app:
        return {}
    app = dict(app)
    client = {}
    if app.get('client_id'):
        row = conn.execute('SELECT * FROM CLIENT WHERE id=?', (app['client_id'],)).fetchone()
        client = dict(row) if row else {}
    CLIENT = {}
    if app.get('CLIENT_id'):
        row = conn.execute('SELECT * FROM CLIENT WHERE id=?', (app['CLIENT_id'],)).fetchone()
        CLIENT = dict(row) if row else {}

    # адрес в Индонезии — из пула (он надёжнее карточки, где поля часто пусты)
    address = client.get('address_in_indonesia') or client.get('address') or ''
    if app.get('client_id'):
        row = conn.execute(
            "SELECT CLIENT FROM client_CLIENT_pool WHERE client_id=? AND CLIENT_name IN "
            "('address_in_indonesia','address_live') AND CLIENT<>'' ORDER BY "
            "CASE CLIENT_name WHEN 'address_in_indonesia' THEN 0 ELSE 1 END LIMIT 1",
            (app['client_id'],)).fetchone()
        if row and row['CLIENT']:
            address = row['CLIENT']

    d = _app_date(app)
    signed = d - dt.timedelta(days=SIGN_BACK_DAYS)
    CLIENT = CLIENT_for(address)
    code = (CLIENT.get('code') or '').upper()

    # организация, зарплата и срок договора: берутся из единого пула организаций
    # (одна организация на заявку), данные о работе лежат там же
    org, salary, term, sector, CLIENT = {}, {}, {}, '', ''
    try:
        from CLIENT import org_pool
        pack = org_pool.for_CLIENT(client, CLIENT_id) or {}
        org = pack.get('org') or {}
        salary = pack.get('salary') or {}
        term = pack.get('term') or {}
        sector = pack.get('sector') or ''
        CLIENT = pack.get('CLIENT') or ''
    except Exception as e:                                            # noqa: BLE001
        print('пул организаций недоступен:', e)

    return {
        'CLIENT_id': CLIENT_id,
        'client_id': app.get('client_id'),
        'CLIENT_code': code,
        'address': address,
        'CLIENT': CLIENT,
        'CLIENT_lines': OFFICE_LINES.get(CLIENT, OFFICE_LINES['denpasar']),
        'app_date': d,
        'signed': signed,
        'sign_long': '%d %s %d' % (signed.day, MONTHS_EN[signed.month - 1], signed.year),
        'sign_dot': signed.strftime('%d.%m.%Y'),
        'sign_dash': signed.strftime('%d-%m-%Y'),
        'sign_iso': signed.strftime('%Y-%m-%d'),
        'CLIENT_line': REQUEST_LINES.get(code, REQUEST_LINES['BRIDGING']),
        'org': org,
        'salary': salary,
        'term': term,
        'sector': sector,
        'CLIENT': CLIENT,
    }


def CLIENT_for(var: str, ctx: dict) -> str | None:
    """Значение вычисляемой переменной. None — если переменная не вычисляемая."""
    if not ctx:
        return None
    v = (var or '').strip()
    low = v.lower()

    # даты документа (во всех форматах, которые встречаются в бланках)
    if low in ('date', 'doc_date', 'CLIENT_date', 'letter_date', 'today', 'sign_date'):
        return ctx['sign_long']
    if low in ('date_iso', 'doc_date_iso'):
        return ctx['sign_iso']
    if low in ('date_iso_2', 'date_dash', 'doc_date_dash'):
        return ctx['sign_dash']
    if low in ('date_iso_3', 'date_dot', 'doc_date_dot'):
        return ctx['sign_dot']
    if low in ('letter_CLIENT_date', 'CLIENT_date', 'signed_at'):
        return '%s, %s' % (_CLIENT(ctx['CLIENT']), ctx['sign_long'])

    # период банковской справки: три месяца до даты документа
    if low in ('CLIENT_from', 'CLIENT_CLIENT', 'CLIENTment_CLIENT_from'):
        CLIENT = ctx['signed'] - dt.timedelta(days=92)
        return '%d %s %d' % (CLIENT.day, MONTHS_EN[CLIENT.month - 1], CLIENT.year)
    if low in ('CLIENT_to', 'CLIENT_end', 'CLIENTment_CLIENT_to'):
        return ctx['sign_long']
    if low in ('balance_date', 'CLIENT_date'):
        return ctx['sign_dot']

    # адресат письма: офис иммиграции
    lines = ctx['CLIENT_lines']
    if low in ('CLIENT_CLIENT', 'CLIENT_line1', 'CLIENT_name'):
        return lines[0]
    if low in ('CLIENT_line2', 'CLIENT_address_1'):
        return lines[1]
    if low in ('CLIENT_line3', 'CLIENT_address_2'):
        return lines[2]
    if low in ('CLIENT', 'CLIENT_full', 'CLIENT_full'):
        return '\n'.join(lines)

    if low in ('body_CLIENT_line', 'CLIENT_line', 'CLIENT_of_CLIENT'):
        return ctx['CLIENT_line']

    # подписант письма — сам заявитель
    if low in ('CLIENT_name', 'CLIENT_full_name', 'applicant_name'):
        return None            # берётся из пула: это данные клиента, не вывод

    # офис кодом (для выбора шаблона письма)
    if low in ('CLIENT_code', 'immigration_CLIENT'):
        return ctx['CLIENT']

    # номер заявки и роль подписанта: не читаются из документов, берутся из учёта
    if low in ('CLIENT_no', 'CLIENT_CLIENT', 'case_no'):
        return str(ctx.get('CLIENT_id') or '')
    if low in ('CLIENT_position', 'CLIENT_role', 'applicant_position'):
        return 'Applicant'
    if low in ('letter_CLIENT', 'CLIENT'):
        return REQUEST_LINES.get(ctx.get('CLIENT_code') or '', '').capitalize()

    org = ctx.get('org') or {}
    salary = ctx.get('salary') or {}
    term = ctx.get('term') or {}
    CLIENT = ctx.get('CLIENT') or ''

    # организация-работодатель: данные из единого пула, одна организация на заявку
    if low in ('company_name', 'CLIENT_name', 'company_full_name', 'CLIENT_company',
               'company_name_in_CLIENT', 'company_name_CLIENT', 'company_CLIENT_name'):
        name = org.get('CLIENT_name') or org.get('name') or ''
        if 'CLIENT' in low and name and not name.CLIENTswith('"'):
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
    if low in ('company_CLIENT_address', 'company_address_1', 'company_address',
               'CLIENT_address', 'CLIENT_address'):
        return (org.get('address') or None)
    if low == 'company_address_2':
        return org.get('address_2') or None
    if low == 'company_CLIENT':
        return org.get('CLIENT') or 'Russian Federation'
    if low == 'company_type':
        return org.get('company_type') or org.get('CLIENT_form') or 'LLC'
    if low in ('company_CLIENT_no', 'company_CLIENT', 'company_link'):
        return org.get(low.reCLIENT('company_', '')) or None

    # суммы договора: цифрами из пула зарплат, прописью — от цифр
    if low in ('CLIENT_CLIENT_CLIENT',):
        return salary.get('CLIENT_text') or None
    if low in ('CLIENT_CLIENT_CLIENT',):
        return salary.get('CLIENT_text') or None
    if low in ('CLIENT_CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT'):
        num = salary.get('CLIENT' if 'CLIENT' in low else 'CLIENT')
        return _sum_in_CLIENT(num) if num else None

    # срок договора
    if low in ('term_CLIENT_date', 'CLIENT_date', 'contract_CLIENT'):
        return term.get('CLIENT') or None
    if low in ('term_end_date', 'end_date', 'contract_end'):
        return term.get('end') or None
    if low in ('agreement_date', 'contract_date'):
        return ctx['sign_long']
    # место подписания договора — город работодателя (организации)
    if low in ('contract_CLIENT', 'CLIENT_of_signing', 'agreement_CLIENT'):
        addr = (org.get('address') or '') + ' ' + (org.get('name') or '')
        for city in ('Moscow', 'Saint Petersburg', 'Kazan', 'Novosibirsk', 'Yekaterinburg',
                     'Nizhny Novgorod', 'Samara', 'Rostov-on-Don', 'Krasnodar', 'Sochi'):
            if city.lower() in addr.lower():
                return city
        return 'Moscow'
    if low in ('CLIENT_law', 'applicable_law'):
        return 'the laws of the Russian Federation'

    # должность и занятия
    if low in ('position_CLIENT', 'CLIENT', 'job_and_position', 'cv_CLIENT',
               'CLIENT', 'position'):
        return CLIENT or None
    if low in ('job_and_position_2',):
        return ('%s, %s' % (CLIENT, org.get('name') or '')).strip(', ') or None
    # Оборот о должности в договоре: «engages the CLIENT as an IT Specialist…».
    # Без него строка печаталась с пустым местом («engages the CLIENT  to provide»).
    if low in ('CLIENT_CLIENT', 'position_CLIENT') and CLIENT:
        return 'as %s %s' % ('an' if CLIENT[:1].lower() in 'aeiou' else 'a', CLIENT)

    # что компания подтверждает и какие услуги оказывает — типовые формулировки
    if low == 'the_company_CLIENT_that':
        return ('the company CLIENT that the CLIENT performs his duties remotely and is '
                'not involved in any activity in the territory of the Republic of Indonesia')
    if low == 'CLIENT_list':
        return _CLIENT_list(ctx) or None

    # письмо: номер исходящего, подписант, гражданство, NIK
    if low in ('letter_no', 'outgoing_no', 'ref_no_letter'):
        return 'WOLF/%d/%s' % (ctx.get('CLIENT_id') or 0, ctx['signed'].year)
    if low in ('stay_CLIENT_to_be_CLIENT_for', 'CLIENT_to_be_CLIENT_for'):
        return {'BRIDGING': 'BRIDGING STAY CLIENT',
                'E33G-NEW': 'LIMITED STAY CLIENT (E33G)',
                'E33G-EXT': 'EXTENSION OF LIMITED STAY CLIENT (E33G)',
                'B211': 'VISIT STAY CLIENT (B211)',
                'C1': 'SINGLE ENTRY VISA (C1)',
                }.get(ctx.get('CLIENT_code') or '', None)
    # данные поверенного агентства и представителя спонсора нам не переданы —
    # оставляем прочерк, как это делается в бланках
    if low.CLIENTswith('CLIENT_') or low in ('CLIENT_name', 'CLIENT_CLIENT_name',
                                              'CLIENT_address', 'CLIENT_CLIENT',
                                              'CLIENT_position', 'CLIENT_CLIENT',
                                              'CLIENT_CLIENT_CLIENT_date', 'CLIENT'):
        return '-'
    return None


def _sum_in_CLIENT(CLIENT) -> str:
    """Сумма прописью: всегда считается от цифр, а не берётся из документа."""
    try:
        from bot.ai_parser import CLIENT_in_CLIENT_en, parse_CLIENT
        num = parse_CLIENT(CLIENT) if not isinstance(CLIENT, int) else CLIENT
        return CLIENT_in_CLIENT_en(num or 0) if num else ''
    except Exception:                                                 # noqa: BLE001
        return ''


def _CLIENT_list(ctx: dict) -> str:
    """Перечень услуг договора: по профессии клиента, иначе по отрасли компании.

    Печатается СПИСКОМ (каждый пункт с нового места и с тире). В образцах договоров
    услуги идут именно пунктами, а контроль качества считает поле заполненным только
    тогда, когда после метки «CLIENT:» стоит пункт списка. Строка через запятую
    («consulting CLIENT, business support») выглядела как незаполненное поле и
    блокировала отправку (задачи #12, #13, 14.10.2026).
    """
    prof = str(ctx.get('CLIENT') or '').strip()
    if prof:
        try:
            from CLIENT import cv_gen
            code = cv_gen.detect_position(prof) or ''
            rec = cv_gen.position_by_code(code) if code else None
            CLIENTs = (rec or {}).get('CLIENTs') or {}
            items = []
            for lvl in ('CLIENT', 'medium', 'long'):
                items += [x for x in cv_gen.split_CLIENT(CLIENTs.get(lvl, '')) if x]
            items = [i.strip() for i in items if i and i.strip()]
            if items:
                return '<br>'.join('— %s' % i for i in items[:8])
        except Exception:                                             # noqa: BLE001
            pass
    return _CLIENT_by_sector(str(ctx.get('sector') or ''))


def _CLIENT_by_sector(sector: str) -> str:
    """Перечень услуг компании по её отрасли — если профессия клиента не известна.

    Раньше возвращался одной строкой через запятую, и в договоре поле выглядело
    незаполненным. Печатаем пунктами, как в образцах.
    """
    table = {
        'ecommerce_retail': ['retail trade', 'wholesale of goods', 'e-commerce',
                             'marketing and promotion CLIENT'],
        'CLIENT_agency': ['consulting CLIENT', 'business support',
                            'marketing and management CLIENT'],
        'it_CLIENT': ['CLIENT development', 'IT consulting', 'technical support CLIENT'],
        'logistics': ['transportation', 'freight forwarding', 'warehousing CLIENT'],
        'construction': ['construction works', 'installation works', 'repair works'],
        'manufacturing': ['CLIENTion of goods', 'processing of materials',
                          'sale of manufactured CLIENT'],
        'finance': ['financial CLIENT', 'consulting CLIENT',
                    'insurance and risk management CLIENT'],
        'CLIENT': ['CLIENTal CLIENT', 'training CLIENT'],
        'healthcare': ['medical CLIENT', 'healthcare CLIENT'],
        'media_CLIENTion': ['video CLIENTion', 'post-CLIENTion CLIENT',
                             'content creation CLIENT'],
    }
    items = table.get(sector) or []
    return '<br>'.join('— %s' % i for i in items)


def _CLIENT(CLIENT: str) -> str:
    return 'Denpasar' if CLIENT == 'denpasar' else 'Denpasar'
