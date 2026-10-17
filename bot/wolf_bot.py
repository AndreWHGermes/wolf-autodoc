"""Wolf AutoDoc Telegram bot — long-polling.

Зависимости: только стандартная библиотека + sqlite3 из core/db.py.
Бот (@Wolf_AutoDoc_bot) принимает заявки от разрешённых менеджеров,
создаёт клиента + заявку в Wolf CRM, рассылает уведомления админам.
Также поддерживает /invitemanager, /inviteadmin, /list, /whoami, /remove.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = "/opt/wolf_v2/data/wolf.db"   # единая база системы
BASE_URL = "http://103.90.75.37"   # через nginx (порт 80), ссылки работают без порта
INVITE_TTL_MIN = 120
POLL_TIMEOUT = 30
LOG_PATH = Path("/opt/wolf_v2/logs/wolf_bot.log")

# Корень проекта в sys.path — иначе `from core.…` в командах бота падает
# с «No module named 'core'» (Python кладёт в path только папку скрипта, /opt/wolf_v2/bot).
_PROJECT_ROOT = "/opt/wolf_v2"
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,          # чужие логгеры (fontTools/weasyprint) не забивают файл
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("wolf_bot").setLevel(logging.INFO)
log = logging.getLogger("wolf_bot")

# Сопроводительные файлы заявки (текст заявки для Google Drive)
APP_FILES_DIR = Path("/opt/wolf_v2/data/app_files")


# ---------- DB ----------

def _record_kind(conn):
    """Пометка новых записей: 'test' пока идёт обкатка, иначе None (рабочая).

    Управляется настройкой record_mode (scripts/mark_records.py mode test|prod).
    """
    row = conn.execute("SELECT value FROM settings WHERE key='record_mode'").fetchone()
    return ((row[0] if row else "") or "").strip() or None


def db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_setting(key: str, default: str = "") -> str:
    row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def bot_token() -> str:
    return get_setting("bot_token", "")


# ---------- Telegram HTTP ----------

def tg(method: str, params: dict | None = None, files: dict | None = None) -> dict:
    """Call Telegram Bot API. Returns parsed JSON. params may include 'data' for sendMessage."""
    token = bot_token()
    if not token:
        raise RuntimeError("bot_token не задан в settings")
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        # multipart — редко нужно, на будущее
        import io
        boundary = "----wolf" + secrets.token_hex(8)
        body = io.BytesIO()
        for k, v in (params or {}).items():
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for fname, (filename, content) in files.items():
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{fname}\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
            body.write(content)
            body.write(b"\r\n")
        body.write(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(url, data=body.getvalue(),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        data = urllib.parse.urlencode(params or {}).encode()
        req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def send(chat_id: int | str, text: str, reply_markup: dict | None = None,
         parse_mode: str | None = None) -> dict:
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    if parse_mode:
        params["parse_mode"] = parse_mode
    try:
        res = tg("sendMessage", params)
        log.info("send → chat=%s ok=%s (%d симв.)",
                 chat_id, res.get("ok"), len(text))
        return res
    except Exception as exc:
        log.error("send → chat=%s FAILED: %s", chat_id, exc)
        raise


# ---------- helpers ----------

def fmt_dt(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts.replace("Z", "")).strftime("%d.%m %H:%M")
    except Exception:
        return ts


def find_user(telegram_id: str) -> sqlite3.Row | None:
    return db().execute(
        "SELECT * FROM bot_managers WHERE telegram_id=?", (telegram_id,)).fetchone()


def user_role(telegram_id: str) -> str:
    """manager | admin | both | blocked | ''"""
    row = find_user(telegram_id)
    return row["role"] if row else ""


def is_privileged(telegram_id: str) -> bool:
    return user_role(telegram_id) in ("admin", "both")


def all_admins() -> list[sqlite3.Row]:
    return db().execute(
        "SELECT * FROM bot_managers WHERE role IN ('admin','both')").fetchall()


# ---------- /start и приглашения ----------

WELCOME_ADMIN = (
    "👋 Привет, {name}.\n\n"
    "Вы администратор Wolf AutoDoc.\n"
    "Сайт: {base}\n"
    "Сюда будут приходить уведомления о новых заявках от менеджеров.\n\n"
    "Команды:\n"
    "/whoami — кто я\n"
    "/list — все менеджеры и админы\n"
    "/invitemanager — пригласить менеджера\n"
    "/inviteadmin — пригласить администратора\n"
    "/remove <telegram_id> — удалить человека\n"
    "/help — эта справка"
)

WELCOME_MANAGER = (
    "👋 Привет, {name}.\n\n"
    "Вы менеджер Wolf AutoDoc.\n"
    "Присылайте заявки клиента — можно в СВОБОДНОЙ форме:\n"
    "карточку из Kommo, текст из WhatsApp, пересланное сообщение.\n"
    "Бот сам разберёт данные и заполнит карточку клиента.\n\n"
    "Главное — чтобы было понятно ФИО и какой продукт нужен\n"
    "(C1, E33G, D12, бридж, конверсия).\n\n"
    "Можно и по шаблону — {template}\n\n"
    "Бот ответит «Заявка #N принята».\n"
    "Команда /help — подробности"
)

APPLICATION_TEMPLATE = """/new
ФИО полностью: Иванов Иван Иванович
ФИО латиницей: Ivanov Ivan
Дата рождения: 1985-06-12
Пол: М
Гражданство: РФ
Паспорт серия: 45 04
Паспорт номер: 123456
Кем выдан: ОВД Тверское г. Москвы
Дата выдачи: 2005-08-20
Срок действия: 2025-08-20
ИНН: 7711223344
Телефон: +79001234567
Telegram: @username
Email: ivanov@example.com
Адрес регистрации: г. Москва, ул. Тверская, д. 1, кв. 23
Адрес проживания: г. Москва, ул. Тверская, д. 1, кв. 23
Компания: ООО «Ромашка»
Должность: Senior Developer
Зарплата: 250000 RUB/мес
Банк: Т-Банк
Название продукта: Виза C1
Стоимость IDR: 4500000
Google Drive клиента: https://drive.google.com/drive/folders/...
Комментарий: срочно, вылет 14.09.2026"""


def make_invite(role: str, created_by_tg: str) -> str:
    code = secrets.token_urlsafe(24)
    now = datetime.now()
    expires = now + timedelta(minutes=INVITE_TTL_MIN)
    creator = find_user(created_by_tg)
    conn = db()
    conn.execute(
        "INSERT INTO invites (code, role, created_by, created_at, expires_at) "
        "VALUES (?,?,?,?,?)",
        (code, role, creator["id"] if creator else None,
         now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")))
    conn.commit()
    return code


def consume_invite(code: str, telegram_id: str) -> sqlite3.Row | None:
    conn = db()
    row = conn.execute("SELECT * FROM invites WHERE code=?", (code,)).fetchone()
    if not row:
        return None
    if row["used_at"]:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.now() > expires:
        return None
    conn.execute(
        "UPDATE invites SET used_by_tg_id=?, used_at=? WHERE id=?",
        (telegram_id, datetime.now().isoformat(timespec="seconds"), row["id"]))
    conn.commit()
    return row


# ---------- парсер заявки ----------

FIELD_MAP = {
    "фио полностью": "full_name",
    "фио": "full_name",
    "фио латиницей": "full_name_latin",
    "дата рождения": "birth_date",
    "пол": "gender",
    "гражданство": "citizenship",
    "паспорт серия": "passport_series",
    "паспорт номер": "passport_number",
    "паспорт": "passport_number",
    "кем выдан": "passport_issued_by",
    "дата выдачи": "passport_issue_date",
    "срок действия": "passport_expiry",
    "инн": "inn",
    "телефон": "phone",
    "telegram": "telegram_username",
    "@": "telegram_username",
    "email": "email",
    "адрес регистрации": "address_reg",
    "адрес проживания": "address_live",
    "адрес": "address_reg",
    "компания": "company_name",
    "должность": "position",
    "зарплата": "salary_amount",
    "банк": "bank_name",
    "название продукта": "product_name",
    "продукт": "product_name",
    "стоимость idr": "price_idr",
    "сумма idr": "price_idr",
    "google drive клиента": "gdrive_url",
    "google drive": "gdrive_url",
    "drive": "gdrive_url",
    "комментарий": "comment",
}


def parse_application(text: str) -> dict:
    """Парсит многострочный текст вида 'Метка: значение' в dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line and "：" not in line:
            continue
        sep = ":" if ":" in line else "："
        label, _, value = line.partition(sep)
        label = label.strip().lower().rstrip(" .").rstrip()
        value = value.strip()
        if not value:
            continue
        key = FIELD_MAP.get(label)
        if key:
            out[key] = value
    return out


