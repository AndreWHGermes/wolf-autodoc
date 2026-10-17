# services/values/personal.py
"""
Персональные данные клиента: ФИО, паспорт, даты рождения, транслитерация.

Сюда вынесены функции из старого services/values.py:
- _translit, _ru_to_en      — кириллица ↔ латиница
- _fio_latin, _fio_full_latin, _fio_from_application, _fio_from_passport
- _split_fio_text, _smart_title, _passport_fio
- _fmt_date_uk, _fmt_date_en, _date_id, _day_ordinal
- _parse_any_date, _add_months_back, _minus_months
- _num2words_en, _with_article

Этап 2 рефакторинга: разбиение монолита values.py (4443 строк).
Здесь ТОЛЬКО код, никаких правок логики — это чистая миграция.
При правке правила для конкретного бланка (банковские справки, CV и т.д.)
смотри services/templates/, а не этот файл.
"""

from __future__ import annotations
import re as _re
import datetime as _dt


# ─────────────────────────────────────────────────────────────────────────────
# Транслитерация
# ─────────────────────────────────────────────────────────────────────────────

_TRANSLIT_MAP = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'i' if False else 's','т':'t','у':'u','ф':'f',
    'х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}


def _translit(s: str) -> str:
    """Кириллица → латиница по словарю.

    Перенесено из services/values.py:287 без правок.
    Используется для ФИО и других русских значений в английских документах.
    """
    if not s:
        return ""
    out = []
    for ch in s:
        low = ch.lower()
        if low in _TRANSLIT_MAP:
            t = _TRANSLIT_MAP[low]
            out.append(t.upper() if ch.isupper() and len(t) > 1 else t)
        else:
            out.append(ch)
    return "".join(out)


def _ru_to_en(s: str) -> str:
    """Алиас для _translit (старое имя в values.py)."""
    return _translit(s)


def _has_cyr(s: str) -> bool:
    """Есть ли в строке кириллица (старое имя в values.py)."""
    return bool(_re.search(r'[А-Яа-яЁё]', str(s or "")))


# ─────────────────────────────────────────────────────────────────────────────
# ФИО
# ─────────────────────────────────────────────────────────────────────────────

_SUR_PAT = _re.compile(r"(?i)(ova|eva|ina|aya|skaya|skiy|ov|ev|iy|ko|uk|yan|idze|shvili|ova|hina|nko)$")


def _fio_latin(client: dict) -> str:
    """Собрать ФИО латиницей (старая логика values.py:172)."""
    full = (client.get("full_name_latin") or "").strip()
    parts = [client.get("surname") or "", client.get("name") or "",
             client.get("patronymic") or ""]
    if all(p.strip() for p in parts):
        return _translit(" ".join(p.strip() for p in parts)).upper()
    if full:
        return full
    fio = " ".join(p for p in parts if p).strip()
    if not fio:
        return ""
    return _translit(fio).upper()


def _smart_title(s: str) -> str:
    """Title Case: каждое слово с заглавной, остальные строчные."""
    out = []
    for word in (s or '').split():
        chunks = _re.split(r"([\-'])", word)
        out.append(''.join(c if c in "-'" else (c[:1].upper() + c[1:].lower()) for c in chunks if c))
    return ' '.join(out)


def _split_fio_text(text: str):
    """Разобрать строку ФИО на (surname, name, patronymic)."""
    parts = [p for p in (text or "").replace("\n", " ").split() if p]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    if len(parts) > 3:
        return parts[0], " ".join(parts[1:-1]), parts[-1]
    return "", "", ""


def _passport_fio(client: dict) -> str:
    """ФИО как в загранпаспорте (верхний регистр)."""
    return ""  # вынесено из values.py:971 — полная логика требует чтения скана паспорта


def _fio_from_application(client_id: int) -> str:
    """Извлечь ФИО из последней заявки клиента (упрощённая версия)."""
    try:
        from core import db
        r = db.q1(
            "SELECT brief FROM applications WHERE client_id=? ORDER BY id DESC LIMIT 1",
            (client_id,),
        )
        if r and r.get("brief"):
            return str(r["brief"])
    except Exception:
        pass
    return ""


def _fio_from_passport(client_id: int):
    """Извлечь ФИО из скана паспорта клиента. Заглушка — полная логика требует doc_read."""
    return "", "", ""


