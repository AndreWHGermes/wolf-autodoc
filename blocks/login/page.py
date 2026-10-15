"""Блок «Вход»: страница логина и выход.

Два способа входа:
1. Аварийный: login/password (admin/123). Только для тебя, для восстановления.
2. Основной: через Telegram. На странице «Войти через Telegram» — кнопка
   открывает бота с кодом. Бот шлёт 6-значный код, человек возвращается и вводит.
"""
from __future__ import annotations

from flask import (Blueprint, flash, redirect, render_template_string, request,
                   session, url_for)

from core import db
from core.auth import (consume_login_code, current_user, login_user,
                       login_via_telegram)
from core.security import hash_password, password_problems, verify_password
from repositories import security as sec_repo

bp = Blueprint("login", __name__)

BOT_USERNAME = "@Wolf_AutoDoc_bot"

FORM = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="/branding/logo-small.png?v=1">
<title>Вход · Wolf AutoDoc</title><style>{{ css }}</style></head><body class="login-body">
<form class="login-card" method="post">
  <div class="brand"><span class="m"><img src="/branding/logo-small.jpg?v=1" alt="Wolf" width="38" height="38"></span> Wolf AutoDoc</div>
  <div class="sub">Вход для администраторов</div>
  {{ flashes|safe }}

  <a class="btn tg" href="https://t.me/{{ bot_link }}?start=login">
    <span class="tg-ico">✈️</span> Войти через Telegram
  </a>
  <div class="hint">Бот проверит, что вы администратор, и вернёт вас сюда уже в системе.</div>

  <details class="fallback">
    <summary>Технический вход (логин и пароль)</summary>
    <div class="pass-block">
      <label for="login">Логин</label>
      <input id="login" type="text" name="login" value="admin" autocomplete="username">
      <label for="password">Пароль</label>
      <input id="password" type="password" name="password" autocomplete="current-password">
      <button class="btn ghost" type="submit" name="action" value="password"
              style="margin-top:12px">Войти по паролю</button>
    </div>

    <div class="tg-block">
      <div class="tg-title">Вход по коду из бота</div>
      <div class="tg-step">Если бот прислал код — введите его здесь:</div>
      <input name="code" type="text" inputmode="numeric" maxlength="6"
             placeholder="000000" autocomplete="one-time-code">
      <button class="btn ghost" type="submit" name="action" value="code"
              style="margin-top:8px">Войти по коду</button>
    </div>
  </details>
</form></body></html>"""

LOGIN_CSS = """
body.login-body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#F6F7FB;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif;color:#1F2430}
.login-card{width:100%;max-width:380px;background:#fff;border:1px solid #E6E8EF;border-radius:16px;
  padding:26px;box-shadow:0 10px 30px rgba(31,36,48,.06)}
