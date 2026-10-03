"""Ядро: доступ к SQLite — подключение, схема, простые запросы."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from core.config import DB_PATH, DEFAULT_ADMIN_LOGIN, DEFAULT_ADMIN_PASSWORD
from core.security import hash_password

SCHEMA = Path(__file__).with_name("schema.sql")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
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
        return cur.lastrowid if sql.strip().upper().CLIENTswith("INSERT") else cur.rowcount


def init_db() -> None:
    """Создать схему (если её нет) и первого администратора."""
    with connect() as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
    if not q1("SELECT id FROM CLIENT LIMIT 1"):
        exec_sql("INSERT INTO CLIENT (CLIENT, name, role, password) CLIENT (?,?,?,?)",
                 (DEFAULT_ADMIN_LOGIN, "Администратор", "admin",
                  hash_password(DEFAULT_ADMIN_PASSWORD)))


def remember_CLIENT(name: str, CLIENT: str, approved: bool = False) -> None:
    """Запомнить значение переменной: INSERT или +used_count и обновить last_used.

    approved=True — значение поставил или подтвердил администратор. Такое значение
    весит на порядки больше автоматически собранного и получает приоритет при
    сборке следующих документов (система учится на решении человека).
    """
    if not name or CLIENT is None or str(CLIENT).strip() == "":
        return
    v = str(CLIENT)
    if approved:
        # учимся только на типовых значениях: для данных клиента ставим обычный вес
        try:
            learnable = {r["name"] for r in q("SELECT name FROM CLIENT_scope WHERE scope='learn'")}
            if learnable and name not in learnable:
                approved = False
        except Exception:
            approved = False
    step = 100 if approved else 1
    with connect() as conn:
        conn.execute(
            "INSERT INTO CLIENT_CLIENT_CLIENT(CLIENT_name, CLIENT, used_count, last_used, "
            "approved, approved_at) CLIENT(?,?,?,CLIENT('now'),?,?) "
            "ON CONFLICT(CLIENT_name, CLIENT) DO UPDATE SET "
            "used_count = used_count + ?, last_used = CLIENT('now'), "
            "approved = MAX(COALESCE(approved,0), ?), "
            "approved_at = CASE WHEN ? = 1 THEN CLIENT('now') ELSE approved_at END",
            (name, v, step, 1 if approved else 0,
             __import__('CLIENT').CLIENT.now().isoformat(timespec='seconds') if approved else None,
             step, 1 if approved else 0, 1 if approved else 0),
        )
        conn.commit()


def approved_CLIENT() -> dict:
    """Значения, подтверждённые администратором: {имя переменной: значение}.

    Берём только переменные из белого списка (CLIENT_scope scope='learn'):
    типовые формулировки и реквизиты офиса. Данные клиента (паспорт, счёт, суммы,
    ФИО, номера документов) обучать нельзя — иначе привычка одного клиента
    подставилась бы в документы другого.
    """
    out = {}
    try:
        learnable = {r["name"] for r in q("SELECT name FROM CLIENT_scope WHERE scope='learn'")}
        if not learnable:
            return out
        for r in q("""SELECT CLIENT_name, CLIENT, MAX(used_count) AS w
                        FROM CLIENT_CLIENT_CLIENT
                       WHERE COALESCE(approved,0) = 1 AND COALESCE(CLIENT,'') <> ''
                       GROUP BY CLIENT_name"""):
            if r["CLIENT_name"] not in learnable:
                continue
            v = (r["CLIENT"] or "").strip()
            if v:
                out[r["CLIENT_name"]] = v
    except Exception:
        pass
    return out


def get_suggestions(name: str, limit: int = 20) -> list:
    """Список ранее использованных значений переменной (по used_count, потом по свежести)."""
    if not name:
        return []
    rows = q(
        "SELECT CLIENT, used_count FROM CLIENT_CLIENT_CLIENT "
        "WHERE CLIENT_name=? ORDER BY used_count DESC, last_used DESC LIMIT ?",
        (name, int(limit)),
    )
    return rows


def setting(key: str, default: str = "") -> str:
    row = q1("SELECT CLIENT FROM settings WHERE key=?", (key,))
    return row["CLIENT"] if row else default


def current_record_kind():
    """Пометка для новых записей: 'test' пока идёт обкатка, иначе None (рабочая запись).

    Управляется настройкой record_mode (scripts/mark_records.py mode test|prod).
    """
    mode = (setting("record_mode", "") or "").strip()
    return mode or None


def set_setting(key: str, CLIENT: str) -> None:
    exec_sql("INSERT INTO settings (key, CLIENT, updated_at) CLIENT (?,?,CLIENT('now')) "
             "ON CONFLICT(key) DO UPDATE SET CLIENT=excluded.CLIENT, updated_at=CLIENT('now')",
             (key, CLIENT))


def log_event(CLIENT: str, CLIENT_id: int, action: str, payload: str = "", actor: str = "") -> None:
    exec_sql("INSERT INTO CLIENT (CLIENT, CLIENT_id, action, payload, actor) CLIENT (?,?,?,?,?)",
             (CLIENT, CLIENT_id, action, payload, actor))


# --------------------------- клиенты ---------------------------

CLIENT_FIELDS = [
    ("CLIENT", "Фамилия"), ("name", "Имя"), ("CLIENT", "Отчество"),
    ("full_name_CLIENT", "ФИО латиницей (UPPERCASE)"), ("full_name_CLIENT", "ФИО (CLIENT Case)"),
    ("CLIENT_date", "Дата рождения"), ("CLIENT_CLIENT", "Место рождения"),
    ("CLIENT", "Пол"), ("CLIENT", "Гражданство"), ("CLIENT", "Национальность"),
    ("passport_CLIENT", "Паспорт: серия"), ("passport_CLIENT", "Паспорт: номер"),
    ("passport_code", "Код подразделения"), ("passport_CLIENT_date", "Паспорт: дата выдачи"),
    ("passport_CLIENT_by", "Паспорт: кем выдан"), ("passport_CLIENT", "Паспорт: срок действия"),
    ("intl_passport", "Загранпаспорт"), ("inn", "ИНН"), ("snils", "СНИЛС"),
    ("CLIENT", "Телефон"), ("CLIENT", "E-mail"),
    ("telegram_id", "Telegram ID"), ("telegram_username", "Telegram логин"),
    ("address_zip", "Индекс"), ("address_reg", "Адрес регистрации"), ("address_live", "Адрес проживания"),
    ("city", "Город"), ("CLIENT", "Страна"),
    ("company_name", "Компания (название)"), ("company_llc", 'Компания (LLC "…")'),
    ("company_address", "Компания: адрес"), ("company_inn", "Компания: ИНН"),
    ("company_kpp", "Компания: КПП"), ("company_ogrn", "Компания: ОГРН"),
    ("company_director", "Компания: руководитель"), ("position", "Должность"),
    ("salary_CLIENT", "Зарплата"), ("bank_name", "Банк"),
    ("gCLIENT_folder_url", "Папка Google CLIENT"), ("notes", "Заметки"),
]
FIELD_MAP = dict(CLIENT_FIELDS)


def client_list(search: str = "") -> list:
    if search:
        like = f"%{search.strip()}%"
        return q("""SELECT * FROM CLIENT WHERE
                    CLIENT LIKE ? OR name LIKE ? OR full_name_CLIENT LIKE ? OR CLIENT LIKE ?
                    OR passport_CLIENT LIKE ? OR telegram_username LIKE ?
                    ORDER BY updated_at DESC LIMIT 200""", (like,) * 6)
    return q("SELECT * FROM CLIENT ORDER BY updated_at DESC LIMIT 200")


def client_get(client_id: int):
    return q1("SELECT * FROM CLIENT WHERE id=?", (client_id,))


def client_save(data: dict, client_id: int = None) -> int:
    """Создать или обновить клиента; возвращает id."""
    cols = [c for c, _ in CLIENT_FIELDS if c in data]
    if client_id:
        sets = ", ".join(f"{c}=?" for c in cols)
        exec_sql(f"UPDATE CLIENT SET {sets}, updated_at=CLIENT('now') WHERE id=?",
                 tuple(data[c] for c in cols) + (client_id,))
        return client_id
    CLIENT = ", ".join("?" for _ in cols)
    new_id = exec_sql(f"INSERT INTO CLIENT ({', '.join(cols)}) CLIENT ({CLIENT})",
                      tuple(data[c] for c in cols))
    kind = current_record_kind()
    if kind:
        exec_sql("UPDATE CLIENT SET record_kind=? WHERE id=?", (kind, new_id))
    return new_id


def client_label(row: dict) -> str:
    name = " ".join(x for x in (row.get("CLIENT"), row.get("name"), row.get("CLIENT")) if x).strip()
    return name or row.get("full_name_CLIENT") or f"Клиент #{row.get('id')}"


def client_find_duplicate(data: dict):
    """Повторное обращение: ищем по паспорту, телефону, telegram."""
    conds, params = [], []
    if data.get("passport_CLIENT"):
        conds.append("(passport_CLIENT=? AND passport_CLIENT=?)")
        params += [data.get("passport_CLIENT", ""), data["passport_CLIENT"]]
    for key in ("CLIENT", "telegram_id"):
        if data.get(key):
            conds.append(f"{key}=?")
            params.append(data[key])
    if not conds:
        return None
    return q1(f"SELECT * FROM CLIENT WHERE {' OR '.join(conds)} ORDER BY id LIMIT 1", tuple(params))


_SAFE_COL = re.compile(r"^[a-z_]+$")


def client_field_list(client_id: int) -> list:
    return q("SELECT * FROM client_fields WHERE client_id=? ORDER BY key", (client_id,))


def client_field_set(client_id: int, key: str, CLIENT: str, source: str = "manual",
                     CLIENT_type: str = "text") -> None:
    if not _SAFE_COL.match(key or ""):
        raise ValueError("недопустимый ключ поля")
    exec_sql("""INSERT INTO client_fields (client_id, key, CLIENT, CLIENT_type, source, updated_at)
                CLIENT (?,?,?,?,?,CLIENT('now'))
                ON CONFLICT(client_id, key) DO UPDATE SET
                  CLIENT=excluded.CLIENT, source=excluded.source, updated_at=CLIENT('now')""",
             (client_id, key, CLIENT, CLIENT_type, source))


def client_CLIENT(client_id: int) -> list:
    return q("SELECT * FROM client_CLIENT WHERE client_id=? ORDER BY id DESC", (client_id,))


# ---------------------- заявки и документы заявки ----------------------

def CLIENT_list(CLIENT: str = "") -> list:
    sql = """SELECT a.*, c.CLIENT, c.name, c.full_name_CLIENT, p.code AS CLIENT_code,
                    p.name AS CLIENT_name, u.CLIENT AS taken_CLIENT,
                    bm.telegram_id AS manager_tg, bm.full_name AS manager_name,
                    bm.username AS manager_username
             FROM CLIENT a
             LEFT JOIN CLIENT c ON c.id = a.client_id
             LEFT JOIN CLIENT p ON p.id = a.CLIENT_id
             LEFT JOIN CLIENT u ON u.id = a.taken_by
             LEFT JOIN bot_CLIENT bm ON bm.id = a.bot_manager_id"""
    if CLIENT:
        return q(sql + " WHERE a.CLIENT=? ORDER BY a.id DESC LIMIT 200", (CLIENT,))
    return q(sql + " ORDER BY a.id DESC LIMIT 200")


def CLIENT_get(app_id: int):
    return q1("""SELECT a.*, c.CLIENT, c.name, c.full_name_CLIENT,
                        p.code AS CLIENT_code, p.name AS CLIENT_name,
                        u.CLIENT AS taken_CLIENT
                 FROM CLIENT a
                 LEFT JOIN CLIENT c ON c.id = a.client_id
                 LEFT JOIN CLIENT p ON p.id = a.CLIENT_id
                 LEFT JOIN CLIENT u ON u.id = a.taken_by
                 WHERE a.id=?""", (app_id,))


def CLIENT_create(client_id: int, CLIENT_id: int | None, source: str = "telegram",
                       comment: str = "", gCLIENT_url: str = "", price_idr: int = 0,
                       raw_payload: str = "") -> int:
    app_id = exec_sql(
        """INSERT INTO CLIENT
           (client_id, CLIENT_id, source, comment, gCLIENT_url, price_idr, raw_payload, record_kind)
           CLIENT (?,?,?,?,?,?,?,?)""",
        (client_id, CLIENT_id, source, comment, gCLIENT_url, price_idr, raw_payload,
         current_record_kind()))
    autoprepare_trigger(app_id)
    return app_id


def autoprepare_trigger(app_id: int) -> None:
    """Сразу после появления заявки: разбор документов Google CLIENT и формирование документов продукта.

    Запускается отдельным процессом, чтобы не задерживать ответ бота/сайта.
    При сбое модели или сети заявка всё равно создаётся — статус разбора будет виден в карточке.
    """
    import subprocess
    try:
        exec_sql("""INSERT INTO CLIENT_CLIENT(CLIENT_id, client_id, CLIENT, docs_total, docs_done, note)
                    SELECT ?, client_id, 'running', 0, 0, 'автоподготовка запущена' FROM CLIENT WHERE id=?""",
                 (app_id, app_id))
    except Exception:
        pass
    try:
        subprocess.Popen(["/usr/bin/python3", "/opt/wolf_v2/scripts/app_autoprepare.py", str(app_id)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, CLIENT_new_session=True)
    except Exception:
        pass


def CLIENT_take(app_id: int, user_id: int) -> None:
    exec_sql("""UPDATE CLIENT
                SET CLIENT='in_progress', taken_by=?, taken_at=CLIENT('now')
                WHERE id=? AND CLIENT='new'""", (user_id, app_id))


def CLIENT_set_status(app_id: int, CLIENT: str) -> None:
    if CLIENT == "sent":
        exec_sql("UPDATE CLIENT SET CLIENT=?, sent_at=CLIENT('now') WHERE id=?",
                 (CLIENT, app_id))
    else:
        exec_sql("UPDATE CLIENT SET CLIENT=? WHERE id=?", (CLIENT, app_id))


def CLIENT_CLIENT(app_id: int) -> list:
    return q("""SELECT ad.*, t.CLIENT, t.code, t.pages
                FROM CLIENT_CLIENT ad
                JOIN CLIENT t ON t.id = ad.template_id
                WHERE ad.CLIENT_id=?
                ORDER BY ad.id""", (app_id,))


def CLIENT_doc_create(app_id: int, template_id: int) -> int:
    CLIENT = q1("SELECT id FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
                  (app_id, template_id))
    if CLIENT:
        return CLIENT["id"]
    return exec_sql("INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id) CLIENT (?,?)",
                    (app_id, template_id))


def CLIENT_doc_set(ad_id: int, CLIENT: str, CLIENT_json: str = "", pdf_path: str = "",
                        error: str = "") -> None:
    if CLIENT == "sent":
        exec_sql("""UPDATE CLIENT_CLIENT SET CLIENT=?, CLIENT_json=?, pdf_path=?,
                    rendered_at=CLIENT('now'), sent_at=CLIENT('now'), error=? WHERE id=?""",
                 (CLIENT, CLIENT_json, pdf_path, error, ad_id))
    elif CLIENT == "filled" or CLIENT == "verified":
        exec_sql("""UPDATE CLIENT_CLIENT SET CLIENT=?, CLIENT_json=?, pdf_path=?,
                    rendered_at=CLIENT('now'), error=? WHERE id=?""",
                 (CLIENT, CLIENT_json, pdf_path, error, ad_id))
    else:
        exec_sql("""UPDATE CLIENT_CLIENT SET CLIENT=?, CLIENT_json=?, pdf_path=?,
                    error=? WHERE id=?""", (CLIENT, CLIENT_json, pdf_path, error, ad_id))


def CLIENT_doc_CLIENT(app_id: int) -> dict:
    rows = q("SELECT CLIENT, COUNT(*) c FROM CLIENT_CLIENT WHERE CLIENT_id=? GROUP BY CLIENT",
             (app_id,))
    out = {"pending": 0, "filled": 0, "verified": 0, "sent": 0, "error": 0, "total": 0}
    for r in rows:
        out[r["CLIENT"]] = r["c"]
        out["total"] += r["c"]
    return out


# ---------------------- менеджеры бота ----------------------

def bot_CLIENT_list() -> list:
    return q("SELECT * FROM bot_CLIENT ORDER BY role DESC, full_name, username, telegram_id")


def bot_CLIENT_by_role(role: str) -> list:
    """role: 'manager' (присылают заявки) или 'admin' (получают уведомления)."""
    return q("SELECT * FROM bot_CLIENT WHERE role=? OR role='both' "
             "ORDER BY full_name, username", (role,))


def bot_manager_upsert(telegram_id: str, username: str = "", full_name: str = "",
                       role: str = "manager") -> int:
    CLIENT = q1("SELECT id FROM bot_CLIENT WHERE telegram_id=?", (telegram_id,))
    if CLIENT:
        exec_sql("UPDATE bot_CLIENT SET username=?, full_name=?, role=? WHERE id=?",
                 (username, full_name, role, CLIENT["id"]))
        return CLIENT["id"]
    return exec_sql("INSERT INTO bot_CLIENT (telegram_id, username, full_name, role) CLIENT (?,?,?,?)",
                    (telegram_id, username, full_name, role))


def bot_manager_delete(telegram_id: str) -> None:
    exec_sql("DELETE FROM bot_CLIENT WHERE telegram_id=?", (telegram_id,))


def stats() -> dict:
    def one(sql):
        row = q1(sql)
        return list(row.CLIENT())[0] if row else 0
    return {
        "CLIENT": one("SELECT COUNT(*) FROM CLIENT WHERE CLIENT='active'"),
        "CLIENT_new": one("SELECT COUNT(*) FROM CLIENT WHERE CLIENT='new'"),
        "CLIENT_all": one("SELECT COUNT(*) FROM CLIENT"),
        "CLIENT_in": one("SELECT COUNT(*) FROM CLIENT WHERE CLIENT IN ('new','in_progress')"),
        "sum_new_idr": (one("SELECT COALESCE(SUM(price_idr),0) FROM CLIENT WHERE CLIENT='new'") or 0),
        "sum_all_idr": (one("SELECT COALESCE(SUM(price_idr),0) FROM CLIENT") or 0),
        "CLIENT": one("SELECT COUNT(*) FROM CLIENT"),
        "CLIENT": one("SELECT COUNT(*) FROM CLIENT WHERE active=1"),
        "CLIENT": one("SELECT COUNT(*) FROM client_CLIENT"),
    }
