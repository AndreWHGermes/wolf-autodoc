"""Реквизиты организации из документов клиента.

В папке клиента почти всегда есть его договор или справка с реквизитами
работодателя: ИНН, КПП, ОГРН, юридический адрес, название. Раньше мы это
не читали — и в договорах, которые собираем сами, реквизиты оставались
пустыми, хотя данные лежали в присланных файлах.

Понимает и русскую запись («ИНН 000000000, КПП 773101001, ОГРН ...»),
и английскую, как в наших бланках («INN 000000000, KPP 773101001»).
"""
from __future__ import annotations

import re

# названия: ООО «КУПИШУЗ», LLC "KUPISHUZ", JSC "SOTKA"
_NAME_RU = re.compile(r'(ООО|АО|ПАО|ЗАО|ОАО|ИП)\s*[«"”]?\s*([^»"”,\n]{2,60})', re.I)
_NAME_EN = re.compile(r'\b(LLC|Ltd|Limited|JSC|PJSC|PLC|Inc|Corp)\b\s*[«"”]?\s*'
                      r'([A-Z][^»"”,\n]{1,60})')

# «Limited Stay Visa No. 26E33G97730» — это вид разрешения, а не компания:
# такие сочетания в названия попадать не должны
_NOT_A_NAME = (
    'stay visa', 'stay permit', 'limited stay', 'visit visa', 'entry visa', 'kitas',
    'permit no', 'visa no', 'passport no', 'krasnodar', 'краснодар', 'moscow, ',
    'bank', 'statement', 'insurance', 'policy', 'agreement no', 'contract no',
    # служебные слова бланков: «Limited "Suite C"», «Limited "Signature …"»
    'signature', 'suite', 'registered office', 'part a', 'part b', 'article',
    'section', 'annex', 'schedule', 'exhibit', 'blank', 'page',
)


def _clean_name(raw: str) -> str:
    """Убрать из названия хвосты вроде «permit No …» и отбраковать мусор."""
    name = re.sub(r'\s+', ' ', str(raw or '')).strip(' »,."')
    low = name.lower()
    if any(bad in low for bad in _NOT_A_NAME):
        return ''
    # «No. 26E33G…», «№ 123» — это номер документа, а не название
    if re.match(r'^(no\.?|№)\s*\S', low) or re.search(r'\bno\.?\s*\d', low):
        return ''
    words = [w for w in re.split(r'[\s/,]+', name) if len(w) > 1]
    if not words or len(name) < 3:
        return ''
    # одиночная аббревиатура без названия («LLC», «ИП») — не компания
    if len(words) == 1 and words[0].upper() in ('LLC', 'LTD', 'JSC', 'PJSC', 'PLC',
                                                'INC', 'CORP', 'ИП', 'ООО', 'АО'):
        return ''
    return name[:70]

_ORG_KEYS = {
    'inn': (r'\bИНН\b[^\d]{0,6}(\d{10}|\d{12})', r'\bINN\b[^\d]{0,6}(\d{10}|\d{12})',
            r'\bTax\s*ID\b[^\d]{0,6}(\d{10}|\d{12})'),
    'kpp': (r'\bКПП\b[^\d]{0,6}(\d{9})', r'\bKPP\b[^\d]{0,6}(\d{9})'),
    'ogrn': (r'\bОГРН\b[^\d]{0,6}(\d{13})', r'\bOGRN\b[^\d]{0,6}(\d{13})',
             r'\bOGRNIP\b[^\d]{0,6}(\d{15})'),
}
_ADDRESS = (
    r'(?:юридический\s+адрес|адрес\s+место\s+нахождения|registered\s+address|'
    r'address\s+of\s+the\s+company|company\s+address)[:\s]*([^\n]{10,140})',
    r'(?:адрес)[:\s]*((?:Россия|г\.|улица|ул\.|проспект|просп\.)[^\n]{10,140})',
)


def parse_company(text: str) -> dict:
    """Вытащить реквизиты организации из текста документа."""
    out: dict = {}
    t = text or ''

    for key, patterns in _ORG_KEYS.items():
        for p in patterns:
            m = re.search(p, t, re.I)
            if m:
                out['company_' + key] = m.group(1)
                break

    # место нахождения часто идёт одной строкой с индексом: «123308, Москва, ...»
    for p in _ADDRESS:
        m = re.search(p, t, re.I)
        if m:
            addr = re.sub(r'\s+', ' ', m.group(1)).strip(' ,.')
            # в строку адреса часто затягиваются реквизиты: «Kazan, INN: 1660338214…»
            addr = re.split(r',?\s*(?:\bINN\b|\bКПП\b|\bKPP\b|\bОГРН\b|\bOGRN\b|\bИНН\b)',
                            addr, flags=re.I)[0].strip(' ,.')
            # «in Kazan» — предлог попал из формулировки договора
            addr = re.sub(r'^(?:in|at|г\.?)\s+', '', addr, flags=re.I).strip(' ,.')
            if len(addr) > 3:
                out['company_registered_address'] = addr[:160]
                break

    # название: сначала английская форма (она уходит в наши бланки), потом русская
    name_en = ''
    for m in _NAME_EN.finditer(t):
        # название заканчивается на кавычке/запятой/переносе — иначе в него
        # затягивается хвост строки («LLC "SOTKA, INN 1660338214»)
        inner = re.split(r'["»”\n,]', m.group(2).strip())[0].strip()
        cand = _clean_name('%s "%s"' % (m.group(1), inner))
        if cand:
            # закрывающая кавычка обязана остаться: в бланке печатается «LLC "SOTKA"»
            if cand.count('"') % 2:
                cand += '"'
            name_en = cand
            break
    m_ru = _NAME_RU.search(t)
    name_ru = ''
    if m_ru:
        inner = _clean_name(m_ru.group(2))
        if inner:
            name_ru = '%s «%s»' % (m_ru.group(1).upper(), inner)
    if name_ru:
        out.setdefault('company_name_ru', name_ru)
    if name_en:
        out['company_name'] = name_en
        out.setdefault('company_name_in_quotes', name_en)
        out.setdefault('company_full_name', name_en)
    elif name_ru:
        out['company_name'] = name_ru

    # строка реквизитов одним значением — как её печатают в бланках
    parts = []
    if out.get('company_inn'):
        parts.append('INN %s' % out['company_inn'])
    if out.get('company_kpp'):
        parts.append('KPP %s' % out['company_kpp'])
    if out.get('company_ogrn'):
        parts.append('OGRN %s' % out['company_ogrn'])
    if parts:
        out['inn_kpp_ogrn'] = ', '.join(parts)
    return out


def looks_like_company_doc(text: str) -> bool:
    """Есть ли в тексте признаки реквизитов организации."""
    t = (text or '').lower()
    if any(x in t for x in ('инн', 'кпп', 'огрн', 'inn', 'kpp', 'ogrn')):
        return True
    return bool(_NAME_RU.search(text or '') or _NAME_EN.search(text or ''))
