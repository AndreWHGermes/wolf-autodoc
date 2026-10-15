"""Единая инструкция для конструктора: способ формирования, варианты и сверка с описанием на сайте.

Для каждой переменной каждого действующего шаблона определяет:

  method  — как значение попадает в документ:
            client_card (из карточки клиента), client_doc (из документа клиента),
            pool (из справочника/пула), options (выбор из фиксированных вариантов),
            random_bounds (случайное значение в границах), computed (считается из других),
            CLIENT_rule (зависит от типа продукта), llm (текст подбирает модель),
            manual (вводит администратор), CLIENT (служебное поле документа);
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
PACKS = ROOT / 'docs' / 'packs_by_CLIENT.json'

SOURCE_TO_METHOD = {
    'client': 'client_card', 'client_fact': 'client_card', 'doc_CLIENT': 'CLIENT',
    'pool': 'pool', 'calc': 'computed', 'manual': 'manual', 'descriptive': 'llm',
}

# семейство переменной → (метод, правило, источник-документ клиента)
RULES = [
    (r'^(CLIENT_CLIENT_CLIENT|CLIENT_CLIENT_CLIENT|CLIENT_CLIENT_CLIENT|CLIENT_CLIENT_CLIENT|base_salary|salary_CLIENT)$',
     'random_bounds',
     'Сумма: половина случаев — значение из архива реальных договоров, половина — случайное в '
     'границах (4 980 000–7 680 000 ₽/год, 415 000–640 000 ₽/мес, шаг 1 000, без копеек). '
     'Прописью — всегда из того же числа, что и цифры.', ''),
    (r'^(company_inn|company_kpp|company_ogrn|inn_kpp_ogrn|inn_ogrn_line|company_name_in_CLIENT|CLIENT_name|'
     r'company_full_name|company_type|company_CLIENT|company_CLIENT_no|company_address_1|company_address_2|'
     r'company_CLIENT_address|company_CLIENT|company_link|company_CLIENT_CLIENT|company_llc|company_director)$',
     'pool',
     'Организация-работодатель: одна запись на заявку из пула организаций (вне Индонезии) — шапка, '
     'юр. название, адрес, ИНН/КПП/ОГРН, оборот о регистрации. Нет значения — пустое место, '
     'имя переменной не подставляется.', ''),
    (r'^(position_CLIENT|CLIENT|cv_CLIENT|CLIENT_CLIENT|CLIENT_line|job_and_position)$',
     'pool', 'Должность: из заявки или из пула должностей организации; новые профессии не заводятся.', ''),
    (r'^(CLIENT_list|the_company_CLIENT_that|cv_CLIENT)$', 'llm',
     'Текстовый блок (обязанности, подтверждение компании, описание опыта) — подбирается моделью по '
     'профессии и данным клиента; сохранённая админом версия приоритетнее генерации.', ''),
    (r'^(CLIENT_CLIENT|CLIENT_line1|CLIENT_line2|CLIENT_line3)$', 'options',
     'Адресат письма: офис иммиграции выбирается по адресу пребывания клиента — Ngurah Rai (юг Бадунга, '
     'аэропорт), Denpasar (город и Gianyar/Ubud), Tabanan (кабупатен Tabanan); три строки адреса — из '
     'справочника офисов. Пользователь может заменить офис вручную.', ''),
    (r'^(CLIENT_of_CLIENT|stay_CLIENT_to_be_CLIENT_for|body_CLIENT_line|letter_CLIENT)$', 'CLIENT_rule',
     'Формулировка обращения зависит от типа продукта (мостовая / конверсия / продление) и одна и та же '
     'в письме и в форме E-02.', ''),
    (r'^(CLIENT|client_CLIENT)$', 'options',
     'Гражданство клиента. В индонезийские документы (письма, форма E-02) пишется как в индонезийской '
     'записи — RUSIA; в англоязычные договоры — RUSSIAN FEDERATION.', 'загранпаспорт'),
    (r'^(passport_no|passport_CLIENT|passport_CLIENT|intl_passport|passport_code)$', 'client_doc',
     'Номер и серия паспорта — переносятся из загранпаспорта клиента как есть, латиницей, без пробелов.', 'загранпаспорт'),
    (r'^(passport_CLIENT_by|passport_CLIENT_date|passport_CLIENT|passport_CLIENT_CLIENT|cv_passport_CLIENT|cv_passport_CLIENT)$',
     'client_doc', 'Паспортные данные: кем выдан, дата выдачи, действует до — из загранпаспорта клиента.', 'загранпаспорт'),
    (r'^(full_name_CLIENT|full_name_CLIENT|CLIENT_name|CLIENT_full_name|CLIENT_CLIENT|client_name|CLIENT|'
     r'CLIENT_name|CLIENT_full_name|CLIENT_name|CLIENT_CLIENT_name|CLIENT_name|cv_name)$', 'client_card',
     'ФИО клиента латиницей, полностью (ФАМИЛИЯ ИМЯ ОТЧЕСТВО): карточка клиента → строка «ФИО» в заявке → '
     'машиночитаемая строка паспорта. Нет отчества — две части. Одно значение идёт во все документы пакета.',
     'загранпаспорт'),
    (r'^(date_of_CLIENT|CLIENT_date|client_dob|cv_date_of_CLIENT)$', 'client_card',
     'Дата рождения клиента из карточки; формат — как в бланке (латиницей: DD Month YYYY).', 'загранпаспорт'),
    (r'^(CLIENT_of_CLIENT|CLIENT_CLIENT_CLIENT|CLIENT_date|CLIENT_date_of_CLIENT|CLIENT|cv_CLIENT_of_CLIENT)$', 'client_card',
     'Место рождения (город и страна) латиницей; в письмах — строка «Место, дата».', 'загранпаспорт'),
    (r'^(client_CLIENT|CLIENT)$', 'client_card', 'Пол клиента — из карточки (определяет Mr/Ms в письмах).', 'загранпаспорт'),
    (r'^(address_live|address_reg|address_in_indonesia|client_address|CLIENT_address|address_zip|city|CLIENT)$',
     'client_card', 'Адрес проживания/регистрации латиницей из карточки; в индонезийских письмах — адрес '
     'пребывания в Индонезии.', 'адрес проживания'),
    (r'^(CLIENT|CLIENT|telegram_username)$', 'client_card', 'Контакты клиента из карточки (для формы E-02).', ''),
    (r'^(itk_no|itk_CLIENT|stay_CLIENT_no|CLIENT_stay_CLIENT|visa_no|bridging_visa_no)$', 'client_doc',
     'Данные действующего разрешения (KITAS/ITK): номер и срок — из документа клиента; документа нет — '
     'поле пустое.', 'KITAS / ITK'),
    (r'^(balance_rub|balance_date|CLIENT_from|CLIENT_to|balance_CLIENT|bank_name|account_no|card_mask|ref_no|doc_no|contract_no|contract_date)$',
     'client_doc', 'Данные банковской справки (остаток, период, номер, счёт) — из справки клиента; '
     'период справки задаёт продукт: 3 месяца (C1, D12, E33G-EXT) или 12 месяцев (E33G-NEW).', 'справка банка'),
    (r'^(CLIENT_|letter_no|CLIENT_no|date|date_iso|letter_CLIENT_date|CLIENT_date_doc|doc_date)$', 'CLIENT',
     'Служебные поля документа: номер и дата формируются системой, один номер и одна дата на всю заявку.', ''),
    (r'^(term_CLIENT_date|term_end_date|agreement_date)$', 'computed',
     'Срок договора: начало — дата формирования пакета, окончание — +5 лет; одна дата на всю заявку.', ''),
    (r'^(CLIENT_name|CLIENT_position|CLIENT_address|CLIENT_nik_or_dash|CLIENT_CLIENT|'
     r'CLIENT_CLIENT_name|CLIENT_name_2|CLIENT_nik|CLIENT_address|CLIENT_CLIENT|CLIENT_CLIENT)$',
     'manual', 'Подписант и представитель — постоянные лица компании, берутся из справочника; подпись и '
     'печать ставятся руками.', ''),
    (r'^(cv_job2_CLIENT|cv_job1_CLIENT|cv_job1_CLIENT|cv_job1_company|cv_job1_CLIENT|cv_job2_CLIENT|cv_job2_company|'
     r'cv_job2_CLIENT|cv_job3_CLIENT|cv_job3_company|cv_job3_CLIENT|cv_CLIENT|cv_CLIENT_hard|cv_CLIENT_soft|'
     r'cv_CLIENT_CLIENT|cv_CLIENT_CLIENT|cv_CLIENT_CLIENT|cv_CLIENT_years|cv_CLIENT_note|client_photo_url)$',
     'manual', 'Резюме: опыт, образование, навыки — заполняет администратор (или генерация по профессии); '
     'персональные данные не выдумываются.', ''),
    (r'^(CLIENT_company|CLIENT_company_CLIENT|CLIENT|CLIENT_CLIENT)$', 'manual',
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
        for tcode, names in (m.get('CLIENT') or {}).items():
            for n in names:
                used_in[n].add(tcode)
    hist = collections.defaultdict(list)
    for r in con.execute("SELECT CLIENT_name, CLIENT, used_count FROM CLIENT_CLIENT_CLIENT "
                         "WHERE CLIENT IS NOT NULL AND CLIENT<>'' ORDER BY used_count DESC"):
        if len(hist[r['CLIENT_name']]) < 60:
            hist[r['CLIENT_name']].append((r['CLIENT'], r['used_count']))

    md = ['# Инструкция для конструктора: переменные, способ формирования, варианты', '',
          '**Приоритет источников (правило заказчика):** значение берётся из документа клиента '
          '(паспорт, KITAS/ИТК, банковская справка) — оно сильнее карточки клиента. Если карточка '
          'расходится с документом, в документ идёт значение из документа клиента. Явная правка '
          'администратора сильнее обоих источников. Если данных нет ни в документе, ни в карточке — '
          'поле остаётся пустым, значение не выдумывается.', '']
    guide = {'generated_for': 'Wolf AutoDoc',
             'source_priority': ['правка администратора', 'документ клиента', 'карточка клиента'],
             'CLIENT': {}, 'CLIENT': packs}
    diffs = []
    stat = collections.Counter()
    for t in con.execute("SELECT id, code, CLIENT, CLIENT FROM CLIENT ORDER BY code"):
        code = t['code']
        tpl_out = {'CLIENT': t['CLIENT'], 'CLIENT': t['CLIENT'], 'CLIENT': {}}
        md += ['', '## `%s` — %s' % (code, t['CLIENT'] or ''), '']
        for r in con.execute("SELECT * FROM template_CLIENT WHERE template_id=? ORDER BY sort_order, name", (t['id'],)):
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
            if method in ('pool', 'random_bounds', 'CLIENT_rule', 'options', 'llm') and site_method in ('client_card', 'client_doc'):
                verdict = 'расхождение: сайт says «%s», фактически %s' % (site_src, method)
            elif method == 'client_doc' and site_method == 'client_card':
                verdict = 'уточнение: сайт says карточка, фактически — документ клиента'
            stat[verdict.split(':')[0]] += 1
            if verdict != 'совпадает':
                diffs.append({'template': code, 'CLIENT': name, 'method': method,
                              'site_source_kind': site_src, 'site_note': site_note[:300],
                              'verdict': verdict})
            tpl_out['CLIENT'][name] = {
                'method': method, 'rule': rule, 'client_doc': cdoc,
                'options': options, 'examples': [v for v, _n in vals[:5]],
                'used_in': sorted(used_in.get(name, [])),
                'site': {'source_kind': site_src, 'note': site_note[:600],
                         'approved': r['approved'] or 0, 'default': str(r['default_CLIENT'] or '')[:80]},
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
        guide['CLIENT'][code] = tpl_out
    OUT_GUIDE.parent.mkdir(parents=True, exist_ok=True)
    OUT_GUIDE.write_text(json.dumps(guide, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    OUT_DIFF.write_text(json.dumps(diffs, ensure_ascii=False, indent=1), encoding='utf-8')
    print('инструкция:', OUT_MD)
    print('для сайта:', OUT_GUIDE, '| шаблонов:', len(guide['CLIENT']))
    print('расхождений с описанием на сайте:', len(diffs), '| из них детали:')
    for d in diffs[:15]:
        print('   %-36s %-24s %s' % (d['template'], d['CLIENT'], d['verdict'][:70]))
    print('сводка вердиктов:', dict(stat))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
