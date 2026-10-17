"""Блок «Главная»: верхняя плашка (заявки + сумма) и лента входящих заявок.

Заявки приходят только от Telegram-бота. Менеджер/администратор видит ленту,
нажимает на карточку → попадает в карточку клиента с предзаполнением.
"""
from __future__ import annotations
from urllib.parse import quote
import html

esc = html.escape
import re
import subprocess

import json
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, flash, jsonify, current_app, redirect, render_template, request, send_file, url_for

from blocks.shared.layout import card as ui_card, docs_state_html, header_stats, item, modal, render
from services import render as doc_render
from services import marks
from core import db
from core.auth import current_user, login_required
from core.ru_labels import label_for
from repositories import applications as apps_repo, clients as clients_repo, templates as tpl_repo, variables as vars_repo

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



def _app_pdf_path(tpl: dict, values: dict, app_id: int) -> Path:
    """Путь готового PDF заявки: имя документа по-английски, ФИО латиницей, дата.

    Если файл с таким именем уже есть — добавляем время, чтобы не перезаписать.
    """
    # Имя файла — по ЗАЯВКЕ: ФИО берём из её клиента, а не из values (там могло
    # оказаться имя из образца — так появлялись файлы «KOTETS VIACHESLAV» в чужих
    # заявках). Время в имени не добавляем: документ перезаписывается, дублей нет.
    _v = dict(values or {})
    try:
        _cl = db.q1("SELECT c.surname, c.name, c.full_name_latin FROM applications a "
                    "JOIN clients c ON c.id=a.client_id WHERE a.id=?", (app_id,)) or {}
        _fio = " ".join(x for x in (_cl.get("surname"), _cl.get("name")) if x).strip()
        if _fio:
            _v["full_name_latin"] = _fio
    except Exception:
        pass
    base = doc_render.doc_filename((tpl or {}).get("title") or (tpl or {}).get("code") or "document",
                                   _v, code=(tpl or {}).get("code"))
    return Path('/opt/wolf_v2/data/renders') / base


def human_value(text: str) -> str:
    """Значение для показа: числа с разделителями разрядов, да/нет по-русски."""
    t = (text or "").strip()
    low = t.lower()
    if low in ("true", "yes", "да"):
        return "да"
    if low in ("false", "no", "нет"):
        return "нет"
    if t.isdigit() and len(t) >= 5:
        return "{:,}".format(int(t)).replace(",", " ")
    return t


# =============== ОРИГИНАЛЫ КЛИЕНТА (Google Drive) ===============
GDRIVE_ROOT = Path("/opt/wolf_v2/data/gdrive_examples")

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


from services import drive
from services.values import (  # noqa: E402 — логика вынесена в сервис
    GDRIVE_ROOT, ORIGINAL_PATTERNS,
    _original_patterns_for, _find_client_folder_by_id, _find_original_file, _minus_months, _num2words_en, _date_id, _fio_latin, _has_cyr, _translit, _ru_to_en, build_template_values)


def kind_badge(row) -> str:
    """Пометка записи. Тестовых меток нет: остался только «архив».

    Раньше «тест» и «тест с реальными данными» были разными плашками, хотя
    означали одно и то же — обкатку системы. Метки убраны по просьбе заказчика.
    """
    try:
        kind = (row.get("record_kind") or "").strip()
    except Exception:                                  # noqa: BLE001
        kind = ""
    if kind == "archive":
        return ' <span class="kind-badge kind-archive">архив</span>'
    return ""


AUTO_ON, AUTO_PAUSE = "on", "pause"


def auto_mode() -> str:
    """Режим автоматики: 'on' — заявки уходят в работу сразу, 'pause' — стоят."""
    try:
        val = (db.setting("auto_mode", "") or "").strip()
    except Exception:                                  # noqa: BLE001
        val = ""
    return AUTO_ON if val == AUTO_ON else AUTO_PAUSE


def _queue_state(app_id: int) -> str:
    """Состояние заявки в очереди: queued / running / paused / failed / done."""
    try:
        r = db.q1("SELECT status FROM auto_queue WHERE application_id=? "
                  "ORDER BY id DESC LIMIT 1", (app_id,))
        return (r.get("status") or "") if r else ""
    except Exception:                                  # noqa: BLE001
        return ""


def _last_run(app_id: int):
    try:
        return db.q1("SELECT ok, sent, stage, files, errors, finished_at FROM auto_runs "
                     "WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))
    except Exception:                                  # noqa: BLE001
        return None


def _err_list(row) -> list:
    """Ошибки последнего прогона — списком коротких строк."""
    raw = (row or {}).get("errors") if row else ""
    if isinstance(row, dict):
        raw = row.get("errors")
    try:
        data = json.loads(raw) if raw else []
    except Exception:                                  # noqa: BLE001
        data = [raw]
    return [str(x).strip() for x in (data or []) if str(x).strip()]


def _ts_fmt(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "")).strftime("%d.%m %H:%M")
    except Exception:                                  # noqa: BLE001
        return str(ts)[:16]


def _where_now(app_id: int) -> dict:
    try:
        from services import app_steps as _steps
        return _steps.where_now(app_id) or {}
    except Exception:                                  # noqa: BLE001
        return {}


def _is_active_elsewhere(app_id: int) -> bool:
    """Есть ли другая заявка, которая сейчас обрабатывается (очередь идёт по одной)."""
    try:
        r = db.q1("SELECT application_id FROM auto_queue WHERE status='running' "
                  "AND application_id<>? LIMIT 1", (app_id,))
        return bool(r)
    except Exception:                                  # noqa: BLE001
        return False


def now_state(app_id: int) -> dict:
    """Что происходит с заявкой прямо сейчас — одной строкой для менеджера."""
    try:
        from services import app_steps as _steps
        rows = _steps.trail(app_id, limit=12)
    except Exception:                                  # noqa: BLE001
        rows = []
    last = rows[-1] if rows else {}
    try:
        a = db.q1("SELECT status, sent_at FROM applications WHERE id=?", (app_id,)) or {}
    except Exception:                                  # noqa: BLE001
        a = {}
    try:
        docs = db.application_doc_summary(app_id) or {}
    except Exception:                                  # noqa: BLE001
        docs = {}
    verified = int(docs.get("verified") or 0) + int(docs.get("sent") or 0)
    draft = (int(docs.get("filled") or 0) + int(docs.get("pending") or 0)
             + int(docs.get("draft") or 0))
    bad = int(docs.get("error") or 0) + int(docs.get("rejected") or 0)
    total = int(docs.get("total") or 0)
    docs_note = "документы: %d готово · %d в работе · %d отклонено" % (verified, draft, bad) if total else ""

    state = _queue_state(app_id)
    if state == "running":
        return {"tone": "run", "label": "В работе",
                "note": "сейчас идёт этап: %s" % (_steps_label(last.get("step")) or "—"), "docs": docs_note}
    if state == "queued":
        return {"tone": "wait", "label": "В очереди", "note": "ждёт запуска вместе с остальными", "docs": docs_note}
    if a.get("sent_at") or (a.get("status") or "") == "sent":
        return {"tone": "ok", "label": "Отправлено на Диск",
                "note": "пакет ушёл, заявка закрыта", "docs": docs_note}
    status = (last.get("status") or "")
    if status in ("fail", "warn"):
        return {"tone": "bad", "label": "Остановлена на этапе: %s" % (_steps_label(last.get("step")) or last.get("step") or "—"),
                "note": str(last.get("note") or "").strip(), "docs": docs_note}
    if total and verified == total:
        return {"tone": "ok", "label": "Готова к отправке",
                "note": "все документы проверены — нажмите отправку на Диск", "docs": docs_note}
    # причина остановки: последнее предупреждение или ошибка в ленте
    reason = ""
    for r in reversed(rows):
        if (r.get("status") or "") in ("fail", "warn") and str(r.get("note") or "").strip():
            reason = str(r.get("note")).strip()
            break
    if total:
        return {"tone": "wait", "label": "Не обрабатывается",
                "note": ("цикл завершён, но пакет не готов — нужен повторный прогон"
                         + (": " + reason if reason else "")), "docs": docs_note}
    return {"tone": "wait", "label": "Ждёт обработки", "note": "цикл ещё не запускался", "docs": ""}


def _steps_label(step) -> str:
    try:
        from services import app_steps as _steps
        return _steps.STAGES.get(step, str(step or ""))
    except Exception:                                  # noqa: BLE001
        return str(step or "")


def steps_html(app_id: int) -> str:
    """Этапы обработки заявки: сверху свежий этап, снизу первый; плюс текущее состояние.

    Реализация вынесена в blocks/dashboard/helpers.py (этап 5 рефакторинга).
    """
    from blocks.dashboard.helpers import steps_html as _impl
    return _impl(app_id)


def _queue_positions() -> dict:
    """Динамическая очередь: позиция заявки = её место среди активных (queued) входящих.

    Пауза исключает заявку из нумерации, следующая сразу становится №1; новая заявка
    или снятая с паузы встаёт в конец. Считается на каждый показ, не хранится в базе.
    """
    try:
        rows = db.q("""SELECT q.application_id
                         FROM auto_queue q
                         JOIN applications a ON a.id = q.application_id
                        WHERE q.status='queued' AND a.status='new'
                        ORDER BY q.id""")
    except Exception:                                  # noqa: BLE001
        return {}
    return {int(r["application_id"]): i for i, r in enumerate(rows, 1)}


def progress_html(app_id: int) -> str:
    """Ход работы заявки: очередь, обработка, ошибка, отправка на Google Диск.

    Реализация вынесена в blocks/dashboard/helpers.py (этап 5 рефакторинга).
    """
    from blocks.dashboard.helpers import progress_html as _impl
    return _impl(app_id)


def inbox_row(a) -> str:
    """Карточка входящей заявки с кнопками: в работу / пауза / в архив.

    Реализация вынесена в blocks/dashboard/helpers.py (этап 5 рефакторинга).
    Здесь оставлен тонкий реэкспорт для обратной совместимости.
    """
    from blocks.dashboard.helpers import inbox_row as _impl
    return _impl(a)


def _work_seconds(app_id: int) -> tuple[int, bool]:
    """Рабочее время заявки: суммарно по прогонам обработчика.

    Время в очереди НЕ считается: пока заявка ждёт, таймер стоит. Идёт только
    тогда, когда обработчик реально её выполняет (auto_queue.status='running').
    """
    from datetime import datetime as _d
    try:
        rows = db.q("SELECT status, started_at, finished_at FROM auto_queue "
                    "WHERE application_id=? ORDER BY id", (app_id,))
    except Exception:                                  # noqa: BLE001
        return 0, False
    total, running = 0, False

    def _p(v):
        try:
            return _d.fromisoformat(str(v).replace("Z", ""))
        except Exception:
            return None

    for r in rows:
        t0 = _p(r.get("started_at"))
        if not t0:
            continue
        t1 = _p(r.get("finished_at"))
        st = str(r.get("status") or "")
        if st == "running" and not t1:
            t1 = _d.utcnow()
            running = True
        elif not t1:
            continue
        total += max(0, int((t1 - t0).total_seconds()))
    return total, running


def _elapsed(a: dict) -> int:
    return _work_seconds(int(a.get("id") or 0))[0]


def _is_running(a: dict) -> int:
    return 1 if _work_seconds(int(a.get("id") or 0))[1] else 0


