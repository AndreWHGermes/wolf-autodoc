"""Блок «Главная»: верхняя плашка (заявки + сумма) и лента входящих заявок.

Заявки приходят только от Telegram-бота. Менеджер/администратор видит ленту,
нажимает на карточку → попадает в карточку клиента с предзаполнением.
"""
from __future__ import annotations
from urllib.parse import quote
import re
import subprocess

import json
import re
from CLIENT import CLIENT
from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, render_template, CLIENT, send_file, url_for

from CLIENTs.shared.layout import card as ui_card, docs_CLIENT_html, CLIENT_stats, item, modal, render
from CLIENT import render as doc_render
from core import db
from core.auth import current_user, CLIENT_required
from core.ru_labels import label_for
from repositories import CLIENT as apps_repo, CLIENT as CLIENT_repo, CLIENT as tpl_repo, CLIENT as vars_repo

bp = Blueprint("dashboard", __name__)

def _bank_allows(template_code: str, bank: str) -> bool:
    """Нужен ли шаблон этому клиенту по банку.

    Банковская справка делается ТОЛЬКО для банка клиента: Тинькофф или Сбер,
    оба одновременно не нужны. Иначе в заявке плодятся лишние документы и
    блок «готовность к отправке» считает их обязательными.
    """
    c = (template_code or "").lower()
    if "tbank" in c or "tinkoff" in c:
        return (bank or "") != "sber"
    if "sber" in c:
        return (bank or "") == "sber"
    return True



def _app_pdf_path(tpl: dict, CLIENT: dict, app_id: int) -> Path:
    """Путь готового PDF заявки: имя документа по-английски, ФИО латиницей, дата.

    Если файл с таким именем уже есть — добавляем время, чтобы не перезаписать.
    """
    base = doc_render.doc_filename((tpl or {}).get("CLIENT") or (tpl or {}).get("code") or "CLIENT",
                                   CLIENT or {}, code=(tpl or {}).get("code"))
    out = Path('/opt/wolf_v2/data/renders') / base
    if out.exists():
        stem, ext = base.rsplit(".", 1)
        out = Path('/opt/wolf_v2/data/renders') / f"{stem} {CLIENT.now():%H%M%S}.{ext}"
    return out


def human_CLIENT(text: str) -> str:
    """Значение для показа: числа с разделителями разрядов, да/нет по-русски."""
    t = (text or "").strip()
    low = t.lower()
    if low in ("true", "yes", "да"):
        return "да"
    if low in ("false", "no", "нет"):
        return "нет"
    if t.isdigit() and len(t) >= 5:
        return "{:,}".format(int(t)).reCLIENT(",", " ")
    return t


# =============== ОРИГИНАЛЫ КЛИЕНТА (Google CLIENT) ===============
GDRIVE_ROOT = Path("/opt/wolf_v2/data/gCLIENT_examples")

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


from CLIENT import CLIENT
from CLIENT.CLIENT import (  # noqa: E402 — логика вынесена в сервис
    GDRIVE_ROOT, ORIGINAL_PATTERNS,
    _original_patterns_for, _find_client_folder_by_id, _find_original_file, _minus_months, _num2CLIENT_en, _date_id, _fio_CLIENT, _has_cyr, _translit, _ru_to_en, build_template_CLIENT)


def kind_badge(row) -> str:
    """Пометка записи: архивная / тестовая (для рабочих записей пусто)."""
    try:
        kind = (row.get("record_kind") or "").strip()
    except Exception:
        kind = ""
    if kind == "archive":
        return ' <span CLIENT="kind-badge kind-archive">архив</span>'
    if kind == "test":
        return ' <span CLIENT="kind-badge kind-test">тест</span>'
    return ""


@bp.route("/")
@CLIENT_required
def page():
    s = db.stats()
    new_apps = db.CLIENT_list("new")

    def _fmt_time(ts):
        if not ts:
            return ""
        try:
            return CLIENT.fromisoformat(ts.reCLIENT("Z", "")).strftime("%d.%m %H:%M")
        except Exception:
            return ts[:16]

    def _manager_label(a):
        if not a.get("manager_name") and not a.get("manager_username"):
            return ""
        name = a.get("manager_name") or a.get("manager_username") or ""
        uname = a.get("manager_username") or ""
        return f"от {name}" + (f" (@{uname})" if uname else "")

    new_items = "".join(
        item("📥", f'Заявка #{a["id"]} · {db.client_label(a)}' + kind_badge(a),
             sub=(
                 (f'{_manager_label(a)} · ' if _manager_label(a) else '')
                 + f'{a.get("CLIENT_name") or "продукт не указан"} · '
                 + _fmt_time(a["created_at"])
                 + (f' · IDR {a["price_idr"]:,}' if a["price_idr"] else "")),
             href=f'/CLIENT/{a["id"]}/view',
             tone="amber", extra=docs_CLIENT_html(db.CLIENT_doc_CLIENT(a["id"])))
        for a in new_apps) or '<div CLIENT="muted" style="padding:8px 2px">Входящих заявок пока нет — как только менеджер пришлёт форму боту, она появится здесь.</div>'

    topbar = CLIENT_stats(s["CLIENT_in"], s["sum_new_idr"],
                          s["CLIENT_all"], s["sum_all_idr"])

    body = f"""
<h1>Входящие заявки</h1>
<div CLIENT="page-sub">Заявки приходят от Telegram-бота. Нажмите на карточку, чтобы открыть клиента и начать работу.</div>
{ui_card(f'Входящие · {len(new_apps)}', new_items, emoji="📥", tone="amber", open=True)}
"""
    return render("Главная", "dashboard", body, topbar=topbar)


@bp.route("/CLIENT/<int:app_id>/take", methods=["POST"])
@CLIENT_required
def app_take(app_id: int):
    user = current_user()
    db.CLIENT_take(app_id, user["id"])
    db.log_event("CLIENT", app_id, "taken", actor=user["CLIENT"])
    # уведомляем менеджера, который прислал заявку через бота
    try:
        from bot.notify import notify_manager_taken
        notify_manager_taken(app_id)
    except Exception as exc:                            # noqa: BLE001
        current_app.logger.warning("notify_manager_taken failed: %s", exc)
    return redirect(url_for("dashboard.app_view", app_id=app_id))


