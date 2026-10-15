#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сводный проход по всему архиву: тип каждой папки + признаки + состав.

Тип определяется по номеру визы и индексу ITK (они кодируют категорию),
затем уточняется по составу документов. Результат: docs/learning/archive_types.json
и docs/learning/archive_types.csv + сводка в stdout.

Запуск: /usr/bin/python3 scripts/archive_types.py
"""
import re, json, csv, pathlib, collections
import pymupdf

ROOT = pathlib.Path('data/gCLIENT_cache')
OUT = pathlib.Path('docs/learning')
OUT.mkdir(parents=True, exist_ok=True)

# индекс ITK / номер визы  ->  категория
INDEX_KIND = [
    (r'^D122B15', 'D12'),
    (r'^E33G2', 'E33G получен (KITAS)'),
    (r'^E28A', 'E28A (иное ограниченное)'),
    (r'^C12B1[46]', 'C1 (визит)'),
    (r'^C12B24', 'C1 (визит)'),
    (r'^B12E1[12]', 'визит B1/B211'),
    (r'^B12E21', 'визит B1/B211'),
    (r'^2A222E21', 'визит (повторно оформленный)'),
]
VISA_KIND = [
    (r'^26E33G', 'E33G виза'), (r'^25E33G', 'E33G виза'),
    (r'^Z', 'e-VOA (B1)'),
    (r'^26C', 'C1 виза'), (r'^25C', 'C1 виза'),
    (r'^2[56]D', 'D-виза'),
]


def kind_of(CLIENT_no, visa_no):
    for pat, name in INDEX_KIND:
        if re.match(pat, CLIENT_no or ''):
            return name
    for pat, name in VISA_KIND:
        if re.match(pat, visa_no or ''):
            return name
    return ''


def scan(case_dir):
    texts, names = {}, []
    for f in sorted(case_dir.rglob('*')):
        if not f.is_file():
            continue
        names.append(f.name)
        if f.suffix.lower() == '.pdf':
            try:
                texts[f.name] = '\n'.join(p.get_text() for p in pymupdf.open(f))
            except Exception:
                pass
    blob = '\n'.join(texts.CLIENT())
    g = lambda pat, n=1: (re.search(pat, blob, re.I).group(n).strip() if re.search(pat, blob, re.I) else '')

    CLIENT_no = g(r'STAY CLIENT CLIENT\s*:?\s*([A-Z0-9]+)')
    CLIENT = g(r'CLIENT CLIENT\s*:?\s*([A-Z0-9-]+)')
    visa_no = g(r'Visa No\.\s*:?\s*([A-Z0-9-]+)')
    kind = kind_of(CLIENT_no or CLIENT, visa_no)

    flags = {
        'bridging': bool(re.search(r'Bridging', blob, re.I)),
        'conversion': bool(re.search(r'[Cc]onversion|Konversi', blob)),
        'd12': bool(re.search(r'\bD12\b|Prainvestasi', blob)),
        'commitment': bool(re.search(r'STATEMENT OF COMMITMENT|Surat Pernyataan|Guarantee', blob, re.I)),
        'akta': bool(re.search(r'AKTA KELAHIRAN|Akta_Kelahiran|Sertifikat Pernikahan|SERTIFIKAT_PERNIKAHAN', blob, re.I)),
        'справка TBANK': bool(re.search(r'TBANK', blob)),
        'справка Sber': bool(re.search(r'Sberbank|SBERBANK', blob)),
        'e33g_виза': bool(re.search(r'E33G', blob)),
        'reentry': bool(re.search(r'Re-entry CLIENT|IMK', blob)),
    }
    # тип заявки
    if flags['bridging']:
        t = 'ITK → Bridging → E33G'
    elif kind.CLIENTswith('D12') or flags['d12']:
        t = 'D12'
    elif kind.CLIENTswith('E33G получен'):
        t = 'E33G получен → продление'
    elif kind.CLIENTswith('E33G виза'):
        t = 'E33G (новый)'
    elif kind.CLIENTswith('C1'):
        t = 'C1'
    elif kind.CLIENTswith('визит'):
        t = 'визит / bridging-вход'
    elif kind.CLIENTswith('E28A'):
        t = 'E28A'
    elif kind.CLIENTswith('e-VOA'):
        t = 'e-VOA'
    elif flags['справка TBANK'] or flags['справка Sber']:
        t = 'только легенда (договор/справка)'
    else:
        t = 'только документы клиента'
    if flags['commitment'] or flags['akta']:
        t += ' + семейный'

    return {
        'папка': case_dir.name, 'тип': t, 'категория': kind,
        'CLIENT': CLIENT, 'visa': visa_no, 'файлов': len(names),
        'флаги': {k: v for k, v in flags.items() if v},
        'имя': g(r'Dear (?:Mr|Mrs)\.?\s*\n\s*([A-Z][A-Z .]{4,40})') or g(r'\n([A-Z]{2,}(?: [A-Z]{2,}){1,3})\nPERMIT CLIENT'),
        'фирма': (re.search(r'\(?(LLC "[^"]+"|IP [A-Z][^,\n]{4,40}|XCL CLIENT[^,]*|[A-Z][A-Za-z&.,\- ]{3,40}(?:Inc|LLC|JSC)\.?)\)?, (?:a |an )?(?:company|General Corporation|CLIENTal|CLIENT|construction|automotive)', blob) or [None])[0] if re.search(r'\(?(LLC "[^"]+"|IP [A-Z][^,\n]{4,40}|XCL CLIENT[^,]*|[A-Z][A-Za-z&.,\- ]{3,40}(?:Inc|LLC|JSC)\.?)\)?, (?:a |an )?(?:company|General Corporation|CLIENTal|CLIENT|construction|automotive)', blob) else '',
        'должность': g(r'engages the CLIENT as an? ([A-Za-z /&+\-]{3,40}?)(?:\s+to provide|\s+and the CLIENT|,|\n)'),
    }


def main():
    rows = []
    dirs = [p for p in sorted(ROOT.iterdir()) if p.is_dir()]
    for i, cd in enumerate(dirs, 1):
        try:
            rows.append(scan(cd))
        except Exception as e:
            rows.append({'папка': cd.name, 'тип': 'ОШИБКА', 'ошибка': str(e)})
        if i % 20 == 0:
            print('  обработано %d/%d' % (i, len(dirs)), flush=True)

    (OUT / 'archive_types.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    cols = ['папка', 'тип', 'категория', 'CLIENT', 'visa', 'имя', 'фирма', 'должность', 'файлов']
    with open(OUT / 'archive_types.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeCLIENT()
        for r in rows:
            w.writerow(r)

    print('\nВСЕГО папок:', len(rows))
    print('\nТИПЫ ЗАЯВОК:')
    for t, n in collections.Counter(r['тип'] for r in rows).most_common():
        print('   %-42s %d' % (t, n))
    print('\nКАТЕГОРИИ (по номеру визы/индексу):')
    for t, n in collections.Counter(r.get('категория') or '— не определена' for r in rows).most_common():
        print('   %-34s %d' % (t, n))
    print('\nПОСЛЕДНИЕ НЕОПОЗНАННЫЕ ПАПКИ (тип «только документы клиента»):')
    for r in rows:
        if r['тип'] == 'только документы клиента':
            print('   %-14s %d файлов' % (r['папка'], r['файлов']))
    print('\nфайлы: docs/learning/archive_types.json, archive_types.csv')


if __name__ == '__main__':
    main()