def find_product_id(name: str) -> int | None:
    """Ищет продукт по коду (C1, E33G-NEW) или по подстроке в названии/коде.

    Строгие правила (приоритет):
    1) точное совпадение по коду (E33G-NEW, E33G-EXT, C1, C1-EXT)
    2) «продление» в тексте → EXT
    3) иначе → NEW
    """
    if not name:
        return None
    n = name.strip().lower()
    has_ext = any(w in n for w in ("продление", "продлить", "extension", "ext", "renewal"))
    # 1) точный код
    row = db().execute(
        "SELECT id, code FROM products WHERE lower(code)=? LIMIT 1", (n,)).fetchone()
    if row:
        return row["id"]
    # 2) код без пробелов
    short = "".join(ch for ch in n if ch.isalnum())
    row = db().execute(
        "SELECT id FROM products WHERE lower(code)=? LIMIT 1", (short,)).fetchone()
    if row:
        return row["id"]
    # 2.5) синонимы из свободного текста: «BRIDGE», «мост» → BRIDGING;
    #      «конверсия» → CONV; «кунджунган» → C1; «китас» → E33G-NEW и т.д.
    try:
        from bot.ai_parser import detect_product
        code = detect_product(n)
        if code:
            row = db().execute("SELECT id FROM products WHERE code=? LIMIT 1", (code,)).fetchone()
            if row:
                return row["id"]
    except Exception:
        pass
    # 3) NEW vs EXT — различение
    if "e33g" in n:
        if has_ext:
            row = db().execute(
                "SELECT id FROM products WHERE code='E33G-EXT' LIMIT 1").fetchone()
        else:
            row = db().execute(
                "SELECT id FROM products WHERE code='E33G-NEW' LIMIT 1").fetchone()
        if row:
            return row["id"]
    if "c1" in n and not "c1-ext" in n and not "c1ext" in n:
        if has_ext:
            row = db().execute(
                "SELECT id FROM products WHERE code='C1-EXT' LIMIT 1").fetchone()
        else:
            row = db().execute(
                "SELECT id FROM products WHERE code='C1' LIMIT 1").fetchone()
        if row:
            return row["id"]
    # 4) общий LIKE
    row = db().execute(
        "SELECT id FROM products WHERE lower(name) LIKE ? OR lower(code) LIKE ? "
        "ORDER BY length(name) LIMIT 1",
        (f"%{n}%", f"%{n}%")).fetchone()
    if row:
        return row["id"]
    # 5) последнее слово
    parts = n.split()
    if len(parts) > 1:
        last = parts[-1]
        row = db().execute(
            "SELECT id FROM products WHERE lower(code) LIKE ? OR lower(name) LIKE ? "
            "ORDER BY length(name) LIMIT 1",
            (f"%{last}%", f"%{last}%")).fetchone()
        if row:
            return row["id"]
    return None


def split_fio(full: str) -> tuple[str, str, str]:
    parts = (full or "").split()
    surname = parts[0] if len(parts) >= 1 else ""
    name = parts[1] if len(parts) >= 2 else ""
    patronymic = " ".join(parts[2:]) if len(parts) >= 3 else ""
    return surname, name, patronymic


def _bank_allows(template_code: str, bank: str) -> bool:
    """Пропускать ли шаблон для выбранного банка.

    Банковские справки делаются ТОЛЬКО для банка клиента: либо Тинькофф,
    либо Сбербанк — оба одновременно не нужны.
    """
    c = (template_code or "").lower()
    if "tbank" in c or "tinkoff" in c:
        return bank != "sber"
    if "sber" in c:
        return bank == "sber"
    return True


def application_text_path(app_id: int) -> Path:
    """Путь обычного текстового файла с сопроводительным текстом заявки."""
    return APP_FILES_DIR / ("app_" + str(app_id)) / "Заявка.txt"


