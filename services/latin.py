"""Латинская запись русских данных для документов.

Документы пакета — на английском, а справочники (организации, адреса, города)
в системе заполнены по-русски: «ООО «Медиа Сервис»», «г. Москва, ул. Дубининская».
Если подставлять их как есть, в английском бланке появляется русский текст —
проверка ставит блокировку «русский текст в документе».

Правила записи:
  * известные компании — их собственное написание (Росгосстрах → Rosgosstrakh);
  * организационная форма — латинская: ООО → LLC, АО → JSC, ПАО → PJSC, ИП → IE;
  * остальное — практическая транслитерация (ГОСТ 7.79-2000, система Б);
  * ФИО — «Имя И. Фамилия» (CLIENT Yu. Reshetnikov);
  * адресные сокращения — по-английски (ул. → ul., д. → d., офис → office).
"""
from __future__ import annotations

import re

# Организационная форма: русская запись → латинская.
FORMS = (
    ('ООО', 'LLC'), ('ОАО', 'OJSC'), ('ЗАО', 'CJSC'), ('ПАО', 'PJSC'),
    ('АО', 'JSC'), ('ИП', 'IE'), ('НКО', 'NPO'), ('ФГУП', 'FSUE'), ('МУП', 'MUE'),
)

# Известные компании и города: берём их собственное латинское написание,
# транслитерация тут даёт неверный результат.
KNOWN_ORGS = {
    'росгосстрах': 'Rosgosstrakh',
    'россгосстрах': 'Rosgosstrakh',
    'сбербанк': 'Sberbank',
    'т-банк': 'T-Bank',
    'тбанк': 'T-Bank',
    'тинькофф': 'Tinkoff',
    'альфа-банк': 'Alfa-Bank',
    'втб': 'VTB',
    'газпромбанк': 'Gazprombank',
    'райффайзенбанк': 'Raiffeisenbank',
    'открытие': 'Otkritie',
    'яндекс': 'Yandex',
    'озон': 'Ozon',
    'вконтакте': 'VK',
    'маил.ру': 'Mail.ru',
    'медиа сервис': 'Media Service',
    'роснефть': 'Rosneft',
    'лукойл': 'Lukoil',
    'аэрофлот': 'Aeroflot',
    'мтс': 'MTS',
    'билайн': 'Beeline',
    'мегафон': 'MegaFon',
    'ростелеком': 'Rostelecom',
}

KNOWN_CITIES = {
    'москва': 'Moscow',
    'санкт-петербург': 'Saint Petersburg',
    'спб': 'Saint Petersburg',
    'екатеринбург': 'Yekaterinburg',
    'новосибирск': 'Novosibirsk',
    'казань': 'Kazan',
    'нижний новгород': 'Nizhny Novgorod',
    'самара': 'Samara',
    'ростов-на-дону': 'Rostov-on-Don',
    'краснодар': 'Krasnodar',
    'воронеж': 'Voronezh',
    'пермь': 'Perm',
    'уфа': 'Ufa',
    'челябинск': 'Chelyabinsk',
    'волгоград': 'Volgograd',
}

# Практическая транслитерация: буква → латиница (ГОСТ 7.79-2000, система Б).
_TR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    '—': '-', '–': '-', '«': '', '»': '', '№': 'No.',
}

# Адресные сокращения: русское сокращение → английское.
_ADDR = (
    (r'\bвн\.?\s*тер\.?\s*г\.?', ''),
    (r'\bмуниципальный округ\b', 'municipal district'),
    (r'\bобл\.?\b', 'oblast'),
    (r'\bобласть\b', 'oblast'),
    (r'\bкрай\b', 'krai'),
    (r'\bг\.\s*', ''),
    (r'\bул\.\s*', 'ul. '),
    (r'\bпр-т\b', 'ave.'),
    (r'\bпроспект\b', 'avenue'),
    (r'\bш\.\s*', 'sh. '),
    (r'\bд\.\s*', 'd. '),
    (r'\bк\.\s*', 'bldg. '),
    (r'\bкорп\.\s*', 'bldg. '),
    (r'\bофис\b', 'office'),
    (r'\bоф\.\s*', 'office '),
    (r'\bпом\.\s*', 'premises '),
    (r'\bэтаж\b', 'floor'),
    (r'\bкв\.\s*', 'apt. '),
    (r'\bдом\b', 'house'),
    (r'\bгород\b', 'city'),
)

