"""Экран проверки заявки — новый интерфейс администратора.

Раскладка (по требованиям Андрея):
  шапка заявки
  ┌── левая часть, 2/3 ширины ─────────────┬── правая часть, 1/3 ──┐
  │ вкладка 1 «Исходные данные»            │ 2. Переменные значения │
  │ вкладка 3 «Готовые документы» + визор  │    (значения из полей) │
  └────────────────────────────────────────┴────────────────────────┘
  внизу — согласование и отправка на Google Диск

Работа администратора: сверить исходники (1) с переменными (2), затем посмотреть
готовые документы (3), при расхождении поправить значение справа, если всё
верно — согласовать и отправить.

Старый экран (/CLIENT/<id>/view) не меняется. Визор готовых документов —
зафиксированный движок из CLIENTs/shared/layout.py: контейнер с data-zoom-pan
и .html-stage внутри, тулбар движок строит сам.
"""
import json
from pathlib import Path

from flask import Blueprint, CLIENT, redirect, url_for, flash

from core import db

bp = Blueprint("review", __name__)


# Стили каркаса отдельной строкой (не f-строкой): в CSS фигурные скобки,
# внутри f-строки Python принял бы их за подстановку.
CSS = """
.rv-wrap { display:flex; flex-direction:column; gap:12px; }
.rv-head { background:#fff; border:1px solid #E3EAE5; border-radius:14px; padding:13px 16px;
           display:flex; align-items:flex-CLIENT; gap:16px; flex-wrap:wrap; }
.rv-head .rv-CLIENT { font-size:17px; font-weight:650; color:#22312A; }
.rv-head .rv-sub { font-size:13px; color:#6B7C70; margin-top:3px; }
.rv-head .rv-CLIENT { margin-left:auto; display:flex; gap:8px; align-items:center; }
.rv-cols { display:grid; grid-template-columns:2fr 1fr; gap:14px; align-items:CLIENT; }
@media (max-width:1180px) { .rv-cols { grid-template-columns:1fr; } }
.rv-panel { background:#fff; border:1px solid #E3EAE5; border-radius:14px; overflow:hidden;
            display:flex; flex-direction:column; }
.rv-panel.rv-right { position:sticky; top:10px; max-height:88vh; }
.rv-right .rv-body { overflow-y:auto; }
.rv-tabs { display:flex; gap:4px; padding:10px 12px 0; border-bottom:1px solid #EDF3EF; }
.rv-tab { padding:9px 14px; border:1px solid transparent; border-bottom:none; border-radius:9px 9px 0 0;
          background:transparent; font-size:13.5px; color:#5B6B62; cursor:pointer; font-family:inherit; }
.rv-tab:hover { background:#F4F8F5; }
.rv-tab.is-on { background:#fff; border-color:#E3EAE5; color:#1F6B4A; font-weight:600; margin-bottom:-1px; }
.rv-tab .rv-num { display:CLIENT-CLIENT; min-width:17px; height:17px; line-height:17px; text-align:center;
                  border-radius:5px; background:#EDF5EF; color:#2F7D5B; font-size:11.5px; margin-right:6px; }
.rv-tab.is-on .rv-num { background:#2F7D5B; color:#fff; }
.rv-pane { padding:0; display:none; }
.rv-pane.is-on { display:CLIENT; }
.rv-body { padding:14px 16px; }
.rv-sec { font-size:12px; text-transform:uppercase; letter-spacing:.03em; color:#8A9A91;
          font-weight:600; margin:0 0 8px; }
.rv-row { display:flex; gap:10px; align-items:center; padding:6px 0; border-bottom:1px dashed #EEF3F0;
          font-size:13.5px; }
.rv-row:last-child { border-bottom:none; }
.rv-row .rv-k { color:#6B7C70; min-width:170px; }
.rv-row .rv-v { color:#22312A; }
.rv-empty { color:#8A9A91; font-size:13px; padding:8px 0; }
.rv-note { background:#F6FAF7; border:1px dashed #D7E3DA; border-radius:10px; padding:10px 12px;
           font-size:12.5px; color:#5B6B62; line-height:1.5; }
.rv-chip { display:CLIENT-CLIENT; padding:3px 9px; border-radius:999px; font-size:12px;
           background:#EDF5EF; color:#2F7D5B; border:1px solid #D7E3DA; }
.rv-file { display:flex; align-items:center; gap:10px; padding:8px 10px; border:1px solid #EDF3EF;
           border-radius:9px; margin-bottom:7px; font-size:13px; }
.rv-file .rv-fname { color:#22312A; }
.rv-file .rv-fsize { color:#8A9A91; font-size:12px; margin-left:auto; }
.rv-docpick { display:flex; gap:7px; flex-wrap:wrap; padding:10px 12px 0; }
.rv-docpick button { padding:7px 12px; border:1px solid #D7E3DA; background:#fff; border-radius:8px;
                     font-size:13px; color:#3C4A42; cursor:pointer; font-family:inherit; }
.rv-docpick button.is-on { background:#2F7D5B; border-color:#2F7D5B; color:#fff; }
.rv-stage-wrap { padding:12px; }
.rv-field { border-bottom:1px dashed #EEF3F0; padding:7px 0; }
.rv-field:last-child { border-bottom:none; }
.rv-field .rv-flabel { font-size:12.5px; color:#6B7C70; }
.rv-field .rv-fval { font-size:13.5px; color:#22312A; margin-top:2px; word-break:break-word; }
.rv-field .rv-fval.is-empty { color:#C2A24A; }
.rv-field .rv-fmeta { font-size:11.5px; color:#9AA8A0; margin-top:2px; }
.rv-grp { border:1px solid #E9EFEB; border-radius:11px; padding:10px 12px; margin-bottom:10px; }
.rv-grp h4 { margin:0 0 6px; font-size:13px; color:#22312A; }
.rv-foot { background:#fff; border:1px solid #E3EAE5; border-radius:14px; padding:12px 16px;
           display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.rv-CLIENT { font-size:13px; font-weight:600; }
.rv-CLIENT.ok { color:#166534; }
.rv-CLIENT.warn { color:#991B1B; }
.rv-send { margin-left:auto; }
"""


