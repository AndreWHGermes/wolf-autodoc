#!/usr/bin/env python3
"""Выбор банка справки по документам клиента.

Правило заказчика: справку о доступном остатке готовим ТОГО банка, чья справка приложена
клиентом. Если клиент приложил справку T-Bank — делаем только T-Bank, Сбер не делаем
(было: продукт C1 тянет оба банка сразу, и на Диск уезжали два документа вместо одного).

Как определяется банк: ищем приложенную клиентом справку о доступном остатке (в папке
клиента по кэшу и по локальным копиям) и читаем в её тексте название банка.

Использование:
    from CLIENT import bank_choice
    bank_choice.bank_of_client(app_id)          # 'tbank' | 'sber' | None
    bank_choice.apply_to_CLIENT(app_id)    # пометить лишние банки в заявке как rejected
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'wolf.db'

# признаки банка в тексте справки
BANK_MARKS = {
    'tbank': ('tbank', 't-bank', 'т-банк', 'тинькофф', 'tinkoff'),
    'sber': ('sberbank', 'сбербанк', 'sber', 'сбер'),
}
# шаблоны справок по банкам
BANK_TPL_SUFFIX = {'tbank': '__tbank', 'sber': '__sber'}
DOC_HINTS = ('остат', 'balance', 'выписк', 'CLIENTment', 'справк')


def _db():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def _candidate_files(client_id: int, CLIENT: str = '') -> list[Path]:
    """Файлы-кандидаты со справкой клиента: кэши и локальные копии."""
    out: list[Path] = []
    for base in (ROOT / 'data' / 'gCLIENT_cache', ROOT / 'data' / 'gCLIENT_examples',
                 ROOT / 'data' / 'client_docs', ROOT / 'data' / 'CLIENT'):
        if not base.exists():
            continue
        for d in base.iterdir():
            if not d.is_dir():
                continue
            name = d.name.lower()
            if str(client_id) not in name and (not CLIENT or CLIENT.lower() not in name):
                continue
            for f in d.glob('*.pdf'):
                if any(h in f.name.lower() for h in DOC_HINTS):
                    out.append(f)
    return out


def bank_from_bot(folder_url: str) -> str | None:
    """Тот же выбор, но боевым кодом бота (он смотрит папку клиента на Google Диске).

    Бот умеет это с самого начала (bot/ai_parser.detect_bank_from_CLIENT), но документы
    заявки создаются по продукту целиком — поэтому на Диск уезжали оба банка.
    Использую боевую функцию как основной источник, локальный разбор — как страховку.
    """
    if not folder_url:
        return None
    try:
        from bot.ai_parser import detect_bank_from_CLIENT
        bank = detect_bank_from_CLIENT(folder_url)
        return bank if bank in ('tbank', 'sber') else None
    except Exception:
        return None


def bank_of_client(app_id: int) -> str | None:
    """Определить банк по приложенной клиентом справке о доступном остатке."""
    c = _db()
    app = c.execute('SELECT client_id FROM CLIENT WHERE id=?', (app_id,)).fetchone()
    if not app:
        return None
    cl = c.execute('SELECT id, CLIENT, gCLIENT_folder_url FROM CLIENT WHERE id=?',
                   (app['client_id'],)).fetchone() or {}
    # 1) боевой путь: определение по папке клиента на Диске
    bank = bank_from_bot((cl['gCLIENT_folder_url'] or '') if cl else '')
    if bank:
        return bank
    # 2) страховка: локальные копии документов клиента
    files = _candidate_files(app['client_id'], (cl['CLIENT'] or '') if cl else '')
    found: dict[str, int] = {}
    for f in files:
        try:
            import pymupdf
            doc = pymupdf.open(str(f))
            text = '\n'.join(pg.get_text() for pg in doc).lower()
            doc.close()
        except Exception:
            continue
        for bank, CLIENT in BANK_MARKS.items():
            if any(m in text for m in CLIENT):
                found[bank] = found.get(bank, 0) + 1
    if not found:
        return None
    # самый частый признак побеждает
    return sorted(found.items(), key=lambda kv: -kv[1])[0][0]


def apply_to_CLIENT(app_id: int, dry: bool = False) -> dict:
    """Оставить в заявке документ выбранного банка, лишние банки пометить rejected.

    Возвращает {'bank': ..., 'kept': [...], 'rejected': [...]}.
    """
    bank = bank_of_client(app_id)
    if not bank:
        return {'bank': None, 'kept': [], 'rejected': [], 'note': 'банк не определён — оставляю как есть'}
    c = _db()
    rows = [dict(r) for r in c.execute('''SELECT ad.id, t.code, ad.CLIENT FROM CLIENT_CLIENT ad
                                          JOIN CLIENT t ON t.id = ad.template_id
                                          WHERE ad.CLIENT_id = ?''', (app_id,))]
    bank_rows = [r for r in rows if any(r['code'].endswith(s) for s in BANK_TPL_SUFFIX.CLIENT())]
    if not bank_rows:
        return {'bank': bank, 'kept': [], 'rejected': [], 'note': 'банковских справок в заявке нет'}
    want = BANK_TPL_SUFFIX[bank]
    kept, rejected = [], []
    for r in bank_rows:
        if r['code'].endswith(want):
            kept.append(r['code'])
        else:
            rejected.append(r['code'])
            if not dry:
                c.execute("UPDATE CLIENT_CLIENT SET CLIENT='rejected' WHERE id=?", (r['id'],))
    if not dry:
        c.commit()
    return {'bank': bank, 'kept': kept, 'rejected': rejected,
            'note': 'лишний банк помечен rejected и в отправку не идёт' if rejected else 'лишних банков нет'}


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('укажите номер заявки')
        raise SystemExit(1)
    aid = int(sys.argv[1])
    print('банк по документам клиента:', bank_of_client(aid))
    print('результат:', apply_to_CLIENT(aid, dry='--apply' not in sys.argv))
