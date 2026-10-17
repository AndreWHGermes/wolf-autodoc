"""Точка входа: только сборка приложения из блоков.

Добавить новый блок = создать папку в blocks/<имя>/page.py и вписать одну строку
в список BLUEPRINTS ниже.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from datetime import datetime, timedelta

from flask import Flask, redirect, request, url_for
from waitress import serve

from core.log import get_logger, setup as setup_logging
from core.config import (BASE_DIR, WEB_HOST, WEB_PORT, WEB_SECRET, SESSION_HOURS,
                         MAX_UPLOAD_MB, DB_PATH)
from core import db
from core.auth import current_user, login_required
from repositories import clients as clients_repo

BLUEPRINTS = [
    ("blocks.login.page", "bp"),
    ("blocks.dashboard.page", "bp"),
    ("blocks.history.page", "bp"),
    ("blocks.templates.page", "bp"),
    ("blocks.settings.page", "bp"),
    ("blocks.dashboard.events", "bp"),
    ("blocks.review.page", "bp"),
    ("blocks.guide.page", "bp"),
]


def create_app() -> Flask:
    # Статика отделена от шаблонов: файлы в blocks/static, отдаются по /static/...
    app = Flask(__name__, template_folder=str(BASE_DIR / "blocks"),
                static_folder=str(BASE_DIR / "blocks" / "static"),
                static_url_path="/static")
    setup_logging()
    app.config["SECRET_KEY"] = WEB_SECRET
    # cookie только для HTTP-запросов и без кросс-сайтовых отправок
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=SESSION_HOURS)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    import importlib
    for module_path, attr in BLUEPRINTS:
        module = importlib.import_module(module_path)
        app.register_blueprint(getattr(module, attr))

    # Эндпоинт живости: /health отдаёт состояние сервиса и базы.
    # Нужен внешнему мониторингу, чтобы падение замечалось сразу.
    try:
        from blocks.shared import health as _health
        _health.register(app)
    except Exception as _e:  # pragma: no cover
        print("health не подключён:", _e)

    @app.errorhandler(Exception)
    def _log_exception(e):  # noqa: ANN001
        """Ошибку запроса пишем в лог с трассировкой, а не молча отдаём 500."""
        from flask import request
        import traceback
        get_logger("wolf.error").error("Ошибка %s %s: %s\n%s", request.method, request.path,
                                       e, traceback.format_exc())
        return "Ошибка сервера — детали записаны в logs/wolf.log", 500

    db.init_db()

    @app.before_request
    def _safety_checks():
        """1) пока не сменили заводской пароль — работаем только на странице смены;
           2) небезопасные методы принимаем только со своего сайта (защита от CSRF)."""
        from flask import redirect, request, session, url_for
        path = request.path
        skip = ("/static/", "/branding/", "/password", "/logout", "/login")
        if session.get("must_change_password") and not path.startswith(skip):
            return redirect(url_for("login.change_password"))
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
            if origin and request.host not in origin:
                return "Запрос отклонён: чужой источник", 403
        return None

    @app.before_request
    def _mark_user_activity():
        """Отмечаем, что администратор работает в сайте.

        Фоновая подготовка заявок читает эту метку и уступает дорогу: ядер на
        сервере мало, и сборка документов в фоне не должна тормозить интерфейс
        (замер: во время подготовки заявка открывалась 4 с вместо 0,04 с).
        """
        try:
            if request.path.startswith("/applications/") or request.path in ("/", "/index"):
                import time as _t
                from pathlib import Path as _P
                _p = _P("/opt/wolf_v2/data/prep")
                _p.mkdir(parents=True, exist_ok=True)
                (_p / "user_active.ts").write_text(str(_t.time()))
        except Exception:
            pass
        return None

    @app.after_request
    def _compress_text(resp):
        """Сжимаем текстовые ответы своим gzip.

        Сайт открыт наружу и напрямую на порт 8094, где нет nginx: страница
        заявки весит 220 КБ, скрипты ещё 95 КБ. Сжатие уменьшает это в 4–5 раз,
        и страница приходит заметно быстрее (на телефоне особенно).
        """
        try:
            if (resp.status_code == 200
                    and resp.headers.get("Content-Encoding") is None
                    and "gzip" in (request.headers.get("Accept-Encoding") or "")):
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if any(k in ctype for k in ("text/", "application/json",
                                            "application/javascript", "image/svg")):
                    # Статика Flask отдаётся потоком, и длина не всегда известна —
                    # берём данные и проверяем размер уже после чтения. Крупные
                    # файлы (PDF, снимки) сюда не попадают: у них не текстовый тип.
                    # Статику Flask отдаёт потоком (direct_passthrough): снимаем
                    # флаг, иначе данные не прочитать и сжатие не применится.
                    if resp.direct_passthrough:
                        resp.direct_passthrough = False
                    data = resp.get_data()
                    if 700 < len(data) <= 500_000:
                        import gzip as _gzip
                        packed = _gzip.compress(data, 9)
                        if len(packed) < len(data):
                            resp.set_data(packed)
                            resp.headers["Content-Encoding"] = "gzip"
                            resp.headers["Content-Length"] = str(len(packed))
                            resp.headers.add("Vary", "Accept-Encoding")
        except Exception:
            pass
        return resp

    @app.route("/front/<path:name>")
    def _front_asset(name):
        """Отдаём общий CSS/JS одним файлом с длинным кэшем.

        Имя содержит отпечаток содержимого, поэтому файл можно кэшировать год:
        при повторных заходах браузер не скачивает код интерфейса заново, а
        страница приходит с одними данными заявки.
        """
        from flask import Response as _R
        kind = "css" if str(name).endswith(".css") else ("js" if str(name).endswith(".js") else "")
        if not kind:
            return _R("нет такого файла", status=404)
        try:
            from blocks.shared import layout as _lay
            body, digest = _lay.front_bundle(kind)
        except Exception as exc:  # noqa: BLE001
            log.warning("файл фронта не собран: %s", str(exc)[:120])
            return _R("", status=500)
        # Имя запросили не то, что собрали — значит версия устарела.
        if digest not in str(name):
            return _R("", status=404)
        etag = '"%s"' % digest
        if request.headers.get("If-None-Match") == etag:
            return _R(status=304)
        resp = _R(body, mimetype="text/css" if kind == "css" else "application/javascript")
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        resp.headers["ETag"] = etag
        return resp

    @app.before_request
    def _tolerate_trailing_slash():
        path = request.path
        if not path.endswith("/") or len(path) <= 1:
            return None
        stripped = path.rstrip("/") or "/"
        try:
            app.url_map.bind("localhost").match(stripped)
        except Exception:                               # noqa: BLE001
            return None
        return redirect(stripped, code=301)

    @app.errorhandler(404)
    def _not_found(_err):
        from blocks.shared.layout import render
        return render("Не найдено", "", '<h1>Страница не найдена</h1>'
                                       '<div class="muted" style="margin-bottom:14px">Проверьте адрес.</div>'
                                       '<a class="btn" href="/">На главную</a>'), 404

    @app.route("/clients/<int:client_id>")
    @login_required
    def _client_view(client_id: int):
        """Карточка клиента: зелёная шапка, заявка, документы, данные."""
        from blocks.shared.layout import card as ui_card, item, render
        client = db.client_get(client_id)
        if not client:
            return "Клиент не найден", 404

        last_app = db.q1("""SELECT a.*, p.code AS product_code, p.name AS product_name,
                                   u.login AS taken_login,
                                   bm.username AS bot_manager_username,
                                   bm.telegram_id AS bot_manager_tg
                            FROM applications a
                            LEFT JOIN products p ON p.id = a.product_id
                            LEFT JOIN users u ON u.id = a.taken_by
                            LEFT JOIN bot_managers bm ON bm.id = a.bot_manager_id
                            WHERE a.client_id=?
                            ORDER BY a.id DESC LIMIT 1""", (client_id,))
        app_docs = (db.application_documents(last_app["id"])
                    if last_app else [])
        summary = (db.application_doc_summary(last_app["id"])
                   if last_app else {"total": 0, "verified": 0})

        def _fmt_dt(ts):
            if not ts:
                return "—"
            try:
                return datetime.fromisoformat(ts.replace("Z", "")).strftime("%d.%m.%Y %H:%M")
            except Exception:
                return str(ts)[:16]

        manager_display = "—"
        if last_app:
            manager_display = (last_app.get("taken_login")
                               or last_app.get("bot_manager_username")
                               or last_app.get("source")
                               or "—")

        # блок «Откуда заявка»
        if last_app:
            origin_rows = (
                f'<div class="item no-line"><div class="txt"><div class="s">Менеджер</div>'
                f'<div class="t">{manager_display}</div></div></div>'
                f'<div class="item no-line"><div class="txt"><div class="s">Когда</div>'
                f'<div class="t">{_fmt_dt(last_app.get("created_at"))}</div></div></div>'
                f'<div class="item no-line"><div class="txt"><div class="s">Продукт</div>'
                f'<div class="t">{last_app.get("product_name") or "—"}</div></div></div>'
                f'<div class="item no-line"><div class="txt"><div class="s">Стоимость</div>'
                f'<div class="t">IDR {last_app["price_idr"]:,}</div></div></div>'
                f'<div class="item no-line"><div class="txt"><div class="s">Комментарий</div>'
                f'<div class="t">{last_app.get("comment") or "—"}</div></div></div>'
            )
        else:
            origin_rows = '<div class="muted" style="padding:6px 2px">Заявок пока нет — придёт от Telegram-бота.</div>'

        # блок «Контакт» — кликабельные ссылки
        phone_raw = (client.get("phone") or "").strip()
        phone_clean = re.sub(r"[^\d+]", "", phone_raw)
        wa_phone = phone_clean.lstrip("+").replace("+", "") if phone_clean else ""
        tg_username = (client.get("telegram_username") or "").lstrip("@")
        email = (client.get("email") or "").strip()

        contact_buttons = []
        if phone_clean:
            contact_buttons.append(
                f'<a class="btn block ok" href="tel:{phone_clean}">📞 {phone_raw or "Позвонить"}</a>')
        if wa_phone:
            contact_buttons.append(
                f'<a class="btn block" target="_blank" rel="noopener" '
                f'href="https://wa.me/{wa_phone}">💬 WhatsApp</a>')
        if tg_username:
            contact_buttons.append(
                f'<a class="btn block" target="_blank" rel="noopener" '
                f'href="https://t.me/{tg_username}">✈️ Telegram</a>')
        elif client.get("telegram_id"):
            tg_id = str(client["telegram_id"]).lstrip("-")
            contact_buttons.append(
                f'<a class="btn block" target="_blank" rel="noopener" '
                f'href="https://t.me/{tg_id}">✈️ Telegram</a>')
        if email:
            contact_buttons.append(
                f'<a class="btn block ghost" href="mailto:{email}">✉️ {email}</a>')
        contact_buttons_html = "".join(contact_buttons) or \
            '<div class="muted" style="padding:6px 2px">Контакты пока не заполнены.</div>'

        # блок «Фото клиента» — загрузка + превью
        photo_path = client.get("photo_path") or ""
        if photo_path:
            photo_html = (
                f'<div id="client-photo-preview" style="margin-bottom:8px">'
                f'<img src="/clients/{client_id}/photo?v={int(time.time())}" '
                f'style="max-width:160px;max-height:200px;border-radius:8px;border:1px solid #dceee2" />'
                f'</div>'
                f'<form method="POST" enctype="multipart/form-data" action="/clients/{client_id}/photo" '
                f'id="client-photo-form" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                f'<input type="file" name="photo" accept="image/*" '
                f'    style="font-size:12px;padding:4px;border:1px solid #dceee2;border-radius:6px" />'
                f'<button type="submit" class="btn small">Заменить</button>'
                f'<button type="button" class="btn small ghost" onclick="deletePhoto({client_id})">Удалить</button>'
                f'</form>'
            )
        else:
            photo_html = (
                f'<form method="POST" enctype="multipart/form-data" action="/clients/{client_id}/photo" '
                f'style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                f'<input type="file" name="photo" accept="image/*" required '
                f'    style="font-size:12px;padding:4px;border:1px solid #dceee2;border-radius:6px" />'
                f'<button type="submit" class="btn small">📷 Загрузить фото</button>'
                f'</form>'
                f'<div class="muted" style="margin-top:6px;font-size:11px">'
                f'Фото будет доступно через переменную <code>{{{{ client_photo_url }}}}</code> '
                f'во всех шаблонах документов.</div>'
            )

        # блок «Drive клиента» — активная ссылка
        drive_url = (last_app.get("gdrive_url") if last_app else None) or \
                    client.get("gdrive_folder_url") or ""
        if drive_url:
            drive_html = (f'<a class="btn block" target="_blank" rel="noopener" '
                          f'href="{drive_url}">📁 Открыть Google Drive клиента</a>'
                          f'<div class="muted mono" style="margin-top:6px;word-break:break-all">{drive_url}</div>')
        else:
            drive_html = '<div class="muted" style="padding:6px 2px">Ссылка на Google Drive клиента пока не пришла.</div>'

        # блок «Документы по заявке» — минимум кнопок
        if last_app and app_docs:
            def _doc_buttons(d):
                open_pdf = ''
                if d.get("pdf_path"):
                    fname = Path(d["pdf_path"]).name
                    open_pdf = (f'<a class="btn sm" target="_blank" '
                                f'href="/templates/file/renders/{fname}">Открыть PDF</a>')
                else:
                    open_pdf = '<span class="badge">PDF ещё не собран</span>'
                edit_btn = (f'<a class="btn ghost sm" '
                            f'href="/applications/{last_app["id"]}/doc/{d["id"]}">Редактировать</a>')
                verified = ''
                if d["status"] in ("filled", "verified", "pending", "error"):
                    action_label = "✓ Корректно" if d["status"] != "verified" else "Отменить"
                    verified = (f'<form method="post" style="display:inline" '
                                f'action="/clients/{client_id}/doc/{d["id"]}/approve">'
                                f'<button class="btn ok sm" type="submit">{action_label}</button></form>')
                state = {"verified": "проверен", "filled": "заполнен",
                         "sent": "отправлен", "error": "ошибка"}.get(d["status"], "в очереди")
                return (f'<div class="doc-actions">'
                        f'{open_pdf}{edit_btn}{verified}'
                        f'<span class="badge" style="margin-left:auto">{state}</span>'
                        f'</div>')

            doc_rows = "".join(
                f'<div class="doc-card">'
                f'<div class="doc-name">📄 {d["title"]} <span class="muted">· {d["pages"] or 0} стр.</span></div>'
                f'{_doc_buttons(d)}'
                f'</div>'
                for d in app_docs)

            all_ok = (summary.get("total", 0) > 0
                      and summary.get("verified", 0) + summary.get("sent", 0)
                      >= summary.get("total", 0))
            if all_ok:
                send_btn = (f'<form method="post" action="/clients/{client_id}/send" '
                            f'style="margin-top:12px">'
                            f'<button class="btn ok block" type="submit">'
                            f'Документы готовы · отправить на Google Drive</button></form>')
            else:
                left = summary.get("total", 0) - summary.get("verified", 0) - summary.get("sent", 0)
                send_btn = (f'<div class="hint" style="margin-top:12px">'
                            f'Осталось проверить документов: {left}.</div>')

            docs_card = (f'{ui_card(f"Документы · {summary.get("total", 0)}", "", emoji="📦", tone="violet", open=True)}'
                         '<div class="doc-list">' + doc_rows + send_btn + '</div>')
        else:
            docs_card = ui_card("Документы по заявке",
                                '<div class="muted" style="padding:6px 2px">Заявок пока нет.</div>',
                                emoji="📦", tone="violet")

        # данные клиента — с inline-edit
        groups = [
            ("Личные данные", ["surname", "name", "patronymic", "full_name_latin",
                              "full_name_title", "birth_date", "birth_place",
                              "gender", "citizenship", "nationality"]),
            ("Паспорт", ["passport_series", "passport_number", "passport_code",
                        "passport_issue_date", "passport_issued_by",
                        "passport_expiry", "inn", "snils", "intl_passport"]),
            ("Контакт", ["phone", "email", "telegram_username",
                        "address_zip", "country", "city", "address_reg", "address_live"]),
            ("Работа", ["company_name", "company_llc", "company_address",
                         "company_inn", "company_kpp", "company_ogrn",
                         "company_director", "position", "salary_amount", "bank_name"]),
            ("Заметки", ["notes"]),
        ]
        # EDITABLE_FIELDS — белый список колонок, которые можно править через /clients/<id>/edit
        EDITABLE_FIELDS = set()
        for _, keys in groups:
            EDITABLE_FIELDS.update(keys)

        group_blocks = []
        for title, keys in groups:
            rows_html = []
            for k in keys:
                val = client.get(k)
                # input с текущим значением (или пустой)
                cur = str(val) if val else ""
                rows_html.append(
                    f'<div class="item no-line client-field" data-key="{k}" '
                    f'data-label="{db.FIELD_MAP.get(k, k)}">'
                    f'<div class="txt">'
                    f'<div class="s">{db.FIELD_MAP.get(k, k)}</div>'
                    f'<div class="t">'
                    f'<span class="client-val">{val or "—"}</span>'
                    f'<input class="client-input" name="{k}" '
                    f'value="{cur.replace(chr(34), "&quot;")}" '
                    f'style="display:none;width:100%;padding:6px 8px;'
                    f'border:1px solid #dceee2;border-radius:6px;'
                    f'font-size:13px;font-family:monospace;margin-top:4px" />'
                    f'</div></div></div>'
                )
            rows = "".join(rows_html)
            # кнопка редактирования идёт ПЕРВОЙ строкой в карточке
            edit_btn = (f'<div class="item no-line" style="border-bottom:1px solid #dceee2;padding-bottom:8px;margin-bottom:8px">'
                        f'<button type="button" class="btn small ghost client-edit-btn" '
                        f'data-group="{title}" '
                        f'style="float:right">✏️ Редактировать</button>'
                        f'<div class="txt"><div class="s" style="font-weight:600;color:#374151">{title}</div></div>'
                        f'</div>')
            group_blocks.append(ui_card(title, edit_btn + rows, emoji="👤", tone="blue"))

        head_chips = ""
        if last_app:
            head_chips = (
                f'<div class="clh-chip"><b>Заявка</b>#{last_app["id"]}</div>'
                f'<div class="clh-chip"><b>Продукт</b>{last_app.get("product_name") or "—"}</div>'
                f'<div class="clh-chip"><b>Сумма</b>IDR {last_app["price_idr"]:,}</div>')

        body = f"""
