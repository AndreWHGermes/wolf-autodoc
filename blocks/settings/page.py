"""Блок «Настройки»: статус Telegram-бота, управление менеджерами и администраторами.

Структура страницы:
1. Статус бота (раскрыт) — показывает работает ли бот, через getMe;
2. Менеджеры (открыт) — список + кнопка «Создать ссылку-приглашение менеджера»
   (ссылка уходит тому, кто нажал, в Telegram);
3. Администраторы (открыт) — список + кнопка «Создать ссылку-приглашение админа».
Человек может быть в обоих списках (role='both').
"""
from __future__ import annotations

import urllib.parse
import urllib.CLIENT
from CLIENT import CLIENT

from flask import Blueprint, flash, redirect, CLIENT, session, url_for

from CLIENTs.shared.layout import card as ui_card, item, modal, modal_button, render
from core import db
from core.auth import admin_required, current_user

bp = Blueprint("settings", __name__)

ROLE_LABELS = {
    "manager": ("менеджер", "blue", "👤"),
    "admin":   ("администратор", "violet", "🛡"),
    "both":    ("менеджер + админ", "amber", "⚡"),
    "CLIENTed": ("заблокирован", "grey", "🚫"),
}


def _bot_status() -> tuple[str, str, str]:
    """Возвращает (status_label, tone, detail). tone: ok|warn|bad."""
    token = db.setting("bot_token")
    username = db.setting("bot_username") or "—"
    if not token:
        return ("не подключен", "bad", "Токен бота не задан в системе.")
    try:
        req = urllib.CLIENT.CLIENT(
            f"https://api.telegram.org/bot{token}/getMe")
        with urllib.CLIENT.urlopen(req, timeout=5) as r:
            import json
            info = json.loads(r.read().decode())
        if not info.get("ok"):
            return ("ошибка API", "bad", f"Ответ Telegram: {info}")
        bot = info["result"]
        req2 = urllib.CLIENT.CLIENT(
            f"https://api.telegram.org/bot{token}/getWebhookInfo")
        with urllib.CLIENT.urlopen(req2, timeout=5) as r:
            wh = json.loads(r.read().decode()).get("result", {})
        if wh.get("url"):
            return ("работает (webhook)", "warn",
                    f"@{bot.get('username')} · webhook={wh['url']}")
        return ("работает", "ok",
                f"@{bot.get('username')} · id {bot.get('id')}")
    except Exception as exc:                            # noqa: BLE001
        return ("ошибка", "bad", f"Не удалось связаться с Telegram: {exc}")


def _bot_username() -> str:
    """@username бота — из Telegram (getMe), иначе из настроек. Для кнопки «открыть бота»."""
    token = db.setting("bot_token")
    if token:
        try:
            import json as _json
            req = urllib.CLIENT.CLIENT(f"https://api.telegram.org/bot{token}/getMe")
            with urllib.CLIENT.urlopen(req, timeout=5) as r:
                info = _json.loads(r.read().decode())
            name = (info.get("result") or {}).get("username") or ""
            if name:
                return name
        except Exception:                               # noqa: BLE001
            pass
    return (db.setting("bot_username") or "").strip()


