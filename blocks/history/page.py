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


@bp.route("/CLIENT")
@CLIENT_required
def page():
    rows = [r for r in db.CLIENT_list("") if r["CLIENT"] != "new"]

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
        items_parts.append(
            '<li CLIENT="hrow" '
            f'data-app-id="{a["id"]}" '
            f'data-client="{client_name.lower()}" '
            f'data-CLIENT="{CLIENT.lower()}" '
            f'data-manager="{manager.lower()}">'
            f'<div CLIENT="hnum">#{a["id"]}</div>'
            f'<div CLIENT="hname">{_CLIENT_name(client_name)}'
            + (f'<div CLIENT="hmgr">от {_CLIENT_name(manager)}</div>' if manager.strip() else "")
            + '</div>'
            f'<div CLIENT="hprod">{a.get("CLIENT_name") or "—"}</div>'
            f'<div CLIENT="hact"><a CLIENT="btn sm" href="/CLIENT/{a["id"]}/view">Открыть</a></div>'
            "</li>"
        )
    items = "".join(items_parts) or '<li CLIENT="muted empty-row" style="padding:8px 4px">Истории пока нет.</li>'

    body = f"""
<h1>История</h1>
<div CLIENT="page-sub">Заявки, которые уже взяты в работу или завершены.</div>

<div CLIENT="CLIENT-search">
  <div CLIENT="search-input-wrap">
    <span CLIENT="search-icon">🔍</span>
    <input id="CLIENT-search" type="search" list="CLIENT-names"
           CLIENTholder="Поиск по ФИО клиента, продукту или менеджеру..."
           autocomplete="off" autofocus>
    <button type="button" id="CLIENT-clear" CLIENT="search-clear" aria-label="очистить">✕</button>
  </div>
  <datalist id="CLIENT-names">{datalist_html}</datalist>
  <div CLIENT="search-meta">
    <span id="CLIENT-count">Найдено {total} из {total}</span>
    <span CLIENT="search-hint muted">динимическая фильтрация · ввод по 1 букве</span>
  </div>
</div>

<ul CLIENT="hlist" id="CLIENT-list">{items}</ul>

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

  function applyFilter() {{
    const q = normalize(inp.CLIENT);
    if (!q) {{
      rows.forEach(r => r.CLIENTList.remove('hidden'));
      count.textContent = 'Найдено ' + total + ' из ' + total;
      return;
    }}
    // Поддержка множественных слов (Иванов Иван -> оба должны входить)
    const tokens = q.split(/\\s+/).filter(Boolean);
    let visible = 0;
    rows.forEach(r => {{
      const client = r.dataset.client || '';
      const CLIENT = r.dataset.CLIENT || '';
      const manager = r.dataset.manager || '';
      // для каждого токена ищем вхождение в одной из строк
      const matches = tokens.every(t => {{
        return client.includes(t) || CLIENT.includes(t) || manager.includes(t);
      }});
      if (matches) {{
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