def _fmt_elapsed(a: dict) -> str:
    sec = _elapsed(a)
    m, s_ = divmod(sec, 60)
    if m >= 60:
        return "%d ч %d мин" % (m // 60, m % 60)
    return ("%d мин %d с" % (m, s_)) if m else ("%d с" % s_)


def auto_switch_html() -> str:
    """Кнопки управления всей автоматикой: Старт и Пауза.

    Реализация вынесена в blocks/dashboard/helpers.py (этап 5 рефакторинга).
    """
    from blocks.dashboard.helpers import auto_switch_html as _impl
    return _impl()


def _inbox_script() -> str:
    """Кнопки главной работают без перезагрузки: страница не «моргает».

    Реализация вынесена в blocks/dashboard/helpers.py (этап 5 рефакторинга).
    """
    from blocks.dashboard.helpers import _inbox_script as _impl
    return _impl()


@bp.route("/")
@login_required
def page():
    s = db.stats()
    # Архивные заявки в «Входящих» не показываем — они уехали в историю.
    new_apps = [a for a in db.application_list("new")
                if (a.get("record_kind") or "") != "archive"]
    # Порядок в «Входящих»: сверху та заявка, с которой СЕЙЧАС идёт работа,
    # под ней — очередь по порядку (№1, №2…), ниже — остальные (пауза/ошибка),
    # старые выше новых. Отработала верхняя и ушла — список сдвигается вверх.
    try:
        _q_rows = db.q("SELECT application_id, status, id FROM auto_queue ORDER BY id")
        _q_state = {}
        for _r in _q_rows:                      # последняя запись по заявке — актуальна
            _q_state[int(_r["application_id"])] = str(_r["status"] or "")
        _q_order = {}
        _n = 0
        for _r in _q_rows:
            if str(_r["status"] or "") == "queued":
                _n += 1
                _q_order[int(_r["application_id"])] = _n

        def _rank(a):
            _id = int(a.get("id") or 0)
            _st = _q_state.get(_id, "")
            if _st == "running":
                return (0, 0, _id)
            if _st == "queued":
                return (1, _q_order.get(_id, 999), _id)
            return (2, 0, _id)

        new_apps.sort(key=_rank)
    except Exception:                                  # noqa: BLE001
        pass

    def _fmt_time(ts):
        if not ts:
            return ""
        try:
            return datetime.fromisoformat(ts.replace("Z", "")).strftime("%d.%m %H:%M")
        except Exception:
            return ts[:16]

    def _manager_label(a):
        if not a.get("manager_name") and not a.get("manager_username"):
            return ""
        name = a.get("manager_name") or a.get("manager_username") or ""
        uname = a.get("manager_username") or ""
        return f"от {name}" + (f" (@{uname})" if uname else "")

    new_items = "".join(inbox_row(a) for a in new_apps) or (
        '<div class="muted" style="padding:8px 2px">Входящих заявок пока нет — как только '
        'менеджер пришлёт форму боту, она появится здесь.</div>')

    topbar = header_stats(s["applications_in"], s["sum_new_idr"],
                          s["applications_all"], s["sum_all_idr"])

    # Строка о периоде: тестовые метки убраны, остаётся только подпись периода.
    _mark_label = marks.label()
    _mark_line = (f'<div class="page-sub" style="color:#92400E;font-weight:700">'
                  f'{_mark_label} · заявок периода: {marks.count()}</div>') if _mark_label else ''

    body = f"""
<div class="inbox-head">
  <div class="inbox-headrow">
    <h1>Входящие заявки</h1>
    <div class="inbox-headmid">{auto_switch_html()}</div>
    <div class="inbox-headspacer"></div>
  </div>
  <div class="inbox-hint">Заявка из Telegram-бота появляется здесь сразу. «Старт» — заявки уходят в работу
по очереди, по одной; «Пауза» — стоят и ждут. Каждую заявку можно остановить или убрать в архив отдельно.</div>
</div>
{_mark_line}
{ui_card(f'Входящие · {len(new_apps)}', new_items, emoji="📥", tone="amber", open=True)}
{_inbox_script()}
{_timer_css}
"""
    known_ids = [a["id"] for a in new_apps]
    # CSS крупного таймера + спиннера вставляется один раз на страницу.
    try:
        from blocks.dashboard.helpers import _emit_timer_css
        _timer_css = _emit_timer_css()
    except Exception:
        _timer_css = ""
    live_js = """
<div id="newapp-toast" style="display:none;position:fixed;left:50%;transform:translateX(-50%);
     top:14px;z-index:9998;background:#0E9F6E;color:#fff;border-radius:12px;padding:11px 16px;
     font-weight:600;box-shadow:0 12px 30px rgba(14,159,110,.35);font-size:14px"></div>
<script>
(function(){
  var KNOWN = __KNOWN__;
  var busy = false;
  function show(list){
    var t = document.getElementById('newapp-toast');
    var a = list[0];
    t.style.display = 'block';
    t.innerHTML = '🔔 Новая заявка #' + a.id + ' · ' + a.client + ' · ' + a.product;
    setTimeout(function(){ location.reload(); }, 2200);
  }
  function check(){
    if (busy) return; busy = true;
    fetch('/api/inbox-ids', {headers: {'X-Requested-With': 'fetch'}, credentials: 'same-origin'})
      .then(function(r){ return r.json(); })
      .then(function(d){
        busy = false;
        var fresh = (d.items || []).filter(function(x){ return KNOWN.indexOf(x.id) < 0; });
        if (fresh.length) { show(fresh); return; }
        // заявка ушла из «новых» (взята в работу) — тоже обновим список
        if ((d.ids || []).length !== KNOWN.length) { location.reload(); }
      })
      .catch(function(){ busy = false; });
  }
  function fmt(sec){
    var m = Math.floor(sec / 60), s2 = sec % 60;
    if (m >= 60) { var h = Math.floor(m / 60); return '⏱ ' + h + ' ч ' + (m % 60) + ' мин'; }
    return m ? ('⏱ ' + m + ' мин ' + s2 + ' с') : ('⏱ ' + s2 + ' с');
  }
  setInterval(function(){
    document.querySelectorAll('.app-timer').forEach(function(el){
      if (el.dataset.running !== '1') return;
      el.dataset.elapsed = String(parseInt(el.dataset.elapsed || '0', 10) + 1);
      el.textContent = fmt(parseInt(el.dataset.elapsed, 10));
    });
  }, 1000);
  setInterval(check, 5000);
  document.addEventListener('visibilitychange', function(){ if (!document.hidden) check(); });
})();
</script>
""".replace("__KNOWN__", str(known_ids))
    body = body + live_js
    return render("Главная", "dashboard", body, topbar=topbar)


@bp.route("/api/inbox-ids")
@login_required
def api_inbox_ids():
    """Список новых заявок для автообновления главной страницы (без перезагрузки)."""
    rows = [a for a in db.application_list("new")
            if (a.get("record_kind") or "") != "archive"]
    data = [{"id": a["id"],
             "client": " ".join(x for x in (a.get("surname"), a.get("name")) if x) or "—",
             "product": a.get("product_name") or "—",
             "mgr": a.get("manager_name") or a.get("manager_username") or "",
             "time": (a.get("created_at") or "")[:16]} for a in rows]
    return jsonify({"ids": [d["id"] for d in data], "items": data, "count": len(data)})


@bp.route("/live")
@login_required
def live_state():
    """Живое состояние входящих: этапы и очередь обновляются без перезагрузки страницы."""
    rows = [a for a in db.application_list("new")
            if (a.get("record_kind") or "") != "archive"]
    apps = []
    for a in rows:
        aid = a["id"]
        st = _queue_state(aid)
        apps.append({
            "id": aid,
            "state": st,
            "progress": progress_html(aid),
            "steps": steps_html(aid),
            "queued": st in ("queued", "running"),
        })
    return jsonify({"ok": True, "mode": auto_mode(), "apps": apps})


@bp.route("/applications/<int:app_id>/take", methods=["POST"])
@login_required
def app_take(app_id: int):
    user = current_user()
    db.application_take(app_id, user["id"])
    db.log_event("application", app_id, "taken", actor=user["login"])
    # уведомляем менеджера, который прислал заявку через бота
    try:
        from bot.notify import notify_manager_taken
        notify_manager_taken(app_id)
    except Exception as exc:                            # noqa: BLE001
        current_app.logger.warning("notify_manager_taken failed: %s", exc)
    return redirect(url_for("dashboard.app_view", app_id=app_id))


@bp.route("/auto/mode", methods=["POST"])
@login_required
def auto_mode_set():
    """Кнопка «Старт/Пауза» на главной: включает и выключает автоматику."""
    want = AUTO_ON if (request.form.get("mode") or "").strip() == AUTO_ON else AUTO_PAUSE
    db.set_setting("auto_mode", want)
    if want == AUTO_ON:
        _wake_worker()                      # «Старт» сразу запускает очередь, без ожидания крона
    db.log_event("system", 0, "auto_mode", payload=want,
                 actor=(current_user() or {}).get("login", ""))
    return jsonify({"ok": True, "mode": want})


def _queue_ensure() -> None:
    db.exec_sql("""CREATE TABLE IF NOT EXISTS auto_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        started_at TEXT, finished_at TEXT, last_error TEXT)""")


def _queue_set(app_id: int, action: str) -> str:
    """Поставить заявку в работу или остановить её.

    «В работу» — заявка встаёт В КОНЕЦ очереди: прежняя строка закрывается, создаётся
    новая, поэтому номер очереди у остальных пересчитывается (динамическая очередь).
    «Пауза» — заявка выходит из нумерации, следующая сразу становится первой.
    """
    _queue_ensure()
    if action == "start":
        db.exec_sql("UPDATE auto_queue SET status='closed' WHERE application_id=? "
                    "AND status IN ('queued','paused','failed','done','closed')", (app_id,))
        db.exec_sql("INSERT INTO auto_queue (application_id, status) VALUES (?, 'queued')", (app_id,))
        state = "queued"
    else:
        state = "paused"
        row = db.q1("SELECT id FROM auto_queue WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))
        if row:
            db.exec_sql("UPDATE auto_queue SET status=?, last_error=NULL WHERE id=?", (state, row["id"]))
        else:
            db.exec_sql("INSERT INTO auto_queue (application_id, status) VALUES (?,?)", (app_id, state))
    db.log_event("application", app_id, "queue_" + action, payload=state)
    return state


def _wake_worker() -> None:
    """Разбудить очередь сразу после нажатия «Старт»/«В работу», не ожидая тика крона."""
    try:
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        subprocess.Popen([sys.executable or "/usr/bin/python3",
                          str(root / "scripts" / "auto_queue.py"), "worker"],
                         cwd=str(root), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:                                  # noqa: BLE001
        pass


@bp.route("/applications/<int:app_id>/queue/<action>", methods=["POST"])
@login_required
def app_queue(app_id: int, action: str):
    """Кнопка на заявке: «в работу» или «пауза»."""
    if action not in ("start", "pause"):
        return jsonify({"ok": False, "error": "unknown action"}), 400
    # Используем единый фасад services.queue (вместо прямого _queue_set)
    from services.queue import set_state as _qset, is_active_elsewhere as _ia
    state = _qset(app_id, action)
    actor = (current_user() or {}).get("login", "") or "admin"
    if action == "start":
        # Ручной запуск работает НЕЗАВИСИМО от auto_mode: даже при глобальной паузе
        # администратор может явно запустить обработку. Логируем — кто нажал.
        db.log_event("application", app_id, "queue_start",
                     actor=actor,
                     payload={"mode": auto_mode(), "state": state})
        if auto_mode() == AUTO_ON:
            _wake_worker()                                 # пошла сразу, а не через 2 минуты
        else:
            db.log_event("application", app_id, "queue_start_paused",
                         actor=actor,
                         payload={"note": "автоматика на паузе, обработка встанет в очередь"})
    elif action == "pause":
        db.log_event("application", app_id, "queue_pause", actor=actor, payload={"state": state})
    return jsonify({"ok": True, "state": state, "queued": state in ("queued", "running") or _ia(app_id),
                    "progress": progress_html(app_id)})


@bp.route("/applications/<int:app_id>/restart", methods=["POST"])
@login_required
def app_restart(app_id: int):
    """Кнопка «Прогнать ещё раз»: заявка, остановленная проверкой, идёт по кругу заново.

    Также используется админом, чтобы ДОСТАТЬ заявку из архива:
    record_kind='archive' → record_kind='inbox', статус → new, документы
    sent → verified. Заявка снова попадает в цикл.
    """
    db.exec_sql("UPDATE applications SET status='new', sent_at=NULL, "
                "record_kind='inbox' WHERE id=?", (app_id,))
    # подтверждённые документы остаются подтверждёнными, сброс — только у отправленных
    db.exec_sql("UPDATE application_documents SET status='verified' "
                "WHERE application_id=? AND status='sent'", (app_id,))
    state = _queue_set(app_id, "start")
    if auto_mode() == AUTO_ON:
        _wake_worker()
    db.log_event("application", app_id, "restart", actor=(current_user() or {}).get("login", "") or "admin",
                 payload={"state": state, "from_archive": True})
    return jsonify({"ok": True, "state": state, "progress": progress_html(app_id)})


@bp.route("/applications/<int:app_id>/archive", methods=["POST"])
@login_required
def app_archive(app_id: int):
    """Убрать заявку из входящих: она остаётся в истории."""
    db.exec_sql("UPDATE applications SET record_kind='archive' WHERE id=?", (app_id,))
    _queue_ensure()
    db.exec_sql("UPDATE auto_queue SET status='archived' WHERE application_id=? "
                "AND status IN ('queued','running','paused')", (app_id,))
    db.log_event("application", app_id, "archived", actor=(current_user() or {}).get("login", ""))
    return jsonify({"ok": True, "state": "archive"})


@bp.route("/applications/<int:app_id>/change-product", methods=["POST"])
@login_required
def app_change_product(app_id: int):
    """Смена продукта администратором. Пересоздаёт application_documents."""
    from flask import request
    new_pid = request.form.get("product_id", type=int)
    if not new_pid:
        flash("Не выбран продукт", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    # обновляем заявку
    prod = db.q1("SELECT id, code, name, description FROM products WHERE id=?", (new_pid,))
    if not prod:
        flash("Продукт не найден", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    # Тот же продукт — не трогаем ни документы, ни галочки: повторное сохранение
    # карточки не должно пересобирать список документов заявки.
    _cur = db.q1("SELECT product_id FROM applications WHERE id=?", (app_id,)) or {}
    if int((_cur.get("product_id") or 0)) == new_pid:
        flash("Продукт не изменился — список документов оставлен как есть.", "ok")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    # вытащим price_idr из description или 0
    new_price = 0
    if prod.get("description"):
        import re as _re
        m = _re.search(r"price_idr\s*=\s*(\d+)", prod["description"])
        if m:
            new_price = int(m.group(1))
    db.exec_sql("UPDATE applications SET product_id=?, price_idr=? WHERE id=?",
              (prod["id"], new_price, app_id))
    # Удаляем старые application_documents и создаём новые под новый продукт.
    # Подтверждённые (verified) и уже отправленные (sent) не трогаем: это
    # зафиксированные документы заявки, они переживают смену продукта.
    db.exec_sql("DELETE FROM application_documents WHERE application_id=? "
                "AND IFNULL(status,'') NOT IN ('verified','sent')", (app_id,))
    new_templates = db.q(
        """SELECT t.id, t.code, t.title FROM product_documents pd
              JOIN templates t ON t.id=pd.template_id
              WHERE pd.product_id=? ORDER BY t.id""",
        (new_pid,))
    import datetime as _dt
    now = _dt.datetime.now().isoformat(timespec="seconds")
    _cl_bank = ""
    try:
        _cl_row = db.client_get(a["client_id"]) or {}
        _cl_bank = (_cl_row.get("bank_name") or "").lower()
    except Exception:
        _cl_bank = ""
    # Взаимозаменяемые документы (банковские справки Тинькофф/Сбер, форма резюме, письмо
    # Нгурах-Рай/Денпасар) — это один слот: в заявке должен быть ОДИН документ из группы.
    _rows = db.q("""SELECT t.id, t.code, pd.slot_code, COALESCE(pd.is_default, 0) AS is_default
                      FROM product_documents pd JOIN templates t ON t.id = pd.template_id
                      WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged') ORDER BY t.id""", (new_pid,))
    _by_slot = {}
    for _r in _rows:
        _by_slot.setdefault(_r["slot_code"] or ("tpl_" + str(_r["id"])), []).append(_r)
    for _slot, _variants in _by_slot.items():
        _ok = [v for v in _variants if _bank_allows(v["code"], _cl_bank)] or _variants
        _def = [v for v in _ok if v["is_default"]] or _ok
        db.exec_sql(
            "INSERT INTO application_documents (application_id, template_id, status, rendered_at) "
            "SELECT ?, ?, 'pending', ? WHERE NOT EXISTS ("
            "SELECT 1 FROM application_documents WHERE application_id=? AND template_id=?)",
            (app_id, _def[0]["id"], now, app_id, _def[0]["id"]))
    db.log_event("application", app_id, "product_changed", actor=current_user()["login"],
                 payload=json.dumps({"new_product": prod["code"]}, ensure_ascii=False))
    flash(f"Продукт изменён: {prod['name']}. Список документов обновлён.", "ok")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


# Переменные, которые система заполняет сама или которых может не быть: в проверку готовности не входят
_AUTO_OR_OPTIONAL_VARS = {
    "doc_no", "ref_no", "card_mask", "doc_date", "balance_rub", "balance_value",
    "balance_words", "balance_cents", "period_from", "period_to",
    "account_no", "contract_date", "contract_no",
}


def doc_missing_fields(app_id: int, template_id: int) -> list:
    """Каких данных не хватает документу заявки.

    Считаем ровно по тем значениям, которые уходят в документ (та же сборка, что при
    формировании PDF): незаполненными считаются переменные, оставшиеся в шаблоне без значения.
    """
    try:
        from services.values import build_template_values
        from services.render import VAR_RE, fill
    except Exception:                                       # noqa: BLE001
        return []
    tpl = tpl_repo.get(template_id)
    if not tpl:
        return []
    code = tpl["code"]
    path = Path("/opt/wolf_v2/data/templates") / code / "template.html"
    if not path.exists():
        return []
    a = db.application_get(app_id) or {}
    client = db.client_get(a.get("client_id")) or {}
    ad = db.q1("SELECT values_json FROM application_documents WHERE application_id=? AND template_id=?",
               (app_id, template_id)) or {}
    doc_values = {}
    if ad.get("values_json"):
        try:
            doc_values = json.loads(ad["values_json"] or "{}") or {}
        except Exception:                                   # noqa: BLE001
            doc_values = {}
    try:
        vals = build_template_values(client, code, doc_values) or {}
    except Exception:                                       # noqa: BLE001
        vals = dict(doc_values)
    html = path.read_text(encoding="utf-8")
    filled = fill(html, vals, keep_unfilled=True, template_code=code)
    return sorted(set(VAR_RE.findall(filled)) - _AUTO_OR_OPTIONAL_VARS)



def _app_loader_frame(app_id: int, title: str):
    """Каркас страницы заявки: шапка уже видна, содержимое догружается.

    Тяжёлые блоки (сборка документов, предпросмотр) готовятся секундами,
    поэтому страница сразу отдаёт название и крутящийся индикатор, а сами
    блоки приезжают отдельным запросом.
    """
    frame = """
<div id="wolf-content">
  __PIPELINE__
  <div style="display:flex;align-items:center;gap:14px;padding:26px 18px;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#3C4A42">
    <span style="width:26px;height:26px;flex:0 0 26px;border:3px solid #D7E3DA;
          border-top-color:#2F7D5B;border-radius:50%;animation:wolfflip .8s linear infinite"></span>
    <span style="font-size:15px"><b>Заявка #__APPID__</b> — загружаю блоки…<br>
      <span style="font-size:12.5px;color:#6B7C70">Собираю данные заявки, документы и предпросмотр</span></span>
  </div>
  <style>
@keyframes spin{to{transform:rotate(360deg)}}@keyframes wolfflip{to{transform:rotate(360deg)}}</style>
</div>
<script>
(function(){
  var url = "/applications/__APPID__/review";
  fetch(url, {credentials: "same-origin"})
    .then(function(r){ return r.text(); })
    .then(function(h){
      var box = document.getElementById("wolf-content");
      if (!box) return;
      // HTML приходит с этого же сайта (same-origin, наш собственный рендер),
      // пользовательский ввод в него не попадает, вставка безопасна.
      var doc = new DOMParser().parseFromString(h, "text/html");
      var fresh = doc.getElementById("wolf-content");
      if (fresh) { box.innerHTML = fresh.innerHTML; }
      else { box.innerHTML = '<div style="padding:20px;color:#B91C1C">Не удалось собрать страницу заявки</div>'; }
      var sc = doc.querySelectorAll("script");
      for (var i = 0; i < sc.length; i++) {
        var el = document.createElement("script");
        if (sc[i].src) { el.src = sc[i].src; } else { el.textContent = sc[i].textContent; }
        document.body.appendChild(el);
      }
    })
    .catch(function(e){
      var box = document.getElementById("wolf-content");
      if (box) box.innerHTML = '<div style="padding:20px;color:#B91C1C">Ошибка загрузки: '
        + (e && e.message ? e.message : "") + '</div>';
    });
})();
</script>
""".replace("__APPID__", str(app_id))
    try:
        from blocks.dashboard.pipeline import pipeline_visual
        frame = frame.replace("__PIPELINE__", pipeline_visual(app_id))
    except Exception:
        frame = frame.replace("__PIPELINE__", "")
    return render(title, "dashboard", frame)


@bp.route("/applications/<int:app_id>/view")
@login_required
def app_view(app_id: int):
    a = db.application_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))
    # === BLOCK 0: ранний выход (loader frame) ===
    if not request.args.get("full"):
        return _app_loader_frame(app_id, "Заявка #" + str(app_id))
    if request.args.get("saved"):
        flash("Значения документа сохранены — документ соберётся заново при следующем просмотре PDF", "ok")
    # Автоматический take убран — заявка остаётся "new" во входящих,
    # пока админ сам не нажмёт "Взять в работу"
    a = db.application_get(app_id)

    # === BLOCK 1: загрузка контекста (клиент, документы, сводка) ===
    client = db.client_get(a["client_id"]) or {}
    client_id_for_originals = a["client_id"]
    docs = db.application_documents(app_id)
    summary = db.application_documents_summary(app_id) if hasattr(db, 'application_documents_summary') else None

    # АВТО-ГЕНЕРАЦИЯ PDF на заходе админа ОТКЛЮЧЕНА.
    # Каждый визит на /applications/<id>/view запускал build_pending_async,
    # что пересобирало все pending-документы в фоне и порождало расхождение
    # «комплект на Диске старше рендеров на N минут»: out/ собирает только воркер.
    # Сборка теперь идёт ТОЛЬКО из трёх мест: кнопка «↻ Пересобрать» админа,
    # кнопка «Взять в работу» (старт прогона), автоцикл воркера.
    # Если нужно дозаполнить pending-документы после правки переменных —
    # жмём «↻ Пересобрать» в карточке.

    # === BLOCK 2: статус, менеджер, продукт, ссылка на Drive ===

    status_label = {"new": ("новая", "amber"), "in_progress": ("в работе", "blue"),
                    "ready": ("готова", "ok"), "sent": ("отправлена", "ok"),
                    "closed": ("закрыта", "muted"), "error": ("ошибка", "bad")}.get(
                        a["status"], (a["status"], ""))

    manager = db.q1(
        """SELECT bm.telegram_id, bm.full_name, bm.username
             FROM bot_managers bm WHERE bm.id=?""",

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
            '<a class="from-write-btn" target="_blank" rel="noopener" '
            'href="' + manager_tg_url + '" title="Написать менеджеру в Telegram">'
            '✉️ ' + manager_label + '</a>'
        )
    else:
        manager_btn = '<span class="from-value">' + manager_label + '</span>'

    product = db.q1("SELECT name, code FROM products WHERE id=?", (a["product_id"],)) if a.get("product_id") else None
    product_label = (product["name"] if product else a.get("product_name") or "—")
    product_code = (product["code"] if product else "—")

    drive_url = (a.get("gdrive_url") or client.get("gdrive_folder_url") or "").strip()

    # Ключи, которые уже показаны в других местах карточки (продукт, комментарий,
    # ссылка на Drive, цена) — в таблице «как пришло в заявке» их не дублируем.
    _SHOWN_ELSEWHERE = {"product", "product_name", "product_id", "price", "price_idr",
                        "comment", "comments", "_raw_text", "gdrive_url",
                        "gdrive_folder_url", "source_channel", "record_kind"}
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
                raw_payload_rows.append((str(k), "" if v is None else human_value(str(v))))
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

    # === BLOCK 3: банк клиента и сырой payload (как пришло в заявке) ===
    client_bank = ""
    # --- банк клиента для фильтрации банковских справок ---
    # Приоритет: карточка клиента (clients.bank_name) → raw_payload заявки.
    # clients.bank_name заполняется автоматически при разборе Google Drive.
    client_bank = ""
    try:
        _cl_row = db.q1("SELECT bank_name FROM clients WHERE id=?",
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
        non_bank_kw = ("work_agreement", "contract", "cv", "statement_letter", "d12", "wna")
        if any(k in c for k in non_bank_kw):
            return True
        if any(k in cl for k in ("т-банк", "t-bank", "tbank", "тинькофф", "tinkoff")):
            return any(k in c for k in ("tbank", "t-bank", "тинькофф", "tinkoff"))
        if any(k in cl for k in ("сбер", "sber")):
            return any(k in c for k in ("sber", "сбер", "sberbank"))
        return True

    templates_all = db.q(
        """SELECT t.id, t.code, t.title, t.pages, t.html_path, t.doc_index,
                  pd.slot_code, COALESCE(pd.is_default, 0) AS is_default
             FROM product_documents pd
             JOIN templates t ON t.id=pd.template_id
            WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged') ORDER BY COALESCE(t.doc_index, 999), pd.sort_order, t.id""",
        (a["product_id"],)) if a.get("product_id") else []
    # Слот = обязательный документ; варианты (банк, формат CV, офис иммиграции) — внутри слота
    _slots = {}
    for _t in templates_all:
        _slots.setdefault(_t["slot_code"] or ("doc_" + str(_t["id"])), []).append(_t)
    docs_in_product = []
    for _slot, _rows in _slots.items():
        _pick = next((_r for _r in _rows if _bank_match(_r["code"])), None)
        if _pick is None:
            _pick = next((_r for _r in _rows if _r["is_default"]), _rows[0])
        _pick = dict(_pick)
        _pick["variants"] = _rows
        docs_in_product.append(_pick)
    adoc_by_tpl = {d["template_id"]: d for d in docs}

    # Документы в 2 колонки: список слева + iframe справа
    doc_items_html = ""
    for t in docs_in_product:
        ad = adoc_by_tpl.get(t["id"])
        status = ad["status"] if ad else "новый"
        pdf_name = ""
        if ad and ad.get("pdf_path"):
            pdf_name = Path(ad["pdf_path"]).name
        # есть ли оригинал клиента для этого типа документа
        has_original = bool(_find_original_file(client_id_for_originals, t["code"])) \
            if client_id_for_originals else False
        is_ok = status in ("verified", "sent")
        ok_btn_class = "btn-ok-active" if is_ok else "btn-ok-idle"
        ok_btn_label = ("✓ Проверен" if is_ok else "☐ Отметить Ок")
        status_class = {
            "verified": "ok", "sent": "ok", "filled": "amber",
            "error": "bad", "pending": "grey", "rejected": "rej",
        }.get(status, "grey")
        status_label_txt = {"verified": "проверен", "sent": "отправлен", "filled": "заполнен",
                            "pending": "ожидает", "draft": "черновик",
                            "rejected": "не нужен"}.get(status, status)
        # чего не хватает этому документу: считается по тем же значениям, что уходят в PDF
        _miss = doc_missing_fields(app_id, t["id"])
        _miss_txt = ", ".join(_miss)
        _fill_badge = ('<span class="badge fill-ok" title="Все поля документа заполнены">\u2705 все поля заполнены</span>'
                       if not _miss else
                       '<span class="badge fill-warn" title="Не заполнено: ' + _miss_txt + '">'
                       '\u26a0\ufe0f не заполнено полей: ' + str(len(_miss)) + '</span>')

        doc_items_html += (
            '<li class="doc-row" data-pdf-name="' + pdf_name + '"'
            ' data-tpl-id="' + str(t["id"]) + '"'
            ' data-has-original="' + ("1" if has_original else "0") + '">'
            '<div class="doc-name">' + ('<span class="check-ok">✓</span>' if is_ok else "") + ' '
            + '<span class="doc-no">№' + str(t.get("doc_index") or t["id"]) + '</span> ' + t["title"]
            + '<div class="doc-meta">'
            + ('<select class="doc-variant" data-slot="' + str(t.get("slot_code") or "") + '">'
               + ''.join('<option value="' + str(_v["id"]) + '"'
                         + (' selected' if _v["id"] == t["id"] else '') + '>' + _v["title"] + '</option>'
                         for _v in t.get("variants", []))
               + '</select> ' if len(t.get("variants", [])) > 1 else '')
            + str(t["pages"] or 0) + ' стр. · '
            + '<span class="badge ' + status_class + '">' + status_label_txt + '</span> '
            + _fill_badge
            + ('<span class="badge orig-badge" style="margin-left:4px;background:#E0F2FE;color:#075985">📁 есть оригинал</span>' if has_original else "")
            + '</div></div>'
            '<div class="doc-actions">'
            '<button type="button" class="doc-btn doc-view" data-pdf="' + pdf_name + '" '
            'data-tpl-id="' + str(t["id"]) + '" '
            + ' title="Показать документ с данными клиента">👁</button>'
            '<a class="doc-btn" href="/templates/' + str(t["id"]) + '?app=' + str(app_id) + '" title="Редактировать документ заявки" target="_blank" rel="noopener">\u270f\ufe0f</a>'
            '<button type="button" class="doc-btn doc-paper" '
            'data-paper="' + ('/templates/file/renders/' + pdf_name if pdf_name else '') + '" '
            'data-tpl-id="' + str(t["id"]) + '" '
            + ' title="Посмотреть PDF поверх экрана">\U0001f4c4</button>'
            '<div class="verdict-pair">'
            '<button type="button" class="doc-btn verdict-btn verdict-yes ' + ('is-on' if is_ok else '') + (' is-locked' if (_miss and not is_ok) else '') + '" '
            'data-verify-app="' + str(app_id) + '" data-verify-tpl="' + str(t["id"]) + '" '
            + ('disabled ' if (_miss and not is_ok) else '')
            + 'title="' + ('Проверен. Нажмите, чтобы снять проверку' if is_ok else
                           ('Нельзя подтвердить: не заполнено — ' + _miss_txt if _miss else 'Проверен — документ согласован')) + '">'
            + '\u2713</button>'
            '<button type="button" class="doc-btn verdict-btn verdict-no ' + ('is-on' if status == 'rejected' else '') + '" '
            'data-reject-app="' + str(app_id) + '" data-reject-tpl="' + str(t['id']) + '" '
            'title="' + ('Не нужен. Нажмите, чтобы вернуть в комплект' if status == 'rejected'
                          else 'Не нужен — исключить документ из комплекта') + '">'
            + '\u2715</button>'
            '</div>'
            '</div>'
            '</li>'
        )

    # Готовность к отправке. Считаем по ПАКЕТУ ПРОДУКТА: одна позиция пакета = один тип
    # документа. Для C1 это только банковская справка, поэтому три файла в папке заявки
    # (варианты банков вперемешку) не должны превращаться в «проверено 1 из 3».
    _send_sum = db.application_doc_summary(app_id) or {}
    _slot_by_tpl = {}
    _pkg_slots = []
    _pid = a.get("product_id") if isinstance(a, dict) else (a["product_id"] if "product_id" in a.keys() else None)
    if _pid:
        for _r in db.q("SELECT template_id, slot_code FROM product_documents WHERE product_id=?", (_pid,)):
            _sc = _r["slot_code"] or ("tpl_" + str(_r["template_id"]))
            _slot_by_tpl[_r["template_id"]] = _sc
            if _sc not in _pkg_slots:
                _pkg_slots.append(_sc)
    _checked_slots = set()
    for _d in docs:
        _sl = _slot_by_tpl.get(_d["template_id"]) or ("tpl_" + str(_d["template_id"]))
        # в зачёт идёт и «проверен», и «не нужен» — администратор так или иначе решил по документу
        if _d.get("status") in ("verified", "sent", "rejected"):
            _checked_slots.add(_sl)
    _checked = len(_checked_slots)
    _total = len(_pkg_slots) if _pkg_slots else (len({(_slot_by_tpl.get(_d["template_id"]) or ("tpl_" + str(_d["template_id"]))) for _d in docs}) or 0)
    # Незаполненные поля блокируют отправку только у НЕподтверждённых документов:
    # галочка означает, что админ сверил документ и зафиксировал его значения.
    _send_missing = sorted({m for _d in docs
                            if (_d.get("status") or "") not in ("verified", "sent", "rejected")
                            for m in doc_missing_fields(app_id, _d["template_id"])})
    # === BLOCK 5: проверка готовности отправки (согласовано N из M, нет ли незаполненных полей) ===
    _blockers = []
    if _checked < _total:
        _blockers.append("согласовано " + str(_checked) + " из " + str(_total) + " документов")
    if _send_missing:
        _blockers.append("не заполнены поля: " + ", ".join(_send_missing[:6])
                         + (" и ещё " + str(len(_send_missing) - 6) if len(_send_missing) > 6 else ""))
    _send_ready = not _blockers
    send_state = (
        '<div class="send-state ok">\u2705 Все документы согласованы — можно отправлять на Google Диск</div>'
        if _send_ready else
        '<div class="send-state warn">\u26d4 Отправить нельзя: ' + "; ".join(_blockers) + '</div>'
    )
    # === BLOCK 5a: явная кнопка «Запустить обработку» на странице заявки ===
    # Работает даже при глобальной паузе автоматики: ручной запуск — независимый путь.
    _qstate = _queue_state(app_id)
    _qpos = _queue_positions().get(int(app_id)) if _qstate == "queued" else None
    _launch_btn = ""
    if _qstate not in ("running",):
        if _qstate == "paused":
            _launch_btn = (
                '<button type="button" class="ibtn go" id="launch-btn" '
                'data-act="start" data-app="' + str(app_id) + '" '
                'title="Снять с паузы и поставить в очередь">▶ Возобновить обработку</button>'
            )
        elif _qstate == "queued":
            _launch_btn = (
                '<button type="button" class="ibtn pause" id="launch-btn" '
                'data-act="pause" data-app="' + str(app_id) + '" '
                'title="Заявка уже в очереди №' + str(_qpos or "?") + ' — можно поставить на паузу">'
                '\u23f8 В очереди №' + str(_qpos or "?") + ' — на паузу</button>'
            )
        else:
            _launch_btn = (
                '<button type="button" class="ibtn go" id="launch-btn" '
                'data-act="start" data-app="' + str(app_id) + '" '
                'title="Явный запуск обработки этой заявки">\U0001f680 Запустить обработку</button>'
            )
    launch_panel = (
        '<div class="launch-panel" style="margin:10px 0;display:flex;gap:8px;align-items:center;'
        'padding:10px 12px;background:#F8FAF9;border:1px solid #DCEEE2;border-radius:8px">'
        + _launch_btn +
        '<span style="font-size:12px;color:#6B7C70">'
        'Эта кнопка работает и при глобальной паузе автоматики — действие записывается в лог.'
        '</span></div>'
    ) if _launch_btn else ""

    all_products = db.q("SELECT id, code, name FROM products ORDER BY id")
    product_select = ""
    # === BLOCK 6: селектор смены продукта и скан Google Drive ===
    if all_products:
        opts = "".join(
            '<option value="' + str(p["id"]) + '"'
            + (' selected' if p["id"] == a.get("product_id") else '')
            + '>' + p["name"] + ' (' + p["code"] + ')</option>'
            for p in all_products
        )
        product_select = (
            '<form method="post" action="/applications/' + str(app_id) + '/change-product" style="margin:6px 0 0">'
            '<select name="product_id" onchange="this.form.submit()" '
            'style="width:100%;padding:6px 8px;border:1px solid #DCEEE2;border-radius:6px;font-size:12.5px;background:#fff">'
            + opts + '</select>'
            '</form>'
        )

    # === BLOCK 7 prep 2: рендер блока «Продукт + Google Drive» через views.py ===
    try:
        from blocks.dashboard.views import render_blocks as _render_blocks2
        _ctx_pd = {
            "app_id": app_id,
            "a": a,
            "product_label": product_label,
            "product_code": product_code,
            "product_select": product_select,
            "drive_btn": drive_btn,
        }
        _blocks_product_drive = _render_blocks2(_ctx_pd, "product_drive")
    except Exception:                                       # noqa: BLE001
        _blocks_product_drive = ""

    try:
        _drive_scan = db.q1("SELECT status, docs_total, docs_done, note, created_at FROM drive_scans WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))
    except Exception:
        _drive_scan = None
    if _drive_scan:
        _st = (_drive_scan["status"] or "").lower()
        if _st == "ok":
            _mark = '<span class="drive-mark ok" title="Документы с Google Drive прочитаны автоматически">✅ разобрано ' + str(_drive_scan["docs_done"] or 0) + ' из ' + str(_drive_scan["docs_total"] or 0) + '</span>'
        elif _st == "running":
            _mark = '<span class="drive-mark run" title="Разбор выполняется">⏳ разбор идёт…</span>'
        else:
            _mark = '<span class="drive-mark fail" title="' + (_drive_scan["note"] or "Автоматическое прочтение не выполнено") + '">❗ не разобрано</span>'
    else:
        _mark = '<span class="drive-mark">ещё не разбиралось</span>'
    # Перечень того, что реально лежит в папке Google Drive (по свежему разбору).
    # Устаревшие отметки автопроверки не показываем — они противоречат разбору.
    try:
        import json as _json
        _rk = db.q1("""SELECT payload FROM drive_scans
                       WHERE application_id=? AND payload IS NOT NULL
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
        _mark += ('<span class="drive-mark ok" title="Что лежит в папке Google Drive">'
                  '\U0001f4c1 в наличии ' + str(len(_payload)) + ': ' + _listing + '</span>')
        if _has_pass:
            _mark += '<span class="drive-mark ok" title="Паспорт клиента прочитан">✅ паспорт прочитан</span>'
        else:
            _mark += '<span class="drive-mark fail" title="В папке нет паспорта клиента">⚠️ паспорта в папке нет</span>'
    drive_btn = (
        '<div class="drive-actions">'
        '<a href="' + drive_url + '" target="_blank" rel="noopener" class="drive-btn">'
        '📂 Google Drive клиента</a>'
        '<button type="button" class="drive-scan-btn" title="Прочитает документы из папки Google Drive заявки и вытащит значения. Если разбор уже сделан — скажет об этом" '
        'onclick="wolfDriveScan(' + str(app_id) + ', this)">'
        '🧠 Разобрать документы (нейросеть)</button>'
        '<button type="button" class="drive-see-btn" onclick="wolfDriveShow(' + str(app_id) + ')">'
        '🔍 Что вытащено</button>'
        '<button type="button" class="af-all-btn" title="Соберёт все документы заявки по правилам и покажет их в окне просмотра" '
        'onclick="wolfAutofillAll(' + str(app_id) + ', this)">'
        '⚡ Заполнить автоматически</button>' 
        + _mark
        + '</div><div id="drive-scan-note" style="font-size:12px;color:#3A4A40;margin-top:6px"></div>'
        if drive_url else '<span class="muted" style="font-size:12.5px">ссылка не указана</span>'
        + '<button type="button" class="drive-scan-btn" onclick="wolfDriveScan(' + str(app_id) + ')">🧠 Разобрать документы (нейросеть)</button>'
    )

        # Продукт добавляем первым с жёлтой подсветкой
    extra_rows = []
    # Данные, вытащенные из документов Google Drive — администратор должен видеть,
    # что именно распознано, и сверить с первоисточником.
    try:
        _cd = db.q1("SELECT * FROM clients WHERE id=(SELECT client_id FROM applications WHERE id=?)",
                    (app_id,)) or {}
    except Exception:
        _cd = {}
    # комментарий клиента/менеджера — держим наверху блока и выделяем ярко
    try:
        _rp = db.q1("SELECT raw_payload FROM applications WHERE id=?", (app_id,)) or {}
        import json as _json
        _cmt = str((_json.loads(_rp.get("raw_payload") or "{}") or {}).get("comment") or "").strip()
    except Exception:
        _cmt = ""
    if _cmt:
        extra_rows.append('<tr class="kv-comment-row"><td class="kv-key kv-key-comment">'
                          '💬 Комментарий заявки</td><td class="kv-val kv-val-comment">'
                          + _cmt + '</td></tr>')
    _DRIVE_FIELDS = [("full_name_latin", "ФИО латиницей"), ("surname", "Фамилия"),
                     ("name", "Имя"), ("patronymic", "Отчество"),
                     ("birth_date", "Дата рождения"), ("birth_place", "Место рождения"),
                     ("passport_number", "Номер паспорта"), ("citizenship", "Гражданство"),
                     ("address_live", "Адрес проживания"), ("phone", "Телефон"),
                     ("email", "E-mail"), ("bank_name", "Банк")]
    for _f, _lbl in _DRIVE_FIELDS:
        _v = str(_cd.get(_f) or "").strip()
        if not _v:
            continue
        extra_rows.append('<tr class="kv-drive-row"><td class="kv-key kv-key-drive">'
                          + _lbl + '</td><td class="kv-val">' + _v
                          + ' <span class="kv-src" title="Значение распознано из документов Google Drive">из документов</span></td></tr>')
    if product:
        extra_rows.append(
            '<tr class="kv-product-row"><td class="kv-key kv-key-product">'
            'Продукт</td>'
            '<td class="kv-val kv-val-product">' + product_label + ' '
            '<span class="kv-product-code">· код ' + product_code + '</span></td></tr>'
        )
    elif a.get("product_id"):
        extra_rows.append(
            '<tr class="kv-product-row"><td class="kv-key kv-key-product">'
            'Продукт</td>'
            '<td class="kv-val kv-val-product">ещё не выбран (ID ' + str(a["product_id"]) + ')</td></tr>'
        )
    if raw_payload_rows:
        _raw_payload_html = (
            '<table class="kv-table">'
            + ''.join(extra_rows)
            + ''.join('<tr><td class="kv-key">' + label_for(k) + '</td><td class="kv-val">' + v + '</td></tr>' for k, v in raw_payload_rows if k.lower() not in _SHOWN_ELSEWHERE)
            + '</table>'
        )
    elif raw_payload_text or extra_rows:
        _raw_payload_html = (
            '<table class="kv-table">'
            + ''.join(extra_rows)
            + (''.join('<tr><td class="rp-k">' + label_for(k) + '</td><td class="rp-v">' + v + '</td></tr>' for k, v in raw_payload_rows if k.lower() not in _SHOWN_ELSEWHERE) if raw_payload_rows else '')
            + (('<tr><td colspan="2" class="rp-note">' + ' · '.join(raw_notes[:6]) + '</td></tr>') if raw_notes else '')
            + '</table>'
        )
    else:
        _raw_payload_html = '<div class="muted">Нет данных</div>'

    # === BLOCK 4: комментарий менеджера ===
    # ── комментарий менеджера: необязательное, но важное поле (ускорение, партнёр, сроки) ──
    _comment_txt = ""
    try:
        _rp_c = json.loads(a["raw_payload"]) if a.get("raw_payload") else {}
        _comment_txt = str(_rp_c.get("comment") or "").strip()
    except Exception:
        _comment_txt = ""
    _comment_html = ""
    if _comment_txt:
        _safe_comment = _comment_txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        _comment_html = ('<div class="app-comment-flash">'
                         '<span class="acf-label">\U0001f4ac Комментарий менеджера</span>'
                         '<div class="acf-text">' + _safe_comment + '</div></div>')

    # окно с полным текстом заявки (открывается из заголовка блока 3)
    _text_modal_html = modal("app-text-modal", "\U0001f4c4 Текст заявки",
                             '<pre class="app-text-pre" id="app-text-pre">Загрузка…</pre>')

    # Подставлены ли данные из Google Drive? Если нет — на просмотре документа
    # показываем красный водяной знак, но сам документ открывать не запрещаем.
    _scan = db.q1("SELECT status, docs_done, note FROM drive_scans "
                  "WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,)) or {}
    _cl_row = db.q1("SELECT surname, full_name_latin, passport_number, birth_date "
                    "FROM clients WHERE id=(SELECT client_id FROM applications WHERE id=?)",
                    (app_id,)) or {}
    _has_client_data = bool((_cl_row.get("full_name_latin") or "").strip()
                            or ((_cl_row.get("surname") or "").strip()
                                and (_cl_row.get("passport_number") or "").strip()))
    _scan_ok = (str(_scan.get("status") or "").lower() == "ok") and int(_scan.get("docs_done") or 0) > 0
    # Знак показываем, когда данные клиента НЕ распознаны (нет ФИО и паспорта).
    # Если данные есть (из Drive или введены вручную) — документ чистый.
    _data_ready = bool(_has_client_data)
    _wm_note = ("Google Drive не разобран" if not _scan_ok
                else "Данные клиента не распознаны")
    _wm_html = ("" if _data_ready else
                '<div class="paper-watermark" id="paper-watermark">'
                '<div class="paper-watermark-text">ДАННЫЕ НЕ ПОДСТАВЛЕНЫ'
                '<span class="paper-watermark-sub">' + _wm_note + '</span></div></div>')
    _data_ready_js = "true" if _data_ready else "false"

    # === BLOCK 7 prep: сборка именованных HTML-блоков верхней части страницы.
    # Позволяет расширять страницу заявки новыми блоками в views.py без правки тела app_view.
    _blocks_top = ""
    try:
        from blocks.dashboard.views import render_blocks as _render_blocks
        _ctx = {
            "app_id": app_id,
            "client": client,
            "a": a,
            "status_label": status_label,
            "manager_btn": manager_btn,
            "_comment_html": _comment_html,
        }
        _blocks_top = _render_blocks(_ctx, "comment", "header", "intro")
    except Exception:                                       # noqa: BLE001
        _blocks_top = ""

    # _blocks_product_drive собирается ПОЗЖЕ — после определения product_* и drive_btn.
    _blocks_product_drive = ""
    # placeholder: будет заполнено после определения product_select и drive_btn

    body = """
<div class="app-card-green">

# === BLOCK 7: HTML-тело страницы (шапка, этапы сбора, документы, визуализатор) ===
""" + _blocks_top + """
""" + _blocks_product_drive + """
<details class="ui-card stage-block stage-fold" id="stage-3" open>
  <summary class="ui-card-head">
    <span class="stage-no">3</span><span class="ui-card-emoji">📋</span>
    Входные данные заявки <span class="ui-card-meta">""" + str(len(raw_payload_rows)) + """ полей</span>
    <button type="button" class="app-text-btn" data-app-text="1"
            title="Полный текст заявки: как её прислал менеджер — уходит на Google Диск вместе с документами">\U0001f4c4 Текст заявки</button>
    <span class="stage-fold-hint">свернуть</span><span class="chev">›</span>
  </summary>
  <div class="ui-card-body">
    """ + _raw_payload_html + """
  </div>
</details>

""" + _text_modal_html + """
<div class="stage-title">Документы</div>
<div class="docs-section">
  <div class="docs-list-wrap stage-block">
    <div class="docs-list-head">
      <span class="stage-no">4</span> 📑 Перечень документов <span class="docs-count">· """ + str(len(docs_in_product)) + """</span>
    </div>
    <ul class="docs-list">
      """ + (doc_items_html or '<li class="muted">Нет документов</li>') + """
    </ul>
  </div>
  <div class="docs-viewer stage-block" id="docs-viewer">
    <div class="docs-list-head">
      <span class="stage-no">5</span> 🖥 Просмотр готового документа
      <span class="viewer-fill" id="viewer-fill"></span>
    </div>
    <div class="viewer-tabs" id="viewer-tabs" style="display:none;gap:8px;align-items:center;margin:8px 0">
      <span class="vtab-name" id="viewer-doc-name" style="font-weight:600"></span>
    </div>
    <div class="docs-viewer-empty" id="docs-viewer-empty">
      <div style="font-size:48px;opacity:.4;margin-bottom:8px">\U0001f4c4</div>
      <div>Нажмите «👁» рядом с документом,<br>чтобы открыть готовый документ</div>
    </div>
    """ + _wm_html + """
    <div class="app-paper-wrap" id="app-paper-wrap" style="display:none">
      <iframe id="app-paper-frame" title="Готовый документ"></iframe>
    </div>
    <div class="zp-preview" data-zoom-pan><div id="app-preview-stage" class="html-stage"></div></div>
    <div class="docs-viewer-err" id="docs-viewer-err" style="display:none">
      <div style="font-size:40px;opacity:.5;margin-bottom:8px">🚫</div>
      <div id="docs-viewer-err-text">Документ недоступен</div>
      <div class="muted" style="font-size:12px;margin-top:6px" id="docs-viewer-err-hint"></div>
    </div>
  </div>
</div>

<form method="post" action="/applications/""" + str(app_id) + """/send" class="stage-block send-block">
  <div class="stage-no">6</div>
  """ + launch_panel + send_state + """
  <div class="send-hint">На Google Диск уйдут <b>все подтверждённые документы</b> и <b>текст заявки</b>.</div>
  """ + ('' if _send_ready else '<div class="send-hint send-todo">Чтобы кнопка стала активной, у каждого документа блока 4 нажмите <b>✓ Проверен</b> (документ нужен и согласован) или <b>✕</b> (документ не нужен). Счётчик блока 6 считает и то, и другое.</div>') + """
  <button class="send-final-btn" type="submit\"""" + ('' if _send_ready else ' disabled') + """
          onclick="return confirm('Отправить документы в Google Drive и уведомить менеджера?')"
          """ + ('' if _send_ready else 'disabled ') + 'title="' + ('Отправить документы в Google Drive'
                 if _send_ready else 'Сначала согласуйте документы: проверьте или отмените каждый') + '\">'"""
    📤 Отправить документы на Google Drive
  </button>
</form>

</div>

<script>
(function() {
  const APP_ID = """ + str(app_id) + """;
  const DATA_READY = """ + _data_ready_js + """;   // данные из Google Drive подставлены?
  const stage = document.getElementById('app-preview-stage');
  const empty = document.getElementById('docs-viewer-empty');
  const err = document.getElementById('docs-viewer-err');
  const errText = document.getElementById('docs-viewer-err-text');
  const errHint = document.getElementById('docs-viewer-err-hint');
  const docName = document.getElementById('viewer-doc-name');

  function hideAll() {
    if (err) err.style.display = 'none';
  }
  function showErr(text, hint) {
    hideAll();
    if (errText) errText.textContent = text;
    if (errHint) errHint.textContent = hint || '';
    if (err) err.style.display = 'block';
  }
  /* HTML-лист с реальными данными — тот же контейнер и тот же вид, что в конструкторе */
  var curTpl = '', savedNodes = null, busyTr = false;
  function showToolbar(on) {
    var tb = document.getElementById('doc-toolbar');
    if (tb) tb.style.display = on ? 'flex' : 'none';
  }
  function note(id, txt) { var el = document.getElementById(id); if (el) el.textContent = txt || ''; }
  function setBtn(sel, attr, val) {
    var all = document.querySelectorAll('.doc-toolbar ' + sel);
    for (var i = 0; i < all.length; i++) all[i].classList.toggle('is-on', all[i].dataset[attr] === val);
  }
  function syncWatermark() {
    /* Знак «данные не подставлены»: держим его видимым над превью, пока этап 2 не пройден */
    var wm = document.getElementById('paper-watermark');
    if (!wm) return;
    var viewer = document.querySelector('.docs-viewer');
    if (!viewer) return;
    if (typeof DATA_READY !== 'undefined' && !DATA_READY) {
      if (wm.parentNode !== viewer) viewer.appendChild(wm);
      wm.style.display = 'flex';
      viewer.classList.add('has-watermark');
    } else {
      wm.style.display = 'none';
      viewer.classList.remove('has-watermark');
    }
  }

  function loadRemote(url, what) {
    hideAll();
    if (stage) stage.innerHTML = '<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Загружаю ' + (what || '') + '…</div>';
    fetch(url, { credentials: 'same-origin' })
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(function(h) {
        if (!stage) return;
        stage.innerHTML = h;
        if (window.zpScan) window.zpScan();
        /* Режимы PDF (оригинал клиента, чистый/размеченный пример, PDF-шаблон):
           растягиваем окно визора, чтобы страницы были видны целиком.
           innerHTML — из ответа нашего же сервера (внутренняя админка). */
        if (stage.classList) {
          var isPdf = /pdf-page-img/.test(h);
          stage.classList.toggle('is-pdfmode', isPdf);
          var v = document.querySelector('.rv-view');
          if (v && v.classList) v.classList.toggle('is-orig', isPdf);
        }
      })
      .catch(function() { showErr('Этот вид недоступен для документа', 'Попробуйте другой режим просмотра'); });
  }
  /* Готовый сформированный документ показываем сразу — PDF с данными клиента.
     Сравнение с бланком и разметку менеджер в заявке не делает: это делается один раз в настройках. */
  function showPaper(pdfName) {
    var wrap = document.getElementById('app-paper-wrap');
    var fr = document.getElementById('app-paper-frame');
    var zp = document.querySelector('.docs-viewer .zp-preview');
    if (!wrap || !fr) return false;
    fr.src = '/templates/file/renders/' + pdfName;
    wrap.style.display = 'block';
    if (zp) zp.style.display = 'none';
    var mt = document.getElementById('docs-viewer-empty');
    if (mt) mt.style.display = 'none';
    return true;
  }
  function openDoc(tplId, pdfName) {
    hideAll();
    if (!tplId) { showErr('Шаблон документа не найден', ''); return; }
    curTpl = tplId; savedNodes = null;
    var wrap = document.getElementById('app-paper-wrap');
    var zp = document.querySelector('.docs-viewer .zp-preview');
    if (pdfName) { showPaper(pdfName); return; }
    /* PDF ещё не сформирован — показываем лист с данными заявки */
    if (wrap) wrap.style.display = 'none';
    if (zp) zp.style.display = 'block';
    if (stage) stage.innerHTML = '<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Открываю документ…</div>';
    fetch('/applications/' + APP_ID + '/doc/' + tplId + '/html', { credentials: 'same-origin' })
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
  var TR_FIELDS = ['position', 'profession', 'occupation', 'job', 'job_title',
                   'job_and_position', 'position_title', 'profession_title', 'duties',
                   'position_name', 'work_position', 'speciality', 'specialty',
                   /* кусочки резюме: описание, обязанности, навыки, образование, должности —
                      их администратор читает по-русски, а в документ уходит английский */
                   'cv_summary', 'cv_job1_bullets', 'cv_job2_bullets', 'cv_job3_bullets',
                   'cv_job1_title', 'cv_job2_title', 'cv_job3_title',
                   'cv_skills_hard', 'cv_skills_soft', 'cv_skills_tools',
                   'cv_education_degree', 'cv_education_note',
                   /* договор работы с организацией: должность и обязанности */
                   'services_list'];
  function textNodes() {
    var pv = [];
    try {
      var el = document.getElementById('app-values');
      if (el) { var m = JSON.parse(el.textContent || '{}'); Object.keys(m).forEach(function(k) { var v = String(m[k] || '').trim(); if (v) pv.push(v); }); }
    } catch (e) { pv = []; }
    var out = [], w = document.createTreeWalker(stage, NodeFilter.SHOW_TEXT, null), n;
    while (n = w.nextNode()) {
      var p = n.parentElement;
      if (!p) continue;
      var tag = (p.nodeName || '').toLowerCase();
      if (tag === 'script' || tag === 'style' || tag === 'title') continue;
      var holder = p.closest('.var-val');
      if (holder) {
        var nm = (holder.dataset.var || '').toLowerCase();
        /* данные клиента переводим тоже: промпт сохраняет имена, номера и адреса */
      }
      var v = (n.nodeValue || '').trim();
      if (v.length < 2 || v.indexOf('{{') >= 0) continue;
      if (!/[A-Za-z]{3}/.test(v)) continue;
      /* значения переменных тоже переводим: нужен полный русский текст документа */
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
    uniq = uniq.slice(0, 400);
    note('ls-note', '⏳ перевожу ' + uniq.length + ' строк…');
    fetch('/templates/' + curTpl + '/translate', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ lines: uniq, cache_only: false })
    }).then(function(r) { return r.json(); }).then(function(j) {
      busyTr = false;
      if (!j || !j.ok) { note('ls-note', 'ошибка перевода'); return; }
      var m = {};
      uniq.forEach(function(s, i) { m[s] = (j.ru || [])[i] || s; });
      textNodes().forEach(function(n) { var k = n.nodeValue.trim(); if (m[k]) n.nodeValue = n.nodeValue.replace(k, m[k]); });
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
    var first = document.querySelector('.doc-row');
    if (!first) return;
    var btn = first.querySelector('.doc-view');
    if (btn && !btn.disabled) btn.click();
  }
  document.addEventListener('click', function(e) {
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
        loadRemote('/applications/' + APP_ID + '/original-pages/' + curTpl, 'оригинал клиента');
      } else {
        var what = m === 'source' ? 'PDF-шаблон' : (m === 'marked' ? 'размеченный пример' : 'чистый пример');
        loadRemote('/templates/pdfview/' + curTpl + '?kind=' + m, what);
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
    /* кнопка «бумажка» — PDF поверх экрана, без перехода на другую страницу */
    if (t.closest('.doc-paper')) {
      var pb = t.closest('.doc-paper');
      curTpl = pb.dataset.tplId || curTpl;
      if (pb.dataset.paper) { openPaper(pb.dataset.paper); return; }
      note('drive-scan-note', '⏳ формирую PDF…');
      fetch('/applications/' + APP_ID + '/doc/' + pb.dataset.tplId + '/ensure-pdf',
            { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          note('drive-scan-note', '');
          if (j && j.ok && j.pdf_name) {
            pb.dataset.paper = '/templates/file/renders/' + j.pdf_name;
            openPaper(pb.dataset.paper);
          } else { showErr('Не удалось сформировать PDF', 'Проверьте, заполнены ли поля документа'); }
        })
        .catch(function() { note('drive-scan-note', ''); showErr('Не удалось сформировать PDF', ''); });
      return;
    }
    if (t.classList && t.classList.contains('doc-view')) {
      var r = e.target.closest('.doc-row');
      var tplId = (r && (r.dataset.tplId || '')) || '';
      var nm = r ? r.querySelector('.doc-name') : null;
      if (docName) docName.textContent = nm ? nm.textContent.split(String.fromCharCode(10))[0] : '';
      if (empty) empty.style.display = 'none';
      openDoc(tplId, '');   /* всегда HTML-лист с реальными данными клиента */
      /* индикатор: все поля заполнены (зелёный) или нет (красный) */
      var vf = document.getElementById('viewer-fill');
      if (vf) {
        var fb = r ? r.querySelector('.badge.fill-ok, .badge.fill-warn') : null;
        if (!fb) { vf.className = 'viewer-fill'; vf.textContent = ''; }
        else if (fb.classList.contains('fill-ok')) {
          vf.className = 'viewer-fill ok';
          vf.textContent = '✅ все поля заполнены';
        } else {
          vf.className = 'viewer-fill warn';
          vf.textContent = '⚠️ ' + fb.textContent.trim().replace('⚠️', '').trim();
        }
      }
      /* подсвечиваем документ, который сейчас в просмотре */
      document.querySelectorAll('.doc-view').forEach(function(b) { b.classList.remove('is-on'); });
      e.target.classList.add('is-on');
      document.querySelectorAll('.doc-row').forEach(function(rr) { rr.classList.remove('active'); });
      if (r) r.classList.add('active');
      return;
    }
  });
  function sendVariant(sel) {
    fetch('/applications/' + APP_ID + '/doc-variant', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ slot: sel.dataset.slot, template_id: sel.value })
    }).then(function() { location.reload(); })
      .catch(function() { location.reload(); });
  }
  document.addEventListener('change', function(e) {
    if (e.target.classList && e.target.classList.contains('doc-variant')) sendVariant(e.target);
  });
  /* ── «Бумажка»: PDF открывается поверх этого же экрана, никуда не уходим ── */
  var paperOv = null;
  function openPaper(url) {
    if (!url) return;
    if (!paperOv) {
      paperOv = document.createElement('div');
      paperOv.className = 'paper-overlay';
      paperOv.innerHTML = '<div class="paper-bar">'
        + '<span class="paper-name" id="paper-name"></span>'
        + '<button type="button" class="paper-dl" id="paper-dl">⬇ Скачать</button>'
        + '<button type="button" class="paper-big" id="paper-big">⤢ Во всё окно</button>'
        + '<button type="button" class="paper-ok" id="paper-ok">✓ Ок — документ проверен</button>'
        + '<button type="button" class="paper-close" id="paper-close">✕ Закрыть (Esc)</button></div>'
        + '<div class="paper-body"><div class="paper-stage" id="paper-stage">'
        + '<iframe id="paper-frame" title="PDF"></iframe>'
        + '</div></div>';
      document.body.appendChild(paperOv);
      paperOv.addEventListener('click', function(ev) {
        if (ev.target === paperOv || (ev.target.id === 'paper-close')) closePaper();
      });
      document.addEventListener('keydown', function(ev) { if (ev.key === 'Escape') closePaper(); });
    }
    document.getElementById('paper-frame').src = url;
    document.getElementById('paper-dl').onclick = function() { window.open(url, '_blank'); };
    document.getElementById('paper-name').textContent = decodeURIComponent(url.split('/').pop());
    var bigBtn = document.getElementById('paper-big');
    if (bigBtn) bigBtn.onclick = function() { window.open(url, '_blank'); };
    var okBtn = document.getElementById('paper-ok');
    if (okBtn) okBtn.onclick = function() {
      var tpl = curTpl;
      if (!tpl) { closePaper(); return; }
      okBtn.disabled = true; okBtn.textContent = '⏳ отмечаю…';
      fetch('/applications/' + APP_ID + '/doc/' + tpl + '/verify',
            { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
        .then(function() { closePaper(); location.reload(); })
        .catch(function() { closePaper(); location.reload(); });
    };
    var _stage = document.getElementById('paper-stage');
    var _wm = document.getElementById('paper-watermark');
    if (_wm && _stage) {
      _stage.appendChild(_wm);                       // переносим знак в окно просмотра
      _wm.style.display = DATA_READY ? 'none' : 'flex';
    }
    paperOv.classList.add('is-on');
    document.documentElement.style.overflow = 'hidden';
  }
  function closePaper() {
    if (!paperOv) return;
    paperOv.classList.remove('is-on');
    var f = document.getElementById('paper-frame');
    if (f) f.src = 'about:blank';
    document.documentElement.style.overflow = '';
  }
  /* подпись «свернуть/развернуть» у блока 3 */
  var s3 = document.getElementById('stage-3');
  if (s3) s3.addEventListener('toggle', function() {
    var h = s3.querySelector('.stage-fold-hint');
    if (h) h.textContent = s3.open ? 'свернуть' : 'развернуть';
  });

  /* обновление блока «готовность к отправке» без перезагрузки страницы */
  function refreshSendState() {
    // Лёгкий запрос: только состояние готовности, без рендера всей карточки.
    fetch('/applications/' + APP_ID + '/send-state', { credentials: 'same-origin' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (!d || !d.ok) return;
        var mine = document.querySelector('.send-state');
        if (mine) {
          mine.textContent = (d.state === 'ok' ? '\u2705 ' : '\u26d4 ') + d.hint;
          mine.className = 'send-state ' + (d.state || 'warn');
        }
        var btn = document.querySelector('.send-final-btn');
        if (btn) {
          btn.disabled = !d.can_send;
          btn.title = d.can_send ? 'Отправить документы в Google Drive'
                                 : 'Сначала согласуйте документы: проверьте или отмените каждый';
        }
        var todo = document.querySelector('.send-todo');
        if (todo && d.can_send) todo.remove();
      }).catch(function() {});
  }
  /* привести строку документа к состоянию: проверен / не нужен / просто заполнен */
  function applyVerdict(row, verified, rejected) {
    if (!row) return;
    var y = row.querySelector('.verdict-yes'), nbtn = row.querySelector('.verdict-no');
    if (y) y.classList.toggle('is-on', !!verified);
    if (nbtn) nbtn.classList.toggle('is-on', !!rejected);
    var nm = row.querySelector('.doc-name');
    if (nm) {
      var ck = nm.querySelector('.check-ok');
      if (verified && !ck) {
        ck = document.createElement('span'); ck.className = 'check-ok'; ck.textContent = '\u2713';
        nm.insertBefore(ck, nm.firstChild);
        nm.insertBefore(document.createTextNode(' '), ck.nextSibling);
      } else if (!verified && ck) { ck.remove(); }
    }
    var bd = row.querySelector('.badge');
    if (bd) {
      if (rejected) { bd.className = 'badge rej'; bd.textContent = 'не нужен'; }
      else if (verified) { bd.className = 'badge ok'; bd.textContent = 'проверен'; }
      else { bd.className = 'badge amber'; bd.textContent = 'заполнен'; }
    }
    row.classList.toggle('is-rejected', !!rejected);
  }
  /* ── Вердикт по документу: «✓» и «✕» — нажимаемые, взаимоисключающие ── */
  function postVerdict(url, btn) {
    var oldText = btn.textContent;
    btn.disabled = true;
    fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        btn.disabled = false;
        applyVerdict(btn.closest('.doc-row'), !!d.verified, !!d.rejected);
        refreshSendState();
      })
      .catch(function() { btn.disabled = false; btn.textContent = oldText; });
  }
  document.addEventListener('click', function(e) {
    if (!e.target || !e.target.closest) return;
    var y = e.target.closest('[data-verify-app]');
    if (y && !y.disabled) {
      e.preventDefault();
      postVerdict('/applications/' + y.getAttribute('data-verify-app')
                  + '/doc/' + y.getAttribute('data-verify-tpl') + '/verify', y);
      return;
    }
    var x = e.target.closest('[data-reject-app]');
    if (x && !x.disabled) {
      e.preventDefault();
      postVerdict('/applications/' + x.getAttribute('data-reject-app')
                  + '/doc/' + x.getAttribute('data-reject-tpl') + '/reject', x);
    }
  });
  /* -- Tekst zayavki: vsplyvayushcheye okno -- */
  document.addEventListener('click', function(e) {
    var b = e.target && e.target.closest ? e.target.closest('[data-app-text]') : null;
    if (!b) return;
    e.preventDefault();
    e.stopPropagation();
    var pre = document.getElementById('app-text-pre');
    if (pre) {
      pre.textContent = 'Zagruzka...';
      fetch('/applications/' + APP_ID + '/text-file', { credentials: 'same-origin' })
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
  display: inline-block; font-weight: 800; font-size: 13px; letter-spacing: .2px;
  color: #8A5B00; text-transform: uppercase; margin-bottom: 6px;
}
.app-comment-flash .acf-text { font-size: 15px; line-height: 1.45; color: #4A3200; font-weight: 600; }
.app-text-btn { text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }

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
.from-value { font-weight: 600; }
.from-write-btn {
  display: inline-flex; align-items: center; gap: 4px;
  background: #DCFCE7; color: #15803D; padding: 5px 10px;
  border-radius: 7px; font-weight: 600; font-size: 13px;
  text-decoration: none; border: 1px solid #86EFAC;
}
.from-write-btn:hover { background: #BBF7D0; }

.row.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; align-items: stretch; }
.row.two-col .kv-cell{display:flex;flex-direction:column;justify-content:flex-start;min-height:132px}
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
.verdict-pair { display: inline-flex; gap: 6px; align-items: center; margin-left: 2px; }
.verdict-btn { width: 34px; height: 30px; padding: 0; font-size: 15px; font-weight: 700;
               border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; }
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

.send-state { font-size:13px; font-weight:600; padding:8px 12px; border-radius:8px; margin:4px 0 8px; }
.send-state.ok { background:#DCFCE7; color:#166534; border:1px solid #86EFAC; }
.send-state.warn { background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; }
.send-final-btn[disabled] { opacity:.45; cursor:not-allowed; }
.drive-btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: #229ED9; color: #fff !important;
  padding: 8px 14px; border-radius: 8px;
  text-decoration: none; font-size: 13px; font-weight: 600;
  margin-top: 4px;
}
.drive-btn:hover { background: #1B7DB0; }

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
.kv-product-row td.kv-key-product { background:#FEF3C7 !important; color:#78350F !important; font-weight:700; }
.kv-product-row td.kv-val-product { background:#FFFBEB !important; color:#15803D !important; font-weight:700; font-size:14px; }
.kv-product-code { color:#6B7C70; font-weight:400; font-size:12px; margin-left:4px; }
.raw-payload-text { white-space:pre-wrap; word-break:break-word; font-size:13.5px;
                    font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                    background:#fff; border:1px solid #DCEEE2; border-radius:8px;
                    padding:10px; margin:0; line-height:1.5;
                    max-height:300px; overflow:auto; }

.check-ok { display:inline-flex; align-items:center; justify-content:center;
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
.doc-no { display:inline-block; font-size:11.5px; font-weight:800; color:#14532D; background:#E7F6EC; border:1px solid #BFE0CB; border-radius:6px; padding:1px 6px; margin-right:5px; }
.doc-meta { font-size:11px; color:#6B7C70; margin-top:3px; font-weight:400; }
.doc-actions { display:flex; gap:4px; flex-wrap:wrap; }
.doc-btn {
  background:#F4FAF6; border:1px solid #DCEEE2;
  border-radius:6px; padding:5px 9px; font-size:12px; font-weight:600;
  cursor:pointer; color:#15803D; text-decoration:none;
  display:inline-flex; align-items:center; gap:3px;
}
.doc-btn:hover { background:#E5F2EA; }
.btn-ok-idle { background:#FEF3C7; color:#78350F; border-color:#D97706; }
.btn-ok-idle:hover { background:#FDE68A; }
.btn-ok-active { background:#DCFCE7; color:#15803D; border-color:#16A34A; }

.docs-viewer .html-stage{width:794.5px;margin:0 !important;padding:0 !important;border:0 !important;background:#fff !important;transform-origin:top left;box-shadow:0 1px 6px rgba(0,0,0,.12)}
.docs-viewer .zp-preview{display:block;padding:0}
.docs-viewer .zp-tools{background:#fff;border:0;border-radius:8px;padding:6px 8px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between}
.docs-viewer { background:#E7EBEE; border:1px solid #DCEEE2; border-radius:10px;
               display:flex; flex-direction:column; align-items:stretch; justify-content:flex-start;
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
.stage-title { margin:16px 0 8px; padding:7px 12px; border-radius:9px; background:#EAF6EE;
               border:1px solid #C7E6CF; font-size:15px; font-weight:800; color:#14663A; }
.stage-block { position:relative; }
.stage-no { display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
            border-radius:50%; background:#14663A; color:#fff; font-size:12.5px; font-weight:800;
            margin-right:7px; flex:0 0 auto; vertical-align:middle; }
.send-block { display:flex; align-items:center; gap:10px; margin-top:16px; padding:10px 12px;
              background:#F4FAF6; border:1px solid #DCEEE2; border-radius:10px; }
.send-block .send-final-btn { flex:1; }
/* блок 3: компактнее и сворачивается */
#stage-3 .ui-card-head { display:flex; align-items:center; gap:8px; cursor:pointer; list-style:none; }
#stage-3 .ui-card-head::-webkit-details-marker { display:none; }
.stage-fold > summary .chev { margin-left:6px; color:#9AA3B2; font-size:18px; transition:transform .18s; }
.stage-fold[open] > summary .chev { transform:rotate(90deg); }
.stage-fold-hint { font-size:11.5px; color:#6B7C70; margin-left:auto; }
#stage-3 .ui-card-body { padding:6px 12px 10px; }
#stage-3 .kv-table td { padding:4px 8px; font-size:12.5px; }
@media (min-width: 900px) {
  #stage-3 .kv-table tbody { display:grid; grid-template-columns:1fr 1fr; gap:0 18px; }
  #stage-3 .kv-table tr { display:grid; grid-template-columns:140px minmax(0,1fr); }
}
/* «бумажка» — PDF поверх экрана (статичная разметка, без данных пользователя) */
.paper-overlay { display:none; position:fixed; inset:0; z-index:9999; background:rgba(18,24,20,.78); }
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

.badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
.badge.ok { background:#DCFCE7; color:#15803D; }
.badge.amber { background:#FEF3C7; color:#78350F; }
.badge.blue { background:#DBEAFE; color:#1E40AF; }
.badge.muted { background:#E5E7EB; color:#6B7280; }
.badge.bad { background:#FEE2E2; color:#B91C1C; }
.badge.grey { background:#E5E7EB; color:#6B7280; }
</style>

<div id="drive-modal" onclick="if(event.target===this)wolfDriveClose()">
  <div class="dm-box">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <b>Что вытащено из Google Drive</b>
      <button type="button" onclick="wolfDriveClose()" style="border:0;background:none;font-size:20px;cursor:pointer">×</button>
    </div>
    <div id="drive-modal-body"></div>
  </div>
</div>

<style>
.drive-actions{display:flex;flex-wrap:wrap;gap:6px}
.drive-btn{color:#14663A !important;background:#F3FAF5 !important;border:1px solid #BFE0CB !important;font-weight:600}
.rp-k{width:150px;color:#4B5B52;font-size:12.5px;padding:3px 8px 3px 0;vertical-align:top;white-space:nowrap}
.rp-v{font-size:13px;padding:3px 0;word-break:break-word}
.rp-note{font-size:12px;color:#6B7C70;padding:8px 0 2px;line-height:1.45}
.kv-table{border-collapse:collapse;width:100%}
.kv-table td{border-bottom:1px solid #F0F5F2}
.drive-status-line{display:flex;align-items:center;gap:8px;margin-top:8px;min-height:24px}
.drive-status-line .drive-mark{margin-top:0}
.drive-scan-btn,.drive-see-btn{color:#14663A;background:#fff;font-weight:500}
.drive-btn,.drive-scan-btn,.drive-see-btn{display:inline-flex;align-items:center;justify-content:center;flex:0 0 190px;width:190px;height:36px;margin-top:6px;margin-right:6px;padding:0 12px;border-radius:8px;font-size:12.5px;text-decoration:none;box-sizing:border-box;
  border:1px solid #BFE0CB;background:#fff;font-size:12px;cursor:pointer}
.drive-scan-btn:hover,.drive-see-btn:hover,.drive-btn:hover{background:#F0FAF3}
.drive-mark{display:inline-block;margin-top:0;font-size:12px;padding:3px 8px;border-radius:6px;background:#F1F5F3;color:#3A4A40}
.drive-mark.ok{background:#E7F7EC;color:#14663A}
.drive-mark.fail{background:#FDECEC;color:#A02020}
.drive-mark.run{background:#FFF7E0;color:#8A5A00}
#drive-modal{display:none;position:fixed;inset:0;background:rgba(14,26,20,.55);z-index:60;align-items:center;justify-content:center}
#drive-modal .dm-box{background:#fff;border-radius:12px;max-width:min(920px,94vw);max-height:86vh;overflow:auto;padding:18px 20px}
.doc-eye.is-on{background:#16A34A;color:#fff;border-color:#16A34A}
</style>

<script>
/* Визор заявки: PDF показывается страницами внутри листа (без браузерного просмотрщика). */
function wolfDocView(pdfPath, btn){
  var st=document.getElementById('app-preview-stage');
  if(!st){ return; }
  var holder=document.getElementById('app-preview-holder');
  if(holder){ holder.style.display='none'; }
  st.innerHTML='<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Открываю документ…</div>';
  document.querySelectorAll('.doc-eye').forEach(function(b){ b.classList.remove('is-on'); });
  if(btn) btn.classList.add('is-on');
  fetch('/templates/pdfpages?path='+encodeURIComponent(pdfPath),{credentials:'same-origin'})
    .then(function(r){return r.text();})
    .then(function(h){ st.innerHTML=h; if(window.zpScan) setTimeout(window.zpScan,80); })
    .catch(function(){ st.innerHTML='<div style="padding:24px;color:#B91C1C">Не удалось открыть документ</div>'; });
  return false;
}
function wolfDriveScan(appId, btn){
  if (btn) { btn.disabled = true; }
  wolfNote('⏳ Запускаю разбор документов с Google Drive…', 'work');
  fetch('/applications/'+appId+'/drive-scan',{method:'POST',credentials:'same-origin',
       headers:{'X-Requested-With':'fetch'}})
    .then(function(r){return r.json();})
    .then(function(d){
      if(!d.ok){ if(st) st.textContent='❗ '+(d.note||'не удалось'); return; }
      if(d.already){ if(st) st.textContent='✅ '+(d.note||'документы уже вытащены'); return; }
      if(st) st.textContent='⏳ разбор идёт…';
      var n=0;
      var t=setInterval(function(){
        n++;
        fetch('/applications/'+appId+'/drive-status',{credentials:'same-origin'})
          .then(function(r){return r.json();})
          .then(function(s2){
            if(st) st.textContent='⏳ '+(s2.done||0)+' из '+(s2.total||0)+' документов…';
            if(s2.status!=='running'||n>240){
              clearInterval(t);
              if(st) st.textContent=(s2.status==='ok'?'✅ ':'❗ ')+(s2.note||'');
              if(s2.status==='ok'){ setTimeout(function(){ location.reload(); }, 900); }
            }
          });
      },5000);
    })
    .catch(function(){ if(st) st.textContent='❗ разбор не запустился'; });
}
function wolfNote(text, tone){
  var el = document.getElementById('drive-scan-note');
  if (!el) return;
  var colors = {ok: '#14663A', warn: '#8A5A00', err: '#B91C1C', work: '#3A4A40'};
  el.style.color = colors[tone] || colors.work;
  el.textContent = text;   // только текст: содержимое приходит от сервера, HTML не нужен
}

function wolfAutofillAll(appId, btn){
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Собираю документы…'; }
  wolfNote('⏳ Собираю документы заявки: значения по правилам, затем PDF…', 'work');
  fetch('/applications/' + appId + '/autofill-all', {method: 'POST',
        headers: {'X-Requested-With': 'fetch'}})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (!d.ok) { alert('Не получилось: ' + (d.error || 'ошибка')); 
                   if (btn) { btn.disabled = false; btn.textContent = '⚡ Заполнить автоматически'; }
                   return; }
      var msg = 'Готово: документов ' + d.documents + ', значений ' + d.values;
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
  var m=document.getElementById('drive-modal'), body=document.getElementById('drive-modal-body');
  if(!m) return;
  m.style.display='flex'; body.innerHTML='<div style="padding:16px;color:#6B7C70">Загружаю…</div>';
  fetch('/applications/'+appId+'/drive-report',{credentials:'same-origin'})
    .then(function(r){return r.text();})
    .then(function(h){ body.innerHTML=h; })
    .catch(function(){ body.innerHTML='<div style="padding:16px;color:#B91C1C">Не удалось загрузить отчёт</div>'; });
}
function wolfDriveClose(){ var m=document.getElementById('drive-modal'); if(m) m.style.display='none'; }
</script>
"""
    return render("Заявка #" + str(app_id), "dashboard",
                  '<div id="wolf-content">' + body + '</div>')


    return render(f'Заявка #{app_id}', "dashboard", body)


@bp.route("/applications/<int:app_id>/drive-scan", methods=["POST"])
def app_drive_scan(app_id: int):
    """Запуск разбора Google Drive — решение и запуск в services/drive.py.

    `?force=1` — принудительный повторный заход (кнопка этапа 1): сверяем папку
    клиента с тем, что уже лежит на сервере, догружаем отличия и пересчитываем
    значения и документы. Обычный заход повторно ничего не качает.
    """
    a = apps_repo.get(app_id)
    if not a:
        return jsonify({"ok": False, "note": "заявка не найдена"})
    force = str(request.args.get("force") or "").strip() in ("1", "true", "yes")
    if force:
        try:
            import subprocess as _sp
            _sp.Popen(["/usr/bin/nice", "-n", "15", "/usr/bin/python3",
                       "/opt/wolf_v2/scripts/app_prepare.py", str(app_id), "--force"],
                      stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, start_new_session=True)
            return jsonify({"ok": True, "note": "обновление с Google Диска запущено"})
        except Exception as e:  # noqa: BLE001
            return jsonify({"ok": False, "note": "не удалось запустить обновление: %s" % str(e)[:120]})
    return jsonify(drive.start_scan(app_id, a["client_id"]))


@bp.route("/applications/<int:app_id>/drive-status")
def app_drive_status(app_id: int):
    """Статус разбора для индикатора в карточке заявки."""
    return jsonify(drive.status(app_id))


@bp.route("/applications/<int:app_id>/drive-report")
def app_drive_report(app_id: int):
    """Что именно вытащено из документов Google Drive."""
    return drive.report_html(app_id)

@bp.route("/applications/<int:app_id>/doc-variant", methods=["POST"])
def app_doc_variant(app_id: int):
    """Переключение варианта документа внутри слота (банк, формат CV, офис иммиграции)."""
    data = request.get_json(silent=True) or request.form
    slot = (data.get("slot") or "").strip()
    try:
        new_tpl = int(data.get("template_id") or 0)
    except Exception:
        new_tpl = 0
    if not slot or not new_tpl:
        return jsonify({"ok": False, "error": "не переданы слот или шаблон"})
    c = db.connect()
    a = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not a:
        c.close(); return jsonify({"ok": False, "error": "заявка не найдена"})
    ids = [r[0] for r in c.execute("""SELECT t.id FROM product_documents pd JOIN templates t ON t.id=pd.template_id
                                       WHERE pd.product_id=? AND pd.slot_code=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged')""", (a["product_id"], slot))]
    row = c.execute("""SELECT id, values_json FROM application_documents
                        WHERE application_id=? AND template_id IN (%s) ORDER BY id DESC LIMIT 1"""
                    % ",".join("?" * len(ids)), (app_id, *ids)).fetchone() if ids else None
    if row:
        c.execute("UPDATE application_documents SET template_id=?, pdf_path=NULL, status='draft' WHERE id=?",
                  (new_tpl, row[0]))
    else:
        c.execute("""INSERT INTO application_documents (application_id, template_id, status, values_json)
                     VALUES (?,?,'draft','{}')""", (app_id, new_tpl))
    c.commit(); c.close()
    return jsonify({"ok": True, "slot": slot, "template_id": new_tpl})


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/thumb")
@login_required
def app_doc_thumb(app_id: int, template_id: int):
    """Миниатюра готового документа заявки — картинкой (WebP), а не живым HTML.

    Плитка с документом в списке должна весить десятки килобайт, а не тянуть
    целый документ: живой HTML грузится только в окно просмотра, по нажатию.
    Адрес же прогревается заранее (scripts/app_prepare.py), поэтому заявка
    открывается сразу с готовыми миниатюрами.
    """
    from flask import Response, send_file
    from services import previews
    out = previews.doc_thumb(app_id, template_id, 220)
    if not out:
        return Response("", status=404)
    resp = send_file(str(out), mimetype="image/webp", conditional=True)
    # Документ пересобирается при правке значений — браузер не должен держать старую картинку.
    resp.headers["Cache-Control"] = "private, no-cache, max-age=0"
    return resp


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/html")
def app_doc_html(app_id: int, template_id: int):
    """HTML-лист документа с подставленными данными заявки — для окна просмотра (как в конструкторе)."""
    from flask import Response
    c = db.connect()
    a = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    t = c.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
    ad = c.execute("""SELECT * FROM application_documents
                      WHERE application_id=? AND template_id=? ORDER BY id DESC LIMIT 1""",
                   (app_id, template_id)).fetchone()
    client = c.execute("SELECT * FROM clients WHERE id=?", (a["client_id"],)).fetchone() if a else None
    c.close()
    if not t:
        return Response("Шаблон не найден", status=404)
    html_file = Path("/opt/wolf_v2/data/templates") / t["code"] / "template.html"
    if not html_file.exists():
        return Response("HTML шаблона нет", status=404)
    try:
        doc_values = json.loads(ad["values_json"] or "{}") if ad else {}
    except Exception:
        doc_values = {}
    # Готовый HTML документа кэшируем на диске: сборка значений (генерация
    # справок, резюме) занимает секунды, а окно просмотра запрашивает документ
    # при каждом открытии заявки. Без кэша страница заявки «тупила».
    import hashlib as _hashlib
    # Каркасные шаблоны собираем каркасом ВСЕГДА: кэш хранил старый вид
    # (прежний template.html — без подложки и с наложениями), и просмотр отдавал его.
    _fr0 = Path("/opt/wolf_v2/data/templates") / str(t["code"] or "") / "frame"
    _q0 = _fr0 / "quality.json"
    _tpl0 = Path("/opt/wolf_v2/data/templates") / str(t["code"] or "")
    try:
        _has_frame = ((_tpl0 / "fields.json").exists() or (_fr0 / "fields.json").exists()
                      or (_fr0 / "manual_zones.json").exists()) and _q0.exists() \
            and json.loads(_q0.read_text(encoding="utf-8")).get("ok")
    except Exception:
        _has_frame = False
    _cache_dir = Path("/opt/wolf_v2/data/doc_html")
    try:
        _cache_dir.mkdir(parents=True, exist_ok=True)
        _sig = "|".join([str(template_id),
                         str((client or {})["id"] if client else ""),
                         str(ad["values_json"] if ad else ""),
                         str(html_file.stat().st_mtime)])
        _key = _hashlib.sha1(_sig.encode("utf-8")).hexdigest()[:16]
        _cache_file = _cache_dir / ("app%s_tpl%s_%s.html" % (app_id, template_id, _key))
        if _cache_file.exists() and _cache_file.stat().st_size > 100 and not _has_frame:
            return Response(_cache_file.read_text(encoding="utf-8"),
                            mimetype="text/html; charset=utf-8")
    except Exception:
        _cache_file = None
    values = build_template_values(dict(client) if client else {}, t["code"], doc_values,
                                       app_id=app_id)
    # Приводим значения к виду документа прямо здесь: через эту точку идут и окно
    # просмотра, и слепок для проверки, и сборка. Раньше нормализация стояла только
    # на пути PDF, поэтому проверка читала HTML-кэш с русским значением и ставила
    # блокировку документу, в котором русских букв уже нет.
    try:
        from services import render as _render_norm
        values = _render_norm.normalize(values, t["code"] or "")
    except Exception as _exc:                                  # noqa: BLE001
        try:
            current_app.logger.warning("нормализация значений (%s) не прошла: %s", t["code"], _exc)
        except Exception:
            pass
    # Каркасная вёрстка: подложка листа, точные координаты, поведение Word.
    # Без этой ветки просмотр, слепок и готовый PDF собирались из прежнего template.html —
    # документ уходил на Диск БЕЗ фона и с наложениями текста.
    try:
        _fr = Path("/opt/wolf_v2/data/templates") / str(t["code"] or "") / "frame"
        _q = _fr / "quality.json"
        _tpl_dir = Path("/opt/wolf_v2/data/templates") / str(t["code"] or "")
        _zones_any = (_tpl_dir / "fields.json").exists() or (_fr / "fields.json").exists() \
            or (_fr / "manual_zones.json").exists()
        if _has_frame:
            import importlib.util as _ilu
            from services import html_frame
            _spec = _ilu.spec_from_file_location("_bfl_view", "/opt/wolf_v2/scripts/build_html_flow.py")
            _bfl = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_bfl)
            _vals = html_frame.values_with_frames(t["code"], values, app_id)
            _lay = _bfl.build_layout(t["code"], dict(_vals))
            return Response(_bfl.render_html(t["code"], _lay), mimetype="text/html; charset=utf-8")
    except Exception as _exc:                            # noqa: BLE001
        current_app.logger.warning("каркас для просмотра (%s) не собрался: %s", t["code"], _exc)
    html = html_file.read_text(encoding="utf-8")
    # Подстановка: в тексте значения оборачиваем в span (перевод их не трогает),
    # внутри тегов/стилей подставляем как есть, чтобы не ломать вёрстку.
    def _sub(chunk: str, wrap: bool) -> str:
        def rep(m):
            name = m.group(1)
            val = str(values.get(name, "") or "")
            if not val and str(t["code"] or "").startswith("statement_letter") and False:
                val = "-"
            return (f'<span class="var-val" data-var="{name}">{val}</span>' if wrap else val)
        return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", rep, chunk)

    parts = re.split(r"(<[^>]*>)", html)
    html = "".join(_sub(p, not p.startswith("<")) for p in parts)
    # визор обязан показывать ровно то, что уйдёт в PDF: перенос длинных строк,
    # один кегль значений и никаких пустых разделов (для резюме)
    try:
        from services.render import tidy_for_pdf, hide_empty_sections
        html = tidy_for_pdf(html, t["code"] or "")
        if "cv__" in (t["code"] or ""):
            html = hide_empty_sections(html)
    except Exception:
        pass
    # значения переменных — чтобы перевод не трогал подставленные данные клиента
    payload = json.dumps({k: v for k, v in values.items() if v}, ensure_ascii=False)
    html += ('<script id="app-values" type="application/json">'
             + payload.replace('</', '<\\/') + '</script>')
    # готовый документ — в кэш: следующее открытие заявки покажет его мгновенно
    try:
        if _cache_file is not None:
            _cache_file.write_text(html, encoding="utf-8")
    except Exception:
        pass
    return Response(html, mimetype="text/html; charset=utf-8")


@bp.route("/applications/<int:app_id>/client-photo")
def app_client_photo(app_id: int):
    """Фотография клиента из папки Google Drive — для окна просмотра документа."""
    from flask import send_file
    c = db.connect()
    a = c.execute("SELECT client_id FROM applications WHERE id=?", (app_id,)).fetchone()
    c.close()
    if not a:
        return Response("Заявка не найдена", status=404)
    try:
        from services.values import _client_photo_path
        path = _client_photo_path(a["client_id"])
    except Exception:
        path = ""
    if not path or not Path(path).exists():
        return Response("Фотографии клиента нет", status=404)
    return send_file(path)


@bp.route("/applications/<int:app_id>/original-pages/<int:template_id>")
def app_original_pages(app_id: int, template_id: int):
    """Оригинал клиента (Google Drive) страницами PNG — для листа визора."""
    a = apps_repo.get(app_id)
    t = tpl_repo.get(template_id)
    if not a or not t:
        return "<div style='padding:20px'>Нет данных</div>"
    # Сначала образец документа (заполненный подлинник — он же вкладка «Оригинальный
    # пример» в конструкторе), и только если образца нет — файл клиента с Google Drive.
    sample = Path("/opt/wolf_v2/data/templates") / (t["code"] or "") / "example_filled.pdf"
    if sample.exists():
        try:
            rel = str(sample.relative_to("/opt/wolf_v2/data"))
            return redirect("/templates/pdfpages?path=" + quote(rel))
        except Exception:
            pass
    f = _find_original_file(a["client_id"], t["code"])
    if not f:
        return ("<div style='padding:20px;color:#6B7C70'>Для этого документа не загружен "
                "оригинальный пример, и в папке клиента на Google Drive файла этого типа нет.</div>")
    try:
        rel = str(Path(f).relative_to("/opt/wolf_v2/data"))
    except Exception:
        return "<div style='padding:20px;color:#B91C1C'>Файл вне хранилища</div>"
    return redirect("/templates/pdfpages?path=" + quote(rel))


def freeze_document(app_id: int, template_id: int, actor: str = "") -> str:
    """Зафиксировать подтверждённый документ.

    Зелёная галочка означает: значения переменных проверены и больше не
    меняются. Снимок значений и HTML-слепок документа сохраняются на диск
    (`data/frozen/`), поэтому на Google Диск уходит ровно тот вид, который
    администратор подтвердил, — даже если позже карточка клиента изменится.
    """
    import json as _json
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    from blocks.dashboard.page import app_doc_html as _html_route
    frozen_dir = _Path("/opt/wolf_v2/data/frozen")
    frozen_dir.mkdir(parents=True, exist_ok=True)
    # Перед сборкой слепка выбрасываем кэш отрендеренного HTML: после правки
    # значений кэш отдавал старую версию, и в PDF уходил документ без правок.
    for _c in _Path("/opt/wolf_v2/data/doc_html").glob("app%s_tpl%s_*.html" % (app_id, template_id)):
        try:
            _c.unlink()
        except Exception:
            pass
    ad = db.q1("""SELECT id, values_json FROM application_documents
                   WHERE application_id=? AND template_id=? ORDER BY id DESC LIMIT 1""",
               (app_id, template_id))
    values = {}
    try:
        values = _json.loads((ad or {}).get("values_json") or "{}") or {}
    except Exception:
        values = {}
    # HTML с подставленными значениями — тем же маршрутом, что и окно просмотра
    html = ""
    try:
        from flask import current_app
        with current_app.test_request_context():
            resp = _html_route(app_id, template_id)
            html = resp.get_data(as_text=True)
    except Exception as exc:  # noqa: BLE001
        html = "<!-- не удалось собрать HTML: %s -->" % str(exc)[:200]
    target = frozen_dir / ("app%s_tpl%s.html" % (app_id, template_id))
    target.write_text(html, encoding="utf-8")
    if ad:
        db.exec_sql("""UPDATE application_documents
                          SET values_json=?, rendered_at=datetime('now'), error=?
                        WHERE id=?""",
                    (_json.dumps(values, ensure_ascii=False), 
                     "подтверждён %s %s" % (_dt.now().strftime("%d.%m.%Y %H:%M"), actor or ""),
                     ad["id"]))
    return str(target)


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/reject", methods=["POST"])
@login_required
def app_doc_reject(app_id, template_id):
    """Переключатель «не нужен»: убрать документ из комплекта или вернуть его обратно."""
    ad = db.q1("SELECT id, status FROM application_documents WHERE application_id=? AND template_id=?",
               (app_id, template_id))
    if not ad:
        db.exec_sql("""INSERT INTO application_documents (application_id, template_id, status)
                       VALUES (?,?, 'rejected')""", (app_id, template_id))
        _new_status = "rejected"
    else:
        _new_status = "filled" if ad["status"] == "rejected" else "rejected"
        db.exec_sql("UPDATE application_documents SET status=? WHERE id=?", (_new_status, ad["id"]))
    db.log_event("application_document", (ad["id"] if ad else 0), _new_status,
                 actor=current_user()["login"],
                 payload=json.dumps({"app": app_id, "tpl": template_id}, ensure_ascii=False))
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "rejected": _new_status == "rejected",
                        "app_id": app_id, "template_id": template_id})
    flash("Документ исключён из комплекта" if _new_status == "rejected" else "Документ возвращён в комплект")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/verify", methods=["POST"])
@login_required
def app_doc_verify(app_id, template_id):
    """Переключатель: отметить документ проверенным или снять проверку."""
    # Подтвердить можно только полностью заполненный документ. Если админ настаивает
    # (галочка нажата второй раз — «подтвердить всё равно»), фиксируем как есть.
    _force = (request.args.get("force") or "").strip() in ("1", "true", "yes")
    _miss_verify = doc_missing_fields(app_id, template_id)
    if _miss_verify and not _force:
        _msg = "Нельзя подтвердить документ: не заполнено — " + ", ".join(_miss_verify)
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": False, "error": _msg, "missing": _miss_verify, "can_force": True})
        flash(_msg, "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    ad = db.q1("SELECT id, status FROM application_documents WHERE application_id=? AND template_id=?",
               (app_id, template_id))
    # повторное нажатие снимает проверку
    _unverify = bool(ad and ad["status"] in ("verified", "sent"))
    if _unverify:
        db.exec_sql("UPDATE application_documents SET status='filled' WHERE id=?", (ad["id"],))
        db.log_event("application_document", ad["id"], "unverified",
                     actor=current_user()["login"],
                     payload=json.dumps({"app": app_id, "tpl": template_id}, ensure_ascii=False))
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": True, "verified": False, "app_id": app_id, "template_id": template_id})
        flash("Проверка снята")
        return redirect(url_for("dashboard.app_view", app_id=app_id))
    if not ad:
        db.exec_sql("""INSERT INTO application_documents (application_id, template_id, status)
                       VALUES (?,?, 'verified')""", (app_id, template_id))
    else:
        # решения взаимоисключающие: «проверен» автоматически снимает «не нужен»
        db.exec_sql("UPDATE application_documents SET status='verified' WHERE id=?", (ad["id"],))
    db.log_event("application_document", (ad["id"] if ad else 0), "verified",
                 actor=current_user()["login"],
                 payload=json.dumps({"app": app_id, "tpl": template_id}, ensure_ascii=False))
    # Фиксация подтверждённого документа: снимок значений и HTML-слепок.
    # Так зелёная галочка означает «проверено и сохранено для отправки».
    _frozen = ""
    try:
        _frozen = freeze_document(app_id, template_id, actor=current_user()["login"])
    except Exception as _exc:  # noqa: BLE001
        _frozen = ""
    # Если запрос через fetch — вернём JSON, иначе redirect (для обратной совместимости)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "verified": True, "app_id": app_id,
                        "template_id": template_id, "frozen": _frozen})
    flash("Документ отмечен проверенным и зафиксирован для отправки")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/autofill-values", methods=["GET"])
@login_required
def app_doc_autofill(app_id: int, template_id: int):
    """Возвращает категоризированные значения переменных шаблона.

    Категории:
      auto         — точно из clients/<field> или application.values_json (подставлять сразу)
      suggested    — из variable_value_history (топ-1, приходит с плашкой «из опыта»)
      generated    — значения не было нигде — сгенерировано по правилу переменной
      manual_only  — пусто, ставим placeholder
    """
    a = apps_repo.get(app_id)
    if not a:
        return jsonify({"ok": False, "error": "Заявка не найдена"}), 404
    tpl = tpl_repo.get(template_id)
    if not tpl:
        return jsonify({"ok": False, "error": "Шаблон не найден"}), 404

    variables = db.q("SELECT name, label FROM template_variables WHERE template_id=?",
                     (template_id,))
    if not variables:
        return jsonify({"ok": True, "auto": {}, "suggested": {},
                        "manual_only": [], "messages": []})

    # 1) Из clients
    client = db.client_get(a["client_id"]) or {}
    # 2) Из application.values_json (что менеджер прислал)
    app_values = {}
    try:
        app_values = json.loads(a.get("values_json") or "{}")
    except Exception:
        pass
    # 3) Из последнего application_document (что в этом документе уже вводили)
    prev_doc = db.q1("""SELECT values_json FROM application_documents
                        WHERE application_id=? AND template_id=?
                        ORDER BY id DESC LIMIT 1""", (app_id, template_id))
    doc_values = {}
    if prev_doc and prev_doc.get("values_json"):
        try:
            doc_values = json.loads(prev_doc["values_json"])
        except Exception:
            pass

    # Сборка прямых маппингов client → переменная
    simple_map = {
        "full_name": f'{client.get("surname", "")} {client.get("name", "")}'.strip(),
        "surname": client.get("surname"),
        "name": client.get("name"),
        "patronymic": client.get("patronymic"),
        "full_name_latin": client.get("full_name_latin"),
        "full_name_title": client.get("full_name_title"),
        "client_name": client.get("full_name_latin") or client.get("name") or "",
        "for_name": client.get("full_name_latin") or client.get("name") or "",
        "birth_date": client.get("birth_date"),
        "date_of_birth": client.get("birth_date"),
        "place_of_birth": client.get("birth_place"),
        "birth_place": client.get("birth_place"),
        "gender": client.get("gender"),
        "citizenship": client.get("citizenship"),
        "nationality": client.get("nationality"),
        "passport_series": client.get("passport_series"),
        "passport_number": client.get("passport_number"),
        "passport_no": client.get("passport_number"),
        "passport_issued_by": client.get("passport_issued_by"),
        "passport_issue_date": client.get("passport_issue_date"),
        "passport_expiry": client.get("passport_expiry"),
        "inn": client.get("inn"),
        "snils": client.get("snils"),
        "intl_passport": client.get("intl_passport"),
        "phone": client.get("phone"),
        "email": client.get("email"),
        "address_reg": client.get("address_reg"),
        "address_live": client.get("address_live"),
        "address_zip": client.get("address_zip"),
        "city": client.get("city"),
        "country": client.get("country"),
        "position": client.get("position"),
        "salary_amount": client.get("salary_amount"),
        "salary": client.get("salary_amount"),
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
        "doc_no", "ref_no", "balance_rub", "balance_date", "period_from",
        "period_to", "account_no", "contract_no", "contract_date",
        "doc_date", "doc_title", "aggreement_date", "agreement_date",
        "agreement_no", "period_dates", "balance_value", "doc_purpose",
    }

    auto = {}
    suggested = {}
    generated = {}
    _gv_cache = None
    manual_only = []
    messages = []

    for v in variables:
        name = v["name"]
        if name in SPECIFIC_FIELDS:
            # «Свои» поля документа (номер, дата, период, остаток) в карточке
            # клиента не лежат — их берём из правил генерации, и только если
            # правило не сработало, оставляем администратору на ручной ввод.
            try:
                if _gv_cache is None:
                    _gv_cache = build_template_values(dict(client), tpl["code"], {})
                if _gv_cache.get(name) not in (None, ""):
                    generated[name] = {"value": str(_gv_cache[name]),
                                       "source": "сгенерировано по правилу переменной"}
                    continue
            except Exception:
                pass
            manual_only.append(name)
            continue

        # Приоритет 1: что ввёл менеджер (app_values)
        if name in app_values and app_values[name]:
            auto[name] = {"value": str(app_values[name]),
                          "source": "application.values_json"}
            continue

        # Приоритет 2: что уже введено в этом документе
        if name in doc_values and doc_values[name]:
            auto[name] = {"value": str(doc_values[name]),
                          "source": "previous input"}
            continue

        # Приоритет 3: прямое соответствие колонкам clients
        if name in simple_map and simple_map[name]:
            auto[name] = {"value": str(simple_map[name]),
                          "source": f"clients.{name.replace('full_name','full_name') if 'full_name' in name else name}"}
            continue

        # Приоритет 4: variable_value_history (top-1 для этого клиента)
        # Берём значение, которое чаще всего использовалось для ЭТОГО клиента
        try:
            client_match = db.q1(
                """SELECT value, used_count FROM variable_value_history
                   WHERE variable_name=? AND value IN
                       (SELECT DISTINCT values_json FROM application_documents
                        WHERE application_id IN
                          (SELECT id FROM applications WHERE client_id=?))
                   ORDER BY used_count DESC LIMIT 1""",
                (name, a["client_id"]))
            if client_match:
                suggested[name] = {
                    "value": str(client_match["value"]),
                    "source": f"опыт по клиенту (×{client_match['used_count']})"
                }
                continue
        except Exception:
            pass

        # Приоритет 5: top-1 из общей variable_value_history
        try:
            top = db.q1(
                """SELECT value, used_count FROM variable_value_history
                   WHERE variable_name=? ORDER BY used_count DESC LIMIT 1""",
                (name,))
            if top:
                suggested[name] = {
                    "value": str(top["value"]),
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
                _gv_cache = build_template_values(dict(client), tpl["code"], {})
            if _gv_cache.get(name) not in (None, ""):
                generated[name] = {"value": str(_gv_cache[name]),
                                   "source": "сгенерировано по правилу переменной"}
                continue
        except Exception as exc:  # noqa: BLE001
            generated.setdefault("_err", {"value": str(exc)[:120], "source": "debug"})

        manual_only.append(name)

    return jsonify({
        "ok": True,
        "auto": auto,
        "suggested": suggested,
        "generated": generated,
        "manual_only": manual_only,
        "messages": [f"{len(auto)} из данных, {len(generated)} сгенерировано, "
                     f"{len(suggested)} из опыта, {len(manual_only)} вручную"],
        "client_name": client.get("full_name_latin") or "",
    })


@bp.route("/applications/<int:app_id>/send-state")
def app_send_state(app_id):
    """Быстрый ответ о готовности комплекта: сколько документов согласовано.

    Нужен, чтобы счётчик блока 6 обновлялся сразу после отметки «✓ Проверен»,
    без перезагрузки страницы и без повторного рендера всей карточки.
    """
    import json as _json
    rows = db.q(
        "SELECT status FROM application_documents WHERE application_id=?",
        (app_id,),
    )
    total = len(rows)
    checked = 0
    for r in rows:
        st = (r["status"] if not isinstance(r, (list, tuple)) else r[0]) or ""
        if st in ("verified", "rejected"):
            checked += 1
    can_send = total > 0 and checked == total
    if can_send:
        hint = "Все документы согласованы — можно отправлять на Google Диск"
        state = "ok"
    else:
        hint = ("Отправить нельзя: согласовано " + str(checked) + " из "
                + str(total) + " документов")
        state = "warn"
    return _json.dumps({
        "ok": True,
        "ready": checked,
        "total": total,
        "can_send": can_send,
        "hint": hint,
        "state": state,
    }, ensure_ascii=False), 200, {"Content-Type": "application/json; charset=utf-8"}


@bp.route("/applications/<int:app_id>/autofill-all", methods=["POST"])
@login_required
def app_autofill_all(app_id: int):
    """Яркая кнопка в карточке: собрать ВСЕ документы заявки на просмотр.

    Для каждого документа заявки значения берутся по правилам (данные клиента →
    документы Google Drive → правила генерации), затем документ рендерится в PDF.
    Дальше администратор просто смотрит результат в окне готовых документов
    и правит карандашом только то, что сочёл неверным.
    """
    a = apps_repo.get(app_id)
    if not a:
        return jsonify({"ok": False, "error": "Заявка не найдена"}), 404
    client = db.client_get(a["client_id"]) or {}
    docs = db.q("""SELECT ad.id AS ad_id, ad.template_id, ad.values_json, t.code, t.title, t.pages
                   FROM application_documents ad JOIN templates t ON t.id=ad.template_id
                   WHERE ad.application_id=? ORDER BY ad.id""", (app_id,))
    if not docs:
        return jsonify({"ok": False, "error": "У заявки нет документов"}), 400

    done, failed, values_count = [], [], 0
    for d in docs:
        code = d["code"]
        try:
            prev_values = json.loads(d["values_json"] or "{}")
        except Exception:
            prev_values = {}
        try:
            vals = build_template_values(dict(client), code, prev_values) or {}
        except Exception as exc:  # noqa: BLE001
            failed.append({"code": code, "error": str(exc)[:120]})
            continue
        values_count += sum(1 for v in vals.values() if v)
        try:
            db.exec_sql("UPDATE application_documents SET values_json=? WHERE id=?",
                        (json.dumps(vals, ensure_ascii=False), d["ad_id"]))
        except Exception as exc:  # noqa: BLE001
            failed.append({"code": code, "error": str(exc)[:120]})
            continue
        # рендерим PDF, чтобы документ сразу был в окне просмотра
        try:
            html_file = Path("/opt/wolf_v2/data/templates") / code / "template.html"
            if html_file.exists():
                out_pdf = _app_pdf_path({"code": code}, vals, app_id)
                out_pdf.parent.mkdir(parents=True, exist_ok=True)
                html = html_file.read_text(encoding="utf-8")
                filled = doc_render.fill(html, vals, keep_unfilled=False, template_code=code)
                doc_render.render_pdf(filled, base_dir=str(html_file.parent), out_path=out_pdf)
                db.exec_sql("""UPDATE application_documents
                               SET pdf_path=?, status=CASE WHEN status IN ('pending','new','draft')
                                    THEN 'filled' ELSE status END, rendered_at=datetime('now')
                               WHERE id=?""", (str(out_pdf), d["ad_id"]))
        except Exception as exc:  # noqa: BLE001
            failed.append({"code": code, "error": "PDF: " + str(exc)[:100]})
        done.append({"code": code, "title": d["title"]})

    return jsonify({"ok": True, "documents": len(done), "values": values_count,
                    "failed": failed, "list": [x["title"] for x in done]})


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/ensure-pdf", methods=["POST"])
@login_required
def app_doc_ensure_pdf(app_id: int, template_id: int):
    """Гарантирует наличие сформированного PDF. Генерирует, если файла нет.

    Возвращает JSON: {ok, pdf_name} — имя файла для предпросмотра.
    """
    a = apps_repo.get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        return jsonify({"ok": False, "error": "Заявка или шаблон не найдены"}), 404

    ad = db.q1("""SELECT * FROM application_documents
                  WHERE application_id=? AND template_id=?
                  ORDER BY id DESC LIMIT 1""", (app_id, template_id))

    # 1) файл уже есть и он не старше шаблона — отдаём его.
    # Если шаблон правился позже PDF, документ пересобираем: менеджер должен видеть
    # готовый документ из АКТУАЛЬНОГО одобренного шаблона, а не старую сборку.
    tpl_html = Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html"
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
    html_path = Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html"
    if not html_path.exists():
        return jsonify({"ok": False, "error": "template.html не найден"}), 404

    client = db.client_get(a["client_id"]) or {}
    # значения: из документа → из клиента → из истории
    values = {}
    if ad and ad.get("values_json"):
        try:
            values = json.loads(ad["values_json"])
        except Exception:
            pass
    try:
        from blocks.dashboard.page import build_template_values
        values.update(build_template_values(client, tpl["code"], values))
    except Exception:
        pass

    out_pdf = _app_pdf_path(tpl, values, app_id)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    html = html_path.read_text(encoding="utf-8")
    # ЕДИНЫЙ рендер: тот же код, что в конструкторе, боте и автоподготовке
    filled = doc_render.fill(html, values, keep_unfilled=False, template_code=tpl["code"])
    try:
        doc_render.render_pdf(filled, base_dir=str(html_path.parent), out_path=out_pdf)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Ошибка генерации: {str(exc)[:200]}"}), 500

    if not out_pdf.exists():
        return jsonify({"ok": False, "error": "PDF не создан"}), 500

    # обновляем запись
    if ad:
        db.exec_sql("""UPDATE application_documents
                       SET pdf_path=?, status=CASE WHEN status IN ('pending','new') THEN 'filled' ELSE status END,
                           rendered_at=datetime('now')
                       WHERE id=?""", (str(out_pdf), ad["id"]))
    else:
        db.exec_sql("""INSERT INTO application_documents
                       (application_id, template_id, status, pdf_path, rendered_at)
                       VALUES (?,?, 'filled', ?, datetime('now'))""",
                    (app_id, template_id, str(out_pdf)))

    return jsonify({"ok": True, "pdf_name": out_pdf.name, "created": True})


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/editor")
@login_required
def app_doc_editor(app_id: int, template_id: int):
    """Двух-колонковый редактор шаблона: список переменных + предпросмотр HTML и PDF."""
    a = db.application_get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        flash("Документ не найден", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))

    variables = [dict(v) for v in db.q(
        "SELECT tv.*, COALESCE(vs.scope, 'common') AS scope FROM template_variables tv "
        "LEFT JOIN variable_scope vs ON vs.name = tv.name "
        "WHERE tv.template_id=? ORDER BY tv.sort_order, tv.name", (template_id,))]
    client = db.client_get(a["client_id"]) or {}
    from blocks.dashboard.page import build_template_values
    auto_values = build_template_values(client, tpl["code"])
    # Пул значений из архива: для типовых переменных менеджер выбирает готовый вариант
    # или вводит свой (он сохранится в пул и будет доступен в других заявках).
    pool = {}
    try:
        for r in db.q("""SELECT variable_name, value FROM variable_value_history v
                         WHERE value != '' AND LENGTH(value) <= 120
                           AND COALESCE((SELECT scope FROM variable_scope WHERE name=v.variable_name),'common')='common'
                         ORDER BY used_count DESC"""):
            vals = pool.setdefault(r["variable_name"], [])
            if r["value"] not in vals and len(vals) < 15:
                vals.append(r["value"])
    except Exception:
        pool = {}
    # значения, введённые админом ранее
    doc_row = db.q1(
        "SELECT values_json FROM application_documents WHERE application_id=? AND template_id=?",
        (app_id, template_id))
    saved = {}
    if doc_row and doc_row.get("values_json"):
        try:
            saved = json.loads(doc_row["values_json"])
        except Exception:
            saved = {}
    merged = {**auto_values, **{k: v for k, v in saved.items() if v}}

    html_file = (Path(tpl["html_path"]) if tpl.get("html_path")
                 else Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html")
    raw_html = html_file.read_text(encoding="utf-8") if html_file.exists() else ""

    return render_template("editor.html", **{
        "a": a, "tpl": tpl, "client": client,
        "variables": variables,
        "pool": pool,
        "scopes": {v["name"]: v.get("scope", "common") for v in variables},
        "values_json": json.dumps(merged, ensure_ascii=False),
        "auto_values_json": json.dumps(auto_values, ensure_ascii=False),
        "raw_html": raw_html,
        "app_id": app_id, "template_id": template_id,
    })


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/preview-pdf", methods=["POST"])
@login_required
def app_doc_preview_pdf(app_id: int, template_id: int):
    """Рендер PDF по текущим значениям формы (без сохранения), отдаём HTML страницы с iframe."""
    a = db.application_get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        return "Not found", 404
    html_file = (Path(tpl["html_path"]) if tpl.get("html_path")
                 else Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html")
    if not html_file.exists():
        return "Шаблон не сконвертирован", 400
    # подставляем значения
    variables = db.q("SELECT * FROM template_variables WHERE template_id=?", (template_id,))
    values = json.loads(request.form.get("values_json") or "{}")
    try:
        from bot.ai_parser import translit_ru, amount_in_words_en, format_amount_en, parse_amount
        for _k in list(values.keys()):
            v = values[_k]
            if isinstance(v, str) and any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in v):
                if "bank_statement" in tpl["code"]:
                    values[_k] = translit_ru(v)
        if "bank_statement" in tpl["code"]:
            bal = values.get("balance_rub")
            if bal and parse_amount(bal) > 0:
                values["balance_words"] = amount_in_words_en(bal)
                values["balance_rub"] = format_amount_en(bal)
    except Exception:
        pass
    _hv = {k: (str(v).replace("\r\n", "\n").replace("\n", "<br>")
               if isinstance(v, str) else v) for k, v in values.items()}
    html = html_file.read_text(encoding="utf-8")
    # Пустая переменная не печатается: имени переменной в предпросмотре быть не должно.
    # В формах иммиграции пустое поле показываем прочерком — как в поданных документах.
    _dash = str(tpl.get("code") or "").startswith("statement_letter")
    filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                    lambda m: str(_hv.get(m.group(1)) or ("-" if _dash else "")), html)
    from core.pdf2html import render_pdf
    tmp = html_file.parent / "filled_preview.html"
    tmp.write_text(filled, encoding="utf-8")
    pdf_path = Path('/opt/wolf_v2/data/renders') / f"{tpl['code']}_app{app_id}_preview_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    try:
        render_pdf(tmp, pdf_path)
    except Exception as e:
        return f"Ошибка рендера: {e}", 500
    # имя файла → URL. Отдаём через общий маршрут файлов рендера
    # (/branding/render/ не существует — из-за этого превью в редакторе не открывалось).
    return jsonify({"pdf_url": f"/templates/file/renders/{pdf_path.name}"}), 200


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/save-values", methods=["POST"])
@login_required
def app_doc_save_values(app_id: int, template_id: int):
    """Сохраняет текущие значения переменных в application_documents.values_json
    и дублирует автозначения в clients (если совпадают)."""
    try:
        values = json.loads(request.form.get("values_json") or "{}")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    tpl = tpl_repo.get(template_id)
    a = db.application_get(app_id)
    if not tpl or not a:
        return jsonify({"ok": False, "error": "not found"}), 404

    # обновляем values_json в документе.
    # pdf_path сбрасываем: документ должен быть собран заново с новыми значениями,
    # иначе менеджер увидит старую сборку (это и была причина «документ с ошибкой»).
    db.exec_sql(
        "UPDATE application_documents SET values_json=?, pdf_path=NULL, status='draft' "
        "WHERE application_id=? AND template_id=?",
        (json.dumps(values, ensure_ascii=False), app_id, template_id))

    # Значения, введённые человеком, запоминаем в пул: в следующих заявках они
    # предлагаются в выпадающем списке у этой же переменной (память архива).
    try:
        for k, v in values.items():
            s = str(v or "").strip()
            if not s or len(s) > 120:
                continue
            row = db.q1("SELECT id FROM variable_value_history WHERE variable_name=? AND value=?", (k, s))
            if row:
                db.exec_sql("UPDATE variable_value_history SET used_count=used_count+1, "
                            "last_used=datetime('now') WHERE id=?", (row["id"],))
            else:
                db.exec_sql("INSERT INTO variable_value_history(variable_name, value, used_count, last_used) "
                            "VALUES(?,?,1,datetime('now'))", (k, s))
    except Exception:
        pass

    # обновим полный лист переменных, если есть пустые
    variables = vars_repo.names(template_id)
    return jsonify({"ok": True, "saved": list(values.keys())})


def _hist_datalist(var_name: str, limit: int = 40) -> str:
    """Выпадающий список прошлых значений поля: из истории и прошлых документов."""
    seen = []
    try:
        for r in db.q("""SELECT value FROM variable_value_history
                         WHERE variable_name=? ORDER BY used_count DESC, last_used DESC LIMIT ?""",
                      (var_name, limit)):
            v = str(r["value"] if hasattr(r, "keys") else r[0]).strip()
            if v and v not in seen:
                seen.append(v)
    except Exception:
        pass
    try:
        for r in db.q("""SELECT values_json FROM application_documents
                         WHERE values_json LIKE ? ORDER BY id DESC LIMIT 200""",
                      ("%" + var_name + "%",)):
            try:
                val = str(json.loads(r["values_json"] or "{}").get(var_name) or "").strip()
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
    opts = "".join('<option value="' + v.replace("&", "&amp;").replace('"', "&quot;") + '"></option>'
                   for v in seen[:limit])
    return f'<datalist id="hist_{var_name}">{opts}</datalist>'


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
def app_doc_edit(app_id: int, template_id: int):
    a = db.application_get(app_id)
    tpl = tpl_repo.get(template_id)
    if not a or not tpl:
        flash("Документ не найден", "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))

    if request.method == "POST":
        action = request.form.get("action") or "fill"
        variables = db.q("SELECT * FROM template_variables WHERE template_id=?",
                         (template_id,))
        values = json.loads(tpl.get("default_values_json") or "{}")
        # подставляем из клиента по именам переменных
        client = db.client_get(a["client_id"]) or {}
        for v in variables:
            val = (request.form.get(v["name"]) or "").strip()
            if val:
                values[v["name"]] = val
                # запомнить введённое значение для будущего автодополнения
                # (но НЕ для уникальных данных клиента)
                if v["name"] not in {
                    "surname", "name", "patronymic", "full_name", "full_name_latin",
                    "birth_date", "place_of_birth", "date_of_birth",
                    "passport_series", "passport_number", "passport_no",
                    "passport_issued_by", "passport_issue_date", "passport_expiry",
                    "inn", "phone", "email", "address_reg", "address_live",
                    "card_mask", "ref_no",
                }:
                    try:
                        db.remember_value(v["name"], val)
                    except Exception:
                        pass
        html_file = Path(tpl["html_path"]) if tpl.get("html_path") else None
        if not html_file or not html_file.exists():
            html_file = Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html"
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
                values.setdefault("profession", _art + _pos)
            values.setdefault("client_name",
                              f'{(client.get("surname") or "")} {(client.get("name") or "")}'.strip())
            values.setdefault("full_name_latin", values.get("client_name", ""))
            for _k in ("address_live", "address_reg", "email", "phone",
                       "card_mask", "account_no", "contract_no", "balance_rub",
                       "balance_date", "doc_no", "ref_no", "bank_name"):
                if client.get(_k):
                    values.setdefault(_k, client[_k])
            # номер карты в документ уходит только маской (6 цифр + ****** + 4 цифры)
            try:
                from services.values import mask_card as _mask_card
                values["card_mask"] = _mask_card(values.get("card_mask"), tpl.get("code") or "",
                                                 seed=client.get("id"))
            except Exception:
                pass
        # многострочные значения (например, список услуг) → <br> для HTML
        _hv = {k: (str(v).replace("\r\n", "\n").replace("\n", "<br>")
                   if isinstance(v, str) else v) for k, v in values.items()}
        # банковские справки — строго английский: кириллицу транслитерируем
        if "bank_statement" in (tpl.get("code") or ""):
            try:
                from bot.ai_parser import (translit_ru, amount_in_words_en,
                                       format_amount_en, parse_amount)
                for _k in list(_hv.keys()):
                    if isinstance(_hv[_k], str) and any(
                            "а" <= c.lower() <= "я" or c.lower() == "ё" for c in _hv[_k]):
                        _hv[_k] = translit_ru(_hv[_k])
                # сумма: формат «1 770 300,00» + прописью
                _bal = _hv.get("balance_rub")
                if _bal:
                    try:
                        if parse_amount(_bal) > 0:
                            _hv["balance_words"] = amount_in_words_en(_bal)
                            _hv["balance_rub"] = format_amount_en(_bal)
                    except Exception:
                        pass
            except Exception:
                pass
        # Полный расчёт значений: имя переменной не должно попадать в готовый PDF.
        try:
            from services.values import build_template_values as _btv2
            _cl2 = db.client_get((db.q1("SELECT client_id FROM applications WHERE id=?",
                                        (app_id,)) or {}).get("client_id")) or {}
            _hv.update(_btv2(dict(_cl2), tpl["code"], values, app_id=app_id) or {})
        except Exception:
            pass
        _dash2 = str(tpl.get("code") or "").startswith("statement_letter")
        filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                        lambda m: str(_hv.get(m.group(1)) or ("-" if _dash2 else "")), html)
        out_pdf = Path('/opt/wolf_v2/data/renders') / \
            f'{tpl["code"]}_app{app_id}_{datetime.now():%Y%m%d_%H%M%S}.pdf'
        tmp_html = html_file.parent / "filled.html"
        tmp_html.write_text(filled, encoding="utf-8")
        try:
            from core import pdf2html
            pdf2html.render_pdf(tmp_html, out_pdf)
        except Exception as exc:
            # отметим application_document ошибкой если он есть
            ad = db.q1("SELECT id FROM application_documents WHERE application_id=? AND template_id=?",
                       (app_id, template_id))
            if ad:
                db.application_doc_set(ad["id"], "error",
                                       values_json=json.dumps(values, ensure_ascii=False),
                                       error=str(exc)[:300])
            flash(f"Ошибка PDF: {exc}", "error")
            return redirect(url_for("dashboard.app_doc_edit", app_id=app_id, template_id=template_id))

        # обновим/создадим application_document
        ad = db.q1("SELECT id FROM application_documents WHERE application_id=? AND template_id=?",
                   (app_id, template_id))
        _prev_st = (db.q1("SELECT status FROM application_documents WHERE application_id=? AND template_id=?",
                          (app_id, template_id)) or {}).get("status")
        if action == "verify":
            new_status = "verified"
        elif (_prev_st or "") in ("verified", "sent"):
            new_status = _prev_st          # уже проверен — пересборка галочку не снимает
        else:
            new_status = "filled"
        if ad:
            db.application_doc_set(ad["id"], new_status,
                                   values_json=json.dumps(values, ensure_ascii=False),
                                   pdf_path=str(out_pdf))
        else:
            db.exec_sql(
                "INSERT INTO application_documents (application_id, template_id, status, "
                "values_json, pdf_path, updated_at) VALUES (?,?,?,?,?,datetime('now'))",
                (app_id, template_id, new_status,
                 json.dumps(values, ensure_ascii=False), str(out_pdf)))
        flash("PDF сформирован" if new_status == "filled"
              else "PDF сформирован и помечен как проверенным")
        return redirect(url_for("dashboard.app_doc_edit", app_id=app_id, template_id=template_id))

    variables = db.q("SELECT * FROM template_variables WHERE template_id=? ORDER BY sort_order, name",
                     (template_id,))
    # значения по умолчанию: из последнего application_document этого шаблона, иначе из default
    prev = db.q1("SELECT * FROM application_documents WHERE application_id=? AND template_id=?",
                 (app_id, template_id))
    # === АВТО-ГЕНЕРАЦИЯ: если документ только что создан (pending) и PDF нет — сгенерируем сразу ===
    if prev and prev["status"] == "pending" and not prev.get("pdf_path"):
        try:
            from core import pdf2html as _pdf2html
            html_path = Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html"
            if html_path.exists():
                # возьмём дефолтные значения для генерации
                _vals = {}
                if tpl.get("default_values_json"):
                    try: _vals = json.loads(tpl["default_values_json"])
                    except: pass
                # простая подстановка из клиента
                _cli = db.client_get(a["client_id"]) or {}
                for _k in ("full_name_latin", "client_name", "name", "surname", "patronymic",
                           "address_live", "address_registration", "inn", "phone", "email"):
                    if not _vals.get(_k):
                        _vals[_k] = _cli.get(_k) or _cli.get(_k.replace("_live","_reg")) or ""
                _html = html_path.read_text(encoding="utf-8")
                # Полный расчёт значений — тот же путь, что у окна просмотра и у слепка:
                # имя переменной в готовый PDF попадать не должно, поэтому не найденное
                # значение печатается пустым (в формах иммиграции — прочерком).
                try:
                    from services.values import build_template_values as _btv
                    _adv = db.q1("""SELECT values_json FROM application_documents
                                     WHERE application_id=? AND template_id=?
                                     ORDER BY id DESC LIMIT 1""", (app_id, template_id)) or {}
                    try:
                        _dv = json.loads(_adv.get("values_json") or "{}")
                    except Exception:
                        _dv = {}
                    _vals.update(_btv(dict(_cli), tpl["code"], _dv, app_id=app_id) or {})
                except Exception as _e:
                    flash(f"Значения документа посчитаны не полностью: {_e}", "warning")
                _dash = str(tpl.get("code") or "").startswith("statement_letter")
                _filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                                 lambda m: str(_vals.get(m.group(1)) or ("-" if _dash else "")),
                                 _html)
                _tmp = html_path.parent / "filled.html"
                _tmp.write_text(_filled, encoding="utf-8")
                _out = Path('/opt/wolf_v2/data/renders') / (tpl["code"] + "_app" + str(app_id) + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pdf")
                _pdf2html.render_pdf(_tmp, _out)
                # обновим запись
                db.exec_sql("UPDATE application_documents SET pdf_path=?, status='filled', rendered_at=datetime('now') "
                            "WHERE id=? AND IFNULL(status,'') NOT IN ('verified','sent')",
                            (str(_out), prev["id"]))
                prev = db.q1("SELECT * FROM application_documents WHERE id=?", (prev["id"],))
                flash("PDF сформирован автоматически")
        except Exception as _exc:
            flash(f"Авто-генерация не удалась: {_exc}", "warning")
    values = {}
    if prev and prev.get("values_json"):
        try:
            values = json.loads(prev["values_json"])
        except Exception:
            pass
    if not values and tpl.get("default_values_json"):
        try:
            values = json.loads(tpl["default_values_json"])
        except Exception:
            pass
    # Подставим из клиента (ФИО, телефон и т.п.) если переменная называется как поле клиента
    client = db.client_get(a["client_id"]) or {}
    simple_map = {
        "full_name": f'{client.get("surname","")} {client.get("name","")}'.strip(),
        "surname": client.get("surname") or "",
        "name": client.get("name") or "",
        "patronymic": client.get("patronymic") or "",
        "full_name_latin": client.get("full_name_latin") or "",
        "client_name": client.get("full_name_latin") or client.get("name") or client.get("surname") or "",
        "for_name": client.get("full_name_latin") or client.get("name") or client.get("surname") or "",
        "birth_date": client.get("birth_date") or "",
        "gender": client.get("gender") or "",
        "citizenship": client.get("citizenship") or "",
        "passport_series": client.get("passport_series") or "",
        "passport_number": client.get("passport_number") or "",
        "passport_issued_by": client.get("passport_issued_by") or "",
        "passport_issue_date": client.get("passport_issue_date") or "",
        "passport_expiry": client.get("passport_expiry") or "",
        "phone": client.get("phone") or "",
        "email": client.get("email") or "",
        "address_reg": client.get("address_reg") or "",
        "address_live": client.get("address_live") or "",
        "company_name": client.get("company_name") or "",
        "position": client.get("position") or "",
        "salary_amount": client.get("salary_amount") or "",
        "bank_name": client.get("bank_name") or "",
        "inn": client.get("inn") or "",
    }
    for k, v in simple_map.items():
        values.setdefault(k, v or "")

    # Переменные, которые НЕ нужно копить в памяти (всегда уникальные).
    # Для них datalist пустой — только ручной ввод.
    NO_MEMORY_VARS = {
        "surname", "name", "patronymic", "full_name", "full_name_latin",
        "birth_date", "place_of_birth", "date_of_birth",
        "passport_series", "passport_number", "passport_no",
        "passport_issued_by", "passport_issue_date", "passport_expiry",
        "inn", "phone", "email", "address_reg", "address_live",
        "card_mask", "ref_no",
    }
    # Переменные с рандомайзером (формат описан в RANDOM_FORMATS)
    RANDOM_VARS = {"doc_no", "ref_no"}

    fields = "".join(
        f'<div class="var-field" data-var="{v["name"]}">'
        f'<label for="v_{v["name"]}">'
        + (v["label"] or v["name"])
        + f'<span class="muted mono"> · {v["name"]}</span>'
        # индикатор сколько вариантов есть в БД
        + f'<span class="muted mono var-hint" id="hint_{v["name"]}"></span>'
        + '</label>'
        + ('<div class="var-rule" title="' + (v.get('rule_note') or '').replace('"', '&quot;') + '" '
           'style="font-size:11px;color:#7c8ea0;margin:-2px 0 4px 6px;'
           'cursor:help;border-left:2px solid #334155;padding-left:6px;'
           'white-space:pre-wrap">📝 '
           + ((v.get('rule_note') or '')[:180]
              + ('…' if len(v.get('rule_note') or '') > 180 else ''))
           + '</div>' if v.get('rule_note') else
           '<div class="var-rule missing" '
           'style="font-size:11px;color:#a8776e;margin:-2px 0 4px 6px;'
           'cursor:help;border-left:2px solid #7c3a2a;padding-left:6px">'
           '📝 правило не задано — откройте Шаблоны → bank_statement_3m__tbank и опишите источник</div>')
        + '<div class="var-row">'
        # input для ручного ввода + скрытый select для вариантов.
        # Для длинных/многострочных значений (например, список услуг) — textarea.
        + (lambda _v: (
            f'<textarea id="v_{_v["name"]}" name="{_v["name"]}" '
            f'class="var-input var-ta" autocomplete="off" data-var="{_v["name"]}" rows="5" '
            f'placeholder="введите или выберите вариант...">'
            f'{str(values.get(_v["name"], _v["default_value"] or "")).replace("&", "&amp;").replace("<", "&lt;")}'
            f'</textarea>'
            if ((_v.get("vtype") or "") == "text"
                or "\n" in str(values.get(_v["name"], _v["default_value"] or ""))
                or len(str(values.get(_v["name"], _v["default_value"] or ""))) > 90)
            else
            f'<input id="v_{_v["name"]}" type="text" name="{_v["name"]}" '
            f'class="var-input" autocomplete="off" data-var="{_v["name"]}" '
            f'list="hist_{_v["name"]}" '
            f'placeholder="введите или выберите вариант..." '
            f'value="{str(values.get(_v["name"], _v["default_value"] or "")).replace("&", "&amp;").replace(chr(34), "&quot;")}">'
        ))(v)
        # исторические значения этого поля — администратор выбирает из списка
        # или вписывает своё; список формируется из прошлых документов и истории
        + (_hist_datalist(v["name"])
           if any(w in (v["name"] or "").lower() for w in ("addr", "address", "domicil")) else "")
        + (f'<span class="var-info" title="'
           + (v.get('rule_note') or 'Инструкция будет добавлена').replace('"', '&quot;').replace('\n', '&#10;')
           + f'" data-var="{v["name"]}" data-template="{template_id}"'
           + ' data-doc="документ заявки"'
           + ' data-rule="' + (v.get('rule_note') or '').replace('"', '&quot;').replace('\n', '&#10;') + '">i</span>')
        + (f'<button type="button" class="btn ghost sm random-btn" '
           f' onclick="randomizeDocNo(\'v_{v["name"]}\')" '
           f'title="Сгенерировать случайный номер">🎲</button>'
           if v["name"] in RANDOM_VARS else "")
        + ('<button type="button" class="btn ghost sm suggest-btn" '
           f'data-target="v_{v["name"]}" '
           f'title="Показать варианты из прошлых документов">📋</button>'
           if v["name"] not in NO_MEMORY_VARS else "")
        + '</div>'
        # dropdown с вариантами (скрыт по умолчанию)
        + ('<div class="var-dropdown" id="dd_' + v["name"] + '" style="display:none">'
           + '<div class="var-dropdown-header">'
           '<span>Варианты из прошлых документов</span>'
           f'<button type="button" class="btn ghost sm" onclick="closeDropdown(\'{v["name"]}\')">✕</button>'
           '</div>'
           '<div class="var-dropdown-list">'
           + "".join(
               f'<div class="var-option" data-value="{str(s["value"]).replace(chr(34), "&quot;")}" '
               f'onclick="pickValue(\'v_{v["name"]}\', this.dataset.value)">'
               f'<span class="var-value">{str(s["value"])}</span>'
               f'<span class="var-meta">{s.get("used_count", 1)}× · {s.get("last_used", "")[:10]}</span>'
               '</div>'
               for s in db.get_suggestions(v["name"], 30)
           )
           + '</div>'
           + '</div>'
           if v["name"] not in NO_MEMORY_VARS else '')
        + '</div>'
        for v in variables) or '<div class="muted">У шаблона нет переменных</div>'

    # JavaScript для dropdowns
    fields += '''
<script>
function toggleDropdown(name) {
  const dd = document.getElementById('dd_' + name);
  if (!dd) return;
  // Закрыть все остальные
  document.querySelectorAll('.var-dropdown').forEach(d => {
    if (d.id !== 'dd_' + name) d.style.display = 'none';
  });
  dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
}
function closeDropdown(name) {
  const dd = document.getElementById('dd_' + name);
  if (dd) dd.style.display = 'none';
}
function pickValue(inputId, value) {
  const inp = document.getElementById(inputId);
  if (inp) {
    inp.value = value;
    inp.dispatchEvent(new Event('input', {bubbles: true}));
    inp.dispatchEvent(new Event('change', {bubbles: true}));
  }
  closeDropdown(inputId.replace('v_', ''));
}
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.suggest-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      toggleDropdown(this.dataset.target.replace('v_', ''));
    });
  });
  // Закрыть по клику вне
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.var-dropdown') && !e.target.closest('.suggest-btn')) {
      document.querySelectorAll('.var-dropdown').forEach(d => d.style.display = 'none');
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
.var-dropdown{position:relative;margin-top:6px;background:#fff;border:1px solid #dceee2;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.08);max-height:280px;overflow-y:auto;z-index:10}
.var-dropdown-header{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #dceee2;background:#f9fafb;font-size:12px;color:#666}
.var-dropdown-header button{padding:2px 6px;border:none;background:transparent;cursor:pointer;color:#666}
.var-option{padding:8px 12px;cursor:pointer;border-bottom:1px solid #f3f4f6;display:flex;flex-direction:column;gap:2px}
.var-option:hover{background:#f0fdf4}
.var-option:last-child{border-bottom:none}
.var-value{font-family:monospace;font-size:13px;color:#111}
.var-meta{font-size:11px;color:#666}
.var-hint{font-size:11px;margin-left:6px}
</style>
'''

    # ссылка на Google Drive клиента
    drive_url = (a.get("gdrive_url") or client.get("gdrive_folder_url") or "").strip()
    drive_link = ""
    if drive_url:
        drive_link = (f'<a class="btn block" target="_blank" rel="noopener" '
                      f'href="{drive_url}" style="margin-bottom:10px">📁 Открыть Google Drive клиента</a>')

    # Загрузим HTML для live-обновления
    html_for_live = ""
    html_path = Path('/opt/wolf_v2/data/templates') / tpl["code"] / "template.html"
    if html_path.exists():
        html_for_live = html_path.read_text(encoding="utf-8")
        # подсветим {{ var }} и подставим значения
        def _hl(m):
            name = m.group(1)
            val = str(values.get(name) or "")
            if val:
                safe = val.replace("&", "&").replace("<", "<").replace(">", ">").replace('"', chr(34) + chr(34))
                return '<span class="var-hl-filled" data-var="' + name + '">' + safe + "</span>"
            return '<span class="var-hl" data-var="' + name + '">{{ ' + name + ' }}</span>'
        html_for_live = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _hl, html_for_live)

    body = f"""
<div class="doc-edit-grid">
  <div class="doc-edit-left">
<h1>{tpl["title"]}</h1>
<div class="page-sub">Заявка #{app_id} · код <span class="mono">{tpl["code"]}</span> ·
  страниц {tpl["pages"] or 0} &middot;
  <span class="badge">{prev["status"] if prev else 'новый'}</span></div>
<div class="row tight" style="gap:8px;flex-wrap:wrap">
  <a class="btn ghost" href="/applications/{app_id}/review">&larr; К заявке</a>
  <button type="button" class="btn primary" id="autofill-btn"
          style="background:linear-gradient(135deg,#7C3AED,#EC4899);color:#fff;border:none">
    <span id="autofill-label">✨ Заполнить автоматически</span>
  </button>
  <button type="button" class="btn ghost" id="autofill-suggest-btn"
          title="Подставить рекомендации из прошлых документов (можно поправить вручную)">
    💡 Подсказать из опыта
  </button>
  <span id="autofill-status" class="muted" style="font-size:12px;margin-left:6px"></span>
</div>
{ui_card(f'Переменные · {len(variables)}', f'<div class="kv">{fields}</div>',
         emoji='\u270f\ufe0f', tone="blue", open=True)}
<div class="row tight" style="margin-top:10px;gap:8px">
  <button class="btn ok block" type="submit" name="action" value="verify" style="flex:2">\u2705 Сохранить и перегенерировать PDF</button>
  {('<a class="btn block" target="_blank" href="/templates/file/renders/' + Path(prev["pdf_path"]).name + '" style="flex:1;text-decoration:none;background:#FFF7ED;color:#9A3412;border:1px solid #FDBA74">\U0001f4c4 Открыть PDF</a>') if (prev and prev.get("pdf_path")) else ''}
</div>
  </div>
  <div class="doc-edit-right">
{ui_card("Предпросмотр HTML (живой)",
         (('<div class="zp-preview" data-zoom-pan><div id="app-preview-stage" class="doc-html-stage">' + html_for_live + '</div></div>')
          if html_for_live else '<div class="muted" style="padding:14px;text-align:center">HTML не сконвертирован.<br>Сначала конвертируйте шаблон в «Шаблоны».</div>'),
         emoji='\U0001f4dd', tone="green", open=True)}
{ui_card("Предпросмотр PDF",
         ((f'<div class="zp-preview" data-zoom-pan><iframe class="pdf-preview" style="width:794.5px;height:1123px;border:0" src="/templates/file/renders/{Path(prev["pdf_path"]).name}"></iframe></div>')
          if prev and prev.get("pdf_path") else
          '<div class="muted" style="padding:18px;text-align:center">PDF ещё не сформирован.<br>Нажмите «Перегенерировать PDF».</div>'),
         emoji='\U0001f4c4', tone="amber", open=True)}
  </div>
</div>

<style>
.doc-edit-grid {{
  display: grid;
  grid-template-columns: minmax(0, 0.7fr) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
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
  color: #78350F; font-weight: 700;
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
  const el = document.getElementById(inputId);
  if (el) {{ el.value = s; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
}}

// Live-обновление HTML-stage при изменении input
(function() {{
  const stage = document.getElementById('doc-html-stage');
  if (!stage) return;
  function refresh() {{
    const placeholders = stage.querySelectorAll('.var-hl, .var-hl-filled');
    placeholders.forEach(function(ph){{
      const name = ph.dataset.var;
      if (!name) return;
      const inp = document.querySelector('input[name="' + name + '"]');
      const val = inp ? inp.value.trim() : '';
      if (val) {{
        const safe = val.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
        ph.className = 'var-hl-filled';
        ph.textContent = safe;
      }} else {{
        ph.className = 'var-hl';
        ph.textContent = '{{ ' + name + ' }}';
      }}
    }});
  }}
  document.querySelectorAll('input[name]').forEach(function(inp){{
    inp.addEventListener('input', function(){{
      clearTimeout(window.__docLive);
      window.__docLive = setTimeout(refresh, 80);
    }});
  }});
  refresh();

  // === Autofill из 3 источников (auto / suggested / manual_only) ===
  const autofillBtn = document.getElementById('autofill-btn');
  const suggestBtn = document.getElementById('autofill-suggest-btn');
  const status = document.getElementById('autofill-status');
  const APP_ID = {app_id};
  const TEMPLATE_ID = {template_id};

  function showStatus(text, color) {{
    if (!status) return;
    status.style.color = color || '#374151';
    status.textContent = text;
  }}

  function setInput(name, value, source, highlightType) {{
    const inp = document.querySelector('input[name="' + name + '"]');
    if (!inp) return false;
    const prev = inp.value;
    inp.value = value;
    // подсветка источника
    inp.style.transition = 'background 0.5s';
    inp.style.background = highlightType === 'auto' ? '#DCFCE7'
                          : highlightType === 'suggest' ? '#FEF3C7'
                          : highlightType === 'gen' ? '#EDE9FE' : '';
    inp.title = source ? 'Источник: ' + source : '';
    setTimeout(function() {{ inp.style.background = ''; }}, 2500);
    if ((highlightType === 'auto' || highlightType === 'gen') && !prev) {{
      // отметим плашкой, откуда взято значение: данные клиента или правило
      let badge = inp.parentNode.parentNode.querySelector('.src-badge');
      if (!badge) {{
        badge = document.createElement('span');
        badge.className = 'src-badge';
        badge.style.cssText = 'display:inline-block;margin-left:6px;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;vertical-align:middle';
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
    return prev !== value;
  }}

  function fillByCategory(category, highlightType) {{
    const url = '/applications/' + APP_ID + '/doc/' + TEMPLATE_ID + '/autofill-values';
    fetch(url).then(r => r.json()).then(function(d) {{
      if (!d.ok) {{ showStatus('✗ ' + (d.error || 'ошибка'), '#dc2626'); return; }}
      let count = 0;
      const data = d[category] || {{}};
      Object.keys(data).forEach(function(name) {{
        const item = data[name];
        if (setInput(name, item.value, item.source, highlightType)) count++;
      }});
      showStatus('✓ Подставлено ' + count + ' полей (' + category + ')', '#16a34a');
    }}).catch(function(e) {{
      showStatus('✗ Сетевая ошибка: ' + e.message, '#dc2626');
    }});
  }}

  if (autofillBtn) autofillBtn.addEventListener('click', function() {{
    showStatus('⏳ Загружаю данные клиента и генерирую недостающие...', '#6b7280');
    fillByCategory('auto', 'auto');
    // поля, которых нет ни в документах, ни в заявке — генерируются по правилу
    setTimeout(function() {{ fillByCategory('generated', 'gen'); }}, 250);
  }});
  if (suggestBtn) suggestBtn.addEventListener('click', function() {{
    showStatus('⏳ Ищу в опыте прошлых документов...', '#6b7280');
    fillByCategory('suggested', 'suggest');
  }});
}})();
</script>
"""
    return render(tpl["title"], "dashboard", body)


