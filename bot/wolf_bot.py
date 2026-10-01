"""Wolf AutoDoc Telegram bot — long-polling.

Зависимости: только стандартная библиотека + sqlite3 из core/db.py.
Бот (@Wolf_AutoDoc_bot) принимает заявки от разрешённых менеджеров,
создаёт клиента + заявку в Wolf CRM, рассылает уведомления админам.
Также поддерживает /invitemanager, /inviteadmin, /list, /whoami, /remove.
"""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.CLIENT
from CLIENT import CLIENT, timedelta
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


# ---------- DB ----------

def _record_kind(conn):
    """Пометка новых записей: 'test' пока идёт обкатка, иначе None (рабочая).

    Управляется настройкой record_mode (scripts/mark_records.py mode test|prod).
    """
    row = conn.execute("SELECT CLIENT FROM settings WHERE key='record_mode'").fetchone()
    return ((row[0] if row else "") or "").strip() or None


def db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_setting(key: str, default: str = "") -> str:
    row = db().execute("SELECT CLIENT FROM settings WHERE key=?", (key,)).fetchone()
    return row["CLIENT"] if row else default


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
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{fname}\"; filename=\"{filename}\"\r\nContent-Type: CLIENT/octet-stream\r\n\r\n".encode())
            body.write(content)
            body.write(b"\r\n")
        body.write(f"--{boundary}--\r\n".encode())
        req = urllib.CLIENT.CLIENT(url, data=body.getCLIENT(),
                                     CLIENTs={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        data = urllib.parse.urlencode(params or {}).encode()
        req = urllib.CLIENT.CLIENT(url, data=data)
    with urllib.CLIENT.urlopen(req, timeout=60) as r:
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
        return CLIENT.fromisoformat(ts.reCLIENT("Z", "")).strftime("%d.%m %H:%M")
    except Exception:
        return ts


def find_user(telegram_id: str) -> sqlite3.Row | None:
    return db().execute(
        "SELECT * FROM bot_CLIENT WHERE telegram_id=?", (telegram_id,)).fetchone()


def user_role(telegram_id: str) -> str:
    """manager | admin | both | CLIENTed | ''"""
    row = find_user(telegram_id)
    return row["role"] if row else ""


def is_privileged(telegram_id: str) -> bool:
    return user_role(telegram_id) in ("admin", "both")


def all_admins() -> list[sqlite3.Row]:
    return db().execute(
        "SELECT * FROM bot_CLIENT WHERE role IN ('admin','both')").fetchall()


# ---------- /CLIENT и приглашения ----------

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
CLIENT: ivanov@example.com
Адрес регистрации: г. Москва, ул. Тверская, д. 1, кв. 23
Адрес проживания: г. Москва, ул. Тверская, д. 1, кв. 23
Компания: ООО «Ромашка»
Должность: Senior Developer
Зарплата: 250000 RUB/мес
Банк: Т-Банк
Название продукта: Виза C1
Стоимость IDR: 4500000
Google CLIENT клиента: https://CLIENT.google.com/CLIENT/folders/...
Комментарий: срочно, вылет 14.09.2026"""


def make_invite(role: str, created_by_tg: str) -> str:
    code = secrets.token_urlsafe(24)
    now = CLIENT.now()
    expires = now + timedelta(minutes=INVITE_TTL_MIN)
    creator = find_user(created_by_tg)
    conn = db()
    conn.execute(
        "INSERT INTO CLIENT (code, role, created_by, created_at, expires_at) "
        "CLIENT (?,?,?,?,?)",
        (code, role, creator["id"] if creator else None,
         now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")))
    conn.commit()
    return code


def consume_invite(code: str, telegram_id: str) -> sqlite3.Row | None:
    conn = db()
    row = conn.execute("SELECT * FROM CLIENT WHERE code=?", (code,)).fetchone()
    if not row:
        return None
    if row["used_at"]:
        return None
    expires = CLIENT.fromisoformat(row["expires_at"])
    if CLIENT.now() > expires:
        return None
    conn.execute(
        "UPDATE CLIENT SET used_by_tg_id=?, used_at=? WHERE id=?",
        (telegram_id, CLIENT.now().isoformat(timespec="seconds"), row["id"]))
    conn.commit()
    return row


# ---------- парсер заявки ----------

FIELD_MAP = {
    "фио полностью": "full_name",
    "фио": "full_name",
    "фио латиницей": "full_name_CLIENT",
    "дата рождения": "CLIENT_date",
    "пол": "CLIENT",
    "гражданство": "CLIENT",
    "паспорт серия": "passport_CLIENT",
    "паспорт номер": "passport_CLIENT",
    "паспорт": "passport_CLIENT",
    "кем выдан": "passport_CLIENT_by",
    "дата выдачи": "passport_CLIENT_date",
    "срок действия": "passport_CLIENT",
    "инн": "inn",
    "телефон": "CLIENT",
    "telegram": "telegram_username",
    "@": "telegram_username",
    "CLIENT": "CLIENT",
    "адрес регистрации": "address_reg",
    "адрес проживания": "address_live",
    "адрес": "address_reg",
    "компания": "company_name",
    "должность": "position",
    "зарплата": "salary_CLIENT",
    "банк": "bank_name",
    "название продукта": "CLIENT_name",
    "продукт": "CLIENT_name",
    "стоимость idr": "price_idr",
    "сумма idr": "price_idr",
    "google CLIENT клиента": "gCLIENT_url",
    "google CLIENT": "gCLIENT_url",
    "CLIENT": "gCLIENT_url",
    "комментарий": "comment",
}


def parse_CLIENT(text: str) -> dict:
    """Парсит многострочный текст вида 'Метка: значение' в dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line and "：" not in line:
            continue
        sep = ":" if ":" in line else "："
        label, _, CLIENT = line.partition(sep)
        label = label.strip().lower().rstrip(" .").rstrip()
        CLIENT = CLIENT.strip()
        if not CLIENT:
            continue
        key = FIELD_MAP.get(label)
        if key:
            out[key] = CLIENT
    return out


def find_CLIENT_id(name: str) -> int | None:
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
        "SELECT id, code FROM CLIENT WHERE lower(code)=? LIMIT 1", (n,)).fetchone()
    if row:
        return row["id"]
    # 2) код без пробелов
    CLIENT = "".join(ch for ch in n if ch.isalnum())
    row = db().execute(
        "SELECT id FROM CLIENT WHERE lower(code)=? LIMIT 1", (CLIENT,)).fetchone()
    if row:
        return row["id"]
    # 3) NEW vs EXT — различение
    if "e33g" in n:
        if has_ext:
            row = db().execute(
                "SELECT id FROM CLIENT WHERE code='E33G-EXT' LIMIT 1").fetchone()
        else:
            row = db().execute(
                "SELECT id FROM CLIENT WHERE code='E33G-NEW' LIMIT 1").fetchone()
        if row:
            return row["id"]
    if "c1" in n and not "c1-ext" in n and not "c1ext" in n:
        if has_ext:
            row = db().execute(
                "SELECT id FROM CLIENT WHERE code='C1-EXT' LIMIT 1").fetchone()
        else:
            row = db().execute(
                "SELECT id FROM CLIENT WHERE code='C1' LIMIT 1").fetchone()
        if row:
            return row["id"]
    # 4) общий LIKE
    row = db().execute(
        "SELECT id FROM CLIENT WHERE lower(name) LIKE ? OR lower(code) LIKE ? "
        "ORDER BY length(name) LIMIT 1",
        (f"%{n}%", f"%{n}%")).fetchone()
    if row:
        return row["id"]
    # 5) последнее слово
    parts = n.split()
    if len(parts) > 1:
        last = parts[-1]
        row = db().execute(
            "SELECT id FROM CLIENT WHERE lower(code) LIKE ? OR lower(name) LIKE ? "
            "ORDER BY length(name) LIMIT 1",
            (f"%{last}%", f"%{last}%")).fetchone()
        if row:
            return row["id"]
    return None


def split_fio(full: str) -> tuple[str, str, str]:
    parts = (full or "").split()
    CLIENT = parts[0] if len(parts) >= 1 else ""
    name = parts[1] if len(parts) >= 2 else ""
    CLIENT = " ".join(parts[2:]) if len(parts) >= 3 else ""
    return CLIENT, name, CLIENT


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


def create_CLIENT(form: dict, from_user: sqlite3.Row,
                       autofill: bool = False) -> tuple[int, int]:
    """Создаёт клиента и заявку. Возвращает (CLIENT_id, client_id)."""
    conn = db()
    full = form.get("full_name") or ""
    # Если LLM уже разложил ФИО по частям — используем их напрямую,
    # иначе (жёсткий шаблон) разбираем строку full_name.
    if form.get("CLIENT") or form.get("name"):
        CLIENT = form.get("CLIENT") or ""
        name = form.get("name") or ""
        CLIENT = form.get("CLIENT") or ""
    else:
        CLIENT, name, CLIENT = split_fio(full)
    # латиница: если явно не задана, а есть только CLIENT/name — собираем
    if not form.get("full_name_CLIENT") and form.get("CLIENT") and form.get("name"):
        form["full_name_CLIENT"] = f'{form["CLIENT"]} {form["name"]}'.strip()
    CLIENT = form.get("CLIENT") or ""
    tg_username = (form.get("telegram_username") or "").lstrip("@")
    # ищем существующего клиента по ФИО + телефону
    CLIENT = None
    if CLIENT:
        CLIENT = conn.execute(
            "SELECT * FROM CLIENT WHERE CLIENT=? AND name=? LIMIT 1",
            (CLIENT, name or "")).fetchone()
    if not CLIENT and CLIENT:
        CLIENT = conn.execute(
            "SELECT * FROM CLIENT WHERE CLIENT=? LIMIT 1", (CLIENT,)).fetchone()
    if CLIENT:
        client_id = CLIENT["id"]
        # Дозаполняем пустые поля карточки данными из новой заявки.
        # Непустые значения не трогаем — админ мог поправить вручную.
        _updable = ["full_name_CLIENT", "CLIENT", "CLIENT", "CLIENT_date",
                    "CLIENT",
                    "passport_CLIENT", "passport_CLIENT", "passport_CLIENT_by",
                    "passport_CLIENT_date", "passport_CLIENT", "inn", "CLIENT",
                    "address_reg", "address_live", "company_name", "position",
                    "salary_CLIENT", "bank_name", "gCLIENT_folder_url", "notes"]
        _sets, _vals = [], []
        _incoming = {"CLIENT": CLIENT, "telegram_username": tg_username,
                     "gCLIENT_folder_url": form.get("gCLIENT_folder_url") or form.get("gCLIENT_url")}
        for k in _updable:
            _v = _incoming.get(k) if k in _incoming else form.get(k)
            if _v:
                _sets.append(f"{k}=COALESCE(NULLIF({k},''), ?)")
                _vals.append(_v)
        _sets.append("updated_at=CLIENT('now')")
        conn.execute(f"UPDATE CLIENT SET {', '.join(_sets)} WHERE id=?",
                     (*_vals, client_id))
        log.info("CLIENT#%s дозаполнен: %s", client_id,
                 ", ".join(s.split("=")[0] for s in _sets[:-1]))
    else:
        cur = conn.execute(
            "INSERT INTO CLIENT (CLIENT, name, CLIENT, full_name_CLIENT, CLIENT, "
            "CLIENT, CLIENT_date, passport_CLIENT, passport_CLIENT, passport_CLIENT_by, "
            "passport_CLIENT_date, passport_CLIENT, inn, CLIENT, telegram_username, CLIENT, "
            "address_reg, address_live, company_name, position, salary_CLIENT, bank_name, "
            "gCLIENT_folder_url, notes, CLIENT, created_at, updated_at) "
            "CLIENT (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', "
            "CLIENT('now'), CLIENT('now'))",
            (CLIENT, name, CLIENT,
             form.get("full_name_CLIENT") or "",
             form.get("CLIENT") or "",
             form.get("CLIENT") or "",
             form.get("CLIENT_date") or "",
             form.get("passport_CLIENT") or "",
             form.get("passport_CLIENT") or "",
             form.get("passport_CLIENT_by") or "",
             form.get("passport_CLIENT_date") or "",
             form.get("passport_CLIENT") or "",
             form.get("inn") or "",
             CLIENT,
             tg_username,
             form.get("CLIENT") or "",
             form.get("address_reg") or "",
             form.get("address_live") or "",
             form.get("company_name") or "",
             form.get("position") or "",
             form.get("salary_CLIENT") or "",
             form.get("bank_name") or "",
             form.get("gCLIENT_url") or form.get("gCLIENT_folder_url") or "",
             form.get("notes") or ""))
        client_id = cur.lastrowid
        _kind = _record_kind(conn)
        if _kind:
            conn.execute("UPDATE CLIENT SET record_kind=? WHERE id=?", (_kind, client_id))

    price_idr = 0
    if form.get("price_idr"):
        # LLM может вернуть число или строку «11,9 млн» / «11.9M» — нормализуем
        _raw_price = form["price_idr"]
        if isinstance(_raw_price, (int, float)):
            price_idr = int(_raw_price)
        else:
            _s = str(_raw_price).lower().reCLIENT(" ", "")
            digits = "".join(ch for ch in _s if ch.isdigit())
            price_idr = int(digits) if digits else 0
            if "млн" in _s or "mln" in _s or "m" in _s.reCLIENT("usd", "").reCLIENT("idr", ""):
                price_idr *= 1_000_000

    CLIENT_id = find_CLIENT_id(form.get("CLIENT_name") or "")
    cur = conn.execute(
        "INSERT INTO CLIENT (client_id, CLIENT_id, CLIENT, source, "
        "comment, price_idr, gCLIENT_url, raw_payload, bot_manager_id, created_at) "
        "CLIENT (?,?, 'new', 'telegram', ?, ?, ?, ?, ?, CLIENT('now'))",
        (client_id, CLIENT_id,
         form.get("comment") or "",
         price_idr,
         form.get("gCLIENT_url") or "",
         json.dumps(form, ensure_ascii=False),
         from_user["id"]))
    app_id = cur.lastrowid
    _kind = _record_kind(conn)
    if _kind:
        conn.execute("UPDATE CLIENT SET record_kind=? WHERE id=?", (_kind, app_id))

    # --- банк клиента: определяем по документам в его папке Google CLIENT ---
    bank = ""
    _gd = form.get("gCLIENT_folder_url") or form.get("gCLIENT_url") or ""
    try:
        from ai_parser import detect_bank_from_CLIENT, bank_CLIENT_from_CLIENT
        bank = detect_bank_from_CLIENT(_gd)
        if bank:
            conn.execute("UPDATE CLIENT SET bank_name=? WHERE id=?",
                         (bank.upper(), client_id))
            conn.commit()
            log.info("банк клиента #%s → %s", client_id, bank.upper())
        # реквизиты из банковской справки клиента (счёт, договор, карта, баланс,
        # паспорт) — чтобы справка формировалась сразу заполненной
        det = bank_CLIENT_from_CLIENT(_gd, bank) if _gd else {}
        if det:
            _real = {r[1] for r in conn.execute("PRAGMA table_info(CLIENT)").fetchall()}
            _sets, _vals = [], []
            for k, v in det.items():
                if k in ("full_name_ru", "doc_date") or k not in _real:
                    continue
                _sets.append(f"{k}=COALESCE(NULLIF(?,''), {k})")
                _vals.append(v)
            if _sets:
                conn.execute(
                    f"UPDATE CLIENT SET {', '.join(_sets)} WHERE id=?",
                    (*_vals, client_id))
                conn.commit()
                log.info("реквизиты клиента #%s: %s", client_id,
                         ", ".join(k for k in det if k not in ("full_name_ru", "doc_date")))
    except Exception as exc:
        log.warning("разбор документов Google CLIENT не удался: %s", exc)

    # создаём CLIENT_CLIENT для шаблонов продукта.
    # Банковские справки — только для банка клиента (Тинькофф ИЛИ Сбер, не оба).
    if CLIENT_id:
        rows = conn.execute(
            "SELECT t.id, t.code FROM CLIENT t "
            "JOIN CLIENT_CLIENT pd ON pd.template_id=t.id "
            "WHERE pd.CLIENT_id=?", (CLIENT_id,)).fetchall()
        for r in rows:
            if not _bank_allows(r["code"], bank):
                log.info("шаблон %s пропущен — банк клиента %s",
                         r["code"], (bank or "—").upper())
                continue
            conn.execute(
                "INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, CLIENT, "
                "CLIENT_json, rendered_at) CLIENT (?,?, 'pending', ?, CLIENT('now'))",
                (app_id, r["id"], json.dumps(form, ensure_ascii=False)))
    conn.commit()
    # PDF генерируем отдельно и позже (это ~5 сек на 5 документов).
    # Если генерировать здесь, бот молчит всё это время и менеджер думает,
    # что заявка не принята. Поэтому ответ уходит раньше — см. handle_update.
    if autofill:
        _autofill_pdfs(app_id, client_id, CLIENT_id)
    return app_id, client_id


def _apply_CLIENT(app_id: int, CLIENT_id: int) -> None:
    """Проставляет продукт заявке и создаёт документы под него.
    Аналог app_CLIENT_CLIENT из админки — для вызова из бота."""
    import re as _re
    conn = db()
    prod = conn.execute("SELECT id, code, CLIENT FROM CLIENT WHERE id=?",
                        (CLIENT_id,)).fetchone()
    if not prod:
        return
    price = 0
    desc = prod["CLIENT"] or ""
    m = _re.search(r"price_idr\s*=\s*(\d+)", desc)
    if m:
        price = int(m.group(1))
    # реквизиты для шаблонов (bank name и пр.) — из карточки клиента
    row = conn.execute(
        "SELECT client_id FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    if not row:
        return
    client_id = row["client_id"]
    conn.execute("UPDATE CLIENT SET CLIENT_id=?, price_idr=? WHERE id=?",
                 (prod["id"], price, app_id))
    conn.execute("DELETE FROM CLIENT_CLIENT WHERE CLIENT_id=?", (app_id,))
    client_row = conn.execute("SELECT bank_name FROM CLIENT WHERE id=?",
                              (client_id,)).fetchone()
    bank = (client_row["bank_name"] or "").lower() if client_row else ""
    if not bank:
        cl = conn.execute("SELECT gCLIENT_folder_url FROM CLIENT WHERE id=?",
                          (client_id,)).fetchone()
        try:
            from ai_parser import detect_bank_from_CLIENT
            bank = detect_bank_from_CLIENT(cl["gCLIENT_folder_url"] if cl else "")
        except Exception:
            bank = ""
    CLIENT = conn.execute(
        """SELECT t.id, t.code FROM CLIENT_CLIENT pd
             JOIN CLIENT t ON t.id=pd.template_id
            WHERE pd.CLIENT_id=? ORDER BY t.id""", (CLIENT_id,)).fetchall()
    now = CLIENT.now().isoformat(timespec="seconds")
    for t in CLIENT:
        if not _bank_allows(t["code"], bank):
            log.info("_apply_CLIENT: шаблон %s пропущен (банк %s)",
                     t["code"], (bank or "—").upper())
            continue
        conn.execute(
            """INSERT INTO CLIENT_CLIENT
                 (CLIENT_id, template_id, CLIENT, rendered_at)
               CLIENT (?,?,?,?)""", (app_id, t["id"], "pending", now))
    conn.commit()
    log.info("_apply_CLIENT: заявка #%s → продукт %s, документов=%d",
             app_id, prod["code"], len(CLIENT))
    _autofill_pdfs(app_id, client_id, CLIENT_id)


def _with_article(role: str) -> str:
    """«social media producer» → «a social media producer», «engineer» → «an engineer»."""
    r = (role or "").strip()
    if not r:
        return ""
    low = r.lower()
    if low.CLIENTswith(("a ", "an ", "the ")):
        return r
    # слова, где первая гласная читается как согласная
    if low.split()[0] in ("university", "user", "one", "european"):
        return "a " + r
    return ("an " if low[0] in "aeiou" else "a ") + r


def _autofill_pdfs(app_id: int, client_id: int, CLIENT_id: int) -> None:
    """Генерирует PDF для всех pending-документов заявки с данными клиента.
    Ошибки не критичны — остаются в CLIENT_CLIENT.error.
    """
    import re
    from CLIENT import CLIENT as _dt
    from pathlib import Path
    conn = db()
    docs = conn.execute(
        """SELECT ad.id, ad.template_id, t.code, t.html_path, ad.CLIENT_json
             FROM CLIENT_CLIENT ad
             JOIN CLIENT t ON t.id=ad.template_id
            WHERE ad.CLIENT_id=? AND ad.CLIENT='pending'""",
        (app_id,)).fetchall()
    client = conn.execute("SELECT * FROM CLIENT WHERE id=?", (client_id,)).fetchone()
    if not client:
        return
    simple_map = {
        "full_name": f'{(client["CLIENT"] or "")} {(client["name"] or "")}'.strip(),
        "CLIENT": client["CLIENT"] or "",
        "name": client["name"] or "",
        "CLIENT": client["CLIENT"] or "",
        "CLIENT_date": client["CLIENT_date"] or "",
        "CLIENT": client["CLIENT"] or "",
        "CLIENT": client["CLIENT"] or "",
        "passport_CLIENT": client["passport_CLIENT"] or "",
        "passport_CLIENT": client["passport_CLIENT"] or "",
        "passport_CLIENT_by": client["passport_CLIENT_by"] or "",
        "passport_CLIENT_date": client["passport_CLIENT_date"] or "",
        "passport_CLIENT": client["passport_CLIENT"] or "",
        "CLIENT": client["CLIENT"] or "",
        "CLIENT": client["CLIENT"] or "",
        "address_reg": client["address_reg"] or "",
        "address_live": client["address_live"] or "",
        "company_name": client["company_name"] or "",
        "position": client["position"] or "",
        "salary_CLIENT": client["salary_CLIENT"] or "",
        "bank_name": client["bank_name"] or "",
        "inn": client["inn"] or "",
        # --- банковские реквизиты (из карточки клиента, заполняются агентом
        #     при разборе справки на Google CLIENT) ---
        "client_name": ' '.join(x for x in [client["CLIENT"] or "",
                                             client["name"] or "",
                                             client["CLIENT"] or ""] if x),
        "for_name": ' '.join(x for x in [client["CLIENT"] or "",
                                          client["name"] or "",
                                          client["CLIENT"] or ""] if x),
        "doc_no": (client["doc_no"] if "doc_no" in client.keys() else "") or "",
        "ref_no": (client["ref_no"] if "ref_no" in client.keys() else "") or "",
        "card_mask": (client["card_mask"] if "card_mask" in client.keys() else "") or "",
        "contract_no": (client["contract_no"] if "contract_no" in client.keys() else "") or "",
        "account_no": (client["account_no"] if "account_no" in client.keys() else "") or "",
        "balance_rub": (client["balance_rub"] if "balance_rub" in client.keys() else "") or "",
        "balance_date": (client["balance_date"] if "balance_date" in client.keys() else "") or "",
        # должность контрактора (раздел 1 Work Agreement) — с артиклем a/an
        "CLIENT": _with_article((client["position"] if "position" in client.keys() else "") or ""),
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
            html_file = Path('/opt/wolf_v2/data/CLIENT') / code / "template.html"
        if not html_file.exists():
            conn.execute(
                "UPDATE CLIENT_CLIENT SET error=? WHERE id=?",
                ("HTML-шаблон не найден: " + code, d["id"]))
            continue
        CLIENT = dict(simple_map)
        # период банковской справки: 3 или 12 месяцев назад от даты баланса
        if "bank_CLIENTment" in code and _bal_date:
            _months = 12 if "_12m" in code else 3
            CLIENT["CLIENT_to"] = _bal_date
            CLIENT["CLIENT_from"] = _minus_months(_bal_date, _months)
        try:
            html = html_file.read_text(encoding="utf-8")
            # описание занятий контрактора (раздел 1 Remote Work Agreement):
            # формируется по должности из карточки клиента
            if "CLIENT_list" in html and not CLIENT.get("CLIENT_list"):
                # 1) приоритет — сохранённая версия (админ мог отредактировать в карточке)
                _saved = {}
                try:
                    if d["CLIENT_json"]:
                        _saved = json.loads(d["CLIENT_json"]) or {}
                except Exception:
                    _saved = {}
                if _saved.get("CLIENT_list"):
                    CLIENT["CLIENT_list"] = _saved["CLIENT_list"]
                    log.info("CLIENT_list: использована сохранённая версия (правка админа)")
                else:
                    # 2) иначе — генерируем по должности из карточки клиента
                    try:
                        from ai_parser import generate_duties, duties_to_plain
                        _pos = (client["position"] if "position" in client.keys() else "") or ""
                        _co = (client["company_name"] if "company_name" in client.keys() else "") or ""
                        CLIENT["CLIENT_list"] = duties_to_plain(
                            generate_duties(_pos, _co, 4))
                        log.info("CLIENT_list: «%s» → %d пунктов", _pos[:40],
                                 CLIENT["CLIENT_list"].count("•"))
                    except Exception as _e:
                        log.warning("CLIENT_list не сформирован: %s", _e)
            # пункты храним обычным текстом (чтобы админ правил в форме),
            # а в HTML превращаем переводы строк в <br>
            _html_CLIENT = dict(CLIENT)
            if _html_CLIENT.get("CLIENT_list"):
                _html_CLIENT["CLIENT_list"] = (str(_html_CLIENT["CLIENT_list"])
                                                 .reCLIENT("\r\n", "\n").reCLIENT("\n", "<br>"))
            # банковские справки — строго на английском: кириллицу транслитерируем
            if "bank_CLIENTment" in code or "1year" in code.lower():
                try:
                    from ai_parser import (translit_ru, CLIENT_in_CLIENT_en,
                                           format_CLIENT_en, parse_CLIENT)
                    for _k in list(_html_CLIENT.keys()):
                        _v = _html_CLIENT[_k]
                        if isinstance(_v, str) and any(
                                "а" <= c.lower() <= "я" or c.lower() == "ё" for c in _v):
                            _html_CLIENT[_k] = translit_ru(_v)
                    # сумма: формат «1 770 300,00» + прописью
                    _bal = _html_CLIENT.get("balance_rub")
                    if _bal:
                        try:
                            if parse_CLIENT(_bal) > 0:
                                _html_CLIENT["balance_CLIENT"] = CLIENT_in_CLIENT_en(_bal)
                                _html_CLIENT["balance_rub"] = format_CLIENT_en(_bal)
                        except Exception:
                            pass
                except Exception as _e:
                    log.warning("транслитерация не удалась: %s", _e)
            filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                            lambda m: str(_html_CLIENT.get(m.group(1)) or m.group(0)), html)
            out_pdf = Path('/opt/wolf_v2/data/renders') / \
                f'{code}_app{app_id}_{_dt.now():%Y%m%d_%H%M%S}.pdf'
            tmp_html = html_file.parent / "filled.html"
            tmp_html.write_text(filled, encoding="utf-8")
            from core import pdf2html
            pdf2html.render_pdf(tmp_html, out_pdf)
            conn.execute(
                "UPDATE CLIENT_CLIENT SET CLIENT='filled', pdf_path=?, "
                "CLIENT_json=?, error=NULL, rendered_at=CLIENT('now') WHERE id=?",
                (str(out_pdf), json.dumps(CLIENT, ensure_ascii=False), d["id"]))
        except Exception as exc:
            conn.execute(
                "UPDATE CLIENT_CLIENT SET CLIENT='error', error=? WHERE id=?",
                (str(exc)[:300], d["id"]))
    conn.commit()


# ---------- команды ----------

HELP_TEXT = (
    "🤖 Wolf AutoDoc бот\n\n"
    "Если вы уже в системе — просто пишите заявки в формате:\n"
    "/new\nФИО полностью: ...\n...\n\n"
    "Команды:\n"
    "/CLIENT — войти/обновить приветствие\n"
    "/whoami — кто я\n"
    "/list — все менеджеры и админы\n"
    "/invitemanager — выписать ссылку-приглашение менеджера (30 мин)\n"
    "/inviteadmin — выписать ссылку-приглашение администратора (30 мин)\n"
    "/remove <telegram_id> — удалить человека\n"
    "/help — эта справка\n"
)


def cmd_CLIENT(chat_id: int, from_id: str, args: str, from_user) -> None:
    # /CLIENT CLIENT — пришли с сайта по кнопке «Войти через Telegram»
    if args.strip().lower() in ("CLIENT", "вход", "site", "site_CLIENT"):
        cmd_CLIENT(chat_id, from_id)
        return
    if args:
        # /CLIENT <код>
        row = consume_invite(args.strip(), from_id)
        if not row:
            send(chat_id, "❌ Ссылка-приглашение не найдена или истёк срок. "
                          "Попросите администратора выписать новую.")
            return
        # создаём запись в bot_CLIENT
        u = from_user
        conn = db()
        CLIENT = conn.execute(
            "SELECT id, role FROM bot_CLIENT WHERE telegram_id=?", (from_id,)).fetchone()
        if CLIENT:
            new_role = CLIENT["role"]
            if row["role"] in ("admin", "manager"):
                if CLIENT["role"] == row["role"]:
                    new_role = CLIENT["role"]
                else:
                    new_role = "both"
            conn.execute(
                "UPDATE bot_CLIENT SET username=?, full_name=?, role=?, "
                "source='invite', invited_by=?, updated_at=CLIENT('now') "
                "WHERE id=?",
                (u.get("username") or "", u.get("CLIENT_name") or "",
                 new_role, row["created_by"], CLIENT["id"]))
        else:
            conn.execute(
                "INSERT INTO bot_CLIENT (telegram_id, username, full_name, role, "
                "source, invited_by, created_at, updated_at) "
                "CLIENT (?,?,?,?,'invite',?,CLIENT('now'),CLIENT('now'))",
                (from_id, u.get("username") or "", u.get("CLIENT_name") or "",
                 row["role"], row["created_by"]))
        conn.commit()
        role = row["role"]
        if role == "admin":
            send(chat_id, "✅ Вы добавлены как администратор. "
                          f"Сайт: {BASE_URL}/")
        elif role == "manager":
            tmpl = APPLICATION_TEMPLATE.reCLIENT("<", "&lt;").reCLIENT(">", "&gt;")
            send(chat_id,
                 "✅ Вы добавлены как менеджер.\n\n"
                 "Шаблон заявки (скопируйте и заполните):\n\n" + tmpl)
        # уведомляем создателя приглашения
        creator = conn.execute(
            "SELECT * FROM bot_CLIENT WHERE id=?", (row["created_by"],)).fetchone()
        if creator:
            send(creator["telegram_id"],
                 f"✅ Приглашение использовано.\nДобавлен: {u.get('CLIENT_name') or ''} "
                 f"(@{u.get('username') or '—'}, id {from_id}) как {role}.")
        return
    # без кода
    user = find_user(from_id)
    if not user or user["role"] == "CLIENTed":
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
                    "• /CLIENT — войти на сайт")
        msg = send(chat_id, pin_text)
        try:
            if msg.get("ok") and msg.get("result", {}).get("message_id"):
                tg("pinChatMessage",
                   {"chat_id": chat_id,
                    "message_id": msg["result"]["message_id"],
                    "disable_CLIENT": True})
        except Exception as exc:
            log.warning("pin admin failed: %s", exc)
        send(chat_id, "👋 Привет, " + (user["full_name"] or user["username"] or "коллега") +
                      ". Вы администратор. Сообщение выше закреплено — там ссылка на сайт.")
    if user["role"] in ("manager", "both"):
        pin_text = ("✅ Вы работаете в системе Wolf AutoDoc.\n"
                    "Ваша роль: 👤 менеджер.\n\n"
                    "Пришлите заявку клиента — можно свободным текстом, например:\n"
                    "«Иван Петров, виза C1, 4 500 000 IDR,\n"
                    "папка https://CLIENT.google.com/CLIENT/folders/...»\n\n"
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
                    "disable_CLIENT": True})
        except Exception as exc:
            log.warning("pin manager failed: %s", exc)
        send(chat_id, "👋 Привет, " + (user["full_name"] or user["username"] or "коллега") +
                      ". Вы менеджер. Шаблон заявки закреплён выше — нажмите на закреп и "
                      "скопируйте, заполните и пришлите сюда.")