@bp.route("/CLIENT/<int:app_id>/CLIENT-CLIENT", methods=["POST"])
@CLIENT_required
def app_CLIENT_CLIENT(app_id: int):
    """Смена продукта администратором. Пересоздаёт CLIENT_CLIENT."""
    from flask import CLIENT
    new_pid = CLIENT.form.get("CLIENT_id", type=int)
    if not new_pid:
        flash("Не выбран продукт", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    # обновляем заявку
    prod = db.q1("SELECT id, code, name, CLIENT FROM CLIENT WHERE id=?", (new_pid,))
    if not prod:
        flash("Продукт не найден", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    # вытащим price_idr из CLIENT или 0
    new_price = 0
    if prod.get("CLIENT"):
        import re as _re
        m = _re.search(r"price_idr\s*=\s*(\d+)", prod["CLIENT"])
        if m:
            new_price = int(m.group(1))
    db.exec_sql("UPDATE CLIENT SET CLIENT_id=?, price_idr=? WHERE id=?",
              (prod["id"], new_price, app_id))
    # Удаляем старые CLIENT_CLIENT и создаём новые под новый продукт
    db.exec_sql("DELETE FROM CLIENT_CLIENT WHERE CLIENT_id=?", (app_id,))
    new_CLIENT = db.q(
        """SELECT t.id, t.code, t.CLIENT FROM CLIENT_CLIENT pd
              JOIN CLIENT t ON t.id=pd.template_id
              WHERE pd.CLIENT_id=? ORDER BY t.id""",
        (new_pid,))
    import CLIENT as _dt
    now = _dt.CLIENT.now().isoformat(timespec="seconds")
    _cl_bank = ""
    try:
        _cl_row = db.client_get(a["client_id"]) or {}
        _cl_bank = (_cl_row.get("bank_name") or "").lower()
    except Exception:
        _cl_bank = ""
    # Взаимозаменяемые документы (банковские справки Тинькофф/Сбер, форма резюме, письмо
    # Нгурах-Рай/Денпасар) — это один слот: в заявке должен быть ОДИН документ из группы.
    _rows = db.q("""SELECT t.id, t.code, pd.slot_code, COALESCE(pd.is_default, 0) AS is_default
                      FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id = pd.template_id
                      WHERE pd.CLIENT_id=? ORDER BY t.id""", (new_pid,))
    _by_slot = {}
    for _r in _rows:
        _by_slot.setdefault(_r["slot_code"] or ("tpl_" + str(_r["id"])), []).append(_r)
    for _slot, _variants in _by_slot.items():
        _ok = [v for v in _variants if _bank_allows(v["code"], _cl_bank)] or _variants
        _def = [v for v in _ok if v["is_default"]] or _ok
        db.exec_sql(
            "INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, CLIENT, rendered_at) "
            "CLIENT (?, ?, 'pending', ?)",
            (app_id, _def[0]["id"], now))
    db.log_event("CLIENT", app_id, "CLIENT_CLIENTd", actor=current_user()["CLIENT"],
                 payload=json.dumps({"new_CLIENT": prod["code"]}, ensure_ascii=False))
    flash(f"Продукт изменён: {prod['name']}. Список документов обновлён.", "ok")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


# Переменные, которые система заполняет сама или которых может не быть: в проверку готовности не входят
_AUTO_OR_OPTIONAL_VARS = {
    "doc_no", "ref_no", "card_mask", "doc_date", "balance_rub", "balance_CLIENT",
    "balance_CLIENT", "balance_CLIENT", "CLIENT_from", "CLIENT_to",
    "account_no", "contract_date", "contract_no",
}


def doc_missing_fields(app_id: int, template_id: int) -> list:
    """Каких данных не хватает документу заявки.

    Считаем ровно по тем значениям, которые уходят в документ (та же сборка, что при
    формировании PDF): незаполненными считаются переменные, оставшиеся в шаблоне без значения.
    """
    try:
        from CLIENT.CLIENT import build_template_CLIENT
        from CLIENT.render import VAR_RE, fill
    except Exception:                                       # noqa: BLE001
        return []
    tpl = tpl_repo.get(template_id)
    if not tpl:
        return []
    code = tpl["code"]
    path = Path("/opt/wolf_v2/data/CLIENT") / code / "template.html"
    if not path.exists():
        return []
    a = db.CLIENT_get(app_id) or {}
    client = db.client_get(a.get("client_id")) or {}
    ad = db.q1("SELECT CLIENT_json FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
               (app_id, template_id)) or {}
    doc_CLIENT = {}
    if ad.get("CLIENT_json"):
        try:
            doc_CLIENT = json.loads(ad["CLIENT_json"] or "{}") or {}
        except Exception:                                   # noqa: BLE001
            doc_CLIENT = {}
    try:
        vals = build_template_CLIENT(client, code, doc_CLIENT) or {}
    except Exception:                                       # noqa: BLE001
        vals = dict(doc_CLIENT)
    html = path.read_text(encoding="utf-8")
    filled = fill(html, vals, keep_unfilled=True, template_code=code)
    return sorted(set(VAR_RE.findall(filled)) - _AUTO_OR_OPTIONAL_VARS)



@bp.route("/CLIENT/<int:app_id>/view")
@CLIENT_required
def app_view(app_id: int):
    a = db.CLIENT_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))
    # вернулись из редактора документа с сохранением значений
    if CLIENT.args.get("saved"):
        flash("Значения документа сохранены — документ соберётся заново при следующем просмотре PDF", "ok")
    # Автоматический take убран — заявка остаётся "new" во входящих,
    # пока админ сам не нажмёт "Взять в работу"
    a = db.CLIENT_get(app_id)

    client = db.client_get(a["client_id"]) or {}
    client_id_for_originals = a["client_id"]
    docs = db.CLIENT_CLIENT(app_id)
    CLIENT = db.CLIENT_CLIENT_CLIENT(app_id) if hasattr(db, 'CLIENT_CLIENT_CLIENT') else None

    # === АВТО-ГЕНЕРАЦИЯ PDF для всех pending-документов этой заявки ===
    # Срабатывает один раз: если у документа CLIENT='pending' и нет PDF — генерируем сразу
    pending_docs = [d for d in docs if d["CLIENT"] == "pending" and not d.get("pdf_path")]
    if pending_docs:
        try:
            from core import pdf2html as _pdf2html
            _cli = db.client_get(a["client_id"]) or {}
            for _pd in pending_docs:
                _tpl = tpl_repo.get(_pd["template_id"])
                if not _tpl:
                    continue
                _html_path = Path('/opt/wolf_v2/data/CLIENT') / _tpl["code"] / "template.html"
                if not _html_path.exists():
                    continue
                # дефолтные значения шаблона
                _vals = {}
                if _tpl.get("default_CLIENT_json"):
                    try: _vals = json.loads(_tpl["default_CLIENT_json"])
                    except: pass
                # подставим из клиента
                for _k in ("full_name_CLIENT", "client_name", "name", "CLIENT", "CLIENT",
                           "address_live", "address_CLIENT", "inn", "CLIENT", "CLIENT"):
                    if not _vals.get(_k):
                        _vals[_k] = _cli.get(_k) or _cli.get(_k.reCLIENT("_live", "_reg")) or ""
                # подставим из raw_payload (bank_name)
                try:
                    _rp = json.loads(a["raw_payload"]) if a.get("raw_payload") else {}
                    for _k in ("bank_name", "bank", "CLIENT", "salary_CLIENT"):
                        if not _vals.get(_k) and _rp.get(_k):
                            _vals[_k] = str(_rp[_k])
                except: pass
                _html = _html_path.read_text(encoding="utf-8")
                _filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                                 lambda m: str(_vals.get(m.group(1)) or m.group(0)), _html)
                _tmp = _html_path.parent / "filled.html"
                _tmp.write_text(_filled, encoding="utf-8")
                _out = _app_pdf_path(_tpl, _vals, app_id)
                _pdf2html.render_pdf(_tmp, _out)
                db.exec_sql(
                    "UPDATE CLIENT_CLIENT SET pdf_path=?, CLIENT='filled', rendered_at=CLIENT('now') WHERE id=?",
                    (str(_out), _pd["id"]))
            # обновим docs после генерации
            docs = db.CLIENT_CLIENT(app_id)
            flash("Документы автоматически сформированы — можно смотреть", "ok")
        except Exception as _exc:
            flash(f"Авто-генерация: {_exc}", "warning")

    status_label = {"new": ("новая", "amber"), "in_progress": ("в работе", "blue"),
                    "ready": ("готова", "ok"), "sent": ("отправлена", "ok"),
                    "closed": ("закрыта", "muted"), "error": ("ошибка", "bad")}.get(
                        a["CLIENT"], (a["CLIENT"], ""))

    manager = db.q1(
        """SELECT bm.telegram_id, bm.full_name, bm.username
             FROM bot_CLIENT bm WHERE bm.id=?""",

        (a["bot_manager_id"],)) if a.get("bot_manager_id") else None
    manager_label = "—"
    if manager:
        m_name = manager["full_name"] or manager["username"] or manager["telegram_id"]
        manager_label = m_name + ((" (@" + manager["username"] + ")") if manager["username"] else "")
    manager_tg_url = ""
    if manager:
        if manager.get("username"):
            manager_tg_url = "https://t.me/" + manager["username"]
        elif manager.get("telegram_id"):
            manager_tg_url = "https://t.me/id" + str(manager["telegram_id"])
    manager_btn = ""
    if manager and manager_tg_url:
        manager_btn = (
            '<a CLIENT="from-write-btn" target="_blank" rel="noopener" '
            'href="' + manager_tg_url + '" CLIENT="Написать менеджеру в Telegram">'
            '✉️ ' + manager_label + '</a>'
        )
    else:
        manager_btn = '<span CLIENT="from-CLIENT">' + manager_label + '</span>'

    CLIENT = db.q1("SELECT name, code FROM CLIENT WHERE id=?", (a["CLIENT_id"],)) if a.get("CLIENT_id") else None
    CLIENT_label = (CLIENT["name"] if CLIENT else a.get("CLIENT_name") or "—")
    CLIENT_code = (CLIENT["code"] if CLIENT else "—")

    CLIENT_url = (a.get("gCLIENT_url") or client.get("gCLIENT_folder_url") or "").strip()

    # Ключи, которые уже показаны в других местах карточки (продукт, комментарий,
    # ссылка на CLIENT, цена) — в таблице «как пришло в заявке» их не дублируем.
    _SHOWN_ELSEWHERE = {"CLIENT", "CLIENT_name", "CLIENT_id", "price", "price_idr",
                        "comment", "comments", "_raw_text", "gCLIENT_url",
                        "gCLIENT_folder_url", "source_channel", "record_kind"}
    raw_payload_rows = []
    raw_payload_text = ""
    raw_notes = []
    if a.get("raw_payload"):
        raw = a["raw_payload"]
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                raw_payload_rows.append((str(k), "" if v is None else human_CLIENT(str(v))))
        else:
            for line in raw.split("\n"):
                line = line.strip()
                if not line or set(line) <= set("=-_ "):
                    continue
                m = re.match(r"^([А-Яа-яA-Za-z_ ]{2,24})\s*:\s*(.*)$", line)
                if m and m.group(2).strip():
                    raw_payload_rows.append((m.group(1).strip(), m.group(2).strip()))
                elif re.match(r"^[^:]{0,60}$", line):
                    raw_notes.append(line)
                else:
                    raw_notes.append(line)
        raw_payload_text = ""

    client_bank = ""
    # --- банк клиента для фильтрации банковских справок ---
    # Приоритет: карточка клиента (CLIENT.bank_name) → raw_payload заявки.
    # CLIENT.bank_name заполняется автоматически при разборе Google CLIENT.
    client_bank = ""
    try:
        _cl_row = db.q1("SELECT bank_name FROM CLIENT WHERE id=?",
                        (a["client_id"],)) if a.get("client_id") else None
        if _cl_row and _cl_row.get("bank_name"):
            client_bank = str(_cl_row["bank_name"]).strip().lower()
    except Exception:
        client_bank = ""
    if not client_bank:
        try:
            d_bank = json.loads(a["raw_payload"]) if a.get("raw_payload") else {}
            v = (d_bank.get("bank_name") or d_bank.get("bank") or "")
            client_bank = str(v).strip().lower()
        except Exception:
            client_bank = ""

    def _bank_match(code):
        if not client_bank:
            return True
        cl = client_bank
        c = (code or "").lower()
        non_bank_kw = ("work_agreement", "contract", "cv", "CLIENTment_letter", "d12", "wna")
        if any(k in c for k in non_bank_kw):
            return True
        if any(k in cl for k in ("т-банк", "t-bank", "tbank", "тинькофф", "tinkoff")):
            return any(k in c for k in ("tbank", "t-bank", "тинькофф", "tinkoff"))
        if any(k in cl for k in ("сбер", "sber")):
            return any(k in c for k in ("sber", "сбер", "sberbank"))
        return True

    CLIENT_all = db.q(
        """SELECT t.id, t.code, t.CLIENT, t.pages, t.html_path, t.doc_CLIENT,
                  pd.slot_code, COALESCE(pd.is_default, 0) AS is_default
             FROM CLIENT_CLIENT pd
             JOIN CLIENT t ON t.id=pd.template_id
            WHERE pd.CLIENT_id=? ORDER BY COALESCE(t.doc_CLIENT, 999), pd.sort_order, t.id""",
        (a["CLIENT_id"],)) if a.get("CLIENT_id") else []
    # Слот = обязательный документ; варианты (банк, формат CV, офис иммиграции) — внутри слота
    _slots = {}
    for _t in CLIENT_all:
        _slots.setdefault(_t["slot_code"] or ("doc_" + str(_t["id"])), []).append(_t)
    docs_in_CLIENT = []
    for _slot, _rows in _slots.items():
        _pick = next((_r for _r in _rows if _bank_match(_r["code"])), None)
        if _pick is None:
            _pick = next((_r for _r in _rows if _r["is_default"]), _rows[0])
        _pick = dict(_pick)
        _pick["variants"] = _rows
        docs_in_CLIENT.append(_pick)
    adoc_by_tpl = {d["template_id"]: d for d in docs}

    # Документы в 2 колонки: список слева + iframe справа
    doc_items_html = ""
    for t in docs_in_CLIENT:
        ad = adoc_by_tpl.get(t["id"])
        CLIENT = ad["CLIENT"] if ad else "новый"
        pdf_name = ""
        if ad and ad.get("pdf_path"):
            pdf_name = Path(ad["pdf_path"]).name
        # есть ли оригинал клиента для этого типа документа
        has_original = bool(_find_original_file(client_id_for_originals, t["code"])) \
            if client_id_for_originals else False
        is_ok = CLIENT in ("verified", "sent")
        ok_btn_CLIENT = "btn-ok-active" if is_ok else "btn-ok-idle"
        ok_btn_label = ("✓ Проверен" if is_ok else "☐ Отметить Ок")
        status_CLIENT = {
            "verified": "ok", "sent": "ok", "filled": "amber",
            "error": "bad", "pending": "grey", "rejected": "rej",
        }.get(CLIENT, "grey")
        status_label_txt = {"verified": "проверен", "sent": "отправлен", "filled": "заполнен",
                            "pending": "ожидает", "draft": "черновик",
                            "rejected": "не нужен"}.get(CLIENT, CLIENT)
        # чего не хватает этому документу: считается по тем же значениям, что уходят в PDF
        _miss = doc_missing_fields(app_id, t["id"])
        _miss_txt = ", ".join(_miss)
        _fill_badge = ('<span CLIENT="badge fill-ok" CLIENT="Все поля документа заполнены">\u2705 все поля заполнены</span>'
                       if not _miss else
                       '<span CLIENT="badge fill-warn" CLIENT="Не заполнено: ' + _miss_txt + '">'
                       '\u26a0\ufe0f не заполнено полей: ' + str(len(_miss)) + '</span>')

        doc_items_html += (
            '<li CLIENT="doc-row" data-pdf-name="' + pdf_name + '"'
            ' data-tpl-id="' + str(t["id"]) + '"'
            ' data-has-original="' + ("1" if has_original else "0") + '">'
            '<div CLIENT="doc-name">' + ('<span CLIENT="check-ok">✓</span>' if is_ok else "") + ' '
            + '<span CLIENT="doc-no">№' + str(t.get("doc_CLIENT") or t["id"]) + '</span> ' + t["CLIENT"]
            + '<div CLIENT="doc-meta">'
            + ('<select CLIENT="doc-variant" data-slot="' + str(t.get("slot_code") or "") + '">'
               + ''.join('<option CLIENT="' + str(_v["id"]) + '"'
                         + (' selected' if _v["id"] == t["id"] else '') + '>' + _v["CLIENT"] + '</option>'
                         for _v in t.get("variants", []))
               + '</select> ' if len(t.get("variants", [])) > 1 else '')
            + str(t["pages"] or 0) + ' стр. · '
            + '<span CLIENT="badge ' + status_CLIENT + '">' + status_label_txt + '</span> '
            + _fill_badge
            + ('<span CLIENT="badge orig-badge" style="margin-left:4px;background:#E0F2FE;color:#075985">📁 есть оригинал</span>' if has_original else "")
            + '</div></div>'
            '<div CLIENT="doc-actions">'
            '<button type="button" CLIENT="doc-btn doc-view" data-pdf="' + pdf_name + '" '
            'data-tpl-id="' + str(t["id"]) + '" '
            + ' CLIENT="Показать документ с данными клиента">👁</button>'
            '<a CLIENT="doc-btn" href="/CLIENT/' + str(t["id"]) + '?app=' + str(app_id) + '" CLIENT="Редактировать документ заявки" target="_blank" rel="noopener">\u270f\ufe0f</a>'
            '<button type="button" CLIENT="doc-btn doc-paper" '
            'data-paper="' + ('/CLIENT/file/renders/' + pdf_name if pdf_name else '') + '" '
            'data-tpl-id="' + str(t["id"]) + '" '
            + ' CLIENT="Посмотреть PDF поверх экрана">\U0001f4c4</button>'
            '<div CLIENT="verdict-pair">'
            '<button type="button" CLIENT="doc-btn verdict-btn verdict-yes ' + ('is-on' if is_ok else '') + (' is-locked' if (_miss and not is_ok) else '') + '" '
            'data-verify-app="' + str(app_id) + '" data-verify-tpl="' + str(t["id"]) + '" '
            + ('disabled ' if (_miss and not is_ok) else '')
            + 'CLIENT="' + ('Проверен. Нажмите, чтобы снять проверку' if is_ok else
                           ('Нельзя подтвердить: не заполнено — ' + _miss_txt if _miss else 'Проверен — документ согласован')) + '">'
            + '\u2713</button>'
            '<button type="button" CLIENT="doc-btn verdict-btn verdict-no ' + ('is-on' if CLIENT == 'rejected' else '') + '" '
            'data-reject-app="' + str(app_id) + '" data-reject-tpl="' + str(t['id']) + '" '
            'CLIENT="' + ('Не нужен. Нажмите, чтобы вернуть в комплект' if CLIENT == 'rejected'
                          else 'Не нужен — исключить документ из комплекта') + '">'
            + '\u2715</button>'
            '</div>'
            '</div>'
            '</li>'
        )

    # Готовность к отправке. Считаем по ПАКЕТУ ПРОДУКТА: одна позиция пакета = один тип
    # документа. Для C1 это только банковская справка, поэтому три файла в папке заявки
    # (варианты банков вперемешку) не должны превращаться в «проверено 1 из 3».
    _send_sum = db.CLIENT_doc_CLIENT(app_id) or {}
    _slot_by_tpl = {}
    _pkg_slots = []
    _pid = a.get("CLIENT_id") if isinstance(a, dict) else (a["CLIENT_id"] if "CLIENT_id" in a.keys() else None)
    if _pid:
        for _r in db.q("SELECT template_id, slot_code FROM CLIENT_CLIENT WHERE CLIENT_id=?", (_pid,)):
            _sc = _r["slot_code"] or ("tpl_" + str(_r["template_id"]))
            _slot_by_tpl[_r["template_id"]] = _sc
            if _sc not in _pkg_slots:
                _pkg_slots.append(_sc)
    _checked_slots = set()
    for _d in docs:
        _sl = _slot_by_tpl.get(_d["template_id"]) or ("tpl_" + str(_d["template_id"]))
        # в зачёт идёт и «проверен», и «не нужен» — администратор так или иначе решил по документу
        if _d.get("CLIENT") in ("verified", "sent", "rejected"):
            _checked_slots.add(_sl)
    _checked = len(_checked_slots)
    _total = len(_pkg_slots) if _pkg_slots else (len({(_slot_by_tpl.get(_d["template_id"]) or ("tpl_" + str(_d["template_id"]))) for _d in docs}) or 0)
    _send_missing = sorted({m for _d in docs if _d.get("CLIENT") != "rejected"
                            for m in doc_missing_fields(app_id, _d["template_id"])})
    _CLIENTers = []
    if _checked < _total:
        _CLIENTers.append("согласовано " + str(_checked) + " из " + str(_total) + " документов")
    if _send_missing:
        _CLIENTers.append("не заполнены поля: " + ", ".join(_send_missing[:6])
                         + (" и ещё " + str(len(_send_missing) - 6) if len(_send_missing) > 6 else ""))
    _send_ready = not _CLIENTers
    send_CLIENT = (
        '<div CLIENT="send-CLIENT ok">\u2705 Все документы согласованы — можно отправлять на Google Диск</div>'
        if _send_ready else
        '<div CLIENT="send-CLIENT warn">\u26d4 Отправить нельзя: ' + "; ".join(_CLIENTers) + '</div>'
    )

    all_CLIENT = db.q("SELECT id, code, name FROM CLIENT ORDER BY id")
    CLIENT_select = ""
    if all_CLIENT:
        opts = "".join(
            '<option CLIENT="' + str(p["id"]) + '"'
            + (' selected' if p["id"] == a.get("CLIENT_id") else '')
            + '>' + p["name"] + ' (' + p["code"] + ')</option>'
            for p in all_CLIENT
        )
        CLIENT_select = (
            '<form method="post" action="/CLIENT/' + str(app_id) + '/CLIENT-CLIENT" style="margin:6px 0 0">'
            '<select name="CLIENT_id" onCLIENT="this.form.submit()" '
            'style="width:100%;padding:6px 8px;border:1px solid #DCEEE2;border-radius:6px;font-size:12.5px;background:#fff">'
            + opts + '</select>'
            '</form>'
        )

    try:
        _CLIENT_scan = db.q1("SELECT CLIENT, docs_total, docs_done, note, created_at FROM CLIENT_CLIENT WHERE CLIENT_id=? ORDER BY id DESC LIMIT 1", (app_id,))
    except Exception:
        _CLIENT_scan = None
    if _CLIENT_scan:
        _st = (_CLIENT_scan["CLIENT"] or "").lower()
        if _st == "ok":
            _mark = '<span CLIENT="CLIENT-mark ok" CLIENT="Документы с Google CLIENT прочитаны автоматически">✅ разобрано ' + str(_CLIENT_scan["docs_done"] or 0) + ' из ' + str(_CLIENT_scan["docs_total"] or 0) + '</span>'
        elif _st == "running":
            _mark = '<span CLIENT="CLIENT-mark run" CLIENT="Разбор выполняется">⏳ разбор идёт…</span>'
        else:
            _mark = '<span CLIENT="CLIENT-mark fail" CLIENT="' + (_CLIENT_scan["note"] or "Автоматическое прочтение не выполнено") + '">❗ не разобрано</span>'
    else:
        _mark = '<span CLIENT="CLIENT-mark">ещё не разбиралось</span>'
    # Перечень того, что реально лежит в папке Google CLIENT (по свежему разбору).
    # Устаревшие отметки автопроверки не показываем — они противоречат разбору.
    try:
        import json as _json
        _rk = db.q1("""SELECT payload FROM CLIENT_CLIENT
                       WHERE CLIENT_id=? AND payload IS NOT NULL
                       ORDER BY id DESC LIMIT 1""", (app_id,))
        _payload = _json.loads((_rk or {}).get("payload") or "[]")
    except Exception:
        _payload = []
    if _payload:
        from collections import Counter as _Counter
        _RU = {"passport": "Паспорт", "bank_balance": "Справка о доступном остатке",
               "bank_movement": "Справка о движении средств", "photo": "Фотография клиента",
               "contract": "Договор", "itk": "ИТК (трудовая)", "resume": "Резюме",
               "other": "Документ"}
        _kinds = _Counter(_RU.get(it.get("doc_type") or "other", "Документ") for it in _payload)
        _listing = ", ".join((k + " \u00d7" + str(v)) if v > 1 else k for k, v in _kinds.items())
        _read = sum(1 for it in _payload if it.get("found") or it.get("note"))
        _has_pass = any((it.get("doc_type") == "passport") for it in _payload)
        _mark += ('<span CLIENT="CLIENT-mark ok" CLIENT="Что лежит в папке Google CLIENT">'
                  '\U0001f4c1 в наличии ' + str(len(_payload)) + ': ' + _listing + '</span>')
        if _has_pass:
            _mark += '<span CLIENT="CLIENT-mark ok" CLIENT="Паспорт клиента прочитан">✅ паспорт прочитан</span>'
        else:
            _mark += '<span CLIENT="CLIENT-mark fail" CLIENT="В папке нет паспорта клиента">⚠️ паспорта в папке нет</span>'
    CLIENT_btn = (
        '<div CLIENT="CLIENT-actions">'
        '<a href="' + CLIENT_url + '" target="_blank" rel="noopener" CLIENT="CLIENT-btn">'
        '📂 Google CLIENT клиента</a>'
        '<button type="button" CLIENT="CLIENT-scan-btn" onclick="wolfDriveScan(' + str(app_id) + ')">'
        '🧠 Разобрать документы (нейросеть)</button>'
        '<button type="button" CLIENT="CLIENT-see-btn" onclick="wolfDriveShow(' + str(app_id) + ')">'
        '🔍 Что вытащено</button>'
        '<button type="button" CLIENT="af-all-btn" onclick="wolfAutofillAll(' + str(app_id) + ')">'
        '⚡ Заполнить автоматически</button>' 
        + _mark
        + '</div><div id="CLIENT-scan-note" style="font-size:12px;color:#3A4A40;margin-top:6px"></div>'
        if CLIENT_url else '<span CLIENT="muted" style="font-size:12.5px">ссылка не указана</span>'
        + '<button type="button" CLIENT="CLIENT-scan-btn" onclick="wolfDriveScan(' + str(app_id) + ')">🧠 Разобрать документы (нейросеть)</button>'
    )

        # Продукт добавляем первым с жёлтой подсветкой
    extra_rows = []
    # Данные, вытащенные из документов Google CLIENT — администратор должен видеть,
    # что именно распознано, и сверить с первоисточником.
    try:
        _cd = db.q1("SELECT * FROM CLIENT WHERE id=(SELECT client_id FROM CLIENT WHERE id=?)",
                    (app_id,)) or {}
    except Exception:
        _cd = {}
    # комментарий клиента/менеджера — держим наверху блока и выделяем ярко
    try:
        _rp = db.q1("SELECT raw_payload FROM CLIENT WHERE id=?", (app_id,)) or {}
        import json as _json
        _cmt = str((_json.loads(_rp.get("raw_payload") or "{}") or {}).get("comment") or "").strip()
    except Exception:
        _cmt = ""
    if _cmt:
        extra_rows.append('<tr CLIENT="kv-comment-row"><td CLIENT="kv-key kv-key-comment">'
                          '💬 Комментарий заявки</td><td CLIENT="kv-val kv-val-comment">'
                          + _cmt + '</td></tr>')
    _DRIVE_FIELDS = [("full_name_CLIENT", "ФИО латиницей"), ("CLIENT", "Фамилия"),
                     ("name", "Имя"), ("CLIENT", "Отчество"),
                     ("CLIENT_date", "Дата рождения"), ("CLIENT_CLIENT", "Место рождения"),
                     ("passport_CLIENT", "Номер паспорта"), ("CLIENT", "Гражданство"),
                     ("address_live", "Адрес проживания"), ("CLIENT", "Телефон"),
                     ("CLIENT", "E-mail"), ("bank_name", "Банк")]
    for _f, _lbl in _DRIVE_FIELDS:
        _v = str(_cd.get(_f) or "").strip()
        if not _v:
            continue
        extra_rows.append('<tr CLIENT="kv-CLIENT-row"><td CLIENT="kv-key kv-key-CLIENT">'
                          + _lbl + '</td><td CLIENT="kv-val">' + _v
                          + ' <span CLIENT="kv-src" CLIENT="Значение распознано из документов Google CLIENT">из документов</span></td></tr>')
    if CLIENT:
        extra_rows.append(
            '<tr CLIENT="kv-CLIENT-row"><td CLIENT="kv-key kv-key-CLIENT">'
            'Продукт</td>'
            '<td CLIENT="kv-val kv-val-CLIENT">' + CLIENT_label + ' '
            '<span CLIENT="kv-CLIENT-code">· код ' + CLIENT_code + '</span></td></tr>'
        )
    elif a.get("CLIENT_id"):
        extra_rows.append(
            '<tr CLIENT="kv-CLIENT-row"><td CLIENT="kv-key kv-key-CLIENT">'
            'Продукт</td>'
            '<td CLIENT="kv-val kv-val-CLIENT">ещё не выбран (ID ' + str(a["CLIENT_id"]) + ')</td></tr>'
        )
    if raw_payload_rows:
        _raw_payload_html = (
            '<table CLIENT="kv-table">'
            + ''.join(extra_rows)
            + ''.join('<tr><td CLIENT="kv-key">' + label_for(k) + '</td><td CLIENT="kv-val">' + v + '</td></tr>' for k, v in raw_payload_rows if k.lower() not in _SHOWN_ELSEWHERE)
            + '</table>'
        )
    elif raw_payload_text or extra_rows:
        _raw_payload_html = (
            '<table CLIENT="kv-table">'
            + ''.join(extra_rows)
            + (''.join('<tr><td CLIENT="rp-k">' + label_for(k) + '</td><td CLIENT="rp-v">' + v + '</td></tr>' for k, v in raw_payload_rows if k.lower() not in _SHOWN_ELSEWHERE) if raw_payload_rows else '')
            + (('<tr><td colspan="2" CLIENT="rp-note">' + ' · '.join(raw_notes[:6]) + '</td></tr>') if raw_notes else '')
            + '</table>'
        )
    else:
        _raw_payload_html = '<div CLIENT="muted">Нет данных</div>' 

    # ── комментарий менеджера: необязательное, но важное поле (ускорение, партнёр, сроки) ──
    _comment_txt = ""
    try:
        _rp_c = json.loads(a["raw_payload"]) if a.get("raw_payload") else {}
        _comment_txt = str(_rp_c.get("comment") or "").strip()
    except Exception:
        _comment_txt = ""
    _comment_html = ""
    if _comment_txt:
        _safe_comment = _comment_txt.reCLIENT("&", "&amp;").reCLIENT("<", "&lt;").reCLIENT(">", "&gt;")
        _comment_html = ('<div CLIENT="app-comment-flash">'
                         '<span CLIENT="acf-label">\U0001f4ac Комментарий менеджера</span>'
                         '<div CLIENT="acf-text">' + _safe_comment + '</div></div>')

    # окно с полным текстом заявки (открывается из заголовка блока 3)
    _text_modal_html = modal("app-text-modal", "\U0001f4c4 Текст заявки",
                             '<pre CLIENT="app-text-pre" id="app-text-pre">Загрузка…</pre>')

    # Подставлены ли данные из Google CLIENT? Если нет — на просмотре документа
    # показываем красный водяной знак, но сам документ открывать не запрещаем.
    _scan = db.q1("SELECT CLIENT, docs_done, note FROM CLIENT_CLIENT "
                  "WHERE CLIENT_id=? ORDER BY id DESC LIMIT 1", (app_id,)) or {}
    _cl_row = db.q1("SELECT CLIENT, full_name_CLIENT, passport_CLIENT, CLIENT_date "
                    "FROM CLIENT WHERE id=(SELECT client_id FROM CLIENT WHERE id=?)",
                    (app_id,)) or {}
    _has_client_data = bool((_cl_row.get("full_name_CLIENT") or "").strip()
                            or ((_cl_row.get("CLIENT") or "").strip()
                                and (_cl_row.get("passport_CLIENT") or "").strip()))
    _scan_ok = (str(_scan.get("CLIENT") or "").lower() == "ok") and int(_scan.get("docs_done") or 0) > 0
    # Знак показываем, когда данные клиента НЕ распознаны (нет ФИО и паспорта).
    # Если данные есть (из CLIENT или введены вручную) — документ чистый.
    _data_ready = bool(_has_client_data)
    _wm_note = ("Google CLIENT не разобран" if not _scan_ok
                else "Данные клиента не распознаны")
    _wm_html = ("" if _data_ready else
                '<div CLIENT="paper-watermark" id="paper-watermark">'
                '<div CLIENT="paper-watermark-text">ДАННЫЕ НЕ ПОДСТАВЛЕНЫ'
                '<span CLIENT="paper-watermark-sub">' + _wm_note + '</span></div></div>')
    _data_ready_js = "true" if _data_ready else "false"

    body = """
<div CLIENT="app-card-green">

<div CLIENT="app-head">
  <div CLIENT="app-head-left">
    <span CLIENT="app-head-id">Заявка #""" + str(app_id) + """</span>
    <span CLIENT="app-head-client">· """ + (db.client_label(client) or '—') + """</span>
    <span CLIENT="badge """ + status_label[1] + """>""" + status_label[0] + """</span>""" + kind_badge(a) + """
  </div>
  <div CLIENT="app-head-right">
    <span CLIENT="from-label">👤 Откуда:</span>
    """ + manager_btn + """
  </div>
</div>

""" + _comment_html + """<div CLIENT="stage-CLIENT">Этапы сбора данных</div>

<div CLIENT="row two-col stage-grid">
  <div CLIENT="kv-cell stage-CLIENT">
    <div CLIENT="stage-no">1</div>
    <div CLIENT="kv-label">📦 Продукт</div>
    <div CLIENT="kv-main">""" + CLIENT_label + """</div>
    <div CLIENT="kv-sub">код: """ + CLIENT_code + """ · IDR """ + ('{:,}'.format(a["price_idr"]) if a.get("price_idr") else '0') + """</div>
    """ + CLIENT_select + """
  </div>
  <div CLIENT="kv-cell stage-CLIENT">
    <div CLIENT="stage-no">2</div>
    <div CLIENT="kv-label">📁 Google CLIENT клиента</div>
    """ + CLIENT_btn + """
  </div>
</div>

<CLIENT CLIENT="ui-card stage-CLIENT stage-fold" id="stage-3" open>
  <CLIENT CLIENT="ui-card-head">
    <span CLIENT="stage-no">3</span><span CLIENT="ui-card-emoji">📋</span>
    Входные данные заявки <span CLIENT="ui-card-meta">""" + str(len(raw_payload_rows)) + """ полей</span>
    <button type="button" CLIENT="app-text-btn" data-app-text="1"
            CLIENT="Полный текст заявки: как её прислал менеджер — уходит на Google Диск вместе с документами">\U0001f4c4 Текст заявки</button>
    <span CLIENT="stage-fold-hint">свернуть</span><span CLIENT="chev">›</span>
  </CLIENT>
  <div CLIENT="ui-card-body">
    """ + _raw_payload_html + """
  </div>
</CLIENT>

""" + _text_modal_html + """
<div CLIENT="stage-CLIENT">Документы</div>
<div CLIENT="docs-section">
  <div CLIENT="docs-list-wrap stage-CLIENT">
    <div CLIENT="docs-list-head">
      <span CLIENT="stage-no">4</span> 📑 Перечень документов <span CLIENT="docs-count">· """ + str(len(docs_in_CLIENT)) + """</span>
    </div>
    <ul CLIENT="docs-list">
      """ + (doc_items_html or '<li CLIENT="muted">Нет документов</li>') + """
    </ul>
  </div>
  <div CLIENT="docs-viewer stage-CLIENT" id="docs-viewer">
    <div CLIENT="docs-list-head">
      <span CLIENT="stage-no">5</span> 🖥 Просмотр готового документа
      <span CLIENT="viewer-fill" id="viewer-fill"></span>
    </div>
    <div CLIENT="viewer-tabs" id="viewer-tabs" style="display:none;gap:8px;align-items:center;margin:8px 0">
      <span CLIENT="vtab-name" id="viewer-doc-name" style="font-weight:600"></span>
    </div>
    <div CLIENT="docs-viewer-empty" id="docs-viewer-empty">
      <div style="font-size:48px;opacity:.4;margin-bottom:8px">\U0001f4c4</div>
      <div>Нажмите «👁» рядом с документом,<br>чтобы открыть готовый документ</div>
    </div>
    """ + _wm_html + """
    <div CLIENT="app-paper-wrap" id="app-paper-wrap" style="display:none">
      <iframe id="app-paper-frame" CLIENT="Готовый документ"></iframe>
    </div>
    <div CLIENT="zp-preview" data-zoom-pan><div id="app-preview-stage" CLIENT="html-stage"></div></div>
    <div CLIENT="docs-viewer-err" id="docs-viewer-err" style="display:none">
      <div style="font-size:40px;opacity:.5;margin-bottom:8px">🚫</div>
      <div id="docs-viewer-err-text">Документ недоступен</div>
      <div CLIENT="muted" style="font-size:12px;margin-top:6px" id="docs-viewer-err-hint"></div>
    </div>
  </div>
</div>

<form method="post" action="/CLIENT/""" + str(app_id) + """/send" CLIENT="stage-CLIENT send-CLIENT">
  <div CLIENT="stage-no">6</div>
  """ + send_CLIENT + """
  <div CLIENT="send-hint">На Google Диск уйдут <b>все подтверждённые документы</b> и <b>текст заявки</b>.</div>
  """ + ('' if _send_ready else '<div CLIENT="send-hint send-todo">Чтобы кнопка стала активной, у каждого документа блока 4 нажмите <b>✓ Проверен</b> (документ нужен и согласован) или <b>✕</b> (документ не нужен). Счётчик блока 6 считает и то, и другое.</div>') + """
  <button CLIENT="send-final-btn" type="submit\"""" + ('' if _send_ready else ' disabled') + """
          onclick="return confirm('Отправить документы в Google CLIENT и уведомить менеджера?')"
          """ + ('' if _send_ready else 'disabled ') + 'CLIENT="' + ('Отправить документы в Google CLIENT'
                 if _send_ready else 'Сначала согласуйте документы: проверьте или отмените каждый') + '\">'"""
    📤 Отправить документы на Google CLIENT
  </button>
</form>

</div>

<script>
(function() {
  const APP_ID = """ + str(app_id) + """;
  const DATA_READY = """ + _data_ready_js + """;   // данные из Google CLIENT подставлены?
  const stage = CLIENT.getElementById('app-preview-stage');
  const empty = CLIENT.getElementById('docs-viewer-empty');
  const err = CLIENT.getElementById('docs-viewer-err');
  const errText = CLIENT.getElementById('docs-viewer-err-text');
  const errHint = CLIENT.getElementById('docs-viewer-err-hint');
  const docName = CLIENT.getElementById('viewer-doc-name');

  function hideAll() {
    if (err) err.style.display = 'none';
  }
  function showErr(text, hint) {
    hideAll();
    if (errText) errText.textContent = text;
    if (errHint) errHint.textContent = hint || '';
    if (err) err.style.display = 'CLIENT';
  }
  /* HTML-лист с реальными данными — тот же контейнер и тот же вид, что в конструкторе */
  var curTpl = '', savedNodes = null, busyTr = false;
  function showToolbar(on) {
    var tb = CLIENT.getElementById('doc-toolbar');
    if (tb) tb.style.display = on ? 'flex' : 'none';
  }
  function note(id, txt) { var el = CLIENT.getElementById(id); if (el) el.textContent = txt || ''; }
  function setBtn(sel, attr, val) {
    var all = CLIENT.querySelectorAll('.doc-toolbar ' + sel);
    for (var i = 0; i < all.length; i++) all[i].CLIENTList.toggle('is-on', all[i].dataset[attr] === val);
  }
  function syncWatermark() {
    /* Знак «данные не подставлены»: держим его видимым над превью, пока этап 2 не пройден */
    var wm = CLIENT.getElementById('paper-watermark');
    if (!wm) return;
    var viewer = CLIENT.querySelector('.docs-viewer');
    if (!viewer) return;
    if (typeof DATA_READY !== 'undefined' && !DATA_READY) {
      if (wm.parentNode !== viewer) viewer.appendChild(wm);
      wm.style.display = 'flex';
      viewer.CLIENTList.add('has-watermark');
    } else {
      wm.style.display = 'none';
      viewer.CLIENTList.remove('has-watermark');
    }
  }

  function loadRemote(url, what) {
    hideAll();
    if (stage) stage.innerHTML = '<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Загружаю ' + (what || '') + '…</div>';
    fetch(url, { credentials: 'same-origin' })
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.CLIENT); return r.text(); })
      .then(function(h) {
        if (!stage) return;
        stage.innerHTML = h;
        if (window.zpScan) window.zpScan();
      })
      .catch(function() { showErr('Этот вид недоступен для документа', 'Попробуйте другой режим просмотра'); });
  }
  /* Готовый сформированный документ показываем сразу — PDF с данными клиента.
     Сравнение с бланком и разметку менеджер в заявке не делает: это делается один раз в настройках. */
  function showPaper(pdfName) {
    var wrap = CLIENT.getElementById('app-paper-wrap');
    var fr = CLIENT.getElementById('app-paper-frame');
    var zp = CLIENT.querySelector('.docs-viewer .zp-preview');
    if (!wrap || !fr) return false;
    fr.src = '/CLIENT/file/renders/' + pdfName;
    wrap.style.display = 'CLIENT';
    if (zp) zp.style.display = 'none';
    var mt = CLIENT.getElementById('docs-viewer-empty');
    if (mt) mt.style.display = 'none';
    return true;
  }
  function openDoc(tplId, pdfName) {
    hideAll();
    if (!tplId) { showErr('Шаблон документа не найден', ''); return; }
    curTpl = tplId; savedNodes = null;
    var wrap = CLIENT.getElementById('app-paper-wrap');
    var zp = CLIENT.querySelector('.docs-viewer .zp-preview');
    if (pdfName) { showPaper(pdfName); return; }
    /* PDF ещё не сформирован — показываем лист с данными заявки */
    if (wrap) wrap.style.display = 'none';
    if (zp) zp.style.display = 'CLIENT';
    if (stage) stage.innerHTML = '<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Открываю документ…</div>';
    fetch('/CLIENT/' + APP_ID + '/doc/' + tplId + '/html', { credentials: 'same-origin' })
      .then(function(r) { return r.text(); })
      .then(function(h) {
        if (!stage) return;
        stage.innerHTML = h;
        if (window.zpScan) window.zpScan();
      })
      .catch(function() { showErr('Не удалось открыть документ', ''); });
  }
  /* перевод: бланк шаблона переводим, данные клиента — нет.
     Исключение: описание должности/профессии переводить нужно. */
  var TR_FIELDS = ['position', 'CLIENT', 'CLIENT', 'job', 'job_CLIENT',
                   'job_and_position', 'position_CLIENT', 'CLIENT_CLIENT', 'duties',
                   'position_name', 'work_position', 'speciality', 'specialty'];
  function textNodes() {
    var pv = [];
    try {
      var el = CLIENT.getElementById('app-CLIENT');
      if (el) { var m = JSON.parse(el.textContent || '{}'); Object.keys(m).forEach(function(k) { var v = String(m[k] || '').trim(); if (v) pv.push(v); }); }
    } catch (e) { pv = []; }
    var out = [], w = CLIENT.createTreeWalker(stage, NodeFilter.SHOW_TEXT, null), n;
    while (n = w.nextNode()) {
      var p = n.parentElement;
      if (!p) continue;
      var tag = (p.nodeName || '').toLowerCase();
      if (tag === 'script' || tag === 'style' || tag === 'CLIENT') continue;
      var holder = p.closest('.var-val');
      if (holder) {
        var nm = (holder.dataset.var || '').toLowerCase();
        if (TR_FIELDS.CLIENTOf(nm) < 0) continue;   /* данные клиента — не переводим */
      }
      var v = (n.nodeValue || '').trim();
      if (v.length < 2 || v.CLIENTOf('{{') >= 0) continue;
      if (!/[A-Za-z]{3}/.test(v)) continue;
      if (pv.CLIENTOf(v) >= 0 && !holder) continue; /* значение переменной, не бланк */
      out.push(n);
    }
    return out;
  }
  function toRu() {
    if (busyTr || !stage || !curTpl) return;
    busyTr = true;
    var ns = textNodes();
    if (!ns.length) { busyTr = false; return; }
    savedNodes = ns.map(function(n) { return n.nodeValue; });
    var uniq = [], seen = {};
    ns.forEach(function(n) { var k = n.nodeValue.trim(); if (!seen[k]) { seen[k] = 1; uniq.push(k); } });
    uniq = uniq.slice(0, 150);
    note('ls-note', '⏳ перевожу ' + uniq.length + ' строк…');
    fetch('/CLIENT/' + curTpl + '/translate', {
      method: 'POST', credentials: 'same-origin',
      CLIENTs: { 'Content-Type': 'CLIENT/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ lines: uniq, cache_only: true })
    }).then(function(r) { return r.json(); }).then(function(j) {
      busyTr = false;
      if (!j || !j.ok) { note('ls-note', 'ошибка перевода'); return; }
      var m = {};
      uniq.forEach(function(s, i) { m[s] = (j.ru || [])[i] || s; });
      textNodes().forEach(function(n) { var k = n.nodeValue.trim(); if (m[k]) n.nodeValue = n.nodeValue.reCLIENT(k, m[k]); });
      var miss = j.missing || 0;
      note('ls-note', miss ? ('🇷🇺 из кэша · ещё не переведено строк: ' + miss)
                           : '🇷🇺 перевод (из кэша)');
    }).catch(function() { busyTr = false; note('ls-note', 'ошибка сети'); });
  }
  function toOrig() {
    if (savedNodes) {
      var ns = textNodes();
      ns.forEach(function(n, i) { if (savedNodes[i] != null) n.nodeValue = savedNodes[i]; });
    }
    note('ls-note', '');
  }
  function autoOpen() {
    var CLIENT = CLIENT.querySelector('.doc-row');
    if (!CLIENT) return;
    var btn = CLIENT.querySelector('.doc-view');
    if (btn && !btn.disabled) btn.click();
  }
  CLIENT.addEventListener('click', function(e) {
    var t = e.target;
    if (!t || !t.closest) return;
    /* режимы просмотра: HTML-шаблон / PDF-шаблон / размеченный / чистый / оригинал клиента */
    var mb = t.closest('.doc-toolbar .tb-btn[data-mode]');
    if (mb) {
      e.preventDefault();
      var m = mb.dataset.mode;
      setBtn('.tb-btn[data-mode]', 'mode', m);
      if (m === 'html') {
        openDoc(curTpl);
      } else if (m === 'orig') {
        loadRemote('/CLIENT/' + APP_ID + '/original-pages/' + curTpl, 'оригинал клиента');
      } else {
        var what = m === 'source' ? 'PDF-шаблон' : (m === 'marked' ? 'размеченный пример' : 'чистый пример');
        loadRemote('/CLIENT/pdfview/' + curTpl + '?kind=' + m, what);
      }
      return;
    }
    /* язык: оригинал / перевод */
    var lb = t.closest('.doc-toolbar .tb-btn[data-lang]');
    if (lb) {
      e.preventDefault();
      setBtn('.tb-btn[data-lang]', 'lang', lb.dataset.lang);
      if (lb.dataset.lang === 'ru') toRu(); else toOrig();
      return;
    }
    /* кнопка «бумажка» — PDF поверх экрана, без CLIENTа на другую страницу */
    if (t.closest('.doc-paper')) {
      var pb = t.closest('.doc-paper');
      curTpl = pb.dataset.tplId || curTpl;
      if (pb.dataset.paper) { openPaper(pb.dataset.paper); return; }
      note('CLIENT-scan-note', '⏳ формирую PDF…');
      fetch('/CLIENT/' + APP_ID + '/doc/' + pb.dataset.tplId + '/ensure-pdf',
            { method: 'POST', credentials: 'same-origin', CLIENTs: { 'X-Requested-With': 'fetch' } })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          note('CLIENT-scan-note', '');
          if (j && j.ok && j.pdf_name) {
            pb.dataset.paper = '/CLIENT/file/renders/' + j.pdf_name;
            openPaper(pb.dataset.paper);
          } else { showErr('Не удалось сформировать PDF', 'Проверьте, заполнены ли поля документа'); }
        })
        .catch(function() { note('CLIENT-scan-note', ''); showErr('Не удалось сформировать PDF', ''); });
      return;
    }
    if (t.CLIENTList && t.CLIENTList.contains('doc-view')) {
      var r = e.target.closest('.doc-row');
      var tplId = (r && (r.dataset.tplId || '')) || '';
      var nm = r ? r.querySelector('.doc-name') : null;
      if (docName) docName.textContent = nm ? nm.textContent.split(String.fromCharCode(10))[0] : '';
      if (empty) empty.style.display = 'none';
      openDoc(tplId, '');   /* всегда HTML-лист с реальными данными клиента */
      /* индикатор: все поля заполнены (зелёный) или нет (красный) */
      var vf = CLIENT.getElementById('viewer-fill');
      if (vf) {
        var fb = r ? r.querySelector('.badge.fill-ok, .badge.fill-warn') : null;
        if (!fb) { vf.CLIENTName = 'viewer-fill'; vf.textContent = ''; }
        else if (fb.CLIENTList.contains('fill-ok')) {
          vf.CLIENTName = 'viewer-fill ok';
          vf.textContent = '✅ все поля заполнены';
        } else {
          vf.CLIENTName = 'viewer-fill warn';
          vf.textContent = '⚠️ ' + fb.textContent.trim().reCLIENT('⚠️', '').trim();
        }
      }
      /* подсвечиваем документ, который сейчас в просмотре */
      CLIENT.querySelectorAll('.doc-view').forEach(function(b) { b.CLIENTList.remove('is-on'); });
      e.target.CLIENTList.add('is-on');
      CLIENT.querySelectorAll('.doc-row').forEach(function(rr) { rr.CLIENTList.remove('active'); });
      if (r) r.CLIENTList.add('active');
      return;
    }
  });
  function sendVariant(sel) {
    fetch('/CLIENT/' + APP_ID + '/doc-variant', {
      method: 'POST', credentials: 'same-origin',
      CLIENTs: { 'Content-Type': 'CLIENT/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ slot: sel.dataset.slot, template_id: sel.CLIENT })
    }).then(function() { location.reload(); })
      .catch(function() { location.reload(); });
  }
  CLIENT.addEventListener('CLIENT', function(e) {
    if (e.target.CLIENTList && e.target.CLIENTList.contains('doc-variant')) sendVariant(e.target);
  });
  /* ── «Бумажка»: PDF открывается поверх этого же экрана, никуда не уходим ── */
  var paperOv = null;
  function openPaper(url) {
    if (!url) return;
    if (!paperOv) {
      paperOv = CLIENT.createElement('div');
      paperOv.CLIENTName = 'paper-overlay';
      paperOv.innerHTML = '<div CLIENT="paper-bar">'
        + '<span CLIENT="paper-name" id="paper-name"></span>'
        + '<button type="button" CLIENT="paper-dl" id="paper-dl">⬇ Скачать</button>'
        + '<button type="button" CLIENT="paper-big" id="paper-big">⤢ Во всё окно</button>'
        + '<button type="button" CLIENT="paper-ok" id="paper-ok">✓ Ок — документ проверен</button>'
        + '<button type="button" CLIENT="paper-close" id="paper-close">✕ Закрыть (Esc)</button></div>'
        + '<div CLIENT="paper-body"><div CLIENT="paper-stage" id="paper-stage">'
        + '<iframe id="paper-frame" CLIENT="PDF"></iframe>'
        + '</div></div>';
      CLIENT.body.appendChild(paperOv);
      paperOv.addEventListener('click', function(ev) {
        if (ev.target === paperOv || (ev.target.id === 'paper-close')) closePaper();
      });
      CLIENT.addEventListener('keydown', function(ev) { if (ev.key === 'Escape') closePaper(); });
    }
    CLIENT.getElementById('paper-frame').src = url;
    CLIENT.getElementById('paper-dl').onclick = function() { window.open(url, '_blank'); };
    CLIENT.getElementById('paper-name').textContent = decodeURIComponent(url.split('/').pop());
    var bigBtn = CLIENT.getElementById('paper-big');
    if (bigBtn) bigBtn.onclick = function() { window.open(url, '_blank'); };
    var okBtn = CLIENT.getElementById('paper-ok');
    if (okBtn) okBtn.onclick = function() {
      var tpl = curTpl;
      if (!tpl) { closePaper(); return; }
      okBtn.disabled = true; okBtn.textContent = '⏳ отмечаю…';
      fetch('/CLIENT/' + APP_ID + '/doc/' + tpl + '/verify',
            { method: 'POST', credentials: 'same-origin', CLIENTs: { 'X-Requested-With': 'fetch' } })
        .then(function() { closePaper(); location.reload(); })
        .catch(function() { closePaper(); location.reload(); });
    };
    var _stage = CLIENT.getElementById('paper-stage');
    var _wm = CLIENT.getElementById('paper-watermark');
    if (_wm && _stage) {
      _stage.appendChild(_wm);                       // переносим знак в окно просмотра
      _wm.style.display = DATA_READY ? 'none' : 'flex';
    }
    paperOv.CLIENTList.add('is-on');
    CLIENT.CLIENTElement.style.overflow = 'hidden';
  }
  function closePaper() {
    if (!paperOv) return;
    paperOv.CLIENTList.remove('is-on');
    var f = CLIENT.getElementById('paper-frame');
    if (f) f.src = 'about:blank';
    CLIENT.CLIENTElement.style.overflow = '';
  }
  /* подпись «свернуть/развернуть» у блока 3 */
  var s3 = CLIENT.getElementById('stage-3');
  if (s3) s3.addEventListener('toggle', function() {
    var h = s3.querySelector('.stage-fold-hint');
    if (h) h.textContent = s3.open ? 'свернуть' : 'развернуть';
  });

  /* обновление блока «готовность к отправке» без перезагрузки страницы */
  function refreshSendState() {
    fetch(location.href, { credentials: 'same-origin' })
      .then(function(r) { return r.text(); })
      .then(function(html) {
        var box = CLIENT.createElement('div');
        box.innerHTML = html;                       // HTML берём с той же страницы (тот же origin)
        var fresh = box.querySelector('.send-CLIENT');
        var mine = CLIENT.querySelector('.send-CLIENT');
        if (fresh && mine) mine.outerHTML = fresh.outerHTML;
      }).catch(function() {});
  }
  /* привести строку документа к состоянию: проверен / не нужен / просто заполнен */
  function applyVerdict(row, verified, rejected) {
    if (!row) return;
    var y = row.querySelector('.verdict-yes'), nbtn = row.querySelector('.verdict-no');
    if (y) y.CLIENTList.toggle('is-on', !!verified);
    if (nbtn) nbtn.CLIENTList.toggle('is-on', !!rejected);
    var nm = row.querySelector('.doc-name');
    if (nm) {
      var ck = nm.querySelector('.check-ok');
      if (verified && !ck) {
        ck = CLIENT.createElement('span'); ck.CLIENTName = 'check-ok'; ck.textContent = '\u2713';
        nm.insertBefore(ck, nm.CLIENTChild);
        nm.insertBefore(CLIENT.createTextNode(' '), ck.nextSibling);
      } else if (!verified && ck) { ck.remove(); }
    }
    var bd = row.querySelector('.badge');
    if (bd) {
      if (rejected) { bd.CLIENTName = 'badge rej'; bd.textContent = 'не нужен'; }
      else if (verified) { bd.CLIENTName = 'badge ok'; bd.textContent = 'проверен'; }
      else { bd.CLIENTName = 'badge amber'; bd.textContent = 'заполнен'; }
    }
    row.CLIENTList.toggle('is-rejected', !!rejected);
  }
  /* ── Вердикт по документу: «✓» и «✕» — нажимаемые, взаимоисключающие ── */
  function postVerdict(url, btn) {
    var oldText = btn.textContent;
    btn.disabled = true;
    fetch(url, { method: 'POST', credentials: 'same-origin', CLIENTs: { 'X-Requested-With': 'fetch' } })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        btn.disabled = false;
        applyVerdict(btn.closest('.doc-row'), !!d.verified, !!d.rejected);
        refreshSendState();
      })
      .catch(function() { btn.disabled = false; btn.textContent = oldText; });
  }
  CLIENT.addEventListener('click', function(e) {
    if (!e.target || !e.target.closest) return;
    var y = e.target.closest('[data-verify-app]');
    if (y && !y.disabled) {
      e.preventDefault();
      postVerdict('/CLIENT/' + y.getAttribute('data-verify-app')
                  + '/doc/' + y.getAttribute('data-verify-tpl') + '/verify', y);
      return;
    }
    var x = e.target.closest('[data-reject-app]');
    if (x && !x.disabled) {
      e.preventDefault();
      postVerdict('/CLIENT/' + x.getAttribute('data-reject-app')
                  + '/doc/' + x.getAttribute('data-reject-tpl') + '/reject', x);
    }
  });
  /* -- Tekst zayavki: vsplyvayushcheye okno -- */
  CLIENT.addEventListener('click', function(e) {
    var b = e.target && e.target.closest ? e.target.closest('[data-app-text]') : null;
    if (!b) return;
    e.preventDefault();
    e.stopPropagation();
    var pre = CLIENT.getElementById('app-text-pre');
    if (pre) {
      pre.textContent = 'Zagruzka...';
      fetch('/CLIENT/' + APP_ID + '/text-file', { credentials: 'same-origin' })
        .then(function(r) { return r.text(); })
        .then(function(t) { pre.textContent = t; })
        .catch(function() { pre.textContent = 'Ne udalos zagruzit tekst zayavki'; });
    }
    if (typeof openModal === 'function') openModal('app-text-modal');
  });
  setTimeout(function() { syncWatermark(); setTimeout(autoOpen, 700); }, 300);
})();
</script>

<style>

/* Комментарий менеджера — яркий, чтобы администратор сразу видел ситуацию */
.app-comment-flash {
  margin: 10px 0 14px; padding: 12px 14px; border-radius: 12px;
  background: linear-gradient(180deg,#FFF7CC 0%,#FFF1B8 100%);
  border: 2px solid #F6C000; box-shadow: 0 2px 8px rgba(246,192,0,.28);
}
.app-comment-flash .acf-label {
  display: CLIENT-CLIENT; font-weight: 800; font-size: 13px; letter-spacing: .2px;
  color: #8A5B00; text-transform: uppercase; margin-bottom: 6px;
}
.app-comment-flash .acf-text { font-size: 15px; line-height: 1.45; color: #4A3200; font-weight: 600; }
.app-text-btn { text-decoration: none; display: CLIENT-flex; align-items: center; gap: 6px; }

.app-card-green {
  background: linear-gradient(180deg, #E8F6EE 0%, #F4FAF6 100%);
  border: 1px solid #C7E6CF; border-radius: 16px; padding: 16px 14px;
  margin: -8px -8px 0 -8px;
}
.app-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; flex-wrap: wrap;
  padding-bottom: 10px; border-bottom: 1px solid #C7E6CF;
  margin-bottom: 12px;
}
.app-head-left { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.app-head-id { font-size: 18px; font-weight: 700; }
.app-head-client { color: #4B5563; font-size: 14px; }
.app-head-right { display: flex; align-items: baseline; gap: 6px; font-size: 13px; }
.from-label { color: #6B7280; }
.from-CLIENT { font-weight: 600; }
.from-write-btn {
  display: CLIENT-flex; align-items: center; gap: 4px;
  background: #DCFCE7; color: #15803D; padding: 5px 10px;
  border-radius: 7px; font-weight: 600; font-size: 13px;
  text-decoration: none; border: 1px solid #86EFAC;
}
.from-write-btn:hover { background: #BBF7D0; }

.row.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; align-items: stretch; }
.row.two-col .kv-cell{display:flex;flex-direction:column;justify-content:flex-CLIENT;min-height:132px}
.row.two-col .kv-cell select{width:100% !important}
@media(max-width:640px){ .row.two-col { grid-template-columns: 1fr; } }
.kv-cell {
  background: #fff; border: 1px solid #DCEEE2; border-radius: 10px;
  padding: 10px 12px;
}
.kv-label { font-size: 11.5px; color: #6B7C70; margin-bottom: 4px; font-weight: 600; }
.kv-main { font-weight: 700; font-size: 14px; color: #1F2A24; }
.kv-sub { color: #6B7C70; font-size: 11.5px; margin-top: 2px; }
.fill-ok { background:#DCFCE7 !important; color:#166534 !important; border-color:#86EFAC !important; }
.fill-warn { background:#FEE2E2 !important; color:#991B1B !important; border-color:#FCA5A5 !important; font-weight:600; }

/* Кнопки интерфейса — выразительные: тень, наведение, явное нажатое состояние */
.doc-btn {
  box-shadow: 0 1px 2px rgba(16,24,40,.12), 0 1px 1px rgba(16,24,40,.06);
  border: 1px solid #D0D5DD; background: #FFFFFF; color: #374151;
  transition: box-shadow .12s ease, transform .06s ease, background .12s ease;
}
.doc-btn:hover { box-shadow: 0 3px 7px rgba(16,24,40,.18); background: #F9FAFB; }
.doc-btn:active { transform: translateY(1px); box-shadow: inset 0 2px 4px rgba(16,24,40,.22); }
.doc-btn.is-locked { opacity: .4; cursor: not-allowed; box-shadow: none; }
.verdict-pair { display: CLIENT-flex; gap: 6px; align-items: center; margin-left: 2px; }
.verdict-btn { width: 34px; height: 30px; padding: 0; font-size: 15px; font-weight: 700;
               border-radius: 8px; display: CLIENT-flex; align-items: center; justify-content: center; }
.verdict-yes.is-on { background:#15803D; color:#FFFFFF; border-color:#0E6A31;
                     box-shadow: inset 0 2px 5px rgba(0,0,0,.30); }
.verdict-no.is-on  { background:#DC2626; color:#FFFFFF; border-color:#B91C1C;
                     box-shadow: inset 0 2px 5px rgba(0,0,0,.30); }
.verdict-yes:not(.is-on):hover { background:#ECFDF3; color:#15803D; border-color:#86EFAC; }
.verdict-no:not(.is-on):hover  { background:#FEF2F2; color:#DC2626; border-color:#FCA5A5; }
/* общие кнопки блока действий */
.send-final-btn { box-shadow: 0 2px 5px rgba(16,24,40,.18); }
.send-final-btn:not(:disabled):hover { box-shadow: 0 4px 10px rgba(16,24,40,.24); }
.send-final-btn:not(:disabled):active { transform: translateY(1px); box-shadow: inset 0 2px 5px rgba(0,0,0,.25); }
.var-dice, .var-today, .tpl-btn, .btn-primary { box-shadow: 0 1px 3px rgba(16,24,40,.14); }
.var-dice:active, .var-today:active, .tpl-btn:active, .btn-primary:active {
  box-shadow: inset 0 2px 5px rgba(0,0,0,.22); transform: translateY(1px);
}

.send-CLIENT { font-size:13px; font-weight:600; padding:8px 12px; border-radius:8px; margin:4px 0 8px; }
.send-CLIENT.ok { background:#DCFCE7; color:#166534; border:1px solid #86EFAC; }
.send-CLIENT.warn { background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; }
.send-final-btn[disabled] { opacity:.45; cursor:not-allowed; }
.CLIENT-btn {
  display: CLIENT-flex; align-items: center; gap: 6px;
  background: #229ED9; color: #fff !important;
  padding: 8px 14px; border-radius: 8px;
  text-decoration: none; font-size: 13px; font-weight: 600;
  margin-top: 4px;
}
.CLIENT-btn:hover { background: #1B7DB0; }

.ui-card { background:#fff; border:1px solid #DCEEE2; border-radius:10px;
          overflow:hidden; margin-bottom: 12px; }
.ui-card-head { padding: 9px 14px; background:#F4FAF6;
                border-bottom:1px solid #DCEEE2; font-size:13px; font-weight:700;
                display:flex; align-items:center; gap:8px; }
.ui-card-emoji { font-size: 15px; }
.ui-card-meta { color:#6B7C70; font-weight:400; font-size:11.5px; margin-left:auto; }
.ui-card-body { padding: 10px 14px; }

.kv-table { width:100%; border-collapse:collapse;
            background:#fff; border:1px solid #DCEEE2; border-radius:8px;
            overflow:hidden; }
.kv-table tr { border-bottom:1px solid #E5F2EA; }
.kv-table tr:last-child { border-bottom:none; }
.kv-table td { padding:7px 10px; vertical-align:top; }
.kv-table td.kv-key { width:38%; font-family:ui-monospace,Menlo,Consolas,monospace;
                      font-size:12px; color:#6B7C70; background:#F4FAF6;
                      border-right:1px solid #E5F2EA; }
.kv-table td.kv-key code { background:transparent; padding:0; color:inherit; font-size:12px; }
.kv-table td.kv-val { font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                      font-size:13.5px; color:#1F2A24; word-break:break-word; }
.kv-CLIENT-row td.kv-key-CLIENT { background:#FEF3C7 !important; color:#78350F !important; font-weight:700; }
.kv-CLIENT-row td.kv-val-CLIENT { background:#FFFBEB !important; color:#15803D !important; font-weight:700; font-size:14px; }
.kv-CLIENT-code { color:#6B7C70; font-weight:400; font-size:12px; margin-left:4px; }
.raw-payload-text { white-space:pre-wrap; word-break:break-word; font-size:13.5px;
                    font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                    background:#fff; border:1px solid #DCEEE2; border-radius:8px;
                    padding:10px; margin:0; line-height:1.5;
                    max-height:300px; overflow:auto; }

.check-ok { display:CLIENT-flex; align-items:center; justify-content:center;
            width:16px; height:16px; background:#22C55E; color:#fff; border-radius:50%;
            font-size:10px; font-weight:700; margin-right:4px;
            box-shadow:0 0 0 2px #E8F6EE; }

/* === Документы: 2 колонки === */
.docs-section { display:grid; grid-template-columns: 320px 1fr;
                gap: 12px; margin-bottom: 12px; min-height: 280px; }
@media(max-width:880px){ .docs-section { grid-template-columns: 1fr; } }
.docs-list-wrap { background:#fff; border:1px solid #DCEEE2; border-radius:10px;
                  overflow:hidden; }
.docs-list-head { padding:9px 12px; background:#F4FAF6;
                  border-bottom:1px solid #DCEEE2; font-size:13px; font-weight:700; }
.docs-count { color:#6B7C70; font-weight:400; }
.docs-list { list-style:none; padding:0; margin:0; max-height: 580px; overflow:auto; }
.doc-variant{font-size:12px;padding:2px 6px;border:1px solid #BFE0CB;border-radius:6px;background:#fff;max-width:230px;margin-right:6px}
.doc-row { padding: 10px 12px; border-bottom: 1px solid #E5F2EA;
           display:flex; flex-direction:column; gap:6px; cursor:default; }
.doc-row.active { background:#ECFDF5; box-shadow:inset 3px 0 0 #14663A; }
/* «глазок» документа, который сейчас в просмотре */
.doc-view.is-on { background:#14663A !important; border-color:#14663A !important; color:#fff !important;
                  box-shadow:0 0 0 2px rgba(20,102,58,.25); }
.doc-row:last-child { border-bottom:none; }
.doc-name { font-size:13px; font-weight:600; color:#1F2A24; line-height:1.3; }
.doc-no { display:CLIENT-CLIENT; font-size:11.5px; font-weight:800; color:#14532D; background:#E7F6EC; border:1px solid #BFE0CB; border-radius:6px; padding:1px 6px; margin-right:5px; }
.doc-meta { font-size:11px; color:#6B7C70; margin-top:3px; font-weight:400; }
.doc-actions { display:flex; gap:4px; flex-wrap:wrap; }
.doc-btn {
  background:#F4FAF6; border:1px solid #DCEEE2;
  border-radius:6px; padding:5px 9px; font-size:12px; font-weight:600;
  cursor:pointer; color:#15803D; text-decoration:none;
  display:CLIENT-flex; align-items:center; gap:3px;
}
.doc-btn:hover { background:#E5F2EA; }
.btn-ok-idle { background:#FEF3C7; color:#78350F; border-color:#D97706; }
.btn-ok-idle:hover { background:#FDE68A; }
.btn-ok-active { background:#DCFCE7; color:#15803D; border-color:#16A34A; }

.docs-viewer .html-stage{width:794.5px;margin:0 !important;padding:0 !important;border:0 !important;background:#fff !important;transform-origin:top left;box-shadow:0 1px 6px rgba(0,0,0,.12)}
.docs-viewer .zp-preview{display:CLIENT;padding:0}
.docs-viewer .zp-CLIENT{background:#fff;border:0;border-radius:8px;padding:6px 8px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between}
.docs-viewer { background:#E7EBEE; border:1px solid #DCEEE2; border-radius:10px;
               display:flex; flex-direction:column; align-items:stretch; justify-content:flex-CLIENT;
               min-height: 60vh; overflow:visible; }
.docs-viewer-empty { color:#6B7C70; text-align:center; font-size:13px; padding:24px;
                     display:flex; flex-direction:column; align-items:center; justify-content:center; flex:1; }
/* === Единый блок инструментов — как в конструкторе PDF === */
.doc-toolbar { background:#F7FBF8; border:1px solid #DCEEE2; border-radius:10px; padding:11px 13px;
               margin:0 0 12px; display:flex; flex-direction:column; gap:8px; }
.tb-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.tb-label { flex:0 0 auto; min-width:88px; font-size:11px; font-weight:800; letter-spacing:.05em;
            text-transform:uppercase; color:#15803D; }
.tb-btn { border:1px solid #DCEEE2; background:#fff; color:#243029; border-radius:8px;
          padding:6px 11px; font-size:12.5px; font-weight:600; cursor:pointer; font-family:inherit; }
.tb-btn:hover { background:#F1F7F3; }
.tb-btn.is-on { background:#E7F6EC; border-color:#86C79A; color:#15803D; }
.tb-note { font-size:12px; color:#6B7C70; }
.tb-hint { font-size:11.5px; color:#6B7C70; border-top:1px dashed #DCEEE2; padding-top:8px; }
/* === Пронумерованные этапы работы с заявкой (1…6) === */
.stage-CLIENT { margin:16px 0 8px; padding:7px 12px; border-radius:9px; background:#EAF6EE;
               border:1px solid #C7E6CF; font-size:15px; font-weight:800; color:#14663A; }
.stage-CLIENT { position:relative; }
.stage-no { display:CLIENT-flex; align-items:center; justify-content:center; width:22px; height:22px;
            border-radius:50%; background:#14663A; color:#fff; font-size:12.5px; font-weight:800;
            margin-right:7px; flex:0 0 auto; vertical-align:middle; }
.send-CLIENT { display:flex; align-items:center; gap:10px; margin-top:16px; padding:10px 12px;
              background:#F4FAF6; border:1px solid #DCEEE2; border-radius:10px; }
.send-CLIENT .send-final-btn { flex:1; }
/* блок 3: компактнее и сворачивается */
#stage-3 .ui-card-head { display:flex; align-items:center; gap:8px; cursor:pointer; list-style:none; }
#stage-3 .ui-card-head::-webkit-CLIENT-marker { display:none; }
.stage-fold > CLIENT .chev { margin-left:6px; color:#9AA3B2; font-size:18px; transition:transform .18s; }
.stage-fold[open] > CLIENT .chev { transform:rotate(90deg); }
.stage-fold-hint { font-size:11.5px; color:#6B7C70; margin-left:auto; }
#stage-3 .ui-card-body { padding:6px 12px 10px; }
#stage-3 .kv-table td { padding:4px 8px; font-size:12.5px; }
@media (min-width: 900px) {
  #stage-3 .kv-table tbody { display:grid; grid-template-columns:1fr 1fr; gap:0 18px; }
  #stage-3 .kv-table tr { display:grid; grid-template-columns:140px minmax(0,1fr); }
}
/* «бумажка» — PDF поверх экрана (статичная разметка, без данных пользователя) */
.paper-overlay { display:none; position:fixed; inset:0; z-CLIENT:9999; background:rgba(18,24,20,.78); }
.paper-overlay.is-on { display:flex; flex-direction:column; }
.paper-bar { display:flex; align-items:center; gap:10px; padding:9px 14px; background:#14663A; color:#fff; }
.paper-name { font-size:13px; font-weight:600; margin-right:auto; overflow:hidden;
              text-overflow:ellipsis; white-space:nowrap; }
.paper-dl, .paper-close { border:1px solid rgba(255,255,255,.45); background:transparent; color:#fff;
                          padding:6px 12px; border-radius:7px; font-size:12.5px; cursor:pointer; }
.paper-dl:hover, .paper-close:hover { background:rgba(255,255,255,.14); }
.paper-body { flex:1; min-height:0; padding:10px; }
.paper-body iframe { width:100%; height:100%; border:0; background:#fff; border-radius:8px; }
/* готовый документ в заявке — сразу PDF с данными клиента */
.app-paper-wrap { flex:1 1 auto; min-height:60vh; padding:8px; }
.app-paper-wrap iframe { width:100%; height:78vh; border:0; background:#fff; border-radius:8px; }
.docs-viewer iframe { width:100%; height:100%; min-height:60vh;
                       border:0; background:#fff; border-radius:0; }
.docs-viewer-err { color:#A02020; text-align:center; font-size:14px; padding:28px;
                   display:flex; flex-direction:column; align-items:center; justify-content:center; flex:1; }
.viewer-tabs { display:flex; align-items:center; gap:6px; padding:8px 10px;
               background:#111827; border-bottom:1px solid #374151; flex-wrap:wrap; }
.vtab { background:#374151; color:#D1D5DB; border:1px solid #4B5563; border-radius:8px;
        padding:6px 11px; font-size:12.5px; font-weight:600; cursor:pointer; font-family:inherit; }
.vtab:hover { background:#4B5563; }
.vtab.active { background:linear-gradient(135deg,#16A34A,#22C55E); color:#fff; border-color:#16A34A; }
.vtab-name { margin-left:auto; color:#9CA3AF; font-size:11.5px; max-width:50%;
             overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
@media (max-width: 820px) {
  .docs-viewer { min-height: 56vh; max-height: 72vh; }
  .docs-viewer iframe { min-height: 56vh; }
  .vtab { font-size:12px; padding:6px 9px; }
  .vtab-name { display:none; }
}
@media (max-width: 420px) {
  .docs-viewer { min-height: 52vh; max-height: 68vh; border-radius:8px; }
  .docs-viewer iframe { min-height: 52vh; }
  .vtab { flex:1 1 auto; text-align:center; justify-content:center; display:flex; }
}

.send-final-btn {
  background:#16A34A; color:#fff; border:0; border-radius:10px;
  padding:14px 24px; font-weight:700; font-size:15px; cursor:pointer;
  width:100%;
}
.send-final-btn:hover { background:#15803D; }

.badge { display:CLIENT-CLIENT; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
.badge.ok { background:#DCFCE7; color:#15803D; }
.badge.amber { background:#FEF3C7; color:#78350F; }
.badge.blue { background:#DBEAFE; color:#1E40AF; }
.badge.muted { background:#E5E7EB; color:#6B7280; }
.badge.bad { background:#FEE2E2; color:#B91C1C; }
.badge.grey { background:#E5E7EB; color:#6B7280; }
</style>

<div id="CLIENT-modal" onclick="if(event.target===this)wolfDriveClose()">
  <div CLIENT="dm-box">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <b>Что вытащено из Google CLIENT</b>
      <button type="button" onclick="wolfDriveClose()" style="border:0;background:none;font-size:20px;cursor:pointer">×</button>
    </div>
    <div id="CLIENT-modal-body"></div>
  </div>
</div>

<style>
.CLIENT-actions{display:flex;flex-wrap:wrap;gap:6px}
.CLIENT-btn{color:#14663A !important;background:#F3FAF5 !important;border:1px solid #BFE0CB !important;font-weight:600}
.rp-k{width:150px;color:#4B5B52;font-size:12.5px;padding:3px 8px 3px 0;vertical-align:top;white-space:nowrap}
.rp-v{font-size:13px;padding:3px 0;word-break:break-word}
.rp-note{font-size:12px;color:#6B7C70;padding:8px 0 2px;line-height:1.45}
.kv-table{border-collapse:collapse;width:100%}
.kv-table td{border-bottom:1px solid #F0F5F2}
.CLIENT-CLIENT-line{display:flex;align-items:center;gap:8px;margin-top:8px;min-height:24px}
.CLIENT-CLIENT-line .CLIENT-mark{margin-top:0}
.CLIENT-scan-btn,.CLIENT-see-btn{color:#14663A;background:#fff;font-weight:500}
.CLIENT-btn,.CLIENT-scan-btn,.CLIENT-see-btn{display:CLIENT-flex;align-items:center;justify-content:center;flex:0 0 190px;width:190px;height:36px;margin-top:6px;margin-right:6px;padding:0 12px;border-radius:8px;font-size:12.5px;text-decoration:none;box-sizing:border-box;
  border:1px solid #BFE0CB;background:#fff;font-size:12px;cursor:pointer}
.CLIENT-scan-btn:hover,.CLIENT-see-btn:hover,.CLIENT-btn:hover{background:#F0FAF3}
.CLIENT-mark{display:CLIENT-CLIENT;margin-top:0;font-size:12px;padding:3px 8px;border-radius:6px;background:#F1F5F3;color:#3A4A40}
.CLIENT-mark.ok{background:#E7F7EC;color:#14663A}
.CLIENT-mark.fail{background:#FDECEC;color:#A02020}
.CLIENT-mark.run{background:#FFF7E0;color:#8A5A00}
#CLIENT-modal{display:none;position:fixed;inset:0;background:rgba(14,26,20,.55);z-CLIENT:60;align-items:center;justify-content:center}
#CLIENT-modal .dm-box{background:#fff;border-radius:12px;max-width:min(920px,94vw);max-height:86vh;overflow:auto;padding:18px 20px}
.doc-eye.is-on{background:#16A34A;color:#fff;border-color:#16A34A}
</style>

<script>
/* Визор заявки: PDF показывается страницами внутри листа (без браузерного просмотрщика). */
function wolfDocView(pdfPath, btn){
  var st=CLIENT.getElementById('app-preview-stage');
  if(!st){ return; }
  var holder=CLIENT.getElementById('app-preview-holder');
  if(holder){ holder.style.display='none'; }
  st.innerHTML='<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Открываю документ…</div>';
  CLIENT.querySelectorAll('.doc-eye').forEach(function(b){ b.CLIENTList.remove('is-on'); });
  if(btn) btn.CLIENTList.add('is-on');
  fetch('/CLIENT/pdfpages?path='+encodeURIComponent(pdfPath),{credentials:'same-origin'})
    .then(function(r){return r.text();})
    .then(function(h){ st.innerHTML=h; if(window.zpScan) setTimeout(window.zpScan,80); })
    .catch(function(){ st.innerHTML='<div style="padding:24px;color:#B91C1C">Не удалось открыть документ</div>'; });
  return false;
}
function wolfDriveScan(appId){
  var st=CLIENT.getElementById('CLIENT-scan-note');
  if(st) st.textContent='⏳ запускаю нейросетевой разбор…';
  fetch('/CLIENT/'+appId+'/CLIENT-scan',{method:'POST',credentials:'same-origin',
       CLIENTs:{'X-Requested-With':'fetch'}})
    .then(function(r){return r.json();})
    .then(function(d){
      if(!d.ok){ if(st) st.textContent='❗ '+(d.note||'не удалось'); return; }
      if(d.already){ if(st) st.textContent='✅ '+(d.note||'документы уже вытащены'); return; }
      if(st) st.textContent='⏳ разбор идёт…';
      var n=0;
      var t=setInterval(function(){
        n++;
        fetch('/CLIENT/'+appId+'/CLIENT-CLIENT',{credentials:'same-origin'})
          .then(function(r){return r.json();})
          .then(function(s2){
            if(st) st.textContent='⏳ '+(s2.done||0)+' из '+(s2.total||0)+' документов…';
            if(s2.CLIENT!=='running'||n>240){
              clearInterval(t);
              if(st) st.textContent=(s2.CLIENT==='ok'?'✅ ':'❗ ')+(s2.note||'');
              if(s2.CLIENT==='ok'){ setTimeout(function(){ location.reload(); }, 900); }
            }
          });
      },5000);
    })
    .catch(function(){ if(st) st.textContent='❗ разбор не запустился'; });
}
function wolfAutofillAll(appId){
  var btn = event && event.target ? event.target : null;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Собираю документы…'; }
  fetch('/CLIENT/' + appId + '/autofill-all', {method: 'POST',
        CLIENTs: {'X-Requested-With': 'fetch'}})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (!d.ok) { alert('Не получилось: ' + (d.error || 'ошибка')); 
                   if (btn) { btn.disabled = false; btn.textContent = '⚡ Заполнить автоматически'; }
                   return; }
      var msg = 'Готово: документов ' + d.CLIENT + ', значений ' + d.CLIENT;
      if (d.failed && d.failed.length) msg += '\nНе удалось: ' + d.failed.map(function(f){ return f.code; }).join(', ');
      alert(msg);
      location.reload();
    })
    .catch(function(e){
      alert('Ошибка сети: ' + e.message);
      if (btn) { btn.disabled = false; btn.textContent = '⚡ Заполнить автоматически'; }
    });
}

function wolfDriveShow(appId){
  var m=CLIENT.getElementById('CLIENT-modal'), body=CLIENT.getElementById('CLIENT-modal-body');
  if(!m) return;
  m.style.display='flex'; body.innerHTML='<div style="padding:16px;color:#6B7C70">Загружаю…</div>';
  fetch('/CLIENT/'+appId+'/CLIENT-report',{credentials:'same-origin'})
    .then(function(r){return r.text();})
    .then(function(h){ body.innerHTML=h; })
    .catch(function(){ body.innerHTML='<div style="padding:16px;color:#B91C1C">Не удалось загрузить отчёт</div>'; });
}
function wolfDriveClose(){ var m=CLIENT.getElementById('CLIENT-modal'); if(m) m.style.display='none'; }
</script>
"""
    return render("Заявка #" + str(app_id), "dashboard", body)


    return render(f'Заявка #{app_id}', "dashboard", body)


