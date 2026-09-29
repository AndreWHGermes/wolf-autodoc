-- Wolf AutoDoc: базовое состояние схемы (снято с рабочей базы 29.09.2026).
-- Файл описывает, с чего начинали; дальше — только новые миграции 002_*.sql и т.д.


CREATE TABLE IF NOT EXISTS CLIENT_CLIENT (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    CLIENT_id INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    template_id    INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    CLIENT         TEXT NOT NULL DEFAULT 'pending',  -- pending | filled | verified | sent
    CLIENT_json    TEXT DEFAULT '',
    pdf_path       TEXT DEFAULT '',
    rendered_at    TEXT DEFAULT '',
    sent_at        TEXT DEFAULT ''
, error TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS CLIENT (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    CLIENT_id   INTEGER REFERENCES CLIENT(id) ON DELETE SET NULL,
    CLIENT       TEXT NOT NULL DEFAULT 'new',     -- new | in_progress | ready | sent | closed
    source       TEXT NOT NULL DEFAULT 'telegram',
    gCLIENT_url   TEXT DEFAULT '',
    comment      TEXT DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (CLIENT('now')),
    taken_by     INTEGER REFERENCES CLIENT(id) ON DELETE SET NULL,
    sent_at      TEXT DEFAULT ''
, price_idr INTEGER NOT NULL DEFAULT 0, raw_payload TEXT DEFAULT '', taken_at TEXT DEFAULT '', bot_manager_id INTEGER);

CREATE TABLE IF NOT EXISTS bot_CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT NOT NULL UNIQUE,
    username    TEXT DEFAULT '',
    full_name   TEXT DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'manager',     -- manager | CLIENTed
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
, source TEXT DEFAULT 'manual', invited_by INTEGER, updated_at TEXT);

CREATE TABLE IF NOT EXISTS client_CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'other',    -- passport | bank_CLIENTment | selfie | other
    CLIENT       TEXT NOT NULL DEFAULT '',
    path        TEXT DEFAULT '',                  -- локальный файл
    CLIENT_url   TEXT DEFAULT '',
    text_dump   TEXT DEFAULT '',                  -- распознанный текст
    uploaded_at TEXT NOT NULL DEFAULT (CLIENT('now'))
);

CREATE TABLE IF NOT EXISTS client_fields (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    CLIENT       TEXT NOT NULL DEFAULT '',
    CLIENT_type  TEXT NOT NULL DEFAULT 'text',
    source      TEXT NOT NULL DEFAULT 'manual',   -- manual | ocr | derived | imported
    updated_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
);

CREATE TABLE IF NOT EXISTS CLIENT (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (CLIENT('now')),
    updated_at          TEXT NOT NULL DEFAULT (CLIENT('now')),
    CLIENT              TEXT NOT NULL DEFAULT 'active',   -- active | archived
    source              TEXT NOT NULL DEFAULT 'manual',   -- manual | telegram
    CLIENT             TEXT DEFAULT '',
    name                TEXT DEFAULT '',
    CLIENT          TEXT DEFAULT '',
    full_name_CLIENT     TEXT DEFAULT '',
    full_name_CLIENT     TEXT DEFAULT '',
    CLIENT_date          TEXT DEFAULT '',
    CLIENT_CLIENT         TEXT DEFAULT '',
    CLIENT              TEXT DEFAULT '',
    CLIENT         TEXT DEFAULT '',
    CLIENT         TEXT DEFAULT '',
    passport_CLIENT     TEXT DEFAULT '',
    passport_CLIENT     TEXT DEFAULT '',
    passport_code       TEXT DEFAULT '',
    passport_CLIENT_date TEXT DEFAULT '',
    passport_CLIENT_by  TEXT DEFAULT '',
    passport_CLIENT     TEXT DEFAULT '',
    intl_passport       TEXT DEFAULT '',
    inn                 TEXT DEFAULT '',
    snils               TEXT DEFAULT '',
    CLIENT               TEXT DEFAULT '',
    CLIENT               TEXT DEFAULT '',
    telegram_id         TEXT DEFAULT '',
    telegram_username   TEXT DEFAULT '',
    address_zip         TEXT DEFAULT '',
    address_reg         TEXT DEFAULT '',
    address_live        TEXT DEFAULT '',
    city                TEXT DEFAULT '',
    CLIENT             TEXT DEFAULT '',
    company_name        TEXT DEFAULT '',
    company_llc         TEXT DEFAULT '',
    company_address     TEXT DEFAULT '',
    company_inn         TEXT DEFAULT '',
    company_kpp         TEXT DEFAULT '',
    company_ogrn        TEXT DEFAULT '',
    company_director    TEXT DEFAULT '',
    position            TEXT DEFAULT '',
    salary_CLIENT       TEXT DEFAULT '',
    bank_name           TEXT DEFAULT '',
    gCLIENT_folder_url   TEXT DEFAULT '',
    notes               TEXT DEFAULT ''
, photo_path TEXT DEFAULT NULL, account_no TEXT, contract_no TEXT, card_mask TEXT, balance_rub TEXT, balance_date TEXT, ref_no TEXT, doc_no TEXT, stay_CLIENT_no TEXT, CLIENT TEXT, contract_date TEXT);

