#!/usr/bin/env python3
"""Сбор пула организаций, видов деятельности и должностей из архивных документов.

Источник — только те документы, где значения уже заполнены: комплекты клиентов из кэша
Google Диска (data/gdrive_cache/client_*/), подлинники-эталоны (data/templates/*/example_filled.pdf,
data/originals/*.pdf), справочные комплекты docs/reference/.

Что собираем:
  * organizations — название, адрес, ИНН/КПП/ОГРН и прочие реквизиты, виды деятельности, должности;
  * sectors       — вид деятельности, к нему описание (из чего состоит) и типовые должности;
  * positions     — должности по частоте (чем занимаются люди в этих организациях).

Результат: data/harvest_orgs.json (сырьё для слияния в data/organizations.json).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
OUT = ROOT / 'data' / 'harvest_orgs.json'

# ── виды деятельности: код → (человеческое название, из чего состоит, ключевые слова) ──
SECTORS = {
    'services_agency': ('Услуги и агентства',
                        'маркетинг, реклама, SMM, дизайн, консалтинг, кадры, юридические и деловые услуги',
                        ('marketing', 'advertis', 'smm', 'social media', 'brand', 'pr ', 'design', 'consult',
                         'agency', 'recruit', 'staffing', 'outsourc', 'маркет', 'реклам', 'агентств')),
    'it_software': ('ИТ и разработка',
                    'разработка ПО, интеграция, поддержка систем, данные, тестирование',
                    ('software', 'develop', 'programm', 'information technolog', 'it ', 'data', 'digital',
                     'technolog', 'разработ', 'программ')),
    'logistics_trade': ('Логистика и торговля',
                        'перевозки, склад, закупки, импорт-экспорт, оптовая торговля',
                        ('logistic', 'freight', 'forwarding', 'shipping', 'transport', 'warehouse', 'trade',
                         'import', 'export', 'supply', 'логист', 'торгов', 'поставк')),
    'bank_insurance': ('Банки и страхование',
                       'банковские услуги, страхование, финансы, инвестиции, бухгалтерия',
                       ('bank', 'insurance', 'financial', 'finance', 'invest', 'capital', 'credit',
                        'страхов', 'банк', 'финанс')),
    'media_education': ('Медиа и образование',
                        'издательства, медиа, обучение, курсы, репетиторство, культура',
                        ('media', 'publish', 'educat', 'school', 'learn', 'academy', 'training', 'studio',
                         'образова', 'издатель', 'медиа')),
    'ecommerce_retail': ('Розница и электронная торговля',
                         'магазины, маркетплейсы, электронная коммерция, продажи конечному покупателю',
                         ('retail', 'shop', 'store', 'ecommerce', 'e-commerce', 'marketplace', 'seller',
                          'ритейл', 'магазин', 'маркетплей')),
    'household_service': ('Бытовые услуги',
                          'сервис, ремонт, обслуживание, гостеприимство, клининг, общепит',
                          ('service', 'repair', 'cleaning', 'hospitality', 'hotel', 'restaurant', 'cafe',
                           'food', 'бытов', 'ремонт', 'обслуж')),
    'construction_architecture': ('Строительство и архитектура',
                                  'строительство, проектирование, архитектура, инженерия зданий',
                                  ('construct', 'architect', 'building', 'engineering', 'real estate',
                                   'строит', 'архитект')),
    'industry_production': ('Производство',
                            'заводы, производство товаров, переработка, промышленность',
                            ('manufactur', 'production', 'factory', 'industrial', 'plant', 'производ', 'завод')),
}

FORM = r'(?:LLC|L\.L\.C|LTD|LIMITED|LLP|INC|CORP|CO\.|GMBH|PT|PTE|IP|IE|ООО|ОАО|ЗАО|ПАО|АО|ИП)'
ORG_RE = re.compile(r'\b(' + FORM + r'\s*[«"\']?[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9 "\'.,&\-]{2,60}?)(?=[,;.]|\s+(?:a|an|is|with|has|was|the)\b|$)', re.M)
INN_RE = re.compile(r'(?:INN|ИНН)[:\s]*([0-9]{10,12})', re.I)
KPP_RE = re.compile(r'(?:KPP|КПП)[:\s]*([0-9]{9})', re.I)
OGRN_RE = re.compile(r'(?:OGRN|OGRNIP|ОГРН|ОГРНИП)[:\s]*([0-9]{13,15})', re.I)
POS_RE = re.compile(r'(?:position of|employed as|engaged as|as an?\s|Position:|Title:)\s*((?:[A-Z][A-Za-z/&\-]+(?:\s+[A-Z][A-Za-z/&\-]+){0,4}))', re.M)
ADDR_RE = re.compile(r'((?:[0-9]{5,6}\s*,\s*)?[A-Z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+){0,3}\s*,\s*(?:street|str\.|ul\.|avenue|prospekt|lane|district|Oblast|region)[^,\n]{5,80})', re.I)


def texts_from(path: Path) -> str:
    try:
        import pymupdf
    except ImportError:
        return ''
    try:
        doc = pymupdf.open(path)
    except Exception:
        return ''
    out = []
    for page in doc:
        try:
            out.append(page.get_text())
        except Exception:
            continue
    return ' '.join(' '.join(out).split())


def sector_of(text: str) -> str:
    low = text.lower()
    best, score = '', 0
    for code, (_name, _desc, keys) in SECTORS.items():
        s = sum(low.count(k) for k in keys)
        if s > score:
            best, score = code, s
    return best if score >= 2 else ''



def doc_kind(path: Path, text: str) -> str:
    """Тип архивного документа: в выписках и паспортах названий работодателей нет —
    оттуда тянуть организации нельзя, там контрагенты и служебные строки."""
    n = path.name.lower()
    t = text.lower()
    if any(w in n for w in ('bank', 'statement', 'personalbank', 'выписк', 'passport', 'паспорт')):
        return 'bank' if 'bank' in n or 'statement' in n or 'personalbank' in n or 'выписк' in n else 'passport'
    if any(w in n for w in ('resume', 'cv', 'резюме')):
        return 'resume'
    if any(w in n for w in ('contract', 'agreement', 'договор', 'employment')):
        return 'contract'
    if any(w in n for w in ('letter', 'письмо', 'statement_letter', 'form e-02', 'e-02')):
        return 'letter'
    if 'bank statement' in t or 'account statement' in t or 'opening balance' in t:
        return 'bank'
    if 'passport' in t and 'nationality' in t and 'date of birth' in t:
        return 'passport'
    if ('work experience' in t or 'professional experience' in t or 'education' in t) and 'position' in t:
        return 'resume'
    if 'agreement' in t and ('employer' in t or 'employee' in t or 'contractor' in t):
        return 'contract'
    return 'other'


def main() -> None:
    sources = []
    for pat in ('data/gdrive_cache/**/*.pdf', 'data/templates/*/example_filled.pdf',
                'data/originals/*.pdf', 'docs/reference/**/*.pdf'):
        sources += sorted(ROOT.glob(pat))
    sources = [p for p in sources if p.is_file()]
    print('документов к разбору:', len(sources), file=sys.stderr)

    orgs: dict[str, dict] = {}
    pos_counter: Counter = Counter()
    sec_counter: Counter = Counter()
    sec_positions: dict[str, Counter] = defaultdict(Counter)

    for i, path in enumerate(sources, 1):
        text = texts_from(path)
        if len(text) < 80:
            continue
        kind = doc_kind(path, text)
        if kind in ('bank', 'passport'):
            continue          # в выписках и паспортах работодателей нет
        low = text.lower()
        sec = sector_of(text)
        if sec:
            sec_counter[sec] += 1
        for m in ORG_RE.finditer(text):
            name = re.sub(r'\s+', ' ', m.group(1)).strip(' "\'.,&')
            # отбрасываем служебные строки и хвосты из таблиц (цифры, коды операций)
            if len(name) < 5 or re.search(r'\b\d{3,}\b', name):
                continue
            if not any(w in name.upper() for w in ('LLC', 'LTD', 'LIMITED', 'LLP', 'INC', 'CORP', 'ООО', 'ОАО',
                                                   'ЗАО', 'ПАО', 'ИП', 'PT ', 'PT. ', 'GMBH', 'CO.')):
                continue
            key = name.lower()
            rec = orgs.setdefault(key, {'name': name, 'address': '', 'inn': '', 'kpp': '', 'ogrn': '',
                                        'sectors': [], 'positions': [], 'sources': []})
            tail = text[m.end():m.end() + 320]
            for rx, field in ((INN_RE, 'inn'), (KPP_RE, 'kpp'), (OGRN_RE, 'ogrn')):
                mm = rx.search(tail)
                if mm and not rec[field]:
                    rec[field] = mm.group(1)
            if not rec['address']:
                mm = ADDR_RE.search(tail)
                if mm:
                    rec['address'] = re.sub(r'\s+', ' ', mm.group(1)).strip(' ,')
            if sec and sec not in rec['sectors']:
                rec['sectors'].append(sec)
            if str(path) not in rec['sources']:
                rec['sources'].append(str(path.relative_to(ROOT)))
        for m in POS_RE.finditer(text):
            pos = re.sub(r'\s+', ' ', m.group(1)).strip(' .,')
            if 3 < len(pos) < 46 and not re.search(r'\b(the|and|with|shall|under)\b', pos, re.I):
                pos_counter[pos] += 1
                if sec:
                    sec_positions[sec][pos] += 1
        if i % 50 == 0:
            print('  разобрано %d/%d' % (i, len(sources)), file=sys.stderr)

    payload = {
        'note': 'Собрано из архивных документов: организации с реквизитами, виды деятельности, должности.',
        'organizations': sorted(orgs.values(), key=lambda o: (-len(o['sources']), o['name'])),
        'sectors': {code: {'title': v[0], 'description': v[1], 'keywords': list(v[2]),
                           'documents': sec_counter.get(code, 0),
                           'positions': [p for p, _ in sec_positions[code].most_common(25)]}
                    for code, v in SECTORS.items()},
        'positions': [{'title': p, 'count': c} for p, c in pos_counter.most_common(200)],
        'totals': {'documents': len(sources), 'organizations': len(orgs), 'positions': len(pos_counter)},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print('итог: организаций %d, видов деятельности %d, должностей %d → %s'
          % (len(orgs), len(SECTORS), len(pos_counter), OUT), file=sys.stderr)
    top = payload['organizations'][:12]
    for o in top:
        print('   %-38s %-22s inn=%-12s должн=%s' % (o['name'][:36], ','.join(o['sectors'])[:20],
                                                     o['inn'], len(o['positions'])), file=sys.stderr)


if __name__ == '__main__':
    main()