<style>
.doc-list{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.doc-card{{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:12px;box-shadow:var(--shadow)}}
.doc-name{{font-weight:700;font-size:15px;margin-bottom:8px}}
.doc-actions{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.doc-actions .btn{{flex:0 0 auto}}
</style>
<div class="client-head">
  <div class="clh-row">
    <a class="clh-back" href="/" aria-label="назад">‹</a>
    <div>
      <h1>{db.client_label(client)}</h1>
      <div class="clh-sub">Карточка клиента #{client["id"]} · обновлена {client["updated_at"][:16]}</div>
    </div>
  </div>
  <div class="clh-chips">{head_chips}</div>
</div>
{ui_card("Откуда заявка", origin_rows, emoji="📥", tone="amber", open=True)}
{ui_card("Контакт", contact_buttons_html, emoji="📞", tone="green", open=True)}
{ui_card("Фото клиента", photo_html, emoji="📷", tone="blue", open=True)}
{ui_card("Google Drive клиента", drive_html, emoji="📁", tone="blue", open=True)}
{docs_card}
{"".join(group_blocks)}
<script>
function deletePhoto(cid) {{
  if (!confirm('Удалить фото клиента?')) return;
  fetch('/clients/' + cid + '/photo', {{method: 'DELETE'}})
    .then(r => r.json())
    .then(d => {{
      if (d.ok) location.reload();
    }});
}}

// === Inline-edit карточки клиента ===
const CLIENT_ID = {client_id};

document.addEventListener('DOMContentLoaded', function() {{
  // Клик «✏️ Редактировать»
  document.querySelectorAll('.client-edit-btn').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      toggleGroupEdit(btn.dataset.group, btn);
    }});
  }});

  // Ctrl/Cmd + S в активной группе — сохранить
  document.addEventListener('keydown', function(e) {{
    if (!(e.ctrlKey || e.metaKey) || e.key !== 's') return;
    const editing = document.querySelector('.client-edit-controls[data-active=true]');
    if (!editing) return;
    e.preventDefault();
    saveGroupEdit(editing.dataset.group);
  }});
}});

