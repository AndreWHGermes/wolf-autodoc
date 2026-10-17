"""Блок «История»: компактный плоский список заявок + поиск по клиенту/продукту."""
from __future__ import annotations

from flask import Blueprint
from flask import abort, jsonify, redirect, request, url_for

import html
import json

from blocks.shared.layout import render
from core import db
from core.auth import login_required

bp = Blueprint("history", __name__)


def _steps_modal() -> str:
    """Всплывающее окно с этапами заявки: открывается кнопкой «Этапы» в истории."""
    return """
<div id="steps-modal" style="display:none;position:fixed;inset:0;z-index:9999;
     background:rgba(15,23,42,.45);padding:16px">
  <div style="max-width:760px;margin:4vh auto;max-height:86vh;overflow:auto;background:#fff;
       border-radius:14px;padding:16px 18px;box-shadow:0 24px 70px rgba(0,0,0,.35)">
    <div style="position:sticky;top:0;z-index:3;background:#fff;display:flex;
         justify-content:space-between;align-items:center;gap:10px;padding:0 0 9px 0;
         margin-bottom:10px;border-bottom:1px solid #EDF0F5">
      <b style="font-size:15px">Этапы заявки <span id="steps-app" style="color:#1F3A93"></span></b>
      <button type="button" class="btn sm" id="steps-close">✕ Закрыть</button>
    </div>
    <div id="steps-body"><div class="muted">Загрузка…</div></div>
  </div>
</div>
<script>
(function () {
  var modal = document.getElementById('steps-modal');
  var body = document.getElementById('steps-body');
  function close() { modal.style.display = 'none'; body.innerHTML = ''; }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest ? ev.target.closest('button.steps-btn') : null;
    if (b) {
      ev.preventDefault();
      body.innerHTML = '<div class="muted">Загрузка…</div>';
      document.getElementById('steps-app').textContent = '№' + b.dataset.steps;
      modal.style.display = 'block';
      fetch('/history/' + b.dataset.steps + '/steps', {headers: {'X-Requested-With': 'fetch'},
             credentials: 'same-origin'})
        .then(function (r) { return r.text(); })
        .then(function (t) { body.innerHTML = t; })
        .catch(function () { body.innerHTML = '<div class="muted">Не удалось загрузить этапы</div>'; });
      return;
    }
    if (ev.target === modal || (ev.target.id === 'steps-close')) { close(); }
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { close(); } });
})();
</script>
"""


def _short_name(full: str) -> str:
    """Иванов Иван Иванович -> Иванов И. (или полное 'Иванов Иван', если отчества нет)."""
    if not full:
        return "—"
    parts = full.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return parts[0]


def kind_badge(row) -> str:
    """Пометка записи. Тестовые метки убраны: остался только «архив»."""
    kind = ((row.get("record_kind") if hasattr(row, "get") else "") or "").strip()
    if kind == "archive":
        return ' <span class="kind-badge kind-archive">архив</span>'
    return ""


def result_badge(run) -> str:
    """Итог обработки заявки: ушла на Google Диск или упёрлась в ошибку."""
    if not run:
        return ""
    if run.get("sent"):
        return ' <span class="kind-badge kind-sent">✅ на Диск</span>'
    if run.get("ok"):
        return ' <span class="kind-badge kind-ok">✅ обработана</span>'
    errs = run.get("errors") or ""
    try:
        data = json.loads(errs) if errs else []
    except Exception:                                  # noqa: BLE001
        data = [errs]
    first = next((str(x).strip() for x in (data or []) if str(x).strip()), "ошибка обработки")
    title = html.escape("; ".join(str(x).strip() for x in (data or []) if str(x).strip())[:600], quote=True)
    short = first if len(first) <= 60 else first[:58] + "…"
    return (f' <span class="kind-badge kind-err" title="{title}">'
            f'⚠ {html.escape(short)}</span>')


