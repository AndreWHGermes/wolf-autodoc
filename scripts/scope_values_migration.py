"""Изоляция значений по клиенту и заявке + регистрация документов клиента.

Зачем: пул значений (variable_value_history) сейчас общий — значения лежат
просто «по имени переменной», без привязки к клиенту и заявке. Это и есть
риск, о котором сказал Андрей: значение одного клиента может подставиться
в документы другого.

Что делает шаг:
1) добавляет в пул колонки client_id, application_id, scope;
2) персональные переменные (ФИО, паспорт, дата рождения, ИНН — всё, что
   однозначно опознаёт человека) помечает scope='personal' и client_id=NULL:
   из общего пула они больше не выбираются никогда, только по конкретному клиенту;
3) заполняет client_documents: каждый файл в кэше клиента становится записью
   «документ клиента» с типом — это источник значений.

Запуск: python3 scripts/scope_values_migration.py [--apply]
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

DB = Path('/opt/wolf_v2/data/wolf.db')
CACHE = Path('/opt/wolf_v2/data/gdrive_cache')

# переменные, которые однозначно опознают человека и в общий пул не годятся
PERSONAL = {
    'surname', 'name', 'patronymic', 'surname_latin', 'name_latin', 'patronymic_latin',
    'full_name_latin', 'full_name_ru', 'full_name_title', 'client_name', 'client_full_name',
    'birth_date', 'birth_place', 'place_birth_inline', 'citizenship', 'nationality',
    'passport_number', 'passport_no', 'passport_series', 'passport_issue_date',
    'passport_issued_by', 'passport_expiry', 'passport_authority', 'inn', 'snils',
    'phone', 'email', 'address_live', 'address_reg', 'address_in_indonesia',
    'itk_no', 'itk_expiry', 'stay_permit_no', 'passport_valid_until', 'client_gender',
}


def main() -> None:
    apply = '--apply' in sys.argv
    conn = sqlite3.connect(str(DB), timeout=60, isolation_level=None)
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute('PRAGMA table_info("variable_value_history")')]

    added = []
    for col, ddl in (('client_id', 'INTEGER'), ('application_id', 'INTEGER'),
                     ('scope', "TEXT DEFAULT 'pool'")):
        if col not in cols:
            if apply:
                conn.execute('ALTER TABLE variable_value_history ADD COLUMN %s %s' % (col, ddl))
            added.append(col)
    print('колонок добавлено:', ', '.join(added) if added else 'нет (уже есть)')

    if apply:
        # обезличенное остаётся общим пулом, персональное — только в своём клиенте
        for var in PERSONAL:
            conn.execute("UPDATE variable_value_history SET scope='personal', client_id=NULL "
                         "WHERE variable_name=?", (var,))
        conn.execute("UPDATE variable_value_history SET scope='pool' WHERE scope IS NULL OR scope=''")
        pers = conn.execute("SELECT COUNT(*) FROM variable_value_history WHERE scope='personal'").fetchone()[0]
        pool = conn.execute("SELECT COUNT(*) FROM variable_value_history WHERE scope='pool'").fetchone()[0]
        print('в пуле обезличенных: %d, персональных (из пула исключены): %d' % (pool, pers))

    # документы клиента — источник значений: регистрируем файлы из кэша
    doc_cols = [r[1] for r in conn.execute('PRAGMA table_info("client_documents")')]
    print('client_documents колонки:', ', '.join(doc_cols))
    if apply:
        from scripts.drive_scan import doc_kind_name
        conn.execute('DELETE FROM client_documents')
        total = 0
        for folder in sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1])):
            cid = int(folder.name.split('_')[1])
            for f in sorted(folder.iterdir()):
                if not f.is_file():
                    continue
                kind = doc_kind_name(f, '')
                conn.execute('INSERT INTO client_documents (client_id, kind, title, path, uploaded_at) '
                             "VALUES (?,?,?,?,datetime('now'))",
                             (cid, kind, f.name[:180], str(f)))
                total += 1
        print('зарегистрировано документов клиентов:', total)

    print('\nпроверка:')
    try:
        for r in conn.execute("SELECT scope, COUNT(*) n FROM variable_value_history GROUP BY scope"):
            print('   scope=%-9s значений %d' % (r['scope'], r['n']))
    except sqlite3.OperationalError:
        print('   (колонок scope ещё нет — это примерка)')
    print('   client_documents:', conn.execute('SELECT COUNT(*) FROM client_documents').fetchone()[0])
    if not apply:
        print('\nэто примерка: запусти с --apply, чтобы применить')


if __name__ == '__main__':
    main()