CREATE TABLE IF NOT EXISTS CLIENT_CLIENT(
   id INTEGER PRIMARY KEY AUTOINCREMENT,
   CLIENT_id INTEGER, client_id INTEGER, CLIENT TEXT, docs_total INTEGER,
   docs_done INTEGER, note TEXT, payload TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    CLIENT      TEXT NOT NULL,
    CLIENT_id   INTEGER NOT NULL DEFAULT 0,
    action      TEXT NOT NULL,
    payload     TEXT DEFAULT '',
    actor       TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
);

CREATE TABLE IF NOT EXISTS CLIENT (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_by_tg_id TEXT,
    used_at TEXT
);

CREATE TABLE IF NOT EXISTS CLIENT_codes (
    code TEXT PRIMARY KEY,
    telegram_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    target_url TEXT
);

CREATE TABLE IF NOT EXISTS CLIENT_CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    CLIENT_id  INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    template_id INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    required    INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
, slot_code TEXT, is_default INTEGER DEFAULT 0, slot_part INTEGER DEFAULT 1);

CREATE TABLE IF NOT EXISTS CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL,
    CLIENT TEXT DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    CLIENT       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
);

CREATE TABLE IF NOT EXISTS template_CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES CLIENT(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    vtype       TEXT NOT NULL DEFAULT 'text',
    format      TEXT DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT 'client',   -- client | client_field | derived | manual
    source_ref  TEXT DEFAULT '',
    default_CLIENT TEXT DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0
, rule_note TEXT DEFAULT "", approved INTEGER DEFAULT 0, examples_json TEXT);

CREATE TABLE IF NOT EXISTS CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    CLIENT       TEXT NOT NULL,
    source_pdf  TEXT DEFAULT '',
    html_path   TEXT DEFAULT '',
    pages       INTEGER DEFAULT 0,
    CLIENT      TEXT NOT NULL DEFAULT 'draft',    -- draft | ok | needs_review
    qa_json     TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (CLIENT('now')),
    updated_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
, reviewed INTEGER DEFAULT 0, doc_CLIENT INTEGER, example_path TEXT, example_source TEXT, example_client TEXT);

CREATE TABLE IF NOT EXISTS CLIENT_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER, src_hash TEXT UNIQUE, ru_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS CLIENT_line(
                         template_id INTEGER NOT NULL, src TEXT NOT NULL, ru TEXT NOT NULL,
                         PRIMARY KEY(template_id, src));

CREATE TABLE IF NOT EXISTS CLIENT (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    CLIENT       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'admin',      -- admin | manager
    password    TEXT NOT NULL,                      -- хеш
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (CLIENT('now'))
, telegram_id TEXT);

CREATE TABLE IF NOT EXISTS CLIENT_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    var_name TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CLIENT_scope(
                     name TEXT PRIMARY KEY, scope TEXT NOT NULL, note TEXT);

CREATE TABLE IF NOT EXISTS CLIENT_CLIENT_CLIENT (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  CLIENT_name TEXT NOT NULL,
  CLIENT TEXT NOT NULL,
  used_count INTEGER DEFAULT 1,
  last_used TEXT,
  UNIQUE(CLIENT_name, CLIENT)
);

CREATE UNIQUE CLIENT IF NOT EXISTS idx_client_fields ON client_fields(client_id, key);

CREATE CLIENT IF NOT EXISTS idx_CLIENT_passport ON CLIENT(passport_CLIENT, passport_CLIENT);

CREATE CLIENT IF NOT EXISTS idx_CLIENT_CLIENT    ON CLIENT(CLIENT);

CREATE CLIENT IF NOT EXISTS idx_CLIENT_tg       ON CLIENT(telegram_id);

CREATE CLIENT IF NOT EXISTS idx_vvh_name ON CLIENT_CLIENT_CLIENT(CLIENT_name);

CREATE CLIENT IF NOT EXISTS ix_varchat ON CLIENT_chat(template_id, var_name, id);