@bp.route("/applications/<int:app_id>/text-file")
@login_required
def app_text_file(app_id: int):
    """Обычный текстовый файл заявки: сопроводительный текст менеджера.

    Тот же файл уходит на Google Drive вместе с готовыми документами, чтобы
    администратор видел комментарии прямо в папке клиента.
    """
    a = db.application_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))
    p = Path("/opt/wolf_v2/data/app_files") / ("app_" + str(app_id)) / "Заявка.txt"
    if not p.is_file():
        _client = db.client_get(a["client_id"]) or {}
        _prod = db.q1("SELECT code, name FROM products WHERE id=?", (a.get("product_id"),)) if a.get("product_id") else None
        _rp = {}
        try:
            _rp = json.loads(a["raw_payload"]) if a.get("raw_payload") else {}
        except Exception:
            _rp = {}
        _lines = [
            "ЗАЯВКА №" + str(app_id),
            "=" * 60,
            "Клиент: " + (db.client_label(_client) or "—"),
            "Клиент (латиницей): " + (_client.get("full_name_latin") or "—"),
            "Продукт: " + ((_prod["code"] + " — " + (_prod["name"] or "")) if _prod else (a.get("product_name") or "не определён")),
            "Стоимость: " + (str(a.get("price_idr")) + " IDR" if a.get("price_idr") else "не указана"),
            "Ссылка на Google Drive: " + (a.get("gdrive_url") or _client.get("gdrive_folder_url") or "—"),
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


@bp.route("/applications/<int:app_id>/send", methods=["POST"])
@login_required
def app_send(app_id: int):
    """Отправка пакета: подтверждённые документы → папка клиента на Google Диске.

    HTML-форма (обычный POST) получает flash + redirect, окно «Готовые доки»
    (fetch) — JSON со ссылкой на папку. Документы НЕ помечаются отправленными,
    если Диск не принял файлы: иначе в истории появилась бы ложная отправка.

    Каждый запуск логируется в events: 'send_start', 'send_ok', 'send_fail'.
    """
    want_json = request.headers.get("X-Requested-With") == "fetch"
    actor = (current_user() or {}).get("login", "") or "admin"
    a = apps_repo.get(app_id) or {}
    client = db.client_get(a.get("client_id")) or {}
    drive = (a.get("gdrive_url") or client.get("gdrive_folder_url") or "").strip()
    db.log_event("application", app_id, "send_start",
                 actor=actor, payload={"want_json": want_json, "drive": bool(drive)})
    # Единый импорт фасада шагов — замена 5 повторяющихся блоков from+step.
    try:
        from services.steps import ok as _st_ok, run as _st_run, fail as _st_fail
    except Exception:
        _st_ok = _st_run = _st_fail = (lambda *a, **kw: None)

    def _fail(msg: str):
        # Каждая ошибка отправки логируется — иначе в логе только успехи.
        db.log_event("application", app_id, "send_fail",
                     actor=actor, payload={"msg": msg[:200], "errors": errors[:3] if errors else []})
        if want_json:
            return jsonify({"ok": False, "error": msg, "link": drive}), 200
        flash(msg, "error")
        return redirect(url_for("dashboard.app_view", app_id=app_id))

    _rows = db.q("SELECT status FROM application_documents WHERE application_id=?", (app_id,))
    _decided = sum(1 for r in _rows
                   if ((r["status"] if not isinstance(r, (list, tuple)) else r[0]) or "")
                   in ("verified", "rejected", "sent"))
    if not _rows or _decided < len(_rows):
        return _fail("Не все документы проверены: согласовано %s из %s" % (_decided, len(_rows)))
    # Проверка готовности через единый фасад services.documents
    try:
        from services.documents import all_missing as _all_missing
        _miss_send = sorted({m for entry in _all_missing(app_id) for m in entry["missing"]})
    except Exception:
        _miss_send = sorted({m for d in db.application_documents(app_id)
                             if (d.get("status") or "") not in ("verified", "sent", "rejected")
                             for m in doc_missing_fields(app_id, d["template_id"])})
    if _miss_send:
        return _fail("Нельзя отправить: не заполнены поля — " + ", ".join(_miss_send[:6]))

    # Финишная проверка пакета: наши документы + то, что реально лежит в папке клиента на Диске.
    # Не прошла — файлы на Диск не уходят, в систему возвращается список нестыковок по документам.
    # Единый запуск всех трёх проверок через services.checks.
    # До этого здесь стояли три блока try/except (doc_check + autofix + recheck,
    # pdf_quality, logical_check) — 60 строк копипасты.
    try:
        from services.checks import run_all as _checks_run_all
        _all_ok, _all_findings = _checks_run_all(app_id)
        if not _all_ok:
            _msg = ("Проверка не пройдена: %d замечаний. Файлы на Диск не отправлены."
                    % len(_all_findings))
            if want_json:
                return jsonify({"ok": False, "error": _msg, "check": True,
                                "findings": _all_findings, "link": drive}), 200
            return _fail(_msg + " " + "; ".join(
                (f.get("doc", "") or f.get("rule", "?")) + ": " + (f.get("msg", "") or "")
                for f in _all_findings[:3]))
    except Exception as _exc:                            # noqa: BLE001
        current_app.logger.warning("checks failed: %s", _exc)

    pdfs = []
    for d in db.application_documents(app_id):
        if (d.get("status") or "") in ("verified", "sent"):
            p = _ready_doc_pdf(app_id, d["template_id"])
            if p and Path(p).exists():
                pdfs.append(Path(p))
    if not pdfs:
        return _fail("Нет подтверждённых документов с готовым PDF")
    if not drive:
        return _fail("В заявке нет ссылки на папку клиента на Google Диске")

    uploaded, errors = [], []
    folder_link = drive
    try:
        from services import gdrive_write
        # Документы уходят не в корень папки клиента, а в отдельную папку заявки:
        # «номер заявки + тип продукта + имя клиента + дата создания».
        sub_name = _ready_folder_name(app_id, a, client)
        try:
            _st_ok(app_id, "send_folder", f"создаю папку «{sub_name}»", actor=actor)
        except Exception:
            pass
        sub = _find_app_folder(gdrive_write, drive, sub_name, a, client, app_id) or \
              gdrive_write.ensure_folder(drive, sub_name)
        sub_id = (sub or {}).get("id") or drive
        folder_link = "https://drive.google.com/drive/folders/" + str(sub_id)
        # Чистим прежние версии этих же документов: имя файла содержит имя клиента и дату,
        # поэтому обновление не перезаписывало старый файл и в папке копились дубли.
        try:
            def _doc_key(name: str) -> str:
                return re.split(r'\s*(?:KOBLIKOVA|MUR|[A-Z]{3,}(?:\s+[A-Z]{3,})*)\s', name)[0].strip().lower()
            keys = {_doc_key(x.name) for x in pdfs}
            for item in gdrive_write.list_folder_contents(sub_id):
                nm = item.get('name') or ''
                if item.get('mimeType', '').endswith('folder') or nm.endswith('.txt'):
                    continue
                if _doc_key(nm) in keys and nm not in {x.name for x in pdfs}:
                    gdrive_write._get_service().files().delete(fileId=item['id']).execute()
        except Exception as _e_dedup:
            pass
        try:
            _st_run(app_id, "send_upload", f"загружаю {len(pdfs)} PDF", actor=actor)
        except Exception:
            pass
        for p in pdfs:
            try:
                gdrive_write.upload_file(sub_id, p, name=p.name, overwrite=True)
                uploaded.append(p.name)
                try:
                    _st_ok(app_id, "send_upload_file", p.name, actor=actor)
                except Exception:
                    pass
            except Exception as exc:
                errors.append(p.name + ": " + str(exc)[:120])
                try:
                    _st_fail(app_id, "send_upload_file", str(exc)[:120], actor=actor)
                except Exception:
                    pass
        # Вместе с документами уходит txt с точь-в-точь текстом заявки,
        # как её прислал менеджер в Telegram (для сверки и истории).
        try:
            rmsg = db.q1("SELECT raw_message FROM applications WHERE id=?", (app_id,)) or {}
            rmsg = str((rmsg or {}).get("raw_message") or "").strip()
            if rmsg:
                head = ("Application #%s\nCreated: %s\nClient: %s\n\n"
                        "--- request text as sent in Telegram ---\n\n"
                        % (app_id, str(a.get("created_at") or "")[:19],
                           (client.get("full_name_latin") or client.get("full_name") or "").strip()))
                txt_name = "Application #%s - request text (Telegram).txt" % app_id
                gdrive_write.upload_bytes(sub_id, (head + rmsg + "\n").encode("utf-8"),
                                          txt_name, "text/plain", overwrite=True)
                uploaded.append(txt_name)
                try:
                    _st_ok(app_id, "send_upload_txt", txt_name, actor=actor)
                except Exception:
                    pass
        except Exception as exc:
            errors.append("request text: " + str(exc)[:120])
    except Exception as exc:
        errors.append(str(exc)[:200])
    if errors or not uploaded:
        return _fail("Google Диск не принял файлы: " + _drive_hint("; ".join(errors[:3])))

    for d in db.application_documents(app_id):
        if d["status"] in ("filled", "verified"):
            db.application_doc_set(d["id"], "sent")
    # Заявка → в архив только при ЧИСТОЙ отправке (правило 17.10.2026).
    # Если были ошибки — _fail() выше уже ушёл, мы сюда не дошли.
    db.application_set_status(app_id, "sent")
    db.exec_sql("UPDATE applications SET record_kind='archive' WHERE id=?", (app_id,))
    # Тому, кто прислал заявку: документы готовы и лежат на Google Диске (со ссылкой).
    try:
        from services.notifier import notify as _notify
        _notify("done", app_id, folder_link=folder_link)
    except Exception as exc:                            # noqa: BLE001
        current_app.logger.warning("notify(done) failed: %s", exc)
    db.log_event("application", app_id, "send_ok",
                 actor=actor, payload={"uploaded": uploaded, "link": folder_link,
                                       "errors": errors[:3] if errors else []})
    if want_json:
        return jsonify({"ok": True, "uploaded": uploaded, "link": folder_link,
                        "hint": "Документы отправлены на Google Диск"}), 200
    flash("Отправлено на Google Диск: " + str(len(uploaded)) + " файл(ов) — папка заявки")
    return redirect(url_for("dashboard.app_view", app_id=app_id))


# ── Готовые документы: контрольная проверка перед отправкой ─────────────────────
def _drive_hint(err: str) -> str:
    """Человеческая причина отказа Google Диска вместо технического текста."""
    e = err or ""
    low = e.lower()
    if "storage quota" in low or "storagequota" in low:
        return ("у робота Google нет своей квоты на запись. Нужно либо перенести папки "
                "клиентов в общий диск (Shared Drive) и расшарить роботу, либо подключить "
                "отправку от вашего аккаунта (OAuth-токен). Файлы при этом не потеряны — "
                "они лежат в `data/ready`.")
    if "insufficient" in low or "permission" in low:
        return ("у робота нет прав на папку: проверьте, что папка клиента расшарена на "
                "wolf-drive@wolf-autodoc.iam.gserviceaccount.com с правом «Редактор»")
    if "not found" in low or "404" in e:
        return "папка клиента на Google Диске не найдена — проверьте ссылку в заявке"
    return e


def _find_app_folder(gdrive_write, drive: str, sub_name: str, a: dict, client: dict, app_id: int = 0):
    """Существующая папка заявки/клиента: точное имя, иначе — та же пара клиент+продукт.

    Распоряжение заказчика: если папка уже есть — перезаливать документы в неё,
    даже когда заявка пришла заново с новым номером.
    """
    try:
        found = gdrive_write.find_file_in_folder(drive, sub_name)
        if found and found.get("id"):
            return found
    except Exception:
        pass
    try:
        # Папка этой же заявки, но со старым именем (в прежних сборках в имя
        # добавлялась дата) — иначе повторный прогон создаст вторую папку.
        items0 = gdrive_write.list_folder_contents(drive) or []
        for it in items0:
            if it.get("mimeType") != "application/vnd.google-apps.folder":
                continue
            if ("№%d " % app_id) in (it.get("name") or ""):
                return it
        name = (client.get("full_name_latin") or "").strip() or " ".join(
            x for x in [(client.get("surname") or "").strip(), (client.get("name") or "").strip()] if x).strip()
        code = ""
        try:
            pr = db.q1("SELECT code FROM products WHERE id=?", (a.get("product_id"),)) or {}
            code = str(pr.get("code") or "").strip()
        except Exception:
            code = ""
        items = gdrive_write.list_folder_contents(drive) or []
        for it in items:
            if it.get("mimeType") != "application/vnd.google-apps.folder":
                continue
            nm = it.get("name") or ""
            if name and name in nm and (not code or ("/ " + code) in nm or nm.endswith(code)):
                return it
    except Exception:
        pass
    return None


def _ready_folder_name(app_id: int, a: dict, client: dict) -> str:
    """Имя папки отправки: номер заявки, тип продукта, имя клиента, дата создания."""
    code = ""
    try:
        pr = db.q1("SELECT code, name FROM products WHERE id=?", (a.get("product_id"),)) or {}
        code = str(pr.get("code") or "").strip()
    except Exception:
        code = ""
    name = (client.get("full_name_latin") or "").strip()
    if not name:
        name = " ".join(x for x in [(client.get("surname") or "").strip(),
                                    (client.get("name") or "").strip()] if x).strip()
    if not name:
        name = str(client.get("full_name") or "").strip() or "CLIENT"
    made = str(a.get("created_at") or "")[:10]
    try:
        made = datetime.strptime(made, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        pass
    # Формат Андрея: «Wolf AutoDoc №<заявка> <клиент> / <продукт>».
    # Дата в имени не ставится: повторный прогон должен перезаливать те же файлы
    # в ту же папку, а не плодить вторую.
    return "Wolf AutoDoc \u2116%s %s / %s" % (app_id, name, code or "PRODUCT")


def _ready_docs(app_id: int) -> list:
    """Подтверждённые документы заявки: английское имя файла, шаблон, дата."""
    # Порядок и номера — как в базе: templates.doc_index (номер документа в наборе),
    # а не порядковый номер в списке.
    rows = db.q("""SELECT d.*, t.code AS tpl_code, t.title AS tpl_title,
                          COALESCE(t.doc_index, t.id) AS tpl_index
                   FROM application_documents d JOIN templates t ON t.id = d.template_id
                   WHERE d.application_id=? AND IFNULL(d.status,'') IN ('verified','sent')
                   ORDER BY COALESCE(t.doc_index, 999), t.id""", (app_id,))
    a = apps_repo.get(app_id) or {}
    client = db.client_get(a.get("client_id")) or {}
    today = datetime.now().strftime("%d.%m.%Y")
    out = []
    for ad in rows:
        code = ad.get("tpl_code") or ""
        values = {}
        try:
            values = json.loads(ad.get("values_json") or "{}")
        except Exception:
            values = {}
        try:
            values.update(build_template_values(client, code, values))
        except Exception:
            pass
        title = doc_render.doc_title_en(code, ad.get("tpl_title") or "")
        try:
            name = doc_render.doc_filename(title, values, code=code)
        except Exception:
            name = (title or code or "document") + " " + today + ".pdf"
        out.append({"tpl": ad.get("template_id"), "title": title, "name": name,
                    "date": today, "status": ad.get("status"),
                    "num": ad.get("tpl_index") or ad.get("template_id")})
    return out


def _ready_doc_pdf(app_id: int, template_id: int):
    """PDF подтверждённого документа ровно в том виде, который зафиксировали галочкой.

    Источник — слепок `data/frozen/app<N>_tpl<M>.html`; если слепка нет (старые
    заявки) — сборка из значений документа тем же рендером, что и конструктор.
    """
    info = next((x for x in _ready_docs(app_id) if x["tpl"] == template_id), None)
    tpl = tpl_repo.get(template_id) or {}
    frozen = Path("/opt/wolf_v2/data/frozen") / ("app%s_tpl%s.html" % (app_id, template_id))
    tpl_html = Path("/opt/wolf_v2/data/templates") / str(tpl.get("code") or "") / "template.html"
    src = frozen if frozen.exists() else tpl_html
    if not src.exists():
        return None
    out_dir = Path("/opt/wolf_v2/data/ready")
    out_dir.mkdir(parents=True, exist_ok=True)

    # То же и для PDF: строим из текущего слепка, а не из кэша HTML.
    for _c in Path("/opt/wolf_v2/data/doc_html").glob("app%s_tpl%s_*.html" % (app_id, template_id)):
        try:
            _c.unlink()
        except Exception:
            pass
    name = (info or {}).get("name") or (str(tpl.get("code") or "doc") + ".pdf")
    out_pdf = out_dir / name
    try:
        if out_pdf.exists() and out_pdf.stat().st_size > 1000 and out_pdf.stat().st_mtime >= src.stat().st_mtime:
            return out_pdf
        html = src.read_text(encoding="utf-8")
        if not frozen.exists():
            a = apps_repo.get(app_id) or {}
            client = db.client_get(a.get("client_id")) or {}
            values = {}
            ad = db.q1("""SELECT values_json FROM application_documents
                          WHERE application_id=? AND template_id=? ORDER BY id DESC LIMIT 1""",
                       (app_id, template_id)) or {}
            try:
                values = json.loads(ad.get("values_json") or "{}")
            except Exception:
                values = {}
            try:
                values.update(build_template_values(client, str(tpl.get("code") or ""), values,
                                                    app_id=app_id))
            except Exception:
                pass
            html = doc_render.fill(html, values, keep_unfilled=False, template_code=tpl.get("code"))
        # base_dir обязателен: подложки листов (bg-1.png…) подключены относительными
        # путями, без него фон в готовом PDF молча пропадал.
        _frame = Path("/opt/wolf_v2/data/templates") / str(tpl.get("code") or "") / "frame"
        doc_render.render_pdf(html, out_path=out_pdf,
                              base_dir=(_frame if _frame.exists() else None))
    except Exception as exc:
        print("ready-pdf error app=%s tpl=%s: %s" % (app_id, template_id, exc))
        return None
    return out_pdf if out_pdf.exists() else None


@bp.route("/applications/<int:app_id>/ready-docs")
@login_required
def app_ready_docs(app_id: int):
    """Список подтверждённых документов заявки для окна «Готовые доки»."""
    return jsonify({"ok": True, "docs": _ready_docs(app_id)}), 200


def rebuild_application_documents(app_id: int, actor: str = "") -> dict:
    """Пересобрать все подтверждённые документы заявки — после правки её комментария.

    Возвращает названия пересобранных документов и ошибки сборки.
    """
    rebuilt, failed = [], []
    try:
        # Пересобираем все документы заявки, кроме отклонённых: и подтверждённые,
        # и ещё не проверенные (filled) — правка комментария меняет их все.
        rows = db.q("""SELECT t.id, t.code, t.title
                         FROM application_documents ad
                         JOIN templates t ON t.id = ad.template_id
                        WHERE ad.application_id=?
                          AND COALESCE(ad.status,'') NOT IN ('rejected','hidden','merged')
                        GROUP BY t.id""", (app_id,))
        if not rows:
            rows = db.q("""SELECT t.id, t.code, t.title
                             FROM application_documents ad
                             JOIN templates t ON t.id = ad.template_id
                            WHERE ad.application_id=? GROUP BY t.id""", (app_id,))
    except Exception:
        rows = []
    for r in rows:
        try:
            freeze_document(app_id, r["id"], actor=actor or "пересборка заявки")
            rebuilt.append(r.get("title") or r.get("code"))
        except Exception as exc:  # noqa: BLE001
            failed.append("%s: %s" % (r.get("code"), str(exc)[:90]))
    return {"rebuilt": rebuilt, "failed": failed}


@bp.route("/applications/<int:app_id>/fix-docs", methods=["POST"])
@login_required
def app_fix_docs(app_id: int):
    """«Исправить» из окна проверки: пересобрать документы и сбросить осевшие значения.

    Проверка перед отправкой возвращает документы в редактор — администратору нужна
    не только причина, но и кнопка, которая это лечит. Пересобираем документы с
    текущими правилами, предварительно сбросив сохранённые значения (в них оседают
    старые подстановки вроде Occupation = Manager, из-за которых проверка и падала).
    """
    from flask import jsonify as _jsonify, request as _rq
    try:
        rows = db.q("""SELECT t.id AS tid, t.code, t.doc_index FROM application_documents ad
                         JOIN templates t ON t.id = ad.template_id
                        WHERE ad.application_id=? AND COALESCE(ad.status,'') NOT IN ('rejected','hidden','merged')
                        GROUP BY t.id""", (app_id,))
    except Exception:
        rows = []
    code_filter = str(_rq.args.get("code") or "").strip()      # необязательно: только один документ
    fixed, failed = [], []
    for r in rows:
        if code_filter and code_filter not in str(r.get("code") or ""):
            continue
        try:
            # сбрасываем осевшие значения: иначе пересборка повторит старую подстановку
            db.exec_sql("""UPDATE application_documents SET values_json='{}'
                            WHERE application_id=? AND template_id=?""", (app_id, r["tid"]))
            freeze_document(app_id, r["tid"], actor="автоисправление из окна проверки")
            fixed.append({"code": r.get("code"), "num": r.get("doc_index")})
        except Exception as exc:  # noqa: BLE001
            failed.append("%s: %s" % (r.get("code"), str(exc)[:90]))
    return _jsonify({"ok": True, "fixed": fixed, "failed": failed}), 200


@bp.route("/applications/<int:app_id>/brief", methods=["POST", "GET"])
@login_required
def app_brief(app_id: int):
    """Комментарий заявки (свободный текст) — правит сборку документов «на лету».

    GET  — текущий комментарий и что заявлено в нём (должность, сфера).
    POST — сохранить комментарий и пересобрать все подтверждённые документы заявки:
           должность уходит в резюме и договор, по сфере подбирается организация.
    """
    from flask import Response as _Resp, request as _rq
    if _rq.method == "GET":
        row = db.q1("SELECT brief FROM applications WHERE id=?", (app_id,)) or {}
        brief = str(row.get("brief") or "")
        parsed = {}
        try:
            from services import brief_values as _bv
            _ru, _en = _bv.parse_position(brief)
            parsed = {"position": _en or _ru, "sphere": _bv.parse_sphere(brief)}
        except Exception:
            pass
        return jsonify({"ok": True, "brief": brief, "parsed": parsed}), 200

    data = _rq.get_json(silent=True) or {}
    brief = str(data.get("brief") if data.get("brief") is not None else _rq.form.get("brief") or "")
    brief = brief.strip()[:2000]
    db.exec_sql("UPDATE applications SET brief=? WHERE id=?", (brief, app_id))
    rebuilt, failed = [], []
    try:
        reb = rebuild_application_documents(app_id, actor="комментарий заявки")
        rebuilt, failed = reb.get("rebuilt") or [], reb.get("failed") or []
    except Exception as exc:  # noqa: BLE001
        failed.append(str(exc)[:120])
    try:
        from services.doc_check import check_package
        verdict, finds = check_package(app_id, with_drive=False)
        blocks = [f for f in finds if f.get("level") == "BLOCK"]
    except Exception:
        verdict, blocks = {"ok": None, "summary": ""}, []
    return jsonify({"ok": True, "brief": brief, "rebuilt": rebuilt, "failed": failed,
                    "verdict": verdict, "findings": blocks[:8]}), 200


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/ready-pdf")
@login_required
def app_doc_ready_pdf(app_id: int, template_id: int):
    """PDF подтверждённого документа — показывается в окне «Готовые доки».

    ?download=1 — отдать файлом (кнопка «скачать» у документа в списке), иначе
    показывается в браузере, как раньше.
    """
    from flask import Response as _Resp, request as _rq
    p = _ready_doc_pdf(app_id, template_id)
    if not p or not Path(p).exists():
        return _Resp("PDF не собран", status=404)
    as_file = str(_rq.args.get("download") or "") in ("1", "true", "yes")
    return send_file(str(p), mimetype="application/pdf", as_attachment=as_file,
                     download_name=Path(p).name)


@bp.route("/applications/<int:app_id>/doc/<int:template_id>/ready-img/<int:page_no>")
@login_required
def app_doc_ready_img(app_id: int, template_id: int, page_no: int):
    """Страница готового PDF картинкой.

    Нужна, чтобы окно «Готовые доки» показывало ВСЕ документы одной полосой в
    одном визоре: без вложенных окон просмотра, обычной прокруткой страницы.
    Отдаёт 404, когда страницы кончились — по этому сигналу клиент останавливается.
    """
    from flask import Response as _Resp
    p = _ready_doc_pdf(app_id, template_id)
    if not p or not Path(p).exists():
        return _Resp("PDF не собран", status=404)
    cache_dir = Path("/opt/wolf_v2/data/ready/img")
    cache_dir.mkdir(parents=True, exist_ok=True)
    img = cache_dir / ("%s_p%d.png" % (Path(p).stem, page_no))
    try:
        if img.exists() and img.stat().st_size > 500 and img.stat().st_mtime >= Path(p).stat().st_mtime:
            return send_file(str(img), mimetype="image/png")
        try:
            import pymupdf as fitz
        except Exception:
            import fitz  # noqa: F401
        doc = fitz.open(str(p))
        try:
            if page_no < 1 or page_no > doc.page_count:
                return _Resp("нет такой страницы", status=404)
            pix = doc.load_page(page_no - 1).get_pixmap(dpi=110)
            pix.save(str(img))
        finally:
            doc.close()
    except Exception as exc:
        print("ready-img error app=%s tpl=%s p=%s: %s" % (app_id, template_id, page_no, exc))
        return _Resp("не удалось отрисовать страницу", status=500)
    if not img.exists():
        return _Resp("не удалось отрисовать страницу", status=500)
    return send_file(str(img), mimetype="image/png")