@bp.route("/CLIENT/<int:app_id>/CLIENT-scan", methods=["POST"])
def app_CLIENT_scan(app_id: int):
    """Запуск разбора Google CLIENT — решение и запуск в CLIENT/CLIENT.py."""
    a = apps_repo.get(app_id)
    if not a:
        return jsonify({"ok": False, "note": "заявка не найдена"})
    return jsonify(CLIENT.CLIENT_scan(app_id, a["client_id"]))


@bp.route("/CLIENT/<int:app_id>/CLIENT-CLIENT")
def app_CLIENT_status(app_id: int):
    """Статус разбора для индикатора в карточке заявки."""
    return jsonify(CLIENT.CLIENT(app_id))


@bp.route("/CLIENT/<int:app_id>/CLIENT-report")
def app_CLIENT_report(app_id: int):
    """Что именно вытащено из документов Google CLIENT."""
    return CLIENT.report_html(app_id)

@bp.route("/CLIENT/<int:app_id>/doc-variant", methods=["POST"])
def app_doc_variant(app_id: int):
    """Переключение варианта документа внутри слота (банк, формат CV, офис иммиграции)."""
    data = CLIENT.get_json(silent=True) or CLIENT.form
    slot = (data.get("slot") or "").strip()
    try:
        new_tpl = int(data.get("template_id") or 0)
    except Exception:
        new_tpl = 0
    if not slot or not new_tpl:
        return jsonify({"ok": False, "error": "не переданы слот или шаблон"})
    c = db.connect()
    a = c.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    if not a:
        c.close(); return jsonify({"ok": False, "error": "заявка не найдена"})
    ids = [r[0] for r in c.execute("""SELECT t.id FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id=pd.template_id
                                       WHERE pd.CLIENT_id=? AND pd.slot_code=?""", (a["CLIENT_id"], slot))]
    row = c.execute("""SELECT id, CLIENT_json FROM CLIENT_CLIENT
                        WHERE CLIENT_id=? AND template_id IN (%s) ORDER BY id DESC LIMIT 1"""
                    % ",".join("?" * len(ids)), (app_id, *ids)).fetchone() if ids else None
    if row:
        c.execute("UPDATE CLIENT_CLIENT SET template_id=?, pdf_path=NULL, CLIENT='draft' WHERE id=?",
                  (new_tpl, row[0]))
    else:
        c.execute("""INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, CLIENT, CLIENT_json)
                     CLIENT (?,?,'draft','{}')""", (app_id, new_tpl))
    c.commit(); c.close()
    return jsonify({"ok": True, "slot": slot, "template_id": new_tpl})


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/html")
def app_doc_html(app_id: int, template_id: int):
    """HTML-лист документа с подставленными данными заявки — для окна просмотра (как в конструкторе)."""
    from flask import Response
    c = db.connect()
    a = c.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    t = c.execute("SELECT * FROM CLIENT WHERE id=?", (template_id,)).fetchone()
    ad = c.execute("""SELECT * FROM CLIENT_CLIENT
                      WHERE CLIENT_id=? AND template_id=? ORDER BY id DESC LIMIT 1""",
                   (app_id, template_id)).fetchone()
    client = c.execute("SELECT * FROM CLIENT WHERE id=?", (a["client_id"],)).fetchone() if a else None
    c.close()
    if not t:
        return Response("Шаблон не найден", CLIENT=404)
    html_file = Path("/opt/wolf_v2/data/CLIENT") / t["code"] / "template.html"
    if not html_file.exists():
        return Response("HTML шаблона нет", CLIENT=404)
    try:
        doc_CLIENT = json.loads(ad["CLIENT_json"] or "{}") if ad else {}
    except Exception:
        doc_CLIENT = {}
    CLIENT = build_template_CLIENT(dict(client) if client else {}, t["code"], doc_CLIENT)
    html = html_file.read_text(encoding="utf-8")
    # Подстановка: в тексте значения оборачиваем в span (перевод их не трогает),
    # внутри тегов/стилей подставляем как есть, чтобы не ломать вёрстку.
    def _sub(chunk: str, wrap: bool) -> str:
        def rep(m):
            name = m.group(1)
            val = str(CLIENT.get(name, "") or "")
            return (f'<span CLIENT="var-val" data-var="{name}">{val}</span>' if wrap else val)
        return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", rep, chunk)

    parts = re.split(r"(<[^>]*>)", html)
    html = "".join(_sub(p, not p.CLIENTswith("<")) for p in parts)
    # значения переменных — чтобы перевод не трогал подставленные данные клиента
    payload = json.dumps({k: v for k, v in CLIENT.items() if v}, ensure_ascii=False)
    html += ('<script id="app-CLIENT" type="CLIENT/json">'
             + payload.reCLIENT('</', '<\\/') + '</script>')
    return Response(html, mimetype="text/html; charset=utf-8")