function toggleGroupEdit(groupName, btn) {{
  const card = btn.closest('.card');
  if (!card) return;

  const wasEditing = btn.dataset.state === 'editing';

  if (wasEditing) {{
    // Отмена: скрыть input'ы, восстановить спаны
    card.querySelectorAll('.client-field').forEach(function(f) {{
      f.querySelector('.client-input').style.display = 'none';
      const sp = f.querySelector('.client-val');
      if (sp) sp.style.display = '';
    }});
    card.querySelectorAll('.client-edit-controls').forEach(function(c) {{ c.remove(); }});
    btn.textContent = '✏️ Редактировать';
    btn.dataset.state = '';
    return;
  }}

  // Войти в режим редактирования
  card.querySelectorAll('.client-field').forEach(function(f) {{
    f.querySelector('.client-val').style.display = 'none';
    const inp = f.querySelector('.client-input');
    inp.style.display = '';
  }});

  // кнопки «Сохранить» / «Отмена»
  const controls = document.createElement('div');
  controls.className = 'client-edit-controls';
  controls.dataset.group = groupName;
  controls.dataset.active = 'true';
  controls.style.cssText = 'display:flex;gap:8px;margin-top:12px;padding-top:8px;border-top:1px solid #dceee2';
  controls.innerHTML = `
    <button type="button" class="btn small client-save-btn"
            onclick="saveGroupEdit('${{groupName}}'.replace('&dollar;', '$'))"
            style="background:#16a34a;color:#fff;border:none;padding:6px 14px;border-radius:6px;font-size:13px;cursor:pointer">
      💾 Сохранить
    </button>
    <button type="button" class="btn small ghost client-cancel-btn"
            style="padding:6px 14px;background:#f3f4f6;color:#374151;border:1px solid #d1d5db;border-radius:6px;font-size:13px;cursor:pointer">
      Отмена
    </button>
    <span class="client-edit-status" style="margin-left:auto;font-size:12px;color:#6b7280"></span>
  `;

  // ищим хвост карточки и вставляем
  const inner = card.querySelector('.card-body') || card;
  inner.appendChild(controls);

  controls.querySelector('.client-cancel-btn').addEventListener('click', function() {{
    // сбросить input'ы к исходным значениям
    card.querySelectorAll('.client-field').forEach(function(f) {{
      f.querySelector('.client-input').value = f.querySelector('.client-val').textContent.trim() === '—'
        ? '' : f.querySelector('.client-val').textContent.trim();
    }});
    toggleGroupEdit(groupName, btn);
  }});

  btn.textContent = '✕ Отменить';
  btn.dataset.state = 'editing';
}}

