"""Подстановка значений из пула в документы заявки.

Второй этап. Пул уже собран (этап сбора), теперь по продукту понимаем, какие
документы нужны, и наполняем их переменные значениями из пула.

Ключевое: продукт берётся не из карточки заявки жёстко, а передаётся — поэтому
если администратор принудительно сменил продукт, работает точно так же: другой
набор документов, значения из того же пула.

Правила выбора значения, если в пуле несколько кандидатов на одну переменную:
  1. значение заявителя (person='main') приоритетнее значений других людей;
  2. подтверждённое (rule или rule+llm) приоритетнее найденного только моделью;
  3. спорное (confidence='check') не ставится — попадает в список «на проверку»;
  4. для персональных переменных значения других людей не берутся вовсе.

Запуск:
    python3 -m services.pool_assign <application_id> [--product CODE] [--json]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

DB = Path('/opt/wolf_v2/data/wolf.db')

# переменные, которые описывают конкретного человека: чужие значения брать нельзя
try:
    from services.values import _PERSONAL_VARS as PERSONAL_VARS        # noqa: E402
except Exception:                                                       # noqa: BLE001
    PERSONAL_VARS = {
        'surname', 'name', 'patronymic', 'surname_latin', 'name_latin', 'patronymic_latin',
        'full_name_latin', 'full_name_ru', 'client_name', 'client_full_name', 'birth_date',
        'birth_place', 'place_of_birth', 'place_birth_inline', 'citizenship', 'nationality',
        'client_gender', 'passport_number', 'passport_no', 'passport_series', 'passport_expiry',
        'passport_issue_date', 'passport_issued_by', 'passport_valid_until', 'inn', 'snils',
        'phone', 'email', 'address_live', 'address_reg', 'address_in_indonesia', 'itk_no',
        'itk_expiry', 'stay_permit_no', 'stay_permit_expiry', 'visa_no', 'bridging_visa_no',
    }

_METHOD_RANK = {'rule+llm': 3, 'rule': 2, 'llm': 1, '': 1}

# Надёжность источника: паспорт и его машиночитаемая зона точнее карточки ВНЖ,
# а ВНЖ точнее банковской справки, где ФИО напечатано мелким шрифтом
_KIND_RANK = {
    'passport': 5, 'visa': 4, 'itk': 3, 'bank_balance': 2, 'bank_movement': 2,
    'contract': 1, 'resume': 1, 'photo': 0, 'other': 0, '': 0,
}

# Одно и то же значение в пуле и в шаблонах зовётся по-разному. Без этой карты
# подстановка «не находит» данные, которые в пуле лежат: пул по паспорту знает
# birth_date, а шаблон просит client_dob — и переменная уезжает пустой.
ALIASES = {
    'client_dob': ('birth_date',),
    'date_of_birth': ('birth_date',),
    'client_birth_date': ('birth_date',),
    'client_address': ('address_in_indonesia', 'address_live', 'address_reg'),
    'employee_address': ('address_live', 'address_reg', 'address_in_indonesia'),
    'signatory_address': ('address_live', 'address_reg', 'address_in_indonesia'),
    'client_name': ('full_name_latin', 'full_name_ru', 'surname'),
    'full_name': ('full_name_latin', 'full_name_ru', 'surname'),
    'employee_full_name': ('full_name_latin', 'full_name_ru'),
    'full_name_ru_doc': ('full_name_ru',),
    'place_of_birth': ('birth_place', 'place_birth_inline', 'place_of_birth'),
    'client_place_of_birth': ('birth_place', 'place_birth_inline'),
    'cv_place_of_birth': ('birth_place', 'place_birth_inline'),
    'cv_date_of_birth': ('birth_date',),
    'cv_nationality': ('citizenship', 'nationality'),
    'cv_passport_no': ('passport_no', 'passport_number'),
    'cv_name': ('full_name_latin', 'full_name_ru'),
    'existing_stay_permit': ('itk_no', 'stay_permit_no', 'visa_no'),
    'passport_valid_until': ('passport_expiry',),
    'nationality_doc': ('nationality', 'citizenship'),
    'gender': ('client_gender',),
    'inn': ('inn',),
    # подписант письма — сам заявитель, его ФИО лежит в пуле под другими именами
    'signatory_name': ('full_name_latin', 'full_name_ru', 'surname'),
    'signatory_full_name': ('full_name_latin', 'full_name_ru'),
    'applicant_name': ('full_name_latin', 'full_name_ru', 'surname'),
    'client_nationality': ('nationality', 'citizenship'),
    'nationality': ('citizenship', 'nationality'),
    'address_live': ('address_in_indonesia', 'address_reg'),
    'cv_profession': ('occupation', 'profession', 'position'),
    'employee_name': ('full_name_latin', 'full_name_ru', 'surname'),
    # банковская справка: остаток/счёт/договор в пуле зовутся иначе, чем в бланке
    'balance_rub': ('balance', 'amount', 'balance_amount', 'ostatok'),
    'balance_amount': ('balance', 'amount', 'balance_rub'),
    'account_no': ('account', 'account_number', 'card_mask'),
    'bank_account': ('account', 'card_mask'),
    'contract_no': ('bank_contract_no', 'contract_number'),
    'client_photo_url': ('photo_url', 'photo_file'),
    # справка E-02: сроки и место рождения — из данных ВНЖ/визы
    'date_of_issue': ('passport_issue_date', 'visa_issue_date', 'itk_issue_date'),
    'date_of_expiry': ('passport_expiry', 'visa_expiry', 'itk_expiry'),
    'cv_passport_issue': ('passport_issue_date',),
    'cv_passport_expiry': ('passport_expiry', 'passport_valid_until'),
    'cv_nationality': ('citizenship', 'nationality'),
    'passport_issued_by': ('passport_issued_by', 'passport_authority'),
    'passport_issue_date': ('passport_issue_date',),
}

# мусор от распознавания: «VITALIICKKKEKKEKKKKEEKEEEELEES» — такое в документ нельзя
_BAD_CHARS = 0.25


def _en(value: str) -> str:
    """Документы у нас только на английском: кириллицу транслитерируем.

    Паспорт даёт фамилию как «СУРКОВ», а в бланк иммиграции должно уйти
    «SURKOV» — иначе документ не пройдёт проверку и его вернут.
    """
    v = str(value or '')
    if not re.search(r'[А-Яа-яЁё]', v):
        return v
    try:
        from bot.ai_parser import translit_ru
        out = translit_ru(v)
        return out.upper() if v.isupper() else out
    except Exception:                                                 # noqa: BLE001
        return v


def _looks_like_garbage(value: str) -> bool:
    v = str(value or '')
    letters = [c for c in v if c.isalpha()]
    if len(letters) < 4:
        return False
    repeats = sum(1 for i in range(1, len(letters)) if letters[i] == letters[i - 1])
    if repeats / max(1, len(letters)) > _BAD_CHARS:
        return True
    # три одинаковые буквы подряд в имени/фамилии — распознавание поехало
    return bool(re.search(r'(?i)([a-zа-яё])\1{2,}', v))


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def pick_value(rows: list, var: str) -> tuple:
    """Выбрать значение из пула: приоритет по подтверждённости и владельцу."""
    cands = [r for r in rows if r['variable_name'] == var and (r['value'] or '').strip()]
    if not cands:
        return None, []
    check = [r for r in cands if (r['confidence'] or '') == 'check']
    good = [r for r in cands if (r['confidence'] or '') != 'check']

    if var in PERSONAL_VARS:
        own = [r for r in good if (r['person'] or 'main') == 'main']
        good = own or []          # чужие паспортные данные не подставляем никогда
    else:
        own = [r for r in good if (r['person'] or 'main') == 'main']
        good = own or good

    if not good:
        return None, [r['source_file'] for r in check]
    best = sorted(good, key=lambda r: (-_METHOD_RANK.get(r['method'] or '', 1),
                                       -_KIND_RANK.get(r['doc_kind'] or '', 0),
                                       -(r['use_count'] or 0)))[0]
    return best, []


def assign(application_id: int, product_code: str | None = None) -> dict:
    """Разложить значения пула по документам заявки."""
    conn = _db()
    app = conn.execute('SELECT * FROM applications WHERE id=?', (application_id,)).fetchone()
    if not app:
        return {'error': 'заявка %s не найдена' % application_id}
    client_id = app['client_id']
    _cl = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    client = dict(_cl) if _cl else {}

    product = None
    if product_code:
        product = conn.execute('SELECT * FROM products WHERE code=?', (product_code,)).fetchone()
    if product is None and app['product_id']:
        product = conn.execute('SELECT * FROM products WHERE id=?', (app['product_id'],)).fetchone()
    if product is None:
        return {'error': 'продукт не определён (в заявке пусто и не передан)'}

    docs = list(conn.execute(
        'SELECT pd.slot_code, pd.required, t.id AS template_id, t.code, t.title '
        'FROM product_documents pd JOIN templates t ON t.id = pd.template_id '
        'WHERE pd.product_id=? ORDER BY pd.sort_order', (product['id'],)))
    # Состав набора решает регламент продукта (services.package): один документ на
    # слот (банковская справка — по банку клиента) и НИКАКИХ договоров/резюме там,
    # где продукт их не подаёт (C1, C1-EXT, BRIDGING, CONV — по визитной визе работа
    # запрещена). Без этого в набор попадали обе справки и трудовой договор с
    # пустыми полями: проверка оформления браковала их всегда, и заявка намертво
    # вставала в этапе «сборка».
    try:
        from services import package as _pkg
        _allowed = {d['code'] for d in _pkg.selected(product['code'], client_id)}
        if _allowed:
            _dropped = [d['code'] for d in docs if d['code'] not in _allowed]
            docs = [d for d in docs if d['code'] in _allowed]
            if _dropped:
                print('   не входит в пакет %s: %s' % (product['code'], ', '.join(_dropped)))
    except Exception as _e_pkg:                                # noqa: BLE001
        print('   состав пакета по требованиям недоступен: %s' % _e_pkg)
    pool = list(conn.execute('SELECT * FROM client_values_pool WHERE client_id=?', (client_id,)))

    # контекст для вычисляемых переменных: дата документа, адресат, офис, просьба
    try:
        from services.derived_vars import build_context
        ctx = build_context(application_id)
    except Exception as e:                                            # noqa: BLE001
        ctx = {}
        print('вычисляемые переменные недоступны:', e)

    result = {'application_id': application_id, 'client_id': client_id,
              'product': product['code'], 'product_from': 'admin' if product_code else 'application',
              'pool_size': len(pool), 'docs': [], 'missing_total': 0, 'check_total': 0,
              'pool_used': set(), 'derived_used': set(), 'generated_used': set()}

    for d in docs:
        tpl_vars = list(conn.execute(
            'SELECT name, label, vtype FROM template_variables WHERE template_id=? ORDER BY sort_order',
            (d['template_id'],)))
        values, missing, to_check = {}, [], []
        for v in tpl_vars:
            val, chk = pick_value(pool, v['name'])
            if val is None:
                # переменная может зваться иначе в пуле, чем в шаблоне
                for alias in ALIASES.get(v['name'], ()):
                    val, chk = pick_value(pool, alias)
                    if val is not None or chk:
                        break
            if val is not None and _looks_like_garbage(val['value']):
                # распознавание поехало — в документ такое не ставим
                val, chk = None, [val['source_file']]
            if chk:
                to_check.append({'var': v['name'], 'candidates': chk[:2]})
                continue
            if val is None:
                # в документах клиента такого нет — считаем по заявке и продукту
                try:
                    from services.derived_vars import value_for
                    dv = value_for(v['name'], ctx)
                except Exception:                                     # noqa: BLE001
                    dv = None
                if dv:
                    values[v['name']] = dv
                    result['derived_used'].add(v['name'])
                    continue
                missing.append({'var': v['name'], 'label': v['label']})
                continue
            values[v['name']] = _en(val['value'])
            result['pool_used'].add(v['name'])

        # ФИО: если цельной строки нет (или её забраковали как мусор), собираем
        # из частей — фамилия и имя по отдельности распознаются надёжнее
        want_names = {'full_name_latin', 'full_name', 'client_name', 'employee_full_name',
                      'cv_name', 'full_name_ru'}
        for var in [v['name'] for v in tpl_vars if v['name'] in want_names]:
            if values.get(var):
                continue
            # даже если цельная строка забракована как мусор — части могут быть чистыми.
            # берём их из ПУЛА, а не из уже собранных значений документа: в шаблоне
            # переменной «surname» может не быть, а в пуле она есть
            def _part(name: str) -> str:
                if values.get(name):
                    return values[name]
                row, _ = pick_value(pool, name)
                return (row['value'] if row else '') or ''
            parts = [_part('surname_latin'), _part('name_latin')]
            if not any(parts):
                parts = [_part('surname'), _part('name'), _part('patronymic')]
            joined = ' '.join(p for p in parts if p).strip()
            if len(joined) > 3 and not _looks_like_garbage(joined):
                values[var] = _en(joined)
                to_check = [c for c in to_check if c['var'] != var]
                missing = [m for m in missing if m['var'] != var]
                result['pool_used'].add(var)

        # величины, которые складываются из нескольких значений пула
        def _val(name: str) -> str:
            if values.get(name):
                return values[name]
            row, _ = pick_value(pool, name)
            return (row['value'] if row else '') or ''

        for var in [v['name'] for v in tpl_vars]:
            # прописью и составные величины считаем всегда: в документе строка
            # может прийти обрезанной или собранной неверно
            if values.get(var) and var not in ('balance_words', 'amount_words'):
                continue
            if var == 'place_date_of_birth':
                place, dob = _val('birth_place'), _val('birth_date')
                if not place:
                    # в карточке ВНЖ место и дата идут одной строкой: «- / 08-11-1982»
                    inline = _val('place_birth_inline')
                    m = re.match(r'(.+?)\s*/\s*(\d{2}[-.]\d{2}[-.]\d{4})', inline or '')
                    if m:
                        place, dob = m.group(1).strip(), dob or m.group(2)
                if place and place.strip('-'):
                    values[var] = '%s, %s' % (_en(place.title()), dob)
                elif dob:
                    values[var] = dob
            elif var in ('signatory_nik_or_dash', 'nik_or_dash'):
                values[var] = _val('itk_no') or _val('visa_no') or '-'
            elif var in ('signatory_citizenship', 'client_citizenship'):
                c = _val('nationality') or _val('citizenship')
                if c:
                    values[var] = c
            elif var in ('balance_words', 'amount_words'):
                from bot.ai_parser import parse_amount
                from services.derived_vars import _sum_in_words
                num = parse_amount(_val('balance_rub') or _val('balance') or _val('amount'))
                if num:
                    values[var] = _sum_in_words(num)
            if values.get(var):
                to_check = [c for c in to_check if c['var'] != var]
                missing = [m for m in missing if m['var'] != var]
                result['derived_used'].add(var)

        # Содержание резюме: опыт, образование, навыки клиент не присылает —
        # таких данных в архиве нет вообще. Собираем по профессии и отрасли,
        # но помечаем как сгенерированное: администратор обязан проверить.
        try:
            from services.cv_content import build as build_cv, looks_generated
            gen_want = [v['name'] for v in tpl_vars if looks_generated(v['name'])]
            if gen_want:
                gen = build_cv(gen_want, profession=ctx.get('profession') or '',
                               sector=ctx.get('sector') or '',
                               org_name=((ctx.get('org') or {}).get('name_lat')
                                         or (ctx.get('org') or {}).get('name') or ''),
                               app_id=application_id, signed=ctx.get('signed'))
                for var, val in (gen or {}).items():
                    if val and not values.get(var):
                        values[var] = _en(val)
                        missing = [m for m in missing if m['var'] != var]
                        result['generated_used'].add(var)
        except Exception as e:                                        # noqa: BLE001
            print('содержание резюме недоступно:', str(e)[:120])

        # Гражданство в транслите даёт «ROSSIYSKAYA FEDERATSIYA» — в бланке это
        # читается как ошибка, поэтому печатаем принятую английскую форму
        _nat = str(values.get('cv_nationality') or values.get('client_nationality') or '')
        if _nat and ('ROSSIYSK' in _nat.upper() or 'FEDERATSIYA' in _nat.upper()
                     or _nat.upper() == 'РФ'):
            values['cv_nationality'] = 'RUSSIAN FEDERATION'

        # «Место / дата рождения» иногда приходит как «- / 08-11-1982»:
        # прочерк вместо места — это не место рождения, в резюме его не печатаем
        _pb = str(values.get('cv_place_of_birth') or '').strip()
        if _pb.startswith('-') or len(_pb.strip('- /')) < 4:
            values.pop('cv_place_of_birth', None)

        # Документы печатаются только на английском. Из пула организации может
        # прийти русский адрес («г. Санкт-Петербург, вн.тер.г. муниципальный
        # округ Московская») — в бланке это брак и блокировка при проверке.
        for _v in list(values.keys()):
            _val = values[_v]
            if isinstance(_val, str) and re.search(r'[А-Яа-яЁё]', _val):
                values[_v] = _en(_val)

        # Договоры собираются тем же вычислителем, что и в админке: номер договора,
        # оклад цифрами, подписант, блоки компании и работника, оборот о должности,
        # перечень услуг. Раньше конвейер знал только вывод derived_vars, и в этих
        # строках оставалась пустота («EMPLOYMENT CONTRACT No.», «Moscow,», «Name:»).
        _COMPUTED = {'services_list', 'engagement_line', 'engagement_phrase', 'position_title',
                     'company_incorporated_phrase', 'inn_ogrn_line', 'contract_no', 'base_salary',
                     'signer_name', 'signer_title', 'company_block', 'employee_block',
                     'contractor_block', 'employee_short', 'employee_name',
                     'contractor_full_name', 'governing_law'}
        try:
            from services.values import build_template_values
            extra = build_template_values(client, d['code'], dict(values),
                                          app_id=application_id) or {}
            for k, v in extra.items():
                if not v:
                    continue
                if k in _COMPUTED or not values.get(k):
                    if values.get(k) != v:
                        values[k] = _en(v) if isinstance(v, str) else v
                        result['derived_used'].add(k)
                        missing = [m for m in missing if m['var'] != k]
        except Exception as e:                                        # noqa: BLE001
            print('вычислитель значений договора недоступен:', str(e)[:140])

        result['docs'].append({
            'template': d['code'], 'title': d['title'], 'slot': d['slot_code'],
            'required': d['required'], 'vars_total': len(tpl_vars),
            'filled': len(values), 'missing': missing, 'to_check': to_check,
            'values': values,
        })
        result['missing_total'] += len(missing)
        result['check_total'] += len(to_check)

    result['pool_used'] = sorted(result['pool_used'])
    result['derived_used'] = sorted(result['derived_used'])
    result['generated_used'] = sorted(result['generated_used'])
    return result


def main() -> None:
    app_id = int([a for a in sys.argv[1:] if a.isdigit()][0])
    product = None
    if '--product' in sys.argv:
        product = sys.argv[sys.argv.index('--product') + 1]

    r = assign(app_id, product)
    if r.get('error'):
        print('ошибка:', r['error'])
        return

    print('заявка %d, клиент %d, продукт %s (источник: %s)'
          % (r['application_id'], r['client_id'], r['product'], r['product_from']))
    print('значений в пуле по клиенту: %d, использовано: %d' % (r['pool_size'], len(r['pool_used'])))
    if r.get('generated_used'):
        print('сгенерировано (проверить!): %s' % ', '.join(r['generated_used']))
    for d in r['docs']:
        print('\n— %s (%s)' % (d['template'], d['slot'] or '-'))
        print('   переменных %d, заполнено %d, нет данных %d, на проверке %d'
              % (d['vars_total'], d['filled'], len(d['missing']), len(d['to_check'])))
        for k, v in list(d['values'].items())[:10]:
            print('      %-22s %s' % (k, str(v)[:60]))
        if d['missing']:
            print('   нет данных: %s' % ', '.join(m['var'] for m in d['missing'][:12]))
        if d['to_check']:
            print('   на проверке: %s' % ', '.join(m['var'] for m in d['to_check'][:8]))
    print('\nвсего не хватает значений: %d, спорных: %d' % (r['missing_total'], r['check_total']))
    if '--json' in sys.argv:
        Path('/tmp/pool_assign_%d.json' % app_id).write_text(
            json.dumps(r, ensure_ascii=False, indent=1, default=str)[:400000], encoding='utf-8')
        print('подробности: /tmp/pool_assign_%d.json' % app_id)


if __name__ == '__main__':
    main()