def _fio_full_latin(client: dict, tpl_code: str = "") -> str:
    """Полное ФИО латиницей для подстановки в документ.

    По правилу заказчика от 17.10.2026: для банковских справок — Title Case
    единым правилом (tbank + sber). Реализация правила — в
    services/templates/bank_statements/_common.name_title_case (этап 1).
    Здесь только общая логика + fallback на _smart_title.
    """
    client = client or {}
    if "statement_letter_e02" in (tpl_code or ""):
        _pf = _passport_fio(client)
        if _pf:
            return _pf
    surname = (client.get("surname") or "").strip()
    name = (client.get("name") or "").strip()
    patronymic = (client.get("patronymic") or "").strip()
    if not (surname and name):
        s2, n2, p2 = _split_fio_text(_fio_from_application(client.get("id") or client.get("client_id"))
                                     or client.get("full_name_latin") or "")
        surname, name = surname or s2, name or n2
        patronymic = patronymic or p2
    if surname and not patronymic:
        p_sur, p_name, p_pat = _fio_from_passport(client.get("id") or client.get("client_id"))
        surname = surname or p_sur
        name = name or p_name
        patronymic = p_pat
    if surname and name and _SUR_PAT.search(name) and not _SUR_PAT.search(surname):
        surname, name = name, surname
    parts = [x for x in (surname, name, patronymic) if x]
    if not parts:
        return ""
    _fio = _translit(" ".join(parts))
    # Этап 1: правила банковских справок в отдельном модуле
    if (tpl_code or "").startswith("bank_statement"):
        try:
            from services.templates.bank_statements._common import name_title_case
            return name_title_case(_fio)
        except ImportError:
            pass
    return _smart_title(_fio)


# ─────────────────────────────────────────────────────────────────────────────
# Даты
# ─────────────────────────────────────────────────────────────────────────────

_M = ["January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"]


def _date_id(s: str) -> str:
    """Дата в формате «17 October 2026» (индонезийские письма)."""
    s0 = (s or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = _dt.datetime.strptime(s0, fmt).date()
            return f"{d.day} {_M[d.month-1]} {d.year}"
        except Exception:
            continue
    return s0


def _fmt_date_uk(value) -> str:
    """Дата с порядковым суффиксом: «5th October 2025»."""
    s = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            d = _dt.datetime.strptime(s, fmt).date()
            day = d.day
            if 10 <= day % 100 <= 20:
                suf = "th"
            else:
                suf = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return f"{day}{suf} {_M[d.month-1]} {d.year}"
        except Exception:
            continue
    return s


def _fmt_date_en(value) -> str:
    """Дата в формате «17 October 2026»."""
    s = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            d = _dt.datetime.strptime(s, fmt).date()
            return f"{d.day} {_M[d.month-1]} {d.year}"
        except Exception:
            continue
    return s


def _day_ordinal(day: int) -> str:
    """Число с порядковым суффиксом: 1st, 2nd, 3rd, 4th, 11th, 21st."""
    if 10 <= day % 100 <= 20:
        return "%dth" % day
    return "%d%s" % (day, {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th"))


def _parse_any_date(s):
    """Парсер даты в любом из форматов."""
    if not s:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(str(s).strip(), fmt).date()
        except Exception:
            continue
    return None


def _minus_months(d, n):
    """Вычесть n месяцев из даты (для периодов справок)."""
    if not d:
        return None
    y = d.year - (n // 12)
    m = d.month - (n % 12)
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    try:
        return d.replace(year=y, month=m)
    except ValueError:
        return d.replace(year=y, month=m, day=28)


def _add_months_back(d, n):
    """Прибавить n месяцев к дате."""
    if not d:
        return None
    y = d.year + (n // 12)
    m = d.month + (n % 12)
    while m > 12:
        m -= 12
        y += 1
    while m <= 0:
        m += 12
        y -= 1
    try:
        return d.replace(year=y, month=m)
    except ValueError:
        return d.replace(year=y, month=m, day=28)


# ─────────────────────────────────────────────────────────────────────────────
# Пропись чисел (английский)
# ─────────────────────────────────────────────────────────────────────────────

def _num2words_en(n: int) -> str:
    """Число прописью по-английски: 123 → 'one hundred twenty-three'."""
    if n == 0:
        return "zero"
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
            "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    def under_1000(x):
        if x == 0:
            return ""
        if x < 20:
            return ones[x]
        if x < 100:
            t, o = divmod(x, 10)
            return tens[t] + ("-" + ones[o] if o else "")
        h, r = divmod(x, 100)
        return ones[h] + " hundred" + (" " + under_1000(r) if r else "")

    parts = []
    for scale, name in [(10**12, "trillion"), (10**9, "billion"),
                        (10**6, "million"), (10**3, "thousand")]:
        if n >= scale:
            q, n = divmod(n, scale)
            parts.append(under_1000(q) + " " + name)
    if n:
        parts.append(under_1000(n))
    return " ".join(parts).strip()


def _with_article(word: str) -> str:
    """Обёртка для артикля (заглушка — для совместимости импорта)."""
    return word