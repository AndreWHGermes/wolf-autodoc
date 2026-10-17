"""Единая инструкция для конструктора: способ формирования, варианты и сверка с описанием на сайте.

Для каждой переменной каждого действующего шаблона определяет:

  method  — как значение попадает в документ:
            client_card (из карточки клиента), client_doc (из документа клиента),
            pool (из справочника/пула), options (выбор из фиксированных вариантов),
            random_bounds (случайное значение в границах), computed (считается из других),
            product_rule (зависит от типа продукта), llm (текст подбирает модель),
            manual (вводит администратор), service (служебное поле документа);
  options — конечный список вариантов, если переменная их имеет (по истории значений);
  rule    — правило формирования словами;
  site    — что про неё написано в конструкторе сейчас (rule_note, source_kind);
  verdict — соответствует ли описание на сайте факту.

Выход: docs/GUIDE_FOR_SITE.md (для чтения), data/guide/guide.json (для сайта),
       docs/rules_vs_site.json (расхождения описаний).
"""
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
OUT_MD = ROOT / 'docs' / 'GUIDE_FOR_SITE.md'
OUT_GUIDE = ROOT / 'data' / 'guide' / 'guide.json'
OUT_DIFF = ROOT / 'docs' / 'rules_vs_site.json'
PACKS = ROOT / 'docs' / 'packs_by_product.json'

SOURCE_TO_METHOD = {
    'client': 'client_card', 'client_fact': 'client_card', 'doc_service': 'service',
    'pool': 'pool', 'calc': 'computed', 'manual': 'manual', 'descriptive': 'llm',
}

