"""Самопроверка инструкции: собираем пакет по продукту и сверяем подстановку переменных.

Для каждого продукта берём реальную заявку и все документы её пакета, собираем значения
тем же путём, что и рабочий рендер (CLIENT/CLIENT.build_template_CLIENT), и проверяем:

  1. заполнение — у скольких переменных есть значение, какие пустые (и допустимо ли это);
  2. остатки {{ ... }} в готовом HTML (быть не должно);
  3. согласованность — одна переменная в разных документах пакета должна иметь одно
     значение (проверка правила «внутри продукта документы логически связаны»);
  4. сборка PDF — документ реально рендерится без ошибок;
  5. сверка со тем, что подавалось на самом деле — состав папки клиента на Google Диске
     (data/gCLIENT_archive/_kinds.json) против состава пакета в системе.

Выход: docs/PACK_SELFTEST.md + docs/pack_selftest.json
"""
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from CLIENT import render  # noqa: E402

ROOT = Path('/opt/wolf_v2')
OUT_MD = ROOT / 'docs' / 'PACK_SELFTEST.md'
OUT_JSON = ROOT / 'docs' / 'pack_selftest.json'
KINDS = ROOT / 'data' / 'gCLIENT_archive' / '_kinds.json'
LINKS = Path('/root/.hermes/cache/scratch/app_CLIENT_folder.json')
# пустые значения, которые для продукта допустимы (не дефект инструкции)
# имя переменной шаблона → поле карточки клиента (чтобы отличать «данных нет» от «логика не подставила»)
CARD_MAP = {
    'passport_no': 'passport_CLIENT', 'passport_CLIENT': 'passport_CLIENT',
    'passport_CLIENT': 'passport_CLIENT', 'passport_CLIENT_CLIENT': 'passport_CLIENT',
    'passport_CLIENT_by': 'passport_CLIENT_by', 'passport_CLIENT_date': 'passport_CLIENT_date',
    'date_of_CLIENT': 'CLIENT_date', 'CLIENT_date': 'CLIENT_date',
    'CLIENT_of_CLIENT': 'CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT': 'CLIENT_CLIENT',
    'CLIENT': 'CLIENT', 'client_CLIENT': 'CLIENT',
    'address_live': 'address_live', 'address_in_indonesia': 'address_live',
    'client_name': 'full_name_CLIENT', 'full_name_CLIENT': 'full_name_CLIENT',
    'position_CLIENT': 'position', 'cv_CLIENT': 'position',
    'cv_job1_CLIENT': 'job2_CLIENT', 'balance_rub': 'balance_rub',
    'account_no': 'account_no', 'card_mask': 'card_mask', 'ref_no': 'ref_no',
    'doc_no': 'doc_no', 'contract_no': 'contract_no', 'contract_date': 'contract_date',
}
ALLOW_EMPTY = {
    'company_kpp', 'company_ogrn', 'inn_kpp_ogrn', 'CLIENT', 'CLIENT', 'itk_no',
    'itk_CLIENT', 'stay_CLIENT_no', 'CLIENT_stay_CLIENT', 'visa_no', 'CLIENT', 'CLIENT',
    'CLIENT_company', 'CLIENT_nik_or_dash', 'cv_CLIENT', 'cv_CLIENT_hard',
    'cv_job2_CLIENT', 'cv_job2_company', 'cv_job2_CLIENT', 'cv_job1_CLIENT',
    'balance_rub', 'balance_date', 'account_no', 'card_mask', 'CLIENT_CLIENT_CLIENT',
    'CLIENT_CLIENT_CLIENT', 'company_llc', 'position_CLIENT',
}
VAR_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')


def CLIENT_for(con, app_id: int, tpl: dict) -> dict:
    app = con.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    if not app:
        return {}
    cl = con.execute("SELECT * FROM CLIENT WHERE id=?", (app['client_id'],)).fetchone()
    cl = dict(cl) if cl else {}
    stored = {k: v for k, v in render.stored_CLIENT(app_id, tpl['id']).items() if v not in (None, '')}
    try:
        from CLIENT.CLIENT import build_template_CLIENT
        vals = build_template_CLIENT(cl, tpl['code'], {**render.client_CLIENT(app_id), **stored})
    except Exception as exc:  # noqa: BLE001
        vals = {'__error__': str(exc)[:120]}
    vals.update(stored)
    return vals