@bp.route("/history")
@login_required
def page():
    # Берём все заявки: история — это поиск по всему, что уже было в системе.
    # Входящие тоже видны (у них свой чип), иначе поиск по ним не работал бы.
    rows = db.application_list("")

    # Ссылки на Google Drive: своя у заявки, иначе папка клиента. Нужны, чтобы
    # из истории сразу открыть материалы клиента и сверить переменные.
    app_drive = {}
    client_drive = {}
    try:
        for r in db.q("SELECT id, gdrive_url FROM applications") or []:
            u = (r.get("gdrive_url") or "").strip() if isinstance(r, dict) else ""
            if u:
                app_drive[r["id"]] = u
        for r in db.q("SELECT id, gdrive_folder_url FROM clients") or []:
            u = (r.get("gdrive_folder_url") or "").strip() if isinstance(r, dict) else ""
            if u:
                client_drive[r["id"]] = u
    except Exception:
        pass

    # Итог последней обработки по каждой заявке: ушла на Диск или упёрлась в ошибку.
    run_state = {}
    try:
        for r in db.q("""SELECT r.application_id, r.sent, r.ok, r.errors
                           FROM auto_runs r
                          WHERE r.id = (SELECT MAX(id) FROM auto_runs WHERE application_id = r.application_id)"""):
            run_state[r["application_id"]] = r
    except Exception:                                  # noqa: BLE001
        run_state = {}

    # Для datalist нужен список всех уникальных ФИО клиентов
    all_clients = db.q("SELECT full_name_latin FROM clients WHERE full_name_latin IS NOT NULL AND full_name_latin != '' ORDER BY full_name_latin")
    all_names = sorted({c["full_name_latin"] for c in all_clients})
    datalist_html = "".join(f'<option value="{n.replace(chr(34), "&quot;")}">' for n in all_names)

    # Помечаем строки data-атрибутами для фильтрации
    items_parts = []
    total = 0
    for a in rows:
        total += 1
        client_name = db.client_label(a) or ""
        product = (a.get("product_name") or "") + " " + (a.get("product_code") or "")
        manager = (a.get("manager_name") or "") + " " + (a.get("manager_username") or "")
        # searchable: ФИО клиента + продукт + менеджер
        # Данные для поиска: к имени, продукту и менеджеру добавляем телефон,
        # почту, паспорт, маску карты, счёт, банк и статус — то, по чему ищут
        # заявку руками. Поиск идёт без перезагрузки, прямо в браузере.
        extra_bits = []
        for key in ("phone", "email", "passport_number", "inn", "card_mask",
                    "account_no", "bank_name", "full_name_latin"):
            val = a.get(key)
            if val:
                extra_bits.append(str(val).lower())
        status_raw = (a.get("status") or "").lower()
        items_parts.append(
            '<li class="hrow" '
            f'data-app-id="{a["id"]}" '
            f'data-client="{client_name.lower()}" '
            f'data-product="{product.lower()}" '
            f'data-manager="{manager.lower()}" '
            f'data-extra="{__import__("html").escape(" ".join(extra_bits), quote=True)}" '
            f'data-status="{status_raw}">'
            f'<div class="hnum"><a href="/history/{a["id"]}">#{a["id"]}</a></div>'
            f'<div class="hname">{_short_name(client_name)}'
            + (f'<div class="hmgr">от {_short_name(manager)}</div>' if manager.strip() else "")
            + '</div>'
            f'<div class="hprod">{a.get("product_name") or "—"}'
            + (f'<div class="hmgr">{_short_name(str(a.get("phone") or ""))}</div>' if a.get("phone") else "")
            + (f'<div class="hmgr">{_short_name(str(a.get("bank_name") or ""))}</div>' if a.get("bank_name") else "")
            + '</div>'
            f'<div class="hmark">' + kind_badge(a) + result_badge(run_state.get(a["id"])) + '</div>'
            f'<div class="hact">'
            + f'<a class="btn sm" href="/applications/{a["id"]}/review">Открыть</a>'
            + f'<button type="button" class="btn sm steps-btn" data-steps="{a["id"]}" title="Все этапы, время и ошибки">Этапы</button>'
            + f'<button type="button" class="btn sm reopen" data-app="{a["id"]}" '
              'title="Создать новую заявку с этими же данными и новым номером">↩ В новые</button>'
            + '</div>'
            "</li>"
        )
    items = "".join(items_parts) or '<li class="muted empty-row" style="padding:8px 4px">Истории пока нет.</li>'

    body = f"""
<h1>История и поиск</h1><div class="page-sub"><a class="btn sm" href="/errors">⚠ Журнал ошибок</a></div>
<div class="page-sub">Поиск по всем заявкам: имя клиента, номер заявки, телефон, почта, паспорт, карта, счёт, банк, продукт, менеджер. Отбор идёт сразу при вводе, страница не перезагружается.</div>

<div class="history-search">
  <div class="search-input-wrap">
    <span class="search-icon">🔍</span>
    <input id="history-search" type="search" list="history-names"
           placeholder="Иванов, 76, 7977..., 5536..., Т-Банк, менеджер..."
           autocomplete="off" autofocus>
    <button type="button" id="history-clear" class="search-clear" aria-label="очистить">✕</button>
  </div>
  <datalist id="history-names">{datalist_html}</datalist>
  <div class="search-meta">
    <span id="history-count">Найдено {total} из {total}</span>
    <span class="search-hint muted">фильтр сразу при вводе · страница не перезагружается</span>
  </div>
  <div class="hchips" id="history-chips">
    <button type="button" class="hchip active" data-status="all">все</button>
    <button type="button" class="hchip" data-status="new">входящие</button>
    <button type="button" class="hchip" data-status="in_progress">в работе</button>
    <button type="button" class="hchip" data-status="ready">готовые</button>
    <button type="button" class="hchip" data-status="sent">отправленные</button>
    <button type="button" class="hchip" data-status="closed">закрытые</button>
  </div>
</div>
<style>
 .hchips{{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0 6px}}
 .hchip{{padding:7px 14px;border:1px solid #D7E3DA;background:#fff;border-radius:999px;
        font-size:13.5px;color:#3C4A42;cursor:pointer;font-family:inherit}}
 .hchip:hover{{border-color:#2F7D5B}}
 .hchip.active{{background:#2F7D5B;border-color:#2F7D5B;color:#fff}}
</style>

<ul class="hlist" id="history-list">{items}</ul>
<script>
// «+ Drive»: вставляем ссылку на папку и сразу открываем её из истории.
document.addEventListener('click', function (e) {{
  var b = e.target.closest ? e.target.closest('.hdrive-add') : null;
  if (!b) return;
  e.preventDefault();
  var url = window.prompt('Ссылка на папку Google Drive для этой заявки:');
  if (!url) return;
  var fd = new FormData();
  fd.append('url', url.trim());
  fetch('/applications/' + b.dataset.app + '/review/drive',
        {{method: 'POST', body: fd, credentials: 'same-origin',
          headers: {{'X-Requested-With': 'fetch'}}}})
    .then(function (r) {{ return r.json(); }})
    .then(function (d) {{
      if (d && d.ok) {{
        var a = document.createElement('a');
        a.className = 'btn sm';
        a.href = d.url;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = 'Drive';
        b.parentNode.replaceChild(a, b);
      }} else {{
        window.alert('Не сохранилось: ' + ((d && d.error) || 'проверьте ссылку'));
      }}
    }});
}});
</script>

<script>
(function() {{
  document.addEventListener('click', function (ev) {{
    const b = ev.target.closest ? ev.target.closest('button.reopen') : null;
    if (!b) return;
    ev.preventDefault();
    const id = b.dataset.app;
    if (!confirm('Вернуть заявку #' + id + ' в новые? Будет создана НОВАЯ заявка с новым номером, документами и папкой на Диске.')) return;
    b.disabled = true; b.textContent = '…';
    fetch('/applications/' + id + '/reopen', {{method: 'POST',
      headers: {{'X-Requested-With': 'fetch'}}, credentials: 'same-origin'}})
      .then(function (r) {{ return r.json(); }})
      .then(function (res) {{
        if (res && res.ok) {{ b.textContent = '→ #' + res.new_id; b.classList.add('ok'); }}
        else {{ b.disabled = false; b.textContent = '↩ В новые'; alert('Не получилось вернуть заявку'); }}
      }})
      .catch(function () {{ b.disabled = false; b.textContent = '↩ В новые'; }});
  }});
  const inp = document.getElementById('history-search');
  const clear = document.getElementById('history-clear');
  const list = document.getElementById('history-list');
  const count = document.getElementById('history-count');
  const rows = Array.from(list.querySelectorAll('.hrow'));
  const total = rows.length;

  function normalize(s) {{
    return (s || '').toLowerCase().trim();
  }}

  let activeStatus = 'all';

  function applyFilter() {{
    const q = normalize(inp.value);
    const tokens = q ? q.split(/\s+/).filter(Boolean) : [];
    let visible = 0;
    rows.forEach(r => {{
      const client = r.dataset.client || '';
      const product = r.dataset.product || '';
      const manager = r.dataset.manager || '';
      const extra = r.dataset.extra || '';
      const appId = r.dataset.appId || '';
      // каждое слово должно найтись хотя бы в одном поле: имя, продукт,
      // менеджер, телефон, почта, паспорт, карта, счёт, банк, номер заявки
      const matches = tokens.every(t =>
        client.includes(t) || product.includes(t) || manager.includes(t) ||
        extra.includes(t) || appId === t);
      const statusOk = (activeStatus === 'all') || (r.dataset.status === activeStatus);
      if (matches && statusOk) {{
        r.classList.remove('hidden');
        visible++;
      }} else {{
        r.classList.add('hidden');
      }}
    }});
    count.textContent = 'Найдено ' + visible + ' из ' + total;
  }}
  function debounce(fn, delay) {{
    let t;
    return function() {{
      clearTimeout(t);
      t = setTimeout(fn, delay);
    }};
  }}

  const debounced = debounce(applyFilter, 60);
  inp.addEventListener('input', debounced);
  inp.addEventListener('change', applyFilter);

  clear.addEventListener('click', function() {{
    inp.value = '';
    inp.focus();
    applyFilter();
  }});

  // Esc — очистить
  inp.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
      inp.value = '';
      applyFilter();
    }}
  }});

  // из URL ?q=...
  const params = new URLSearchParams(window.location.search);
  if (params.get('q')) {{
    inp.value = params.get('q');
    applyFilter();
  }}
  // чипы статуса: отбирают записи без перезагрузки страницы
  const chips = Array.from(document.querySelectorAll('#history-chips .hchip'));
  chips.forEach(chip => chip.addEventListener('click', function() {{
    chips.forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    activeStatus = chip.dataset.status || 'all';
    applyFilter();
  }}));

}})();
</script>
{_steps_modal()}

<style>
.history-search{{margin:14px 0 12px 0;display:flex;flex-direction:column;gap:8px}}
.search-input-wrap{{position:relative;display:flex;align-items:center;background:var(--card);
  border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:0 10px}}
.search-input-wrap:focus-within{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(31,107,255,.12)}}
.search-icon{{font-size:16px;color:var(--muted);margin-right:8px;flex:0 0 auto}}
#history-search{{flex:1;border:none;outline:none;font:inherit;font-size:15px;padding:11px 0;
  background:transparent;color:var(--ink)}}
#history-search::placeholder{{color:var(--muted)}}
.search-clear{{background:transparent;border:none;color:var(--muted);font-size:18px;
  cursor:pointer;padding:4px 8px;border-radius:6px;display:none}}
.search-clear.visible{{display:inline-flex}}
.search-meta{{display:flex;justify-content:space-between;align-items:center;font-size:12.5px;padding:0 4px}}
#history-count{{font-weight:600;color:var(--ink)}}
.search-hint{{font-size:11.5px}}
.hlist{{list-style:none;margin:0;padding:0;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}}
.hrow{{display:flex;align-items:center;gap:8px;padding:9px 10px;border-bottom:1px solid var(--line);
  font-size:13.5px;transition:background .15s}}
.hrow:last-child{{border-bottom:none}}
.hrow:hover{{background:#F9FAFC}}
.hrow.hidden{{display:none}}
.hrow .hname mark{{background:#FFE9A8;padding:0 2px;border-radius:3px;font-weight:800}}
@media (max-width:720px){{
  /* Телефон: имя клиента на своей строке, продукт и кнопка ниже — ничего не режется */
  .hrow {{ flex-wrap:wrap; align-items:flex-start; gap:5px 8px; padding:10px 9px; }}
  .hrow .hnum {{ flex:0 0 auto; }}
  .hrow .hname {{ flex:1 1 100%; font-size:14px; order:1; }}
  .hrow .hprod {{ flex:1 1 auto; font-size:12.5px; order:2; }}
  .hrow .hact {{ flex:0 0 auto; margin-left:auto; order:3; align-self:center; }}
  .hrow .hmgr {{ display:none; }}
  /* продукт в истории показываем целиком: раньше он обрезался многоточием */
  .hrow .hprod {{ white-space:normal; overflow:visible; text-overflow:clip; text-align:left;
                  line-height:1.35; }}
}}
.hnum{{font-weight:800;color:var(--muted);min-width:28px;font-size:12.5px}}
.hmark{{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;flex:0 1 auto}}
.hname{{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hmgr{{font-weight:400;color:var(--muted);font-size:11.5px}}
.hprod{{color:var(--muted);font-size:12px;flex:0 1 auto;text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:90px}}
.hact{{flex:0 0 auto}}
@medi‌a(max-width:380px){{.hprod{{display:none}}}}
</style>
"""
    return render("История", "history", body)



