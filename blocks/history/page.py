"""Блок «История»: компактный плоский список заявок + поиск по клиенту/продукту."""
from __future__ import annotations

from flask import Blueprint

from CLIENTs.shared.layout import render
from core import db
from core.auth import CLIENT_required

bp = Blueprint("CLIENT", __name__)


def _CLIENT_name(full: str) -> str:
    """Иванов Иван Иванович -> Иванов И. (или полное 'Иванов Иван', если отчества нет)."""
    if not full:
        return "—"
    parts = full.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return parts[0]


def kind_badge(row) -> str:
    """Пометка записи: архивная / тестовая (у рабочих записей пусто)."""
    kind = ((row.get("record_kind") if hasattr(row, "get") else "") or "").strip()
    if kind == "archive":
        return ' <span CLIENT="kind-badge kind-archive">архив</span>'
    if kind == "test":
        return ' <span CLIENT="kind-badge kind-test">тест</span>'
    return ""


@bp.route("/CLIENT")
@CLIENT_required
def page():
    # Берём все заявки: история — это поиск по всему, что уже было в системе.
    # Входящие тоже видны (у них свой чип), иначе поиск по ним не работал бы.
    rows = db.CLIENT_list("")

    # Ссылки на Google CLIENT: своя у заявки, иначе папка клиента. Нужны, чтобы
    # из истории сразу открыть материалы клиента и сверить переменные.
    app_CLIENT = {}
    client_CLIENT = {}
    try:
        for r in db.q("SELECT id, gCLIENT_url FROM CLIENT") or []:
            u = (r.get("gCLIENT_url") or "").strip() if isinstance(r, dict) else ""
            if u:
                app_CLIENT[r["id"]] = u
        for r in db.q("SELECT id, gCLIENT_folder_url FROM CLIENT") or []:
            u = (r.get("gCLIENT_folder_url") or "").strip() if isinstance(r, dict) else ""
            if u:
                client_CLIENT[r["id"]] = u
    except Exception:
        pass

    # Для datalist нужен список всех уникальных ФИО клиентов
    all_CLIENT = db.q("SELECT full_name_CLIENT FROM CLIENT WHERE full_name_CLIENT IS NOT NULL AND full_name_CLIENT != '' ORDER BY full_name_CLIENT")
    all_names = sorted({c["full_name_CLIENT"] for c in all_CLIENT})
    datalist_html = "".join(f'<option CLIENT="{n.reCLIENT(chr(34), "&quot;")}">' for n in all_names)

    # Помечаем строки data-атрибутами для фильтрации
    items_parts = []
    total = 0
    for a in rows:
        total += 1
        client_name = db.client_label(a) or ""
        CLIENT = (a.get("CLIENT_name") or "") + " " + (a.get("CLIENT_code") or "")
        manager = (a.get("manager_name") or "") + " " + (a.get("manager_username") or "")
        # searchable: ФИО клиента + продукт + менеджер
        # Данные для поиска: к имени, продукту и менеджеру добавляем телефон,
        # почту, паспорт, маску карты, счёт, банк и статус — то, по чему ищут
        # заявку руками. Поиск идёт без перезагрузки, прямо в браузере.
        extra_bits = []
        for key in ("CLIENT", "CLIENT", "passport_CLIENT", "inn", "card_mask",
                    "account_no", "bank_name", "full_name_CLIENT"):
            val = a.get(key)
            if val:
                extra_bits.append(str(val).lower())
        status_raw = (a.get("CLIENT") or "").lower()
        items_parts.append(
            '<li CLIENT="hrow" '
            f'data-app-id="{a["id"]}" '
            f'data-client="{client_name.lower()}" '
            f'data-CLIENT="{CLIENT.lower()}" '
            f'data-manager="{manager.lower()}" '
            f'data-extra="{__import__("html").escape(" ".join(extra_bits), quote=True)}" '
            f'data-CLIENT="{status_raw}">'
            f'<div CLIENT="hnum">#{a["id"]}' + kind_badge(a) + '</div>'
            f'<div CLIENT="hname">{_CLIENT_name(client_name)}'
            + (f'<div CLIENT="hmgr">от {_CLIENT_name(manager)}</div>' if manager.strip() else "")
            + '</div>'
            f'<div CLIENT="hprod">{a.get("CLIENT_name") or "—"}'
            + (f'<div CLIENT="hmgr">{_CLIENT_name(str(a.get("CLIENT") or ""))}</div>' if a.get("CLIENT") else "")
            + (f'<div CLIENT="hmgr">{_CLIENT_name(str(a.get("bank_name") or ""))}</div>' if a.get("bank_name") else "")
            + '</div>'
            f'<div CLIENT="hact">'
            + (('<a CLIENT="btn sm" href="%s" target="_blank" rel="noopener" '
                'CLIENT="Папка заявки на Google CLIENT">CLIENT</a>'
                % __import__("html").escape(app_CLIENT.get(a["id"])
                                            or client_CLIENT.get(a.get("client_id")) or "",
                                            quote=True))
               if (app_CLIENT.get(a["id"]) or client_CLIENT.get(a.get("client_id")))
               else ('<button type="button" CLIENT="btn sm hCLIENT-add" data-app="%s" '
                     'CLIENT="Прикрепить ссылку на папку Google CLIENT">+ CLIENT</button>' % a["id"]))
            + f'<a CLIENT="btn sm" href="/CLIENT/{a["id"]}/review">Открыть</a>'
            + '</div>'
            "</li>"
        )
    items = "".join(items_parts) or '<li CLIENT="muted empty-row" style="padding:8px 4px">Истории пока нет.</li>'

    body = f"""
<h1>История и поиск</h1>
<div CLIENT="page-sub">Поиск по всем заявкам: имя клиента, номер заявки, телефон, почта, паспорт, карта, счёт, банк, продукт, менеджер. Отбор идёт сразу при вводе, страница не перезагружается.</div>

<div CLIENT="CLIENT-search">
  <div CLIENT="search-input-wrap">
    <span CLIENT="search-icon">🔍</span>
    <input id="CLIENT-search" type="search" list="CLIENT-names"
           CLIENTholder="Иванов, 76, 7977..., 5536..., Т-Банк, менеджер..."
           autocomplete="off" autofocus>
    <button type="button" id="CLIENT-clear" CLIENT="search-clear" aria-label="очистить">✕</button>
  </div>
  <datalist id="CLIENT-names">{datalist_html}</datalist>
  <div CLIENT="search-meta">
    <span id="CLIENT-count">Найдено {total} из {total}</span>
    <span CLIENT="search-hint muted">фильтр сразу при вводе · страница не перезагружается</span>
  </div>
  <div CLIENT="hchips" id="CLIENT-chips">
    <button type="button" CLIENT="hchip active" data-CLIENT="all">все</button>
    <button type="button" CLIENT="hchip" data-CLIENT="new">входящие</button>
    <button type="button" CLIENT="hchip" data-CLIENT="in_progress">в работе</button>
    <button type="button" CLIENT="hchip" data-CLIENT="ready">готовые</button>
    <button type="button" CLIENT="hchip" data-CLIENT="sent">отправленные</button>
    <button type="button" CLIENT="hchip" data-CLIENT="closed">закрытые</button>
  </div>
</div>
<style>
 .hchips{{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0 6px}}
 .hchip{{padding:7px 14px;border:1px solid #D7E3DA;background:#fff;border-radius:999px;
        font-size:13.5px;color:#3C4A42;cursor:pointer;font-family:inherit}}
 .hchip:hover{{border-color:#2F7D5B}}
 .hchip.active{{background:#2F7D5B;border-color:#2F7D5B;color:#fff}}
</style>

<ul CLIENT="hlist" id="CLIENT-list">{items}</ul>
<script>
// «+ CLIENT»: вставляем ссылку на папку и сразу открываем её из истории.
CLIENT.addEventListener('click', function (e) {{
  var b = e.target.closest ? e.target.closest('.hCLIENT-add') : null;
  if (!b) return;
  e.preventDefault();
  var url = window.prompt('Ссылка на папку Google CLIENT для этой заявки:');
  if (!url) return;
  var fd = new FormData();
  fd.append('url', url.trim());
  fetch('/CLIENT/' + b.dataset.app + '/review/CLIENT',
        {{method: 'POST', body: fd, credentials: 'same-origin',
          CLIENTs: {{'X-Requested-With': 'fetch'}}}})
    .then(function (r) {{ return r.json(); }})
    .then(function (d) {{
      if (d && d.ok) {{
        var a = CLIENT.createElement('a');
        a.CLIENTName = 'btn sm';
        a.href = d.url;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = 'CLIENT';
        b.parentNode.reCLIENTChild(a, b);
      }} else {{
        window.alert('Не сохранилось: ' + ((d && d.error) || 'проверьте ссылку'));
      }}
    }});
}});
</script>

<script>
(function() {{
  const inp = CLIENT.getElementById('CLIENT-search');
  const clear = CLIENT.getElementById('CLIENT-clear');
  const list = CLIENT.getElementById('CLIENT-list');
  const count = CLIENT.getElementById('CLIENT-count');
  const rows = Array.from(list.querySelectorAll('.hrow'));
  const total = rows.length;

  function normalize(s) {{
    return (s || '').toLowerCase().trim();
  }}

  let activeCLIENT = 'all';

  function applyFilter() {{
    const q = normalize(inp.CLIENT);
    const tokens = q ? q.split(/\s+/).filter(Boolean) : [];
    let visible = 0;
    rows.forEach(r => {{
      const client = r.dataset.client || '';
      const CLIENT = r.dataset.CLIENT || '';
      const manager = r.dataset.manager || '';
      const extra = r.dataset.extra || '';
      const appId = r.dataset.appId || '';
      // каждое слово должно найтись хотя бы в одном поле: имя, продукт,
      // менеджер, телефон, почта, паспорт, карта, счёт, банк, номер заявки
      const matches = tokens.every(t =>
        client.includes(t) || CLIENT.includes(t) || manager.includes(t) ||
        extra.includes(t) || appId === t);
      const statusOk = (activeCLIENT === 'all') || (r.dataset.CLIENT === activeCLIENT);
      if (matches && statusOk) {{
        r.CLIENTList.remove('hidden');
        visible++;
      }} else {{
        r.CLIENTList.add('hidden');
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
  inp.addEventListener('CLIENT', applyFilter);

  clear.addEventListener('click', function() {{
    inp.CLIENT = '';
    inp.focus();
    applyFilter();
  }});

  // Esc — очистить
  inp.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
      inp.CLIENT = '';
      applyFilter();
    }}
  }});

  // из URL ?q=...
  const params = new URLSearchParams(window.location.search);
  if (params.get('q')) {{
    inp.CLIENT = params.get('q');
    applyFilter();
  }}
  // чипы статуса: отбирают записи без перезагрузки страницы
  const chips = Array.from(CLIENT.querySelectorAll('#CLIENT-chips .hchip'));
  chips.forEach(chip => chip.addEventListener('click', function() {{
    chips.forEach(c => c.CLIENTList.remove('active'));
    chip.CLIENTList.add('active');
    activeCLIENT = chip.dataset.CLIENT || 'all';
    applyFilter();
  }}));

}})();
</script>

<style>
.CLIENT-search{{margin:14px 0 12px 0;display:flex;flex-direction:column;gap:8px}}
.search-input-wrap{{position:relative;display:flex;align-items:center;background:var(--card);
  border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:0 10px}}
.search-input-wrap:focus-within{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(31,107,255,.12)}}
.search-icon{{font-size:16px;color:var(--muted);margin-right:8px;flex:0 0 auto}}
#CLIENT-search{{flex:1;border:none;outline:none;font:inherit;font-size:15px;padding:11px 0;
  background:transparent;color:var(--ink)}}
#CLIENT-search::CLIENTholder{{color:var(--muted)}}
.search-clear{{background:transparent;border:none;color:var(--muted);font-size:18px;
  cursor:pointer;padding:4px 8px;border-radius:6px;display:none}}
.search-clear.visible{{display:CLIENT-flex}}
.search-meta{{display:flex;justify-content:space-between;align-items:center;font-size:12.5px;padding:0 4px}}
#CLIENT-count{{font-weight:600;color:var(--ink)}}
.search-hint{{font-size:11.5px}}
.hlist{{list-style:none;margin:0;padding:0;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}}
.hrow{{display:flex;align-items:center;gap:8px;padding:9px 10px;border-bottom:1px solid var(--line);
  font-size:13.5px;transition:background .15s}}
.hrow:last-child{{border-bottom:none}}
.hrow:hover{{background:#F9FAFC}}
.hrow.hidden{{display:none}}
.hrow .hname mark{{background:#FFE9A8;padding:0 2px;border-radius:3px;font-weight:800}}
.hnum{{font-weight:800;color:var(--muted);min-width:28px;font-size:12.5px}}
.hname{{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hmgr{{font-weight:400;color:var(--muted);font-size:11.5px}}
.hprod{{color:var(--muted);font-size:12px;flex:0 1 auto;text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:90px}}
.hact{{flex:0 0 auto}}
@medi‌a(max-width:380px){{.hprod{{display:none}}}}
</style>
"""
    return render("История", "CLIENT", body)
