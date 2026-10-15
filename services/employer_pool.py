"""Пул организаций клиента для договоров (Remote Work Agreement, док. №11).

Источник — архивные подлинники договоров клиентов (data/gdrive_examples) и
собранные рендеры: у каждого клиента своя организация-работодатель.

Правила заказчика:
1. Организация подставляется в документ целиком — название в шапке и реквизиты
   в подвале берутся из ОДНОЙ записи пула, чтобы верх и низ были связаны.
2. Одна заявка = одна организация, при повторной сборке она не меняется.
3. Организация обязана быть ВНЕ Индонезии (договор удалённой работы для E33G
   заключается с иностранной компанией; индонезийское юрлицо недопустимо).
4. Приоритет выбора — город проживания клиента; если совпадений нет, берётся
   любая организация из списка (выбор детерминирован по заявке/клиенту).

Файл пула: data/employer_pool.json
Запись: {name, legal_name, address, inn, kpp, ogrn, source}
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

POOL_PATH = pathlib.Path('/opt/wolf_v2/data/employer_pool.json')

# Признаки индонезийской организации: такие в договор не попадают никогда.
ID_MARKERS = (
    'indonesia', 'jakarta', 'bali', 'denpasar', 'badung', 'gianyar', 'ubud', 'kuta',
    'surabaya', 'bandung', 'tangerang', 'banten', 'yogyakarta', 'semarang', 'medan',
    'makassar', 'batam', 'lombok', 'canggu', 'sanur', 'nusa dua', 'kabupaten',
    'kecamatan', 'kelurahan', 'npwp', 'kitab ', 'pt pma', 'pma', 'ruko', 'jalan ',
    'jl. ', 'jl ', 'indonesian', 'republik indonesia',
)

# Города из адресов пула (для подбора организации по городу клиента).
CITY_ALIASES = {
    'moscow': 'Москва', 'москва': 'Москва', 'moskva': 'Москва', 'московская': 'Москва',
    'saint petersburg': 'Санкт-Петербург', 'st. petersburg': 'Санкт-Петербург',
    'st petersburg': 'Санкт-Петербург', 'petersburg': 'Санкт-Петербург',
    'санкт-петербург': 'Санкт-Петербург', 'спб': 'Санкт-Петербург',
    'petrozavodsk': 'Петрозаводск', 'петрозаводск': 'Петрозаводск',
    'kovrov': 'Ковров', 'ковров': 'Ковров', 'CLIENT': 'Ковров', 'владимир': 'Ковров',
    'blagoveshchensk': 'Благовещенск', 'благовещенск': 'Благовещенск',
    'kazan': 'Казань', 'казань': 'Казань', 'tatarstan': 'Казань',
    'almaty': 'Алматы', 'алматы': 'Алматы', 'kazakhstan': 'Алматы',
}


def _norm(value) -> str:
    return (value or '').strip()


def is_foreign(rec: dict) -> bool:
    """Организация вне Индонезии — обязательное условие для договора."""
    text = ' '.join(_norm(rec.get(k)).lower() for k in ('name', 'legal_name', 'address'))
    return not any(m in text for m in ID_MARKERS)


def is_indonesian(text) -> bool:
    """Похоже ли, что адрес/строка относится к Индонезии (Бали, Джакарта, KITAS)."""
    low = _norm(text).lower()
    return any(m in low for m in ID_MARKERS) if low else False


def city_of(rec: dict) -> str:
    """Город организации из её адреса ('' если не распознан)."""
    return city_in_text(rec.get('address'))


def city_in_text(text) -> str:
    """Город из произвольной строки (адрес клиента, регистрация, место рождения)."""
    low = _norm(text).lower()
    if not low:
        return ''
    for key, ru in CITY_ALIASES.items():
        if key in low:
            return ru
    return ''


def load() -> list:
    """Все записи пула."""
    try:
        rows = json.loads(POOL_PATH.read_text(encoding='utf-8'))
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def ready() -> list:
    """Записи, пригодные для документа: название, ИНН, адрес и НЕ Индонезия.

    Порядок — по полноте реквизитов (сначала те, у кого есть и КПП, и ОГРН),
    чтобы в документ чаще попадали организации без пропусков в подвале.
    """
    def score(r):
        return sum(1 for k in ('name', 'legal_name', 'address', 'inn', 'kpp', 'ogrn')
                   if _norm(r.get(k)))

    out = []
    for r in load():
        name = _norm(r.get('legal_name') or r.get('name'))
        if name and _norm(r.get('inn')) and _norm(r.get('address')) and is_foreign(r):
            out.append(r)
    out.sort(key=score, reverse=True)
    return out


def _pick_from(rows: list, key: str) -> dict:
    if not rows:
        return {}
    h = int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    return rows[h % len(rows)]


def pick(app_id=None, client_id=None, city=None, cities=None) -> dict:
    """Организация для заявки/клиента.

    Сначала ищем в городе проживания клиента (клиент из Москвы — организация
    московская). Нет совпадений — берём любую из списка. Выбор детерминирован:
    при повторной сборке организация не меняется.

    city  — одна строка (город или адрес клиента);
    cities — список кандидатов по приоритету (город, регистрация, место рождения):
             берётся первый, из которого удалось распознать город пула.
    """
    rows = ready()
    if not rows:
        return {}
    key = '%s|%s' % (client_id or '', app_id or '')
    want = ''
    for cand in ([city] if city else []) + list(cities or []):
        if not cand or is_indonesian(cand):
            continue          # адрес проживания в Индонезии ориентиром не является
        want = city_in_text(cand)
        if want:
            break
    if want:
        same = [r for r in rows if city_of(r) == want]
        if same:
            return _pick_from(same, key)
    return _pick_from(rows, key)


def normalize_title(title) -> str:
    """Название организации для сравнения: без кавычек, регистра и лишних пробелов."""
    low = _norm(title).lower().replace('«', '"').replace('»', '"')
    low = re.sub(r'[\s"\'`]+', ' ', low).strip()
    return low


def by_title(title) -> dict:
    """Запись пула по названию ('' / мусор → {}). Сравнение терпимо к кавычкам."""
    want = normalize_title(title)
    if not want:
        return {}
    for r in ready():
        if want in (normalize_title(r.get('name')), normalize_title(r.get('legal_name'))):
            return r
    return {}


def by_any(value) -> dict:
    """Найти организацию по любому её реквизиту.

    Переменные организации созависимы: администратор может поправить не только
    название, но и ИНН (или КПП, ОГРН, адрес) — по введённому значению находим
    организацию в пуле и подставляем всю её группу целиком.
    """
    raw = _norm(value)
    if not raw:
        return {}
    digits = re.sub(r'\D', '', raw)
    org = by_title(raw)
    if org:
        return org
    for r in ready():
        if digits and digits in (re.sub(r'\D', '', _norm(r.get('inn'))),
                                 re.sub(r'\D', '', _norm(r.get('kpp'))),
                                 re.sub(r'\D', '', _norm(r.get('ogrn')))):
            return r
        if len(raw) > 12 and normalize_title(raw)[:24] == normalize_title(r.get('address'))[:24]:
            return r
    return {}


def values_of(org: dict) -> dict:
    """Переменные документа из конкретной записи пула (шапка и подвал согласованы)."""
    if not org:
        return {}
    legal = _norm(org.get('legal_name') or org.get('name'))
    name = _norm(org.get('name') or legal)
    return {
        'employer_name': legal,              # название в тексте договора
        'company_name_in_quotes': name,      # название в шапке документа
        'company_registered_address': _norm(org.get('address')),
        'company_inn': _norm(org.get('inn')),
        'company_kpp': _norm(org.get('kpp')),
        'company_ogrn': _norm(org.get('ogrn')),
    }


def values_for(app_id=None, client_id=None, city=None, cities=None) -> dict:
    """Переменные документа из выбранной организации (шапка и подвал согласованы)."""
    return values_of(pick(app_id=app_id, client_id=client_id, city=city, cities=cities))


def titles() -> list:
    """Список организаций для интерфейса: только вне Индонезии, с городом."""
    out = []
    for i, r in enumerate(ready()):
        title = _norm(r.get('name') or r.get('legal_name'))
        if title:
            out.append({'index': i, 'title': title, 'inn': _norm(r.get('inn')),
                        'city': city_of(r)})
    return out