def _write_application_text(app_id: int, body: str, form: dict, user) -> None:
    """Пишет «Заявка.txt»: всё, что менеджер написал в свободной форме, плюс шапка.

    Файл кладём вместе с готовыми документами на Google Drive — администратор
    открывает папку и видит, что именно было в заявке (ускорение, партнёр, сроки).
    """
    p = application_text_path(app_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    _cl = db().execute("SELECT * FROM clients WHERE id=(SELECT client_id FROM applications WHERE id=?)",
                       (app_id,)).fetchone()
    _prod = db().execute("SELECT code, name FROM products WHERE id=(SELECT product_id FROM applications WHERE id=?)",
                         (app_id,)).fetchone()
    lines = [
        "ЗАЯВКА №" + str(app_id),
        "=" * 60,
        "Клиент: " + " ".join(x for x in [(_cl["surname"] if _cl else ""), (_cl["name"] if _cl else ""),
                                          (_cl["patronymic"] if _cl else "")] if x).strip(),
        "Клиент (латиницей): " + ((_cl["full_name_latin"] if _cl else "") or "—"),
        "Продукт: " + ((_prod["code"] + " — " + (_prod["name"] or "")) if _prod else "не определён"),
        "Стоимость: " + (str(form.get("price_idr")) + " IDR" if form.get("price_idr") else "не указана"),
        "Ссылка на Google Drive: " + ((form.get("gdrive_url") or form.get("gdrive_folder_url") or "—")),
        "Менеджер: " + ((user["full_name"] or user["username"] or str(user["telegram_id"])) if user else "—"),
        "Дата приёма: " + datetime.now().strftime("%d.%m.%Y %H:%M"),
        "",
        "КОММЕНТАРИЙ (свободный текст заявки):",
        "-" * 60,
        (form.get("comment") or "—"),
        "",
        "ИСХОДНОЕ СООБЩЕНИЕ МЕНЕДЖЕРА:",
        "-" * 60,
        (body or "").strip() or "—",
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")

DUP_WINDOW_HOURS = 12
LAST_DUPLICATE = None      # заполняется create_application, если заявка уже была


def _duplicate_application(conn, client_id: int, product_id: int, gdrive_url: str):
    """Та же заявка, присланная повторно: тот же клиент, продукт и папка Диска.

    17.10.2026 менеджер дважды прислал одну и ту же заявку (117 и 118): вышло
    две заявки на одного клиента, два комплекта в одну папку на Диске.
    Повтор в пределах 12 часов считаем тем же делом.
    """
    if not client_id or not gdrive_url:
        return None
    try:
        return conn.execute(
            "SELECT id, status FROM applications WHERE client_id=? "
            "AND COALESCE(product_id,0)=COALESCE(?,0) AND COALESCE(gdrive_url,'')=? "
            "AND status IN ('new','in_work','filled','sent') "
            "AND created_at > datetime('now', ?) ORDER BY id DESC LIMIT 1",
            (client_id, product_id, gdrive_url, '-%d hours' % DUP_WINDOW_HOURS)).fetchone()
    except Exception:                                  # noqa: BLE001
        return None


def create_application(form: dict, from_user: sqlite3.Row,
                       autofill: bool = False, raw_text: str = "") -> tuple[int, int]:
    """Создаёт клиента и заявку. Возвращает (application_id, client_id)."""
    global LAST_DUPLICATE
    LAST_DUPLICATE = None
    conn = db()
    full = form.get("full_name") or ""
    # Если LLM уже разложил ФИО по частям — используем их напрямую,
    # иначе (жёсткий шаблон) разбираем строку full_name.
    if form.get("surname") or form.get("name"):
        surname = form.get("surname") or ""
        name = form.get("name") or ""
        patronymic = form.get("patronymic") or ""
    else:
        surname, name, patronymic = split_fio(full)
    # латиница: если явно не задана, а есть только surname/name — собираем
    if not form.get("full_name_latin") and form.get("surname") and form.get("name"):
        form["full_name_latin"] = f'{form["surname"]} {form["name"]}'.strip()
    phone = form.get("phone") or ""
    tg_username = (form.get("telegram_username") or "").lstrip("@")
    # ищем существующего клиента по ФИО + телефону
    existing = None
    if surname:
        existing = conn.execute(
            "SELECT * FROM clients WHERE surname=? AND name=? LIMIT 1",
            (surname, name or "")).fetchone()
    if not existing and phone:
        existing = conn.execute(
            "SELECT * FROM clients WHERE phone=? LIMIT 1", (phone,)).fetchone()
    if existing:
        client_id = existing["id"]
        # Дозаполняем пустые поля карточки данными из новой заявки.
        # Непустые значения не трогаем — админ мог поправить вручную.
        _updable = ["full_name_latin", "gender", "citizenship", "birth_date",
                    "patronymic",
                    "passport_series", "passport_number", "passport_issued_by",
                    "passport_issue_date", "passport_expiry", "inn", "email",
                    "address_reg", "address_live", "company_name", "position",
                    "salary_amount", "bank_name", "gdrive_folder_url", "notes"]
        _sets, _vals = [], []
        _incoming = {"phone": phone, "telegram_username": tg_username,
                     "gdrive_folder_url": form.get("gdrive_folder_url") or form.get("gdrive_url")}
        for k in _updable:
            _v = _incoming.get(k) if k in _incoming else form.get(k)
            if _v:
                _sets.append(f"{k}=COALESCE(NULLIF({k},''), ?)")
                _vals.append(_v)
        _sets.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE clients SET {', '.join(_sets)} WHERE id=?",
                     (*_vals, client_id))
        log.info("clients#%s дозаполнен: %s", client_id,
                 ", ".join(s.split("=")[0] for s in _sets[:-1]))
    else:
        cur = conn.execute(
            "INSERT INTO clients (surname, name, patronymic, full_name_latin, gender, "
            "citizenship, birth_date, passport_series, passport_number, passport_issued_by, "
            "passport_issue_date, passport_expiry, inn, phone, telegram_username, email, "
            "address_reg, address_live, company_name, position, salary_amount, bank_name, "
            "gdrive_folder_url, notes, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', "
            "datetime('now'), datetime('now'))",
            (surname, name, patronymic,
             form.get("full_name_latin") or "",
             form.get("gender") or "",
             form.get("citizenship") or "",
             form.get("birth_date") or "",
             form.get("passport_series") or "",
             form.get("passport_number") or "",
             form.get("passport_issued_by") or "",
             form.get("passport_issue_date") or "",
             form.get("passport_expiry") or "",
             form.get("inn") or "",
             phone,
             tg_username,
             form.get("email") or "",
             form.get("address_reg") or "",
             form.get("address_live") or "",
             form.get("company_name") or "",
             form.get("position") or "",
             form.get("salary_amount") or "",
             form.get("bank_name") or "",
             form.get("gdrive_url") or form.get("gdrive_folder_url") or "",
             form.get("notes") or ""))
        client_id = cur.lastrowid
        _kind = _record_kind(conn)
        if _kind:
            conn.execute("UPDATE clients SET record_kind=? WHERE id=?", (_kind, client_id))

    price_idr = 0
    if form.get("price_idr"):
        # LLM может вернуть число или строку «11,9 млн» / «11.9M» — нормализуем
        _raw_price = form["price_idr"]
        if isinstance(_raw_price, (int, float)):
            price_idr = int(_raw_price)
        else:
            _s = str(_raw_price).lower().replace(" ", "")
            digits = "".join(ch for ch in _s if ch.isdigit())
            price_idr = int(digits) if digits else 0
            if "млн" in _s or "mln" in _s or "m" in _s.replace("usd", "").replace("idr", ""):
                price_idr *= 1_000_000

    product_id = find_product_id(form.get("product_name") or "")
    # Ссылка на папку клиента приходит под разными именами: бот-парсер пишет
    # gdrive_folder_url, форма — gdrive_url. Берём любую, иначе автораэбор
    # документов с Google Диска не запускается и заявка остаётся без файлов.
    _gdrive_url = (form.get("gdrive_url") or form.get("gdrive_folder_url") or "").strip()
    _dup = _duplicate_application(conn, client_id, product_id, _gdrive_url)
    if _dup:
        log.info("заявка уже принята: #%s (%s), клиент #%s, папка %s — повторно не создаю",
                 _dup["id"], _dup["status"], client_id, _gdrive_url)
        LAST_DUPLICATE = {"app_id": int(_dup["id"]), "status": _dup["status"]}
        conn.commit()
        return int(_dup["id"]), int(client_id)
    cur = conn.execute(
        "INSERT INTO applications (client_id, product_id, status, source, "
        "comment, brief, price_idr, gdrive_url, raw_payload, raw_message, bot_manager_id, created_at) "
        "VALUES (?,?, 'new', 'telegram', ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (client_id, product_id,
         form.get("comment") or "",
         # текст заявки сразу становится комментарием сборки: должность, сфера и прочее,
         # что менеджер написал в боте, применяется к документам заявки без переноса руками
         (form.get("comment") or form.get("notes") or ""),
         price_idr,
         _gdrive_url,
         json.dumps(form, ensure_ascii=False),
         # точь-в-точь текст заявки, как его прислал менеджер в Telegram:
         # уходит отдельным txt-файлом в папку документов на Google Диске
         (raw_text or "").strip(),
         from_user["id"]))
    app_id = cur.lastrowid
    _kind = _record_kind(conn)
    if _kind:
        conn.execute("UPDATE applications SET record_kind=? WHERE id=?", (_kind, app_id))

    # --- банк клиента: определяем по документам в его папке Google Drive ---
    bank = ""
    _gd = form.get("gdrive_folder_url") or form.get("gdrive_url") or ""
    try:
        from bot.ai_parser import detect_bank_from_drive, bank_details_from_drive
        bank = detect_bank_from_drive(_gd)
        if bank:
            conn.execute("UPDATE clients SET bank_name=? WHERE id=?",
                         (bank.upper(), client_id))
            conn.commit()
            log.info("банк клиента #%s → %s", client_id, bank.upper())
        # реквизиты из банковской справки клиента (счёт, договор, карта, баланс,
        # паспорт) — чтобы справка формировалась сразу заполненной
        det = bank_details_from_drive(_gd, bank) if _gd else {}
        if det:
            _real = {r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()}
            _sets, _vals = [], []
            for k, v in det.items():
                if k in ("full_name_ru", "doc_date") or k not in _real:
                    continue
                _sets.append(f"{k}=COALESCE(NULLIF(?,''), {k})")
                _vals.append(v)
            if _sets:
                conn.execute(
                    f"UPDATE clients SET {', '.join(_sets)} WHERE id=?",
                    (*_vals, client_id))
                conn.commit()
                log.info("реквизиты клиента #%s: %s", client_id,
                         ", ".join(k for k in det if k not in ("full_name_ru", "doc_date")))
    except Exception as exc:
        log.warning("разбор документов Google Drive не удался: %s", exc)

    # создаём application_documents для шаблонов продукта.
    # Банковские справки — только для банка клиента (Тинькофф ИЛИ Сбер, не оба).
    if product_id:
        rows = conn.execute(
            "SELECT t.id, t.code FROM templates t "
            "JOIN product_documents pd ON pd.template_id=t.id "
            "WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged')",
            (product_id,)).fetchall()
        # Письма в иммиграцию идут ровно одним комплектом: Ngurah Rai или
        # Denpasar — по адресу проживания клиента. Второй вариант не создаём.
        from services import immigration_office as _io
        _office = (_io.resolve_for_client(conn, client_id) or {}).get("office")
        for r in rows:
            # Лишний вариант письма не выбрасываем, а помечаем крестиком:
            # в миниатюрах он виден с причиной, в работу не идёт (rejected).
            _rejected = not _io.office_allows(r["code"], _office)
            _why = ("исключено автоматически: адрес клиента — зона %s"
                    % _io.office_name(_office)) if _rejected else None
            if _rejected:
                log.info("шаблон %s исключён — комплект %s (адрес клиента)",
                         r["code"], _office)
            # Банк клиента определён — берём справку только этого банка.
            # Банк ещё не определён — даём ОБА варианта (Тинькофф и Сбер),
            # администратор выберет нужный кнопкой «Проверен».
            if bank and not _bank_allows(r["code"], bank):
                log.info("шаблон %s пропущен — банк клиента %s",
                         r["code"], (bank or "—").upper())
                continue
            conn.execute(
                "INSERT INTO application_documents (application_id, template_id, status, "
                "values_json, rendered_at, error) VALUES (?,?,?,?, datetime('now'), ?)",
                (app_id, r["id"], "rejected" if _rejected else "pending",
                 json.dumps(form, ensure_ascii=False), _why))
    conn.commit()
    # Разбор документов клиента из Google Drive — автоматически, сразу после
    # приёма заявки. Раньше приходилось жать «Разобрать документы (нейросеть)»
    # в карточке; теперь данные клиента уже вытащены, когда её открывают.
    # Заявка принята — дальше она идёт в ОЧЕРЕДЬ, а не запускается сразу.
    # Раньше бот немедленно поднимал разбор Диска и предподготовку, и три заявки
    # подряд давали три тяжёлых процесса одновременно — сервер вешало. Теперь
    # тяжёлую работу (сканы, распознавание, сборку) делает один воркер очереди,
    # строго по одной заявке; менеджер при этом сразу получает подтверждение.
    try:
        import sys as _sys
        _sys.path.insert(0, "/opt/wolf_v2/scripts")
        import auto_queue as _auto_queue
        _auto_queue.add(app_id, quiet=True)
        from services import app_steps as _steps
        _steps.step(app_id, 'received', 'ok', 'заявка принята из бота, поставлена в очередь', actor='бот')
        log.info("заявка #%s поставлена в очередь автоподготовки", app_id)
    except Exception as _exc:  # noqa: BLE001
        log.warning("не удалось поставить заявку #%s в очередь: %s", app_id, _exc)

    # PDF генерируем отдельно и позже (это ~5 сек на 5 документов).
    # Если генерировать здесь, бот молчит всё это время и менеджер думает,
    # что заявка не принята. Поэтому ответ уходит раньше — см. handle_update.
    if autofill:
        _autofill_pdfs(app_id, client_id, product_id)
    return app_id, client_id


