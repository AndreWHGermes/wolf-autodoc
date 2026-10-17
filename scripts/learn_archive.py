#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обучающий разбор архива Google Диска (локальный кэш) по слоям:

1) комплектность пакета,
2) карта источников значений (какой документ даёт номер/дату какой переменной),
3) логика дат (хронология и от чего считается срок),
4) легенда (фирма, должность, доход, срок, стаж),
5) проходит ли проверку (пороги, стыковка, годность),
6) архетип заявки (группа).

Результат: docs/learning/cases_full.json (машинный) и docs/learning/cases_full.csv (сводка).
Запуск: /usr/bin/python3 scripts/learn_archive.py [--limit N]
"""
import sys, re, json, csv, pathlib, datetime
import pymupdf

ROOT = pathlib.Path('data/gdrive_cache')
OUT = pathlib.Path('docs/learning')
OUT.mkdir(parents=True, exist_ok=True)

# пороги (RUB при курсе ~83)
MIN_BAL = 2000 * 83          # C1/E33G — 2 000 USD
MIN_BAL_D12 = 5000 * 83      # D12 — 5 000 USD
MIN_YEAR_INCOME = 60000 * 83  # E33G — 60 000 USD/год


def d(s):
    """дата из ДД-ММ-ГГГГ / ДД.ММ.ГГГГ / ДД/ММ/ГГГГ"""
    m = re.match(r'(\d{2})[-/.](\d{2})[-/.](\d{4})', (s or '').strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def num(s):
    return int(re.sub(r'\D', '', s or '')[:9]) if re.sub(r'\D', '', s or '') else 0


def read_pdf(p):
    try:
        doc = pymupdf.open(p)
        return '\n'.join(pg.get_text() for pg in doc)
    except Exception:
        return ''


def analyse(case_dir):
    docs = {}
    for f in sorted(case_dir.rglob('*')):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext == '.pdf':
            docs[f.name] = read_pdf(f)
        elif ext in ('.jpg', '.jpeg', '.png'):
            docs[f.name] = ''
    blob = '\n'.join(docs.values())
    names = list(docs)

    def find(pat, n=1, flags=re.I):
        m = re.search(pat, blob, flags)
        return m.group(n).strip() if m else ''

    # --- 1. комплектность ---
    has = {
        'паспорт': any(re.search(r'passport|паспорт|загран', n, re.I) for n in names),
        'фото': any(re.search(r'photo|фото', n, re.I) for n in names),
        'статус (ITK/e-VOA)': bool(re.search(r'PERMIT NUMBER|Visa No\.', blob)),
        'справка банка': any(re.search(r'bank|personal|bankstatement|справка', n, re.I) for n in names),
        'договор': bool(re.search(r'REMOTE WORK AGREEMENT|EMPLOYMENT CONTRACT|INDEPENDENT CONTRACTOR', blob)),
        'резюме': any(re.search(r'resume|cv\b', n, re.I) for n in names),
        'письмо в иммиграцию': bool(re.search(r'PT ALPHA PRIME BALI|SURAT PERMINTAAN', blob)),
        'форма E-02': bool(re.search(r'STATEMENT LETTER|FORM E-02', blob)),
        'свидетельство (семья)': any(re.search(r'marriage|birth|pernikahan|kelahiran|свидетельств', n, re.I) for n in names),
    }
    full = all(has[k] for k in ('паспорт', 'статус (ITK/e-VOA)', 'справка банка', 'договор'))

    # --- 2/4. значения и легенда ---
    v = {}
    v['имя'] = find(r'Dear (?:Mr|Mrs)\.?\s*\n\s*([A-Z][A-Z .]{4,40})') or find(r'\n([A-Z]{2,}(?: [A-Z]{2,}){1,3})\nPERMIT NUMBER')
    v['паспорт'] = re.sub(r'\s', '', find(r'Passport No\.?\s*:?\s*([\d ]{7,15})'))
    v['др'] = find(r'Date of Birth[^:]*:\s*([\d]{2}[-/.][\d]{2}[-/.][\d]{4})')
    v['гражданство'] = find(r'(?:Nationality|Kebangsaan)[^:]*:\s*(RUSIA|RUSSIA|Russian Federation)', 1)
    v['stay_no'] = find(r'PERMIT NUMBER\s*:?\s*([A-Z0-9-]{8,20})') or find(r'Visa No\.\s*:?\s*([A-Z0-9-]{8,20})')
    v['stay_expiry'] = find(r'(?:STAY PERMIT EXPIRY|Must be used before)\s*:?\s*([\d]{2}[-/.][\d]{2}[-/.][\d]{4})')
    v['visa_type'] = find(r'Visa [Tt]ype[^:]*:\s*([A-Za-z ]{4,30})')
    v['stay_index'] = find(r'STAY PERMIT INDEX\s*:?\s*([A-Z0-9]{4,10})')
    v['address_id'] = find(r'Address(?: in Indonesia)?\s*:?\s*([^\n]{12,90})')
    v['office'] = ('Denpasar' if re.search(r'DENPASAR', v['address_id'] + blob[:0] + '') else
                   'Ngurah Rai' if re.search(r'BADUNG', v['address_id'], re.I) else
                   'Tabanan' if re.search(r'TABANAN', v['address_id'], re.I) else
                   'Gianyar' if re.search(r'GIANYAR', v['address_id'], re.I) else '')
    v['фирма'] = find(r'\((LLC "[^"]+"|Linguamarina, Inc\.|[A-Z][A-Za-z&.,\- ]{3,44}(?:Inc|LLC|Ltd)\.?)\)?, a (?:company|General Corporation)')
    v['inn'] = find(r'INN[: ]+([\d]{10,12})')
    v['ogrn'] = find(r'OGRN[: ]+([\d]{13,15})')
    v['должность'] = find(r'(?:engages the Contractor as an?|position of)\s+([A-Z][A-Za-z /&+\-]{2,40}?)(?:\s+to provide|\s+and the Employee|,|\n)')
    v['оклад_usd'] = find(r'USD\s*([\d, ]{3,12})\s*\(|(\$)\s?([\d, ]{3,12})')
    v['оклад_usd'] = find(r'USD ([\d, ]{3,12}) \(') or find(r'Base Salary \(amount & currency\):\s*\$?([\d, ]{3,12})')
    v['договор_дата'] = find(r'(?:is made on this|dated)\s+([\d]{1,2}(?:st|nd|rd|th)? day of [A-Za-z]+ \d{4})')
    v['договор_срок'] = find(r'(?:take effect on|Start Date:)\s*([\d]{1,2} [A-Za-z]+ \d{4})')
    v['договор_конец'] = find(r'(?:remain valid until|End Date:)\s*([\d]{1,2} [A-Za-z]+ \d{4})')
    v['банк'] = 'TBANK' if re.search(r'TBANK|ТБанк', blob) else ('SBER' if re.search(r'SBER|Сбербанк', blob) else '')
    v['остаток'] = find(r'deposit balance is\s*([\d \u00a0,.]{5,20})\s*rubles')
    v['период'] = find(r'As from\s*([\d.]{8,10})\s*to\s*([\d.]{8,10})') and \
                  (find(r'As from\s*([\d.]{8,10})') + '–' + find(r'to\s*([\d.]{8,10})'))
    v['маска_карты'] = find(r'card No ([\d*]{8,20})')
    v['письмо_номер'] = find(r'Nomor:\s*([\w/\-.]+)')
    v['письмо_дата'] = find(r'(?:Badung|Denpasar),\s*([\d]{1,2} [A-Za-z]+ \d{4})')

    # --- 3/5. логика дат и проверки ---
    app_date = d(v['письмо_дата']) or d(v['stay_expiry'])
    bal = num(v['остаток'])
    income_ok = None
    salary = num(v['оклад_usd'])
    if salary:
        income_ok = salary * 12 >= 60000          # USD
    threshold = MIN_BAL_D12 if (v['stay_index'] or '').startswith('D') else MIN_BAL
    checks = {
        'полный пакет': full,
        'остаток выше порога': (bal >= threshold) if bal else None,
        'годовой доход ≥ 60 000 USD': income_ok,
        'номер статуса есть': bool(v['stay_no']),
        'офис определён по адресу': bool(v['office']),
        'письмо есть и с номером': bool(v['письмо_номер']),
    }

    # --- 6. архетип ---
    arch = 'неполный'
    if full:
        if has['свидетельство (семья)']:
            arch = 'семейный'
        elif re.search(r'Bridging', blob, re.I):
            arch = 'ITK → Bridging → E33G'
        elif (v['visa_type'] or '').lower().startswith('limited stay') or 'E33G' in (v['stay_no'] or ''):
            arch = 'E33G (новый)'
        elif 'D12' in blob:
            arch = 'D12'
        elif re.search(r'Visit Visa|C1\b|B211', blob, re.I):
            arch = 'визит C1'
        else:
            arch = 'прочее'
    return {
        'папка': case_dir.name,
        'архетип': arch,
        'комплектность': {k: v_ for k, v_ in has.items()},
        'значения': v,
        'проверки': checks,
    }


def main():
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    cases = []
    dirs = [p for p in sorted(ROOT.iterdir()) if p.is_dir()]
    if limit:
        dirs = dirs[:limit]
    for cd in dirs:
        try:
            cases.append(analyse(cd))
        except Exception as e:
            cases.append({'папка': cd.name, 'ошибка': str(e)})
    (OUT / 'cases_full.json').write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding='utf-8')

    cols = ['папка', 'архетип', 'имя', 'паспорт', 'stay_no', 'stay_expiry', 'visa_type', 'office',
            'фирма', 'inn', 'должность', 'оклад_usd', 'договор_дата', 'остаток', 'период', 'письмо_номер']
    with open(OUT / 'cases_full.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for c in cases:
            if 'значения' not in c:
                continue
            z = c['значения']
            w.writerow([c['папка'], c['архетип']] + [z.get(k, '') for k in cols[2:]])

    from collections import Counter
    print('разобрано папок:', len(cases))
    print('\nАРХЕТИПЫ:')
    for k, n in Counter(c.get('архетип', 'ошибка разбора') for c in cases).most_common():
        print('   %-24s %d' % (k, n))
    print('\nПОЛНОТА:')
    full_n = sum(1 for c in cases if c.get('комплектность', {}).get('полный пакет') or
                 (c.get('комплектность') and all(c['комплектность'][k] for k in
                  ('паспорт', 'статус (ITK/e-VOA)', 'справка банка', 'договор'))))
    print('   полных пакетов:', full_n)
    print('\nГДЕ ЧЕГО НЕ ХВАТАЕТ (по всем папкам):')
    lack = Counter()
    for c in cases:
        for k, ok in (c.get('комплектность') or {}).items():
            if not ok:
                lack[k] += 1
    for k, n in lack.most_common():
        print('   нет: %-22s %d папок' % (k, n))
    print('\nПРОВЕРКИ (по полным пакетам):')
    chk = Counter()
    for c in cases:
        for k, ok in (c.get('проверки') or {}).items():
            chk[(k, ok)] += 1
    for (k, ok), n in sorted(chk.items()):
        if ok is not None:
            print('   %-30s %s — %d' % (k, 'да' if ok else 'НЕТ', n))
    print('\nфайлы: docs/learning/cases_full.json, docs/learning/cases_full.csv')


if __name__ == '__main__':
    main()
