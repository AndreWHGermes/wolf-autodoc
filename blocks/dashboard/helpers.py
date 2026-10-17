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
        <span class="app-timer{' running' if _is_running(a) else ''}" data-elapsed="{_elapsed(a)}" data-running="{_is_running(a)}"
          title="{'идёт обработка — ' + _fmt_elapsed(a) if _is_running(a) else 'прошло с момента приёма — ' + _fmt_elapsed(a)}">
          {_spinner_html(a)}
          <span class="app-timer-text">⏱ {_fmt_elapsed(a)}</span>
        </span>
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


def render_spinner_html(a) -> str:
    """Колёсико-спиннер рядом с таймером: крутится только когда заявка в работе."""
    from blocks.dashboard import page as _page
    running = bool(_page._is_running(a))
    if running:
        return ('<span class="app-spinner" aria-label="идёт обработка">'
                '<span class="app-spinner-circle"></span></span>')
    return '<span class="app-spinner-placeholder"></span>'


# Алиас для краткости в inbox_row
_spinner_html = render_spinner_html


# CSS для крупного таймера + спиннера.
# Вставляется на страницу через _emit_timer_css() при первом рендере inbox_row.
_TIMER_CSS = """
<style id="wolf-timer-css">
  .app-timer {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: 8px;
    padding: 4px 10px;
    background: #E8EEF9;
    color: #1F3A93;
    border-radius: 8px;
    font-weight: 700;
    font-size: 16px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .app-timer.running {
    background: #DBEAFE;
    color: #1D4ED8;
    box-shadow: 0 0 0 2px rgba(29, 78, 216, 0.15);
  }
  .app-timer-text { white-space: nowrap; }
  .app-spinner {
    width: 16px;
    height: 16px;
    flex: 0 0 16px;
    position: relative;
    display: inline-block;
  }
  .app-spinner-circle {
    position: absolute;
    inset: 0;
    border: 2.5px solid #C7D5F0;
    border-top-color: #1D4ED8;
    border-radius: 50%;
    animation: wolfspin .8s linear infinite;
  }
  .app-spinner-placeholder {
    display: inline-block;
    width: 16px;
    height: 16px;
    flex: 0 0 16px;
  }
  @keyframes wolfspin {
    to { transform: rotate(360deg); }
  }
</style>
"""


def _emit_timer_css() -> str:
    """Возвращает CSS для таймера (один раз на страницу)."""
    return _TIMER_CSS


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


def auto_switch_html() -> str:
    """Кнопки управления всей автоматикой: Старт и Пауза.

    Перенесено из blocks/dashboard/page.py:343 без правок.
    """
    from blocks.dashboard.page import auto_mode, AUTO_ON
    on = auto_mode() == AUTO_ON
    return f"""
<div class="auto-switch" id="auto-switch" data-mode="{'on' if on else 'pause'}">
  <span class="auto-lbl">Автоматика</span>
  <button type="button" class="asw-btn start{' active' if on else ''}" data-mode="on"
    title="Заявки уходят в работу сразу после поступления">▶ Старт</button>
  <button type="button" class="asw-btn stopr{' active' if not on else ''}" data-mode="pause"
    title="Новые заявки стоят и ждут запуска">⏸ Пауза</button>
  <span class="auto-state" id="auto-state">{'включена' if on else 'на паузе'}</span>
</div>"""