def _apply_product(app_id: int, product_id: int) -> None:
    """Проставляет продукт заявке и создаёт документы под него.
    Аналог app_change_product из админки — для вызова из бота."""
    import re as _re
    conn = db()
    prod = conn.execute("SELECT id, code, description FROM products WHERE id=?",
                        (product_id,)).fetchone()
    if not prod:
        return
    price = 0
    desc = prod["description"] or ""
    m = _re.search(r"price_idr\s*=\s*(\d+)", desc)
    if m:
        price = int(m.group(1))
    # реквизиты для шаблонов (bank name и пр.) — из карточки клиента
    row = conn.execute(
        "SELECT client_id FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row:
        return
    client_id = row["client_id"]
    # Тот же продукт — значит ничего не меняем: документы и галочки остаются на месте.
    _cur = conn.execute("SELECT product_id FROM applications WHERE id=? ", (app_id,)).fetchone()
    if _cur and _cur["product_id"] == prod["id"]:
        return
    conn.execute("UPDATE applications SET product_id=?, price_idr=? WHERE id=?",
                 (prod["id"], price, app_id))
    # Галочки и отправленные документы бот не стирает: см. админку.
    conn.execute("DELETE FROM application_documents WHERE application_id=? "
                 "AND IFNULL(status,'') NOT IN ('verified','sent')", (app_id,))
    client_row = conn.execute("SELECT bank_name FROM clients WHERE id=?",
                              (client_id,)).fetchone()
    bank = (client_row["bank_name"] or "").lower() if client_row else ""
    if not bank:
        cl = conn.execute("SELECT gdrive_folder_url FROM clients WHERE id=?",
                          (client_id,)).fetchone()
        try:
            from bot.ai_parser import detect_bank_from_drive
            bank = detect_bank_from_drive(cl["gdrive_folder_url"] if cl else "")
        except Exception:
            bank = ""
    templates = conn.execute(
        """SELECT t.id, t.code FROM product_documents pd
             JOIN templates t ON t.id=pd.template_id
            WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged') ORDER BY t.id""", (product_id,)).fetchall()
    now = datetime.now().isoformat(timespec="seconds")
    # Комплект писем в иммиграцию — по адресу клиента: Ngurah Rai либо Denpasar.
    from services import immigration_office as _io
    _office = (_io.resolve_for_client(conn, client_id) or {}).get("office")
    for t in templates:
        _rejected = not _io.office_allows(t["code"], _office)
        if _rejected:
            log.info("_apply_product: шаблон %s исключён (комплект %s)",
                     t["code"], _office)
        if not _bank_allows(t["code"], bank):
            log.info("_apply_product: шаблон %s пропущен (банк %s)",
                     t["code"], (bank or "—").upper())
            continue
        conn.execute(
            """INSERT INTO application_documents
                 (application_id, template_id, status, rendered_at, error)
               VALUES (?,?,?,?,?)""",
            (app_id, t["id"], "rejected" if _rejected else "pending", now,
             ("исключено автоматически: адрес клиента — зона %s"
              % _io.office_name(_office)) if _rejected else None))
    conn.commit()
    log.info("_apply_product: заявка #%s → продукт %s, документов=%d",
             app_id, prod["code"], len(templates))
    _autofill_pdfs(app_id, client_id, product_id)


def _with_article(role: str) -> str:
    """«social media producer» → «a social media producer», «engineer» → «an engineer»."""
    r = (role or "").strip()
    if not r:
        return ""
    low = r.lower()
    if low.startswith(("a ", "an ", "the ")):
        return r
    # слова, где первая гласная читается как согласная
    if low.split()[0] in ("university", "user", "one", "european"):
        return "a " + r
    return ("an " if low[0] in "aeiou" else "a ") + r


def _autofill_pdfs(app_id: int, client_id: int, product_id: int) -> None:
    """Генерирует PDF для всех pending-документов заявки с данными клиента.
    Ошибки не критичны — остаются в application_documents.error.
    """
    import re
    from datetime import datetime as _dt
    from pathlib import Path
    conn = db()
    docs = conn.execute(
        """SELECT ad.id, ad.template_id, t.code, t.html_path, ad.values_json
             FROM application_documents ad
             JOIN templates t ON t.id=ad.template_id
            WHERE ad.application_id=? AND ad.status='pending'""",
        (app_id,)).fetchall()
    client = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        return
    simple_map = {
        "full_name": f'{(client["surname"] or "")} {(client["name"] or "")}'.strip(),
        "surname": client["surname"] or "",
        "name": client["name"] or "",
        "patronymic": client["patronymic"] or "",
        "birth_date": client["birth_date"] or "",
        "gender": client["gender"] or "",
        "citizenship": client["citizenship"] or "",
        "passport_series": client["passport_series"] or "",
        "passport_number": client["passport_number"] or "",
        "passport_issued_by": client["passport_issued_by"] or "",
        "passport_issue_date": client["passport_issue_date"] or "",
        "passport_expiry": client["passport_expiry"] or "",
        "phone": client["phone"] or "",
        "email": client["email"] or "",
        "address_reg": client["address_reg"] or "",
        "address_live": client["address_live"] or "",
        "company_name": client["company_name"] or "",
        "position": client["position"] or "",
        "salary_amount": client["salary_amount"] or "",
        "bank_name": client["bank_name"] or "",
        "inn": client["inn"] or "",
        # --- банковские реквизиты (из карточки клиента, заполняются агентом
        #     при разборе справки на Google Drive) ---
        "client_name": ' '.join(x for x in [client["surname"] or "",
                                             client["name"] or "",
                                             client["patronymic"] or ""] if x),
        "for_name": ' '.join(x for x in [client["surname"] or "",
                                          client["name"] or "",
                                          client["patronymic"] or ""] if x),
        "doc_no": (client["doc_no"] if "doc_no" in client.keys() else "") or "",
        "ref_no": (client["ref_no"] if "ref_no" in client.keys() else "") or "",
        "card_mask": (client["card_mask"] if "card_mask" in client.keys() else "") or "",
        "contract_no": (client["contract_no"] if "contract_no" in client.keys() else "") or "",
        "account_no": (client["account_no"] if "account_no" in client.keys() else "") or "",
        "balance_rub": (client["balance_rub"] if "balance_rub" in client.keys() else "") or "",
        "balance_date": (client["balance_date"] if "balance_date" in client.keys() else "") or "",
        # должность контрактора (раздел 1 Work Agreement) — с артиклем a/an
        "profession": _with_article((client["position"] if "position" in client.keys() else "") or ""),
        "position": (client["position"] if "position" in client.keys() else "") or "",
    }
    _bal_date = (client["balance_date"] if "balance_date" in client.keys() else "") or ""
    simple_map["doc_date"] = _bal_date
    _cdate = (client["contract_date"] if "contract_date" in client.keys() else "") or ""
    simple_map["contract_date"] = _cdate
    # ref_no: у Т-Банка это номер справки; если отдельно не задан — берём doc_no
    if not simple_map.get("ref_no"):
        simple_map["ref_no"] = simple_map.get("doc_no", "")

    def _minus_months(d: str, months: int) -> str:
        """ДД.ММ.ГГГГ минус N месяцев (без dateutil)."""
        import calendar
        try:
            dd, mm, yy = (int(x) for x in d.split("."))
        except Exception:
            return ""
        mm -= months
        while mm <= 0:
            mm += 12
            yy -= 1
        dd = min(dd, calendar.monthrange(yy, mm)[1])
        return f"{dd:02d}.{mm:02d}.{yy:04d}"
    for d in docs:
        code = d["code"]
        html_path = d["html_path"]
        html_file = Path(html_path) if html_path else None
        if not html_file or not html_file.exists():
            html_file = Path('/opt/wolf_v2/data/templates') / code / "template.html"
        if not html_file.exists():
            conn.execute(
                "UPDATE application_documents SET error=? WHERE id=?",
                ("HTML-шаблон не найден: " + code, d["id"]))
            continue
        values = dict(simple_map)
        # период банковской справки: 3 или 12 месяцев назад от даты баланса
        if "bank_statement" in code and _bal_date:
            _months = 12 if "_12m" in code else 3
            values["period_to"] = _bal_date
            values["period_from"] = _minus_months(_bal_date, _months)
        try:
            html = html_file.read_text(encoding="utf-8")
            # описание занятий контрактора (раздел 1 Remote Work Agreement):
            # формируется по должности из карточки клиента
            if "services_list" in html and not values.get("services_list"):
                # 1) приоритет — сохранённая версия (админ мог отредактировать в карточке)
                _saved = {}
                try:
                    if d["values_json"]:
                        _saved = json.loads(d["values_json"]) or {}
                except Exception:
                    _saved = {}
                if _saved.get("services_list"):
                    values["services_list"] = _saved["services_list"]
                    log.info("services_list: использована сохранённая версия (правка админа)")
                else:
                    # 2) иначе — генерируем по должности из карточки клиента
                    try:
                        from bot.ai_parser import generate_duties, duties_to_plain
                        _pos = (client["position"] if "position" in client.keys() else "") or ""
                        _co = (client["company_name"] if "company_name" in client.keys() else "") or ""
                        values["services_list"] = duties_to_plain(
                            generate_duties(_pos, _co, 4))
                        log.info("services_list: «%s» → %d пунктов", _pos[:40],
                                 values["services_list"].count("•"))
                    except Exception as _e:
                        log.warning("services_list не сформирован: %s", _e)
            # пункты храним обычным текстом (чтобы админ правил в форме),
            # а в HTML превращаем переводы строк в <br>
            _html_values = dict(values)
            if _html_values.get("services_list"):
                _html_values["services_list"] = (str(_html_values["services_list"])
                                                 .replace("\r\n", "\n").replace("\n", "<br>"))
            # банковские справки — строго на английском: кириллицу транслитерируем
            if "bank_statement" in code or "1year" in code.lower():
                try:
                    from bot.ai_parser import (translit_ru, amount_in_words_en,
                                           format_amount_en, parse_amount)
                    for _k in list(_html_values.keys()):
                        _v = _html_values[_k]
                        if isinstance(_v, str) and any(
                                "а" <= c.lower() <= "я" or c.lower() == "ё" for c in _v):
                            _html_values[_k] = translit_ru(_v)
                    # сумма: формат «1 770 300,00» + прописью
                    _bal = _html_values.get("balance_rub")
                    if _bal:
                        try:
                            if parse_amount(_bal) > 0:
                                _html_values["balance_words"] = amount_in_words_en(_bal)
                                _html_values["balance_rub"] = format_amount_en(_bal)
                        except Exception:
                            pass
                except Exception as _e:
                    log.warning("транслитерация не удалась: %s", _e)
            filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                            lambda m: str(_html_values.get(m.group(1)) or m.group(0)), html)
            out_pdf = Path('/opt/wolf_v2/data/renders') / \
                f'{code}_app{app_id}_{_dt.now():%Y%m%d_%H%M%S}.pdf'
            tmp_html = html_file.parent / "filled.html"
            tmp_html.write_text(filled, encoding="utf-8")
            from core import pdf2html
            pdf2html.render_pdf(tmp_html, out_pdf)
            conn.execute(
                "UPDATE application_documents SET status=CASE WHEN status IN ('verified','sent') "
                "THEN status ELSE 'filled' END, pdf_path=?, "
                "values_json=?, error=NULL, rendered_at=datetime('now') WHERE id=?",
                (str(out_pdf), json.dumps(values, ensure_ascii=False), d["id"]))
        except Exception as exc:
            conn.execute(
                "UPDATE application_documents SET status='error', error=? WHERE id=?",
                (str(exc)[:300], d["id"]))
    conn.commit()


