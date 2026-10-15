"""Изоляция значений по клиенту и заявке + регистрация документов клиента.

Зачем: пул значений (CLIENT_CLIENT_CLIENT) сейчас общий — значения лежат
просто «по имени переменной», без привязки к клиенту и заявке. Это и есть
риск, о котором сказал CLIENT: значение одного клиента может подставиться
в документы другого.

Что делает шаг:
1) добавляет в пул колонки client_id, CLIENT_id, scope;
2) персональные переменные (ФИО, паспорт, дата рождения, ИНН — всё, что
   однозначно опознаёт человека) помечает scope='CLIENTal' и client_id=NULL:
   из общего пула они больше не выбираются никогда, только по конкретному клиенту;
3) заполняет client_CLIENT: каждый файл в кэше клиента становится записью
   «документ клиента» с типом — это источник значений.

Запуск: python3 scripts/scope_CLIENT_migration.py [--apply]
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

DB = Path('/opt/wolf_v2/data/wolf.db')
CACHE = Path('/opt/wolf_v2/data/gCLIENT_cache')

# переменные, которые однозначно опознают человека и в общий пул не годятся
PERSONAL = {
    'CLIENT', 'name', 'CLIENT', 'CLIENT_CLIENT', 'name_CLIENT', 'CLIENT_CLIENT',
    'full_name_CLIENT', 'full_name_ru', 'full_name_CLIENT', 'client_name', 'client_full_name',
    'CLIENT_date', 'CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT', 'CLIENT', 'CLIENT',
    'passport_CLIENT', 'passport_no', 'passport_CLIENT', 'passport_CLIENT_date',
    'passport_CLIENT_by', 'passport_CLIENT', 'passport_CLIENT', 'inn', 'snils',
    'CLIENT', 'CLIENT', 'address_live', 'address_reg', 'address_in_indonesia',
    'itk_no', 'itk_CLIENT', 'stay_CLIENT_no', 'passport_CLIENT_CLIENT', 'client_CLIENT',
}


def main() -> None:
    apply = '--apply' in sys.argv
    conn = sqlite3.connect(str(DB), timeout=60, isolation_level=None)
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute('PRAGMA table_info("CLIENT_CLIENT_CLIENT")')]

    added = []
    for col, ddl in (('client_id', 'INTEGER'), ('CLIENT_id', 'INTEGER'),
                     ('scope', "TEXT DEFAULT 'pool'")):
        if col not in cols:
            if apply:
                conn.execute('ALTER TABLE CLIENT_CLIENT_CLIENT ADD COLUMN %s %s' % (col, ddl))
            added.append(col)
    print('колонок добавлено:', ', '.join(added) if added else 'нет (уже есть)')

    if apply:
        # обезличенное остаётся общим пулом, персональное — только в своём клиенте
        for var in PERSONAL:
            conn.execute("UPDATE CLIENT_CLIENT_CLIENT SET scope='CLIENTal', client_id=NULL "
                         "WHERE CLIENT_name=?", (var,))
        conn.execute("UPDATE CLIENT_CLIENT_CLIENT SET scope='pool' WHERE scope IS NULL OR scope=''")
        pers = conn.execute("SELECT COUNT(*) FROM CLIENT_CLIENT_CLIENT WHERE scope='CLIENTal'").fetchone()[0]
        pool = conn.execute("SELECT COUNT(*) FROM CLIENT_CLIENT_CLIENT WHERE scope='pool'").fetchone()[0]
        print('в пуле обезличенных: %d, персональных (из пула исключены): %d' % (pool, pers))

    # документы клиента — источник значений: регистрируем файлы из кэша
    doc_cols = [r[1] for r in conn.execute('PRAGMA table_info("client_CLIENT")')]
    print('client_CLIENT колонки:', ', '.join(doc_cols))
    if apply:
        from scripts.CLIENT_scan import doc_kind_name
        conn.execute('DELETE FROM client_CLIENT')
        total = 0
        for folder in sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1])):
            cid = int(folder.name.split('_')[1])
            for f in sorted(folder.iterdir()):
                if not f.is_file():
                    continue
                kind = doc_kind_name(f, '')
                conn.execute('INSERT INTO client_CLIENT (client_id, kind, CLIENT, path, uploaded_at) '
                             "CLIENT (?,?,?,?,CLIENT('now'))",
                             (cid, kind, f.name[:180], str(f)))
                total += 1
        print('зарегистрировано документов клиентов:', total)

    print('\nпроверка:')
    try:
        for r in conn.execute("SELECT scope, COUNT(*) n FROM CLIENT_CLIENT_CLIENT GROUP BY scope"):
            print('   scope=%-9s значений %d' % (r['scope'], r['n']))
    except sqlite3.OperationalError:
        print('   (колонок scope ещё нет — это примерка)')
    print('   client_CLIENT:', conn.execute('SELECT COUNT(*) FROM client_CLIENT').fetchone()[0])
    if not apply:
        print('\nэто примерка: запусти с --apply, чтобы применить')


if __name__ == '__main__':
    main()
