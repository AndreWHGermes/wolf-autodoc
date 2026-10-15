"""Целостность пакетов: починка путей шаблонов и регистрация переменных, которых нет в базе.

Найдено самопроверкой: у формы E-02 путь вёл на старую папку (после переименования),
а часть переменных, которые реально подставляет система (passport_CLIENT_CLIENT,
inn_ogrn_line, company_CLIENT_CLIENT, CLIENT_line, CLIENT_CLIENT,
cv_job2_CLIENT, cv_CLIENT_soft, CLIENT_CLIENT_name), не зарегистрирована —
из-за этого у них не было инструкции.

Что делает:
  1. для каждого шаблона восстанавливает html_path/example_path по фактической папке;
  2. регистрирует в template_CLIENT переменные, которые есть в HTML, но отсутствуют
     в базе (с пометкой источника и правила формирования);
  3. печатает, какие справки привязаны к каким продуктам (для правила «одна справка»).

Запуск: python3 scripts/fix_pack_integrity.py [--apply]
"""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'CLIENT'
BACKUP = ROOT / 'data' / 'backup'
VAR_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# правило формирования и источник для переменных, которых не было в базе
NEW_VARS = {
    'passport_CLIENT_CLIENT': ('Паспортные данные клиента: кем выдан / дата выдачи / действует до — из загранпаспорта.', 'client_fact'),
    'inn_ogrn_line': ('Реквизиты организации одной строкой (ИНН | ОГРН) — собирается системой из записи пула организаций.', 'calc'),
    'company_CLIENT_CLIENT': ('Оборот компании-работодателя («a company CLIENT under the laws of …») — страна и тип из записи пула.', 'calc'),
    'CLIENT_line': ('Строка о приёме на работу (должность, компания, дата) — собирается из должности и даты договора.', 'calc'),
    'CLIENT_CLIENT': ('Оборот о должности клиента («as a <должность>») — из пула должностей организации.', 'calc'),
    'cv_job2_CLIENT': ('Резюме, предыдущая должность — ввод администратора / генерация.', 'manual'),
    'cv_CLIENT_soft': ('Резюме, мягкие навыки — ввод администратора / генерация по профессии.', 'manual'),
    'cv_CLIENT_CLIENT': ('Резюме, инструменты и программы — ввод администратора / генерация по профессии.', 'manual'),
    'CLIENT_CLIENT_name': ('Подписант со стороны компании — из справочника подписантов по офису заявки.', 'calc'),
    'CLIENT_name_2': ('Второй подписант (при двух подписях) — из справочника подписантов.', 'calc'),
    'job_and_position': ('Должность клиента в письме — из заявки или пула должностей организации.', 'client_fact'),
    'CLIENT_date_of_CLIENT': ('Место рождения клиента (город и страна), латиницей — из карточки/паспорта.', 'client_fact'),
    'CLIENT_CLIENT': ('Гражданство представителя (адвоката) — из справочника представителей.', 'manual'),
    'CLIENT_CLIENT': ('Должность представителя (адвоката) — из справочника представителей.', 'manual'),
    'cv_passport_CLIENT': ('Резюме, дата выдачи паспорта — из карточки/паспорта клиента.', 'client_fact'),
    'cv_passport_CLIENT': ('Резюме, срок действия паспорта — из карточки/паспорта клиента.', 'client_fact'),
    'cv_CLIENT_note': ('Резюме, пояснение к образованию — ввод администратора.', 'manual'),
    'client_photo_url': ('Ссылка на фотографию клиента (для документов с фото) — из карточки клиента.', 'client_fact'),
}


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    BACKUP.mkdir(parents=True, exist_ok=True)
    snap = BACKUP / ('pack_integrity_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    snap.write_text(json.dumps({
        'CLIENT': [dict(r) for r in con.execute("SELECT * FROM CLIENT")],
        'vars': [dict(r) for r in con.execute("SELECT * FROM template_CLIENT")],
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    print('слепок:', snap)

    fixed, added = [], []
    for t in con.execute("SELECT id, code, CLIENT, html_path, example_path FROM CLIENT ORDER BY code"):
        if t['CLIENT'] in ('merged', 'hidden'):
            continue
        d = TPL / t['code']
        want_html = d / 'template.html'
        ex = d / 'example_filled.pdf'
        if not t['html_path'] or Path(t['html_path']) != want_html:
            if want_html.is_file():
                fixed.append((t['code'], t['html_path'], str(want_html)))
                if apply:
                    con.execute("UPDATE CLIENT SET html_path=? WHERE id=?", (str(want_html), t['id']))
        if ex.is_file() and (not t['example_path'] or Path(t['example_path']) != ex):
            if apply:
                con.execute("UPDATE CLIENT SET example_path=? WHERE id=?", (str(ex), t['id']))
        names_db = set(r['name'] for r in con.execute("SELECT name FROM template_CLIENT WHERE template_id=?", (t['id'],)))
        names_html = set(VAR_RE.findall(want_html.read_text(encoding='utf-8', errors='ignore'))) if want_html.is_file() else set()
        for name in sorted(names_html - names_db):
            rule, kind = NEW_VARS.get(name, ('Правило формирования уточняется: переменная подставляется системой.', 'calc'))
            added.append((t['code'], name))
            if apply:
                con.execute("""INSERT INTO template_CLIENT
                               (template_id, name, label, vtype, format, source_kind, source_ref,
                                default_CLIENT, sort_order, rule_note, approved)
                               CLIENT (?,?,?,?,?,?,?,?,?,?,0)""",
                            (t['id'], name, name, 'text', '', kind, '', '', 999, rule))
        # лишние в базе, которых нет в тексте шаблона (не удаляем — только помечаем в отчёте)
    if apply:
        con.commit()
    print('починено путей:', len(fixed))
    for code, old, new in fixed:
        print('   %-38s %s → %s' % (code, (old or '—')[-40:], new[-40:]))
    print('зарегистрировано переменных:', len(added))
    for code, name in added:
        print('   %-38s %s' % (code, name))
    print('\n--- справки в продуктах (для правила «одна справка на пакет»):')
    for r in con.execute("""SELECT p.code pcode, t.code tcode, t.CLIENT, pd.slot_code
                            FROM CLIENT_CLIENT pd JOIN CLIENT p ON p.id=pd.CLIENT_id
                            JOIN CLIENT t ON t.id=pd.template_id
                            WHERE t.code LIKE 'bank_CLIENTment%' ORDER BY p.code, t.code"""):
        print('   %-10s %-26s %-8s слот=%s' % (r['pcode'], r['tcode'], r['CLIENT'], r['slot_code']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