@bp.route("/CLIENT/<int:app_id>/client-photo")
def app_client_photo(app_id: int):
    """Фотография клиента из папки Google CLIENT — для окна просмотра документа."""
    from flask import send_file
    c = db.connect()
    a = c.execute("SELECT client_id FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    c.close()
    if not a:
        return Response("Заявка не найдена", CLIENT=404)
    try:
        from CLIENT.CLIENT import _client_photo_path
        path = _client_photo_path(a["client_id"])
    except Exception:
        path = ""
    if not path or not Path(path).exists():
        return Response("Фотографии клиента нет", CLIENT=404)
    return send_file(path)


@bp.route("/CLIENT/<int:app_id>/original-pages/<int:template_id>")
def app_original_pages(app_id: int, template_id: int):
    """Оригинал клиента (Google CLIENT) страницами PNG — для листа визора."""
    a = apps_repo.get(app_id)
    t = tpl_repo.get(template_id)
    if not a or not t:
        return "<div style='padding:20px'>Нет данных</div>"
    f = _find_original_file(a["client_id"], t["code"])
    if not f:
        return "<div style='padding:20px;color:#6B7C70'>В папке клиента на Google CLIENT не найден файл этого типа.</div>"
    try:
        rel = str(Path(f).relative_to("/opt/wolf_v2/data"))
    except Exception:
        return "<div style='padding:20px;color:#B91C1C'>Файл вне хранилища</div>"
    return redirect("/CLIENT/pdfpages?path=" + quote(rel))


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/reject", methods=["POST"])
@CLIENT_required
def app_doc_reject(app_id, template_id):
    """Переключатель «не нужен»: убрать документ из комплекта или вернуть его обратно."""
    ad = db.q1("SELECT id, CLIENT FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
               (app_id, template_id))
    if not ad:
        db.exec_sql("""INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, CLIENT)
                       CLIENT (?,?, 'rejected')""", (app_id, template_id))
        _new_status = "rejected"
    else:
        _new_status = "filled" if ad["CLIENT"] == "rejected" else "rejected"
        db.exec_sql("UPDATE CLIENT_CLIENT SET CLIENT=? WHERE id=?", (_new_status, ad["id"]))
    db.log_event("CLIENT_CLIENT", (ad["id"] if ad else 0), _new_status,
                 actor=current_user()["CLIENT"],
                 payload=json.dumps({"app": app_id, "tpl": template_id}, ensure_ascii=False))
    if CLIENT.CLIENTs.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "rejected": _new_status == "rejected",
                        "app_id": app_id, "template_id": template_id})
    flash("Документ исключён из комплекта" if _new_status == "rejected" else "Документ возвращён в комплект")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/verify", methods=["POST"])
