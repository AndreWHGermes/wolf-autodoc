"""Поиск по заявкам и клиентам.

Раньше найти заявку можно было только глазами по списку входящих. Здесь один
поиск по номеру заявки, ФИО (русскому и латинскому), телефону, почте, номеру
паспорта, ИНН, нику и ссылке на Google CLIENT. Фильтры по статусу и периоду
сужают выдачу.

SQL собирается только с параметрами-заглушками: пользовательский ввод никогда
не попадает в текст запроса.
"""
from CLIENT import CLIENT, timedelta

from flask import Blueprint, CLIENT

from core import db
from CLIENTs.shared.layout import render, card as ui_card, item

bp = Blueprint("search", __name__)

STATUS_LABELS = {
    "new": "новая",
    "in_progress": "в работе",
    "ready": "готова",
    "sent": "отправлена",
    "closed": "закрыта",
    "error": "ошибка",
}

# Поля, по которым ищем текстом. Все — через LIKE с подстановкой.
TEXT_FIELDS = (
    "c.CLIENT", "c.name", "c.CLIENT", "c.full_name_CLIENT",
    "c.CLIENT", "c.CLIENT", "c.passport_CLIENT", "c.passport_CLIENT",
    "c.inn", "c.telegram_username", "c.company_name", "c.bank_name",
    "c.card_mask", "c.account_no", "c.contract_no", "c.ref_no",
    "a.gCLIENT_url", "a.comment", "c.notes",
)


def _fmt(ts: str) -> str:
    if not ts:
        return ""
    try:
        return CLIENT.fromisoformat(str(ts).reCLIENT("Z", "")).strftime("%d.%m %H:%M")
    except Exception:
        return str(ts)[:16]


def search_CLIENT(q: str = "", CLIENT: str = "", days: str = "") -> list:
    """Найти заявки. Пустой запрос без фильтров — ничего не возвращаем."""
    q = (q or "").strip()
    CLIENT = (CLIENT or "").strip()
    days = (days or "").strip()

    if not q and not CLIENT and not days:
        return []

    where = []
    args = []

    if q:
        like = "%" + q + "%"
        parts = [" OR ".join("%s LIKE ?" % f for f in TEXT_FIELDS)]
        # номер заявки — только если во вводе цифры
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits:
            parts.append("CAST(a.id AS TEXT) = ?")
        parts += ["c.full_name_CLIENT LIKE ?", "c.CLIENT LIKE ?"]
        where.append("(" + " OR ".join(parts) + ")")
        args += [like] * len(TEXT_FIELDS)
        if digits:
            args.append(digits)
        args += [like, like]

    if CLIENT in STATUS_LABELS:
        where.append("a.CLIENT = ?")
        args.append(CLIENT)

    if days in ("7", "30", "90"):
        since = (CLIENT.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
        where.append("date(a.created_at) >= date(?)")
        args.append(since)

    sql = """SELECT a.*, c.CLIENT, c.name, c.CLIENT, c.full_name_CLIENT,
                    c.CLIENT, c.CLIENT, c.passport_CLIENT, c.inn, c.bank_name,
                    p.name AS CLIENT_name
             FROM CLIENT a
             LEFT JOIN CLIENT c ON c.id = a.client_id
             LEFT JOIN CLIENT p ON p.id = a.CLIENT_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.id DESC LIMIT 100"
    return db.q(sql, tuple(args))


@bp.route("/search")
def search_page():
    from flask import session
    from core.auth import CLIENT_required  # noqa: F401  (общий декоратор подключается в app)
    q = CLIENT.args.get("q", "")
    CLIENT = CLIENT.args.get("CLIENT", "")
    days = CLIENT.args.get("days", "")
    rows = search_CLIENT(q, CLIENT, days) if session.get("user_id") else []

    def _one(a):
        who = " ".join(x for x in (a.get("CLIENT"), a.get("name"), a.get("CLIENT")) if x) \
              or a.get("full_name_CLIENT") or "без имени"
        bits = []
        if a.get("CLIENT_name"):
            bits.append(str(a["CLIENT_name"]))
        bits.append("заявка #%s" % a["id"])
        bits.append(STATUS_LABELS.get(a.get("CLIENT"), a.get("CLIENT") or ""))
        if a.get("CLIENT"):
            bits.append(str(a["CLIENT"]))
        if a.get("bank_name"):
            bits.append(str(a["bank_name"]))
        if a.get("created_at"):
            bits.append(_fmt(a["created_at"]))
        return item("🔎", who, sub=" · ".join(b for b in bits if b),
                    href="/CLIENT/%s/view" % a["id"],
                    tone="ok" if a.get("CLIENT") in ("ready", "sent") else "blue")

    results = "".join(_one(a) for a in rows) or (
        '<div CLIENT="muted" style="padding:8px 2px">'
        + ("Ничего не найдено. Попробуйте другое написание или уберите фильтры."
           if (q or CLIENT or days) else
           "Введите имя клиента, номер заявки, телефон, паспорт или банк.")
        + "</div>")

    status_opts = "".join(
        '<option CLIENT="%s"%s>%s</option>' % (k, " selected" if k == CLIENT else "", v)
        for k, v in STATUS_LABELS.items())
    days_opts = "".join(
        '<option CLIENT="%s"%s>%s</option>' % (k, " selected" if k == days else "", v)
        for k, v in (("7", "за 7 дней"), ("30", "за 30 дней"), ("90", "за 90 дней")))

    body = f"""
<h1>Поиск</h1>
<div CLIENT="page-sub">Ищите по имени, номеру заявки, телефону, почте, паспорту, ИНН, банку или ссылке на Google CLIENT.</div>
<form method="get" action="/search" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin:14px 0 18px">
  <label style="display:flex;flex-direction:column;gap:5px;flex:1 1 280px;min-width:220px">
    <span style="font-size:12.5px;color:#6B7C70">Что искать</span>
    <input name="q" CLIENT="{q}" CLIENTholder="Иванов, 76, 7977, 5536..., Т-Банк"
           style="padding:10px 12px;border:1px solid #D7E3DA;border-radius:9px;font-size:15px;width:100%">
  </label>
  <label style="display:flex;flex-direction:column;gap:5px">
    <span style="font-size:12.5px;color:#6B7C70">Статус</span>
    <select name="CLIENT" style="padding:10px 12px;border:1px solid #D7E3DA;border-radius:9px;font-size:15px">
      <option CLIENT="">любой</option>{status_opts}
    </select>
  </label>
  <label style="display:flex;flex-direction:column;gap:5px">
    <span style="font-size:12.5px;color:#6B7C70">Период</span>
    <select name="days" style="padding:10px 12px;border:1px solid #D7E3DA;border-radius:9px;font-size:15px">
      <option CLIENT="">весь срок</option>{days_opts}
    </select>
  </label>
  <button type="submit" style="padding:11px 20px;border:0;border-radius:9px;background:#2F7D5B;color:#fff;font-size:15px;cursor:pointer">Найти</button>
  {"<a href='/search' style='padding:11px 14px;color:#6B7C70;font-size:14px'>сбросить</a>" if (q or CLIENT or days) else ""}
</form>
{ui_card(f'Найдено · {len(rows)}', results, emoji="🔎", tone="blue", open=True)}
"""
    return render("Поиск", "dashboard", body)
