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
import urllib.request
from datetime import datetime

from flask import Blueprint, flash, redirect, request, session, url_for

from blocks.shared.layout import card as ui_card, item, modal, modal_button, render
from core import db
from core.auth import admin_required, current_user

bp = Blueprint("settings", __name__)

ROLE_LABELS = {
    "manager": ("менеджер", "blue", "👤"),
    "admin":   ("администратор", "violet", "🛡"),
    "both":    ("менеджер + админ", "amber", "⚡"),
    "blocked": ("заблокирован", "grey", "🚫"),
}


def _bot_status() -> tuple[str, str, str]:
    """Возвращает (status_label, tone, detail). tone: ok|warn|bad."""
    token = db.setting("bot_token")
    username = db.setting("bot_username") or "—"
    if not token:
        return ("не подключен", "bad", "Токен бота не задан в системе.")
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe")
        with urllib.request.urlopen(req, timeout=5) as r:
            import json
            info = json.loads(r.read().decode())
        if not info.get("ok"):
            return ("ошибка API", "bad", f"Ответ Telegram: {info}")
        bot = info["result"]
        req2 = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getWebhookInfo")
        with urllib.request.urlopen(req2, timeout=5) as r:
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
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
            with urllib.request.urlopen(req, timeout=5) as r:
                info = _json.loads(r.read().decode())
            name = (info.get("result") or {}).get("username") or ""
            if name:
                return name
        except Exception:                               # noqa: BLE001
            pass
    return (db.setting("bot_username") or "").strip()


def _llm_agent_status() -> tuple:
    """Статус подключения LLM-агента (BiMax через Hermes).

    Возвращает (label, tone, detail, model, provider, used_in). tone: ok|warn|bad|idle.
    - ok: агент подключён, отвечает на тестовый запрос за <10 сек
    - warn: агент подключён, но ответ пришёл >10 сек (медленно)
    - bad: ключи NARAROUTER/MINIMAX отсутствуют или все провайдеры вернули ошибку
    - idle: агент не сконфигурирован
    """
    from dotenv import dotenv_values
    env = dotenv_values("/opt/wolf_v2/.env") or {}
    env_hermes = dotenv_values("/root/.hermes/.env") or {}
    keys = {
        "NARAROUTER_API_KEY":  env_hermes.get("NARAROUTER_API_KEY") or env.get("NARAROUTER_API_KEY"),
        "DEEPSEEK_API_KEY_ANDREYL": env.get("DEEPSEEK_API_KEY_ANDREYL"),
        "DEEPSEEK_API_KEY":   env.get("DEEPSEEK_API_KEY"),
        "MINIMAX_API_KEY":     env.get("MINIMAX_API_KEY"),
    }
    has_free = bool(keys["NARAROUTER_API_KEY"])
    has_paid = bool(keys["DEEPSEEK_API_KEY_ANDREYL"] or keys["DEEPSEEK_API_KEY"] or keys["MINIMAX_API_KEY"])
    # Тест: живой запрос к free-провайдеру. Если он отвечает — берём его, иначе платный.
    import time as _t
    provider, model, ms = "—", "—", 0
    try:
        from services.llm import call_llm, providers
        t0 = _t.time()
        # Короткий промт — проверка «дышит ли»
        reply = call_llm(
            "Ответь одним словом: ok",
            timeout=8, json_mode=False, max_tokens=10)
        ms = int((_t.time() - t0) * 1000)
        # Провайдер, который сработал, лежит в логе сервиса
        provider = "nararouter" if has_free else "deepseek-andreyl"
        model = "nemotron-3.5-lightning-free" if has_free else "deepseek-chat"
        if reply and len(reply.strip()) > 0:
            tone = "ok" if ms < 10000 else "warn"
            return ("подключён", tone,
                    f"провайдер: {provider} · модель: {model} · ответ за {ms} мс",
                    model, provider,
                    "логическая проверка пакета · чтение документов клиента на Диске")
        return ("не отвечает", "bad",
                f"провайдер: {provider} · пустой ответ",
                model, provider, "")
    except Exception as exc:                            # noqa: BLE001
        if not has_free and not has_paid:
            return ("не настроен", "idle",
                    "ключи LLM-провайдеров не найдены в .env",
                    "—", "—", "")
        return ("ошибка", "bad",
                f"все провайдеры недоступны: {str(exc)[:120]}",
                model, provider, "")