_CYR = re.compile(r'[А-Яа-яЁё]')


def has_cyrillic(text) -> bool:
    """Есть ли в значении русские буквы."""
    return bool(_CYR.search(str(text or '')))


def translit(text) -> str:
    """Практическая транслитерация русской строки латиницей."""
    src = str(text or '')
    out = []
    for ch in src:
        low = ch.lower()
        if low in _TR:
            lat = _TR[low]
            if ch.isupper() and lat:
                lat = lat[0].upper() + lat[1:]
            out.append(lat)
        else:
            out.append(ch)
    s = ''.join(out)
    # «Даниловский» → Danilovsky, а не Danilovskiy: так пишут в английских документах.
    s = re.sub(r'skiy\b', 'sky', s)
    s = re.sub(r'Skiy\b', 'Sky', s)
    return s


def _clean_spaces(s: str) -> str:
    s = re.sub(r'\s+', ' ', s or '').strip()
    s = re.sub(r'\s+([,.])', r'\1', s)
    return s


def org_name(name) -> str:
    """«ООО «Медиа Сервис»» → «Media Service LLC»."""
    raw = str(name or '').strip()
    if not raw:
        return ''
    if not has_cyrillic(raw):
        return _clean_spaces(raw)
    m = re.match(r'^\s*(ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО|ФГУП|МУП)\s*[«"”\']?\s*([^»"”\']*?)\s*[»"”\']?\s*$',
                 raw, flags=re.IGNORECASE)
    form_lat = ''
    core = raw
    if m:
        for ru, lat in FORMS:
            if m.group(1).upper() == ru:
                form_lat = lat
                break
        core = m.group(2).strip()
    key = core.strip().lower()
    lat_core = KNOWN_ORGS.get(key)
    if not lat_core:
        lat_core = _clean_spaces(translit(core))
        # «Росгосстрах» внутри более длинного названия
        for ru, lat in KNOWN_ORGS.items():
            if ru in key:
                lat_core = re.sub(ru, lat, lat_core, flags=re.IGNORECASE)
                break
    lat_core = lat_core.title() if lat_core.isupper() or lat_core.islower() else lat_core
    return _clean_spaces('%s %s' % (lat_core, form_lat)) if form_lat else lat_core


def person(fio) -> str:
    """«Решетников Михаил Юрьевич» → «CLIENT Yu. Reshetnikov»."""
    raw = str(fio or '').strip()
    if not raw:
        return ''
    if not has_cyrillic(raw):
        return _clean_spaces(raw)
    parts = [p for p in re.split(r'\s+', raw) if p]
    lat = [_clean_spaces(translit(p)).title() for p in parts]
    if len(lat) == 3:
        return '%s %s. %s' % (lat[1], lat[2][:1], lat[0])
    if len(lat) == 2:
        return '%s %s' % (lat[1], lat[0])
    return ' '.join(lat)


def address(addr) -> str:
    """Русский адрес латиницей с английскими сокращениями."""
    raw = str(addr or '').strip()
    if not raw:
        return ''
    if not has_cyrillic(raw):
        return _clean_spaces(raw)
    s = raw
    for pat, rep in _ADDR:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    out = []
    for chunk in s.split(','):
        words = []
        for w in chunk.split():
            low = w.strip('.,').lower()
            if low in KNOWN_CITIES:
                words.append(KNOWN_CITIES[low].title() if low != KNOWN_CITIES[low] else KNOWN_CITIES[low])
            else:
                words.append(_clean_spaces(translit(w)))
        out.append(' '.join(words))
    return _clean_spaces(', '.join(x for x in out if x.strip()))


def city(name) -> str:
    """«Москва» → «Moscow»."""
    raw = str(name or '').strip()
    if not raw:
        return ''
    latin = KNOWN_CITIES.get(raw.lower())
    if latin:
        return latin
    if not has_cyrillic(raw):
        return _clean_spaces(raw)
    return _clean_spaces(translit(raw)).title()


def value(text) -> str:
    """Общая точка входа: если в значении русские буквы — записать латиницей."""
    s = str(text or '')
    if not has_cyrillic(s):
        return s
    return _clean_spaces(translit(s))