# семейство переменной → (метод, правило, источник-документ клиента)
RULES = [
    (r'^(annual_amount_numeric|annual_amount_words|monthly_amount_numeric|monthly_amount_words|base_salary|salary_amount)$',
     'random_bounds',
     'Сумма: половина случаев — значение из архива реальных договоров, половина — случайное в '
     'границах (4 980 000–7 680 000 ₽/год, 415 000–640 000 ₽/мес, шаг 1 000, без копеек). '
     'Прописью — всегда из того же числа, что и цифры.', ''),
    (r'^(company_inn|company_kpp|company_ogrn|inn_kpp_ogrn|inn_ogrn_line|company_name_in_quotes|employer_name|'
     r'company_full_name|company_type|company_country|company_entity_no|company_address_1|company_address_2|'
     r'company_registered_address|company_block|company_link|company_incorporated_phrase|company_llc|company_director)$',
     'pool',
     'Организация-работодатель: одна запись на заявку из пула организаций (вне Индонезии) — шапка, '
     'юр. название, адрес, ИНН/КПП/ОГРН, оборот о регистрации. Нет значения — пустое место, '
     'имя переменной не подставляется.', ''),
    (r'^(position_title|occupation|cv_profession|engagement_phrase|engagement_line|job_and_position)$',
     'pool', 'Должность: из заявки или из пула должностей организации; новые профессии не заводятся.', ''),
    (r'^(services_list|the_company_confirms_that|cv_summary)$', 'llm',
     'Текстовый блок (обязанности, подтверждение компании, описание опыта) — подбирается моделью по '
     'профессии и данным клиента; сохранённая админом версия приоритетнее генерации.', ''),
    (r'^(addressee_office|addressee_line1|addressee_line2|addressee_line3)$', 'options',
     'Адресат письма: офис иммиграции выбирается по адресу пребывания клиента — Ngurah Rai (юг Бадунга, '
     'аэропорт), Denpasar (город и Gianyar/Ubud), Tabanan (кабупатен Tabanan); три строки адреса — из '
     'справочника офисов. Пользователь может заменить офис вручную.', ''),
    (r'^(purpose_of_application|stay_permit_to_be_applied_for|body_request_line|letter_subject)$', 'product_rule',
     'Формулировка обращения зависит от типа продукта (мостовая / конверсия / продление) и одна и та же '
     'в письме и в форме E-02.', ''),
    (r'^(nationality|client_nationality)$', 'options',
     'Гражданство клиента. В индонезийские документы (письма, форма E-02) пишется как в индонезийской '
     'записи — RUSIA; в англоязычные договоры — RUSSIAN FEDERATION.', 'загранпаспорт'),
    (r'^(passport_no|passport_number|passport_series|intl_passport|passport_code)$', 'client_doc',
     'Номер и серия паспорта — переносятся из загранпаспорта клиента как есть, латиницей, без пробелов.', 'загранпаспорт'),
    (r'^(passport_issued_by|passport_issue_date|passport_expiry|passport_valid_until|cv_passport_issue|cv_passport_expiry)$',
     'client_doc', 'Паспортные данные: кем выдан, дата выдачи, действует до — из загранпаспорта клиента.', 'загранпаспорт'),
    (r'^(full_name_latin|full_name_title|employee_name|employee_full_name|employee_short|client_name|surname|'
     r'signer_name|contractor_full_name|sponsor_name|sponsor_person_name|attorney_name|cv_name)$', 'client_card',
     'ФИО клиента латиницей, полностью (ФАМИЛИЯ ИМЯ ОТЧЕСТВО): карточка клиента → строка «ФИО» в заявке → '
     'машиночитаемая строка паспорта. Нет отчества — две части. Одно значение идёт во все документы пакета.',
     'загранпаспорт'),
    (r'^(date_of_birth|birth_date|client_dob|cv_date_of_birth)$', 'client_card',
     'Дата рождения клиента из карточки; формат — как в бланке (латиницей: DD Month YYYY).', 'загранпаспорт'),
    (r'^(place_of_birth|place_birth_inline|place_date|place_date_of_birth|place|cv_place_of_birth)$', 'client_card',
     'Место рождения (город и страна) латиницей; в письмах — строка «Место, дата».', 'загранпаспорт'),
    (r'^(client_gender|gender)$', 'client_card', 'Пол клиента — из карточки (определяет Mr/Ms в письмах).', 'загранпаспорт'),
    (r'^(address_live|address_reg|address_in_indonesia|client_address|employee_address|address_zip|city|country)$',
     'client_card', 'Адрес проживания/регистрации латиницей из карточки; в индонезийских письмах — адрес '
     'пребывания в Индонезии.', 'адрес проживания'),
    (r'^(email|phone|telegram_username)$', 'client_card', 'Контакты клиента из карточки (для формы E-02).', ''),
    (r'^(itk_no|itk_expiry|stay_permit_no|existing_stay_permit|visa_no|bridging_visa_no)$', 'client_doc',
     'Данные действующего разрешения (KITAS/ITK): номер и срок — из документа клиента; документа нет — '
     'поле пустое.', 'KITAS / ITK'),
    (r'^(balance_rub|balance_date|period_from|period_to|balance_words|bank_name|account_no|card_mask|ref_no|doc_no|contract_no|contract_date)$',
     'client_doc', 'Данные банковской справки (остаток, период, номер, счёт) — из справки клиента; '
     'период справки задаёт продукт: 3 месяца (C1, D12, E33G-EXT) или 12 месяцев (E33G-NEW).', 'справка банка'),
    (r'^(addressee_|letter_no|application_no|date|date_iso|letter_place_date|place_date_doc|doc_date)$', 'service',
     'Служебные поля документа: номер и дата формируются системой, один номер и одна дата на всю заявку.', ''),
    (r'^(term_start_date|term_end_date|agreement_date)$', 'computed',
     'Срок договора: начало — дата формирования пакета, окончание — +5 лет; одна дата на всю заявку.', ''),
    (r'^(signatory_name|signatory_position|signatory_address|signatory_nik_or_dash|signatory_citizenship|'
     r'signatory_person_name|signatory_name_2|attorney_nik|attorney_address|attorney_citizenship|attorney_occupation)$',
     'manual', 'Подписант и представитель — постоянные лица компании, берутся из справочника; подпись и '
     'печать ставятся руками.', ''),
    (r'^(cv_job2_title|cv_job1_title|cv_job1_period|cv_job1_company|cv_job1_bullets|cv_job2_period|cv_job2_company|'
     r'cv_job2_bullets|cv_job3_title|cv_job3_company|cv_job3_period|cv_languages|cv_skills_hard|cv_skills_soft|'
     r'cv_skills_tools|cv_education_degree|cv_education_school|cv_education_years|cv_education_note|client_photo_url)$',
     'manual', 'Резюме: опыт, образование, навыки — заполняет администратор (или генерация по профессии); '
     'персональные данные не выдумываются.', ''),
    (r'^(sponsor_company|sponsor_company_details|guarantor|signer_title)$', 'manual',
     'Гарант/подписант со стороны компании — из справочника организации заявки.', ''),
]

OPTION_LIMIT = 8   # сколько уникальных значений считаем «списком вариантов»


def method_of(name: str, source_kind: str | None) -> tuple[str, str, str]:
    for pat, method, rule, cdoc in RULES:
        if re.match(pat, name or ''):
            return method, rule, cdoc
    return SOURCE_TO_METHOD.get(source_kind or '', source_kind or 'manual'), '', ''