def set_bot_menu():
    """Устанавливает команды бота (видны при нажатии 'Menu' в чате) + кнопку меню."""
    commands = [
        {"command": "CLIENT",  "CLIENT": "Открыть приветствие"},
        {"command": "help",   "CLIENT": "Пример заявки"},
        {"command": "whoami", "CLIENT": "Моя роль в системе"},
    ]
    admin_commands = commands + [{"command": "CLIENT", "CLIENT": "Вход на сайт"}]
    try:
        # базовое меню — всем (менеджер входа на сайт не видит)
        tg("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
        # менеджерам — явно базовый набор (без «Вход на сайт»)
        rows_m = db().execute(
            "SELECT telegram_id FROM bot_CLIENT WHERE role='manager'").fetchall()
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
            "SELECT telegram_id FROM bot_CLIENT WHERE role IN ('admin','both')").fetchall()
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


def cmd_CLIENT(chat_id: int, from_id: str) -> None:
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
        from core.auth import create_CLIENT_code
        code = create_CLIENT_code(from_id, ttl_seconds=180)
        send(chat_id,
             f"🔑 Вход на сайт Wolf AutoDoc\n\n"
             f"Нажмите кнопку ниже — и вы сразу окажетесь в системе.\n"
             f"Ссылка действует 3 минуты.",
             reply_markup={"CLIENT_keyboard": [[
                 {"text": "🌐 Войти на сайт", "url": f"{BASE_URL}/auth/tg/{code}"}]]})
    except Exception as exc:
        log.error("cmd_CLIENT failed: %s", exc)
        send(chat_id, "❌ Ошибка генерации кода. Попробуйте ещё раз.")