@bp.route("/history/<int:app_id>")
@login_required
def app_timeline(app_id: int):
    """Полный ход заявки: каждый этап, кто инициировал, время и ошибка, если была."""
    from services import app_steps
    a = db.q1("SELECT a.id, a.status, a.created_at, a.sent_at, c.surname, c.name, "
              "p.name AS product_name, bm.full_name AS manager_name "
              "FROM applications a LEFT JOIN clients c ON c.id=a.client_id "
              "LEFT JOIN products p ON p.id=a.product_id "
              "LEFT JOIN bot_managers bm ON bm.id=a.bot_manager_id WHERE a.id=?", (app_id,))
    if not a:
        abort(404)
    rows = app_steps.timeline(app_id)
    seen = {r["step"] for r in rows}
    lines = []
    for r in rows:
        note = (r.get("note") or "").strip()
        lines.append(
            f'<li class="tl {r["status"]}"><span class="ic">{r["icon"]}</span>'
            f'<span class="lbl">{html.escape(r["label"])}</span>'
            f'<span class="who">{html.escape(r.get("actor") or "система")}</span>'
            f'<span class="when">{html.escape(str(r.get("created_at") or ""))}</span>'
            + (f'<div class="note">{html.escape(note)}</div>' if note else "")
            + "</li>")
    head = (f'<h1>Заявка #{a["id"]} · {html.escape(" ".join(filter(None,[a.get("surname"),a.get("name")])) or "—")}</h1>'
            f'<div class="page-sub">{html.escape(a.get("product_name") or "продукт не указан")} · '
            f'менеджер: {html.escape(a.get("manager_name") or "—")} · статус: {html.escape(a.get("status") or "")}</div>')
    body = head + ('<ol class="timeline">' + "".join(lines) + '</ol>' if lines else
                   '<div class="muted">Этапов пока нет: заявка ещё не обрабатывалась.</div>')
    body += '<div class="page-sub"><a href="/history">← к истории</a></div>'
    return render("История заявки", "history", body)

