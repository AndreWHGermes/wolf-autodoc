"""Ядро: доступ к SQLite — подключение, схема, простые запросы."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from core.config import DB_PATH, DEFAULT_ADMIN_LOGIN, DEFAULT_ADMIN_PASSWORD
from core.security import hash_password

SCHEMA = Path(__file__).with_name("schema.sql")


def connect() -> sqlite3.Connection:
    # timeout и busy_timeout: при одновременной записи (воркер очереди + сайт)
    # SQLite ждёт освобождения базы вместо ошибки «database is locked».
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def q(sql: str, params: tuple = ()) -> list:
    """SELECT → список словарей."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def q1(sql: str, params: tuple = ()):
    rows = q(sql, params)
    return rows[0] if rows else None


def exec_sql(sql: str, params: tuple = ()) -> int:
    """INSERT/UPDATE/DELETE → id последней вставки или число изменённых строк."""
    with connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid if sql.strip().upper().startswith("INSERT") else cur.rowcount


def init_db() -> None:
    """Создать схему (если её нет) и первого администратора."""
    with connect() as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
    if not q1("SELECT id FROM users LIMIT 1"):
        exec_sql("INSERT INTO users (login, name, role, password) VALUES (?,?,?,?)",
                 (DEFAULT_ADMIN_LOGIN, "Администратор", "admin",
                  hash_password(DEFAULT_ADMIN_PASSWORD)))


def remember_value(name: str, value: str, approved: bool = False) -> None:
    """Запомнить значение переменной: INSERT или +used_count и обновить last_used.

    approved=True — значение поставил или подтвердил администратор. Такое значение
    весит на порядки больше автоматически собранного и получает приоритет при
    сборке следующих документов (система учится на решении человека).
    """
    if not name or value is None or str(value).strip() == "":
        return
    v = str(value)
    if approved:
        # учимся только на типовых значениях: для данных клиента ставим обычный вес
        try:
            learnable = {r["name"] for r in q("SELECT name FROM variable_scope WHERE scope='learn'")}
            if learnable and name not in learnable:
                approved = False
        except Exception:
            approved = False
    step = 100 if approved else 1
    with connect() as conn:
        conn.execute(
            "INSERT INTO variable_value_history(variable_name, value, used_count, last_used, "
            "approved, approved_at) VALUES(?,?,?,datetime('now'),?,?) "
            "ON CONFLICT(variable_name, value) DO UPDATE SET "
            "used_count = used_count + ?, last_used = datetime('now'), "
            "approved = MAX(COALESCE(approved,0), ?), "
            "approved_at = CASE WHEN ? = 1 THEN datetime('now') ELSE approved_at END",
            (name, v, step, 1 if approved else 0,
             __import__('datetime').datetime.now().isoformat(timespec='seconds') if approved else None,
             step, 1 if approved else 0, 1 if approved else 0),
        )
        conn.commit()


def approved_values() -> dict:
    """Значения, подтверждённые администратором: {имя переменной: значение}.

    Берём только переменные из белого списка (variable_scope scope='learn'):
    типовые формулировки и реквизиты офиса. Данные клиента (паспорт, счёт, суммы,
    ФИО, номера документов) обучать нельзя — иначе привычка одного клиента
    подставилась бы в документы другого.
    """
    out = {}
    try:
        learnable = {r["name"] for r in q("SELECT name FROM variable_scope WHERE scope='learn'")}
        if not learnable:
            return out
        for r in q("""SELECT variable_name, value, MAX(used_count) AS w
                        FROM variable_value_history
                       WHERE COALESCE(approved,0) = 1 AND COALESCE(value,'') <> ''
                       GROUP BY variable_name"""):
            if r["variable_name"] not in learnable:
                continue
            v = (r["value"] or "").strip()
            if v:
                out[r["variable_name"]] = v
    except Exception:
        pass
    return out


def get_suggestions(name: str, limit: int = 20) -> list:
    """Список ранее использованных значений переменной (по used_count, потом по свежести)."""
    if not name:
        return []
    rows = q(
        "SELECT value, used_count FROM variable_value_history "
        "WHERE variable_name=? ORDER BY used_count DESC, last_used DESC LIMIT ?",
        (name, int(limit)),
    )
    return rows


