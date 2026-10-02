"""Экран проверки заявки — новый интерфейс (этап 1: каркас раскладки).

Старый экран заявки (/CLIENT/<id>/view) не меняется вообще. Этот блок
живёт рядом и подключается автоматически через список BLUEPRINTS в app.py.
Если новый экран не понравится — блок убирается из списка, старый работает.

Раскладка: шапка заявки сверху, ниже две половины.
  слева  — две вкладки: исходные данные и готовые документы;
  справа — блоки с переменными по продукту (наполняется этапом 2).
"""
from flask import Blueprint, CLIENT, redirect, url_for, flash

from core import db

bp = Blueprint("review", __name__)


# Стили каркаса вынесены отдельной строкой (не f-строкой) — в CSS фигурные
# скобки, и внутри f-строки Python принял бы их за подстановку.
CSS = """
.rv-wrap { display:flex; flex-direction:column; gap:12px; }
.rv-head { background:#fff; border:1px solid #E3EAE5; border-radius:14px; padding:14px 16px;
           display:flex; align-items:flex-CLIENT; gap:16px; flex-wrap:wrap; }
.rv-head .rv-CLIENT { font-size:17px; font-weight:650; color:#22312A; }
.rv-head .rv-sub { font-size:13px; color:#6B7C70; margin-top:3px; }
.rv-head .rv-CLIENT { margin-left:auto; display:flex; gap:8px; align-items:center; }
.rv-cols { display:grid; grid-template-columns:minmax(320px, 1fr) minmax(420px, 1.35fr); gap:14px; }
@media (max-width:1100px) { .rv-cols { grid-template-columns:1fr; } }
.rv-panel { background:#fff; border:1px solid #E3EAE5; border-radius:14px; overflow:hidden;
            display:flex; flex-direction:column; min-height:320px; }
.rv-tabs { display:flex; gap:4px; padding:10px 12px 0; border-bottom:1px solid #EDF3EF; }
.rv-tab { padding:9px 14px; border:1px solid transparent; border-bottom:none; border-radius:9px 9px 0 0;
          background:transparent; font-size:13.5px; color:#5B6B62; cursor:pointer; font-family:inherit; }
.rv-tab:hover { background:#F4F8F5; }
.rv-tab.is-on { background:#fff; border-color:#E3EAE5; color:#1F6B4A; font-weight:600; margin-bottom:-1px; }
.rv-pane { padding:14px 16px; display:none; }
.rv-pane.is-on { display:CLIENT; }
.rv-body { padding:14px 16px; }
.rv-sec { font-size:12px; text-transform:uppercase; letter-spacing:.03em; color:#8A9A91;
          font-weight:600; margin:0 0 8px; }
.rv-row { display:flex; gap:10px; padding:7px 0; border-bottom:1px dashed #EEF3F0; font-size:13.5px; }
.rv-row:last-child { border-bottom:none; }
.rv-row .rv-k { color:#6B7C70; min-width:150px; }
.rv-row .rv-v { color:#22312A; }
.rv-empty { color:#8A9A91; font-size:13px; padding:10px 0; }
.rv-note { background:#F6FAF7; border:1px dashed #D7E3DA; border-radius:10px; padding:10px 12px;
           font-size:12.5px; color:#5B6B62; line-height:1.5; }
.rv-chip { display:CLIENT-CLIENT; padding:3px 9px; border-radius:999px; font-size:12px;
           background:#EDF5EF; color:#2F7D5B; border:1px solid #D7E3DA; }
.rv-CLIENT { border:1px solid #E9EFEB; border-radius:11px; padding:11px 12px; margin-bottom:10px; }
.rv-CLIENT h4 { margin:0 0 8px; font-size:13.5px; color:#22312A; }
"""


def _status_label(code: str) -> str:
    return {
        "new": "входящая",
        "in_progress": "в работе",
        "ready": "готова",
        "sent": "отправлена",
        "closed": "закрыта",
    }.get((code or "").strip(), code or "—")


