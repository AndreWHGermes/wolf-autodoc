# blocks/dashboard/helpers.py
"""
Вспомогательные функции для главной страницы и страницы заявки.

Сюда выносятся САМЫЕ БОЛЬШИЕ функции HTML-построения, чтобы разгрузить
blocks/dashboard/page.py (4499 строк). Маленькие хелперы остаются в page.py
для обратной совместимости.

Этап 5 рефакторинга: разделение UI-слоя. Никаких правок логики — это чистая миграция.
"""

from __future__ import annotations
import html
from blocks.shared.layout import docs_state_html
from core import db


def inbox_row(a) -> str:
    """Карточка входящей заявки с кнопками: в работу / пауза / в архив.

    Перенесено из blocks/dashboard/page.py:335 без правок.
    Использует helpers из page.py: _queue_state, _ts_fmt, _err_list, _last_run,
    _elapsed, _is_running, _fmt_elapsed, kind_badge, progress_html, steps_html.
    """
    # Импортируем из page.py — они остаются там (пока)
    from blocks.dashboard.page import (
        _queue_state, _ts_fmt, _err_list, _last_run,
        _elapsed, _is_running, _fmt_elapsed,
        kind_badge, progress_html, steps_html,
    )

    def esc(v):
        return html.escape(str(v or ""), quote=True)

    app_id = a["id"]
    mgr = ""
    if a.get("manager_name") or a.get("manager_username"):
        name = a.get("manager_name") or a.get("manager_username") or ""
        uname = a.get("manager_username") or ""
        mgr = f'от {name}' + (f' (@{uname})' if uname else '')
    subs = [x for x in (mgr, a.get("product_name") or "продукт не указан",
                        _ts_fmt(a.get("created_at"))) if x]
    state = _queue_state(app_id)
    active = state in ("queued", "running")
    btn_main = ('<button type="button" class="ibtn pause" data-act="pause"'
                f' data-app="{app_id}" title="Остановить эту заявку">⏸ Пауза</button>'
                if active else
                '<button type="button" class="ibtn go" data-act="start"'
                f' data-app="{app_id}" title="Поставить эту заявку в работу">▶ В работу</button>')
    price = f' · IDR {a["price_idr"]:,}' if a.get("price_idr") else ''
    # Заявка, остановленная проверкой: даём кнопку повторного прогона по системе.
    _errs = _err_list(_last_run(app_id) or {})
    btn_restart = ('<button type="button" class="ibtn redo" data-act="restart"'
                   f' data-app="{app_id}" title="Прогнать заявку заново по системе">'
                   '🔄 Ещё раз</button>' if _errs else '')
    # Индикатор процесса слева от кнопки: крутится, пока заявка в работе;
    # замер на ошибке (крестик) или на завершении (галочка); часы — в очереди.
    if state == "running":
        _ind = ('<span class="spin" title="идёт обработка" style="display:inline-block;'
                'width:16px;height:16px;border:2px solid #C7D2FE;border-top-color:#1F6BFF;'
                'border-radius:50%;animation:spin 0.8s linear infinite"></span>')
    elif _errs:
        _ind = '<span title="остановлено по ошибке" style="font-size:15px">❌</span>'
    elif state in ("done", "sent"):
        _ind = '<span title="готово" style="font-size:15px">✅</span>'
    else:
        _ind = '<span title="в очереди" style="font-size:15px">🕓</span>'

    return f"""
<div class="inbox-row" data-app="{app_id}" data-state="{esc(state)}">
  <div class="inbox-top">
    <a class="inbox-main" href="/applications/{app_id}/review">
      <div class="inbox-title">Заявка #{app_id} · {esc(db.client_label(a))}{kind_badge(a)}
        <span class="app-timer" data-elapsed="{_elapsed(a)}" data-running="{_is_running(a)}"
          style="font-size:11.5px;font-weight:700;color:#1F3A93;background:#E8EEF9;
          border-radius:6px;padding:1px 7px;margin-left:6px">⏱ {_fmt_elapsed(a)}</span>
      </div>
      <div class="inbox-sub">{esc(" · ".join(subs))}{price}</div>
      {progress_html(app_id)}
      {('<span class="dchip wait">📄 черновики документов собраны при приёме — проверка запустится, когда заявка дойдёт до обработки</span>') if _queue_state(app_id) == 'queued' else docs_state_html(db.application_doc_summary(app_id))}
    </a>
    <div class="inbox-actions">{_ind}{btn_main}
      {btn_restart}
      <button type="button" class="ibtn arch" data-act="archive" data-app="{app_id}"
        title="Убрать из входящих: заявка останется в истории">🗄 В архив</button>
    </div>
  </div>
  {steps_html(app_id)}
</div>"""


