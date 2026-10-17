"""Единый порядок адреса в англоязычных документах.

Правило Андрея: дом → номер (корпус) → название улицы → город → индекс → страна.
Внутри улицы сначала дом с квартирой, затем «ul. <название>», затем город,
регион (край/область), индекс, страна. Один формат для всех наших документов,
поэтому перестановка делается не в шаблоне, а в значении.

    en_order('350901, Краснодарский Край, Г Краснодар, Ул Российская , д. 79/3, корп. 1, кв. 653')
    → 'd. 79/3, korp. 1, kv. 653, ul. Rossiyskaya, Krasnodar, Krasnodarskiy Krai, 350901, Russia'
"""
import re

_ZIP = re.compile(r"\b(\d{6})\b")
_HOUSE = re.compile(r"\b(?:дом|д\.|house|d\.|D\.)\s*([0-9][0-9A-Za-zА-Яа-я/\\\-]*)", re.I)
_KORP = re.compile(r"(?:корпус|корп\.?|korp\.?|bldg\.?|building)\s*([0-9A-Za-zА-Яа-я/\\\-]+)", re.I)
_KV = re.compile(r"\b(?:квартира|кв\.?|apt\.?|apartment|flat|fl\.?|Kv\.?)\s*([0-9A-Za-zА-Яа-я/\\\-]+)", re.I)
_STREET = re.compile(r"\b(?:улица|ул\.?|ul\.?|street)\s*([^,;]+)", re.I)
# «стр. 1» в российском адресе — это СТРОЕНИЕ, а не улица. Раньше оно попадало
# в остаток и уезжало на место города («Str. 1, St. Petersburg»), из-за чего
# строка адреса не влезала в поле и наложение строк блокировало отправку
# (заявка 120, 17.10.2026). Учитываем только вариант с номером: «Str. 1».
_STR = re.compile(r"\b(?:строение|стр\.?|structure|struct\.?|str\.?)\s*([0-9][0-9A-Za-zА-Яа-я/\\\-]*)", re.I)
_CITY = re.compile(r"\b(?:город|г\.?|city|G\.?)\s*([^,;]+)", re.I)
_REGION = re.compile(r"([^,;]*(?:край|область|обл\.?|республика|респ\.?|округ|krai|kray|oblast|okrug|respublika|Obl\.?)[^,;]*)", re.I)
_COUNTRY = re.compile(r"(россия|российская|russia|russian federation)", re.I)

_LAT = re.compile(r"[A-Za-z]")


def _clean(v: str) -> str:
    v = re.sub(r"\s+", " ", str(v or "")).strip(" ,;.")
    return v


def en_order(addr: str, translit=None) -> str:
    """Переставить российский адрес в англоязычный порядок. Чужой формат — вернуть как есть."""
    src = _clean(addr)
    if not src or "," not in src:
        return src

    # Идемпотентность: адрес уже в нашем порядке — возвращаем как есть.
    # Без этой проверки второй проход (значение пришло из сохранённых значений
    # заявки) применял разбор к УЖЕ переставленному тексту: «D. 34» и «Kv. 252»
    # уезжали в конец, а дом с квартирой терялись. На листе это выглядело как
    # наложение двух строк адреса друг на друга.
    if re.match(r"^\s*(d\.|korp\.|kv\.|ul\.)\s*\d?", src, re.I):
        if translit and re.search(r"[А-Яа-яЁё]", src):
            return translit(src, addr=True)
        return src

    def take(rx) -> str:
        nonlocal src
        m = rx.search(src)
        if not m:
            return ""
        val = _clean(m.group(1))
        src = (src[:m.start()] + " " + src[m.end():]).strip(" ,;")
        return val

    zip_code = _clean(take(_ZIP))
    house = _clean(take(_HOUSE))
    korp = _clean(take(_KORP))
    kv = _clean(take(_KV))
    build = _clean(take(_STR))
    street = _clean(take(_STREET))
    city = _clean(take(_CITY))
    region = _clean(take(_REGION))
    # страна: если в адресе её нет словами, но адрес российский (индекс 6 цифр / край-область) —
    # в английском документе страна всё равно нужна
    country = "Russia" if (_COUNTRY.search(addr) or zip_code or region) else ""

    # если что-то не распозналось — регион/город в остатке
    rest = [p.strip() for p in re.split(r"[,;]", src) if p.strip()]
    if not region and rest:
        region = _clean(rest.pop(0))
    if not city and rest:
        city = _clean(rest.pop(0))
    if not street and rest:
        # улица без префикса («Sh Magistral'noe»): раньше терялась целиком
        street = _clean(rest.pop(0))

    parts = []
    for pref, val in (("d.", house), ("korp.", korp), ("str.", build), ("kv.", kv)):
        if val:
            parts.append(pref + " " + val)
    if street:
        parts.append("ul. " + street)
    if city:
        parts.append(city)
    if region:
        parts.append(region)
    if zip_code:
        parts.append(zip_code)
    if country:
        parts.append(country)

    out = ", ".join(parts)
    if translit and re.search(r"[А-Яа-яЁё]", out):
        out = translit(out, addr=True)
    return _clean(out) if out else src