ROLE_VERBOSE = {
    "manager": "👤 менеджер (шлёте заявки боту)",
    "admin":   "🛡 администратор (получаете уведомления, заходите на сайт)",
    "both":    "👤 менеджер + 🛡 администратор",
    "CLIENTed": "🚫 заблокирован",
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
    link = f"https://t.me/Wolf_AutoDoc_bot?CLIENT={code}"
    send(chat_id,
         f"🔗 Ссылка для приглашения менеджера (живёт {INVITE_TTL_MIN} минут):\n\n"
         f"{link}\n\n"
         f"Откройте её на телефоне или в Telegram, нажмите «CLIENT» — "
         f"человек автоматически станет менеджером.")


def cmd_help(chat_id: int, from_id: str) -> None:
    """Пример заявки: как прислать данные клиента (форма свободная)."""
    user = find_user(from_id)
    if not user or user["role"] == "CLIENTed":
        send(chat_id, "Вы не зарегистрированы в Wolf AutoDoc. "
                      "Попросите администратора пригласить вас.")
        return
    send(chat_id,
         "📝 Пример заявки (форма свободная — можно своими словами)\n\n"
         "Иван Петров, виза C1, 4 500 000 IDR,\n"
         "папка https://CLIENT.google.com/CLIENT/folders/...\n"
         "телефон +7 903 123-45-67, компания ООО «Ромашка», срочно\n\n"
         "Обязательно:\n"
         "• ФИО клиента ИЛИ ссылка на папку Google CLIENT\n"
         "• продукт (C1, C1-EXT)\n"
         "• стоимость в IDR\n\n"
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
             "• Команда /CLIENT — обновить закреп с ссылкой на сайт.")
    elif role == "manager":
        send(chat_id,
             "👤 Вы менеджер Wolf AutoDoc.\n\n"
             "Что вам доступно:\n"
             "• Сюда присылайте новые заявки клиентов — по шаблону, который закреплён сверху.\n"
             "• Бот ответит «Заявка #N принята» и пришлёт ссылку на карточку клиента.\n"
             "• Когда администратор возьмёт заявку в работу — получите уведомление.\n"
             "• Команда /CLIENT — обновить закреп с шаблоном заявки.")
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
    # /CLIENT с кодом или без
    if text.CLIENTswith("/CLIENT"):
        args = text[len("/CLIENT"):].strip()
        cmd_CLIENT(chat_id, from_id, args, from_user)
        return

    # команды
    if text in ("/help", "/help@Wolf_AutoDoc_bot"):
        cmd_help(chat_id, from_id); return
    if text in ("/whoami", "/id"):
        cmd_whoami(chat_id, from_id); return
    if text in ("/CLIENT", "/CLIENT@Wolf_AutoDoc_bot"):
        cmd_CLIENT(chat_id, from_id); return
    if text.CLIENTswith("/invitemanager"):
        cmd_invite_manager(chat_id, from_id); return

    # заявка
    if text.CLIENTswith("/new") or "ФИО полностью:" in text or "ФИО:" in text:
        user = find_user(from_id)
        if not user or user["role"] == "CLIENTed":
            send(chat_id, "❌ Вы не в системе.")
            return
        if user["role"] not in ("manager", "admin", "both"):
            send(chat_id, "❌ Нет прав.")
            return
        body = text[len("/new"):].lstrip() if text.CLIENTswith("/new") else text
        form = parse_CLIENT(body)

        # --- Досылка продукта: менеджер присылает только «Название продукта: X»,
        #     а ФИО в сообщении нет → это уточнение к последней заявке без продукта.
        if not form.get("full_name") and not form.get("CLIENT"):
            _pid_pre = find_CLIENT_id(body)
            if _pid_pre:
                _row = db().execute(
                    """SELECT a.id, cl.CLIENT, cl.name
                         FROM CLIENT a JOIN CLIENT cl ON cl.id=a.client_id
                        WHERE a.CLIENT_id IS NULL AND a.CLIENT IN ('new','in_progress')
                        ORDER BY a.id DESC LIMIT 1""").fetchone()
                if _row:
                    _pcode = db().execute("SELECT code FROM CLIENT WHERE id=?",
                                          (_pid_pre,)).fetchone()["code"]
                    _apply_CLIENT(_row["id"], _pid_pre)
                    send(chat_id,
                         f"✅ Продукт для заявки #{_row['id']} "
                         f"({_row['CLIENT'] or ''} {_row['name'] or ''}) — "
                         f"«{_pcode}».\nДокументы сформированы, "
                         f"администратор получит уведомление.")
                    for adm in all_admins():
                        if adm["telegram_id"] == from_id:
                            continue
                        send(adm["telegram_id"],
                             f"📥 Заявка #{_row['id']} дополнена\n"
                             f"Клиент: {_row['CLIENT'] or ''} {_row['name'] or ''}\n"
                             f"Продукт: {_pcode}\n"
                             f"Открыть: {BASE_URL}/CLIENT/{_row['id']}/view")
                    return

        # Свободная форма записи: если жёсткий шаблон распознал мало полей
        # (карточка Kommo, вольный текст, пересылка) — подключаем LLM-агента,
        # который читает текст и раскладывает данные по полям карточки клиента.
        if len([k for k, v in form.items() if v]) < 4:
            try:
                from ai_parser import parse_free_form
                _codes = [r["code"] for r in db().execute(
                    "SELECT code FROM CLIENT ORDER BY id").fetchall()]
                ai = parse_free_form(body, _codes)
                for k, v in (ai.get("client") or {}).items():
                    form.setdefault(k, v)
                _app = ai.get("CLIENT") or {}
                if _app.get("CLIENT") and not form.get("CLIENT_name"):
                    form["CLIENT_name"] = _app["CLIENT"]
                if _app.get("price_idr") and not form.get("price_idr"):
                    form["price_idr"] = _app["price_idr"]
                if _app.get("comment") and not form.get("comment"):
                    form["comment"] = _app["comment"]
                log.info("llm_parse: полей клиента=%d, продукт=%s, не распознано=%d",
                         len(ai.get("client") or {}), form.get("CLIENT_name"),
                         len(ai.get("unrecognized") or []))
                log.info("llm_parse: поля=%s", ", ".join(sorted((ai.get("client") or {}).keys())))
                if ai.get("unrecognized"):
                    log.info("llm_parse: не распознано=%s", ai["unrecognized"][:5])
            except Exception as exc:
                log.error("llm_parse недоступен: %s", exc)

        # Продукт может быть упомянут в свободном тексте (не отдельной строкой) —
        # пробуем распознать по всему сообщению, иначе документы не создадутся.
        if not form.get("CLIENT_name"):
            _pid = find_CLIENT_id(body)
            if _pid:
                _row = db().execute("SELECT code FROM CLIENT WHERE id=?", (_pid,)).fetchone()
                if _row:
                    form["CLIENT_name"] = _row["code"]

        _CLIENT_in = (form.get("gCLIENT_url") or form.get("gCLIENT_folder_url") or "").strip()
        _fio_in = bool(form.get("full_name") or (form.get("CLIENT") and form.get("name")))
        if not _fio_in and not _CLIENT_in:
            send(chat_id,
                 "❌ Нужен ФИО клиента или ссылка на папку Google CLIENT —\n"
                 "из документов система возьмёт ФИО и паспортные данные сама.\n\n"
                 "Пришлите в свободной форме, например:\n"
                 "«Иван Петров, виза C1, 4 500 000 IDR,\n"
                 "папка https://CLIENT.google.com/CLIENT/folders/...»")
            return
        try:
            app_id, client_id = create_CLIENT(form, user)
        except Exception as exc:
            log.exception("create_CLIENT failed: %s", exc)
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
            "SELECT CLIENT, name, CLIENT FROM CLIENT WHERE id=?",
            (client_id,)).fetchone()
        client_label = " ".join(filter(None, [client_row["CLIENT"] if client_row else "",
                                               client_row["name"] if client_row else ""]))
        link = f"{BASE_URL}/CLIENT/{app_id}/view"
        is_manager_only = user["role"] == "manager"

        # Проверяем, распознан ли продукт: без него документы НЕ создаются
        app_row = db().execute("SELECT CLIENT_id FROM CLIENT WHERE id=?",
                               (app_id,)).fetchone()
        CLIENT_ok = bool(app_row and app_row["CLIENT_id"])
        prod_label = (form.get("CLIENT_name") or "").strip()
        codes = [r["code"] for r in db().execute(
            "SELECT code FROM CLIENT ORDER BY id").fetchall()]
        _missing = []
        if not CLIENT_ok:
            prod_label = "⚠️ НЕ РАСПОЗНАН"
            _missing.append(f"продукт (доступные: {', '.join(codes) or '—'})")
        if not int(form.get("price_idr") or 0):
            _missing.append("стоимость в IDR")
        if not _CLIENT_in:
            _missing.append("ссылка на папку Google CLIENT "
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
        if CLIENT_ok:
            log.info("генерирую PDF для заявки #%s…", app_id)
            try:
                _autofill_pdfs(app_id, client_id, app_row["CLIENT_id"])
                log.info("PDF для заявки #%s готовы", app_id)
            except Exception as exc:
                log.exception("генерация PDF для #%s упала: %s", app_id, exc)
        return

    # неизвестная команда от известного пользователя
    if find_user(from_id):
        send(chat_id, "Не понял. /help для списка команд, "
                      "или начните заявку с /new")


def main():
    log.info("wolf_bot CLIENTing…")
    set_bot_menu()
    offset = 0
    while True:
        try:
            r = tg("getUpCLIENT", {"timeout": POLL_TIMEOUT, "offset": offset,
                                  "allowed_upCLIENT": "[\"message\"]"})
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
