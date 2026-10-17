"""Журнал действий: кто, когда и что сделал в системе.

Записи уже писались в таблицу events (вход, проверка документа, авто-сборка),
но посмотреть их из интерфейса было нельзя. Экран даёт ответ на вопрос
«кто это изменил» — при спорах с заказчиком и при разборе ошибок.
"""
from flask import Blueprint, request

from core import db
from blocks.shared.layout import render, card as ui_card, item

bp = Blueprint("events", __name__)

# Человеческие подписи для действий из базы
ACTION_LABELS = {
    "login_password": ("🔑", "вход с паролем"),
    "login_telegram": ("🔑", "вход через Telegram"),
    "login_code": ("🔑", "вход по коду"),
    "verified": ("✅", "документ проверен"),
    "unverified": ("↩️", "проверка снята"),
    "rejected": ("🚫", "документ исключён"),
    "restored": ("↩️", "документ возвращён"),
    "autofill": ("⚡", "автозаполнение"),
    "render": ("📄", "документ собран"),
    "sent": ("📤", "отправлено"),
    "created": ("➕", "создано"),
    "updated": ("✏️", "изменено"),
    "accepted": ("🤝", "взято в работу"),
    "scan": ("📥", "разбор документов"),
    "filled": ("📄", "документ заполнен"),
    "take": ("🤝", "взято в работу"),
    "login": ("🔑", "вход"),
    "rendered": ("📄", "документ собран"),
    "product_changed": ("🧳", "смена продукта"),
    "converted": ("🔄", "шаблон сконвертирован"),
    "uploaded": ("⬆️", "шаблон загружен"),
    "taken": ("🤝", "взято в работу"),
    "doc_added": ("➕", "документ добавлен в продукт"),
    "doc_removed": ("➖", "документ убран из продукта"),
    "bot_saved": ("💾", "сохранено ботом"),
}

ENTITY_LABELS = {
    "user": "пользователь",
    "application": "заявка",
    "application_document": "документ заявки",
    "client": "клиент",
    "template": "шаблон",
    "template_variable": "переменная",
    "drive_scan": "разбор Google Drive",
}


def _fmt(ts: str) -> str:
    if not ts:
        return ""
    return str(ts)[:16]


def recent_events(limit: int = 100, entity: str = "", actor: str = "") -> list:
    """Последние записи журнала с необязательными фильтрами."""
    where, args = [], []
    if entity:
        where.append("entity = ?")
        args.append(entity)
    if actor:
        where.append("actor = ?")
        args.append(actor)
    sql = "SELECT * FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(int(limit))
    try:
        return db.q(sql, tuple(args))
    except Exception:
        return []


def actors() -> list:
    """Кто вообще фигурирует в журнале."""
    try:
        rows = db.q("SELECT actor, COUNT(*) n FROM events WHERE actor <> '' "
                    "GROUP BY actor ORDER BY n DESC LIMIT 12")
        return [(r["actor"], r["n"]) for r in rows]
    except Exception:
        return []


def _describe(row) -> tuple:
    """Иконка, подпись и уточнение по одной записи журнала."""
    act = (row.get("action") or "").strip()
    icon, label = ACTION_LABELS.get(act, ("•", act or "действие"))
    det = ""
    try:
        import json
        payload = json.loads(row.get("payload") or "{}")
        if isinstance(payload, dict):
            parts = []
            if payload.get("app"):
                parts.append("заявка #%s" % payload["app"])
            if payload.get("tpl"):
                parts.append("шаблон %s" % payload["tpl"])
            for k in ("documents", "values", "done", "failed"):
                if payload.get(k):
                    parts.append("%s: %s" % (k, payload[k]))
            det = ", ".join(parts)
    except Exception:
        det = ""
    return icon, label, det


@bp.route("/events")
def events_page():
    limit = request.args.get("limit", "100")
    entity = request.args.get("entity", "")
    actor = request.args.get("actor", "")
    try:
        limit_n = max(20, min(500, int(limit)))
    except Exception:
        limit_n = 100

    rows = recent_events(limit_n, entity, actor)

    def _one(r):
        icon, label, det = _describe(r)
        ent = r.get("entity") or ""
        ent_label = ENTITY_LABELS.get(ent, ent)
        who = r.get("actor") or "система"
        sub = " · ".join(x for x in (
            who,
            _fmt(r.get("created_at")),
            ("%s #%s" % (ent_label, r.get("entity_id"))) if r.get("entity_id") else ent_label,
        ) if x)
        title = label.capitalize() + ((" — " + det) if det else "")
        return item(icon, title, sub=sub, tone="blue" if det else "muted")

    listing = "".join(_one(r) for r in rows) or (
        '<div class="muted" style="padding:8px 2px">Записей пока нет.</div>')

    ent_opts = "".join(
        '<option value="%s"%s>%s</option>' % (k, " selected" if k == entity else "", v)
        for k, v in ENTITY_LABELS.items())
    act_opts = "".join(
        '<option value="%s"%s>%s</option>' % (a, " selected" if a == actor else "",
                                              "%s (%s)" % (a, n))
        for a, n in actors())
    lim_opts = "".join(
        '<option value="%s"%s>%s</option>' % (v, " selected" if limit_n == v else "", v)
        for v in (100, 200, 500))
    reset = ("<a href='/events' style='padding:11px 14px;color:#6B7C70;font-size:14px'>сбросить</a>"
             if (entity or actor) else "")

    body = f"""
<h1>Журнал действий</h1>
<div class="page-sub">Кто и что менял в системе: входы, проверки документов, автозаполнение, сборка. Записи хранятся постоянно.</div>
<form method="get" action="/events" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin:14px 0 18px">
  <label style="display:flex;flex-direction:column;gap:5px">
    <span style="font-size:12.5px;color:#6B7C70">Раздел</span>
    <select name="entity" style="padding:10px 12px;border:1px solid #D7E3DA;border-radius:9px;font-size:15px">
      <option value="">все</option>{ent_opts}
    </select>
  </label>
  <label style="display:flex;flex-direction:column;gap:5px">
    <span style="font-size:12.5px;color:#6B7C70">Кто</span>
    <select name="actor" style="padding:10px 12px;border:1px solid #D7E3DA;border-radius:9px;font-size:15px">
      <option value="">любой</option>{act_opts}
    </select>
  </label>
  <label style="display:flex;flex-direction:column;gap:5px">
    <span style="font-size:12.5px;color:#6B7C70">Сколько показать</span>
    <select name="limit" style="padding:10px 12px;border:1px solid #D7E3DA;border-radius:9px;font-size:15px">
      {lim_opts}
    </select>
  </label>
  <button type="submit" style="padding:11px 20px;border:0;border-radius:9px;background:#2F7D5B;color:#fff;font-size:15px;cursor:pointer">Показать</button>
  {reset}
</form>
{ui_card('Последние записи · ' + str(len(rows)), listing, emoji="🕓", tone="blue", open=True)}
"""
    return render("Журнал действий", "dashboard", body)
