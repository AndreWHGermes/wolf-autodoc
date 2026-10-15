#!/usr/bin/env python3
"""Заполнить application_documents.pdf_path по уже собранным файлам.

Зачем: путь к готовому PDF не записывался у части записей, а три проверки (визуальная,
логическая, смысловая) читают документы именно по этому пути. Для новых сборок причина
устранена в services/autofill.py; здесь путь восстанавливается для старых записей.

Подбор файла идёт ТОЙ ЖЕ строгой функцией, что и у читателя
(services.reader_agent._find_pdf): совпасть должно каждое значимое слово ФИО и
определение банка/офиса из кода. Частичные совпадения запрещены — иначе документ
одного клиента приписывается другому.

Статусы не меняются. По умолчанию сухой прогон, запись только с --apply.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))

DB = ROOT / 'data' / 'wolf.db'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    from services import reader_agent as RA

    con = sqlite3.connect(str(DB), timeout=60)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        """SELECT ad.id, ad.application_id, ad.status, t.code,
                  cl.full_name_latin AS fio_lat, cl.surname, cl.name
             FROM application_documents ad
             JOIN templates t ON t.id = ad.template_id
             LEFT JOIN applications a ON a.id = ad.application_id
             LEFT JOIN clients cl ON cl.id = a.client_id
            WHERE IFNULL(ad.pdf_path, '') = ''
            ORDER BY ad.application_id DESC""")]

    print('записей без пути: %d' % len(rows))
    found = missing = 0
    for r in rows:
        fio = str(r.get('fio_lat') or ('%s %s' % (r.get('surname') or '', r.get('name') or ''))).strip()
        path = RA._find_pdf(r['code'], fio)
        if path:
            found += 1
            if args.apply:
                con.execute("UPDATE application_documents SET pdf_path=? WHERE id=?", (path, r['id']))
            print('   #%-4s %-34s → %s' % (r['application_id'], r['code'], path.split('/')[-1][:56]))
        else:
            missing += 1
    if args.apply:
        con.commit()
        print('записано путей: %d | осталось без файла: %d' % (found, missing))
    else:
        print('сухой прогон: нашлось бы %d, не найдено %d (запись только с --apply)' % (found, missing))
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
