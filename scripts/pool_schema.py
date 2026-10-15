"""Схема пула значений клиента и меток прочитанных документов.

Идея (Андрей): сначала собрать ВСЁ, что есть по клиенту на Google Диске,
в один пул — независимо от продукта и от того, что нам сейчас нужно.
Затем из этого пула брать значения под нужные документы.

Две таблицы:
  client_documents   — документы клиента и метки: что прочитано, когда, чем,
                       изменился ли файл (по отпечатку). Новое читаем, старое не трогаем.
  client_values_pool — значения: переменная, значение, файл-источник, блок
                       документа, цитата, метод получения, подтверждено ли.

Запуск: python3 scripts/pool_schema.py [--apply]
"""
import sqlite3
import sys
from pathlib import Path

DB = Path('/opt/wolf_v2/data/wolf.db')

DOC_EXTRA = [
    ("doc_kind", "TEXT"),            # тип документа: паспорт, виза, справка банка…
    ("blocks_json", "TEXT"),         # найденные смысловые блоки
    ("text_hash", "TEXT"),           # отпечаток текста: менять ли метку при повторном чтении
    ("text_len", "INTEGER DEFAULT 0"),
    ("read_at", "TEXT"),             # когда прочитан полностью
    ("state", "TEXT DEFAULT 'new'"),  # new | read | parsed | empty | error
    ("method", "TEXT"),              # rule | llm | rule+llm
    ("note", "TEXT"),
]

POOL_DDL = """
CREATE TABLE IF NOT EXISTS client_values_pool (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id      INTEGER NOT NULL,
    application_id INTEGER,
    variable_name  TEXT NOT NULL,
    value          TEXT,
    doc_kind       TEXT,
    source_file    TEXT,
    source_block   TEXT,
    quote          TEXT,
    person         TEXT,                       -- main | spouse | child | other
    person_name    TEXT,                       -- чьё это значение по документу
    method         TEXT,                       -- rule | llm | rule+llm
    confidence     TEXT,                       -- high | medium | check
    use_count      INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(client_id, variable_name, source_file)
)
"""

POOL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pool_client ON client_values_pool(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_pool_app ON client_values_pool(application_id)",
    "CREATE INDEX IF NOT EXISTS idx_pool_var ON client_values_pool(variable_name)",
    "CREATE INDEX IF NOT EXISTS idx_pool_state ON client_documents(state)",
    "CREATE INDEX IF NOT EXISTS idx_pool_doc_client ON client_documents(client_id, state)",
]


def main() -> None:
    apply = '--apply' in sys.argv
    conn = sqlite3.connect(str(DB), timeout=60, isolation_level=None)
    cols = [r[1] for r in conn.execute('PRAGMA table_info("client_documents")')]

    add = [(c, d) for c, d in DOC_EXTRA if c not in cols]
    print('client_documents — новых полей: %d (%s)' % (len(add), ', '.join(c for c, _ in add) or 'нет'))
    if apply:
        for col, ddl in add:
            conn.execute('ALTER TABLE client_documents ADD COLUMN %s %s' % (col, ddl))
        conn.execute(POOL_DDL)
        # таблица пула могла быть создана раньше — досыпаем недостающие поля
        pool_cols = [r[1] for r in conn.execute('PRAGMA table_info("client_values_pool")')]
        for col, ddl in (("person", "TEXT"), ("person_name", "TEXT")):
            if col not in pool_cols:
                conn.execute('ALTER TABLE client_values_pool ADD COLUMN %s %s' % (col, ddl))
                print('в пул добавлено поле:', col)
        for ix in POOL_INDEXES:
            conn.execute(ix)
        print('таблица client_values_pool готова')
        print('индексы:', len(POOL_INDEXES))

    print('\nпроверка схемы:')
    for t in ('client_documents', 'client_values_pool'):
        cols2 = [r[1] for r in conn.execute('PRAGMA table_info("%s")' % t)]
        n = conn.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        print('   %-20s полей %d, записей %d' % (t, len(cols2), n))
    if not apply:
        print('\nэто примерка: запусти с --apply')


if __name__ == '__main__':
    main()
