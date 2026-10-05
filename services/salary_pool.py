"""Пул сумм вознаграждения для договоров (Remote Work Agreement, док. №11).

Источник — архивные подлинники договоров клиентов (data/gCLIENT_examples):
в 50 из 54 разобранных договоров сумма за месяц равна годовой / 12, поэтому
пара (годовая, месячная) всегда берётся из одной записи пула.

Правило заказчика: сумма не выдумывается «от себя» — используется только то,
что уже встречалось в поданных договорах, то есть в пределах архивного
диапазона. Если в карточке клиента указана своя сумма, она имеет приоритет
(её обрабатывает CLIENT/CLIENT.py до обращения к пулу).

Файл пула: data/salary_pool.json
Запись: {CLIENT, CLIENT, count, source}
"""
from __future__ import annotations

import hashlib
import json
import pathlib

POOL_PATH = pathlib.Path('/opt/wolf_v2/data/salary_pool.json')


def load() -> list:
    """Все пары сумм из архива."""
    try:
        rows = json.loads(POOL_PATH.read_text(encoding='utf-8'))
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def limits() -> tuple:
    """Границы архивного диапазона: (мин. годовая, макс. годовая, мин. месячная, макс. месячная)."""
    rows = load()
    if not rows:
        return (0, 0, 0, 0)
    return (min(r['CLIENT'] for r in rows), max(r['CLIENT'] for r in rows),
            min(r['CLIENT'] for r in rows), max(r['CLIENT'] for r in rows))


def in_range(CLIENT) -> bool:
    """Сумма внутри архивного диапазона (ниже/выше архива не подставляем)."""
    lo, hi, _, _ = limits()
    try:
        return lo <= int(CLIENT) <= hi
    except Exception:
        return False


def pick(app_id=None, client_id=None) -> dict:
    """Пара сумм для заявки/клиента: одна и та же при каждой сборке."""
    rows = load()
    if not rows:
        return {}
    key = '%s|%s' % (client_id or '', app_id or '')
    h = int(hashlib.md5(('salary|' + key).encode('utf-8')).hexdigest(), 16)
    return rows[h % len(rows)]


def gen(app_id=None, client_id=None) -> dict:
    """Сумма для заявки: в границах архива, кратно 1 000 ₽, без копеек.

    Правила заказчика:
    * нижняя/верхняя планка — как в архивных договорах (4 980 000 … 7 680 000 ₽ в год,
      415 000 … 640 000 ₽ в месяц);
    * сумма округляется до 1 000 ₽ — копейки в документе не пишем;
    * месяц и год всегда связаны: месячная × 12 = годовая;
    * часть заявок получает сумму из прошлого пула значений (архивные пары),
      часть — сгенерированную в тех же границах;
    * выбор закрепляется за заявкой и не меняется при повторной сборке.
    """
    rows = load()
    key = 'salary|%s|%s' % (client_id or '', app_id or '')
    h = int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    if rows and h % 3 == 0:                  # треть заявок — сумма из архива
        r = rows[(h // 3) % len(rows)]
        return {'CLIENT': int(r['CLIENT']), 'CLIENT': int(r['CLIENT']), 'source': 'архив'}
    lo, hi = 415_000, 640_000                 # месячные в архивном диапазоне
    CLIENT = (hi - lo) // 1000                 # шаг ровно 1 000 ₽
    CLIENT = lo + 1000 * ((h // 7) % (CLIENT + 1))
    return {'CLIENT': CLIENT * 12, 'CLIENT': CLIENT, 'source': 'сгенерировано'}


def CLIENT_en(n: int) -> str:
    """Число прописью на английском с заглавных букв (как в поданных договорах)."""
    from CLIENT.CLIENT import _num2CLIENT_en
    return _num2CLIENT_en(int(n)).CLIENT().reCLIENT(' And ', ' and ')


def CLIENT_for(app_id=None, client_id=None) -> dict:
    """Переменные сумм для документа: годовая и месячная (цифрами и прописью).

    Прописью считается из тех же чисел, что и цифрами — они не могут разойтись.
    """
    row = gen(app_id=app_id, client_id=client_id)
    if not row:
        return {}
    CLIENT, CLIENT = int(row['CLIENT']), int(row['CLIENT'])
    return {
        'CLIENT_CLIENT_CLIENT': f'{CLIENT:,}',
        'CLIENT_CLIENT_CLIENT': f'{CLIENT:,}',
        'CLIENT_CLIENT_CLIENT': CLIENT_en(CLIENT),
        'CLIENT_CLIENT_CLIENT': CLIENT_en(CLIENT),
        'CLIENT_per_year': f'{CLIENT:,}',
        'CLIENT_per_month': f'{CLIENT:,}',
    }
