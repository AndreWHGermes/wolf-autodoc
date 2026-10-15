"""Уведомления из Wolf в Telegram бот.

Используется из wolf-crm (blocks/dashboard, app.py карточка клиента).
Отправляет сообщение менеджеру, который прислал заявку, и админам.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import urllib.parse
import urllib.request

DB_PATH = "/opt/wolf_v2/data/wolf.db"
BASE_URL = "http://103.90.75.37"   # через nginx (порт 80), ссылки работают без порта
log = logging.getLogger("wolf_bot")


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _token() -> str:
    c = _conn()
    row = c.execute("SELECT value FROM settings WHERE key='bot_token'").fetchone()
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
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
            if not result.get("ok"):
                log.warning("sendMessage not ok: %s", result)
                return False
            return True
    except Exception as exc:                            # noqa: BLE001
        log.warning("sendMessage failed: %s (получатель %s)", exc, chat_id)
        return False


def _app(app_id: int) -> sqlite3.Row | None:
    c = _conn()
    c.row_factory = sqlite3.Row
    row = c.execute("""SELECT a.id, a.client_id, a.product_id, a.status,
                                 c.surname, c.name, p.name AS product_name,
                                 bm.telegram_id AS manager_tg
                          FROM applications a
                          LEFT JOIN clients c ON c.id=a.client_id
                          LEFT JOIN products p ON p.id=a.product_id
                          LEFT JOIN bot_managers bm ON bm.id=a.bot_manager_id
                          WHERE a.id=?""", (app_id,)).fetchone()
    c.close()
    return row


def notify_manager_taken(app_id: int) -> None:
    """Шлёт менеджеру 'Заявка #N принята в работу'."""
    a = _app(app_id)
    if not a or not a["manager_tg"]:
        return
    client_label = " ".join(filter(None, [a["surname"] or "", a["name"] or ""])) or "—"
    text = (f"✅ Заявка #{a['id']} принята в работу.\n"
            f"Клиент: {client_label}\n"
            f"Продукт: {a['product_name'] or '—'}\n"
            f"Карточка: {BASE_URL}/applications/{a['id']}/review")
    send(a["manager_tg"], text)


def notify_admins_new_app(app_id: int, manager_name: str | None = None) -> None:
    """Шлёт всем admin/both сообщение о новой заявке."""
    a = _app(app_id)
    if not a:
        return
    client_label = " ".join(filter(None, [a["surname"] or "", a["name"] or ""])) or "—"
    # папка клиента из заявки: администратор видит, что лежало раньше и куда лягут наши документы
    client_folder = ""
    try:
        c = _conn()
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT gdrive_url FROM applications WHERE id=?", (app_id,)).fetchone()
        c.close()
        client_folder = ((r["gdrive_url"] if r else "") or "").strip()
    except Exception:                              # noqa: BLE001
        client_folder = ""
    text = (f"📥 Новая заявка #{a['id']}\n"
            f"Клиент: {client_label}\n"
            f"Продукт: {a['product_name'] or '—'}\n"
            f"Менеджер: {manager_name or '—'}\n"
            + (f"Папка клиента: {client_folder}\n" if client_folder else "")
            + f"Открыть: {BASE_URL}/applications/{a['id']}/review")
    conn = _conn()
    rows = conn.execute(
        "SELECT telegram_id FROM bot_managers WHERE role IN ('admin','both')").fetchall()
    conn.close()
    buttons = []
    if client_folder:
        buttons.append([{"text": "📂 Папка клиента", "url": client_folder}])
    buttons.append([{"text": f"📂 Открыть заявку #{a['id']}",
                     "url": f"{BASE_URL}/applications/{a['id']}/review"}])
    for r in rows:
        send(r["telegram_id"], text, reply_markup={"inline_keyboard": buttons})


def notify_manager_done(app_id: int, folder_link: str | None = None,
                        seconds: float | None = None) -> None:
    """Шлёт менеджеру, создавшему заявку: документы готовы и загружены на Google Диск.

    folder_link — ссылка на папку заявки на Диске (её и показываем кнопкой).
    seconds — сколько секунд заняла обработка от приёма заявки до выгрузки на Диск.
    """
    a = _app(app_id)
    if not a or not a["manager_tg"]:
        return
    client_label = " ".join(filter(None, [a["surname"] or "", a["name"] or ""])) or "—"
    link = (folder_link or "").strip() or f"{BASE_URL}/applications/{a['id']}/review"
    timing = ("⏱ Время обработки: %.0f сек (от получения заявки до выгрузки на Google Диск)\n"
              % seconds) if seconds else ""
    text = (f"\U0001F4E6 Документы по заявке #{a['id']} готовы и загружены на Google Диск.\n"
            f"Клиент: {client_label}\n"
            f"Продукт: {a['product_name'] or '—'}\n"
            f"{timing}"
            f"Папка с документами: {link}")
    send(a["manager_tg"], text,
         reply_markup={"inline_keyboard": [[
             {"text": "\U0001F4C2 Открыть папку с документами", "url": link},
             {"text": "Карточка заявки", "url": f"{BASE_URL}/applications/{a['id']}/review"}]]})


def notify_admins_done(app_id: int, folder_link: str | None = None,
                       client_link: str | None = None, seconds: float | None = None,
                       docs: int | None = None) -> None:
    """Шлёт администраторам итог: что готово, сколько заняло, где смотреть.

    client_link — папка клиента, которая была в заявке: в ней менеджер видит и прежние
    документы, и нашу новую папку с собранными документами.
    folder_link — наша папка с документами.
    """
    a = _app(app_id)
    if not a:
        return
    client_label = " ".join(filter(None, [a["surname"] or "", a["name"] or ""])) or "—"
    c = _conn()
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT gdrive_url FROM applications WHERE id=?", (app_id,)).fetchone()
    c.close()
    if not client_link:
        client_link = (row["gdrive_url"] if row else "") or ""
    our = (folder_link or "").strip()
    timing = ("⏱ Время работы: %.0f сек (от момента получения заявки до появления документов "
              "на Google Диске)\n" % seconds) if seconds else ""
    text = (f"\U0001F4E6 Заявка #{app_id} обработана полностью.\n"
            f"Клиент: {client_label}\n"
            f"Продукт: {a['product_name'] or '—'}\n"
            f"{('Документов выгружено: %d\n' % docs) if docs else ''}"
            f"{timing}"
            f"Наша папка с документами: {our or '—'}\n"
            f"Папка клиента (что было раньше): {client_link or '—'}")
    buttons = []
    if our:
        buttons.append([{"text": "\U0001F4C2 Наша папка с документами", "url": our}])
    if client_link:
        buttons.append([{"text": "\U0001F5C2 Папка клиента", "url": client_link}])
    buttons.append([{"text": "Карточка заявки", "url": f"{BASE_URL}/applications/{app_id}/review"}])
    conn = _conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT telegram_id FROM bot_managers WHERE role IN ('admin','both')"
                        " AND telegram_id IS NOT NULL AND telegram_id != ''").fetchall()
    conn.close()
    for r in rows:
        send(r["telegram_id"], text, reply_markup={"inline_keyboard": buttons})