def _inbox_script() -> str:
    """Кнопки главной работают без перезагрузки: страница не «моргает».

    Перенесено из blocks/dashboard/page.py:357 без правок.
    """
    return """
<script>
(function () {
  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: {'X-Requested-With': 'fetch', 'Content-Type': 'application/x-www-form-urlencoded'},
      body: body || '', credentials: 'same-origin'
    }).then(function (r) { return r.json().catch(function () { return {}; }); });
  }
  function applyRow(row, res) {
    if (!row || !res || !res.ok) return;
    row.dataset.state = res.state || '';
    var chip = row.querySelector('.prow');
    if (chip && res.progress) { chip.outerHTML = res.progress; }
    var btn = row.querySelector('.ibtn.go, .ibtn.pause');
    if (btn) {
      if (res.queued) {
        btn.dataset.act = 'pause'; btn.className = 'ibtn pause'; btn.textContent = '⏸ Пауза';
      } else {
        btn.dataset.act = 'start'; btn.className = 'ibtn go'; btn.textContent = '▶ В работу';
      }
    }
  }
  function syncRow(row, d) {
    if (!row) return;
    row.dataset.state = d.state || '';
    var pr = row.querySelector('.prow');
    if (pr && d.progress && pr.outerHTML !== d.progress) { pr.outerHTML = d.progress; }
    var det = row.querySelector('details.stages');
    if (d.steps) {
      if (!det) {
        var host = row.querySelector('.inbox-top');
        if (host) { host.insertAdjacentHTML('afterend', d.steps); }
      } else {
        var open = det.open;
        det.outerHTML = d.steps;
        var nd = row.querySelector('details.stages');
        if (nd) { nd.open = open; }
      }
    }
    var b = row.querySelector('.ibtn.go, .ibtn.pause');
    if (b) {
      if (d.queued) { b.dataset.act = 'pause'; b.className = 'ibtn pause'; b.textContent = '⏸ Пауза'; }
      else { b.dataset.act = 'start'; b.className = 'ibtn go'; b.textContent = '▶ В работу'; }
    }
  }
  var _busy = false;
  function tick() {
    if (_busy || document.hidden) { return; }
    _busy = true;
    fetch('/live', {headers: {'X-Requested-With': 'fetch'}, credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res || !res.ok) { return; }
        (res.apps || []).forEach(function (d) {
          syncRow(document.querySelector('.inbox-row[data-app="' + d.id + '"]'), d);
        });
        var shown = document.querySelectorAll('.inbox-row').length;
        var got = (res.apps || []).length;
        if (got > shown) {
          var tip = document.getElementById('live-new');
          if (!tip) {
            tip = document.createElement('button');
            tip.id = 'live-new'; tip.type = 'button';
            tip.className = 'ibtn go';
            tip.style.cssText = 'margin:6px 2px;';
            tip.addEventListener('click', function () { location.reload(); });
            var head = document.querySelector('.inbox-head');
            if (head) { head.appendChild(tip); } else { document.body.prepend(tip); }
          }
          tip.textContent = '📥 Новая заявка (' + (got - shown) + ') — показать';
        } else {
          var t2 = document.getElementById('live-new');
          if (t2) { t2.remove(); }
        }
        var box = document.getElementById('auto-switch');
        if (box && res.mode) {
          if (box.dataset.mode !== res.mode) {
            box.dataset.mode = res.mode;
            box.querySelectorAll('.asw-btn').forEach(function (b) {
              b.classList.toggle('active', b.dataset.mode === res.mode);
            });
            var st = document.getElementById('auto-state');
            if (st) { st.textContent = (res.mode === 'on') ? 'включена' : 'на паузе'; }
          }
        }
      })
      .catch(function () {})
      .then(function () { _busy = false; });
  }
  setInterval(tick, 3000);
  setTimeout(tick, 800);

  document.addEventListener('click', function (ev) {
    var sw = ev.target.closest ? ev.target.closest('.asw-btn') : null;
    if (sw) {
      ev.preventDefault();
      var box = document.getElementById('auto-switch');
      post('/auto/mode', 'mode=' + encodeURIComponent(sw.dataset.mode)).then(function (res) {
        if (!res || !res.ok) { return; }
        box.dataset.mode = res.mode;
        box.querySelectorAll('.asw-btn').forEach(function (b) {
          b.classList.toggle('active', b.dataset.mode === res.mode);
        });
        var st = document.getElementById('auto-state');
        if (st) { st.textContent = (res.mode === 'on') ? 'включена' : 'на паузе'; }
      });
      return;
    }
    var btn = ev.target.closest ? ev.target.closest('.ibtn') : null;
    if (!btn) { return; }
    ev.preventDefault();
    ev.stopPropagation();
    var app = btn.dataset.app, act = btn.dataset.act;
    var row = document.querySelector('.inbox-row[data-app="' + app + '"]');
    if (act === 'archive') {
      post('/applications/' + app + '/archive', '').then(function (res) {
        if (!res || !res.ok || !row) { return; }
        row.style.opacity = '0';
        setTimeout(function () { row.remove(); }, 220);
      });
      return;
    }
    if (act === 'restart') {
      post('/applications/' + app + '/restart', '').then(function (res) {
        if (!res || !res.ok || !row) { return; }
        row.dataset.state = res.state || 'queued';
        var pr = row.querySelector('.prow');
        if (pr && res.progress) { pr.outerHTML = res.progress; }
        var b = row.querySelector('.ibtn.go, .ibtn.pause');
        if (b) { b.dataset.act = 'pause'; b.className = 'ibtn pause'; b.textContent = '⏸ Пауза'; }
      });
      return;
    }
    post('/applications/' + app + '/queue/' + act, '').then(function (res) { applyRow(row, res); });
  }, true);
})();
</script>
"""