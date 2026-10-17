-- Схема БД Wolf_AutoDoc CRM.
-- Правило: постоянные данные клиента — отдельными колонками,
-- всё, что появляется от новых шаблонов, — в client_fields (расширяемо).

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    login       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'admin',      -- admin | manager
    password    TEXT NOT NULL,                      -- хеш
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    status              TEXT NOT NULL DEFAULT 'active',   -- active | archived
    source              TEXT NOT NULL DEFAULT 'manual',   -- manual | telegram
    surname             TEXT DEFAULT '',
    name                TEXT DEFAULT '',
    patronymic          TEXT DEFAULT '',
    full_name_latin     TEXT DEFAULT '',
    full_name_title     TEXT DEFAULT '',
    birth_date          TEXT DEFAULT '',
    birth_place         TEXT DEFAULT '',
    gender              TEXT DEFAULT '',
    citizenship         TEXT DEFAULT '',
    nationality         TEXT DEFAULT '',
    passport_series     TEXT DEFAULT '',
    passport_number     TEXT DEFAULT '',
    passport_code       TEXT DEFAULT '',
    passport_issue_date TEXT DEFAULT '',
    passport_issued_by  TEXT DEFAULT '',
    passport_expiry     TEXT DEFAULT '',
    intl_passport       TEXT DEFAULT '',
    inn                 TEXT DEFAULT '',
    snils               TEXT DEFAULT '',
    phone               TEXT DEFAULT '',
    email               TEXT DEFAULT '',
    telegram_id         TEXT DEFAULT '',
    telegram_username   TEXT DEFAULT '',
    address_zip         TEXT DEFAULT '',
    address_reg         TEXT DEFAULT '',
    address_live        TEXT DEFAULT '',
    city                TEXT DEFAULT '',
    country             TEXT DEFAULT '',
    company_name        TEXT DEFAULT '',
    company_llc         TEXT DEFAULT '',
    company_address     TEXT DEFAULT '',
    company_inn         TEXT DEFAULT '',
    company_kpp         TEXT DEFAULT '',
    company_ogrn        TEXT DEFAULT '',
    company_director    TEXT DEFAULT '',
    position            TEXT DEFAULT '',
    salary_amount       TEXT DEFAULT '',
    bank_name           TEXT DEFAULT '',
    gdrive_folder_url   TEXT DEFAULT '',
    notes               TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_clients_passport ON clients(passport_series, passport_number);
CREATE INDEX IF NOT EXISTS idx_clients_phone    ON clients(phone);
CREATE INDEX IF NOT EXISTS idx_clients_tg       ON clients(telegram_id);

-- дополнительные переменные клиента (из новых шаблонов)
CREATE TABLE IF NOT EXISTS client_fields (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL DEFAULT '',
    value_type  TEXT NOT NULL DEFAULT 'text',
    source      TEXT NOT NULL DEFAULT 'manual',   -- manual | ocr | derived | imported
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_client_fields ON client_fields(client_id, key);

-- оригиналы клиента (файлы у нас или ссылки на Google Drive)
CREATE TABLE IF NOT EXISTS client_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'other',    -- passport | bank_statement | selfie | other
    title       TEXT NOT NULL DEFAULT '',
    path        TEXT DEFAULT '',                  -- локальный файл
    drive_url   TEXT DEFAULT '',
    text_dump   TEXT DEFAULT '',                  -- распознанный текст
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    title       TEXT NOT NULL,
    source_pdf  TEXT DEFAULT '',
    html_path   TEXT DEFAULT '',
    pages       INTEGER DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'draft',    -- draft | ok | needs_review
    qa_json     TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS template_variables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    vtype       TEXT NOT NULL DEFAULT 'text',
    format      TEXT DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT 'client',   -- client | client_field | derived | manual
    source_ref  TEXT DEFAULT '',
    default_value TEXT DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS product_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    required    INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'new',     -- new | in_progress | ready | sent | closed | error
    source       TEXT NOT NULL DEFAULT 'telegram',
    gdrive_url   TEXT DEFAULT '',
    price_idr    INTEGER NOT NULL DEFAULT 0,
    comment      TEXT DEFAULT '',
    raw_payload  TEXT DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    taken_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    taken_at     TEXT DEFAULT '',
    sent_at      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS application_documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    template_id    INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending | filled | verified | sent | error
    values_json    TEXT DEFAULT '',
    pdf_path       TEXT DEFAULT '',
    error          TEXT DEFAULT '',
    rendered_at    TEXT DEFAULT '',
    sent_at        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bot_managers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT NOT NULL UNIQUE,
    username    TEXT DEFAULT '',
    full_name   TEXT DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'manager',     -- manager | blocked
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity      TEXT NOT NULL,
    entity_id   INTEGER NOT NULL DEFAULT 0,
    action      TEXT NOT NULL,
    payload     TEXT DEFAULT '',
    actor       TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS variable_value_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    variable_name TEXT NOT NULL,
    value         TEXT NOT NULL,
    used_count    INTEGER DEFAULT 1,
    last_used     TEXT,
    UNIQUE(variable_name, value)
);
CREATE INDEX IF NOT EXISTS idx_vvh_name ON variable_value_history(variable_name);