@bp.route("/applications/<int:app_id>/reopen", methods=["POST"])
@login_required
def app_reopen(app_id: int):
    """Вернуть прошедшую заявку в «новые»: создаётся НОВАЯ заявка с тем же клиентом.

    Номер заявки — это её id, поэтому новая запись получает новый номер, заново
    собирает документы и создаёт свою папку Wolf AutoDoc №<новый номер> на Диске.
    Старая остаётся в истории с пометкой «переоткрыта» — для обучения системы.
    """
    src = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not src:
        return jsonify({"ok": False, "error": "заявка не найдена"}), 404
    db.exec_sql(
        """INSERT INTO applications
               (client_id, product_id, status, source, gdrive_url, comment, raw_payload,
                bot_manager_id, record_kind, brief, raw_message, price_idr)
           VALUES (?, ?, 'new', ?, NULL, ?, ?, ?, 'reopen', ?, ?, ?)""",
        (src["client_id"], src["product_id"], src.get("source") or "reopen",
         src.get("comment"), src.get("raw_payload"), src.get("bot_manager_id"),
         src.get("brief"), src.get("raw_message"), src.get("price_idr")))
    new_id = (db.q1("SELECT MAX(id) AS id FROM applications") or {}).get("id")
    db.exec_sql("UPDATE applications SET record_kind='reopened', status='archived' WHERE id=?", (app_id,))
    db.exec_sql("INSERT INTO auto_queue (application_id, status) VALUES (?, 'queued')", (new_id,))
    db.log_event("application", new_id, "reopen", payload={"from": app_id})
    try:
        from services import app_steps as _steps
        _steps.step(new_id, "reopen", "ok", "заявка переоткрыта из #%s" % app_id)
    except Exception:                                              # noqa: BLE001
        pass
    # сразу будим очередь, чтобы прогон пошёл без ожидания крона
    try:
        import subprocess, sys
        from pathlib import Path as _P
        root = _P(__file__).resolve().parents[2]
        subprocess.Popen([sys.executable or "/usr/bin/python3",
                          str(root / "scripts" / "auto_queue.py"), "worker"],
                         cwd=str(root), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:                                              # noqa: BLE001
        pass
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "new_id": new_id})
    return redirect(url_for("history.page"))