function saveGroupEdit(groupName) {{
  const card = document.querySelector('.btn.client-edit-btn[data-group="' + groupName + '"]').closest('.card');
  if (!card) return;
  const status = card.querySelector('.client-edit-status');
  const saveBtn = card.querySelector('.client-save-btn');

  // Соберём formdata
  const form = new FormData();
  card.querySelectorAll('.client-input').forEach(function(inp) {{
    form.append(inp.name, inp.value);
  }});

  saveBtn.disabled = true;
  saveBtn.textContent = '⏳ Сохранение...';
  if (status) status.textContent = '';

  fetch('/clients/' + CLIENT_ID, {{
    method: 'POST',
    headers: {{'X-Requested-With': 'fetch'}},
    body: form
  }})
  .then(r => r.json().then(d => ({{
    ok: r.ok,
    data: d
  }})))
  .then(function(res) {{
    if (!res.ok || !res.data.ok) {{
      const errMsg = res.data && res.data.error || ('HTTP ' + res.ok);
      if (status) {{ status.style.color = '#dc2626'; status.textContent = '✗ ' + errMsg; }}
      saveBtn.disabled = false;
      saveBtn.textContent = '💾 Сохранить';
      return;
    }}
    // OK — обновить значения на странице без перезагрузки
    const updated = res.data.client || {{}};
    let changed = 0;
    card.querySelectorAll('.client-field').forEach(function(f) {{
      const k = f.dataset.key;
      if (k in updated) {{
        const sp = f.querySelector('.client-val');
        const inp = f.querySelector('.client-input');
        const v = updated[k] || '';
        sp.textContent = v || '—';
        inp.value = v;
        if (v) changed++;
      }}
    }});
    if (status) {{
      status.style.color = '#16a34a';
      status.textContent = '✓ Сохранено';
      setTimeout(function() {{ status.textContent = ''; }}, 2500);
    }}
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 Сохранено';
    setTimeout(function() {{
      toggleGroupEdit(groupName, card.querySelector('.client-edit-btn'));
      // обновим имя в шапке если редактировали ФИО
      const h1 = document.querySelector('.client-head h1');
      if (h1 && (groupName === 'Личные данные')) h1.textContent = updated.full_name_latin || updated.name + ' ' + (updated.surname || '') || ('Клиент #' + CLIENT_ID);
    }}, 800);
  }})
  .catch(function(e) {{
    if (status) {{ status.style.color = '#dc2626'; status.textContent = '✗ Ошибка сети'; }}
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 Сохранить';
  }});
}}
</script>
"""
        return render(db.client_label(client), "", body)

    # действия администратора по документу заявки прямо из карточки клиента
    @app.route("/clients/<int:client_id>", methods=["POST"])
    @login_required
    def _client_update(client_id: int):
        """Обновить поля клиента из формы редактирования карточки."""
        client = db.client_get(client_id)
        if not client:
            return jsonify({"ok": False, "error": "Клиент не найден"}), 404

        # Список разрешённых полей
        EDITABLE = {
            "surname", "name", "patronymic", "full_name_latin", "full_name_title",
            "birth_date", "birth_place", "gender", "citizenship", "nationality",
            "passport_series", "passport_number", "passport_code",
            "passport_issue_date", "passport_issued_by", "passport_expiry",
            "inn", "snils", "intl_passport",
            "phone", "email", "telegram_username",
            "address_zip", "country", "city", "address_reg", "address_live",
            "company_name", "company_llc", "company_address",
            "company_inn", "company_kpp", "company_ogrn", "company_director",
            "position", "salary_amount", "bank_name", "notes",
        }

        sets = []
        params = []
        updated = {}
        for key in EDITABLE:
            if key in request.form:
                new_val = request.form.get(key, "").strip() or None
                sets.append(f"{key}=?")
                params.append(new_val)
                if new_val != (client.get(key) or None):
                    updated[key] = new_val

        if not sets:
            return jsonify({"ok": False, "error": "Не передано полей для обновления"}), 400

        params.append(client_id)
        sets.append("updated_at=datetime('now')")
        db.exec_sql(f"UPDATE clients SET {', '.join(sets)} WHERE id=?", tuple(params))
        db.log_event("client", client_id, "updated",
                     payload=json.dumps({"changed": list(updated.keys())}, ensure_ascii=False))

        # Если это fetch с X-Requested-With — вернём JSON
        if request.headers.get("X-Requested-With") == "fetch":
            new_client = db.client_get(client_id)
            return jsonify({
                "ok": True,
                "client_id": client_id,
                "updated_fields": list(updated.keys()),
                "client": new_client,
            })
        # Иначе redirect
        return redirect(f"/clients/{client_id}")

    @app.route("/clients/<int:client_id>/doc/<int:ad_id>/approve", methods=["POST"])
    @login_required
    def _approve_doc(client_id: int, ad_id: int):
        db.application_doc_set(ad_id, "verified")
        db.log_event("application_doc", ad_id, "verified", actor=current_user()["login"])
        return redirect(f"/clients/{client_id}")

    @app.route("/clients/<int:client_id>/doc/<int:ad_id>/reject", methods=["POST"])
    @login_required
    def _reject_doc(client_id: int, ad_id: int):
        db.application_doc_set(ad_id, "pending")
        db.log_event("application_doc", ad_id, "rejected", actor=current_user()["login"])
        return redirect(f"/clients/{client_id}")

    @app.route("/clients/<int:client_id>/doc/<int:ad_id>/fill", methods=["POST"])
    @login_required
    def _fill_doc(client_id: int, ad_id: int):
        doc = db.q1("SELECT application_id, template_id FROM application_documents WHERE id=?", (ad_id,))
        if doc:
            return redirect(f'/applications/{doc["application_id"]}/doc/{ad_id}')
        return redirect(f"/clients/{client_id}")

    @app.route("/clients/<int:client_id>/send", methods=["POST"])
    @login_required
    def _send_to_drive(client_id: int):
        last_app = db.q1("SELECT id FROM applications WHERE client_id=? ORDER BY id DESC LIMIT 1",
                         (client_id,))
        if not last_app:
            return redirect(f"/clients/{client_id}")
        app_id = last_app["id"]
        summary = db.application_doc_summary(app_id)
        if summary.get("verified", 0) + summary.get("sent", 0) < summary.get("total", 0):
            return redirect(f"/clients/{client_id}")
        for d in db.application_documents(app_id):
            if d["status"] in ("filled", "verified"):
                db.application_doc_set(d["id"], "sent")
        db.application_set_status(app_id, "sent")
        db.log_event("application", app_id, "sent", actor=current_user()["login"])
        return redirect(f"/clients/{client_id}")

    @app.errorhandler(413)
    def _too_large(_err):
        return "Файл больше допустимого размера", 413

    # ============ Загрузка фото клиента ============
    from flask import send_from_directory, jsonify, abort

    @app.route("/clients/<int:client_id>/photo", methods=["GET", "POST"])
    @login_required
    def _client_photo(client_id: int):
        """GET — отдаёт фото (или 404), POST — загрузка нового (multipart/form-data)."""
        photos_dir = BASE_DIR / "data" / "client_photos"
        photos_dir.mkdir(parents=True, exist_ok=True)

        if request.method == "GET":
            cl = clients_repo.photo_path(client_id)
            if not cl or not cl.get("photo_path"):
                abort(404)
            return send_from_directory(photos_dir, cl["photo_path"])

        # POST — загрузка
        file = request.files.get("photo")
        if not file:
            return jsonify({"ok": False, "error": "no file"}), 400
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        if ext not in ('png', 'jpg', 'jpeg', 'webp'):
            return jsonify({"ok": False, "error": f"bad ext: {ext}"}), 400
        filename = f"client_{client_id}.{ext}"
        file.save(photos_dir / filename)
        db.exec_sql("UPDATE clients SET photo_path=?, updated_at=datetime('now') WHERE id=?",
                    (filename, client_id))
        # Если запрос через fetch — JSON, иначе redirect
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({"ok": True, "client_id": client_id, "filename": filename,
                            "url": f"/clients/{client_id}/photo"})
        return redirect(request.referrer or f"/clients/{client_id}")

    @app.route("/clients/<int:client_id>/photo", methods=["DELETE"])
    @login_required
    def _client_photo_delete(client_id: int):
        cl = clients_repo.photo_path(client_id)
        if cl and cl.get("photo_path"):
            photos_dir = BASE_DIR / "data" / "client_photos"
            (photos_dir / cl["photo_path"]).unlink(missing_ok=True)
            db.exec_sql("UPDATE clients SET photo_path=NULL WHERE id=?", (client_id,))
        return jsonify({"ok": True})

    @app.route("/branding/<path:filename>")
    def _branding(filename: str):
        """Отдаёт логотип/брендовые ассеты из data/branding (публично, без авторизации)."""
        from flask import send_from_directory
        branding_dir = BASE_DIR / "data" / "branding"
        return send_from_directory(branding_dir, filename, as_attachment=False)

    # ============ ОРИГИНАЛЫ КЛИЕНТА (Google Drive) ============
    GDRIVE_ROOT = BASE_DIR / "data" / "gdrive_examples"

    # Какие имена файлов соответствуют какому типу шаблона
    ORIGINAL_PATTERNS = {
        "bank": ["bankstatement", "bank_statement", "bank statement", "funds_movement",
                 "funds movement", "account_activity", "account activity",
                 "справка", "движение средств"],
        "work": ["workagreement", "work_agreement", "work agreement", "трудовой",
                 "трудовой дог", "employment agreement", "employment_agreement",
                 "договор"],
        "cv": ["resume", "cv", "itk"],
        "personal": ["personal"],
    }

    def _resolve_pattern(template_code: str) -> list:
        """Определяет категорию оригинального файла по коду шаблона."""
        code = (template_code or "").lower()
        if code.startswith("bank_statement") or "bank" in code:
            return ORIGINAL_PATTERNS["bank"]
        if "remote_work" in code or "agreement" in code:
            return ORIGINAL_PATTERNS["work"]
        if code.startswith("cv"):
            return ORIGINAL_PATTERNS["cv"]
        if "personal" in code:
            return ORIGINAL_PATTERNS["personal"]
        # для индонезийских и прочих — личное дело + сканы
        return []

    def _find_client_folder(client_id: int):
        """Ищет папку клиента в gdrive_examples по ФИО (строгий матчинг по токенам)."""
        cl = db.q1("SELECT full_name_latin, surname, name FROM clients WHERE id=?",
                   (client_id,))
        if not cl:
            return None
        if not GDRIVE_ROOT.exists():
            return None

        def norm(s: str) -> str:
            return " ".join("".join(ch for ch in (s or "").lower()
                                    if ch.isalnum() or ch.isspace()).split())

        def tokens(s: str) -> set:
            return set(norm(s).split())

        full = norm(cl.get("full_name_latin"))
        full_tokens = tokens(cl.get("full_name_latin"))
        sur = norm(cl.get("surname"))
        nm = norm(cl.get("name"))

        folders = [d for d in GDRIVE_ROOT.iterdir() if d.is_dir()]

        for d in folders:
            if norm(d.name) == full:
                return d
        if not full_tokens:
            return None
        best = None
        for d in folders:
            dt = tokens(d.name)
            if not dt:
                continue
            if full_tokens <= dt or dt <= full_tokens:
                if len(full_tokens & dt) >= 2 or (sur and nm and sur in dt and nm in dt):
                    return d
            if sur and nm and sur in dt and nm in dt:
                best = best or d
        return best

    def _find_original_file(client_id: int, template_code: str):
        """Возвращает Path оригинального PDF клиента для данного типа документа."""
        folder = _find_client_folder(client_id)
        if not folder:
            return None
        patterns = _resolve_pattern(template_code)
        if not patterns:
            return None
        pdfs = [f for f in folder.iterdir()
                if f.suffix.lower() == ".pdf" and f.is_file()]
        # точный приоритет: сначала bank/work, потом остальные
        for pat in patterns:
            for f in pdfs:
                if pat in f.name.lower():
                    return f
        return None

    @app.route("/clients/<int:client_id>/original/<int:template_id>")
    @login_required
    def _client_original(client_id: int, template_id: int):
        """Отдаёт ОРИГИНАЛЬНЫЙ PDF клиента (из Google Drive) для предпросмотра."""
        from flask import send_from_directory, abort
        tpl = db.q1("SELECT code FROM templates WHERE id=?", (template_id,))
        if not tpl:
            abort(404)
        f = _find_original_file(client_id, tpl["code"])
        if not f:
            abort(404)
        return send_from_directory(f.parent, f.name, as_attachment=False,
                                   mimetype="application/pdf")

    @app.route("/applications/<int:app_id>/original/<int:template_id>")
    @login_required
    def _app_original(app_id: int, template_id: int):
        a = apps_repo.client_id(app_id)
        if not a:
            from flask import abort
            abort(404)
        return _client_original(a["client_id"], template_id)

    @app.route("/applications/<int:app_id>/original-list")
    @login_required
    def _app_original_list(app_id: int):
        """JSON: какие оригиналы есть у клиента (для отрисовки в UI)."""
        a = apps_repo.client_id(app_id)
        if not a:
            return jsonify({"ok": False}), 404
        folder = _find_client_folder(a["client_id"])
        files = []
        if folder:
            for f in sorted(folder.iterdir()):
                if f.is_file():
                    files.append({"name": f.name, "size": f.stat().st_size,
                                  "ext": f.suffix.lower()})
        return jsonify({"ok": True, "folder": folder.name if folder else None,
                        "files": files})

    @app.context_processor
    def _inject_user():
        return {"user": current_user()}

    @app.after_request
    def _gzip_response(resp):
        """Сжатие текстовых ответов (страницы/JSON) — встроенным gzip, без внешних пакетов."""
        try:
            # HTML-страницы не кэшируем: иначе браузер показывает старую версию конструктора
            # и правки (окно PDF, кнопки) «не доезжают» до пользователя до жёсткого обновления
            if (resp.mimetype or "").startswith("text/html"):
                resp.headers["Cache-Control"] = "no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
            if resp.direct_passthrough or resp.headers.get("Content-Encoding"):
                return resp
            mime = resp.mimetype or ""
            if not (mime.startswith("text/") or mime in
                    ("application/json", "application/javascript", "image/svg+xml", "application/xml")):
                return resp
            if "gzip" not in (request.headers.get("Accept-Encoding") or "").lower():
                return resp
            data = resp.get_data()
            if len(data) < 1024:
                return resp
            import gzip as _gzip
            packed = _gzip.compress(data, 6)
            if len(packed) >= len(data):
                return resp
            resp.set_data(packed)
            resp.headers["Content-Encoding"] = "gzip"
            resp.headers["Content-Length"] = str(len(packed))
            resp.headers.add("Vary", "Accept-Encoding")
        except Exception:
            pass
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    print(f"Wolf_AutoDoc CRM → http://{WEB_HOST}:{WEB_PORT}  БД: {DB_PATH}")
    # прогреваем сборщик PDF, чтобы первый документ у админа собирался быстро
    try:
        from services.render import warm_up as _warm_up
        _warm_up()
    except Exception:
        pass
    # В фоне прогреваем кэш адресов клиентов: разбор документов занимает
    # секунды, без прогрева первый заход на карточку заявки может не
    # дождаться ответа (Safari показывает «не удаётся подключиться»).
    try:
        import threading as _th
        def _warm_addr():
            try:
                from scripts.warm_cache import warm
                warm()
            except Exception:
                pass
        _th.Thread(target=_warm_addr, daemon=True).start()
    except Exception:
        pass
    serve(app, host=WEB_HOST, port=WEB_PORT, threads=8, channel_timeout=300)
