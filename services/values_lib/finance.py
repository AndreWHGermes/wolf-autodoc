# services/values/finance.py
"""
Финансовые данные: банковские BIN, формат суммы, балансы, пропись.

Перенесено из services/values.py:
- BANK_BINS, bank_bins()
- BANK_BOUNDS, balance_bounds()
- gen_balance()
- _fmt_money(), parse_amount_any()
- _balance_words_from(), _cached(), _clear_value_cache()
- read_client_bank_amount(), bank_amount_for()
- gen_doc_no(), gen_ref_no(), number_pattern(), _no_busy(), _gen_by_pattern()
- num_ok(), read_client_doc_numbers()
- mask_card(), _round_thousand(), _to_float()
- _product_of_statement(), read_client_card_mask(), card_from_client_docs()

Этап 2 рефакторинга: чистая миграция из values.py без правок логики.
"""

from __future__ import annotations
import re as _re


# ─────────────────────────────────────────────────────────────────────────────
# BIN банков (для маски карты)
# ─────────────────────────────────────────────────────────────────────────────

BANK_BINS = {
    'tbank': ['220070', '521324', '437783'],
    'sber':  ['220220', '427638', '427660', '427602', '427616',
              '427629', '427644', '427699', '427901', '427902'],
}


def bank_bins(bank: str) -> list:
    """Список BIN для банка (tbank/sber)."""
    return BANK_BINS.get(bank, [])


# ─────────────────────────────────────────────────────────────────────────────
# Вилка остатков
# ─────────────────────────────────────────────────────────────────────────────

BANK_BOUNDS = {
    'tbank_3m':  (200_000, 7_500_000),
    'tbank_12m': (200_000, 7_500_000),
    'sber_3m':   (200_000, 7_500_000),
    'sber_12m':  (200_000, 7_500_000),
}


def balance_bounds(bank: str, period: str) -> tuple[int, int]:
    """Границы остатка для банка и периода."""
    return BANK_BOUNDS.get(f"{bank}_{period}", (200_000, 7_500_000))