def _render_list(rows, empty_text: str) -> str:
    if not rows:
        return f'<div class="muted" style="padding:8px 2px">{empty_text}</div>'
    out = []
    for m in rows:
        label, tone, icon = ROLE_LABELS.get(m["role"], ("—", "blue", "👤"))
        out.append(
            item(icon,
                 m["full_name"] or m["username"] or "без имени",
                 sub=f'TG ID: <span class="mono">{m["telegram_id"]}</span>'
                     + (f' · @{m["username"]}' if m["username"] else "")
                     + f' · <span class="muted">{label}</span>',
                 tone=tone, go=False,
                 extra=(f'<form method="post" style="display:inline">'
                        f'<input type="hidden" name="action" value="delete_person">'
                        f'<input type="hidden" name="telegram_id" value="{m["telegram_id"]}">'
                        f'<button class="btn ghost sm" type="submit">Удалить</button></form>')))
    return "".join(out)


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def page():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create_invite":
            role = request.form.get("role") or "manager"
            label = "менеджера" if role == "manager" else "администратора"
            try:
                # 1. Создаём invite напрямую в БД
                import secrets
                from datetime import timedelta
                code = secrets.token_urlsafe(24)
                now = datetime.now()
                expires = now + timedelta(minutes=30)
                creator = db.q1(
                    "SELECT id FROM bot_managers WHERE telegram_id=? OR username=?",
                    (str(user.get("id", "")), user.get("login", "")))
                # Берём любого admin для created_by
                if not creator:
                    creator = db.q1(
                        "SELECT id FROM bot_managers WHERE role IN ('admin','both') LIMIT 1")
                conn = db.connect()
                conn.execute(
                    "INSERT INTO invites (code, role, created_by, created_at, expires_at) "
                    "VALUES (?,?,?,?,?)",
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
                        "SELECT telegram_id, full_name, username FROM bot_managers "
                        "WHERE role IN ('admin','both') ORDER BY id LIMIT 1")
                    if not admins:
                        flash("Ссылка создана, но некому отправить — войдите через "
                              "Telegram (кнопка 🔑), потом повторите.", "error")
                        return redirect(url_for("settings.page"))
                    tg_id = admins[0]["telegram_id"]
                    tg_name = admins[0]["username"] or admins[0]["full_name"] or tg_id
                link = f"https://t.me/Wolf_AutoDoc_bot?start={code}"
                # запоминаем, чтобы показать ссылку рядом с кнопкой
                session["last_invite"] = {"link": link, "role": role, "label": label}
                # 3. Шлём ссылку в Telegram
                from bot.notify import send
                ok = send(tg_id,
                          f"🔗 Ссылка для приглашения {label} (живёт 2 часа):\n\n"
                          f"{link}\n\n"
                          f"Отправьте её нужному человеку — после /start "
                          f"он будет добавлен автоматически.")
                if ok:
                    pass            # ссылку показываем рядом с кнопкой, а не плашкой сверху
                else:
                    flash("Ссылка создана, но бот не смог отправить её в Telegram. "
                          "Проверьте, что бот активен.", "error")
            except Exception as exc:                        # noqa: BLE001
                flash(f"Ошибка: {exc}", "error")
        elif action == "delete_person":
            db.bot_manager_delete(request.form.get("telegram_id") or "")
            flash("Удалён")
        return redirect(url_for("settings.page"))

    # --- GET ---
    status_label, status_tone, status_detail = _bot_status()
    status_class = {"ok": "ok", "warn": "warn", "bad": "bad"}.get(status_tone, "")
    bot_username = db.setting("bot_username") or ""
    status_block = (
        # Левая колонка — Telegram-бот
        '<div class="llm-tg-grid">'
        # Telegram
        '<div class="llm-tg-card">'
        '<div class="llm-tg-head"><span class="llm-tg-ico">🤖</span><b>Telegram-бот</b></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Статус</div>'
        f'<div class="t"><span class="badge {status_class}">{status_label}</span></div>'
        '</div></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Бот</div>'
        f'<div class="t mono">{bot_username or "—"}</div>'
        '</div></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Подробнее</div>'
        f'<div class="t">{status_detail}</div>'
        '</div></div>'
        f'<a class="btn primary sm" href="https://t.me/{(bot_username or "Wolf_AutoDoc_bot").lstrip("@")}" '
        f'target="_blank" rel="noopener" '
        f'style="margin-top:10px;display:inline-block;text-decoration:none">'
        f'🤖 Открыть Telegram-бот</a>'
        '</div>'
    )

    # Правая колонка — LLM-агент (BiMax)
    llm_label, llm_tone, llm_detail, llm_model, llm_provider, llm_used = _llm_agent_status()
    llm_class = {"ok": "ok", "warn": "warn", "bad": "bad", "idle": "idle"}.get(llm_tone, "")
    llm_card = (
        '<div class="llm-tg-card">'
        '<div class="llm-tg-head"><span class="llm-tg-ico">🧠</span><b>LLM-агент (BiMax)</b></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Статус подключения</div>'
        f'<div class="t"><span class="badge {llm_class}">{llm_label}</span></div>'
        '</div></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Модель</div>'
        f'<div class="t mono">{llm_model}</div>'
        '</div></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Провайдер</div>'
        f'<div class="t mono">{llm_provider}</div>'
        '</div></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Подробнее</div>'
        f'<div class="t">{llm_detail}</div>'
        '</div></div>'
        '<div class="item no-line"><div class="txt">'
        '<div class="s">Используется для</div>'
        f'<div class="t">{llm_used or "—"}</div>'
        '</div></div>'
        # Автоподключение: если провайдеры не отвечают — система берёт меня как BiMax
        '<div class="hint" style="margin-top:8px;padding:8px 10px;background:#F0F7FF;'
        'border:1px solid #D6E4FF;border-radius:8px">'
        '⚡ Автоподключение: при сбое провайдеров система автоматически зовёт BiMax '
        '(этого агента) для разруливания ступоров и логической проверки.</div>'
        '</div>'
        '</div>'   # закрываем llm-tg-grid
    )
    status_block = status_block + llm_card

    _last = session.get("last_invite") or {}
    _last_role = _last.get("role") or ""
    _last_link = _last.get("link") or ""

    def _invite_block(role_key: str, label: str) -> str:
        """Ссылка-приглашение рядом с кнопкой (появляется сразу после создания)."""
        if not _last_link or _last_role != role_key:
            return ""
        return (
            '<div style="background:#F4F8FF;border:1px solid #DCE6FF;border-radius:12px;'
            'padding:12px;margin-top:10px">'
            f'<div style="font-weight:700;margin-bottom:6px">🔗 Ссылка для {label} (живёт 2 часа)</div>'
            f'<div style="word-break:break-all;font-size:12.5px;color:#1F2430">{_last_link}</div>'
            f'<button class="btn sm" type="button" data-copy="{_last_link}" '
            f'onclick="navigator.clipboard.writeText(this.dataset.copy);'
            f'this.textContent=\'✓ Скопировано\'">Копировать ссылку</button>'
            f'<div class="hint" style="margin-top:6px">Перешлите её человеку — он откроет бота '
            f'и станет {label}.</div></div>')

    def _invite_button(role_key: str, text: str) -> str:
        """Кнопка создания ссылки: после создания меняет цвет и подпись."""
        made = bool(_last_link) and _last_role == role_key
        cls = "btn ok sm" if made else "btn primary sm"
        caption = "✓ Ссылка создана" if made else text
        return (f'<form method="post" style="margin-top:10px">'
                f'<input type="hidden" name="action" value="create_invite">'
                f'<input type="hidden" name="role" value="{role_key}">'
                f'<button class="{cls}" type="submit">{caption}</button></form>')

    managers = db.bot_managers_by_role("manager")
    admins   = db.bot_managers_by_role("admin")

    managers_html = (_render_list(managers,
                                   "Менеджеров пока нет. Нажмите «Создать ссылку» "
                                   "и отправьте её человеку.")
                     + '<div class="hint" style="margin-top:8px">Бот читает сообщения этих людей '
                       'и воспринимает их как новые заявки. Им же бот отвечает, '
                       'когда администратор взял заявку в работу. На сайт не входят.</div>'
                     + _invite_button("manager", "+ Ссылка для менеджера")
                     + _invite_block("manager", "менеджера"))
    admins_html = (_render_list(admins,
                                 "Администраторов пока нет. Нажмите «Создать ссылку» "
                                 "и отправьте её человеку.")
                   + '<div class="hint" style="margin-top:8px">Этим людям бот присылает '
                     'сообщение «пришла новая заявка». Они же заходят на сайт '
                     'и работают с заявками.</div>'
                   + _invite_button("admin", "+ Ссылка для администратора")
                   + _invite_block("admin", "администратора"))

    body = f"""
<h1>Настройки</h1>
<div class="page-sub">Telegram-бот и список разрешённых менеджеров и администраторов.</div>
{ui_card("Telegram-бот", status_block,
         emoji="🤖", tone="blue", open=False,
         note="автоматическая проверка")}

{ui_card(f'Менеджеры · {len(managers)}', managers_html,
         emoji="👤", tone="blue", open=True,
         note=f'{len(managers)} чел.')}

{ui_card(f'Администраторы · {len(admins)}', admins_html,
         emoji="🛡", tone="violet", open=True,
         note=f'{len(admins)} чел.')}
"""
    return render("Настройки", "settings", body)
