# services/pools/__init__.py
"""
Пулы значений — единая точка входа для организаций, зарплат, адресов, вузов, профессий.

Здесь собираются фасады над существующими модулями:
- services/pools/organizations.py — реэкспорт services.org_pool
- services/pools/salaries.py     — реэкспорт services.salary_pool
- services/pools/employers.py    — реэкспорт services.employer_pool
- services/pools/addresses.py    — реэкспорт services.address_pool
- services/pools/universities.py  — реэкспорт services.pool_uni
- services/pools/selector.py     — реэкспорт services.pool_assign (выбор по клиенту)
- services/pools/builder.py      — реэкспорт services.pool_builder

Принцип:
- Это ТОНКИЕ фасады, не дублирование кода. Реальные данные и логика — в
  services/{org_pool,salary_pool,...}.py (уже существуют и работают).
- Зачем фасады: новый код импортирует «from services.pools import X» и получает
  все пулы из одного места. Старый код «from services.org_pool import X»
  продолжает работать.
- Пул выбирается по клиенту через services.pools.selector — единая точка.
"""

from .organizations import *  # noqa: F401, F403
from .salaries import *       # noqa: F401, F403
from .employers import *      # noqa: F401, F403
from .addresses import *      # noqa: F401, F403
from .universities import *   # noqa: F401, F403
from .selector import *       # noqa: F401, F403
from .builder import *        # noqa: F401, F403