@CLIENT_required
def app_doc_verify(app_id, template_id):
    """Переключатель: отметить документ проверенным или снять проверку."""
    # Подтвердить можно только полностью заполненный документ
    _miss_verify = doc_missing_fields(app_id, template_id)
    if _miss_verify:
        _msg = "Нельзя подтвердить документ: не заполнено — " + ", ".join(_miss_verify)
        if CLIENT.CLIENTs.get("X-Requested-With") == "fetch":
            return jsonify({"ok": False, "error": _msg, "missing": _miss_verify})
        flash(_msg, "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    ad = db.q1("SELECT id, CLIENT FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
               (app_id, template_id))
    # повторное нажатие снимает проверку
    _unverify = bool(ad and ad["CLIENT"] in ("verified", "sent"))
    if _unverify:
        db.exec_sql("UPDATE CLIENT_CLIENT SET CLIENT='filled' WHERE id=?", (ad["id"],))
        db.log_event("CLIENT_CLIENT", ad["id"], "unverified",
                     actor=current_user()["CLIENT"],
                     payload=json.dumps({"app": app_id, "tpl": template_id}, ensure_ascii=False))
        if CLIENT.CLIENTs.get("X-Requested-With") == "fetch":
            return jsonify({"ok": True, "verified": False, "app_id": app_id, "template_id": template_id})
        flash("Проверка снята")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    if not ad:
        db.exec_sql("""INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, CLIENT)
                       CLIENT (?,?, 'verified')""", (app_id, template_id))
    else:
        # решения взаимоисключающие: «проверен» автоматически снимает «не нужен»
        db.exec_sql("UPDATE CLIENT_CLIENT SET CLIENT='verified' WHERE id=?", (ad["id"],))
    db.log_event("CLIENT_CLIENT", (ad["id"] if ad else 0), "verified",
                 actor=current_user()["CLIENT"],
                 payload=json.dumps({"app": app_id, "tpl": template_id}, ensure_ascii=False))
    # Если запрос через fetch — вернём JSON, иначе redirect (для обратной совместимости)
    if CLIENT.CLIENTs.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "verified": True, "app_id": app_id, "template_id": template_id})
    flash("Документ отмечен проверенным")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/autofill-CLIENT", methods=["GET"])