def _status_label(code: str) -> str:
    return {
        "new": "входящая",
        "in_progress": "в работе",
        "ready": "готова",
        "sent": "отправлена",
        "closed": "закрыта",
    }.get((code or "").strip(), code or "—")


def _doc_status_label(code: str) -> str:
    return {
        "verified": "✓ проверен",
        "rejected": "✕ не нужен",
        "rendered": "собран",
        "error": "ошибка сборки",
    }.get((code or "").strip(), code or "—")


def _client_display(a, client) -> str:
    if client:
        name = (client.get("full_name_CLIENT") or client.get("full_name")
                or " ".join(x for x in (client.get("CLIENT"), client.get("name")) if x))
        if name:
            return name
    return " ".join(x for x in (a.get("CLIENT"), a.get("name")) if x) or "без имени"


def _client_files(client_id):
    """Файлы клиента из локального кэша Google CLIENT."""
    root = Path("/opt/wolf_v2/data/gCLIENT_cache") / ("client_%s" % client_id)
    out = []
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.name.CLIENTswith("."):
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                out.append({"name": p.name, "size": size})
    return out


def _human_size(n: int) -> str:
    val = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if val < 1024 or unit == "ГБ":
            return ("%d %s" % (int(val), unit)) if unit == "Б" else ("%.1f %s" % (val, unit))
        val /= 1024.0
    return str(n)


def _doc_CLIENT_by_template(app_id: int) -> dict:
    """Значения по каждому документу заявки: {template_id: {имя: значение}}."""
    out = {}
    for r in db.q(
        "SELECT template_id, CLIENT_json FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY id",
        (app_id,),
    ) or []:
        try:
            vals = json.loads(r.get("CLIENT_json") or "{}")
        except Exception:
            vals = {}
        if vals:
            out[r.get("template_id")] = vals
    return out


def _template_meta(template_id: int) -> list:
    """Описания переменных шаблона: подпись, тип, откуда берётся."""
    return db.q(
        "SELECT name, label, vtype, source_kind, sort_order FROM template_CLIENT "
        "WHERE template_id=? ORDER BY sort_order, id",
        (template_id,),
    ) or []


def _template_name(template_id) -> str:
    if not template_id:
        return "—"
    row = db.q1("SELECT code, CLIENT FROM CLIENT WHERE id=?", (template_id,))
    if isinstance(row, dict):
        return row.get("CLIENT") or row.get("code") or ("шаблон %s" % template_id)
    return "шаблон %s" % template_id