def main() -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    packs = json.loads(PACKS.read_text(encoding='utf-8')) if PACKS.is_file() else {}
    used_in = collections.defaultdict(set)
    for pcode, m in packs.items():
        for tcode, names in (m.get('variables') or {}).items():
            for n in names:
                used_in[n].add(tcode)
    hist = collections.defaultdict(list)
    for r in con.execute("SELECT variable_name, value, used_count FROM variable_value_history "
                         "WHERE value IS NOT NULL AND value<>'' ORDER BY used_count DESC"):
        if len(hist[r['variable_name']]) < 60:
            hist[r['variable_name']].append((r['value'], r['used_count']))

    md = ['# Инструкция для конструктора: переменные, способ формирования, варианты', '',
          '**Приоритет источников (правило заказчика):** значение берётся из документа клиента '
          '(паспорт, KITAS/ИТК, банковская справка) — оно сильнее карточки клиента. Если карточка '
          'расходится с документом, в документ идёт значение из документа клиента. Явная правка '
          'администратора сильнее обоих источников. Если данных нет ни в документе, ни в карточке — '
          'поле остаётся пустым, значение не выдумывается.', '']
    guide = {'generated_for': 'Wolf AutoDoc',
             'source_priority': ['правка администратора', 'документ клиента', 'карточка клиента'],
             'templates': {}, 'products': packs}
    diffs = []
    stat = collections.Counter()
    for t in con.execute("SELECT id, code, status, title FROM templates ORDER BY code"):
        code = t['code']
        tpl_out = {'title': t['title'], 'status': t['status'], 'variables': {}}
        md += ['', '## `%s` — %s' % (code, t['title'] or ''), '']
        for r in con.execute("SELECT * FROM template_variables WHERE template_id=? ORDER BY sort_order, name", (t['id'],)):
            name = r['name']
            method, rule, cdoc = method_of(name, r['source_kind'])
            vals = hist.get(name) or []
            uniq = [v for v, _n in vals]
            options = uniq if 0 < len(set(uniq)) <= OPTION_LIMIT else []
            site_note = re.sub(r'\s+', ' ', str(r['rule_note'] or '')).strip()
            site_src = r['source_kind'] or ''
            # вердикт по описанию на сайте
            verdict = 'совпадает'
            if not site_note:
                verdict = 'нет описания на сайте'
            elif 'не описано' in site_note or 'уточнения' in site_note:
                verdict = 'описание сайта неполное (обещает уточнить)'
            site_method = SOURCE_TO_METHOD.get(site_src, site_src)
            if method in ('pool', 'random_bounds', 'product_rule', 'options', 'llm') and site_method in ('client_card', 'client_doc'):
                verdict = 'расхождение: сайт says «%s», фактически %s' % (site_src, method)
            elif method == 'client_doc' and site_method == 'client_card':
                verdict = 'уточнение: сайт says карточка, фактически — документ клиента'
            stat[verdict.split(':')[0]] += 1
            if verdict != 'совпадает':
                diffs.append({'template': code, 'variable': name, 'method': method,
                              'site_source_kind': site_src, 'site_note': site_note[:300],
                              'verdict': verdict})
            tpl_out['variables'][name] = {
                'method': method, 'rule': rule, 'client_doc': cdoc,
                'options': options, 'examples': [v for v, _n in vals[:5]],
                'used_in': sorted(used_in.get(name, [])),
                'site': {'source_kind': site_src, 'note': site_note[:600],
                         'approved': r['approved'] or 0, 'default': str(r['default_value'] or '')[:80]},
                'verdict': verdict,
            }
            line = '- `%s` — способ: **%s**' % (name, method)
            if options:
                line += '; варианты: %s' % ', '.join('`%s`' % o[:24] for o in options[:6])
            md.append(line)
            if rule:
                md.append('  - правило: %s' % rule)
            if verdict != 'совпадает':
                md.append('  - описание на сайте: %s' % verdict)
        guide['templates'][code] = tpl_out
    OUT_GUIDE.parent.mkdir(parents=True, exist_ok=True)
    OUT_GUIDE.write_text(json.dumps(guide, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    OUT_DIFF.write_text(json.dumps(diffs, ensure_ascii=False, indent=1), encoding='utf-8')
    print('инструкция:', OUT_MD)
    print('для сайта:', OUT_GUIDE, '| шаблонов:', len(guide['templates']))
    print('расхождений с описанием на сайте:', len(diffs), '| из них детали:')
    for d in diffs[:15]:
        print('   %-36s %-24s %s' % (d['template'], d['variable'], d['verdict'][:70]))
    print('сводка вердиктов:', dict(stat))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