def progress_html(app_id: int) -> str:
    """Ход работы заявки: очередь, обработка, ошибка, отправка на Google Диск.

    Перенесено из blocks/dashboard/page.py:300 без правок.
    """
    from blocks.dashboard.page import (
        _queue_state, _queue_positions, _last_run, _err_list,
        _where_now, _is_active_elsewhere,
    )
    q = _queue_state(app_id)
    pos = _queue_positions().get(int(app_id)) if q == "queued" else None
    run = _last_run(app_id) or {}
    errs = _err_list(run)
    parts = []
    if q == "running":
        now = _where_now(app_id)
        step = now.get("next") or now.get("last_ok") or str(run.get("stage") or "")
        parts.append('<span class="pchip run">⏳ обрабатывается'
                     + (f' · этап: {html.escape(step)}' if step else '') + '</span>')
    if q == "queued" and _is_active_elsewhere(app_id):
        parts.append('<span class="pchip wait">🕓 очередь №%s · сейчас обрабатывается другая заявка'
                     '</span>' % (pos or "?"))
    elif q == "queued":
        parts.append('<span class="pchip wait">🕓 очередь №%s</span>' % (pos or "?"))
    elif q == "paused":
        parts.append('<span class="pchip paused">⏸ пауза</span>')
    if run.get("sent"):
        files = run.get("files")
        parts.append('<span class="pchip done">✅ отправлено на Диск'
                     + (f' · файлов {int(files)}' if files else '') + '</span>')
    if errs:
        title = html.escape("; ".join(errs)[:600], quote=True)
        first = errs[0]
        short = first if len(first) <= 96 else first[:94] + "…"
        parts.append(f'<span class="pchip err" title="{title}">⚠ {html.escape(short)}</span>')
        if len(errs) > 1:
            parts.append(f'<span class="pchip err-more" title="{title}">ещё {len(errs) - 1}</span>')
    if not parts:
        parts.append('<span class="pchip idle">не в работе</span>')
    return '<div class="prow">' + "".join(parts) + '</div>'


def steps_html(app_id: int) -> str:
    """Этапы обработки заявки: сверху свежий этап, снизу первый; плюс текущее состояние.

    Перенесено из blocks/dashboard/page.py:247 без правок.
    """
    from blocks.dashboard.page import now_state, _ts_fmt, _steps_label
    try:
        from services import app_steps as _steps
        rows = _steps.trail(app_id, limit=40)
    except Exception:
        rows = []
    now = now_state(app_id)
    if not rows:
        return (f'<div class="now-state {html.escape(now["tone"])}">'
                f'<b>Сейчас: {html.escape(now["label"])}</b>'
                + (f'<span>{html.escape(now["note"])}</span>' if now["note"] else "") + "</div>") if now.get("label") else ""
    icon = {"ok": "✅", "warn": "⚠", "fail": "❌", "run": "⏳"}
    lines = []
    _prev = None
    for r in reversed(rows):
        _key = (r.get("step"), str(r.get("note") or "")[:80])
        if _key == _prev:
            continue
        _prev = _key
        ic = icon.get(r.get("status"), "•")
        note = html.escape(str(r.get("note") or ""))
        lines.append(f'<li>{ic} <b>{html.escape(_steps_label(r.get("step")))}</b> '
                     f'<span class="muted">{_ts_fmt(r.get("created_at"))}</span>'
                     + (f' — {note}' if note else '') + '</li>')
    banner = (f'<div class="now-state {html.escape(now["tone"])}">'
              f'<b>Сейчас: {html.escape(now["label"])}</b>'
              + (f'<span>{html.escape(now["note"])}</span>' if now["note"] else "")
              + (f'<span class="muted">{html.escape(now["docs"])}</span>' if now.get("docs") else "")
              + "</div>")
    return (f'<details class="stages"><summary>этапы ({len(rows)}) · сейчас: {html.escape(now["label"])}</summary>'
            f'{banner}<ol reversed>{"".join(lines)}</ol></details>')