# ---------- команды ----------

HELP_TEXT = (
    "🤖 Wolf AutoDoc бот\n\n"
    "Если вы уже в системе — просто пишите заявки в формате:\n"
    "/new\nФИО полностью: ...\n...\n\n"
    "Команды:\n"
    "/start — войти/обновить приветствие\n"
    "/whoami — кто я\n"
    "/list — все менеджеры и админы\n"
    "/invitemanager — выписать ссылку-приглашение менеджера (30 мин)\n"
    "/inviteadmin — выписать ссылку-приглашение администратора (30 мин)\n"
    "/remove <telegram_id> — удалить человека\n"
    "/help — эта справка\n"
)


def cmd_start(chat_id: int, from_id: str, args: str, from_user) -> None:
    # /start login — пришли с сайта по кнопке «Войти через Telegram»
    if args.strip().lower() in ("login", "вход", "site", "site_login"):
        cmd_login(chat_id, from_id)
        return
    if args:
        # /start <код>
        row = consume_invite(args.strip(), from_id)
        if not row:
            send(chat_id, "❌ Ссылка-приглашение не найдена или истёк срок. "
                          "Попросите администратора выписать новую.")
            return
        # создаём запись в bot_managers
        u = from_user
        conn = db()
        existing = conn.execute(
            "SELECT id, role FROM bot_managers WHERE telegram_id=?", (from_id,)).fetchone()
        if existing:
            new_role = existing["role"]
            if row["role"] in ("admin", "manager"):
                if existing["role"] == row["role"]:
                    new_role = existing["role"]
                else:
                    new_role = "both"
            conn.execute(
                "UPDATE bot_managers SET username=?, full_name=?, role=?, "
                "source='invite', invited_by=?, updated_at=datetime('now') "
                "WHERE id=?",
                (u.get("username") or "", u.get("first_name") or "",
                 new_role, row["created_by"], existing["id"]))
        else:
            conn.execute(
                "INSERT INTO bot_managers (telegram_id, username, full_name, role, "
                "source, invited_by, created_at, updated_at) "
                "VALUES (?,?,?,?,'invite',?,datetime('now'),datetime('now'))",
                (from_id, u.get("username") or "", u.get("first_name") or "",
                 row["role"], row["created_by"]))
        conn.commit()
        role = row["role"]
        if role == "admin":
            send(chat_id, "✅ Вы добавлены как администратор. "
                          f"Сайт: {BASE_URL}/")
        elif role == "manager":
            tmpl = APPLICATION_TEMPLATE.replace("<", "&lt;").replace(">", "&gt;")
            send(chat_id,
                 "✅ Вы добавлены как менеджер.\n\n"
                 "Шаблон заявки (скопируйте и заполните):\n\n" + tmpl)
        # уведомляем создателя приглашения
        creator = conn.execute(
            "SELECT * FROM bot_managers WHERE id=?", (row["created_by"],)).fetchone()
        if creator:
            send(creator["telegram_id"],
                 f"✅ Приглашение использовано.\nДобавлен: {u.get('first_name') or ''} "
                 f"(@{u.get('username') or '—'}, id {from_id}) как {role}.")
        return
    # без кода
    user = find_user(from_id)
    if not user or user["role"] == "blocked":
        send(chat_id, "❌ Вы не зарегистрированы. Попросите администратора "
                      "выписать приглашение командой /invitemanager или /inviteadmin.")
        return
    if user["role"] in ("admin", "both"):
        pin_text = ("✅ Вы работаете в системе Wolf AutoDoc.\n"
                    "Ваша роль: 🛡 администратор.\n\n"
                    "Сайт: " + BASE_URL + "\n"
                    "Сюда приходят уведомления о новых заявках от менеджеров.\n\n"
                    "• /help — пример заявки\n"
                    "• /whoami — моя роль в системе\n"
                    "• /login — войти на сайт")
        msg = send(chat_id, pin_text)
        try:
            if msg.get("ok") and msg.get("result", {}).get("message_id"):
                tg("pinChatMessage",
                   {"chat_id": chat_id,
                    "message_id": msg["result"]["message_id"],
                    "disable_notification": True})
        except Exception as exc:
            log.warning("pin admin failed: %s", exc)
        send(chat_id, "👋 Привет, " + (user["full_name"] or user["username"] or "коллега") +
                      ". Вы администратор. Сообщение выше закреплено — там ссылка на сайт.")
    if user["role"] in ("manager", "both"):
        pin_text = ("✅ Вы работаете в системе Wolf AutoDoc.\n"
                    "Ваша роль: 👤 менеджер.\n\n"
                    "Пришлите заявку клиента — можно свободным текстом, например:\n"
                    "«Иван Петров, виза C1, 4 500 000 IDR,\n"
                    "папка https://drive.google.com/drive/folders/...»\n\n"
                    "Бот ответит «Заявка #N принята», а когда документы будут готовы — "
                    "пришлёт вам сообщение.\n\n"
                    "• /help — пример заявки\n"
                    "• /whoami — моя роль в системе")
        msg = send(chat_id, pin_text)
        try:
            if msg.get("ok") and msg.get("result", {}).get("message_id"):
                tg("pinChatMessage",
                   {"chat_id": chat_id,
                    "message_id": msg["result"]["message_id"],
                    "disable_notification": True})
        except Exception as exc:
            log.warning("pin manager failed: %s", exc)
        send(chat_id, "👋 Привет, " + (user["full_name"] or user["username"] or "коллега") +
                      ". Вы менеджер. Шаблон заявки закреплён выше — нажмите на закреп и "
                      "скопируйте, заполните и пришлите сюда.")


