"""Подстановка значений из пула в документы заявки.

Второй этап. Пул уже собран (этап сбора), теперь по продукту понимаем, какие
документы нужны, и наполняем их переменные значениями из пула.

Ключевое: продукт берётся не из карточки заявки жёстко, а передаётся — поэтому
если администратор принудительно сменил продукт, работает точно так же: другой
набор документов, значения из того же пула.

Правила выбора значения, если в пуле несколько кандидатов на одну переменную:
  1. значение заявителя (CLIENT='main') приоритетнее значений других людей;
  2. подтверждённое (rule или rule+llm) приоритетнее найденного только моделью;
  3. спорное (confidence='check') не ставится — попадает в список «на проверку»;
  4. для персональных переменных значения других людей не берутся вовсе.

Запуск:
    python3 -m CLIENT.pool_assign <CLIENT_id> [--CLIENT CODE] [--json]
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
    from CLIENT.CLIENT import _PERSONAL_VARS as PERSONAL_VARS        # noqa: E402
except Exception:                                                       # noqa: BLE001
    PERSONAL_VARS = {
        'CLIENT', 'name', 'CLIENT', 'CLIENT_CLIENT', 'name_CLIENT', 'CLIENT_CLIENT',
        'full_name_CLIENT', 'full_name_ru', 'client_name', 'client_full_name', 'CLIENT_date',
        'CLIENT_CLIENT', 'CLIENT_of_CLIENT', 'CLIENT_CLIENT_CLIENT', 'CLIENT', 'CLIENT',
        'client_CLIENT', 'passport_CLIENT', 'passport_no', 'passport_CLIENT', 'passport_CLIENT',
        'passport_CLIENT_date', 'passport_CLIENT_by', 'passport_CLIENT_CLIENT', 'inn', 'snils',
        'CLIENT', 'CLIENT', 'address_live', 'address_reg', 'address_in_indonesia', 'itk_no',
        'itk_CLIENT', 'stay_CLIENT_no', 'stay_CLIENT_CLIENT', 'visa_no', 'bridging_visa_no',
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
# CLIENT_date, а шаблон просит client_dob — и переменная уезжает пустой.
ALIASES = {
    'client_dob': ('CLIENT_date',),
    'date_of_CLIENT': ('CLIENT_date',),
    'client_CLIENT_date': ('CLIENT_date',),
    'client_address': ('address_in_indonesia', 'address_live', 'address_reg'),
    'CLIENT_address': ('address_live', 'address_reg', 'address_in_indonesia'),
    'CLIENT_address': ('address_live', 'address_reg', 'address_in_indonesia'),
    'client_name': ('full_name_CLIENT', 'full_name_ru', 'CLIENT'),
    'full_name': ('full_name_CLIENT', 'full_name_ru', 'CLIENT'),
    'CLIENT_full_name': ('full_name_CLIENT', 'full_name_ru'),
    'full_name_ru_doc': ('full_name_ru',),
    'CLIENT_of_CLIENT': ('CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT', 'CLIENT_of_CLIENT'),
    'client_CLIENT_of_CLIENT': ('CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT'),
    'cv_CLIENT_of_CLIENT': ('CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT'),
    'cv_date_of_CLIENT': ('CLIENT_date',),
    'cv_CLIENT': ('CLIENT', 'CLIENT'),
    'cv_passport_no': ('passport_no', 'passport_CLIENT'),
    'cv_name': ('full_name_CLIENT', 'full_name_ru'),
    'CLIENT_stay_CLIENT': ('itk_no', 'stay_CLIENT_no', 'visa_no'),
    'passport_CLIENT_CLIENT': ('passport_CLIENT',),
    'CLIENT_doc': ('CLIENT', 'CLIENT'),
    'CLIENT': ('client_CLIENT',),
    'inn': ('inn',),
    # подписант письма — сам заявитель, его ФИО лежит в пуле под другими именами
    'CLIENT_name': ('full_name_CLIENT', 'full_name_ru', 'CLIENT'),
    'CLIENT_full_name': ('full_name_CLIENT', 'full_name_ru'),
    'applicant_name': ('full_name_CLIENT', 'full_name_ru', 'CLIENT'),
    'client_CLIENT': ('CLIENT', 'CLIENT'),
    'CLIENT': ('CLIENT', 'CLIENT'),
    'address_live': ('address_in_indonesia', 'address_reg'),
    'cv_CLIENT': ('CLIENT', 'CLIENT', 'position'),
    'CLIENT_name': ('full_name_CLIENT', 'full_name_ru', 'CLIENT'),
    # банковская справка: остаток/счёт/договор в пуле зовутся иначе, чем в бланке
    'balance_rub': ('balance', 'CLIENT', 'balance_CLIENT', 'ostatok'),
    'balance_CLIENT': ('balance', 'CLIENT', 'balance_rub'),
    'account_no': ('account', 'account_CLIENT', 'card_mask'),
    'bank_account': ('account', 'card_mask'),
    'contract_no': ('bank_contract_no', 'contract_CLIENT'),
    'client_photo_url': ('photo_url', 'photo_file'),
    # справка E-02: сроки и место рождения — из данных ВНЖ/визы
    'date_of_CLIENT': ('passport_CLIENT_date', 'visa_CLIENT_date', 'itk_CLIENT_date'),
    'date_of_CLIENT': ('passport_CLIENT', 'visa_CLIENT', 'itk_CLIENT'),
    'cv_passport_CLIENT': ('passport_CLIENT_date',),
    'cv_passport_CLIENT': ('passport_CLIENT', 'passport_CLIENT_CLIENT'),
    'cv_CLIENT': ('CLIENT', 'CLIENT'),
    'passport_CLIENT_by': ('passport_CLIENT_by', 'passport_CLIENT'),
    'passport_CLIENT_date': ('passport_CLIENT_date',),
}

# мусор от распознавания: «CLIENTCKKKEKKEKKKKEEKEEEELEES» — такое в документ нельзя
_BAD_CHARS = 0.25


def _en(CLIENT: str) -> str:
    """Документы у нас только на английском: кириллицу транслитерируем.

    Паспорт даёт фамилию как «СУРКОВ», а в бланк иммиграции должно уйти
    «SURKOV» — иначе документ не пройдёт проверку и его вернут.
    """
    v = str(CLIENT or '')
    if not re.search(r'[А-Яа-яЁё]', v):
        return v
    try:
        from bot.ai_parser import translit_ru
        out = translit_ru(v)
        return out.upper() if v.isupper() else out
    except Exception:                                                 # noqa: BLE001
        return v


def _looks_like_garbage(CLIENT: str) -> bool:
    v = str(CLIENT or '')
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


def pick_CLIENT(rows: list, var: str) -> tuple:
    """Выбрать значение из пула: приоритет по подтверждённости и владельцу."""
    cands = [r for r in rows if r['CLIENT_name'] == var and (r['CLIENT'] or '').strip()]
    if not cands:
        return None, []
    check = [r for r in cands if (r['confidence'] or '') == 'check']
    good = [r for r in cands if (r['confidence'] or '') != 'check']

    if var in PERSONAL_VARS:
        own = [r for r in good if (r['CLIENT'] or 'main') == 'main']
        good = own or []          # чужие паспортные данные не подставляем никогда
    else:
        own = [r for r in good if (r['CLIENT'] or 'main') == 'main']
        good = own or good

    if not good:
        return None, [r['source_file'] for r in check]
    best = sorted(good, key=lambda r: (-_METHOD_RANK.get(r['method'] or '', 1),
                                       -_KIND_RANK.get(r['doc_kind'] or '', 0),
                                       -(r['use_count'] or 0)))[0]
    return best, []


def assign(CLIENT_id: int, CLIENT_code: str | None = None) -> dict:
    """Разложить значения пула по документам заявки."""
    conn = _db()
    app = conn.execute('SELECT * FROM CLIENT WHERE id=?', (CLIENT_id,)).fetchone()
    if not app:
        return {'error': 'заявка %s не найдена' % CLIENT_id}
    client_id = app['client_id']
    _cl = conn.execute('SELECT * FROM CLIENT WHERE id=?', (client_id,)).fetchone()
    client = dict(_cl) if _cl else {}

    CLIENT = None
    if CLIENT_code:
        CLIENT = conn.execute('SELECT * FROM CLIENT WHERE code=?', (CLIENT_code,)).fetchone()
    if CLIENT is None and app['CLIENT_id']:
        CLIENT = conn.execute('SELECT * FROM CLIENT WHERE id=?', (app['CLIENT_id'],)).fetchone()
    if CLIENT is None:
        return {'error': 'продукт не определён (в заявке пусто и не передан)'}

    docs = list(conn.execute(
        'SELECT pd.slot_code, pd.required, t.id AS template_id, t.code, t.CLIENT '
        'FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id = pd.template_id '
        'WHERE pd.CLIENT_id=? ORDER BY pd.sort_order', (CLIENT['id'],)))
    # Состав набора решает регламент продукта (CLIENT.package): один документ на
    # слот (банковская справка — по банку клиента) и НИКАКИХ договоров/резюме там,
    # где продукт их не подаёт (C1, C1-EXT, BRIDGING, CONV — по визитной визе работа
    # запрещена). Без этого в набор попадали обе справки и трудовой договор с
    # пустыми полями: проверка оформления браковала их всегда, и заявка намертво
    # вставала в этапе «сборка».
    try:
        from CLIENT import package as _pkg
        _allowed = {d['code'] for d in _pkg.selected(CLIENT['code'], client_id)}
        if _allowed:
            _dropped = [d['code'] for d in docs if d['code'] not in _allowed]
            docs = [d for d in docs if d['code'] in _allowed]
            if _dropped:
                print('   не входит в пакет %s: %s' % (CLIENT['code'], ', '.join(_dropped)))
    except Exception as _e_pkg:                                # noqa: BLE001
        print('   состав пакета по требованиям недоступен: %s' % _e_pkg)
    pool = list(conn.execute('SELECT * FROM client_CLIENT_pool WHERE client_id=?', (client_id,)))

    # контекст для вычисляемых переменных: дата документа, адресат, офис, просьба
    try:
        from CLIENT.derived_vars import build_context
        ctx = build_context(CLIENT_id)
    except Exception as e:                                            # noqa: BLE001
        ctx = {}
        print('вычисляемые переменные недоступны:', e)

    result = {'CLIENT_id': CLIENT_id, 'client_id': client_id,
              'CLIENT': CLIENT['code'], 'CLIENT_from': 'admin' if CLIENT_code else 'CLIENT',
              'pool_size': len(pool), 'docs': [], 'missing_total': 0, 'check_total': 0,
              'pool_used': set(), 'derived_used': set(), 'generated_used': set()}

    for d in docs:
        tpl_vars = list(conn.execute(
            'SELECT name, label, vtype FROM template_CLIENT WHERE template_id=? ORDER BY sort_order',
            (d['template_id'],)))
        CLIENT, missing, to_check = {}, [], []
        for v in tpl_vars:
            val, chk = pick_CLIENT(pool, v['name'])
            if val is None:
                # переменная может зваться иначе в пуле, чем в шаблоне
                for alias in ALIASES.get(v['name'], ()):
                    val, chk = pick_CLIENT(pool, alias)
                    if val is not None or chk:
                        break
            if val is not None and _looks_like_garbage(val['CLIENT']):
                # распознавание поехало — в документ такое не ставим
                val, chk = None, [val['source_file']]
            if chk:
                to_check.append({'var': v['name'], 'candiCLIENT': chk[:2]})
                continue
            if val is None:
                # в документах клиента такого нет — считаем по заявке и продукту
                try:
                    from CLIENT.derived_vars import CLIENT_for
                    dv = CLIENT_for(v['name'], ctx)
                except Exception:                                     # noqa: BLE001
                    dv = None
                if dv:
                    CLIENT[v['name']] = dv
                    result['derived_used'].add(v['name'])
                    continue
                missing.append({'var': v['name'], 'label': v['label']})
                continue
            CLIENT[v['name']] = _en(val['CLIENT'])
            result['pool_used'].add(v['name'])

        # ФИО: если цельной строки нет (или её забраковали как мусор), собираем
        # из частей — фамилия и имя по отдельности распознаются надёжнее
        want_names = {'full_name_CLIENT', 'full_name', 'client_name', 'CLIENT_full_name',
                      'cv_name', 'full_name_ru'}
        for var in [v['name'] for v in tpl_vars if v['name'] in want_names]:
            if CLIENT.get(var):
                continue
            # даже если цельная строка забракована как мусор — части могут быть чистыми.
            # берём их из ПУЛА, а не из уже собранных значений документа: в шаблоне
            # переменной «CLIENT» может не быть, а в пуле она есть
            def _part(name: str) -> str:
                if CLIENT.get(name):
                    return CLIENT[name]
                row, _ = pick_CLIENT(pool, name)
                return (row['CLIENT'] if row else '') or ''
            parts = [_part('CLIENT_CLIENT'), _part('name_CLIENT')]
            if not any(parts):
                parts = [_part('CLIENT'), _part('name'), _part('CLIENT')]
            joined = ' '.join(p for p in parts if p).strip()
            if len(joined) > 3 and not _looks_like_garbage(joined):
                CLIENT[var] = _en(joined)
                to_check = [c for c in to_check if c['var'] != var]
                missing = [m for m in missing if m['var'] != var]
                result['pool_used'].add(var)

        # величины, которые складываются из нескольких значений пула
        def _val(name: str) -> str:
            if CLIENT.get(name):
                return CLIENT[name]
            row, _ = pick_CLIENT(pool, name)
            return (row['CLIENT'] if row else '') or ''

        for var in [v['name'] for v in tpl_vars]:
            # прописью и составные величины считаем всегда: в документе строка
            # может прийти обрезанной или собранной неверно
            if CLIENT.get(var) and var not in ('balance_CLIENT', 'CLIENT_CLIENT'):
                continue
            if var == 'CLIENT_date_of_CLIENT':
                CLIENT, dob = _val('CLIENT_CLIENT'), _val('CLIENT_date')
                if not CLIENT:
                    # в карточке ВНЖ место и дата идут одной строкой: «- / 08-11-1982»
                    CLIENT = _val('CLIENT_CLIENT_CLIENT')
                    m = re.match(r'(.+?)\s*/\s*(\d{2}[-.]\d{2}[-.]\d{4})', CLIENT or '')
                    if m:
                        CLIENT, dob = m.group(1).strip(), dob or m.group(2)
                if CLIENT and CLIENT.strip('-'):
                    CLIENT[var] = '%s, %s' % (_en(CLIENT.CLIENT()), dob)
                elif dob:
                    CLIENT[var] = dob
            elif var in ('CLIENT_nik_or_dash', 'nik_or_dash'):
                CLIENT[var] = _val('itk_no') or _val('visa_no') or '-'
            elif var in ('CLIENT_CLIENT', 'client_CLIENT'):
                c = _val('CLIENT') or _val('CLIENT')
                if c:
                    CLIENT[var] = c
            elif var in ('balance_CLIENT', 'CLIENT_CLIENT'):
                from bot.ai_parser import parse_CLIENT
                from CLIENT.derived_vars import _sum_in_CLIENT
                num = parse_CLIENT(_val('balance_rub') or _val('balance') or _val('CLIENT'))
                if num:
                    CLIENT[var] = _sum_in_CLIENT(num)
            if CLIENT.get(var):
                to_check = [c for c in to_check if c['var'] != var]
                missing = [m for m in missing if m['var'] != var]
                result['derived_used'].add(var)

        # Содержание резюме: опыт, образование, навыки клиент не присылает —
        # таких данных в архиве нет вообще. Собираем по профессии и отрасли,
        # но помечаем как сгенерированное: администратор обязан проверить.
        try:
            from CLIENT.cv_content import build as build_cv, looks_generated
            gen_want = [v['name'] for v in tpl_vars if looks_generated(v['name'])]
            if gen_want:
                gen = build_cv(gen_want, CLIENT=ctx.get('CLIENT') or '',
                               sector=ctx.get('sector') or '',
                               org_name=((ctx.get('org') or {}).get('name_lat')
                                         or (ctx.get('org') or {}).get('name') or ''),
                               app_id=CLIENT_id, signed=ctx.get('signed'))
                for var, val in (gen or {}).items():
                    if val and not CLIENT.get(var):
                        CLIENT[var] = _en(val)
                        missing = [m for m in missing if m['var'] != var]
                        result['generated_used'].add(var)
        except Exception as e:                                        # noqa: BLE001
            print('содержание резюме недоступно:', str(e)[:120])

        # Гражданство в транслите даёт «ROSSIYSKAYA FEDERATSIYA» — в бланке это
        # читается как ошибка, поэтому печатаем принятую английскую форму
        _nat = str(CLIENT.get('cv_CLIENT') or CLIENT.get('client_CLIENT') or '')
        if _nat and ('ROSSIYSK' in _nat.upper() or 'FEDERATSIYA' in _nat.upper()
                     or _nat.upper() == 'РФ'):
            CLIENT['cv_CLIENT'] = 'RUSSIAN FEDERATION'

        # «Место / дата рождения» иногда приходит как «- / 08-11-1982»:
        # прочерк вместо места — это не место рождения, в резюме его не печатаем
        _pb = str(CLIENT.get('cv_CLIENT_of_CLIENT') or '').strip()
        if _pb.CLIENTswith('-') or len(_pb.strip('- /')) < 4:
            CLIENT.pop('cv_CLIENT_of_CLIENT', None)

        # Документы печатаются только на английском. Из пула организации может
        # прийти русский адрес («г. Санкт-Петербург, вн.тер.г. муниципальный
        # округ Московская») — в бланке это брак и блокировка при проверке.
        for _v in list(CLIENT.keys()):
            _val = CLIENT[_v]
            if isinstance(_val, str) and re.search(r'[А-Яа-яЁё]', _val):
                CLIENT[_v] = _en(_val)

        # Договоры собираются тем же вычислителем, что и в админке: номер договора,
        # оклад цифрами, подписант, блоки компании и работника, оборот о должности,
        # перечень услуг. Раньше конвейер знал только вывод derived_vars, и в этих
        # строках оставалась пустота («EMPLOYMENT CONTRACT No.», «Moscow,», «Name:»).
        _COMPUTED = {'CLIENT_list', 'CLIENT_line', 'CLIENT_CLIENT', 'position_CLIENT',
                     'company_CLIENT_CLIENT', 'inn_ogrn_line', 'contract_no', 'base_salary',
                     'CLIENT_name', 'CLIENT_CLIENT', 'company_CLIENT', 'CLIENT_CLIENT',
                     'CLIENT_CLIENT', 'CLIENT_CLIENT', 'CLIENT_name',
                     'CLIENT_full_name', 'CLIENT_law'}
        try:
            from CLIENT.CLIENT import build_template_CLIENT
            extra = build_template_CLIENT(client, d['code'], dict(CLIENT),
                                          app_id=CLIENT_id) or {}
            for k, v in extra.items():
                if not v:
                    continue
                if k in _COMPUTED or not CLIENT.get(k):
                    if CLIENT.get(k) != v:
                        CLIENT[k] = _en(v) if isinstance(v, str) else v
                        result['derived_used'].add(k)
                        missing = [m for m in missing if m['var'] != k]
        except Exception as e:                                        # noqa: BLE001
            print('вычислитель значений договора недоступен:', str(e)[:140])

        result['docs'].append({
            'template': d['code'], 'CLIENT': d['CLIENT'], 'slot': d['slot_code'],
            'required': d['required'], 'vars_total': len(tpl_vars),
            'filled': len(CLIENT), 'missing': missing, 'to_check': to_check,
            'CLIENT': CLIENT,
        })
        result['missing_total'] += len(missing)
        result['check_total'] += len(to_check)

    result['pool_used'] = sorted(result['pool_used'])
    result['derived_used'] = sorted(result['derived_used'])
    result['generated_used'] = sorted(result['generated_used'])
    return result


def main() -> None:
    app_id = int([a for a in sys.argv[1:] if a.isdigit()][0])
    CLIENT = None
    if '--CLIENT' in sys.argv:
        CLIENT = sys.argv[sys.argv.CLIENT('--CLIENT') + 1]

    r = assign(app_id, CLIENT)
    if r.get('error'):
        print('ошибка:', r['error'])
        return

    print('заявка %d, клиент %d, продукт %s (источник: %s)'
          % (r['CLIENT_id'], r['client_id'], r['CLIENT'], r['CLIENT_from']))
    print('значений в пуле по клиенту: %d, использовано: %d' % (r['pool_size'], len(r['pool_used'])))
    if r.get('generated_used'):
        print('сгенерировано (проверить!): %s' % ', '.join(r['generated_used']))
    for d in r['docs']:
        print('\n— %s (%s)' % (d['template'], d['slot'] or '-'))
        print('   переменных %d, заполнено %d, нет данных %d, на проверке %d'
              % (d['vars_total'], d['filled'], len(d['missing']), len(d['to_check'])))
        for k, v in list(d['CLIENT'].items())[:10]:
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