def gen_balance(bank: str, period: str) -> int:
    """Сгенерировать остаток в вилке для банка/периода."""
    import random as _r
    lo, hi = balance_bounds(bank, period)
    return _r.randrange(lo, hi + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Формат суммы (для банковских справок)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_money(value, tpl_code: str = "") -> str:
    """Формат суммы по банку: TBank → «6 277 000, 00», Сбер → «17621.29».

    Этап 1: специализация по банкам вынесена в services/templates/bank_statements/
    Эта функция оставлена как fallback для остальных документов.
    """
    s = str(value or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return ""
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return str(value)
    intpart = int(v)
    cents = int(round((v - intpart) * 100))
    return f"{intpart:,}".replace(",", " ") + f",{cents:02d}"


def parse_amount_any(s: str):
    """Парсер суммы в любом формате → float."""
    if not s:
        return None
    t = str(s).strip().replace("\u00a0", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _round_thousand(n: int) -> int:
    """Округлить до тысяч."""
    return int(round(n / 1000.0)) * 1000


def _to_float(s):
    """Алиас parse_amount_any."""
    return parse_amount_any(s)


def _balance_words_from(amount_rub: int, cents: int) -> str:
    """Пропись остатка: «six million two hundred seventy-seven thousand rubles 00 kopeks»."""
    from .personal import _num2words_en
    rub = _num2words_en(int(amount_rub))
    kop = _num2words_en(int(cents)) if cents else "00"
    return f"{rub} rubles {kop} kopeks"


# ─────────────────────────────────────────────────────────────────────────────
# Кэш значений
# ─────────────────────────────────────────────────────────────────────────────

_VAL_CACHE: dict = {}


def _cached(key: str, fn):
    """Мемоизация: вернуть из кэша или вычислить."""
    if key in _VAL_CACHE:
        return _VAL_CACHE[key]
    v = fn()
    _VAL_CACHE[key] = v
    return v


def _clear_value_cache() -> None:
    """Очистить кэш значений."""
    _VAL_CACHE.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Чтение из документов клиента
# ─────────────────────────────────────────────────────────────────────────────

def read_client_bank_amount(client_id: int) -> int:
    """Прочитать остаток из скана банковской справки клиента (заглушка)."""
    return 0


def bank_amount_for(client_id, tpl_code: str = "") -> str:
    """Подобрать остаток для банка/периода (с учётом вилки)."""
    bank = "tbank"
    period = "3m"
    if "sber" in (tpl_code or ""):
        bank = "sber"
    if "12m" in (tpl_code or ""):
        period = "12m"
    return str(gen_balance(bank, period))


def read_client_card_mask(client_id: int) -> str:
    """Прочитать маску карты из скана (заглушка)."""
    return ""


def card_from_client_docs(client_id: int) -> str:
    """Маска карты из документов клиента (заглушка)."""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Номера документов (Doc No, Ref No)
# ─────────────────────────────────────────────────────────────────────────────

def _gen_by_pattern(seed: str, pattern: str) -> str:
    """Генератор по шаблону: 'lldddddddd' → 'XX00000000'."""
    import hashlib as _hl
    h = _hl.md5(seed.encode("utf-8")).hexdigest()
    out = []
    i = 0
    for ch in pattern:
        if ch == 'l':
            n = int(h[i % len(h)], 16) % 26
            out.append(chr(ord('a') + n))
        elif ch == 'U':
            n = int(h[i % len(h)], 16) % 26
            out.append(chr(ord('A') + n))
        elif ch == 'd':
            n = int(h[i % len(h)], 16) % 10
            out.append(str(n))
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def number_pattern(tpl_code: str, kind: str) -> str:
    """Шаблон номера для шаблона/типа."""
    p = {
        ('bank_statement_3m__tbank',  'doc_no'): 'lldddddddd',
        ('bank_statement_3m__tbank',  'ref_no'): 'UdddddddUUU',
        ('bank_statement_12m__tbank', 'doc_no'): 'lldddddddd',
        ('bank_statement_12m__tbank', 'ref_no'): 'UdddddddUUU',
        ('bank_statement_3m__sber',   'doc_no'): 'dddddddld',
        ('bank_statement_3m__sber',   'ref_no'): 'UdddddddUUU',
    }
    return p.get((tpl_code, kind), 'lldddddddd')


def _no_busy(kind: str, value: str, client_id) -> bool:
    """Проверка, что номер не занят (заглушка — нужна проверка по БД)."""
    return False


def num_ok(value: str, pattern: str, kind: str = "") -> bool:
    """Валиден ли номер по шаблону."""
    if not value or not pattern:
        return False
    if len(value) != len(pattern):
        return False
    for v, p in zip(value, pattern):
        if p == 'd' and not v.isdigit():
            return False
        if p in ('l', 'U') and not v.isalpha():
            return False
    return True


def gen_doc_no(client_name: str, doc_date: str, salt: str = "", pattern: str = None) -> str:
    """Сгенерировать Doc No."""
    return _gen_by_pattern(f'doc|{client_name}|{doc_date}|{salt}',
                           pattern or ('l' + 'l' + 'd' * 8))


def gen_ref_no(client_name: str, doc_date: str, salt: str = "", pattern: str = None) -> str:
    """Сгенерировать Ref No."""
    return _gen_by_pattern(f'ref|{client_name}|{doc_date}|{salt}',
                           pattern or ('U' + 'd' * 8 + 'U' * 3))


def read_client_doc_numbers(client_id: int):
    """Прочитать реальные номера Doc/Ref из скана (заглушка)."""
    return "", ""


def _product_of_statement(tpl_code: str) -> str:
    """Продукт по коду шаблона."""
    if "tbank" in (tpl_code or ""):
        return "tbank"
    if "sber" in (tpl_code or ""):
        return "sber"
    return ""


def mask_card(card: str) -> str:
    """Маска карты: 521324******6363."""
    s = str(card or "").strip()
    if len(s) < 10:
        return s
    return s[:6] + "*" * (len(s) - 10) + s[-4:]