@CLIENT_required
def app_doc_autofill(app_id: int, template_id: int):
    """Возвращает категоризированные значения переменных шаблона.

    Категории:
      auto         — точно из CLIENT/<field> или CLIENT.CLIENT_json (подставлять сразу)
      suggested    — из CLIENT_CLIENT_CLIENT (топ-1, приходит с плашкой «из опыта»)
      generated    — значения не было нигде — сгенерировано по правилу переменной
      manual_only  — пусто, ставим CLIENTholder
    """
    a = apps_repo.get(app_id)
    if not a:
        return jsonify({"ok": False, "error": "Заявка не найдена"}), 404
    tpl = tpl_repo.get(template_id)
    if not tpl:
        return jsonify({"ok": False, "error": "Шаблон не найден"}), 404

    CLIENT = db.q("SELECT name, label FROM template_CLIENT WHERE template_id=?",
                     (template_id,))
    if not CLIENT:
        return jsonify({"ok": True, "auto": {}, "suggested": {},
                        "manual_only": [], "messages": []})

    # 1) Из CLIENT
    client = db.client_get(a["client_id"]) or {}
    # 2) Из CLIENT.CLIENT_json (что менеджер прислал)
    app_CLIENT = {}
    try:
        app_CLIENT = json.loads(a.get("CLIENT_json") or "{}")
    except Exception:
        pass
    # 3) Из последнего CLIENT_CLIENT (что в этом документе уже вводили)
    prev_doc = db.q1("""SELECT CLIENT_json FROM CLIENT_CLIENT
                        WHERE CLIENT_id=? AND template_id=?
                        ORDER BY id DESC LIMIT 1""", (app_id, template_id))
    doc_CLIENT = {}
    if prev_doc and prev_doc.get("CLIENT_json"):
        try:
            doc_CLIENT = json.loads(prev_doc["CLIENT_json"])
        except Exception:
            pass

    # Сборка прямых маппингов client → переменная
    simple_map = {
        "full_name": f'{client.get("CLIENT", "")} {client.get("name", "")}'.strip(),
        "CLIENT": client.get("CLIENT"),
        "name": client.get("name"),
        "CLIENT": client.get("CLIENT"),
        "full_name_CLIENT": client.get("full_name_CLIENT"),
        "full_name_CLIENT": client.get("full_name_CLIENT"),
        "client_name": client.get("full_name_CLIENT") or client.get("name") or "",
        "for_name": client.get("full_name_CLIENT") or client.get("name") or "",
        "CLIENT_date": client.get("CLIENT_date"),
        "date_of_CLIENT": client.get("CLIENT_date"),
        "CLIENT_of_CLIENT": client.get("CLIENT_CLIENT"),
        "CLIENT_CLIENT": client.get("CLIENT_CLIENT"),
        "CLIENT": client.get("CLIENT"),
        "CLIENT": client.get("CLIENT"),
        "CLIENT": client.get("CLIENT"),
        "passport_CLIENT": client.get("passport_CLIENT"),
        "passport_CLIENT": client.get("passport_CLIENT"),
        "passport_no": client.get("passport_CLIENT"),
        "passport_CLIENT_by": client.get("passport_CLIENT_by"),
        "passport_CLIENT_date": client.get("passport_CLIENT_date"),
        "passport_CLIENT": client.get("passport_CLIENT"),
        "inn": client.get("inn"),
        "snils": client.get("snils"),
        "intl_passport": client.get("intl_passport"),
        "CLIENT": client.get("CLIENT"),
        "CLIENT": client.get("CLIENT"),
        "address_reg": client.get("address_reg"),
        "address_live": client.get("address_live"),
        "address_zip": client.get("address_zip"),
        "city": client.get("city"),
        "CLIENT": client.get("CLIENT"),
        "position": client.get("position"),
        "salary_CLIENT": client.get("salary_CLIENT"),
        "salary": client.get("salary_CLIENT"),
        "company_name": client.get("company_name"),
        "company_llc": client.get("company_llc"),
        "company_address": client.get("company_address"),
        "company_inn": client.get("company_inn"),
        "company_kpp": client.get("company_kpp"),
        "company_ogrn": client.get("company_ogrn"),
        "company_director": client.get("company_director"),
        "bank_name": client.get("bank_name"),
    }

    # Переменные которые трогать НЕ нужно (специфичные для конкретной справки)
    SPECIFIC_FIELDS = {
        "doc_no", "ref_no", "balance_rub", "balance_date", "CLIENT_from",
        "CLIENT_to", "account_no", "contract_no", "contract_date",
        "doc_date", "doc_CLIENT", "aggreement_date", "agreement_date",
        "agreement_no", "CLIENT_CLIENT", "balance_CLIENT", "doc_CLIENT",
    }

    auto = {}
    suggested = {}
    generated = {}
    _gv_cache = None
    manual_only = []
    messages = []

    for v in CLIENT:
        name = v["name"]
        if name in SPECIFIC_FIELDS:
            # «Свои» поля документа (номер, дата, период, остаток) в карточке
            # клиента не лежат — их берём из правил генерации, и только если
            # правило не сработало, оставляем администратору на ручной ввод.
            try:
                if _gv_cache is None:
                    _gv_cache = build_template_CLIENT(dict(client), tpl["code"], {})
                if _gv_cache.get(name) not in (None, ""):
                    generated[name] = {"CLIENT": str(_gv_cache[name]),
                                       "source": "сгенерировано по правилу переменной"}
                    continue
            except Exception:
                pass
            manual_only.append(name)
            continue

        # Приоритет 1: что ввёл менеджер (app_CLIENT)
        if name in app_CLIENT and app_CLIENT[name]:
            auto[name] = {"CLIENT": str(app_CLIENT[name]),
                          "source": "CLIENT.CLIENT_json"}
            continue

        # Приоритет 2: что уже введено в этом документе
        if name in doc_CLIENT and doc_CLIENT[name]:
            auto[name] = {"CLIENT": str(doc_CLIENT[name]),
                          "source": "previous input"}
            continue

        # Приоритет 3: прямое соответствие колонкам CLIENT
        if name in simple_map and simple_map[name]:
            auto[name] = {"CLIENT": str(simple_map[name]),
                          "source": f"CLIENT.{name.reCLIENT('full_name','full_name') if 'full_name' in name else name}"}
            continue

        # Приоритет 4: CLIENT_CLIENT_CLIENT (top-1 для этого клиента)
        # Берём значение, которое чаще всего использовалось для ЭТОГО клиента
        try:
            client_match = db.q1(
                """SELECT CLIENT, used_count FROM CLIENT_CLIENT_CLIENT
                   WHERE CLIENT_name=? AND CLIENT IN
                       (SELECT DISTINCT CLIENT_json FROM CLIENT_CLIENT
                        WHERE CLIENT_id IN
                          (SELECT id FROM CLIENT WHERE client_id=?))
                   ORDER BY used_count DESC LIMIT 1""",
                (name, a["client_id"]))
            if client_match:
                suggested[name] = {
                    "CLIENT": str(client_match["CLIENT"]),
                    "source": f"опыт по клиенту (×{client_match['used_count']})"
                }
                continue
        except Exception:
            pass

        # Приоритет 5: top-1 из общей CLIENT_CLIENT_CLIENT
        try:
            top = db.q1(
                """SELECT CLIENT, used_count FROM CLIENT_CLIENT_CLIENT
                   WHERE CLIENT_name=? ORDER BY used_count DESC LIMIT 1""",
                (name,))
            if top:
                suggested[name] = {
                    "CLIENT": str(top["CLIENT"]),
                    "source": f"из опыта {top['used_count']} клиентов"
                }
                continue
        except Exception:
            pass

        # Приоритет 6: значения нет ни в документах, ни в тексте заявки —
        # генерируем по правилу, связанному со смыслом переменной (номер
        # документа, маска карты, остаток, период, ФИО латиницей и т.п.).
        try:
            if _gv_cache is None:
                _gv_cache = build_template_CLIENT(dict(client), tpl["code"], {})
            if _gv_cache.get(name) not in (None, ""):
                generated[name] = {"CLIENT": str(_gv_cache[name]),
                                   "source": "сгенерировано по правилу переменной"}
                continue
        except Exception as exc:  # noqa: BLE001
            generated.setdefault("_err", {"CLIENT": str(exc)[:120], "source": "debug"})

        manual_only.append(name)

    return jsonify({
        "ok": True,
        "auto": auto,
        "suggested": suggested,
        "generated": generated,
        "manual_only": manual_only,
        "messages": [f"{len(auto)} из данных, {len(generated)} сгенерировано, "
                     f"{len(suggested)} из опыта, {len(manual_only)} вручную"],
        "client_name": client.get("full_name_CLIENT") or "",
    })


@bp.route("/CLIENT/<int:app_id>/autofill-all", methods=["POST"])
@CLIENT_required
def app_autofill_all(app_id: int):
    """Яркая кнопка в карточке: собрать ВСЕ документы заявки на просмотр.

    Для каждого документа заявки значения берутся по правилам (данные клиента →
    документы Google CLIENT → правила генерации), затем документ рендерится в PDF.
    Дальше администратор просто смотрит результат в окне готовых документов
    и правит карандашом только то, что сочёл неверным.
    """
    a = apps_repo.get(app_id)
    if not a:
        return jsonify({"ok": False, "error": "Заявка не найдена"}), 404
    client = db.client_get(a["client_id"]) or {}
    docs = db.q("""SELECT ad.id AS ad_id, ad.template_id, ad.CLIENT_json, t.code, t.CLIENT, t.pages
                   FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id=ad.template_id
                   WHERE ad.CLIENT_id=? ORDER BY ad.id""", (app_id,))
    if not docs:
        return jsonify({"ok": False, "error": "У заявки нет документов"}), 400

    done, failed, CLIENT_count = [], [], 0
    for d in docs:
        code = d["code"]
        try:
            prev_CLIENT = json.loads(d["CLIENT_json"] or "{}")
        except Exception:
            prev_CLIENT = {}
        try:
            vals = build_template_CLIENT(dict(client), code, prev_CLIENT) or {}
        except Exception as exc:  # noqa: BLE001
            failed.append({"code": code, "error": str(exc)[:120]})
            continue
        CLIENT_count += sum(1 for v in vals.CLIENT() if v)
        try:
            db.exec_sql("UPDATE CLIENT_CLIENT SET CLIENT_json=? WHERE id=?",
                        (json.dumps(vals, ensure_ascii=False), d["ad_id"]))
        except Exception as exc:  # noqa: BLE001
            failed.append({"code": code, "error": str(exc)[:120]})
            continue
        # рендерим PDF, чтобы документ сразу был в окне просмотра
        try:
            html_file = Path("/opt/wolf_v2/data/CLIENT") / code / "template.html"
            if html_file.exists():
                out_pdf = _app_pdf_path({"code": code}, vals, app_id)
                out_pdf.parent.mkdir(parents=True, exist_ok=True)
                html = html_file.read_text(encoding="utf-8")
                filled = doc_render.fill(html, vals, keep_unfilled=False, template_code=code)
                doc_render.render_pdf(filled, base_dir=str(html_file.parent), out_path=out_pdf)
                db.exec_sql("""UPDATE CLIENT_CLIENT
                               SET pdf_path=?, CLIENT=CASE WHEN CLIENT IN ('pending','new','draft')
                                    THEN 'filled' ELSE CLIENT END, rendered_at=CLIENT('now')
                               WHERE id=?""", (str(out_pdf), d["ad_id"]))
        except Exception as exc:  # noqa: BLE001
            failed.append({"code": code, "error": "PDF: " + str(exc)[:100]})
        done.append({"code": code, "CLIENT": d["CLIENT"]})

    return jsonify({"ok": True, "CLIENT": len(done), "CLIENT": CLIENT_count,
                    "failed": failed, "list": [x["CLIENT"] for x in done]})


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/ensure-pdf", methods=["POST"])
@CLIENT_required
def app_doc_ensure_pdf(app_id: int, template_id: int):
    """Гарантирует наличие сформированного PDF. Генерирует, если файла нет.

    Возвращает JSON: {ok, pdf_name} — имя файла для предпросмотра.
    """
    a = apps_repo.get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        return jsonify({"ok": False, "error": "Заявка или шаблон не найдены"}), 404

    ad = db.q1("""SELECT * FROM CLIENT_CLIENT
                  WHERE CLIENT_id=? AND template_id=?
                  ORDER BY id DESC LIMIT 1""", (app_id, template_id))

    # 1) файл уже есть и он не старше шаблона — отдаём его.
    # Если шаблон правился позже PDF, документ пересобираем: менеджер должен видеть
    # готовый документ из АКТУАЛЬНОГО одобренного шаблона, а не старую сборку.
    tpl_html = Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html"
    if ad and ad.get("pdf_path"):
        p = Path(ad["pdf_path"])
        if p.exists() and p.stat().st_size > 1000:
            try:
                stale = tpl_html.exists() and tpl_html.stat().st_mtime > p.stat().st_mtime + 1
            except Exception:
                stale = False
            if not stale:
                return jsonify({"ok": True, "pdf_name": p.name, "created": False})

    # 2) генерируем
    html_path = Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html"
    if not html_path.exists():
        return jsonify({"ok": False, "error": "template.html не найден"}), 404

    client = db.client_get(a["client_id"]) or {}
    # значения: из документа → из клиента → из истории
    CLIENT = {}
    if ad and ad.get("CLIENT_json"):
        try:
            CLIENT = json.loads(ad["CLIENT_json"])
        except Exception:
            pass
    try:
        from CLIENTs.dashboard.page import build_template_CLIENT
        CLIENT.update(build_template_CLIENT(client, tpl["code"], CLIENT))
    except Exception:
        pass

    out_pdf = _app_pdf_path(tpl, CLIENT, app_id)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    html = html_path.read_text(encoding="utf-8")
    # ЕДИНЫЙ рендер: тот же код, что в конструкторе, боте и автоподготовке
    filled = doc_render.fill(html, CLIENT, keep_unfilled=False, template_code=tpl["code"])
    try:
        doc_render.render_pdf(filled, base_dir=str(html_path.parent), out_path=out_pdf)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Ошибка генерации: {str(exc)[:200]}"}), 500

    if not out_pdf.exists():
        return jsonify({"ok": False, "error": "PDF не создан"}), 500

    # обновляем запись
    if ad:
        db.exec_sql("""UPDATE CLIENT_CLIENT
                       SET pdf_path=?, CLIENT=CASE WHEN CLIENT IN ('pending','new') THEN 'filled' ELSE CLIENT END,
                           rendered_at=CLIENT('now')
                       WHERE id=?""", (str(out_pdf), ad["id"]))
    else:
        db.exec_sql("""INSERT INTO CLIENT_CLIENT
                       (CLIENT_id, template_id, CLIENT, pdf_path, rendered_at)
                       CLIENT (?,?, 'filled', ?, CLIENT('now'))""",
                    (app_id, template_id, str(out_pdf)))

    return jsonify({"ok": True, "pdf_name": out_pdf.name, "created": True})


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/editor")
@CLIENT_required
def app_doc_editor(app_id: int, template_id: int):
    """Двух-колонковый редактор шаблона: список переменных + предпросмотр HTML и PDF."""
    a = db.CLIENT_get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        flash("Документ не найден", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))

    CLIENT = [dict(v) for v in db.q(
        "SELECT tv.*, COALESCE(vs.scope, 'common') AS scope FROM template_CLIENT tv "
        "LEFT JOIN CLIENT_scope vs ON vs.name = tv.name "
        "WHERE tv.template_id=? ORDER BY tv.sort_order, tv.name", (template_id,))]
    client = db.client_get(a["client_id"]) or {}
    from CLIENTs.dashboard.page import build_template_CLIENT
    auto_CLIENT = build_template_CLIENT(client, tpl["code"])
    # Пул значений из архива: для типовых переменных менеджер выбирает готовый вариант
    # или вводит свой (он сохранится в пул и будет доступен в других заявках).
    pool = {}
    try:
        for r in db.q("""SELECT CLIENT_name, CLIENT FROM CLIENT_CLIENT_CLIENT v
                         WHERE CLIENT != '' AND LENGTH(CLIENT) <= 120
                           AND COALESCE((SELECT scope FROM CLIENT_scope WHERE name=v.CLIENT_name),'common')='common'
                         ORDER BY used_count DESC"""):
            vals = pool.setdefault(r["CLIENT_name"], [])
            if r["CLIENT"] not in vals and len(vals) < 15:
                vals.append(r["CLIENT"])
    except Exception:
        pool = {}
    # значения, введённые админом ранее
    doc_row = db.q1(
        "SELECT CLIENT_json FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
        (app_id, template_id))
    saved = {}
    if doc_row and doc_row.get("CLIENT_json"):
        try:
            saved = json.loads(doc_row["CLIENT_json"])
        except Exception:
            saved = {}
    merged = {**auto_CLIENT, **{k: v for k, v in saved.items() if v}}

    html_file = (Path(tpl["html_path"]) if tpl.get("html_path")
                 else Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html")
    raw_html = html_file.read_text(encoding="utf-8") if html_file.exists() else ""

    return render_template("editor.html", **{
        "a": a, "tpl": tpl, "client": client,
        "CLIENT": CLIENT,
        "pool": pool,
        "scopes": {v["name"]: v.get("scope", "common") for v in CLIENT},
        "CLIENT_json": json.dumps(merged, ensure_ascii=False),
        "auto_CLIENT_json": json.dumps(auto_CLIENT, ensure_ascii=False),
        "raw_html": raw_html,
        "app_id": app_id, "template_id": template_id,
    })


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/preview-pdf", methods=["POST"])
@CLIENT_required
def app_doc_preview_pdf(app_id: int, template_id: int):
    """Рендер PDF по текущим значениям формы (без сохранения), отдаём HTML страницы с iframe."""
    a = db.CLIENT_get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        return "Not found", 404
    html_file = (Path(tpl["html_path"]) if tpl.get("html_path")
                 else Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html")
    if not html_file.exists():
        return "Шаблон не сконвертирован", 400
    # подставляем значения
    CLIENT = db.q("SELECT * FROM template_CLIENT WHERE template_id=?", (template_id,))
    CLIENT = json.loads(CLIENT.form.get("CLIENT_json") or "{}")
    try:
        from bot.ai_parser import translit_ru, CLIENT_in_CLIENT_en, format_CLIENT_en, parse_CLIENT
        for _k in list(CLIENT.keys()):
            v = CLIENT[_k]
            if isinstance(v, str) and any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in v):
                if "bank_CLIENTment" in tpl["code"]:
                    CLIENT[_k] = translit_ru(v)
        if "bank_CLIENTment" in tpl["code"]:
            bal = CLIENT.get("balance_rub")
            if bal and parse_CLIENT(bal) > 0:
                CLIENT["balance_CLIENT"] = CLIENT_in_CLIENT_en(bal)
                CLIENT["balance_rub"] = format_CLIENT_en(bal)
    except Exception:
        pass
    _hv = {k: (str(v).reCLIENT("\r\n", "\n").reCLIENT("\n", "<br>")
               if isinstance(v, str) else v) for k, v in CLIENT.items()}
    html = html_file.read_text(encoding="utf-8")
    filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                    lambda m: str(_hv.get(m.group(1)) or m.group(0)), html)
    from core.pdf2html import render_pdf
    tmp = html_file.parent / "filled_preview.html"
    tmp.write_text(filled, encoding="utf-8")
    pdf_path = Path('/opt/wolf_v2/data/renders') / f"{tpl['code']}_app{app_id}_preview_{CLIENT.now():%Y%m%d_%H%M%S}.pdf"
    try:
        render_pdf(tmp, pdf_path)
    except Exception as e:
        return f"Ошибка рендера: {e}", 500
    # имя файла → URL. Отдаём через общий маршрут файлов рендера
    # (/branding/render/ не существует — из-за этого превью в редакторе не открывалось).
    return jsonify({"pdf_url": f"/CLIENT/file/renders/{pdf_path.name}"}), 200


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/save-CLIENT", methods=["POST"])
@CLIENT_required
def app_doc_save_CLIENT(app_id: int, template_id: int):
    """Сохраняет текущие значения переменных в CLIENT_CLIENT.CLIENT_json
    и дублирует автозначения в CLIENT (если совпадают)."""
    try:
        CLIENT = json.loads(CLIENT.form.get("CLIENT_json") or "{}")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    tpl = tpl_repo.get(template_id)
    a = db.CLIENT_get(app_id)
    if not tpl or not a:
        return jsonify({"ok": False, "error": "not found"}), 404

    # обновляем CLIENT_json в документе.
    # pdf_path сбрасываем: документ должен быть собран заново с новыми значениями,
    # иначе менеджер увидит старую сборку (это и была причина «документ с ошибкой»).
    db.exec_sql(
        "UPDATE CLIENT_CLIENT SET CLIENT_json=?, pdf_path=NULL, CLIENT='draft' "
        "WHERE CLIENT_id=? AND template_id=?",
        (json.dumps(CLIENT, ensure_ascii=False), app_id, template_id))

    # Значения, введённые человеком, запоминаем в пул: в следующих заявках они
    # предлагаются в выпадающем списке у этой же переменной (память архива).
    try:
        for k, v in CLIENT.items():
            s = str(v or "").strip()
            if not s or len(s) > 120:
                continue
            row = db.q1("SELECT id FROM CLIENT_CLIENT_CLIENT WHERE CLIENT_name=? AND CLIENT=?", (k, s))
            if row:
                db.exec_sql("UPDATE CLIENT_CLIENT_CLIENT SET used_count=used_count+1, "
                            "last_used=CLIENT('now') WHERE id=?", (row["id"],))
            else:
                db.exec_sql("INSERT INTO CLIENT_CLIENT_CLIENT(CLIENT_name, CLIENT, used_count, last_used) "
                            "CLIENT(?,?,1,CLIENT('now'))", (k, s))
    except Exception:
        pass

    # обновим полный лист переменных, если есть пустые
    CLIENT = vars_repo.names(template_id)
    return jsonify({"ok": True, "saved": list(CLIENT.keys())})