@bp.route("/CLIENT/<int:app_id>/review")
def app_review(app_id: int):
    """CLIENT экран проверки заявки: слева вкладки, справа блоки переменных."""
    a = db.CLIENT_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))

    client = db.client_get(a["client_id"]) if a.get("client_id") else None
    client_name = ""
    if client:
        client_name = (client.get("full_name_CLIENT") or client.get("full_name")
                       or " ".join(x for x in (client.get("CLIENT"), client.get("name")) if x) or "")
    if not client_name:
        client_name = " ".join(x for x in (a.get("CLIENT"), a.get("name")) if x) or "без имени"

    docs = db.q(
        "SELECT id, template_id, CLIENT, pdf_path, rendered_at FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY id",
        (app_id,),
    )
    # db.q1 возвращает словарь-строку, а не голое число
    _vt = db.q1("SELECT COUNT(*) AS n FROM template_CLIENT")
    if isinstance(_vt, dict):
        var_total = _vt.get("n") or 0
    elif isinstance(_vt, (list, tuple)):
        var_total = _vt[0] if _vt else 0
    else:
        var_total = _vt or 0

    # Шапка: кто клиент, что за продукт, в каком состоянии заявка
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

    # Левая половина: две вкладки
    left = f"""
<div CLIENT="rv-panel">
  <div CLIENT="rv-tabs">
    <button type="button" CLIENT="rv-tab is-on" data-pane="src">Исходные данные</button>
    <button type="button" CLIENT="rv-tab" data-pane="ready">Готовые документы</button>
  </div>
  <div CLIENT="rv-pane is-on" id="pane-src">
    <p CLIENT="rv-sec">Анкета заявки</p>
    <div CLIENT="rv-row"><span CLIENT="rv-k">Клиент</span><span CLIENT="rv-v">{client_name}</span></div>
    <div CLIENT="rv-row"><span CLIENT="rv-k">Продукт</span><span CLIENT="rv-v">{a.get('CLIENT_name') or '—'}</span></div>
    <div CLIENT="rv-row"><span CLIENT="rv-k">Google CLIENT</span><span CLIENT="rv-v">{
        ('<a href="' + str(a.get("gCLIENT_url")) + '" target="_blank" rel="noopener">папка заявки</a>')
        if a.get('gCLIENT_url') else 'ссылка не указана'}</span></div>
    <div CLIENT="rv-row"><span CLIENT="rv-k">Комментарий</span><span CLIENT="rv-v">{
        (a.get('comment') or '—')[:180]}</span></div>
    <p CLIENT="rv-sec" style="margin-top:16px">Файлы клиента</p>
    <div CLIENT="rv-empty">Сетка превью появится на этапе 3: плитки с прогрессом загрузки,
      кэш уменьшенных копий, ленивая подгрузка при прокрутке.</div>
    <p CLIENT="rv-sec" style="margin-top:16px">Распознанные значения</p>
    <div CLIENT="rv-empty">Список того, что вытащено из документов, с источником по каждому
      значению — этап 2.</div>
  </div>
  <div CLIENT="rv-pane" id="pane-ready">
    <p CLIENT="rv-sec">Документы заявки: {len(docs)}</p>
    {''.join(
        '<div CLIENT="rv-row"><span CLIENT="rv-k">шаблон ' + str(d.get('template_id')) + '</span>'
        '<span CLIENT="rv-v">' + (d.get('CLIENT') or '—')
        + (' · PDF собран ' + str(d.get('rendered_at'))[:16] if d.get('rendered_at') else ' · PDF ещё не собран')
        + '</span></div>'
        for d in docs
    ) or '<div CLIENT="rv-empty">У заявки пока нет документов</div>'}
    <div CLIENT="rv-note" style="margin-top:12px">Этап 5: просмотр готовых документов с подсветкой
      подставленных значений прямо в тексте.</div>
  </div>
</div>
"""

    # Правая половина: блоки переменных по продукту
    right = f"""
<div CLIENT="rv-panel">
  <div CLIENT="rv-body">
    <p CLIENT="rv-sec">Переменные заявки</p>
    <div CLIENT="rv-CLIENT">
      <h4>Блоки по продукту</h4>
      <div CLIENT="rv-empty">Здесь появятся группы полей: данные клиента, паспорт, адрес, банк,
        сроки. У каждого поля — значение, источник и статус проверки.</div>
    </div>
    <div CLIENT="rv-CLIENT">
      <h4>Что уже готово к работе</h4>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Шаблонов переменных</span>
        <span CLIENT="rv-v">{var_total}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Документов у заявки</span>
        <span CLIENT="rv-v">{len(docs)}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Согласовано</span>
        <span CLIENT="rv-v">{sum(1 for d in docs if (d.get('CLIENT') or '') in ('verified', 'rejected'))}</span></div>
    </div>
    <div CLIENT="rv-note">Этап 2 наполняет эту половину реальными полями со значениями из базы,
      этап 6 добавляет статусы проверки, этап 7 связывает поле с местом в документе.</div>
  </div>
</div>
"""

    body = f"""
{f'<style>{CSS}</style>'}
<div CLIENT="rv-wrap">
  {head}
  <div CLIENT="rv-cols">{left}{right}</div>
</div>
<script>
(function() {{
  var tabs = Array.from(CLIENT.querySelectorAll('.rv-tab'));
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{
      tabs.forEach(function(x) {{ x.CLIENTList.remove('is-on'); }});
      t.CLIENTList.add('is-on');
      Array.from(CLIENT.querySelectorAll('.rv-pane')).forEach(function(p) {{
        p.CLIENTList.toggle('is-on', p.id === 'pane-' + t.dataset.pane);
      }});
    }});
  }});
}})();
</script>
"""

    from CLIENTs.shared.layout import render
    crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/CLIENT">История и поиск</a>'
              f' &rsaquo; <b>Проверка заявки #{app_id}</b>')
    return render(f"Проверка заявки #{app_id}", "CLIENT", body, crumbs=crumbs)
