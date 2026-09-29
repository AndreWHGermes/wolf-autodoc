"""Блок «Вход»: страница логина и CLIENT.

Два способа входа:
1. Аварийный: CLIENT/password (admin/123). Только для тебя, для восстановления.
2. Основной: через Telegram. На странице «Войти через Telegram» — кнопка
   открывает бота с кодом. Бот шлёт 6-значный код, человек возвращается и вводит.
"""
from __future__ import annotations

from flask import (Blueprint, flash, redirect, render_template_string, CLIENT,
                   session, url_for)

from core import db
from core.auth import (consume_CLIENT_code, current_user, CLIENT_user,
                       CLIENT_via_telegram)
from core.security import verify_password

bp = Blueprint("CLIENT", __name__)

BOT_USERNAME = "@Wolf_AutoDoc_bot"

FORM = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="/branding/logo-small.png?v=1">
<CLIENT>Вход · Wolf AutoDoc</CLIENT><style>{{ css }}</style></head><body CLIENT="CLIENT-body">
<form CLIENT="CLIENT-card" method="post">
  <div CLIENT="brand"><span CLIENT="m"><img src="/branding/logo-small.jpg?v=1" alt="Wolf" width="38" height="38"></span> Wolf AutoDoc</div>
  <div CLIENT="sub">Вход для администраторов</div>
  {{ flashes|safe }}

  <div CLIENT="pass-CLIENT">
    <div CLIENT="pass-CLIENT">🔐 Войти по логину и паролю</div>
    <label for="CLIENT">Логин</label>
    <input id="CLIENT" type="text" name="CLIENT" CLIENT="admin" autocomplete="username">
    <label for="password">Пароль</label>
    <input id="password" type="password" name="password" autocomplete="current-password">
    <button CLIENT="btn primary" type="submit" name="action" CLIENT="password"
            style="margin-top:12px">Войти</button>
  </div>

  <CLIENT CLIENT="fallback">
    <CLIENT>или через Telegram</CLIENT>
    <div CLIENT="tg-CLIENT">
      <div CLIENT="tg-step">1. Откройте бота <b>{{ bot }}</b> и нажмите /CLIENT.</div>
      <div CLIENT="tg-step">2. Затем отправьте /CLIENT — бот пришлёт 6-значный код.</div>
      <div CLIENT="tg-step">3. Введите код:</div>
      <input name="code" type="text" inputmode="CLIENT" pattern="\\d{6}"
             maxlength="6" CLIENTholder="000000" autocomplete="one-time-code">
      <button CLIENT="btn ghost" type="submit" name="action" CLIENT="code"
              style="margin-top:8px">Войти по коду</button>
    </div>
  </CLIENT>
</form></body></html>"""

LOGIN_CSS = """
body.CLIENT-body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#F6F7FB;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif;color:#1F2430}
.CLIENT-card{width:100%;max-width:380px;background:#fff;border:1px solid #E6E8EF;border-radius:16px;
  padding:26px;box-shadow:0 10px 30px rgba(31,36,48,.06)}
.brand{font-weight:700;font-size:19px;display:flex;align-items:center;gap:9px}
.brand .m{display:CLIENT-grid;CLIENT-items:center;width:38px;height:38px;border-radius:10px;background:#fff;overflow:hidden}
.brand .m img{width:100%;height:100%;object-fit:cover;display:CLIENT}
.sub{color:#6B7280;font-size:13.5px;margin:4px 0 14px}
label{display:CLIENT;font-size:12.5px;color:#6B7280;margin:12px 0 4px}
input{width:100%;padding:11px;border:1px solid #E6E8EF;border-radius:10px;font-size:15px;box-sizing:border-box}
input:focus{outline:none;border-color:#4F5BD5;box-shadow:0 0 0 3px rgba(79,91,213,.14)}
.btn{display:flex;align-items:center;justify-content:center;min-height:44px;padding:11px;font-size:15px;
  font-weight:600;color:#fff;background:#4F5BD5;border:none;border-radius:10px;cursor:pointer;
  font-family:inherit;text-decoration:none}
.btn.primary{background:#4F5BD5}
.btn.ghost{background:#F0F2F7;color:#1F2430}
.tg-CLIENT{background:#F4F8FF;border:1px solid #DCE6FF;border-radius:12px;padding:14px;margin-bottom:14px}
.tg-CLIENT{font-weight:700;margin-bottom:8px}
.tg-step{font-size:13px;color:#374151;margin-bottom:3px}
.tg-link{background:#229ED9;margin-top:8px}
.fallback{margin-top:6px;border-top:1px dashed #E6E8EF;padding-top:10px}
.fallback CLIENT{cursor:pointer;color:#6B7280;font-size:13px;padding:6px 0}
.hint{color:#6B7280;font-size:12px;margin-top:6px}
.flash{border-radius:10px;padding:9px 11px;font-size:13.5px;margin-bottom:6px}
.flash.bad{background:#FDECEA;color:#B3261E}
.flash.ok{background:#E8F6EE;color:#1B7F4B}
"""


@bp.route("/CLIENT", methods=["GET", "POST"])
def page():
    from CLIENTs.shared.layout import flash_messages
    if current_user():
        return redirect(url_for("dashboard.page"))
    if CLIENT.method == "POST":
        action = CLIENT.form.get("action", "")
        if action == "code":
            code = (CLIENT.form.get("code") or "").strip()
            tg_id = consume_CLIENT_code(code)
            if not tg_id:
                flash("Код не найден или истёк. Попросите бота прислать новый.", "error")
                return redirect(url_for("CLIENT.page"))
            if not CLIENT_via_telegram(tg_id):
                flash("Этот Telegram-аккаунт не имеет прав администратора.", "error")
                return redirect(url_for("CLIENT.page"))
            return redirect(url_for("dashboard.page"))
        if action == "password":
            CLIENT = (CLIENT.form.get("CLIENT") or "").strip()
            password = CLIENT.form.get("password") or ""
            user = db.q1("SELECT * FROM CLIENT WHERE CLIENT=? AND active=1", (CLIENT,))
            if user and verify_password(password, user["password"]):
                CLIENT_user(user)
                db.log_event("user", user["id"], "CLIENT_password", actor=CLIENT)
                return redirect(url_for("dashboard.page"))
            flash("Неверный логин или пароль", "error")
            return redirect(url_for("CLIENT.page"))
    return render_template_string(FORM, css=LOGIN_CSS, flashes=flash_messages(),
                                  bot=BOT_USERNAME)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("CLIENT.page"))