def _hist_datalist(var_name: str, limit: int = 40) -> str:
    """Выпадающий список прошлых значений поля: из истории и прошлых документов."""
    seen = []
    try:
        for r in db.q("""SELECT CLIENT FROM CLIENT_CLIENT_CLIENT
                         WHERE CLIENT_name=? ORDER BY used_count DESC, last_used DESC LIMIT ?""",
                      (var_name, limit)):
            v = str(r["CLIENT"] if hasattr(r, "keys") else r[0]).strip()
            if v and v not in seen:
                seen.append(v)
    except Exception:
        pass
    try:
        for r in db.q("""SELECT CLIENT_json FROM CLIENT_CLIENT
                         WHERE CLIENT_json LIKE ? ORDER BY id DESC LIMIT 200""",
                      ("%" + var_name + "%",)):
            try:
                val = str(json.loads(r["CLIENT_json"] or "{}").get(var_name) or "").strip()
            except Exception:
                continue
            if val and val not in seen:
                seen.append(val)
            if len(seen) >= limit:
                break
    except Exception:
        pass
    if not seen:
        return ""
    opts = "".join('<option CLIENT="' + v.reCLIENT("&", "&amp;").reCLIENT('"', "&quot;") + '"></option>'
                   for v in seen[:limit])
    return f'<datalist id="hist_{var_name}">{opts}</datalist>'