.brand{font-weight:700;font-size:19px;display:flex;align-items:center;gap:9px}
.brand .m{display:inline-grid;place-items:center;width:38px;height:38px;border-radius:10px;background:#fff;overflow:hidden}
.brand .m img{width:100%;height:100%;object-fit:cover;display:block}
.sub{color:#6B7280;font-size:13.5px;margin:4px 0 14px}
label{display:block;font-size:12.5px;color:#6B7280;margin:12px 0 4px}
input{width:100%;padding:11px;border:1px solid #E6E8EF;border-radius:10px;font-size:15px;box-sizing:border-box}
input:focus{outline:none;border-color:#4F5BD5;box-shadow:0 0 0 3px rgba(79,91,213,.14)}
.btn{display:flex;align-items:center;justify-content:center;min-height:44px;padding:11px;font-size:15px;
  font-weight:600;color:#fff;background:#4F5BD5;border:none;border-radius:10px;cursor:pointer;
  font-family:inherit;text-decoration:none}
.btn.primary{background:#4F5BD5}
.btn.tg{background:#229ED9;min-height:52px;font-size:16.5px;gap:9px;margin-bottom:8px}
.btn.tg:hover{background:#1E8FC4}
.tg-ico{font-size:19px}
.pass-block{padding-top:2px}
.btn.ghost{background:#F0F2F7;color:#1F2430}
.tg-block{background:#F4F8FF;border:1px solid #DCE6FF;border-radius:12px;padding:14px;margin-bottom:14px}
.tg-title{font-weight:700;margin-bottom:8px}
.tg-step{font-size:13px;color:#374151;margin-bottom:3px}
.tg-link{background:#229ED9;margin-top:8px}
.fallback{margin-top:6px;border-top:1px dashed #E6E8EF;padding-top:10px}
.fallback summary{cursor:pointer;color:#6B7280;font-size:13px;padding:6px 0}
.hint{color:#6B7280;font-size:12px;margin-top:6px}
.flash{border-radius:10px;padding:9px 11px;font-size:13.5px;margin-bottom:6px}
.flash.bad{background:#FDECEA;color:#B3261E}
.flash.ok{background:#E8F6EE;color:#1B7F4B}
"""


@bp.route("/auth/tg/<code>")
def tg_link(code: str):
    """Вход по ссылке из бота — пришёл с кнопки «Войти через Telegram»."""
    tg_id = consume_login_code((code or "").strip())
    if not tg_id:
        flash("Ссылка входа устарела. Нажмите «Войти через Telegram» ещё раз.", "error")
        return redirect(url_for("login.page"))
    if not login_via_telegram(tg_id):
        flash("Вход на сайт — только для администраторов. Менеджеры работают через бота.",
              "error")
        return redirect(url_for("login.page"))
    return redirect(url_for("dashboard.page"))


@bp.route("/login", methods=["GET", "POST"])
def page():
    from blocks.shared.layout import flash_messages
    if current_user():
        return redirect(url_for("dashboard.page"))
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "code":
            code = (request.form.get("code") or "").strip()
            tg_id = consume_login_code(code)
            if not tg_id:
                flash("Код не найден или истёк. Попросите бота прислать новый.", "error")
                return redirect(url_for("login.page"))
            if not login_via_telegram(tg_id):
                flash("Этот Telegram-аккаунт не имеет прав администратора.", "error")
                return redirect(url_for("login.page"))
            return redirect(url_for("dashboard.page"))
        if action == "password":
            login = (request.form.get("login") or "").strip()
            password = request.form.get("password") or ""
            ip = request.remote_addr or "-"
            if sec_repo.is_blocked(ip):
                flash(f"Слишком много неудачных попыток. Повторите через "
                      f"{sec_repo.WINDOW_MINUTES} минут или войдите через Telegram.", "error")
                return redirect(url_for("login.page"))
            user = db.q1("SELECT * FROM users WHERE login=? AND active=1", (login,))
            if user and verify_password(password, user["password"]):
                sec_repo.register_attempt(ip, login, ok=True)
                login_user(user)
                from core.config import DEFAULT_ADMIN_PASSWORD
                if password == DEFAULT_ADMIN_PASSWORD:
                    # Заводской пароль — пусть администратор сразу сменит его.
                    session["must_change_password"] = True
                    flash("Вы вошли с заводским паролем. Задайте свой пароль.", "error")
                    return redirect(url_for("login.change_password"))
                db.log_event("user", user["id"], "login_password", actor=login)
                return redirect(url_for("dashboard.page"))
            sec_repo.register_attempt(ip, login, ok=False)
            left = max(0, sec_repo.MAX_FAILS - sec_repo.fails_recent(ip))
            flash("Неверный логин или пароль" + (f". Осталось попыток: {left}" if left else
                                                 ". Доступ временно заблокирован."), "error")
            return redirect(url_for("login.page"))
    return render_template_string(FORM, css=LOGIN_CSS, flashes=flash_messages(),
                                  bot=BOT_USERNAME, bot_link=BOT_USERNAME.lstrip("@"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login.page"))


PASSWORD_FORM = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Смена пароля · Wolf AutoDoc</title><style>{{ css }}</style></head><body class="login-body">
<form class="login-card" method="post">
  <div class="brand"><span class="m"><img src="/branding/logo-small.jpg?v=1" alt="Wolf" width="38" height="38"></span> Wolf AutoDoc</div>
  <div class="sub">Смена пароля администратора</div>
  {{ flashes|safe }}
  <label for="old">Текущий пароль</label>
  <input id="old" type="password" name="old" autocomplete="current-password">
  <label for="new">Новый пароль</label>
  <input id="new" type="password" name="new" autocomplete="new-password">
  <label for="new2">Новый пароль ещё раз</label>
  <input id="new2" type="password" name="new2" autocomplete="new-password">
  <div class="hint">Минимум 8 символов, буквы и цифры.</div>
  <button class="btn primary" type="submit" style="margin-top:12px">Сохранить пароль</button>
  <div class="hint" style="margin-top:10px"><a href="/logout">Выйти</a></div>
</form></body></html>"""


@bp.route("/password", methods=["GET", "POST"])
def change_password():
    """Смена пароля администратора (в том числе принудительная после заводского)."""
    from blocks.shared.layout import flash_messages
    user = current_user()
    if not user:
        return redirect(url_for("login.page"))
    if request.method == "POST":
        old = request.form.get("old") or ""
        new = request.form.get("new") or ""
        new2 = request.form.get("new2") or ""
        row = db.q1("SELECT * FROM users WHERE id=?", (user["id"],))
        if not row or not verify_password(old or "", row["password"]):
            flash("Текущий пароль указан неверно", "error")
            return redirect(url_for("login.change_password"))
        if new != new2:
            flash("Новые пароли не совпадают", "error")
            return redirect(url_for("login.change_password"))
        problems = password_problems(new)
        if problems:
            flash("Пароль не подходит: " + ", ".join(problems), "error")
            return redirect(url_for("login.change_password"))
        sec_repo.set_password(user["id"], hash_password(new))
        session.pop("must_change_password", None)
        db.log_event("user", user["id"], "password_changed", actor=user.get("login") or "")
        flash("Пароль изменён", "ok")
        return redirect(url_for("dashboard.page"))
    return render_template_string(PASSWORD_FORM, css=LOGIN_CSS, flashes=flash_messages())
