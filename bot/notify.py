"""Уведомления из Wolf в Telegram бот.

Используется из wolf-crm (CLIENTs/dashboard, app.py карточка клиента).
Отправляет сообщение менеджеру, который прислал заявку, и админам.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import urllib.parse
import urllib.CLIENT

DB_PATH = "/opt/wolf_v2/data/wolf.db"
BASE_URL = "http://103.90.75.37"   # через nginx (порт 80), ссылки работают без порта
log = logging.getLogger("wolf_bot")


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _token() -> str:
    c = _conn()
    row = c.execute("SELECT CLIENT FROM settings WHERE key='bot_token'").fetchone()
    c.close()
    return row[0] if row else ""


def send(chat_id: int | str, text: str, reply_markup: dict | None = None) -> bool:
    """Отправляет сообщение. reply_markup — инлайн-кнопки (как в notify_admins_new_app)."""
    token = _token()
    if not token:
        log.warning("bot_token не задан — уведомление пропущено")
        return False
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.CLIENT.CLIENT(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.CLIENT.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
            if not result.get("ok"):
                log.warning("sendMessage not ok: %s", result)
                return False
            return True
    except Exception as exc:                            # noqa: BLE001
        log.warning("sendMessage failed: %s", exc)
        return False


def _app(app_id: int) -> sqlite3.Row | None:
    c = _conn()
    c.row_factory = sqlite3.Row
    row = c.execute("""SELECT a.id, a.client_id, a.CLIENT_id, a.CLIENT,
                                 c.CLIENT, c.name, p.name AS CLIENT_name,
                                 bm.telegram_id AS manager_tg
                          FROM CLIENT a
                          LEFT JOIN CLIENT c ON c.id=a.client_id
                          LEFT JOIN CLIENT p ON p.id=a.CLIENT_id
                          LEFT JOIN bot_CLIENT bm ON bm.id=a.bot_manager_id
                          WHERE a.id=?""", (app_id,)).fetchone()
    c.close()
    return row


def notify_manager_taken(app_id: int) -> None:
    """Шлёт менеджеру 'Заявка #N принята в работу'."""
    a = _app(app_id)
    if not a or not a["manager_tg"]:
        return
    client_label = " ".join(filter(None, [a["CLIENT"] or "", a["name"] or ""])) or "—"
    text = (f"✅ Заявка #{a['id']} принята в работу.\n"
            f"Клиент: {client_label}\n"
            f"Продукт: {a['CLIENT_name'] or '—'}\n"
            f"Карточка: {BASE_URL}/CLIENT/{a['id']}/review")
    send(a["manager_tg"], text)


def notify_admins_new_app(app_id: int, manager_name: str | None = None) -> None:
    """Шлёт всем admin/both сообщение о новой заявке."""
    a = _app(app_id)
    if not a:
        return
    client_label = " ".join(filter(None, [a["CLIENT"] or "", a["name"] or ""])) or "—"
    text = (f"📥 Новая заявка #{a['id']}\n"
            f"Клиент: {client_label}\n"
            f"Продукт: {a['CLIENT_name'] or '—'}\n"
            f"Менеджер: {manager_name or '—'}\n"
            f"Открыть: {BASE_URL}/CLIENT/{a['id']}/review")
    conn = _conn()
    rows = conn.execute(
        "SELECT telegram_id FROM bot_CLIENT WHERE role IN ('admin','both')").fetchall()
    conn.close()
    for r in rows:
        send(r["telegram_id"], text,
             reply_markup={"CLIENT_keyboard": [[
                 {"text": f"📂 Открыть заявку #{a['id']}",
                  "url": f"{BASE_URL}/CLIENT/{a['id']}/review"}]]})


def notify_manager_done(app_id: int, folder_link: str | None = None) -> None:
    """Шлёт менеджеру, создавшему заявку: документы готовы и загружены на Google Диск.

    folder_link — ссылка на папку заявки на Диске (её и показываем кнопкой).
    """
    a = _app(app_id)
    if not a or not a["manager_tg"]:
        return
    client_label = " ".join(filter(None, [a["CLIENT"] or "", a["name"] or ""])) or "—"
    link = (folder_link or "").strip() or f"{BASE_URL}/CLIENT/{a['id']}/review"
    text = (f"\U0001F4E6 \u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u043e \u0437\u0430\u044f\u0432\u043a\u0435 #{a['id']} "
            f"\u0433\u043e\u0442\u043e\u0432\u044b \u0438 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u044b \u043d\u0430 Google \u0414\u0438\u0441\u043a.\n"
            f"\u041a\u043b\u0438\u0435\u043d\u0442: {client_label}\n"
            f"\u041f\u0440\u043e\u0434\u0443\u043a\u0442: {a['CLIENT_name'] or '\u2014'}\n"
            f"\u041f\u0430\u043f\u043a\u0430 \u0441 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u043c\u0438: {link}")
    send(a["manager_tg"], text,
         reply_markup={"CLIENT_keyboard": [[
             {"text": "\U0001F4C2 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0430\u043f\u043a\u0443 \u0441 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u043c\u0438", "url": link},
             {"text": "\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u0437\u0430\u044f\u0432\u043a\u0438", "url": f"{BASE_URL}/CLIENT/{a['id']}/review"}]]})