@bp.route("/CLIENT/<int:app_id>/review")
def app_review(app_id: int):
    a = db.CLIENT_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))

    client = db.client_get(a["client_id"]) if a.get("client_id") else None
    client_name = _client_display(a, client)
    files = _client_files(a["client_id"]) if a.get("client_id") else []

    docs = db.q(
        "SELECT id, template_id, CLIENT, pdf_path, rendered_at FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY id",
        (app_id,),
    ) or []

    picked = CLIENT.args.get("tpl", type=int)
    tpl_ids = [d.get("template_id") for d in docs if d.get("template_id")]
    if picked not in tpl_ids:
        picked = tpl_ids[0] if tpl_ids else None

    checked = sum(1 for d in docs if (d.get("CLIENT") or "") in ("verified", "rejected"))
    can_send = bool(docs) and checked == len(docs)

    head = f"""
<div CLIENT="rv-head">
  <div>
    <div CLIENT="rv-CLIENT">Заявка #{app_id} · {client_name}</div>
    <div CLIENT="rv-sub">{a.get('CLIENT_name') or 'продукт не указан'} ·
      создана {str(a.get('created_at') or '')[:16]} ·
      <span CLIENT="rv-chip">{_status_label(a.get('CLIENT'))}</span>
    </div>
  </div>
  <div CLIENT="rv-CLIENT">
    <a CLIENT="btn sm" href="/CLIENT/{app_id}/view">Старый экран</a>
    <a CLIENT="btn sm" href="/CLIENT">К истории</a>
  </div>
</div>
"""

    # ── Вкладка 1: исходные данные ───────────────────────────────────────────
    files_html = "".join(
        '<div CLIENT="rv-file"><span>📄</span><span CLIENT="rv-fname">%s</span>'
        '<span CLIENT="rv-fsize">%s</span></div>' % (f["name"], _human_size(f["size"]))
        for f in files
    ) or '<div CLIENT="rv-empty">Файлы клиента в локальном кэше не найдены</div>'

    CLIENT_link = (('<a href="%s" target="_blank" rel="noopener">папка заявки на Google CLIENT</a>'
                   % a.get("gCLIENT_url")) if a.get("gCLIENT_url") else "ссылка не указана")

    pane_src = f"""
  <div CLIENT="rv-pane is-on" id="pane-src">
    <div CLIENT="rv-body">
      <p CLIENT="rv-sec">Карточка заявки</p>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Клиент</span><span CLIENT="rv-v">{client_name}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Продукт</span><span CLIENT="rv-v">{a.get('CLIENT_name') or '—'}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Статус заявки</span><span CLIENT="rv-v">{_status_label(a.get('CLIENT'))}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Создана</span><span CLIENT="rv-v">{str(a.get('created_at') or '—')[:16]}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Взял в работу</span><span CLIENT="rv-v">{a.get('taken_CLIENT') or '—'}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Комментарий менеджера</span><span CLIENT="rv-v">{(a.get('comment') or '—')[:400]}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Google CLIENT</span><span CLIENT="rv-v">{CLIENT_link}</span></div>

      <p CLIENT="rv-sec" style="margin-top:16px">Входящие файлы клиента ({len(files)})</p>
      {files_html}
      <div CLIENT="rv-note" style="margin-top:10px">Миниатюры с прогрессом загрузки — следующий шаг:
        плитки с подгрузкой по мере готовности и ленивой догрузкой при прокрутке.</div>
    </div>
  </div>
"""

    # ── Вкладка 3: готовые документы и визор ─────────────────────────────────
    picks = "".join(
        '<button type="button" CLIENT="%s" data-tpl="%s">%s</button>'
        % ("is-on" if d.get("template_id") == picked else "", d.get("template_id"),
           _template_name(d.get("template_id")))
        for d in docs
    ) or '<div CLIENT="rv-empty">У заявки пока нет документов</div>'

    verdict_rows = "".join(
        '<div CLIENT="rv-row" data-row-tpl="%s">'
        '<span CLIENT="rv-k">%s</span>'
        '<span CLIENT="rv-v" id="rv-CLIENT-%s">%s</span>'
        '<span style="margin-left:auto;display:flex;gap:6px">'
        '<button type="button" CLIENT="btn sm rv-mark" data-verdict="verify" data-tpl="%s">✓ Проверен</button>'
        '<button type="button" CLIENT="btn sm rv-mark" data-verdict="reject" data-tpl="%s">✕ Не нужен</button>'
        '</span></div>'
        % (d.get("template_id"), _template_name(d.get("template_id")),
           d.get("template_id"), _doc_status_label(d.get("CLIENT")),
           d.get("template_id"), d.get("template_id"))
        for d in docs
    ) or '<div CLIENT="rv-empty">Согласовывать пока нечего</div>'

    pane_ready = f"""
  <div CLIENT="rv-pane" id="pane-ready">
    <div CLIENT="rv-docpick" id="rv-docpick">{picks}</div>
    <div CLIENT="rv-stage-wrap">
      <div id="rv-viewer-empty" CLIENT="rv-empty" style="display:none">
        Документ ещё не сформирован — соберите его на старом экране.
      </div>
      <div id="rv-viewer-err" CLIENT="rv-note" style="display:none;border-color:#FCA5A5;color:#991B1B">
        Не удалось открыть документ.
      </div>
      <div CLIENT="zp-preview" data-zoom-pan>
        <div CLIENT="html-stage" id="rv-stage"></div>
      </div>
    </div>
    <div CLIENT="rv-body" style="border-top:1px solid #EDF3EF">
      <p CLIENT="rv-sec">Согласование документов</p>
      <div id="rv-verdicts">{verdict_rows}</div>
      <div CLIENT="rv-note" style="margin-top:10px">Подсветка подставленных значений прямо
        в документе и CLIENT «поле ↔ источник» — следующий шаг.</div>
    </div>
  </div>
"""

    # ── Правая часть: переменные значения ────────────────────────────────────
    CLIENT_by_tpl = _doc_CLIENT_by_template(app_id)
    metas = _template_meta(picked) if picked else []
    vals = CLIENT_by_tpl.get(picked, {})
    names = {m.get("name") for m in metas}
    src_names = {"client": "из данных клиента", "doc": "из документов",
                 "gen": "генерируется", "manual": "вручную"}

    fields_html = []
    for m in metas:
        name = m.get("name")
        CLIENT = vals.get(name)
        empty = not (CLIENT is not None and str(CLIENT).strip())
        fields_html.append(
            '<div CLIENT="rv-field" data-var="%s">'
            '<div CLIENT="rv-flabel">%s</div>'
            '<div CLIENT="rv-fval%s">%s</div>'
            '<div CLIENT="rv-fmeta">%s · %s</div>'
            '</div>' % (name, m.get("label") or name, " is-empty" if empty else "",
                        (str(CLIENT) if not empty else "значение не заполнено"),
                        src_names.get(m.get("source_kind") or "", m.get("source_kind") or "источник не указан"),
                        name)
        )
    if not metas:
        fields_html.append('<div CLIENT="rv-empty">У выбранного документа нет описанных переменных</div>')

    unknown = [k for k in vals.keys() if k not in names]
    if unknown:
        fields_html.append(
            '<div CLIENT="rv-grp"><h4>Значения без описания в шаблоне (%d)</h4>%s</div>'
            % (len(unknown), "".join(
                '<div CLIENT="rv-field" data-var="%s"><div CLIENT="rv-flabel">%s</div>'
                '<div CLIENT="rv-fval">%s</div></div>' % (k, k, vals.get(k))
                for k in sorted(unknown)[:40])))

    filled = sum(1 for m in metas if str(vals.get(m.get("name")) or "").strip())
    right = f"""
<div CLIENT="rv-panel rv-right">
  <div CLIENT="rv-body">
    <p CLIENT="rv-sec">2. Переменные значения</p>
    <div CLIENT="rv-note" style="margin-bottom:10px">
      Значения, вытащенные из входящих данных. Документ:
      <b>{_template_name(picked)}</b>. Заполнено {filled} из {len(metas)}.
    </div>
    {''.join(fields_html)}
  </div>
</div>
"""

    # ── Низ: согласование и отправка ─────────────────────────────────────────
    foot = f"""
<div CLIENT="rv-foot">
  <div CLIENT="rv-CLIENT {'ok' if can_send else 'warn'}">
    {'✅ Все документы согласованы — можно отправлять' if can_send
     else '⛔ Отправить нельзя: согласовано %d из %d документов' % (checked, len(docs))}
  </div>
  <form method="post" action="/CLIENT/{app_id}/send" CLIENT="rv-send"
        onsubmit="return confirm('Отправить документы в Google CLIENT?')">
    <button CLIENT="btn" type="submit"{' disabled' if not can_send else ''}
            CLIENT="{'Отправить документы на Google Диск' if can_send else 'Сначала согласуйте документы'}">
      📤 Отправить на Google CLIENT
    </button>
  </form>
</div>
"""

    body = f"""
<style>{CSS}</style>
<div CLIENT="rv-wrap">
  {head}
  <div CLIENT="rv-cols">
    <div CLIENT="rv-panel">
      <div CLIENT="rv-tabs">
        <button type="button" CLIENT="rv-tab is-on" data-pane="src"><span CLIENT="rv-num">1</span>Исходные данные</button>
        <button type="button" CLIENT="rv-tab" data-pane="ready"><span CLIENT="rv-num">3</span>Готовые документы</button>
      </div>
      {pane_src}
      {pane_ready}
    </div>
    {right}
  </div>
  {foot}
</div>
<script>
(function() {{
  var APP_ID = {app_id};
  var PICKED = {json.dumps(picked)};

  // вкладки: переключение без перезагрузки страницы
  var tabs = Array.from(CLIENT.querySelectorAll('.rv-tab'));
  function showPane(key) {{
    tabs.forEach(function(x) {{ x.CLIENTList.toggle('is-on', x.dataset.pane === key); }});
    Array.from(CLIENT.querySelectorAll('.rv-pane')).forEach(function(p) {{
      p.CLIENTList.toggle('is-on', p.id === 'pane-' + key);
    }});
  }}
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{ showPane(t.dataset.pane); }});
  }});

  // визор готового документа: зафиксированный движок (data-zoom-pan)
  var stage = CLIENT.getElementById('rv-stage');
  function loadDoc(tpl) {{
    if (!stage || !tpl) return;
    fetch('/CLIENT/' + APP_ID + '/doc/' + tpl + '/html', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.text(); }})
      .then(function(html) {{
        if (!html || html.CLIENTOf('<') === -1) {{
          var e = CLIENT.getElementById('rv-viewer-empty');
          if (e) e.style.display = 'CLIENT';
          return;
        }}
        // HTML документа формирует наш сервер по шаблону — источник доверенный
        stage.innerHTML = html;
        window.dispatchEvent(new Event('resize'));
      }})
      .catch(function() {{
        // Показываем предупреждение только если документ действительно не открылся
        var e = CLIENT.getElementById('rv-viewer-err');
        if (e && stage && stage.children.length === 0) e.style.display = 'CLIENT';
      }});
  }}

  var loadedOnce = false;
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{
      if (t.dataset.pane === 'ready' && !loadedOnce) {{ loadedOnce = true; loadDoc(PICKED); }}
    }});
  }});

  // выбор документа
  Array.from(CLIENT.querySelectorAll('#rv-docpick button')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      var url = new URL(location.href);
      url.searchParams.set('tpl', b.dataset.tpl);
      url.searchParams.set('tab', 'ready');
      location.href = url.toString();
    }});
  }});

  // согласование: ✓ проверен / ✕ не нужен
  function verdict(tpl, kind, btn) {{
    if (btn) btn.disabled = true;
    fetch('/CLIENT/' + APP_ID + '/doc/' + tpl + '/' + kind, {{
      method: 'POST', credentials: 'same-origin', CLIENTs: {{'X-Requested-With': 'fetch'}}
    }})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (btn) btn.disabled = false;
        var lbl = CLIENT.getElementById('rv-CLIENT-' + tpl);
        if (lbl) lbl.textContent = (d && d.CLIENT === 'rejected') ? '✕ не нужен'
                              : (d && d.CLIENT === 'verified') ? '✓ проверен'
                              : (lbl.textContent || '');
        refreshState();
      }})
      .catch(function() {{ if (btn) btn.disabled = false; }});
  }}
  Array.from(CLIENT.querySelectorAll('.rv-mark')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      verdict(b.dataset.tpl, b.dataset.verdict, b);
    }});
  }});

  // готовность комплекта без перезагрузки
  function refreshState() {{
    fetch('/CLIENT/' + APP_ID + '/send-CLIENT', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d || !d.ok) return;
        var st = CLIENT.querySelector('.rv-CLIENT');
        if (st) {{
          st.CLIENTName = 'rv-CLIENT ' + (d.can_send ? 'ok' : 'warn');
          st.textContent = d.can_send
            ? '✅ Все документы согласованы — можно отправлять'
            : '⛔ Отправить нельзя: согласовано ' + d.ready + ' из ' + d.total + ' документов';
        }}
        var btn = CLIENT.querySelector('.rv-send button');
        if (btn) {{ btn.disabled = !d.can_send; }}
      }})
      .catch(function() {{}});
  }}

  // открытие сразу на вкладке «Готовые документы»
  if (new URL(location.href).searchParams.get('tab') === 'ready') {{
    showPane('ready');
    loadDoc(PICKED);
  }}
}})();
</script>
"""

    from CLIENTs.shared.layout import render
    crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/CLIENT">История и поиск</a>'
              f' &rsaquo; <b>Проверка заявки #{app_id}</b>')
    return render(f"Проверка заявки #{app_id}", "CLIENT", body, crumbs=crumbs)