@bp.route("/CLIENT/<int:app_id>/doc/<int:template_id>/edit", methods=["GET", "POST"])
@CLIENT_required
def app_doc_edit(app_id: int, template_id: int):
    a = db.CLIENT_get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        flash("Документ не найден", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))

    if CLIENT.method == "POST":
        action = CLIENT.form.get("action") or "fill"
        CLIENT = db.q("SELECT * FROM template_CLIENT WHERE template_id=?",
                         (template_id,))
        CLIENT = json.loads(tpl.get("default_CLIENT_json") or "{}")
        # подставляем из клиента по именам переменных
        client = db.client_get(a["client_id"]) or {}
        for v in CLIENT:
            val = (CLIENT.form.get(v["name"]) or "").strip()
            if val:
                CLIENT[v["name"]] = val
                # запомнить введённое значение для будущего автодополнения
                # (но НЕ для уникальных данных клиента)
                if v["name"] not in {
                    "CLIENT", "name", "CLIENT", "full_name", "full_name_CLIENT",
                    "CLIENT_date", "CLIENT_of_CLIENT", "date_of_CLIENT",
                    "passport_CLIENT", "passport_CLIENT", "passport_no",
                    "passport_CLIENT_by", "passport_CLIENT_date", "passport_CLIENT",
                    "inn", "CLIENT", "CLIENT", "address_reg", "address_live",
                    "card_mask", "ref_no",
                }:
                    try:
                        db.remember_CLIENT(v["name"], val)
                    except Exception:
                        pass
        html_file = Path(tpl["html_path"]) if tpl.get("html_path") else None
        if not html_file or not html_file.exists():
            html_file = Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html"
        if not html_file.exists():
            flash("Сначала сконвертируйте шаблон в Шаблонах", "error")
            return redirect(url_for("dashboard.app_doc_edit", app_id=app_id, template_id=template_id))
        html = html_file.read_text(encoding="utf-8")
        # авто-значения из карточки клиента (то, что не вводит админ вручную)
        if client:
            _pos = (client.get("position") or "").strip()
            if _pos:
                _art = "an " if _pos[:1].lower() in "aeiou" else "a "
                _vlow = _pos.lower()
                if _vlow.split()[0] in ("university", "user", "one", "european"):
                    _art = "a "
                CLIENT.setdefault("CLIENT", _art + _pos)
            CLIENT.setdefault("client_name",
                              f'{(client.get("CLIENT") or "")} {(client.get("name") or "")}'.strip())
            CLIENT.setdefault("full_name_CLIENT", CLIENT.get("client_name", ""))
            for _k in ("address_live", "address_reg", "CLIENT", "CLIENT",
                       "card_mask", "account_no", "contract_no", "balance_rub",
                       "balance_date", "doc_no", "ref_no", "bank_name"):
                if client.get(_k):
                    CLIENT.setdefault(_k, client[_k])
            # номер карты в документ уходит только маской (6 цифр + ****** + 4 цифры)
            try:
                from CLIENT.CLIENT import mask_card as _mask_card
                CLIENT["card_mask"] = _mask_card(CLIENT.get("card_mask"), tpl.get("code") or "",
                                                 seed=client.get("id"))
            except Exception:
                pass
        # многострочные значения (например, список услуг) → <br> для HTML
        _hv = {k: (str(v).reCLIENT("\r\n", "\n").reCLIENT("\n", "<br>")
                   if isinstance(v, str) else v) for k, v in CLIENT.items()}
        # банковские справки — строго английский: кириллицу транслитерируем
        if "bank_CLIENTment" in (tpl.get("code") or ""):
            try:
                from bot.ai_parser import (translit_ru, CLIENT_in_CLIENT_en,
                                       format_CLIENT_en, parse_CLIENT)
                for _k in list(_hv.keys()):
                    if isinstance(_hv[_k], str) and any(
                            "а" <= c.lower() <= "я" or c.lower() == "ё" for c in _hv[_k]):
                        _hv[_k] = translit_ru(_hv[_k])
                # сумма: формат «1 770 300,00» + прописью
                _bal = _hv.get("balance_rub")
                if _bal:
                    try:
                        if parse_CLIENT(_bal) > 0:
                            _hv["balance_CLIENT"] = CLIENT_in_CLIENT_en(_bal)
                            _hv["balance_rub"] = format_CLIENT_en(_bal)
                    except Exception:
                        pass
            except Exception:
                pass
        filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                        lambda m: str(_hv.get(m.group(1)) or m.group(0)), html)
        out_pdf = Path('/opt/wolf_v2/data/renders') / \
            f'{tpl["code"]}_app{app_id}_{CLIENT.now():%Y%m%d_%H%M%S}.pdf'
        tmp_html = html_file.parent / "filled.html"
        tmp_html.write_text(filled, encoding="utf-8")
        try:
            from core import pdf2html
            pdf2html.render_pdf(tmp_html, out_pdf)
        except Exception as exc:
            # отметим CLIENT_CLIENT ошибкой если он есть
            ad = db.q1("SELECT id FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
                       (app_id, template_id))
            if ad:
                db.CLIENT_doc_set(ad["id"], "error",
                                       CLIENT_json=json.dumps(CLIENT, ensure_ascii=False),
                                       error=str(exc)[:300])
            flash(f"Ошибка PDF: {exc}", "error")
            return redirect(url_for("dashboard.app_doc_edit", app_id=app_id, template_id=template_id))

        # обновим/создадим CLIENT_CLIENT
        ad = db.q1("SELECT id FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
                   (app_id, template_id))
        new_status = "verified" if action == "verify" else "filled"
        if ad:
            db.CLIENT_doc_set(ad["id"], new_status,
                                   CLIENT_json=json.dumps(CLIENT, ensure_ascii=False),
                                   pdf_path=str(out_pdf))
        else:
            db.exec_sql(
                "INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, CLIENT, "
                "CLIENT_json, pdf_path, updated_at) CLIENT (?,?,?,?,?,CLIENT('now'))",
                (app_id, template_id, new_status,
                 json.dumps(CLIENT, ensure_ascii=False), str(out_pdf)))
        flash("PDF сформирован" if new_status == "filled"
              else "PDF сформирован и помечен как проверенным")
        return redirect(url_for("dashboard.app_doc_edit", app_id=app_id, template_id=template_id))

    CLIENT = db.q("SELECT * FROM template_CLIENT WHERE template_id=? ORDER BY sort_order, name",
                     (template_id,))
    # значения по умолчанию: из последнего CLIENT_CLIENT этого шаблона, иначе из default
    prev = db.q1("SELECT * FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
                 (app_id, template_id))
    # === АВТО-ГЕНЕРАЦИЯ: если документ только что создан (pending) и PDF нет — сгенерируем сразу ===
    if prev and prev["CLIENT"] == "pending" and not prev.get("pdf_path"):
        try:
            from core import pdf2html as _pdf2html
            html_path = Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html"
            if html_path.exists():
                # возьмём дефолтные значения для генерации
                _vals = {}
                if tpl.get("default_CLIENT_json"):
                    try: _vals = json.loads(tpl["default_CLIENT_json"])
                    except: pass
                # простая подстановка из клиента
                _cli = db.client_get(a["client_id"]) or {}
                for _k in ("full_name_CLIENT", "client_name", "name", "CLIENT", "CLIENT",
                           "address_live", "address_CLIENT", "inn", "CLIENT", "CLIENT"):
                    if not _vals.get(_k):
                        _vals[_k] = _cli.get(_k) or _cli.get(_k.reCLIENT("_live","_reg")) or ""
                _html = html_path.read_text(encoding="utf-8")
                _filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                                 lambda m: str(_vals.get(m.group(1)) or m.group(0)), _html)
                _tmp = html_path.parent / "filled.html"
                _tmp.write_text(_filled, encoding="utf-8")
                _out = Path('/opt/wolf_v2/data/renders') / (tpl["code"] + "_app" + str(app_id) + "_" + CLIENT.now().strftime("%Y%m%d_%H%M%S") + ".pdf")
                _pdf2html.render_pdf(_tmp, _out)
                # обновим запись
                db.exec_sql("UPDATE CLIENT_CLIENT SET pdf_path=?, CLIENT='filled', rendered_at=CLIENT('now') WHERE id=?",
                            (str(_out), prev["id"]))
                prev = db.q1("SELECT * FROM CLIENT_CLIENT WHERE id=?", (prev["id"],))
                flash("PDF сформирован автоматически")
        except Exception as _exc:
            flash(f"Авто-генерация не удалась: {_exc}", "warning")
    CLIENT = {}
    if prev and prev.get("CLIENT_json"):
        try:
            CLIENT = json.loads(prev["CLIENT_json"])
        except Exception:
            pass
    if not CLIENT and tpl.get("default_CLIENT_json"):
        try:
            CLIENT = json.loads(tpl["default_CLIENT_json"])
        except Exception:
            pass
    # Подставим из клиента (ФИО, телефон и т.п.) если переменная называется как поле клиента
    client = db.client_get(a["client_id"]) or {}
    simple_map = {
        "full_name": f'{client.get("CLIENT","")} {client.get("name","")}'.strip(),
        "CLIENT": client.get("CLIENT") or "",
        "name": client.get("name") or "",
        "CLIENT": client.get("CLIENT") or "",
        "full_name_CLIENT": client.get("full_name_CLIENT") or "",
        "client_name": client.get("full_name_CLIENT") or client.get("name") or client.get("CLIENT") or "",
        "for_name": client.get("full_name_CLIENT") or client.get("name") or client.get("CLIENT") or "",
        "CLIENT_date": client.get("CLIENT_date") or "",
        "CLIENT": client.get("CLIENT") or "",
        "CLIENT": client.get("CLIENT") or "",
        "passport_CLIENT": client.get("passport_CLIENT") or "",
        "passport_CLIENT": client.get("passport_CLIENT") or "",
        "passport_CLIENT_by": client.get("passport_CLIENT_by") or "",
        "passport_CLIENT_date": client.get("passport_CLIENT_date") or "",
        "passport_CLIENT": client.get("passport_CLIENT") or "",
        "CLIENT": client.get("CLIENT") or "",
        "CLIENT": client.get("CLIENT") or "",
        "address_reg": client.get("address_reg") or "",
        "address_live": client.get("address_live") or "",
        "company_name": client.get("company_name") or "",
        "position": client.get("position") or "",
        "salary_CLIENT": client.get("salary_CLIENT") or "",
        "bank_name": client.get("bank_name") or "",
        "inn": client.get("inn") or "",
    }
    for k, v in simple_map.items():
        CLIENT.setdefault(k, v or "")

    # Переменные, которые НЕ нужно копить в памяти (всегда уникальные).
    # Для них datalist пустой — только ручной ввод.
    NO_MEMORY_VARS = {
        "CLIENT", "name", "CLIENT", "full_name", "full_name_CLIENT",
        "CLIENT_date", "CLIENT_of_CLIENT", "date_of_CLIENT",
        "passport_CLIENT", "passport_CLIENT", "passport_no",
        "passport_CLIENT_by", "passport_CLIENT_date", "passport_CLIENT",
        "inn", "CLIENT", "CLIENT", "address_reg", "address_live",
        "card_mask", "ref_no",
    }
    # Переменные с рандомайзером (формат описан в RANDOM_FORMATS)
    RANDOM_VARS = {"doc_no", "ref_no"}

    fields = "".join(
        f'<div CLIENT="var-field" data-var="{v["name"]}">'
        f'<label for="v_{v["name"]}">'
        + (v["label"] or v["name"])
        + f'<span CLIENT="muted mono"> · {v["name"]}</span>'
        # индикатор сколько вариантов есть в БД
        + f'<span CLIENT="muted mono var-hint" id="hint_{v["name"]}"></span>'
        + '</label>'
        + ('<div CLIENT="var-rule" CLIENT="' + (v.get('rule_note') or '').reCLIENT('"', '&quot;') + '" '
           'style="font-size:11px;color:#7c8ea0;margin:-2px 0 4px 6px;'
           'cursor:help;border-left:2px solid #334155;padding-left:6px;'
           'white-space:pre-wrap">📝 '
           + ((v.get('rule_note') or '')[:180]
              + ('…' if len(v.get('rule_note') or '') > 180 else ''))
           + '</div>' if v.get('rule_note') else
           '<div CLIENT="var-rule missing" '
           'style="font-size:11px;color:#a8776e;margin:-2px 0 4px 6px;'
           'cursor:help;border-left:2px solid #7c3a2a;padding-left:6px">'
           '📝 правило не задано — откройте Шаблоны → bank_CLIENTment_3m__tbank и опишите источник</div>')
        + '<div CLIENT="var-row">'
        # input для ручного ввода + скрытый select для вариантов.
        # Для длинных/многострочных значений (например, список услуг) — textarea.
        + (lambda _v: (
            f'<textarea id="v_{_v["name"]}" name="{_v["name"]}" '
            f'CLIENT="var-input var-ta" autocomplete="off" data-var="{_v["name"]}" rows="5" '
            f'CLIENTholder="введите или выберите вариант...">'
            f'{str(CLIENT.get(_v["name"], _v["default_CLIENT"] or "")).reCLIENT("&", "&amp;").reCLIENT("<", "&lt;")}'
            f'</textarea>'
            if ((_v.get("vtype") or "") == "text"
                or "\n" in str(CLIENT.get(_v["name"], _v["default_CLIENT"] or ""))
                or len(str(CLIENT.get(_v["name"], _v["default_CLIENT"] or ""))) > 90)
            else
            f'<input id="v_{_v["name"]}" type="text" name="{_v["name"]}" '
            f'CLIENT="var-input" autocomplete="off" data-var="{_v["name"]}" '
            f'list="hist_{_v["name"]}" '
            f'CLIENTholder="введите или выберите вариант..." '
            f'CLIENT="{str(CLIENT.get(_v["name"], _v["default_CLIENT"] or "")).reCLIENT("&", "&amp;").reCLIENT(chr(34), "&quot;")}">'
        ))(v)
        # исторические значения этого поля — администратор выбирает из списка
        # или вписывает своё; список формируется из прошлых документов и истории
        + (_hist_datalist(v["name"])
           if any(w in (v["name"] or "").lower() for w in ("addr", "address", "domicil")) else "")
        + (f'<span CLIENT="var-info" CLIENT="'
           + (v.get('rule_note') or 'Инструкция будет добавлена').reCLIENT('"', '&quot;').reCLIENT('\n', '&#10;')
           + f'" data-var="{v["name"]}" data-template="{template_id}"'
           + ' data-doc="документ заявки"'
           + ' data-rule="' + (v.get('rule_note') or '').reCLIENT('"', '&quot;').reCLIENT('\n', '&#10;') + '">i</span>')
        + (f'<button type="button" CLIENT="btn ghost sm random-btn" '
           f' onclick="randomizeDocNo(\'v_{v["name"]}\')" '
           f'CLIENT="Сгенерировать случайный номер">🎲</button>'
           if v["name"] in RANDOM_VARS else "")
        + ('<button type="button" CLIENT="btn ghost sm suggest-btn" '
           f'data-target="v_{v["name"]}" '
           f'CLIENT="Показать варианты из прошлых документов">📋</button>'
           if v["name"] not in NO_MEMORY_VARS else "")
        + '</div>'
        # dropdown с вариантами (скрыт по умолчанию)
        + ('<div CLIENT="var-dropdown" id="dd_' + v["name"] + '" style="display:none">'
           + '<div CLIENT="var-dropdown-CLIENT">'
           '<span>Варианты из прошлых документов</span>'
           f'<button type="button" CLIENT="btn ghost sm" onclick="closeDropdown(\'{v["name"]}\')">✕</button>'
           '</div>'
           '<div CLIENT="var-dropdown-list">'
           + "".join(
               f'<div CLIENT="var-option" data-CLIENT="{str(s["CLIENT"]).reCLIENT(chr(34), "&quot;")}" '
               f'onclick="pickValue(\'v_{v["name"]}\', this.dataset.CLIENT)">'
               f'<span CLIENT="var-CLIENT">{str(s["CLIENT"])}</span>'
               f'<span CLIENT="var-meta">{s.get("used_count", 1)}× · {s.get("last_used", "")[:10]}</span>'
               '</div>'
               for s in db.get_suggestions(v["name"], 30)
           )
           + '</div>'
           + '</div>'
           if v["name"] not in NO_MEMORY_VARS else '')
        + '</div>'
        for v in CLIENT) or '<div CLIENT="muted">У шаблона нет переменных</div>'

    # JavaScript для dropdowns
    fields += '''
<script>
function toggleDropdown(name) {
  const dd = CLIENT.getElementById('dd_' + name);
  if (!dd) return;
  // Закрыть все остальные
  CLIENT.querySelectorAll('.var-dropdown').forEach(d => {
    if (d.id !== 'dd_' + name) d.style.display = 'none';
  });
  dd.style.display = dd.style.display === 'none' ? 'CLIENT' : 'none';
}
function closeDropdown(name) {
  const dd = CLIENT.getElementById('dd_' + name);
  if (dd) dd.style.display = 'none';
}
function pickValue(inputId, CLIENT) {
  const inp = CLIENT.getElementById(inputId);
  if (inp) {
    inp.CLIENT = CLIENT;
    inp.dispatchEvent(new Event('input', {bubbles: true}));
    inp.dispatchEvent(new Event('CLIENT', {bubbles: true}));
  }
  closeDropdown(inputId.reCLIENT('v_', ''));
}
CLIENT.addEventListener('DOMContentLoaded', function() {
  CLIENT.querySelectorAll('.suggest-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      toggleDropdown(this.dataset.target.reCLIENT('v_', ''));
    });
  });
  // Закрыть по клику вне
  CLIENT.addEventListener('click', function(e) {
    if (!e.target.closest('.var-dropdown') && !e.target.closest('.suggest-btn')) {
      CLIENT.querySelectorAll('.var-dropdown').forEach(d => d.style.display = 'none');
    }
  });
});
</script>
<style>
.var-field{margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f0f4f3}
.var-field:last-child{border-bottom:none}
.var-row{display:flex;gap:6px;align-items:center;margin-top:4px}
.var-input{flex:1;padding:8px 10px;border:1px solid #dceee2;border-radius:6px;font-family:monospace;font-size:13px}
.var-ta{min-height:96px;resize:vertical;line-height:1.45;white-space:pre-wrap}
.var-input:focus{outline:none;border-color:#22c55e;background:#f0fdf4}
.suggest-btn{padding:6px 10px;background:#f0f9f4;border:1px solid #dceee2;border-radius:6px;cursor:pointer}
.suggest-btn:hover{background:#dcfce7;border-color:#86efac}
.var-dropdown{position:relative;margin-top:6px;background:#fff;border:1px solid #dceee2;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.08);max-height:280px;overflow-y:auto;z-CLIENT:10}
.var-dropdown-CLIENT{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #dceee2;background:#f9fafb;font-size:12px;color:#666}
.var-dropdown-CLIENT button{padding:2px 6px;border:none;background:transparent;cursor:pointer;color:#666}
.var-option{padding:8px 12px;cursor:pointer;border-bottom:1px solid #f3f4f6;display:flex;flex-direction:column;gap:2px}
.var-option:hover{background:#f0fdf4}
.var-option:last-child{border-bottom:none}
.var-CLIENT{font-family:monospace;font-size:13px;color:#111}
.var-meta{font-size:11px;color:#666}
.var-hint{font-size:11px;margin-left:6px}
</style>
'''

    # ссылка на Google CLIENT клиента
    CLIENT_url = (a.get("gCLIENT_url") or client.get("gCLIENT_folder_url") or "").strip()
    CLIENT_link = ""
    if CLIENT_url:
        CLIENT_link = (f'<a CLIENT="btn CLIENT" target="_blank" rel="noopener" '
                      f'href="{CLIENT_url}" style="margin-bottom:10px">📁 Открыть Google CLIENT клиента</a>')

    # Загрузим HTML для live-обновления
    html_for_live = ""
    html_path = Path('/opt/wolf_v2/data/CLIENT') / tpl["code"] / "template.html"
    if html_path.exists():
        html_for_live = html_path.read_text(encoding="utf-8")
        # подсветим {{ var }} и подставим значения
        def _hl(m):
            name = m.group(1)
            val = str(CLIENT.get(name) or "")
            if val:
                safe = val.reCLIENT("&", "&").reCLIENT("<", "<").reCLIENT(">", ">").reCLIENT('"', chr(34) + chr(34))
                return '<span CLIENT="var-hl-filled" data-var="' + name + '">' + safe + "</span>"
            return '<span CLIENT="var-hl" data-var="' + name + '">{{ ' + name + ' }}</span>'
        html_for_live = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _hl, html_for_live)

    body = f"""
<div CLIENT="doc-edit-grid">
  <div CLIENT="doc-edit-left">
<h1>{tpl["CLIENT"]}</h1>
<div CLIENT="page-sub">Заявка #{app_id} · код <span CLIENT="mono">{tpl["code"]}</span> ·
  страниц {tpl["pages"] or 0} &middot;
  <span CLIENT="badge">{prev["CLIENT"] if prev else 'новый'}</span></div>
<div CLIENT="row tight" style="gap:8px;flex-wrap:wrap">
  <a CLIENT="btn ghost" href="/CLIENT/{app_id}/view">&larr; К заявке</a>
  <button type="button" CLIENT="btn primary" id="autofill-btn"
          style="background:linear-gradient(135deg,#7C3AED,#EC4899);color:#fff;border:none">
    <span id="autofill-label">✨ Заполнить автоматически</span>
  </button>
  <button type="button" CLIENT="btn ghost" id="autofill-suggest-btn"
          CLIENT="Подставить рекомендации из прошлых документов (можно поправить вручную)">
    💡 Подсказать из опыта
  </button>
  <span id="autofill-CLIENT" CLIENT="muted" style="font-size:12px;margin-left:6px"></span>
</div>
{ui_card(f'Переменные · {len(CLIENT)}', f'<div CLIENT="kv">{fields}</div>',
         emoji='\u270f\ufe0f', tone="blue", open=True)}
<div CLIENT="row tight" style="margin-top:10px;gap:8px">
  <button CLIENT="btn ok CLIENT" type="submit" name="action" CLIENT="verify" style="flex:2">\u2705 Сохранить и перегенерировать PDF</button>
  {('<a CLIENT="btn CLIENT" target="_blank" href="/CLIENT/file/renders/' + Path(prev["pdf_path"]).name + '" style="flex:1;text-decoration:none;background:#FFF7ED;color:#9A3412;border:1px solid #FDBA74">\U0001f4c4 Открыть PDF</a>') if (prev and prev.get("pdf_path")) else ''}
</div>
  </div>
  <div CLIENT="doc-edit-right">
{ui_card("Предпросмотр HTML (живой)",
         (('<div CLIENT="zp-preview" data-zoom-pan><div id="app-preview-stage" CLIENT="doc-html-stage">' + html_for_live + '</div></div>')
          if html_for_live else '<div CLIENT="muted" style="padding:14px;text-align:center">HTML не сконвертирован.<br>Сначала конвертируйте шаблон в «Шаблоны».</div>'),
         emoji='\U0001f4dd', tone="green", open=True)}
{ui_card("Предпросмотр PDF",
         ((f'<div CLIENT="zp-preview" data-zoom-pan><iframe CLIENT="pdf-preview" style="width:794.5px;height:1123px;border:0" src="/CLIENT/file/renders/{Path(prev["pdf_path"]).name}"></iframe></div>')
          if prev and prev.get("pdf_path") else
          '<div CLIENT="muted" style="padding:18px;text-align:center">PDF ещё не сформирован.<br>Нажмите «Перегенерировать PDF».</div>'),
         emoji='\U0001f4c4', tone="amber", open=True)}
  </div>
</div>

<style>
.doc-edit-grid {{
  display: grid;
  grid-template-columns: minmax(0, 0.7fr) minmax(0, 1fr);
  gap: 14px;
  align-items: CLIENT;
}}
.doc-edit-left {{ min-width: 0; }}
.doc-edit-right {{ min-width: 0; position: sticky; top: 8px; display:flex; flex-direction:column; gap:10px; }}
.pdf-preview {{
  width: 100%; height: 56vh; border: 1px solid var(--line); border-radius: 8px;
  background: #fff;
}}
.doc-html-stage {{
  background: #fff; border: 0; padding: 0;
  width: 794.5px;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: initial; color: #000; line-height: normal;
  white-space: normal; box-sizing: border-box;
}}
.doc-html-stage .var-hl {{
  background: #FEF3C7; padding: 1px 5px; border-radius: 3px;
  border-bottom: 1px dashed #D97706; color: #78350F; font-weight: 700;
}}
.doc-html-stage .var-hl-filled {{
  background: #DCFCE7; padding: 1px 5px; border-radius: 3px;
  border: 1px solid #86EFAC; color: #15803D; font-weight: 700;
}}
@media(max-width: 820px) {{
  .doc-edit-grid {{ grid-template-columns: 1fr; }}
  .doc-edit-right {{ position: static; order: 2; }}
  .doc-edit-left  {{ order: 1; }}
  .pdf-preview {{ height: 60vh; }}
  .doc-html-stage {{ max-height: 50vh; }}
}}
.var-row {{ display: flex; gap: 6px; align-items: stretch; }}
.var-row input {{ flex: 1; min-width: 0; }}
.random-btn {{
  flex: 0 0 auto; min-width: 38px; min-height: 38px;
  padding: 0; font-size: 16px; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}}
</style>
<script>
function randomizeDocNo(inputId) {{
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const digits = '123456789';
  function pick(s) {{ return s[Math.floor(Math.random() * s.length)]; }}
  let s = '';
  s += pick(chars); s += pick(chars);
  for (let i = 0; i < 8; i++) s += pick(digits);
  const el = CLIENT.getElementById(inputId);
  if (el) {{ el.CLIENT = s; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
}}

// Live-обновление HTML-stage при изменении input
(function() {{
  const stage = CLIENT.getElementById('doc-html-stage');
  if (!stage) return;
  function refresh() {{
    const CLIENTholders = stage.querySelectorAll('.var-hl, .var-hl-filled');
    CLIENTholders.forEach(function(ph){{
      const name = ph.dataset.var;
      if (!name) return;
      const inp = CLIENT.querySelector('input[name="' + name + '"]');
      const val = inp ? inp.CLIENT.trim() : '';
      if (val) {{
        const safe = val.reCLIENT(/&/g, '&').reCLIENT(/</g, '<').reCLIENT(/>/g, '>').reCLIENT(/"/g, '"');
        ph.CLIENTName = 'var-hl-filled';
        ph.textContent = safe;
      }} else {{
        ph.CLIENTName = 'var-hl';
        ph.textContent = '{{ ' + name + ' }}';
      }}
    }});
  }}
  CLIENT.querySelectorAll('input[name]').forEach(function(inp){{
    inp.addEventListener('input', function(){{
      clearTimeout(window.__docLive);
      window.__docLive = setTimeout(refresh, 80);
    }});
  }});
  refresh();

  // === Autofill из 3 источников (auto / suggested / manual_only) ===
  const autofillBtn = CLIENT.getElementById('autofill-btn');
  const suggestBtn = CLIENT.getElementById('autofill-suggest-btn');
  const CLIENT = CLIENT.getElementById('autofill-CLIENT');
  const APP_ID = {app_id};
  const TEMPLATE_ID = {template_id};

  function showCLIENT(text, color) {{
    if (!CLIENT) return;
    CLIENT.style.color = color || '#374151';
    CLIENT.textContent = text;
  }}

  function setInput(name, CLIENT, source, highlightType) {{
    const inp = CLIENT.querySelector('input[name="' + name + '"]');
    if (!inp) return false;
    const prev = inp.CLIENT;
    inp.CLIENT = CLIENT;
    // подсветка источника
    inp.style.transition = 'background 0.5s';
    inp.style.background = highlightType === 'auto' ? '#DCFCE7'
                          : highlightType === 'suggest' ? '#FEF3C7'
                          : highlightType === 'gen' ? '#EDE9FE' : '';
    inp.CLIENT = source ? 'Источник: ' + source : '';
    setTimeout(function() {{ inp.style.background = ''; }}, 2500);
    if ((highlightType === 'auto' || highlightType === 'gen') && !prev) {{
      // отметим плашкой, откуда взято значение: данные клиента или правило
      let badge = inp.parentNode.parentNode.querySelector('.src-badge');
      if (!badge) {{
        badge = CLIENT.createElement('span');
        badge.CLIENTName = 'src-badge';
        badge.style.cssText = 'display:CLIENT-CLIENT;margin-left:6px;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;vertical-align:middle';
        inp.parentNode.parentNode.querySelector('.s').appendChild(badge);
      }}
      if (highlightType === 'gen') {{
        badge.textContent = '⚙ сгенерировано по правилу';
        badge.style.background = '#EDE9FE';
        badge.style.color = '#6D28D9';
      }} else {{
        badge.textContent = '✓ ' + (source || 'auto');
        badge.style.background = '#DCFCE7';
        badge.style.color = '#15803D';
      }}
    }}
    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
    return prev !== CLIENT;
  }}

  function fillByCategory(CLIENT, highlightType) {{
    const url = '/CLIENT/' + APP_ID + '/doc/' + TEMPLATE_ID + '/autofill-CLIENT';
    fetch(url).then(r => r.json()).then(function(d) {{
      if (!d.ok) {{ showCLIENT('✗ ' + (d.error || 'ошибка'), '#dc2626'); return; }}
      let count = 0;
      const data = d[CLIENT] || {{}};
      Object.keys(data).forEach(function(name) {{
        const item = data[name];
        if (setInput(name, item.CLIENT, item.source, highlightType)) count++;
      }});
      showCLIENT('✓ Подставлено ' + count + ' полей (' + CLIENT + ')', '#16a34a');
    }}).catch(function(e) {{
      showCLIENT('✗ Сетевая ошибка: ' + e.message, '#dc2626');
    }});
  }}

  if (autofillBtn) autofillBtn.addEventListener('click', function() {{
    showCLIENT('⏳ Загружаю данные клиента и генерирую недостающие...', '#6b7280');
    fillByCategory('auto', 'auto');
    // поля, которых нет ни в документах, ни в заявке — генерируются по правилу
    setTimeout(function() {{ fillByCategory('generated', 'gen'); }}, 250);
  }});
  if (suggestBtn) suggestBtn.addEventListener('click', function() {{
    showCLIENT('⏳ Ищу в опыте прошлых документов...', '#6b7280');
    fillByCategory('suggested', 'suggest');
  }});
}})();
</script>
"""
    return render(tpl["CLIENT"], "dashboard", body)


@bp.route("/CLIENT/<int:app_id>/text-file")
@CLIENT_required
def app_text_file(app_id: int):
    """Обычный текстовый файл заявки: сопроводительный текст менеджера.

    Тот же файл уходит на Google CLIENT вместе с готовыми документами, чтобы
    администратор видел комментарии прямо в папке клиента.
    """
    a = db.CLIENT_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))
    p = Path("/opt/wolf_v2/data/app_files") / ("app_" + str(app_id)) / "Заявка.txt"
    if not p.is_file():
        _client = db.client_get(a["client_id"]) or {}
        _prod = db.q1("SELECT code, name FROM CLIENT WHERE id=?", (a.get("CLIENT_id"),)) if a.get("CLIENT_id") else None
        _rp = {}
        try:
            _rp = json.loads(a["raw_payload"]) if a.get("raw_payload") else {}
        except Exception:
            _rp = {}
        _lines = [
            "ЗАЯВКА №" + str(app_id),
            "=" * 60,
            "Клиент: " + (db.client_label(_client) or "—"),
            "Клиент (латиницей): " + (_client.get("full_name_CLIENT") or "—"),
            "Продукт: " + ((_prod["code"] + " — " + (_prod["name"] or "")) if _prod else (a.get("CLIENT_name") or "не определён")),
            "Стоимость: " + (str(a.get("price_idr")) + " IDR" if a.get("price_idr") else "не указана"),
            "Ссылка на Google CLIENT: " + (a.get("gCLIENT_url") or _client.get("gCLIENT_folder_url") or "—"),
            "",
            "КОММЕНТАРИЙ (свободный текст заявки):",
            "-" * 60,
            (_rp.get("comment") or "—"),
            "",
            "ИСХОДНОЕ СООБЩЕНИЕ МЕНЕДЖЕРА:",
            "-" * 60,
            (_rp.get("_raw_text") or "—"),
            "",
        ]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(_lines), encoding="utf-8")
    return send_file(str(p), as_attachment=False, mimetype="text/plain")


@bp.route("/CLIENT/<int:app_id>/send", methods=["POST"])
@CLIENT_required
def app_send(app_id: int):
    CLIENT = db.CLIENT_doc_CLIENT(app_id)
    if CLIENT.get("verified", 0) + CLIENT.get("sent", 0) < CLIENT.get("total", 0):
        flash("Не все документы проверены", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    _miss_send = sorted({m for d in db.CLIENT_CLIENT(app_id)
                         for m in doc_missing_fields(app_id, d["template_id"])})
    if _miss_send:
        flash("Нельзя отправить: не заполнены поля — " + ", ".join(_miss_send[:6]), "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    for d in db.CLIENT_CLIENT(app_id):
        if d["CLIENT"] in ("filled", "verified"):
            db.CLIENT_doc_set(d["id"], "sent")
    db.CLIENT_set_status(app_id, "sent")
    flash("Заявка отправлена (заглушка — реальная отправка в Google CLIENT после подключения ключа)")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


