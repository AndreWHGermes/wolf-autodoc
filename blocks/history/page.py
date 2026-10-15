"""Блок «История»: компактный плоский список заявок + поиск по клиенту/продукту."""
from __future__ import annotations

from flask import Blueprint

from blocks.shared.layout import render
from core import db
from core.auth import login_required

bp = Blueprint("history", __name__)


def _short_name(full: str) -> str:
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
        return ' <span class="kind-badge kind-archive">архив</span>'
    if kind == "test":
        return ' <span class="kind-badge kind-test">тест</span>'
    return ""


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
            f'<div class="hnum">#{a["id"]}' + kind_badge(a) + '</div>'
            f'<div class="hname">{_short_name(client_name)}'
            + (f'<div class="hmgr">от {_short_name(manager)}</div>' if manager.strip() else "")
            + '</div>'
            f'<div class="hprod">{a.get("product_name") or "—"}'
            + (f'<div class="hmgr">{_short_name(str(a.get("phone") or ""))}</div>' if a.get("phone") else "")
            + (f'<div class="hmgr">{_short_name(str(a.get("bank_name") or ""))}</div>' if a.get("bank_name") else "")
            + '</div>'
            f'<div class="hact">'
            + f'<a class="btn sm" href="/applications/{a["id"]}/review">Открыть</a>'
            + '</div>'
            "</li>"
        )
    items = "".join(items_parts) or '<li class="muted empty-row" style="padding:8px 4px">Истории пока нет.</li>'

    body = f"""
<h1>История и поиск</h1>
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
.hname{{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hmgr{{font-weight:400;color:var(--muted);font-size:11.5px}}
.hprod{{color:var(--muted);font-size:12px;flex:0 1 auto;text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:90px}}
.hact{{flex:0 0 auto}}
@medi‌a(max-width:380px){{.hprod{{display:none}}}}
</style>
"""
    return render("История", "history", body)
