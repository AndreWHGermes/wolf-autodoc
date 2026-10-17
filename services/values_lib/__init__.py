# services/values/__init__.py
"""
Точка входа values/ — собирает personal, finance, registry и orchestrator.

Старый импорт «from services.values import build_template_values» продолжает
работать через обратную совместимость (services/values.py остаётся обёрткой).
"""

from .orchestrator import build_template_values  # noqa: F401
from .personal import (  # noqa: F401
    _translit, _ru_to_en, _has_cyr,
    _fio_latin, _smart_title, _split_fio_text, _fio_full_latin,
    _date_id, _fmt_date_uk, _fmt_date_en, _day_ordinal,
    _parse_any_date, _minus_months, _add_months_back,
    _num2words_en, _with_article,
)
from .finance import (  # noqa: F401
    BANK_BINS, BANK_BOUNDS, bank_bins, balance_bounds, gen_balance,
    _fmt_money, parse_amount_any, _balance_words_from,
    _cached, _clear_value_cache,
    read_client_bank_amount, bank_amount_for,
    _gen_by_pattern, number_pattern, _no_busy, num_ok,
    gen_doc_no, gen_ref_no, read_client_doc_numbers,
    mask_card, _round_thousand, _to_float,
    _product_of_statement, read_client_card_mask, card_from_client_docs,
)
from .registry import get_passport, list_known, apply_passport_rules  # noqa: F401

__all__ = [
    "build_template_values",
    "get_passport", "list_known", "apply_passport_rules",
]