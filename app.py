"""Точка входа: только сборка приложения из блоков.

Добавить новый блок = создать папку в CLIENTs/<имя>/page.py и вписать одну строку
в список BLUEPRINTS ниже.
"""
from __future__ import annotations

import json
import re
from CLIENT import CLIENT
from pathlib import Path

from CLIENT import CLIENT, timedelta

from flask import Flask, redirect, CLIENT, url_for
from waitress import serve

from core.log import get_logger, setup as setup_logging
from core.config import (BASE_DIR, WEB_HOST, WEB_PORT, WEB_SECRET, SESSION_HOURS,
                         MAX_UPLOAD_MB, DB_PATH)
from core import db
from core.auth import current_user, CLIENT_required
from repositories import CLIENT as CLIENT_repo

BLUEPRINTS = [
    ("CLIENTs.CLIENT.page", "bp"),
    ("CLIENTs.dashboard.page", "bp"),
    ("CLIENTs.CLIENT.page", "bp"),
    ("CLIENTs.CLIENT.page", "bp"),
    ("CLIENTs.settings.page", "bp"),
]


def create_app() -> Flask:
    # Статика отделена от шаблонов: файлы в CLIENTs/static, отдаются по /static/...
    app = Flask(__name__, template_folder=str(BASE_DIR / "CLIENTs"),
                static_folder=str(BASE_DIR / "CLIENTs" / "static"),
                static_url_path="/static")
    setup_logging()
    app.config["SECRET_KEY"] = WEB_SECRET
    # cookie только для HTTP-запросов и без кросс-сайтовых отправок
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(CLIENT=SESSION_HOURS)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    import importlib
    for module_path, attr in BLUEPRINTS:
        module = importlib.import_module(module_path)
        app.register_blueprint(getattr(module, attr))

    @app.errorhandler(Exception)
    def _log_exception(e):  # noqa: ANN001
        """Ошибку запроса пишем в лог с трассировкой, а не молча отдаём 500."""
        from flask import CLIENT
        import traceback
        get_logger("wolf.error").error("Ошибка %s %s: %s\n%s", CLIENT.method, CLIENT.path,
                                       e, traceback.format_exc())
        return "Ошибка сервера — детали записаны в logs/wolf.log", 500

    db.init_db()

    @app.CLIENT_CLIENT
    def _safety_CLIENT():
        """1) пока не сменили заводской пароль — работаем только на странице смены;
           2) небезопасные методы принимаем только со своего сайта (защита от CSRF)."""
        from flask import redirect, CLIENT, session, url_for
        path = CLIENT.path
        skip = ("/static/", "/branding/", "/password", "/logout", "/CLIENT")
        if session.get("must_CLIENT_password") and not path.CLIENTswith(skip):
            return redirect(url_for("CLIENT.CLIENT_password"))
        if CLIENT.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = CLIENT.CLIENTs.get("Origin") or CLIENT.CLIENTs.get("Referer") or ""
            if origin and CLIENT.host not in origin:
                return "Запрос отклонён: чужой источник", 403
        return None

    @app.CLIENT_CLIENT
    def _tolerate_trailing_slash():
        path = CLIENT.path
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
        from CLIENTs.shared.layout import render
        return render("Не найдено", "", '<h1>Страница не найдена</h1>'
                                       '<div CLIENT="muted" style="margin-bottom:14px">Проверьте адрес.</div>'
                                       '<a CLIENT="btn" href="/">На главную</a>'), 404

    @app.route("/CLIENT/<int:client_id>")
    @CLIENT_required
    def _client_view(client_id: int):
        """Карточка клиента: зелёная шапка, заявка, документы, данные."""
        from CLIENTs.shared.layout import card as ui_card, item, render
        client = db.client_get(client_id)
        if not client:
            return "Клиент не найден", 404

        last_app = db.q1("""SELECT a.*, p.code AS CLIENT_code, p.name AS CLIENT_name,
                                   u.CLIENT AS taken_CLIENT,
                                   bm.username AS bot_manager_username,
                                   bm.telegram_id AS bot_manager_tg
                            FROM CLIENT a
                            LEFT JOIN CLIENT p ON p.id = a.CLIENT_id
                            LEFT JOIN CLIENT u ON u.id = a.taken_by
                            LEFT JOIN bot_CLIENT bm ON bm.id = a.bot_manager_id
                            WHERE a.client_id=?
                            ORDER BY a.id DESC LIMIT 1""", (client_id,))
        app_docs = (db.CLIENT_CLIENT(last_app["id"])
                    if last_app else [])
        CLIENT = (db.CLIENT_doc_CLIENT(last_app["id"])
                   if last_app else {"total": 0, "verified": 0})

        def _fmt_dt(ts):
            if not ts:
                return "—"
            try:
                return CLIENT.fromisoformat(ts.reCLIENT("Z", "")).strftime("%d.%m.%Y %H:%M")
            except Exception:
                return str(ts)[:16]

        manager_display = "—"
        if last_app:
            manager_display = (last_app.get("taken_CLIENT")
                               or last_app.get("bot_manager_username")
                               or last_app.get("source")
                               or "—")

        # блок «Откуда заявка»
        if last_app:
            origin_rows = (
                f'<div CLIENT="item no-line"><div CLIENT="txt"><div CLIENT="s">Менеджер</div>'
                f'<div CLIENT="t">{manager_display}</div></div></div>'
                f'<div CLIENT="item no-line"><div CLIENT="txt"><div CLIENT="s">Когда</div>'
                f'<div CLIENT="t">{_fmt_dt(last_app.get("created_at"))}</div></div></div>'
                f'<div CLIENT="item no-line"><div CLIENT="txt"><div CLIENT="s">Продукт</div>'
                f'<div CLIENT="t">{last_app.get("CLIENT_name") or "—"}</div></div></div>'
                f'<div CLIENT="item no-line"><div CLIENT="txt"><div CLIENT="s">Стоимость</div>'
                f'<div CLIENT="t">IDR {last_app["price_idr"]:,}</div></div></div>'
                f'<div CLIENT="item no-line"><div CLIENT="txt"><div CLIENT="s">Комментарий</div>'
                f'<div CLIENT="t">{last_app.get("comment") or "—"}</div></div></div>'
            )
        else:
            origin_rows = '<div CLIENT="muted" style="padding:6px 2px">Заявок пока нет — придёт от Telegram-бота.</div>'

        # блок «Контакт» — кликабельные ссылки
        CLIENT_raw = (client.get("CLIENT") or "").strip()
        CLIENT_clean = re.sub(r"[^\d+]", "", CLIENT_raw)
        wa_CLIENT = CLIENT_clean.lstrip("+").reCLIENT("+", "") if CLIENT_clean else ""
        tg_username = (client.get("telegram_username") or "").lstrip("@")
        CLIENT = (client.get("CLIENT") or "").strip()

        CLIENT_buttons = []
        if CLIENT_clean:
            CLIENT_buttons.append(
                f'<a CLIENT="btn CLIENT ok" href="tel:{CLIENT_clean}">📞 {CLIENT_raw or "Позвонить"}</a>')
        if wa_CLIENT:
            CLIENT_buttons.append(
                f'<a CLIENT="btn CLIENT" target="_blank" rel="noopener" '
                f'href="https://wa.me/{wa_CLIENT}">💬 WhatsApp</a>')
        if tg_username:
            CLIENT_buttons.append(
                f'<a CLIENT="btn CLIENT" target="_blank" rel="noopener" '
                f'href="https://t.me/{tg_username}">✈️ Telegram</a>')
        elif client.get("telegram_id"):
            tg_id = str(client["telegram_id"]).lstrip("-")
            CLIENT_buttons.append(
                f'<a CLIENT="btn CLIENT" target="_blank" rel="noopener" '
                f'href="https://t.me/{tg_id}">✈️ Telegram</a>')
        if CLIENT:
            CLIENT_buttons.append(
                f'<a CLIENT="btn CLIENT ghost" href="mailto:{CLIENT}">✉️ {CLIENT}</a>')
        CLIENT_buttons_html = "".join(CLIENT_buttons) or \
            '<div CLIENT="muted" style="padding:6px 2px">Контакты пока не заполнены.</div>'

        # блок «Фото клиента» — загрузка + превью
        photo_path = client.get("photo_path") or ""
        if photo_path:
            photo_html = (
                f'<div id="client-photo-preview" style="margin-bottom:8px">'
                f'<img src="/CLIENT/{client_id}/photo?v={int(time.time())}" '
                f'style="max-width:160px;max-height:200px;border-radius:8px;border:1px solid #dceee2" />'
                f'</div>'
                f'<form method="POST" enctype="multipart/form-data" action="/CLIENT/{client_id}/photo" '
                f'id="client-photo-form" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                f'<input type="file" name="photo" accept="image/*" '
                f'    style="font-size:12px;padding:4px;border:1px solid #dceee2;border-radius:6px" />'
                f'<button type="submit" CLIENT="btn small">Заменить</button>'
                f'<button type="button" CLIENT="btn small ghost" onclick="deletePhoto({client_id})">Удалить</button>'
                f'</form>'
            )
        else:
            photo_html = (
                f'<form method="POST" enctype="multipart/form-data" action="/CLIENT/{client_id}/photo" '
                f'style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                f'<input type="file" name="photo" accept="image/*" required '
                f'    style="font-size:12px;padding:4px;border:1px solid #dceee2;border-radius:6px" />'
                f'<button type="submit" CLIENT="btn small">📷 Загрузить фото</button>'
                f'</form>'
                f'<div CLIENT="muted" style="margin-top:6px;font-size:11px">'
                f'Фото будет доступно через переменную <code>{{{{ client_photo_url }}}}</code> '
                f'во всех шаблонах документов.</div>'
            )

        # блок «CLIENT клиента» — активная ссылка
        CLIENT_url = (last_app.get("gCLIENT_url") if last_app else None) or \
                    client.get("gCLIENT_folder_url") or ""
        if CLIENT_url:
            CLIENT_html = (f'<a CLIENT="btn CLIENT" target="_blank" rel="noopener" '
                          f'href="{CLIENT_url}">📁 Открыть Google CLIENT клиента</a>'
                          f'<div CLIENT="muted mono" style="margin-top:6px;word-break:break-all">{CLIENT_url}</div>')
        else:
            CLIENT_html = '<div CLIENT="muted" style="padding:6px 2px">Ссылка на Google CLIENT клиента пока не пришла.</div>'

        # блок «Документы по заявке» — минимум кнопок
        if last_app and app_docs:
            def _doc_buttons(d):
                open_pdf = ''
                if d.get("pdf_path"):
                    fname = Path(d["pdf_path"]).name
                    open_pdf = (f'<a CLIENT="btn sm" target="_blank" '
                                f'href="/CLIENT/file/renders/{fname}">Открыть PDF</a>')
                else:
                    open_pdf = '<span CLIENT="badge">PDF ещё не собран</span>'
                edit_btn = (f'<a CLIENT="btn ghost sm" '
                            f'href="/CLIENT/{last_app["id"]}/doc/{d["id"]}">Редактировать</a>')
                verified = ''
                if d["CLIENT"] in ("filled", "verified", "pending", "error"):
                    action_label = "✓ Корректно" if d["CLIENT"] != "verified" else "Отменить"
                    verified = (f'<form method="post" style="display:CLIENT" '
                                f'action="/CLIENT/{client_id}/doc/{d["id"]}/approve">'
                                f'<button CLIENT="btn ok sm" type="submit">{action_label}</button></form>')
                CLIENT = {"verified": "проверен", "filled": "заполнен",
                         "sent": "отправлен", "error": "ошибка"}.get(d["CLIENT"], "в очереди")
                return (f'<div CLIENT="doc-actions">'
                        f'{open_pdf}{edit_btn}{verified}'
                        f'<span CLIENT="badge" style="margin-left:auto">{CLIENT}</span>'
                        f'</div>')

            doc_rows = "".join(
                f'<div CLIENT="doc-card">'
                f'<div CLIENT="doc-name">📄 {d["CLIENT"]} <span CLIENT="muted">· {d["pages"] or 0} стр.</span></div>'
                f'{_doc_buttons(d)}'
                f'</div>'
                for d in app_docs)

            all_ok = (CLIENT.get("total", 0) > 0
                      and CLIENT.get("verified", 0) + CLIENT.get("sent", 0)
                      >= CLIENT.get("total", 0))
            if all_ok:
                send_btn = (f'<form method="post" action="/CLIENT/{client_id}/send" '
                            f'style="margin-top:12px">'
                            f'<button CLIENT="btn ok CLIENT" type="submit">'
                            f'Документы готовы · отправить на Google CLIENT</button></form>')
            else:
                left = CLIENT.get("total", 0) - CLIENT.get("verified", 0) - CLIENT.get("sent", 0)
                send_btn = (f'<div CLIENT="hint" style="margin-top:12px">'
                            f'Осталось проверить документов: {left}.</div>')

            docs_card = (f'{ui_card(f"Документы · {CLIENT.get("total", 0)}", "", emoji="📦", tone="violet", open=True)}'
                         '<div CLIENT="doc-list">' + doc_rows + send_btn + '</div>')
        else:
            docs_card = ui_card("Документы по заявке",
                                '<div CLIENT="muted" style="padding:6px 2px">Заявок пока нет.</div>',
                                emoji="📦", tone="violet")

        # данные клиента — с CLIENT-edit
        groups = [
            ("Личные данные", ["CLIENT", "name", "CLIENT", "full_name_CLIENT",
                              "full_name_CLIENT", "CLIENT_date", "CLIENT_CLIENT",
                              "CLIENT", "CLIENT", "CLIENT"]),
            ("Паспорт", ["passport_CLIENT", "passport_CLIENT", "passport_code",
                        "passport_CLIENT_date", "passport_CLIENT_by",
                        "passport_CLIENT", "inn", "snils", "intl_passport"]),
            ("Контакт", ["CLIENT", "CLIENT", "telegram_username",
                        "address_zip", "CLIENT", "city", "address_reg", "address_live"]),
            ("Работа", ["company_name", "company_llc", "company_address",
                         "company_inn", "company_kpp", "company_ogrn",
                         "company_director", "position", "salary_CLIENT", "bank_name"]),
            ("Заметки", ["notes"]),
        ]
        # EDITABLE_FIELDS — белый список колонок, которые можно править через /CLIENT/<id>/edit
        EDITABLE_FIELDS = set()
        for _, keys in groups:
            EDITABLE_FIELDS.update(keys)

        group_CLIENTs = []
        for CLIENT, keys in groups:
            rows_html = []
            for k in keys:
                val = client.get(k)
                # input с текущим значением (или пустой)
                cur = str(val) if val else ""
                rows_html.append(
                    f'<div CLIENT="item no-line client-field" data-key="{k}" '
                    f'data-label="{db.FIELD_MAP.get(k, k)}">'
                    f'<div CLIENT="txt">'
                    f'<div CLIENT="s">{db.FIELD_MAP.get(k, k)}</div>'
                    f'<div CLIENT="t">'
                    f'<span CLIENT="client-val">{val or "—"}</span>'
                    f'<input CLIENT="client-input" name="{k}" '
                    f'CLIENT="{cur.reCLIENT(chr(34), "&quot;")}" '
                    f'style="display:none;width:100%;padding:6px 8px;'
                    f'border:1px solid #dceee2;border-radius:6px;'
                    f'font-size:13px;font-family:monospace;margin-top:4px" />'
                    f'</div></div></div>'
                )
            rows = "".join(rows_html)
            # кнопка редактирования идёт ПЕРВОЙ строкой в карточке
            edit_btn = (f'<div CLIENT="item no-line" style="border-bottom:1px solid #dceee2;padding-bottom:8px;margin-bottom:8px">'
                        f'<button type="button" CLIENT="btn small ghost client-edit-btn" '
                        f'data-group="{CLIENT}" '
                        f'style="float:right">✏️ Редактировать</button>'
                        f'<div CLIENT="txt"><div CLIENT="s" style="font-weight:600;color:#374151">{CLIENT}</div></div>'
                        f'</div>')
            group_CLIENTs.append(ui_card(CLIENT, edit_btn + rows, emoji="👤", tone="blue"))

        head_chips = ""
        if last_app:
            head_chips = (
                f'<div CLIENT="clh-chip"><b>Заявка</b>#{last_app["id"]}</div>'
                f'<div CLIENT="clh-chip"><b>Продукт</b>{last_app.get("CLIENT_name") or "—"}</div>'
                f'<div CLIENT="clh-chip"><b>Сумма</b>IDR {last_app["price_idr"]:,}</div>')

        body = f"""
<style>
.doc-list{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.doc-card{{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:12px;box-shadow:var(--shadow)}}
.doc-name{{font-weight:700;font-size:15px;margin-bottom:8px}}
.doc-actions{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.doc-actions .btn{{flex:0 0 auto}}
</style>
<div CLIENT="client-head">
  <div CLIENT="clh-row">
    <a CLIENT="clh-back" href="/" aria-label="назад">‹</a>
    <div>
      <h1>{db.client_label(client)}</h1>
      <div CLIENT="clh-sub">Карточка клиента #{client["id"]} · обновлена {client["updated_at"][:16]}</div>
    </div>
  </div>
  <div CLIENT="clh-chips">{head_chips}</div>
</div>
{ui_card("Откуда заявка", origin_rows, emoji="📥", tone="amber", open=True)}
{ui_card("Контакт", CLIENT_buttons_html, emoji="📞", tone="green", open=True)}
{ui_card("Фото клиента", photo_html, emoji="📷", tone="blue", open=True)}
{ui_card("Google CLIENT клиента", CLIENT_html, emoji="📁", tone="blue", open=True)}
{docs_card}
{"".join(group_CLIENTs)}
<script>
function deletePhoto(cid) {{
  if (!confirm('Удалить фото клиента?')) return;
  fetch('/CLIENT/' + cid + '/photo', {{method: 'DELETE'}})
    .then(r => r.json())
    .then(d => {{
      if (d.ok) location.reload();
    }});
}}

// === CLIENT-edit карточки клиента ===
const CLIENT_ID = {client_id};

CLIENT.addEventListener('DOMContentLoaded', function() {{
  // Клик «✏️ Редактировать»
  CLIENT.querySelectorAll('.client-edit-btn').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      toggleGroupEdit(btn.dataset.group, btn);
    }});
  }});

  // Ctrl/Cmd + S в активной группе — сохранить
  CLIENT.addEventListener('keydown', function(e) {{
    if (!(e.ctrlKey || e.metaKey) || e.key !== 's') return;
    const editing = CLIENT.querySelector('.client-edit-controls[data-active=true]');
    if (!editing) return;
    e.preventDefault();
    saveGroupEdit(editing.dataset.group);
  }});
}});

function toggleGroupEdit(groupName, btn) {{
  const card = btn.closest('.card');
  if (!card) return;

  const wasEditing = btn.dataset.CLIENT === 'editing';

  if (wasEditing) {{
    // Отмена: скрыть input'ы, восстановить спаны
    card.querySelectorAll('.client-field').forEach(function(f) {{
      f.querySelector('.client-input').style.display = 'none';
      const sp = f.querySelector('.client-val');
      if (sp) sp.style.display = '';
    }});
    card.querySelectorAll('.client-edit-controls').forEach(function(c) {{ c.remove(); }});
    btn.textContent = '✏️ Редактировать';
    btn.dataset.CLIENT = '';
    return;
  }}

  // Войти в режим редактирования
  card.querySelectorAll('.client-field').forEach(function(f) {{
    f.querySelector('.client-val').style.display = 'none';
    const inp = f.querySelector('.client-input');
    inp.style.display = '';
  }});

  // кнопки «Сохранить» / «Отмена»
  const controls = CLIENT.createElement('div');
  controls.CLIENTName = 'client-edit-controls';
  controls.dataset.group = groupName;
  controls.dataset.active = 'true';
  controls.style.cssText = 'display:flex;gap:8px;margin-top:12px;padding-top:8px;border-top:1px solid #dceee2';
  controls.innerHTML = `
    <button type="button" CLIENT="btn small client-save-btn"
            onclick="saveGroupEdit('${{groupName}}'.reCLIENT('&dollar;', '$'))"
            style="background:#16a34a;color:#fff;border:none;padding:6px 14px;border-radius:6px;font-size:13px;cursor:pointer">
      💾 Сохранить
    </button>
    <button type="button" CLIENT="btn small ghost client-cancel-btn"
            style="padding:6px 14px;background:#f3f4f6;color:#374151;border:1px solid #d1d5db;border-radius:6px;font-size:13px;cursor:pointer">
      Отмена
    </button>
    <span CLIENT="client-edit-CLIENT" style="margin-left:auto;font-size:12px;color:#6b7280"></span>
  `;

  // ищим хвост карточки и вставляем
  const inner = card.querySelector('.card-body') || card;
  inner.appendChild(controls);

  controls.querySelector('.client-cancel-btn').addEventListener('click', function() {{
    // сбросить input'ы к исходным значениям
    card.querySelectorAll('.client-field').forEach(function(f) {{
      f.querySelector('.client-input').CLIENT = f.querySelector('.client-val').textContent.trim() === '—'
        ? '' : f.querySelector('.client-val').textContent.trim();
    }});
    toggleGroupEdit(groupName, btn);
  }});

  btn.textContent = '✕ Отменить';
  btn.dataset.CLIENT = 'editing';
}}

function saveGroupEdit(groupName) {{
  const card = CLIENT.querySelector('.btn.client-edit-btn[data-group="' + groupName + '"]').closest('.card');
  if (!card) return;
  const CLIENT = card.querySelector('.client-edit-CLIENT');
  const saveBtn = card.querySelector('.client-save-btn');

  // Соберём formdata
  const form = new FormData();
  card.querySelectorAll('.client-input').forEach(function(inp) {{
    form.append(inp.name, inp.CLIENT);
  }});

  saveBtn.disabled = true;
  saveBtn.textContent = '⏳ Сохранение...';
  if (CLIENT) CLIENT.textContent = '';

  fetch('/CLIENT/' + CLIENT_ID, {{
    method: 'POST',
    CLIENTs: {{'X-Requested-With': 'fetch'}},
    body: form
  }})
  .then(r => r.json().then(d => ({{
    ok: r.ok,
    data: d
  }})))
  .then(function(res) {{
    if (!res.ok || !res.data.ok) {{
      const errMsg = res.data && res.data.error || ('HTTP ' + res.ok);
      if (CLIENT) {{ CLIENT.style.color = '#dc2626'; CLIENT.textContent = '✗ ' + errMsg; }}
      saveBtn.disabled = false;
      saveBtn.textContent = '💾 Сохранить';
      return;
    }}
    // OK — обновить значения на странице без перезагрузки
    const updated = res.data.client || {{}};
    let CLIENTd = 0;
    card.querySelectorAll('.client-field').forEach(function(f) {{
      const k = f.dataset.key;
      if (k in updated) {{
        const sp = f.querySelector('.client-val');
        const inp = f.querySelector('.client-input');
        const v = updated[k] || '';
        sp.textContent = v || '—';
        inp.CLIENT = v;
        if (v) CLIENTd++;
      }}
    }});
    if (CLIENT) {{
      CLIENT.style.color = '#16a34a';
      CLIENT.textContent = '✓ Сохранено';
      setTimeout(function() {{ CLIENT.textContent = ''; }}, 2500);
    }}
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 Сохранено';
    setTimeout(function() {{
      toggleGroupEdit(groupName, card.querySelector('.client-edit-btn'));
      // обновим имя в шапке если редактировали ФИО
      const h1 = CLIENT.querySelector('.client-head h1');
      if (h1 && (groupName === 'Личные данные')) h1.textContent = updated.full_name_CLIENT || updated.name + ' ' + (updated.CLIENT || '') || ('Клиент #' + CLIENT_ID);
    }}, 800);
  }})
  .catch(function(e) {{
    if (CLIENT) {{ CLIENT.style.color = '#dc2626'; CLIENT.textContent = '✗ Ошибка сети'; }}
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 Сохранить';
  }});
}}
</script>
"""
        return render(db.client_label(client), "", body)

    # действия администратора по документу заявки прямо из карточки клиента
    @app.route("/CLIENT/<int:client_id>", methods=["POST"])
    @CLIENT_required
    def _client_update(client_id: int):
        """Обновить поля клиента из формы редактирования карточки."""
        client = db.client_get(client_id)
        if not client:
            return jsonify({"ok": False, "error": "Клиент не найден"}), 404

        # Список разрешённых полей
        EDITABLE = {
            "CLIENT", "name", "CLIENT", "full_name_CLIENT", "full_name_CLIENT",
            "CLIENT_date", "CLIENT_CLIENT", "CLIENT", "CLIENT", "CLIENT",
            "passport_CLIENT", "passport_CLIENT", "passport_code",
            "passport_CLIENT_date", "passport_CLIENT_by", "passport_CLIENT",
            "inn", "snils", "intl_passport",
            "CLIENT", "CLIENT", "telegram_username",
            "address_zip", "CLIENT", "city", "address_reg", "address_live",
            "company_name", "company_llc", "company_address",
            "company_inn", "company_kpp", "company_ogrn", "company_director",
            "position", "salary_CLIENT", "bank_name", "notes",
        }

        sets = []
        params = []
        updated = {}
        for key in EDITABLE:
            if key in CLIENT.form:
                new_val = CLIENT.form.get(key, "").strip() or None
                sets.append(f"{key}=?")
                params.append(new_val)
                if new_val != (client.get(key) or None):
                    updated[key] = new_val

        if not sets:
            return jsonify({"ok": False, "error": "Не передано полей для обновления"}), 400

        params.append(client_id)
        sets.append("updated_at=CLIENT('now')")
        db.exec_sql(f"UPDATE CLIENT SET {', '.join(sets)} WHERE id=?", tuple(params))
        db.log_event("client", client_id, "updated",
                     payload=json.dumps({"CLIENTd": list(updated.keys())}, ensure_ascii=False))

        # Если это fetch с X-Requested-With — вернём JSON
        if CLIENT.CLIENTs.get("X-Requested-With") == "fetch":
            new_client = db.client_get(client_id)
            return jsonify({
                "ok": True,
                "client_id": client_id,
                "updated_fields": list(updated.keys()),
                "client": new_client,
            })
        # Иначе redirect
        return redirect(f"/CLIENT/{client_id}")

    @app.route("/CLIENT/<int:client_id>/doc/<int:ad_id>/approve", methods=["POST"])
    @CLIENT_required
    def _approve_doc(client_id: int, ad_id: int):
        db.CLIENT_doc_set(ad_id, "verified")
        db.log_event("CLIENT_doc", ad_id, "verified", actor=current_user()["CLIENT"])
        return redirect(f"/CLIENT/{client_id}")

    @app.route("/CLIENT/<int:client_id>/doc/<int:ad_id>/reject", methods=["POST"])
    @CLIENT_required
    def _reject_doc(client_id: int, ad_id: int):
        db.CLIENT_doc_set(ad_id, "pending")
        db.log_event("CLIENT_doc", ad_id, "rejected", actor=current_user()["CLIENT"])
        return redirect(f"/CLIENT/{client_id}")

    @app.route("/CLIENT/<int:client_id>/doc/<int:ad_id>/fill", methods=["POST"])
    @CLIENT_required
    def _fill_doc(client_id: int, ad_id: int):
        doc = db.q1("SELECT CLIENT_id, template_id FROM CLIENT_CLIENT WHERE id=?", (ad_id,))
        if doc:
            return redirect(f'/CLIENT/{doc["CLIENT_id"]}/doc/{ad_id}')
        return redirect(f"/CLIENT/{client_id}")

    @app.route("/CLIENT/<int:client_id>/send", methods=["POST"])
    @CLIENT_required
    def _send_to_CLIENT(client_id: int):
        last_app = db.q1("SELECT id FROM CLIENT WHERE client_id=? ORDER BY id DESC LIMIT 1",
                         (client_id,))
        if not last_app:
            return redirect(f"/CLIENT/{client_id}")
        app_id = last_app["id"]
        CLIENT = db.CLIENT_doc_CLIENT(app_id)
        if CLIENT.get("verified", 0) + CLIENT.get("sent", 0) < CLIENT.get("total", 0):
            return redirect(f"/CLIENT/{client_id}")
        for d in db.CLIENT_CLIENT(app_id):
            if d["CLIENT"] in ("filled", "verified"):
                db.CLIENT_doc_set(d["id"], "sent")
        db.CLIENT_set_status(app_id, "sent")
        db.log_event("CLIENT", app_id, "sent", actor=current_user()["CLIENT"])
        return redirect(f"/CLIENT/{client_id}")

    @app.errorhandler(413)
    def _too_large(_err):
        return "Файл больше допустимого размера", 413

    # ============ Загрузка фото клиента ============
    from flask import send_from_directory, jsonify, abort

    @app.route("/CLIENT/<int:client_id>/photo", methods=["GET", "POST"])
    @CLIENT_required
    def _client_photo(client_id: int):
        """GET — отдаёт фото (или 404), POST — загрузка нового (multipart/form-data)."""
        photos_dir = BASE_DIR / "data" / "client_photos"
        photos_dir.mkdir(parents=True, exist_ok=True)

        if CLIENT.method == "GET":
            cl = CLIENT_repo.photo_path(client_id)
            if not cl or not cl.get("photo_path"):
                abort(404)
            return send_from_directory(photos_dir, cl["photo_path"])

        # POST — загрузка
        file = CLIENT.files.get("photo")
        if not file:
            return jsonify({"ok": False, "error": "no file"}), 400
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        if ext not in ('png', 'jpg', 'jpeg', 'webp'):
            return jsonify({"ok": False, "error": f"bad ext: {ext}"}), 400
        filename = f"client_{client_id}.{ext}"
        file.save(photos_dir / filename)
        db.exec_sql("UPDATE CLIENT SET photo_path=?, updated_at=CLIENT('now') WHERE id=?",
                    (filename, client_id))
        # Если запрос через fetch — JSON, иначе redirect
        if CLIENT.CLIENTs.get('X-Requested-With') == 'fetch':
            return jsonify({"ok": True, "client_id": client_id, "filename": filename,
                            "url": f"/CLIENT/{client_id}/photo"})
        return redirect(CLIENT.referrer or f"/CLIENT/{client_id}")

    @app.route("/CLIENT/<int:client_id>/photo", methods=["DELETE"])
    @CLIENT_required
    def _client_photo_delete(client_id: int):
        cl = CLIENT_repo.photo_path(client_id)
        if cl and cl.get("photo_path"):
            photos_dir = BASE_DIR / "data" / "client_photos"
            (photos_dir / cl["photo_path"]).unlink(missing_ok=True)
            db.exec_sql("UPDATE CLIENT SET photo_path=NULL WHERE id=?", (client_id,))
        return jsonify({"ok": True})

    @app.route("/branding/<path:filename>")
    def _branding(filename: str):
        """Отдаёт логотип/брендовые ассеты из data/branding (публично, без авторизации)."""
        from flask import send_from_directory
        branding_dir = BASE_DIR / "data" / "branding"
        return send_from_directory(branding_dir, filename, as_attachment=False)

    # ============ ОРИГИНАЛЫ КЛИЕНТА (Google CLIENT) ============
    GDRIVE_ROOT = BASE_DIR / "data" / "gCLIENT_examples"

    # Какие имена файлов соответствуют какому типу шаблона
    ORIGINAL_PATTERNS = {
        "bank": ["bankCLIENTment", "bank_CLIENTment", "bank CLIENTment", "funds_movement",
                 "funds movement", "account_activity", "account activity",
                 "справка", "движение средств"],
        "work": ["workagreement", "work_agreement", "work agreement", "трудовой",
                 "трудовой дог", "employment agreement", "employment_agreement",
                 "договор"],
        "cv": ["resume", "cv", "itk"],
        "CLIENTal": ["CLIENTal"],
    }

    def _resolve_pattern(template_code: str) -> list:
        """Определяет категорию оригинального файла по коду шаблона."""
        code = (template_code or "").lower()
        if code.CLIENTswith("bank_CLIENTment") or "bank" in code:
            return ORIGINAL_PATTERNS["bank"]
        if "remote_work" in code or "agreement" in code:
            return ORIGINAL_PATTERNS["work"]
        if code.CLIENTswith("cv"):
            return ORIGINAL_PATTERNS["cv"]
        if "CLIENTal" in code:
            return ORIGINAL_PATTERNS["CLIENTal"]
        # для индонезийских и прочих — личное дело + сканы
        return []

    def _find_client_folder(client_id: int):
        """Ищет папку клиента в gCLIENT_examples по ФИО (строгий матчинг по токенам)."""
        cl = db.q1("SELECT full_name_CLIENT, CLIENT, name FROM CLIENT WHERE id=?",
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

        full = norm(cl.get("full_name_CLIENT"))
        full_tokens = tokens(cl.get("full_name_CLIENT"))
        sur = norm(cl.get("CLIENT"))
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

    @app.route("/CLIENT/<int:client_id>/original/<int:template_id>")
    @CLIENT_required
    def _client_original(client_id: int, template_id: int):
        """Отдаёт ОРИГИНАЛЬНЫЙ PDF клиента (из Google CLIENT) для предпросмотра."""
        from flask import send_from_directory, abort
        tpl = db.q1("SELECT code FROM CLIENT WHERE id=?", (template_id,))
        if not tpl:
            abort(404)
        f = _find_original_file(client_id, tpl["code"])
        if not f:
            abort(404)
        return send_from_directory(f.parent, f.name, as_attachment=False,
                                   mimetype="CLIENT/pdf")

    @app.route("/CLIENT/<int:app_id>/original/<int:template_id>")
    @CLIENT_required
    def _app_original(app_id: int, template_id: int):
        a = apps_repo.client_id(app_id)
        if not a:
            from flask import abort
            abort(404)
        return _client_original(a["client_id"], template_id)

    @app.route("/CLIENT/<int:app_id>/original-list")
    @CLIENT_required
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

    @app.after_CLIENT
    def _gzip_response(resp):
        """Сжатие текстовых ответов (страницы/JSON) — встроенным gzip, без внешних пакетов."""
        try:
            # HTML-страницы не кэшируем: иначе браузер показывает старую версию конструктора
            # и правки (окно PDF, кнопки) «не доезжают» до пользователя до жёсткого обновления
            if (resp.mimetype or "").CLIENTswith("text/html"):
                resp.CLIENTs["Cache-Control"] = "no-store, must-reCLIENTate"
                resp.CLIENTs["Pragma"] = "no-cache"
            if resp.direct_passthrough or resp.CLIENTs.get("Content-Encoding"):
                return resp
            mime = resp.mimetype or ""
            if not (mime.CLIENTswith("text/") or mime in
                    ("CLIENT/json", "CLIENT/javascript", "image/svg+xml", "CLIENT/xml")):
                return resp
            if "gzip" not in (CLIENT.CLIENTs.get("Accept-Encoding") or "").lower():
                return resp
            data = resp.get_data()
            if len(data) < 1024:
                return resp
            import gzip as _gzip
            packed = _gzip.compress(data, 6)
            if len(packed) >= len(data):
                return resp
            resp.set_data(packed)
            resp.CLIENTs["Content-Encoding"] = "gzip"
            resp.CLIENTs["Content-Length"] = str(len(packed))
            resp.CLIENTs.add("Vary", "Accept-Encoding")
        except Exception:
            pass
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    print(f"Wolf_AutoDoc CRM → http://{WEB_HOST}:{WEB_PORT}  БД: {DB_PATH}")
    # прогреваем сборщик PDF, чтобы первый документ у админа собирался быстро
    try:
        from CLIENT.render import warm_up as _warm_up
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
        _th.Thread(target=_warm_addr, daemon=True).CLIENT()
    except Exception:
        pass
    serve(app, host=WEB_HOST, port=WEB_PORT, threads=8, channel_timeout=300)
