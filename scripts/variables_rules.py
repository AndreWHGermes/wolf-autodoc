"""Правила формирования каждой переменной: откуда берётся, как считается, где повторяется.

Собирает по всем 16 шаблонам:
  1) семейство переменной (по имени) → правило формирования и источник;
  2) фактические значения из базы (variable_value_history: 5407 записей, used_count, approved);
  3) в каких документах пакета переменная повторяется (docs/packs_by_product.json);
  4) заметку из карточки переменной (rule_note) и вычисление в коде (variables_guide.json).

Семейства описаны один раз — так правило одно и то же в любом документе, а документы
внутри продукта получают согласованные значения (см. решение работать по продуктам).

Выход: docs/VARIABLES_RULES.md, docs/variables_rules.json
"""
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
OUT_MD = ROOT / 'docs' / 'VARIABLES_RULES.md'
OUT_JSON = ROOT / 'docs' / 'variables_rules.json'
PACKS = ROOT / 'docs' / 'packs_by_product.json'
GUIDE = Path('/root/.hermes/cache/scratch/variables_guide.json')

# семейство → (как формируется, источник, документ-источник данных клиента)
FAMILIES = [
    (r'^(passport_no|passport_number|passport_series|intl_passport)$',
     'Номер паспорта клиента — переносится в документ как есть, латиницей, без пробелов.',
     'загранпаспорт клиента', 'загранпаспорт'),
    (r'^(passport_issued_by|passport_issue_date|passport_expiry|passport_code)$',
     'Паспортные данные клиента: кем выдан / дата выдачи / действует до — из загранпаспорта.',
     'загранпаспорт клиента', 'загранпаспорт'),
    (r'^(full_name_latin|full_name_title|employee_name|employee_full_name|employee_short|client_name|signer_name|contractor_full_name|surname|sponsor_name|sponsor_person_name|attorney_name)$',
     'Имя в документе — транслитерация ФИО клиента (латиница), как в загранпаспорте. '
     'Одна и та же строка идёт во все документы пакета, поэтому берётся из карточки один раз.',
     'карточка клиента (латиница)', 'загранпаспорт'),
    (r'^(date_of_birth|birth_date|client_dob)$',
     'Дата рождения клиента из карточки; формат — как в бланке (латиницей: DD Month YYYY).',
     'карточка клиента / загранпаспорт', 'загранпаспорт'),
    (r'^(place_of_birth|place_birth_inline|place_date|place_date_of_birth|place)$',
     'Место рождения клиента (город и страна), латиницей; в письмах — одна строка «Место, дата».',
     'карточка клиента / загранпаспорт', 'загранпаспорт'),
    (r'^(nationality|client_nationality|signatory_citizenship)$',
     'Гражданство клиента (или подписанта), латиницей — из паспорта.',
     'карточка клиента / загранпаспорт', 'загранпаспорт'),
    (r'^(client_gender|gender)$', 'Пол клиента — из карточки (влияет на Mr/Ms в письмах).',
     'карточка клиента', 'загранпаспорт'),
    (r'^(address_live|address_reg|address_in_indonesia|client_address|employee_address|address_zip|city|country)$',
     'Адрес: адрес проживания и регистрации — латиницей из карточки; в индонезийских письмах '
     'используется адрес пребывания в Индонезии.',
     'карточка клиента', 'адрес проживания'),
    (r'^(company_name_in_quotes|employer_name|company_full_name|company_type|company_country|company_entity_no|company_address_1|company_address_2|company_registered_address|company_block|company_link|company_inn|company_kpp|company_ogrn|inn_kpp_ogrn|company_director|company_llc)$',
     'Организация-работодатель: одна запись подбирается на заявку из пула организаций '
     '(вне Индонезии) и подставляется во все документы пакета — шапка, юр. название, адрес, '
     'ИНН/КПП/ОГРН. Если КПП или ОГРН нет — остаётся пустое место, имя переменной не пишется.',
     'пул организаций (data/organizations.json)', '—'),
    (r'^(position_title|occupation|cv_profession)$',
     'Должность: берётся из заявки или из пула должностей организации; новые профессии не заводятся.',
     'пул должностей организации / заявка', '—'),
    (r'^(services_list)$',
     'Перечень услуг по договору — типовой список из шаблона договора, при необходимости правится админом.',
     'шаблон договора / ввод администратора', '—'),
    (r'^(base_salary|annual_amount_numeric|annual_amount_words|monthly_amount_numeric|monthly_amount_words|salary_amount)$',
     'Сумма: 50% случаев — значение из архива реальных договоров, 50% — случайное в границах '
     '(4 980 000–7 680 000 ₽/год, 415 000–640 000 ₽/мес, шаг 1 000, без копеек); '
     'прописью — из того же числа, чтобы цифры и слова всегда совпадали.',
     'пул сумм (services/salary_pool.py)', '—'),
    (r'^(term_start_date|term_end_date|contract_date|agreement_date|contract_no)$',
     'Сроки и номер договора: дата — день формирования пакета, срок — 12 месяцев; '
     'номер договора один и тот же во всех документах пакета.',
     'расчёт системы (одна дата и один номер на заявку)', '—'),
    (r'^(date|date_iso|date_iso_2|date_iso_3|letter_place_date|doc_date|place_date_doc)$',
     'Дата документа: день формирования; цифрами и в индонезийском формате — из одной даты.',
     'расчёт системы', '—'),
    (r'^(letter_no|application_no|doc_no|ref_no|account_no|card_mask)$',
     'Служебный номер документа (письма/заявки/справки) — уникальный номер в рамках заявки.',
     'расчёт системы', '—'),
    (r'^(balance_rub|balance_date|period_from|period_to|bank_name)$',
     'Остаток и период справки банка — из справки клиента (или из карточки клиента).',
     'справка банка клиента', 'справка банка'),
    (r'^(itk_no|itk_expiry|stay_permit_no|existing_stay_permit|visa_no)$',
     'Данные действующего разрешения (ИТК/KITAS): номер и срок — из документа клиента; '
     'если документа нет — поле остаётся пустым.',
     'документы клиента (KITAS/ITK)', 'KITAS / ITK'),
    (r'^(purpose_of_application|stay_permit_to_be_applied_for|body_request_line|letter_subject|the_company_confirms_that)$',
     'Формулировка обращения — зависит от продукта заявки (мостовая/конверсия/продление), '
     'а не от документа: одна и та же в письме и в форме E-02.',
     'правило продукта (расчёт системы)', '—'),
    (r'^(addressee_office|addressee_line1|addressee_line2|addressee_line3)$',
     'Адресат письма — офис иммиграции выбирается по адресу клиента (Ngurah Rai / Denpasar / '
     'Tabanan); три строки адреса офиса — из справочника офисов.',
     'правило выбора офиса (services/offices.py)', '—'),
    (r'^(signatory_name|signatory_position|signatory_address|signatory_nik_or_dash|attorney_nik|attorney_address)$',
     'Подписант и представитель — постоянные лица компании (куратор и адвокат): имя, адрес, '
     'NIK/должность берутся из справочника, а не из карточки клиента.',
     'справочник подписантов', '—'),
    (r'^(cv_name|cv_date_of_birth|cv_place_of_birth|cv_nationality|cv_passport_no)$',
     'Резюме, личные данные (латиница) — из карточки клиента.',
     'карточка клиента', 'загранпаспорт'),
    (r'^(cv_summary|cv_job1_title|cv_job1_period|cv_job1_company|cv_job1_bullets|cv_job2_period|cv_job2_company|cv_job2_bullets|cv_languages|cv_skills_hard|cv_education_degree|cv_education_school|cv_education_years)$',
     'Резюме, опыт и образование — составляется один раз на клиента (ввод администратора); '
     'описание компании-работодателя формируется моделью, персональные данные не додумываются.',
     'ввод администратора / генерация модели', '—'),
    (r'^(sponsor_company|guarantor|signer_title|employee_full_name)$',
     'Гарант/подписант со стороны компании — из справочника организации заявки.',
     'справочник организации', '—'),
    (r'^(email|phone|telegram_username)$', 'Контакты клиента — из карточки (нужны для формы E-02).',
     'карточка клиента', '—'),
]