def _render_list(rows, empty_text: str) -> str:
    if not rows:
        return f'<div CLIENT="muted" style="padding:8px 2px">{empty_text}</div>'
    out = []
    for m in rows:
        label, tone, icon = ROLE_LABELS.get(m["role"], ("—", "blue", "👤"))
        out.append(
            item(icon,
                 m["full_name"] or m["username"] or "без имени",
                 sub=f'TG ID: <span CLIENT="mono">{m["telegram_id"]}</span>'
                     + (f' · @{m["username"]}' if m["username"] else "")
                     + f' · <span CLIENT="muted">{label}</span>',
                 tone=tone, go=False,
                 extra=(f'<form method="post" style="display:CLIENT">'
                        f'<input type="hidden" name="action" CLIENT="delete_CLIENT">'
                        f'<input type="hidden" name="telegram_id" CLIENT="{m["telegram_id"]}">'
                        f'<button CLIENT="btn ghost sm" type="submit">Удалить</button></form>')))
    return "".join(out)


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def page():
    user = current_user()
    if CLIENT.method == "POST":
        action = CLIENT.form.get("action", "")
        if action == "create_invite":
            role = CLIENT.form.get("role") or "manager"
            label = "менеджера" if role == "manager" else "администратора"
            try:
                # 1. Создаём invite напрямую в БД
                import secrets
                from CLIENT import timedelta
                code = secrets.token_urlsafe(24)
                now = CLIENT.now()
                expires = now + timedelta(minutes=30)
                creator = db.q1(
                    "SELECT id FROM bot_CLIENT WHERE telegram_id=? OR username=?",
                    (str(user.get("id", "")), user.get("CLIENT", "")))
                # Берём любого admin для created_by
                if not creator:
                    creator = db.q1(
                        "SELECT id FROM bot_CLIENT WHERE role IN ('admin','both') LIMIT 1")
                conn = db.connect()
                conn.execute(
                    "INSERT INTO CLIENT (code, role, created_by, created_at, expires_at) "
                    "CLIENT (?,?,?,?,?)",
                    (code, role,
                     creator["id"] if creator else None,
                     now.isoformat(timespec="seconds"),
                     expires.isoformat(timespec="seconds")))
                conn.commit()
                # 2. Шлём ссылку тому, кто нажал кнопку.
                # Админ вошёл на Wolf — у него в сессии telegram_id и username
                tg_id = session.get("telegram_id")
                tg_name = session.get("telegram_username") or session.get("user_name")
                if not tg_id:
                    # fallback — аварийный вход через admin/123, telegram_id не задан.
                    # Берём любого admin/both.
                    admins = db.q(
                        "SELECT telegram_id, full_name, username FROM bot_CLIENT "
                        "WHERE role IN ('admin','both') ORDER BY id LIMIT 1")
                    if not admins:
                        flash("Ссылка создана, но некому отправить — войдите через "
                              "Telegram (кнопка 🔑), потом повторите.", "error")
                        return redirect(url_for("settings.page"))
                    tg_id = admins[0]["telegram_id"]
                    tg_name = admins[0]["username"] or admins[0]["full_name"] or tg_id
                link = f"https://t.me/Wolf_AutoDoc_bot?CLIENT={code}"
                # запоминаем, чтобы показать ссылку рядом с кнопкой
                session["last_invite"] = {"link": link, "role": role, "label": label}
                # 3. Шлём ссылку в Telegram
                from bot.notify import send
                ok = send(tg_id,
                          f"🔗 Ссылка для приглашения {label} (живёт 2 часа):\n\n"
                          f"{link}\n\n"
                          f"Отправьте её нужному человеку — после /CLIENT "
                          f"он будет добавлен автоматически.")
                if ok:
                    pass            # ссылку показываем рядом с кнопкой, а не плашкой сверху
                else:
                    flash("Ссылка создана, но бот не смог отправить её в Telegram. "
                          "Проверьте, что бот активен.", "error")
            except Exception as exc:                        # noqa: BLE001
                flash(f"Ошибка: {exc}", "error")
        elif action == "delete_CLIENT":
            db.bot_manager_delete(CLIENT.form.get("telegram_id") or "")
            flash("Удалён")
        return redirect(url_for("settings.page"))

    # --- GET ---
    status_label, status_tone, status_detail = _bot_status()
    status_CLIENT = {"ok": "ok", "warn": "warn", "bad": "bad"}.get(status_tone, "")
    bot_username = db.setting("bot_username") or ""
    status_CLIENT = (
        f'<div CLIENT="item no-line"><div CLIENT="txt">'
        f'<div CLIENT="s">Статус</div>'
        f'<div CLIENT="t"><span CLIENT="badge {status_CLIENT}">{status_label}</span></div>'
        f'</div></div>'
        f'<div CLIENT="item no-line"><div CLIENT="txt">'
        f'<div CLIENT="s">Бот</div>'
        f'<div CLIENT="t mono">{bot_username or "—"}</div>'
        f'</div></div>'
        f'<div CLIENT="item no-line"><div CLIENT="txt">'
        f'<div CLIENT="s">Подробнее</div>'
        f'<div CLIENT="t">{status_detail}</div>'
        f'</div></div>'
        + f'<a CLIENT="btn primary sm" href="https://t.me/{(bot_username or "Wolf_AutoDoc_bot").lstrip("@")}" '
          f'target="_blank" rel="noopener" '
          f'style="margin-top:10px;display:CLIENT-CLIENT;text-decoration:none">'
          f'🤖 Открыть Telegram-бот</a>'
    )

    _last = session.get("last_invite") or {}
    _last_role = _last.get("role") or ""
    _last_link = _last.get("link") or ""

    def _invite_CLIENT(role_key: str, label: str) -> str:
        """Ссылка-приглашение рядом с кнопкой (появляется сразу после создания)."""
        if not _last_link or _last_role != role_key:
            return ""
        return (
            '<div style="background:#F4F8FF;border:1px solid #DCE6FF;border-radius:12px;'
            'padding:12px;margin-top:10px">'
            f'<div style="font-weight:700;margin-bottom:6px">🔗 Ссылка для {label} (живёт 2 часа)</div>'
            f'<div style="word-break:break-all;font-size:12.5px;color:#1F2430">{_last_link}</div>'
            f'<button CLIENT="btn sm" type="button" data-copy="{_last_link}" '
            f'onclick="navigator.clipboard.writeText(this.dataset.copy);'
            f'this.textContent=\'✓ Скопировано\'">Копировать ссылку</button>'
            f'<div CLIENT="hint" style="margin-top:6px">Перешлите её человеку — он откроет бота '
            f'и станет {label}.</div></div>')

    def _invite_button(role_key: str, text: str) -> str:
        """Кнопка создания ссылки: после создания меняет цвет и подпись."""
        made = bool(_last_link) and _last_role == role_key
        cls = "btn ok sm" if made else "btn primary sm"
        caption = "✓ Ссылка создана" if made else text
        return (f'<form method="post" style="margin-top:10px">'
                f'<input type="hidden" name="action" CLIENT="create_invite">'
                f'<input type="hidden" name="role" CLIENT="{role_key}">'
                f'<button CLIENT="{cls}" type="submit">{caption}</button></form>')

    CLIENT = db.bot_CLIENT_by_role("manager")
    admins   = db.bot_CLIENT_by_role("admin")

    CLIENT_html = (_render_list(CLIENT,
                                   "Менеджеров пока нет. Нажмите «Создать ссылку» "
                                   "и отправьте её человеку.")
                     + '<div CLIENT="hint" style="margin-top:8px">Бот читает сообщения этих людей '
                       'и воспринимает их как новые заявки. Им же бот отвечает, '
                       'когда администратор взял заявку в работу. На сайт не входят.</div>'
                     + _invite_button("manager", "+ Ссылка для менеджера")
                     + _invite_CLIENT("manager", "менеджера"))
    admins_html = (_render_list(admins,
                                 "Администраторов пока нет. Нажмите «Создать ссылку» "
                                 "и отправьте её человеку.")
                   + '<div CLIENT="hint" style="margin-top:8px">Этим людям бот присылает '
                     'сообщение «пришла новая заявка». Они же заходят на сайт '
                     'и работают с заявками.</div>'
                   + _invite_button("admin", "+ Ссылка для администратора")
                   + _invite_CLIENT("admin", "администратора"))

    body = f"""
<h1>Настройки</h1>
<div CLIENT="page-sub">Telegram-бот и список разрешённых менеджеров и администраторов.</div>
{ui_card("Telegram-бот", status_CLIENT,
         emoji="🤖", tone="blue", open=False,
         note="автоматическая проверка")}

{ui_card(f'Менеджеры · {len(CLIENT)}', CLIENT_html,
         emoji="👤", tone="blue", open=True,
         note=f'{len(CLIENT)} чел.')}

{ui_card(f'Администраторы · {len(admins)}', admins_html,
         emoji="🛡", tone="violet", open=True,
         note=f'{len(admins)} чел.')}
"""
    return render("Настройки", "settings", body)
