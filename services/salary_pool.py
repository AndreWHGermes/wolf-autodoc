"""Пул сумм вознаграждения для договоров (Remote Work Agreement, док. №11).

Источник — архивные подлинники договоров клиентов (data/gdrive_examples):
в 50 из 54 разобранных договоров сумма за месяц равна годовой / 12, поэтому
пара (годовая, месячная) всегда берётся из одной записи пула.

Правило заказчика: сумма не выдумывается «от себя» — используется только то,
что уже встречалось в поданных договорах, то есть в пределах архивного
диапазона. Если в карточке клиента указана своя сумма, она имеет приоритет
(её обрабатывает services/values.py до обращения к пулу).

Файл пула: data/salary_pool.json
Запись: {annual, monthly, count, source}
"""
from __future__ import annotations

import hashlib
from pathlib import Path
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
    return (min(r['annual'] for r in rows), max(r['annual'] for r in rows),
            min(r['monthly'] for r in rows), max(r['monthly'] for r in rows))


def in_range(annual) -> bool:
    """Сумма внутри архивного диапазона (ниже/выше архива не подставляем)."""
    lo, hi, _, _ = limits()
    try:
        return lo <= int(annual) <= hi
    except Exception:
        return False


def pick(app_id=None, client_id=None) -> dict:
    """Пара сумм для заявки/клиента: одна и та же при каждой сборке."""
    # Клиент важнее заявки: если пришёл только app_id — достаём клиента,
    # иначе оклад считается по другому ключу и документы расходятся (560 vs 525).
    if not client_id and app_id:
        try:
            import sqlite3 as _sq
            _c = _sq.connect(str(Path(__file__).resolve().parent.parent / 'data' / 'wolf.db'), timeout=15)
            _r = _c.execute("SELECT client_id FROM applications WHERE id=?", (int(app_id),)).fetchone()
            _c.close()
            client_id = _r[0] if _r else None
        except Exception:
            client_id = None
    # Легенда клиента — источник истины: если в ней уже записан оклад,
    # его и берём, чтобы документы и легенда не расходились.
    try:
        import json as _json
        _lp = Path(__file__).resolve().parent.parent / 'data' / 'legends' / ('client_%s.json' % client_id)
        if client_id and _lp.exists():
            _lg = _json.loads(_lp.read_text(encoding='utf-8'))
            for _src in (_lg.get('finance') or {}, _lg):
                _mo = _src.get('salary_rub') or _src.get('salary') or _src.get('monthly_salary')
                _yr = _src.get('annual_income') or _src.get('annual_salary') or _src.get('income')
                if _mo:
                    _mo = int(str(_mo).replace(' ', '').split(',')[0] or 0)
                    _yr = int(str(_yr).replace(' ', '').split(',')[0]) if _yr else _mo * 12
                    if _mo:
                        return {'annual': _yr or _mo * 12, 'monthly': _mo, 'source': 'легенда клиента'}
    except Exception:
        pass
    rows = load()
    if not rows:
        return {}
    # Оклад — свойство КЛИЕНТА, а не заявки: ключ только по client_id.
    # Иначе договор и контракт одной заявки получали разные суммы (535 vs 555).
    key = str(client_id or app_id or '')
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
        return {'annual': int(r['annual']), 'monthly': int(r['monthly']), 'source': 'архив'}
    lo, hi = 415_000, 640_000                 # месячные в архивном диапазоне
    steps = (hi - lo) // 1000                 # шаг ровно 1 000 ₽
    monthly = lo + 1000 * ((h // 7) % (steps + 1))
    return {'annual': monthly * 12, 'monthly': monthly, 'source': 'сгенерировано'}


def words_en(n: int) -> str:
    """Число прописью на английском с заглавных букв (как в поданных договорах)."""
    from services.values import _num2words_en
    return _num2words_en(int(n)).title().replace(' And ', ' and ')


def values_for(app_id=None, client_id=None) -> dict:
    """Переменные сумм для документа: годовая и месячная (цифрами и прописью).

    Прописью считается из тех же чисел, что и цифрами — они не могут разойтись.
    """
    row = gen(app_id=app_id, client_id=client_id)
    if not row:
        return {}
    annual, monthly = int(row['annual']), int(row['monthly'])
    return {
        'annual_amount_numeric': f'{annual:,}',
        'monthly_amount_numeric': f'{monthly:,}',
        'annual_amount_words': words_en(annual),
        'monthly_amount_words': words_en(monthly),
        'amount_per_year': f'{annual:,}',
        'amount_per_month': f'{monthly:,}',
    }