def family_of(name: str):
    for pat, rule, src, client_doc in FAMILIES:
        if re.match(pat, name or ''):
            return rule, src, client_doc
    return None


def main() -> int:
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    tpls = {r['id']: dict(r) for r in con.execute("SELECT * FROM templates")}
    scopes = {r['name']: dict(r) for r in con.execute("SELECT * FROM variable_scope")}
    # фактические значения из базы: чем чаще использовалось, тем показательнее пример
    hist = collections.defaultdict(list)
    for r in con.execute("SELECT variable_name, value, used_count, approved FROM variable_value_history "
                         "WHERE value IS NOT NULL AND value<>'' ORDER BY used_count DESC"):
        if len(hist[r['variable_name']]) < 5:
            hist[r['variable_name']].append((r['value'], r['used_count'], r['approved']))
    guide = {}
    if GUIDE.is_file():
        try:
            guide = json.loads(GUIDE.read_text(encoding='utf-8'))
        except Exception:
            guide = {}
    packs = {}
    if PACKS.is_file():
        try:
            packs = json.loads(PACKS.read_text(encoding='utf-8'))
        except Exception:
            packs = {}

    where_used = collections.defaultdict(set)
    for code, m in packs.items():
        for tcode, names in (m.get('variables') or {}).items():
            for n in names:
                where_used[n].add(tcode)

    md = ['# Правила формирования переменных', '',
          'Для каждого документа: какая переменная, по какому правилу формируется, откуда берётся, '
          'в каких ещё документах пакета повторяется. Примеры — реальные значения из базы.', '']
    stats = {'total': 0, 'covered': 0, 'no_rule': 0, 'no_docs': 0}
    machine = {}
    for tid, t in sorted(tpls.items(), key=lambda kv: kv[1].get('code') or ''):
        code = t.get('code') or '?'
        if not code:
            continue
        rows = con.execute("SELECT * FROM template_variables WHERE template_id=? "
                           "ORDER BY sort_order, name", (tid,)).fetchall()
        if not rows:
            continue
        md += ['', '## `%s` — %s' % (code, t.get('title') or ''), '']
        tpl_machine = []
        for r in rows:
            name = r['name']
            stats['total'] += 1
            fam = family_of(name)
            rule, src, client_doc = fam if fam else ('', '', '')
            note = re.sub(r'[ \t]+', ' ', str(r['rule_note'] or '')).strip()
            if not rule:
                rule = 'Правило из базы: ' + (note.split('Как ставится:')[-1].strip()[:300]
                                              if note else '— не описано —')
            if not src:
                src = {'client': 'карточка клиента', 'client_fact': 'карточка клиента / документ клиента',
                       'doc_service': 'служебное поле (система)', 'pool': 'пул значений',
                       'calc': 'расчёт системы', 'manual': 'ввод администратора',
                       'descriptive': 'текст подбирает система / модель'}.get(
                           r['source_kind'] or '', r['source_kind'] or '—')
                stats['no_rule'] += 1
            else:
                stats['covered'] += 1
            used = sorted(where_used.get(name, []))
            ex = hist.get(name) or []
            if not used:
                stats['no_docs'] += 1
            md.append('#### `%s`' % name)
            md.append('- **Правило:** %s' % rule)
            md.append('- **Источник:** %s%s' % (src, ' — из документа клиента: %s' % client_doc if client_doc else ''))
            if note and 'Как ставится:' in note:
                detail = note.split('Как ставится:')[-1].split('Если данных нет:')[0].strip()
                if detail and detail[:60].lower() not in rule.lower():
                    md.append('- **Как ставится (из базы правил):** %s' % detail[:600])
            elif note:
                md.append('- **Тип/пояснение из базы правил:** %s' % note[:400])
            md.append('- **Повторяется в пакете:** %s' %
                      (', '.join('`%s`' % u for u in used) if used else '— только в этом документе (или продукт не использует)'))
            md.append('- **Примеры из базы значений:** %s' %
                      ('; '.join('%s (×%s)' % (str(v)[:40], n) for v, n, _a in ex[:4]) or '— нет значений в базе —'))
            md.append('')
            tpl_machine.append({'name': name, 'rule': rule, 'source': src,
                                'client_doc': client_doc, 'used_in': used,
                                'examples': [v for v, _n, _a in ex[:5]],
                                'approved': any(a for _v, _n, a in ex)})
        machine[code] = tpl_machine
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    OUT_JSON.write_text(json.dumps(machine, ensure_ascii=False, indent=1), encoding='utf-8')
    print('правила переменных:', OUT_MD)
    print('шаблонов: %d | переменных: %d | с правилом: %d | без правила: %d | без привязки к пакету: %d'
          % (len(machine), stats['total'], stats['covered'], stats['no_rule'], stats['no_docs']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
