# services/pools/organizations.py
"""
Фасад над services.org_pool.

Пул организаций (300+ записей): реквизиты работодателей клиентов.
Используется при заполнении договоров и CV.

Реальный код: services.org_pool
Этап 3 рефакторинга: фасад для единой точки входа «from services.pools import X».
"""

from services.org_pool import (  # noqa: F401
    organizations, sectors_map, remote_professions, salaries,
    sector_of_profession, score, valid, pick_for, salary_for,
    term_dates, name_in_documents, for_application,
)

__all__ = [
    "organizations", "sectors_map", "remote_professions", "salaries",
    "sector_of_profession", "score", "valid", "pick_for", "salary_for",
    "term_dates", "name_in_documents", "for_application",
]