@bp.route("/errors")
@login_required
def errors_page():
    """Журнал ошибок: номер, заявка, этап, текст, флаг состояния и комментарий."""
    from services import error_log as EL
    want = (request.args.get("status") or "").strip()
    if want == "all":
        want = ""
    rows = EL.entries(want)
    st = EL.stats()
    esc = lambda x: html.escape(str(x or ""))
    chips = "".join(
        '<a class="btn sm%s" href="/errors%s">%s</a>' % (
            ' active' if want == k[0] else '', k[1],
            "%s (%s)" % (k[2], st.get(k[0], 0)))
        for k in (("", "", "Все"), ("open", "?status=open", "Не исправлено"),
                  ("fixed", "?status=fixed", "Исправлено"),
                  ("wontfix", "?status=wontfix", "Требует корректировки")))
    F_OPEN, F_FIX, F_TUNE = "не исправлено", "исправлено", "требует корректировки"
    items = []
    for r in rows:
        cur = r.get("status") or "open"
        opts = "".join(
            '<option value="%s"%s>%s</option>' % (v, " selected" if cur == v else "", lbl)
            for v, lbl in (("open", F_OPEN), ("fixed", F_FIX), ("wontfix", F_TUNE)))
        color = {"open": "#B42318", "fixed": "#067647", "wontfix": "#B45309"}.get(cur, "#333")
        items.append(
            f'<div class="err-item" data-id="{r["id"]}" style="border:1px solid var(--line);'
            f'border-radius:12px;padding:11px 13px;margin:0 0 10px 0;background:#fff">'
            # номер + метаданные
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:baseline">'
            f'<b style="font-size:13px;color:#1F3A93">Ошибка #{r["id"]}</b>'
            f'<span style="font-size:12px;color:#6B7280">{esc(str(r.get("created_at") or "")[:16])}'
            f' · повторов: {r.get("repeats") or 1} · этап: {esc(r.get("stage") or "—")}</span>'
            f'<a href="/applications/{r.get("application_id") or ""}/review" '
            f'style="margin-left:auto;font-size:12.5px;font-weight:600;white-space:nowrap">'
            f'Конструктор заявки #{r.get("application_id") or "—"} →</a></div>'
            # текст ошибки
            f'<div style="margin:7px 0 8px 0;font-size:13.5px;line-height:1.5;white-space:normal;'
            f'overflow-wrap:anywhere">{esc((r.get("text") or "")[:600])}</div>'
            # комментарий агента — что была за ошибка / что сделано
            f'<textarea class="err-note" rows="2" placeholder="Комментарий по ошибке: что случилось и что сделано"'
            f' style="width:100%;box-sizing:border-box;border:1px solid var(--line);border-radius:9px;'
            f'padding:7px 9px;font:inherit;font-size:13px;resize:vertical">{esc(r.get("agent_note"))}</textarea>'
            + (f'<div style="margin:5px 0 0 0;font-size:12px;color:#6B7280">'
               f'комментарий заказчика: {esc(r.get("user_comment"))}</div>' if r.get("user_comment") else "")
            + f'<div style="display:flex;gap:8px;align-items:center;margin-top:7px;flex-wrap:wrap">'
            f'<select class="err-status" style="border:1px solid var(--line);border-radius:9px;'
            f'padding:6px 8px;font:inherit;font-size:13px;color:{color};font-weight:600">{opts}</select>'
            f'<button type="button" class="btn sm err-save" data-id="{r["id"]}">Сохранить</button>'
            f'<span class="err-saved" style="font-size:12px;color:#067647"></span></div>'
            '</div>')
    body = ('<h1>Журнал ошибок</h1>'
            '<div class="page-sub">Нумерованный реестр проблем: у каждой записи свой номер, заявка, '
            'этап, текст ошибки и флаг состояния. Ссылка ведёт в конструктор заявки — там видно, '
            'на каком документе или проверке всё встало.</div>'
            f'<div class="errchips">{chips}</div>'
            + ("".join(items) or '<div class="muted">Записей нет.</div>') +
            '<div class="page-sub"><a href="/history">← к истории</a></div>'
            '<script>(function(){'
            'document.addEventListener("click",function(ev){'
            'var b=ev.target.closest?ev.target.closest(".err-save"):null;if(!b)return;'
            'ev.preventDefault();var box=b.closest(".err-item");'
            'var note=box.querySelector(".err-note").value;'
            'var status=box.querySelector(".err-status").value;'
            'fetch("/errors/"+b.dataset.id+"/status",{method:"POST",'
            'headers:{"X-Requested-With":"fetch","Content-Type":"application/x-www-form-urlencoded"},'
            'body:"status="+encodeURIComponent(status)+"&note="+encodeURIComponent(note),'
            'credentials:"same-origin"}).then(function(r){return r.json();}).then(function(){'
            'var s=box.querySelector(".err-saved");s.textContent="сохранено";'
            'setTimeout(function(){s.textContent="";},2500);});'
            '},true);})();</script>')
    return render("Журнал ошибок", "errors", body)