def set_bot_menu():
    """Устанавливает команды бота (видны при нажатии 'Menu' в чате) + кнопку меню."""
    commands = [
        {"command": "start",  "description": "Открыть приветствие"},
        {"command": "help",   "description": "Пример заявки"},
        {"command": "whoami", "description": "Моя роль в системе"},
    ]
    admin_commands = commands + [{"command": "login", "description": "Вход на сайт"}]
    try:
        # базовое меню — всем (менеджер входа на сайт не видит)
        tg("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
        # менеджерам — явно базовый набор (без «Вход на сайт»)
        rows_m = db().execute(
            "SELECT telegram_id FROM bot_managers WHERE role='manager'").fetchall()
        for r_ in rows_m:
            try:
                tg("setMyCommands", {
                    "commands": json.dumps(commands, ensure_ascii=False),
                    "scope": json.dumps({"type": "chat",
                                         "chat_id": int(r_["telegram_id"])})})
            except Exception as exc:
                log.warning("меню менеджера %s: %s", r_["telegram_id"], exc)
        # администраторам дополнительно «Вход на сайт»
        rows = db().execute(
            "SELECT telegram_id FROM bot_managers WHERE role IN ('admin','both')").fetchall()
        for r_ in rows:
            try:
                tg("setMyCommands", {
                    "commands": json.dumps(admin_commands, ensure_ascii=False),
                    "scope": json.dumps({"type": "chat",
                                         "chat_id": int(r_["telegram_id"])})})
            except Exception as exc:
                log.warning("меню для %s: %s", r_["telegram_id"], exc)
        tg("setChatMenuButton", {"menu_button": json.dumps({"type": "commands"})})
    except Exception as exc:
        log.warning("set_bot_menu failed: %s", exc)


def cmd_login(chat_id: int, from_id: str) -> None:
    """Выдаёт 6-значный код для входа на сайт. Доступно только admin/both."""
    u = find_user(from_id)
    if not u:
        send(chat_id, "❌ Вас нет в системе. Попросите ссылку-приглашение.")
        return
    if u["role"] not in ("admin", "both"):
        send(chat_id, "❌ Команда доступна только администраторам.")
        return
    try:
        # создаём код через ту же логику что и Wolf
        from core.auth import create_login_code
        code = create_login_code(from_id, ttl_seconds=180)
        send(chat_id,
             f"🔑 Вход на сайт Wolf AutoDoc\n\n"
             f"Нажмите кнопку ниже — и вы сразу окажетесь в системе.\n"
             f"Ссылка действует 3 минуты.",
             reply_markup={"inline_keyboard": [[
                 {"text": "🌐 Войти на сайт", "url": f"{BASE_URL}/auth/tg/{code}"}]]})
    except Exception as exc:
        log.error("cmd_login failed: %s", exc)
        send(chat_id, "❌ Ошибка генерации кода. Попробуйте ещё раз.")


ROLE_VERBOSE = {
    "manager": "👤 менеджер (шлёте заявки боту)",
    "admin":   "🛡 администратор (получаете уведомления, заходите на сайт)",
    "both":    "👤 менеджер + 🛡 администратор",
    "blocked": "🚫 заблокирован",
}


def cmd_whoami(chat_id: int, from_id: str) -> None:
    u = find_user(from_id)
    if not u:
        send(chat_id, "❌ Вы не в системе.")
        return
    roles = ROLE_VERBOSE.get(u["role"], u["role"])
    sites = []
    if u["role"] in ("admin", "both"):
        sites.append("🛡 админ-сайт: " + BASE_URL)
    if u["role"] in ("manager", "both"):
        sites.append("👤 присылаете заявки прямо сюда")
    sites_line = "\n".join(sites) if sites else "—"
    send(chat_id,
         "Моя роль в системе Wolf AutoDoc\n\n"
         f"👤 {u['full_name'] or ''} (@{u['username'] or '—'})\n"
         f"Telegram ID: {u['telegram_id']}\n"
         f"Добавлен: {fmt_dt(u['created_at'])}\n"
         f"Источник: {u['source']}\n\n"
         f"Ваши роли:\n{roles}\n\n"
         f"Где работаете:\n{sites_line}")


def cmd_invite_manager(chat_id: int, from_id: str) -> None:
    if not is_privileged(from_id):
        send(chat_id, "❌ Только администратор может приглашать менеджеров.")
        return
    code = make_invite("manager", from_id)
    link = f"https://t.me/Wolf_AutoDoc_bot?start={code}"
    send(chat_id,
         f"🔗 Ссылка для приглашения менеджера (живёт {INVITE_TTL_MIN} минут):\n\n"
         f"{link}\n\n"
         f"Откройте её на телефоне или в Telegram, нажмите «Start» — "
         f"человек автоматически станет менеджером.")


def cmd_help(chat_id: int, from_id: str) -> None:
    """Пример заявки: как прислать данные клиента (форма свободная)."""
    user = find_user(from_id)
    if not user or user["role"] == "blocked":
        send(chat_id, "Вы не зарегистрированы в Wolf AutoDoc. "
                      "Попросите администратора пригласить вас.")
        return
    send(chat_id,
         "📝 Пример заявки (форма свободная — можно своими словами)\n\n"
         "Иван Петров, виза C1, 4 500 000 IDR,\n"
         "папка https://drive.google.com/drive/folders/...\n"
         "телефон +7 903 123-45-67, компания ООО «Ромашка», срочно\n\n"
         "Обязательно:\n"
         "• ФИО клиента ИЛИ ссылка на папку Google Drive\n"
         "• продукт (C1, C1-EXT)\n"
         "• стоимость в IDR (по желанию)\n\n"
         "Остальное — по желанию. Если чего-то не хватит, бот подскажет, что дослать.")


def _cmd_help_roles(chat_id: int, from_id: str) -> None:
    """Прежняя справка по ролям — оставлена на случай прямого вызова."""
    user = find_user(from_id)
    role = user["role"] if user else ""
    if role in ("admin", "both"):
        send(chat_id,
             "🛡 Вы администратор Wolf AutoDoc.\n\n"
             "Что вам доступно:\n"
             "• Сюда приходят уведомления о новых заявках от менеджеров.\n"
             "• Вы можете зайти на сайт: " + BASE_URL + "\n"
             "• Команда /invitemanager — выписать ссылку-приглашение менеджера.\n"
             "• Команда /start — обновить закреп с ссылкой на сайт.")
    elif role == "manager":
        send(chat_id,
             "👤 Вы менеджер Wolf AutoDoc.\n\n"
             "Что вам доступно:\n"
             "• Сюда присылайте новые заявки клиентов — по шаблону, который закреплён сверху.\n"
             "• Бот ответит «Заявка #N принята» и пришлёт ссылку на карточку клиента.\n"
             "• Когда администратор возьмёт заявку в работу — получите уведомление.\n"
             "• Команда /start — обновить закреп с шаблоном заявки.")
    else:
        send(chat_id, "Вы не зарегистрированы в Wolf AutoDoc. "
                      "Попросите администратора пригласить вас.")


# ---------- main loop ----------

def handle_update(upd: dict) -> None:
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return
    from_user = msg.get("from") or {}
    from_id = str(from_user.get("id") or "")
    text = (msg.get("text") or "").strip()
    if not from_id:
        return

    log.info("update: chat=%s from=%s text=%r", chat_id, from_id, text[:1000])
    # /start с кодом или без
    if text.startswith("/start"):
        args = text[len("/start"):].strip()
        cmd_start(chat_id, from_id, args, from_user)
        return

    # команды
    if text in ("/help", "/help@Wolf_AutoDoc_bot"):
        cmd_help(chat_id, from_id); return
    if text in ("/whoami", "/id"):
        cmd_whoami(chat_id, from_id); return
    if text in ("/login", "/login@Wolf_AutoDoc_bot"):
        cmd_login(chat_id, from_id); return
    if text.startswith("/invitemanager"):
        cmd_invite_manager(chat_id, from_id); return

    # заявка
    # Заявку принимаем и БЕЗ служебного /new: если менеджер просто прислал ссылку
    # на папку Google Drive (или продукт отдельной строкой) — это уже заявка.
    _drive_like = "drive.google.com" in text
    _product_like = bool(find_product_id(text)) if len(text) < 400 else False
    if (text.startswith("/new") or "ФИО полностью:" in text or "ФИО:" in text
            or _drive_like or _product_like):
        user = find_user(from_id)
        if not user or user["role"] == "blocked":
            send(chat_id, "❌ Вы не в системе.")
            return
        if user["role"] not in ("manager", "admin", "both"):
            send(chat_id, "❌ Нет прав.")
            return
        body = text[len("/new"):].lstrip() if text.startswith("/new") else text
        # Мгновенный ответ: разбор (LLM + чтение Диска) занимает 10-20 секунд,
        # менеджер не должен ждать молча.
        try:
            send(chat_id, "✅ Заявка принята в обработку. Читаю данные клиента — номер пришлю через несколько секунд.")
        except Exception:  # noqa: BLE001
            pass
        form = parse_application(body)

        # --- Досылка продукта: менеджер присылает только «Название продукта: X»,
        #     а ФИО в сообщении нет → это уточнение к последней заявке без продукта.
        if not form.get("full_name") and not form.get("surname"):
            _pid_pre = find_product_id(body)
            if _pid_pre:
                _row = db().execute(
                    """SELECT a.id, cl.surname, cl.name
                         FROM applications a JOIN clients cl ON cl.id=a.client_id
                        WHERE a.product_id IS NULL AND a.status IN ('new','in_progress')
                        ORDER BY a.id DESC LIMIT 1""").fetchone()
                if _row:
                    _pcode = db().execute("SELECT code FROM products WHERE id=?",
                                          (_pid_pre,)).fetchone()["code"]
                    _apply_product(_row["id"], _pid_pre)
                    send(chat_id,
                         f"✅ Продукт для заявки #{_row['id']} "
                         f"({_row['surname'] or ''} {_row['name'] or ''}) — "
                         f"«{_pcode}».\nДокументы сформированы, "
                         f"администратор получит уведомление.")
                    for adm in all_admins():
                        if adm["telegram_id"] == from_id:
                            continue
                        send(adm["telegram_id"],
                             f"📥 Заявка #{_row['id']} дополнена\n"
                             f"Клиент: {_row['surname'] or ''} {_row['name'] or ''}\n"
                             f"Продукт: {_pcode}\n"
                             f"Открыть: {BASE_URL}/applications/{_row['id']}/review")
                    return

        # Свободная форма записи: если жёсткий шаблон распознал мало полей
        # (карточка Kommo, вольный текст, пересылка) — подключаем LLM-агента,
        # который читает текст и раскладывает данные по полям карточки клиента.
        if len([k for k, v in form.items() if v]) < 4:
            try:
                try:
                    from bot.ai_parser import parse_free_form
                except ImportError:
                    from bot.ai_parser import parse_free_form
                _codes = [r["code"] for r in db().execute(
                    "SELECT code FROM products ORDER BY id").fetchall()]
                # LLM может «зависнуть» на сетевом запросе: бот однопоточный,
                # поэтому жёсткий таймаут — иначе заявка молча не создаётся.
                import signal as _sig
                def _on_alarm(signum, frame):
                    raise TimeoutError('LLM не ответил за 30 с')
                _old_h = _sig.signal(_sig.SIGALRM, _on_alarm)
                _sig.alarm(30)
                try:
                    ai = parse_free_form(body, _codes)
                finally:
                    _sig.alarm(0)
                    _sig.signal(_sig.SIGALRM, _old_h)
                # Заполняем только ПУСТЫЕ поля: setdefault не работал, потому что
                # жёсткий шаблон уже создаёт все ключи пустыми — из-за этого разбор
                # заявки от менеджера уходил в никуда (разбор 05.10.2026).
                for k, v in (ai.get("client") or {}).items():
                    if v not in (None, "", "-") and not str(form.get(k) or "").strip():
                        form[k] = v
                _app = ai.get("application") or {}
                if _app.get("product") and not form.get("product_name"):
                    form["product_name"] = _app["product"]
                if _app.get("price_idr") and not form.get("price_idr"):
                    form["price_idr"] = _app["price_idr"]
                if _app.get("comment") and not form.get("comment"):
                    form["comment"] = _app["comment"]
                log.info("llm_parse: полей клиента=%d, продукт=%s, не распознано=%d",
                         len(ai.get("client") or {}), form.get("product_name"),
                         len(ai.get("unrecognized") or []))
                log.info("llm_parse: поля=%s", ", ".join(sorted((ai.get("client") or {}).keys())))
                if ai.get("unrecognized"):
                    log.info("llm_parse: не распознано=%s", ai["unrecognized"][:5])
            except Exception as exc:
                log.error("llm_parse недоступен: %s", exc)

        # Продукт может быть упомянут в свободном тексте (не отдельной строкой) —
        # пробуем распознать по всему сообщению, иначе документы не создадутся.
        if not form.get("product_name"):
            _pid = find_product_id(body)
            if _pid:
                _row = db().execute("SELECT code FROM products WHERE id=?", (_pid,)).fetchone()
                if _row:
                    form["product_name"] = _row["code"]

        # Обязательны ровно две вещи: валидная ссылка на папку Google Drive и тип продукта.
        # Без папки неоткуда взять данные клиента, без продукта непонятно, какие документы делать.
        _drive_in = (form.get("gdrive_url") or form.get("gdrive_folder_url") or "").strip()
        # Ссылку на папку менеджер часто присылает отдельной строкой — парсер её не видит,
        # вытаскиваем прямо из текста.
        if not _drive_in or "drive.google.com" not in _drive_in:
            _dm = re.search(r"https?://drive\.google\.com/[^\s\"'<>]+", body)
            if _dm:
                _drive_in = _dm.group(0).rstrip(".,;)]}")
                form["gdrive_url"] = _drive_in
        _drive_ok = bool(_drive_in) and ("drive.google.com" in _drive_in)
        _prod_code = (form.get("product_name") or "").strip()
        _problems = []
        if not _drive_ok:
            _problems.append("ссылка на папку Google Drive клиента"
                             + (" (ссылка не похожа на Google Drive)" if _drive_in else ""))
        if not _prod_code:
            _problems.append("тип продукта (например C1, C1-EXT, D12, E33G-NEW)")
        if _problems:
            send(chat_id,
                 "❌ Заявку принять нельзя — не хватает:\n"
                 + "".join("   • " + p + "\n" for p in _problems)
                 + "\nБез папки Google Drive неоткуда взять данные клиента,\n"
                   "без типа продукта непонятно, какие документы готовить.\n"
                   "Цена и остальные поля — необязательны.\n\n"
                   "Пришлите так:\n"
                   "«Иван Петров, виза C1, папка https://drive.google.com/drive/folders/...»\n"
                   "или просто ссылку и продукт — данные система возьмёт из папки сама.")
            return
        try:
            app_id, client_id = create_application(form, user, raw_text=body)
            if LAST_DUPLICATE:
                send(chat_id, "ℹ️ Эта заявка уже принята ранее — №%s (статус: %s).\n"
                              "Повторно не создаю: комплект уже готовится по прежней заявке.\n"
                              "Если нужно новое дело — пришлите новую папку на Google Диске."
                     % (LAST_DUPLICATE["app_id"], LAST_DUPLICATE["status"]))
                return
            # администраторам сообщаем сразу: новая заявка, кто менеджер и папка клиента на Диске
            try:
                from bot.notify import notify_admins_new_app
                notify_admins_new_app(app_id, user["full_name"] or user["username"])
            except Exception as _exc:  # noqa: BLE001
                log.warning("уведомление админам о заявке #%s: %s", app_id, _exc)
            # сразу сообщаем менеджеру, если из папки Google Drive нечего взять
            try:
                from services import drive as _ds
                _chk_msg = _ds.check_folder(app_id, client_id)
                if not _chk_msg.get("ok"):
                    # Папку проверяем мягко: файлы в неё часто загружают уже ПОСЛЕ приёма
                    # заявки, поэтому «нет файлов» сразу после приёма — преждевременный вывод.
                    # Система перепроверит папку при обработке и скажет уже по факту.
                    send(chat_id, ("\u2139\ufe0f Заявка №" + str(app_id) + " принята. В папке Google Drive пока "
                                   + ("не видно паспорта клиента" if _chk_msg.get("files")
                                      else "не видно файлов")
                                   + ".\nЕсли файлы ещё загружаются — ничего делать не нужно: система "
                                     "перепроверит папку при обработке заявки."))
            except Exception as _exc:  # noqa: BLE001
                log.warning("проверка папки после приёма заявки #%s: %s", app_id, _exc)
            try:
                # исходный текст заявки сохраняем — он же попадёт в «Заявка.txt» на Google Drive
                form["_raw_text"] = body
                db().execute("UPDATE applications SET raw_payload=? WHERE id=?",
                             (json.dumps({**form}, ensure_ascii=False, default=str), app_id))
                db().commit()
                _write_application_text(app_id, body, form, user)
            except Exception as _exc:  # файл не критичен для создания заявки
                log.warning("текстовый файл заявки #%s не создан: %s", app_id, _exc)
        except Exception as exc:
            log.exception("create_application failed: %s", exc)
            send(chat_id, "❌ Не удалось создать заявку — техническая ошибка.\n"
                          "Администратор уведомлён, ваши данные не потеряны.")
            for adm in all_admins():
                if adm["telegram_id"] == from_id:
                    continue
                send(adm["telegram_id"],
                     f"⚠️ Ошибка при создании заявки\n"
                     f"Менеджер: {user['full_name'] or user['username'] or from_id}\n"
                     f"Ошибка: {exc}\n\n"
                     f"Исходный текст:\n{body[:900]}")
            return
        client_row = db().execute(
            "SELECT surname, name, patronymic FROM clients WHERE id=?",
            (client_id,)).fetchone()
        client_label = " ".join(filter(None, [client_row["surname"] if client_row else "",
                                               client_row["name"] if client_row else ""]))
        link = f"{BASE_URL}/applications/{app_id}/review"
        is_manager_only = user["role"] == "manager"

        # Проверяем, распознан ли продукт: без него документы НЕ создаются
        app_row = db().execute("SELECT product_id FROM applications WHERE id=?",
                               (app_id,)).fetchone()
        product_ok = bool(app_row and app_row["product_id"])
        prod_label = (form.get("product_name") or "").strip()
        codes = [r["code"] for r in db().execute(
            "SELECT code FROM products ORDER BY id").fetchall()]
        _missing = []
        if not product_ok:
            prod_label = "⚠️ НЕ РАСПОЗНАН"
            _missing.append(f"продукт (доступные: {', '.join(codes) or '—'})")
        # стоимость — необязательное поле: пишем её, если менеджер указал
        if not _drive_in:
            _missing.append("ссылка на папку Google Drive "
                            "(из неё подтянутся ФИО, паспорт, банк)")
        if _missing:
            warn = ("\n⚠️ Не хватает: " + "; ".join(_missing) + "\n"
                    "Дошлите это одним сообщением — администратор внесёт в заявку.\n")
        else:
            warn = ""

        # Менеджер — только подтверждение без ссылки.
        # Админ/both — видит ссылку (он же работает на сайте).
        if is_manager_only:
            send(chat_id,
                 f"✅ Заявка #{app_id} принята.\n"
                 f"Клиент: {client_label or '—'}\n"
                 f"Продукт: {prod_label or '—'}\n"
                 f"{warn}\n"
                 f"Администратор получит уведомление и возьмёт её в работу.\n"
                 f"Когда документы будут готовы — вам придёт сообщение.")
        else:
            send(chat_id,
                 f"✅ Заявка #{app_id} принята (отправлена через ваш Telegram).\n"
                 f"Клиент: {client_label or '—'}\n"
                 f"Продукт: {prod_label or '—'}\n"
                 f"{warn}\n"
                 f"Открыть: {link}")
        # уведомляем админов (исключая отправителя, если он сам админ)
        for adm in all_admins():
            if adm["telegram_id"] == from_id:
                continue
            send(adm["telegram_id"],
                 f"📥 Новая заявка #{app_id}\n"
                 f"Клиент: {client_label or '—'}\n"
                 f"Продукт: {prod_label or '—'}\n"
                 f"{warn}\n"
                 f"Менеджер: {user['full_name'] or user['username'] or from_id}\n"
                 f"Открыть: {link}")
        # Менеджер и админы уже получили ответ. Теперь можно не спеша
        # сгенерировать PDF (5+ сек) — бот при этом остаётся отзывчивым.
        if product_ok:
            log.info("генерирую PDF для заявки #%s…", app_id)
            try:
                _autofill_pdfs(app_id, client_id, app_row["product_id"])
                log.info("PDF для заявки #%s готовы", app_id)
            except Exception as exc:
                log.exception("генерация PDF для #%s упала: %s", app_id, exc)
        return

    # неизвестная команда от известного пользователя
    if find_user(from_id):
        send(chat_id, "Не понял. /help для списка команд, "
                      "или начните заявку с /new")


def main():
    log.info("wolf_bot starting…")
    set_bot_menu()
    offset = 0
    while True:
        try:
            r = tg("getUpdates", {"timeout": POLL_TIMEOUT, "offset": offset,
                                  "allowed_updates": "[\"message\"]"})
            results = r.get("result", [])
            if results:
                log.info("got %d update(s)", len(results))
            for u in results:
                offset = max(offset, u["update_id"] + 1)
                try:
                    handle_update(u)
                except Exception as exc:
                    log.exception("handle_update failed: %s", exc)
        except urllib.error.HTTPError as e:
            log.warning("HTTP %s, retry in 5s", e)
            time.sleep(5)
        except Exception as exc:
            log.exception("loop error: %s", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()