def setting(key: str, default: str = "") -> str:
    row = q1("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default


def current_record_kind():
    """Пометка для новых записей: 'test' пока идёт обкатка, иначе None (рабочая запись).

    Управляется настройкой record_mode (scripts/mark_records.py mode test|prod).
    """
    mode = (setting("record_mode", "") or "").strip()
    return mode or None


def set_setting(key: str, value: str) -> None:
    exec_sql("INSERT INTO settings (key, value, updated_at) VALUES (?,?,datetime('now')) "
             "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
             (key, value))


def log_event(entity: str, entity_id: int, action: str, payload: str = "", actor: str = "") -> None:
    exec_sql("INSERT INTO events (entity, entity_id, action, payload, actor) VALUES (?,?,?,?,?)",
             (entity, entity_id, action, payload, actor))


# --------------------------- клиенты ---------------------------

CLIENT_FIELDS = [
    ("surname", "Фамилия"), ("name", "Имя"), ("patronymic", "Отчество"),
    ("full_name_latin", "ФИО латиницей (UPPERCASE)"), ("full_name_title", "ФИО (Title Case)"),
    ("birth_date", "Дата рождения"), ("birth_place", "Место рождения"),
    ("gender", "Пол"), ("citizenship", "Гражданство"), ("nationality", "Национальность"),
    ("passport_series", "Паспорт: серия"), ("passport_number", "Паспорт: номер"),
    ("passport_code", "Код подразделения"), ("passport_issue_date", "Паспорт: дата выдачи"),
    ("passport_issued_by", "Паспорт: кем выдан"), ("passport_expiry", "Паспорт: срок действия"),
    ("intl_passport", "Загранпаспорт"), ("inn", "ИНН"), ("snils", "СНИЛС"),
    ("phone", "Телефон"), ("email", "E-mail"),
    ("telegram_id", "Telegram ID"), ("telegram_username", "Telegram логин"),
    ("address_zip", "Индекс"), ("address_reg", "Адрес регистрации"), ("address_live", "Адрес проживания"),
    ("city", "Город"), ("country", "Страна"),
    ("company_name", "Компания (название)"), ("company_llc", 'Компания (LLC "…")'),
    ("company_address", "Компания: адрес"), ("company_inn", "Компания: ИНН"),
    ("company_kpp", "Компания: КПП"), ("company_ogrn", "Компания: ОГРН"),
    ("company_director", "Компания: руководитель"), ("position", "Должность"),
    ("salary_amount", "Зарплата"), ("bank_name", "Банк"),
    ("gdrive_folder_url", "Папка Google Drive"), ("notes", "Заметки"),
]
FIELD_MAP = dict(CLIENT_FIELDS)


def client_list(search: str = "") -> list:
    if search:
        like = f"%{search.strip()}%"
        return q("""SELECT * FROM clients WHERE
                    surname LIKE ? OR name LIKE ? OR full_name_latin LIKE ? OR phone LIKE ?
                    OR passport_number LIKE ? OR telegram_username LIKE ?
                    ORDER BY updated_at DESC LIMIT 200""", (like,) * 6)
    return q("SELECT * FROM clients ORDER BY updated_at DESC LIMIT 200")


def client_get(client_id: int):
    return q1("SELECT * FROM clients WHERE id=?", (client_id,))


_PATRONYMIC_TAIL = re.compile(r"(ич|на|улы|кызы|оглы)$", re.I)


def clean_name_part(field: str, value) -> str:
    """Убрать из ФИО мусор распознавания (заявка 108, клиент 89, 15.10.2026).

    Сканер и модель-распознаватель иногда отдают вместо отчества простыню из
    повторяющихся букв («Kkkkkkkeeeekeree»). Значение попадало в карточку клиента
    и уезжало в договоры как часть имени («CLIENT STEPAN KKKKKKKEEEEKEREE»),
    из-за чего документ не проходил проверку качества и заявка вставала в ступор.
    Такие значения в карточку не пишем — поле остаётся пустым, документ соберётся
    без отчества (оно в англоязычных документах и не нужно).
    """
    v = re.sub(r"\s+", " ", str(value or "")).strip()
    if not v:
        return v
    letters = [ch for ch in v.upper() if ch.isalpha()]
    if letters:
        same = max(letters.count(ch) for ch in set(letters)) / float(len(letters))
        vowels = sum(1 for ch in letters if ch in "AEIOUYАЕЁИОУЫЭЮЯ")
        if same >= 0.4 or vowels == 0:            # «KKKKKKKEEEEKEREE», «Ссссссесе»
            return ""
    if re.search(r"\d", v):                        # цифры в ФИО — тоже мусор
        return ""
    if field == "patronymic" and not _PATRONYMIC_TAIL.search(v):
        return ""                                  # не отчество вовсе — не пишем
    return v


def client_save(data: dict, client_id: int = None) -> int:
    """Создать или обновить клиента; возвращает id."""
    data = dict(data or {})
    for _f in ("surname", "name", "patronymic"):
        if _f in data:
            data[_f] = clean_name_part(_f, data[_f])
    cols = [c for c, _ in CLIENT_FIELDS if c in data]
    if client_id:
        sets = ", ".join(f"{c}=?" for c in cols)
        exec_sql(f"UPDATE clients SET {sets}, updated_at=datetime('now') WHERE id=?",
                 tuple(data[c] for c in cols) + (client_id,))
        return client_id
    marks = ", ".join("?" for _ in cols)
    new_id = exec_sql(f"INSERT INTO clients ({', '.join(cols)}) VALUES ({marks})",
                      tuple(data[c] for c in cols))
    kind = current_record_kind()
    if kind:
        exec_sql("UPDATE clients SET record_kind=? WHERE id=?", (kind, new_id))
    return new_id


def client_label(row: dict) -> str:
    name = " ".join(x for x in (row.get("surname"), row.get("name"), row.get("patronymic")) if x).strip()
    return name or row.get("full_name_latin") or f"Клиент #{row.get('id')}"


def client_find_duplicate(data: dict):
    """Повторное обращение: ищем по паспорту, телефону, telegram."""
    conds, params = [], []
    if data.get("passport_number"):
        conds.append("(passport_series=? AND passport_number=?)")
        params += [data.get("passport_series", ""), data["passport_number"]]
    for key in ("phone", "telegram_id"):
        if data.get(key):
            conds.append(f"{key}=?")
            params.append(data[key])
    if not conds:
        return None
    return q1(f"SELECT * FROM clients WHERE {' OR '.join(conds)} ORDER BY id LIMIT 1", tuple(params))


_SAFE_COL = re.compile(r"^[a-z_]+$")


def client_field_list(client_id: int) -> list:
    return q("SELECT * FROM client_fields WHERE client_id=? ORDER BY key", (client_id,))


def client_field_set(client_id: int, key: str, value: str, source: str = "manual",
                     value_type: str = "text") -> None:
    if not _SAFE_COL.match(key or ""):
        raise ValueError("недопустимый ключ поля")
    exec_sql("""INSERT INTO client_fields (client_id, key, value, value_type, source, updated_at)
                VALUES (?,?,?,?,?,datetime('now'))
                ON CONFLICT(client_id, key) DO UPDATE SET
                  value=excluded.value, source=excluded.source, updated_at=datetime('now')""",
             (client_id, key, value, value_type, source))


def client_documents(client_id: int) -> list:
    return q("SELECT * FROM client_documents WHERE client_id=? ORDER BY id DESC", (client_id,))


# ---------------------- заявки и документы заявки ----------------------

def application_list(status: str = "") -> list:
    sql = """SELECT a.*, c.surname, c.name, c.full_name_latin, p.code AS product_code,
                    p.name AS product_name, u.login AS taken_login,
                    bm.telegram_id AS manager_tg, bm.full_name AS manager_name,
                    bm.username AS manager_username
             FROM applications a
             LEFT JOIN clients c ON c.id = a.client_id
             LEFT JOIN products p ON p.id = a.product_id
             LEFT JOIN users u ON u.id = a.taken_by
             LEFT JOIN bot_managers bm ON bm.id = a.bot_manager_id"""
    if status:
        return q(sql + " WHERE a.status=? ORDER BY a.id DESC LIMIT 200", (status,))
    return q(sql + " ORDER BY a.id DESC LIMIT 200")


def application_get(app_id: int):
    return q1("""SELECT a.*, c.surname, c.name, c.full_name_latin,
                        p.code AS product_code, p.name AS product_name,
                        u.login AS taken_login
                 FROM applications a
                 LEFT JOIN clients c ON c.id = a.client_id
                 LEFT JOIN products p ON p.id = a.product_id
                 LEFT JOIN users u ON u.id = a.taken_by
                 WHERE a.id=?""", (app_id,))


def application_create(client_id: int, product_id: int | None, source: str = "telegram",
                       comment: str = "", gdrive_url: str = "", price_idr: int = 0,
                       raw_payload: str = "") -> int:
    app_id = exec_sql(
        """INSERT INTO applications
           (client_id, product_id, source, comment, brief, gdrive_url, price_idr, raw_payload, record_kind)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (client_id, product_id, source, comment, comment, gdrive_url, price_idr, raw_payload,
         current_record_kind()))
    autoprepare_trigger(app_id)
    return app_id


def autoprepare_trigger(app_id: int) -> None:
    """Сразу после появления заявки: разбор документов Google Drive и формирование документов продукта.

    Запускается отдельным процессом, чтобы не задерживать ответ бота/сайта.
    При сбое модели или сети заявка всё равно создаётся — статус разбора будет виден в карточке.
    """
    import subprocess
    try:
        exec_sql("""INSERT INTO drive_scans(application_id, client_id, status, docs_total, docs_done, note)
                    SELECT ?, client_id, 'running', 0, 0, 'автоподготовка запущена' FROM applications WHERE id=?""",
                 (app_id, app_id))
    except Exception:
        pass
    try:
        subprocess.Popen(["/usr/bin/python3", "/opt/wolf_v2/scripts/app_autoprepare.py", str(app_id)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


def application_take(app_id: int, user_id: int) -> None:
    exec_sql("""UPDATE applications
                SET status='in_progress', taken_by=?, taken_at=datetime('now')
                WHERE id=? AND status='new'""", (user_id, app_id))


def application_set_status(app_id: int, status: str) -> None:
    if status == "sent":
        exec_sql("UPDATE applications SET status=?, sent_at=datetime('now') WHERE id=?",
                 (status, app_id))
    else:
        exec_sql("UPDATE applications SET status=? WHERE id=?", (status, app_id))


def application_documents(app_id: int) -> list:
    return q("""SELECT ad.*, t.title, t.code, t.pages
                FROM application_documents ad
                JOIN templates t ON t.id = ad.template_id
                WHERE ad.application_id=?
                ORDER BY ad.id""", (app_id,))


def application_doc_create(app_id: int, template_id: int) -> int:
    # Шаблон, закрытый для работы (status='blocked'), в заявку не заводится: так временно
    # отключаются форматы, которые заказчик убрал из работы (резюме, кроме формата Сиваева).
    tpl = q1("SELECT status FROM templates WHERE id=?", (template_id,))
    if tpl and str(tpl["status"] or "").strip() == "blocked":
        return 0
    existing = q1("SELECT id FROM application_documents WHERE application_id=? AND template_id=?",
                  (app_id, template_id))
    if existing:
        return existing["id"]
    return exec_sql("INSERT INTO application_documents (application_id, template_id) VALUES (?,?)",
                    (app_id, template_id))


def ensure_product_documents(app_id: int) -> list:
    """Достраивает документы заявки по составу продукта: обязательные документы не теряются.

    Если документ из состава продукта (например договор для мостовой визы) в заявке
    отсутствует — он заводится заново. Возвращает коды шаблонов, которые пришлось создать.
    """
    row = q1("SELECT product_id FROM applications WHERE id=?", (app_id,))
    pid = row["product_id"] if row else None
    if not pid:
        return []
    added = []
    rows = q("""SELECT t.id AS tid, t.code FROM product_documents pd
                 JOIN templates t ON t.id=pd.template_id
                WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged')""", (pid,)) or []
    for r in rows:
        got = q1("SELECT id FROM application_documents WHERE application_id=? AND template_id=?",
                 (app_id, r["tid"]))
        if got:
            continue
        try:
            application_doc_create(app_id, r["tid"])
            added.append(r["code"])
        except Exception:
            pass
    return added


def application_doc_set(ad_id: int, status: str, values_json: str = "", pdf_path: str = "",
                        error: str = "") -> None:
    if status == "sent":
        exec_sql("""UPDATE application_documents SET status=?, values_json=?, pdf_path=?,
                    rendered_at=datetime('now'), sent_at=datetime('now'), error=? WHERE id=?""",
                 (status, values_json, pdf_path, error, ad_id))
    elif status == "filled" or status == "verified":
        exec_sql("""UPDATE application_documents SET status=?, values_json=?, pdf_path=?,
                    rendered_at=datetime('now'), error=? WHERE id=?""",
                 (status, values_json, pdf_path, error, ad_id))
    else:
        exec_sql("""UPDATE application_documents SET status=?, values_json=?, pdf_path=?,
                    error=? WHERE id=?""", (status, values_json, pdf_path, error, ad_id))


def application_doc_summary(app_id: int) -> dict:
    rows = q("SELECT status, COUNT(*) c FROM application_documents WHERE application_id=? GROUP BY status",
             (app_id,))
    out = {"pending": 0, "filled": 0, "verified": 0, "sent": 0, "error": 0, "total": 0}
    for r in rows:
        out[r["status"]] = r["c"]
        out["total"] += r["c"]
    return out


# ---------------------- менеджеры бота ----------------------

def bot_managers_list() -> list:
    return q("SELECT * FROM bot_managers ORDER BY role DESC, full_name, username, telegram_id")


def bot_managers_by_role(role: str) -> list:
    """role: 'manager' (присылают заявки) или 'admin' (получают уведомления)."""
    return q("SELECT * FROM bot_managers WHERE role=? OR role='both' "
             "ORDER BY full_name, username", (role,))


def bot_manager_upsert(telegram_id: str, username: str = "", full_name: str = "",
                       role: str = "manager") -> int:
    existing = q1("SELECT id FROM bot_managers WHERE telegram_id=?", (telegram_id,))
    if existing:
        exec_sql("UPDATE bot_managers SET username=?, full_name=?, role=? WHERE id=?",
                 (username, full_name, role, existing["id"]))
        return existing["id"]
    return exec_sql("INSERT INTO bot_managers (telegram_id, username, full_name, role) VALUES (?,?,?,?)",
                    (telegram_id, username, full_name, role))


def bot_manager_delete(telegram_id: str) -> None:
    exec_sql("DELETE FROM bot_managers WHERE telegram_id=?", (telegram_id,))


def stats() -> dict:
    def one(sql):
        row = q1(sql)
        return list(row.values())[0] if row else 0
    return {
        "clients": one("SELECT COUNT(*) FROM clients WHERE status='active'"),
        "applications_new": one("SELECT COUNT(*) FROM applications WHERE status='new'"),
        "applications_all": one("SELECT COUNT(*) FROM applications"),
        "applications_in": one("SELECT COUNT(*) FROM applications WHERE status IN ('new','in_progress')"),
        "sum_new_idr": (one("SELECT COALESCE(SUM(price_idr),0) FROM applications WHERE status='new'") or 0),
        "sum_all_idr": (one("SELECT COALESCE(SUM(price_idr),0) FROM applications") or 0),
        "templates": one("SELECT COUNT(*) FROM templates"),
        "products": one("SELECT COUNT(*) FROM products WHERE active=1"),
        "documents": one("SELECT COUNT(*) FROM client_documents"),
    }