@bp.route("/errors/<int:entry_id>/status", methods=["POST"])
@login_required
def error_status(entry_id: int):
    from services import error_log as EL
    EL.set_status(entry_id, (request.form.get("status") or "").strip(), (request.form.get("note") or "").strip())
    return jsonify({"ok": True})


@bp.route("/errors/<int:entry_id>/comment", methods=["POST"])
@login_required
def error_comment(entry_id: int):
    from services import error_log as EL
    EL.set_comment(entry_id, (request.form.get("comment") or "").strip())
    return jsonify({"ok": True})

def _timeline_body(app_id: int) -> str:
    """Этапы заявки: аккуратный вертикальный список, номера, начало/финал.

    Вёрстка полностью на inline-стилях и своих классах (stp-*), чтобы не наследовать
    старые правила .timeline/.tl — из-за них в окне наезжали друг на друга тексты.
    """
    from services import app_steps
    rows = app_steps.timeline(app_id)
    if not rows:
        return '<div class="muted">Этапов пока нет: заявка ещё не обрабатывалась.</div>'
    total = len(rows)
    first, last = rows[0], rows[-1]
    esc = lambda x: html.escape(str(x or ""))
    # Длительность — только РАБОЧЕЕ время (сумма прогонов обработчика), без времени
    # в очереди: пока заявка ждёт, таймер стоит.
    from datetime import datetime as _dtm
    _dur = "—"
    try:
        _qa = db.q("SELECT status, started_at, finished_at FROM auto_queue "
                   "WHERE application_id=? ORDER BY id", (app_id,))

        def _pd(v):
            try:
                return _dtm.fromisoformat(str(v).replace("Z", ""))
            except Exception:
                return None

        _tot, _run = 0, False
        for _r in _qa:
            _a0 = _pd(_r.get("started_at"))
            if not _a0:
                continue
            _a1 = _pd(_r.get("finished_at"))
            if str(_r.get("status")) == "running" and not _a1:
                _a1, _run = _dtm.utcnow(), True
            if not _a1:
                continue
            _tot += max(0, int((_a1 - _a0).total_seconds()))
        _m, _s2 = divmod(_tot, 60)
        if _m >= 60:
            _dur = "%d ч %d мин" % (_m // 60, _m % 60)
        elif _m:
            _dur = "%d мин %d с" % (_m, _s2)
        else:
            _dur = "%d с" % _s2
        if _run:
            _dur += " (идёт)"
        if not _qa:
            _dur = "ещё не запускалась"
    except Exception:
        pass
    card = ('<div style="display:flex;flex-wrap:wrap;gap:6px 16px;align-items:baseline;'
            'background:#F4F7FD;border:1px solid #DCE6F7;border-radius:10px;'
            'padding:9px 12px;margin:0 0 12px 0;font-size:13px;line-height:1.5">'
            f'<b>Всего этапов: {total}</b>'
            f'<b>⏱ Длительность: {_dur}</b>'
            f'<span>начало — {esc(first.get("label"))} <span style="color:#6B7280">'
            f'{esc(first.get("created_at"))}</span></span>'
            f'<span>финал — {esc(last.get("label"))} <span style="color:#6B7280">'
            f'{esc(last.get("created_at"))}</span></span></div>')
    colors = {"ok": "#0E9F6E", "warn": "#B45309", "fail": "#E11D48",
              "error": "#E11D48", "skip": "#6B7280"}
    items = []
    # Сверху — последние этапы: список переворачиваем, номера оставляем сквозными.
    numbered = list(enumerate(rows, 1))[::-1]
    for i, r in numbered:
        note = str(r.get("note") or "").strip()
        st = str(r.get("status") or "")
        color = colors.get(st, "#374151")
        tag = ""
        if i == 1:
            tag = ('<span style="font-size:10.5px;font-weight:700;color:#1F6BFF;'
                   'background:#E7EFFF;border-radius:6px;padding:1px 6px;margin-left:6px">начало</span>')
        elif i == total:
            tag = ('<span style="font-size:10.5px;font-weight:700;color:#0E9F6E;'
                   'background:#E6F7F0;border-radius:6px;padding:1px 6px;margin-left:6px">финал</span>')
        st_label = {"ok": "пройден", "warn": "внимание", "fail": "не пройден",
                    "error": "ошибка", "skip": "пропущен"}.get(st, st or "—")
        st_bg = {"ok": "#E6F7F0", "warn": "#FEF3C7", "fail": "#FEE4E2",
                 "error": "#FEE4E2", "skip": "#F1F3F7"}.get(st, "#F1F3F7")
        badge = (f'<span style="font-size:10.5px;font-weight:700;color:{color};background:{st_bg};'
                 f'border-radius:6px;padding:1px 6px;margin-left:6px">{st_label}</span>')
        note_html = (f'<div style="margin:3px 0 0 0;color:#4B5563;font-size:12.5px;line-height:1.5;'
                     f'white-space:normal;overflow-wrap:anywhere">{esc(note)}</div>' if note else "")
        items.append(
            '<div style="display:flex;gap:9px;align-items:flex-start;padding:9px 2px;'
            'border-bottom:1px solid #EDF0F5">'
            f'<div style="flex:0 0 22px;height:22px;line-height:22px;text-align:center;border-radius:50%;'
            f'background:#E8EEF9;color:#1F3A93;font-weight:700;font-size:11.5px">{i}</div>'
            '<div style="flex:1 1 auto;min-width:0">'
            f'<div style="font-size:13.5px;font-weight:600;color:{color};overflow-wrap:anywhere">'
            f'{esc(r.get("icon"))} {esc(r.get("label"))}{badge}{tag}</div>'
            f'{note_html}'
            f'<div style="margin-top:2px;font-size:11.5px;color:#6B7280">'
            f'{esc(r.get("created_at"))} · {esc(r.get("actor") or "система")}</div>'
            '</div></div>')
    return card + '<div style="border-top:1px solid #EDF0F5">' + "".join(items) + '</div>'


@bp.route("/history/<int:app_id>/steps")
@login_required
def app_steps_popup(app_id: int):
    """Этапы заявки всплывающим окном: без отдельной страницы."""
    a = db.q1("SELECT a.id, c.surname, c.name, p.name AS product_name, a.status "
              "FROM applications a LEFT JOIN clients c ON c.id=a.client_id "
              "LEFT JOIN products p ON p.id=a.product_id WHERE a.id=?", (app_id,))
    if not a:
        abort(404)
    who = " ".join(x for x in (a.get("surname"), a.get("name")) if x) or "—"
    head = (f'<div class="steps-head">Заявка #{a["id"]} · {html.escape(who)}'
            f'<span class="muted"> · {html.escape(a.get("product_name") or "продукт не указан")}'
            f' · {html.escape(str(a.get("status") or ""))}</span></div>')
    return head + _timeline_body(app_id)