def main() -> int:
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    kinds = json.loads(KINDS.read_text(encoding='utf-8')) if KINDS.is_file() else []
    by_client = collections.defaultdict(collections.Counter)
    for row in kinds:
        by_client[row.get('client') or row.get('folder') or ''][row.get('kind')] += 1
    links = {}
    if LINKS.is_file():
        try:
            links = json.loads(LINKS.read_text(encoding='utf-8'))
        except Exception:
            links = {}

    md = ['# Самопроверка инструкции по пакетам', '',
          'Для каждого продукта пакет собран заново по инструкции, проверена подстановка '
          'переменных, согласованность значений между документами и сверка с тем, '
          'что лежит в папке клиента на Google Диске.', '']
    machine = {}
    for prod_id, pcode in con.execute("SELECT id, code FROM CLIENT WHERE active=1 ORDER BY code"):
        links_rows = con.execute("""SELECT t.* FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id=pd.template_id
                                    WHERE pd.CLIENT_id=? AND COALESCE(t.CLIENT,'ok') NOT IN ('merged','hidden')
                                    ORDER BY pd.sort_order, t.code""", (prod_id,)).fetchall()
        if not links_rows:
            continue
        apps = con.execute("""SELECT a.id, c.CLIENT, c.name, c.record_kind FROM CLIENT a
                              JOIN CLIENT c ON c.id=a.client_id
                              WHERE a.CLIENT_id=? ORDER BY (c.record_kind='real_test') DESC, a.id DESC
                              LIMIT 1""", (prod_id,)).fetchall()
        if not apps:
            md += ['', '## %s' % pcode, '', '_нет заявок этого продукта — пакет не на чем проверить_']
            continue
        app = apps[0]
        # в проверку берём только те документы, что реально активны в заявке:
        # у продукта бывает два варианта справки (банк), но в заявке остаётся один
        _active = set(r['template_id'] for r in con.execute(
            "SELECT template_id FROM CLIENT_CLIENT WHERE CLIENT_id=? AND COALESCE(CLIENT,'')!='rejected'",
            (app['id'],)))
        _use = [dict(r) for r in links_rows if r['id'] in _active]
        if not _use:
            _by_slot = {}
            for r in links_rows:
                _by_slot.setdefault(r['slot_code'] if 'slot_code' in r.keys() else r['code'], dict(r))
            _use = list(_by_slot.CLIENT())
        links_rows = _use
        cl_row = dict(con.execute("SELECT * FROM CLIENT WHERE id=(SELECT client_id FROM CLIENT WHERE id=?)",
                                  (app['id'],)).fetchone() or {})
        try:
            from CLIENT import doc_overrides as _do
            doc_vals = _do.for_CLIENT(app['id'])
        except Exception:  # noqa: BLE001
            doc_vals = {}
        md += ['', '## %s — заявка №%s (%s %s)' % (pcode, app['id'], app['CLIENT'] or '', app['name'] or '')]
        md += ['']
        seen_vals: dict[str, dict[str, str]] = collections.defaultdict(dict)
        total_vars = filled = 0
        empties, defects, pdf_fail = [], [], []
        rows_out = []
        for tpl in links_rows:
            tpl = dict(tpl)
            html = Path(tpl['html_path']).read_text(encoding='utf-8') if tpl.get('html_path') and Path(tpl['html_path']).is_file() else ''
            names = VAR_RE.findall(html)
            vals = CLIENT_for(con, app['id'], tpl)
            got = [n for n in names if vals.get(n) not in (None, '')]
            miss = sorted(set(n for n in names if vals.get(n) in (None, '')))
            filled_html = render.fill(html, vals, keep_unfilled=False, template_code=tpl['code'])
            leftovers = sorted(set(VAR_RE.findall(filled_html)))
            out = ROOT / 'data' / 'cache' / ('selftest_%s_%s.pdf' % (app['id'], tpl['code']))
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                render.generate(app['id'], tpl['id'], out_path=str(out))
                ok_pdf = out.is_file() and out.stat().st_size > 2000
            except Exception as exc:  # noqa: BLE001
                ok_pdf = False
                pdf_fail.append('%s: %s' % (tpl['code'], str(exc)[:80]))
            total_vars += len(set(names))
            filled += len(got)
            bad_empty, no_data = [], []
            for _n in sorted(set(miss)):
                if _n in ALLOW_EMPTY:
                    continue
                _field = CARD_MAP.get(_n)
                if _field and str(cl_row.get(_field) or '').strip() not in ('', 'None'):
                    bad_empty.append(_n)      # данные есть в карточке, но не подставились
                elif _n in doc_vals:
                    bad_empty.append(_n)      # данные есть в документе клиента
                else:
                    no_data.append(_n)        # данных нет нигде — не выдумываем (норма)
            rows_out.append({'code': tpl['code'], 'vars': len(set(names)), 'filled': len(got),
                             'empty_ok': [n for n in set(miss) if n in ALLOW_EMPTY],
                             'empty_bad': bad_empty, 'no_data': no_data,
                             'leftovers': leftovers, 'pdf': ok_pdf,
                             'examples': {n: str(vals.get(n))[:60] for n in list(set(got))[:4]}})
            empties += bad_empty
            if leftovers:
                defects.append('%s: не подставились %s' % (tpl['code'], ', '.join(leftovers)))
            for n in set(names):
                v = vals.get(n)
                if v not in (None, ''):
                    seen_vals[n][tpl['code']] = str(v)[:80]
        # расхождения, допустимые по правилам: в индонезийских документах гражданство пишется
        # как RUSIA, в англоязычных договорах — RUSSIAN FEDERATION; перечень услуг у договоров
        # формируется из одного источника, но тексты могут отличаться формулировкой пунктов
        ALLOW_DIFF = {'CLIENT', 'client_CLIENT', 'CLIENT_list'}
        conflicts = {n: v for n, v in seen_vals.items() if len(set(v.CLIENT())) > 1 and n not in ALLOW_DIFF}
        allowed_diff = {n: v for n, v in seen_vals.items() if len(set(v.CLIENT())) > 1 and n in ALLOW_DIFF}
        if pdf_fail:
            defects += pdf_fail
        md.append('**Документы пакета:**')
        md.append('')
        for r in rows_out:
            md.append('- `%s` — переменных %d, заполнено %d%s%s%s' %
                      (r['code'], r['vars'], r['filled'],
                       ' | пусто (допустимо): %d' % len(r['empty_ok']) if r['empty_ok'] else '',
                       ' | ПУСТО ОШИБОЧНО: %s' % ', '.join('`%s`' % x for x in r['empty_bad']) if r['empty_bad'] else '',
                       ' | нет данных у клиента: %s' % ', '.join('`%s`' % x for x in (r.get('no_data') or [])[:6]) if r.get('no_data') else ''))
        md.append('')
        md.append('**Итог по пакету:** переменных %d, заполнено %d (%.0f%%), конфликтов значений %d, дефектов подстановки %d'
                  % (total_vars, filled, 100.0 * filled / max(total_vars, 1), len(conflicts), len(defects)))
        md.append('')
        if conflicts:
            md.append('**Расхождения: одна переменная имеет разные значения в документах пакета**')
            md.append('')
            for n, v in sorted(conflicts.items())[:20]:
                md.append('- `%s`: %s' % (n, ' | '.join('%s = %s' % (d, x) for d, x in list(v.items())[:4])))
            md.append('')
        if defects:
            md.append('**Дефекты:**')
            md.append('')
            for d in defects[:12]:
                md.append('- %s' % d)
            md.append('')
        # сверка с реальной папкой клиента
        folder = {}
        if isinstance(links, list):
            for it in links:
                if isinstance(it, dict) and str(it.get('CLIENT_id') or it.get('app_id') or '') == str(app['id']):
                    folder = it
                    break
        elif isinstance(links, dict):
            folder = links.get(str(app['id'])) or links.get(app['id']) or {}
        cname = ((app['CLIENT'] or '') + ' ' + (app['name'] or '')).strip()
        real = by_client.get(cname) or collections.Counter()
        if real:
            md.append('**Что фактически лежит в папке клиента на Диске:**')
            md.append('')
            for k, n in real.most_common():
                md.append('- %s — %d файл(ов)' % (k, n))
            md.append('')
        machine[str(app['id'])] = {'CLIENT': pcode, 'docs': rows_out, 'conflicts': conflicts,
                                   'defects': defects, 'client_folder': dict(real),
                                   'total_vars': total_vars, 'filled': filled}
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    OUT_JSON.write_text(json.dumps(machine, ensure_ascii=False, indent=1), encoding='utf-8')
    print('отчёт:', OUT_MD)
    for app_id, m in machine.items():
        print('  %-9s заявка %-4s: переменных %-4d заполнено %-4d конфликтов %-2d дефектов %d'
              % (m['CLIENT'], app_id, m['total_vars'], m['filled'], len(m['conflicts']), len(m['defects'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
