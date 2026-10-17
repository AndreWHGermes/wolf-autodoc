# services/pools/addresses.py
"""Фасад над services.address_pool (пул российских адресов)."""

from services.address_pool import (  # noqa: F401
    _city_entry, detect_city, generate_address,
)

__all__ = ["_city_entry", "detect_city", "generate_address"]