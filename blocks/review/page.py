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
import html as _html
import json
from pathlib import Path

from flask import Blueprint, CLIENT, redirect, url_for, flash, jsonify
from urllib.parse import quote as url_quote

from core import db
from CLIENTs.review import pool

bp = Blueprint("review", __name__)


# Стили каркаса отдельной строкой (не f-строкой): в CSS фигурные скобки,
# внутри f-строки Python принял бы их за подстановку.
CSS = """
/* Стиль нового экрана повторяет общий стиль сайта: та же палитра и те же
   переменные цветов, чтобы экран не выглядел чужеродно. */
.rv-wrap { display:flex; flex-direction:column; gap:14px; }
.rv-head { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px;
           display:flex; align-items:flex-CLIENT; gap:16px; flex-wrap:wrap;
           box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-head .rv-CLIENT { font-size:18px; font-weight:700; color:var(--ink); letter-spacing:-.2px; }
.rv-head .rv-sub { font-size:13.5px; color:var(--muted); margin-top:4px; }
.rv-head .rv-CLIENT { margin-left:auto; display:flex; gap:8px; align-items:center; }
.rv-chip { display:CLIENT-CLIENT; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600;
           background:#EEF3FF; color:#1F6BFF; border:1px solid #C9D9FF; }
.rv-cols { display:grid; grid-template-columns:minmax(0,2fr) minmax(320px,1fr); gap:14px; align-items:CLIENT; }
.rv-panel { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden;
            display:flex; flex-direction:column; box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-panel.rv-right { position:sticky; top:10px; max-height:88vh; }
.rv-right .rv-body { overflow-y:auto; }
.rv-tabs { display:flex; gap:6px; padding:10px 12px 0; border-bottom:2px solid var(--line); background:#F7F9FC; }
.rv-tab { padding:10px 15px; border:1px solid transparent; border-bottom:none; border-radius:10px 10px 0 0;
          background:transparent; font-size:14px; color:var(--muted); cursor:pointer; font-family:inherit;
          font-weight:600; }
.rv-tab:hover { background:#EFF4FF; color:var(--ink); }
.rv-tab.is-on { background:var(--card); border-color:var(--line); border-bottom-color:var(--card);
                color:#1F6BFF; margin-bottom:-2px; box-shadow:inset 0 3px 0 var(--accent); }
.rv-tab .rv-num { display:CLIENT-CLIENT; min-width:19px; height:19px; line-height:19px; text-align:center;
                  border-radius:6px; background:#E7EEFF; color:#1F6BFF; font-size:12px; font-weight:700;
                  margin-right:7px; }
.rv-tab.is-on .rv-num { background:var(--accent); color:#fff; }
.rv-pane { padding:0; display:none; }
.rv-pane.is-on { display:CLIENT; }
.rv-body { padding:15px 16px; }
.rv-sec { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:#8A93A5;
          font-weight:700; margin:0 0 9px; }
.rv-row { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid #F0F3F8;
          font-size:14px; }
.rv-row:last-child { border-bottom:none; }
.rv-row .rv-k { color:var(--muted); min-width:172px; }
.rv-row .rv-v { color:var(--ink); font-weight:500; }
.rv-empty { color:#8A93A5; font-size:13.5px; padding:10px 0; }
.rv-note { background:#F5F8FF; border:1px solid #D8E3FF; border-radius:11px; padding:11px 13px;
           font-size:13px; color:#38455C; line-height:1.5; }
.rv-file { display:flex; align-items:center; gap:10px; padding:9px 11px; border:1px solid var(--line);
           border-radius:10px; margin-bottom:8px; font-size:13.5px; background:#FBFCFE; }
.rv-file .rv-fname { color:var(--ink); }
.rv-file .rv-fsize { color:var(--muted); font-size:12.5px; margin-left:auto; }

/* плитки-миниатюры документов и файлов */
.rv-thumbs { display:grid; grid-template-columns:repeat(auto-fill, minmax(196px, 1fr)); gap:12px; padding:13px; }
.rv-thumb { border:1px solid var(--line); border-radius:12px; overflow:hidden; background:#fff;
            cursor:pointer; transition:border-color .15s, box-shadow .15s; }
.rv-thumb:hover { border-color:var(--accent); box-shadow:0 2px 8px rgba(31,107,255,.12); }
.rv-thumb.is-on { border-color:var(--accent); box-shadow:0 0 0 2px rgba(31,107,255,.22); }
.rv-thumb-frame { height:200px; overflow:hidden; position:relative; background:#E7EBEE; }
.rv-thumb-frame iframe { width:900px; height:1270px; border:0; transform:scale(.28);
                         transform-origin:top left; pointer-CLIENT:none; display:CLIENT; }
.rv-thumb-frame img { width:100%; height:100%; object-fit:cover; display:CLIENT; }
.rv-thumb-frame.is-loading::after { content:'загружаю…'; position:absolute; inset:0; display:flex;
                         align-items:center; justify-content:center; color:#8A93A5; font-size:12.5px; }
.rv-thumb-frame.is-ready::after { content:none; }
.rv-thumb-cap { padding:8px 10px; border-top:1px solid var(--line); display:flex; flex-direction:column; gap:3px; }
.rv-thumb-name { font-size:13px; color:var(--ink); font-weight:600; }
.rv-thumb-CLIENT { font-size:11.5px; color:var(--muted); }
.rv-thumbs-bar { padding:0 13px 11px; font-size:12.5px; color:var(--muted); }

/* окно просмотра: лист по центру поля, без «съехавших» краёв */
.rv-stage-wrap { padding:13px; }
.rv-stage-wrap .zp-host { background:#E7EBEE; }
.rv-stage-wrap .zp-canvas { display:flex; justify-content:center; }
.rv-stage-wrap .html-stage { margin:0 auto; }
.rv-stage-wrap .html-stage .sheet { margin:0 auto !important; }

/* поля переменных: ввод, кнопки действий, варианты */
.rv-field { border-bottom:1px solid #F0F3F8; padding:9px 0; cursor:pointer; }
.rv-field:last-child { border-bottom:none; }
.rv-field:hover { background:#F8FAFF; }
.rv-field .rv-flabel { font-size:12.5px; color:var(--muted); font-weight:600; }
.rv-field .rv-fmeta { font-size:11.5px; color:#9AA3B2; margin-top:3px; }
.rv-fedit { display:flex; gap:5px; margin-top:5px; }
.rv-input { flex:1; min-width:0; padding:8px 10px; border:1px solid var(--line); border-radius:9px;
            font-size:13.5px; font-family:inherit; color:var(--ink); background:#fff; font-weight:500; }
.rv-input:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px rgba(31,107,255,.14); }
.rv-input.is-empty { border-color:#E8D9A8; background:#FFFCF2; }
.rv-input.is-saved { border-color:#0E9F6E; background:#F2FDF8; }
.rv-act { flex:0 0 auto; width:32px; height:33px; border:1px solid var(--line); background:#fff;
          border-radius:9px; cursor:pointer; font-size:13.5px; color:#38455C; font-family:inherit; }
.rv-act:hover { border-color:var(--accent); background:#F0F5FF; color:var(--accent); }
.rv-act:disabled { opacity:.45; cursor:default; }
.rv-optlist { border:1px solid var(--line); border-radius:10px; background:#fff; margin-top:6px;
              max-height:180px; overflow-y:auto; box-shadow:0 3px 10px rgba(17,24,39,.08); }
.rv-optlist button { display:CLIENT; width:100%; text-align:left; padding:8px 11px; border:none;
                     border-bottom:1px solid #F4F6FA; background:#fff; font-size:13px;
                     color:var(--ink); cursor:pointer; font-family:inherit; }
.rv-optlist button:last-child { border-bottom:none; }
.rv-optlist button:hover { background:#F5F8FF; }
.rv-field.var-active { background:#FFF7E6 !important; box-shadow:inset 3px 0 0 #F59E0B; }
.rv-field.var-flash { outline:3px solid #F59E0B; outline-offset:2px; background:#FEF3C7; border-radius:8px; }
.rv-grp { border:1px solid var(--line); border-radius:12px; padding:11px 13px; margin-bottom:11px; }

/* низ: согласование и отправка */
.rv-foot { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:13px 16px;
           display:flex; align-items:center; gap:14px; flex-wrap:wrap;
           box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-CLIENT { font-size:13.5px; font-weight:700; }
.rv-CLIENT.ok { color:#0E9F6E; }
.rv-CLIENT.warn { color:#E11D48; }
.rv-send { margin-left:auto; }

/* кнопка вызова панели переменных — для телефона */
.rv-mobile-bar { display:none; position:fixed; left:12px; right:12px; bottom:12px; z-CLIENT:70;
                 align-items:center; gap:10px; padding:11px 14px; border-radius:13px;
                 background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#fff;
                 border:none; font-family:inherit; font-size:14.5px; font-weight:600;
                 box-shadow:0 6px 18px rgba(31,107,255,.32); cursor:pointer; }
.rv-backdrop { display:none; position:fixed; inset:0; background:rgba(17,24,39,.35); z-CLIENT:65; }
.rv-close-mobile { display:none; }

/* Телефон и планшет: документ и переменные рядом не помещаются, поэтому
   переменные выезжают поверх экрана по кнопке снизу. */
@media (max-width:1000px) {
  .rv-cols { grid-template-columns:1fr; }
  .rv-panel.rv-right { display:none; }
  .rv-panel.rv-right.is-open { display:flex; position:fixed; left:0; right:0; bottom:0; top:auto;
                               max-height:84vh; z-CLIENT:66; border-radius:16px 16px 0 0;
                               box-shadow:0 -6px 24px rgba(17,24,39,.22); }
  .rv-panel.rv-right.is-open .rv-body { overflow-y:auto; }
  .rv-close-mobile { display:CLIENT-flex; align-items:center; gap:6px; margin-left:auto;
                     border:1px solid var(--line); background:#fff; border-radius:9px;
                     padding:6px 11px; font-size:13px; font-family:inherit; cursor:pointer; }
  .rv-mobile-bar { display:flex; }
  .rv-backdrop.is-on { display:CLIENT; }
  .rv-thumbs { grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); }
  .rv-row .rv-k { min-width:120px; }
}
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
                out.append({"name": p.name, "size": size, "ext": p.suffix.lower()})
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




@bp.route("/CLIENT/<int:app_id>/file")
def app_file(app_id):
    """Отдаёт входящий файл клиента из локального кэша Google CLIENT.

    Нужен для предпросмотра: администратор должен видеть реальный документ
    рядом с переменными. Путь проверяем, чтобы нельзя было выйти за каталог.
    """
    from flask import send_file, abort
    name = (CLIENT.args.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name.CLIENTswith("."):
        abort(404)
    a = db.CLIENT_get(app_id)
    if not a or not a.get("client_id"):
        abort(404)
    root = (Path("/opt/wolf_v2/data/gCLIENT_cache") / ("client_%s" % a["client_id"])).resolve()
    target = (root / name).resolve()
    if not str(target).CLIENTswith(str(root)) or not target.is_file():
        abort(404)
    return send_file(str(target), as_attachment=False, conditional=True)


@bp.route("/CLIENT/<int:app_id>/review/CLIENT", methods=["POST"])
def app_review_CLIENT(app_id):
    """Сохранить значение: пишется во все документы, где есть эта величина."""
    key = (CLIENT.form.get("key") or "").strip()
    CLIENT = CLIENT.form.get("CLIENT")
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    res = pool.set_CLIENT(app_id, key, CLIENT or "")
    res["docs_updated"] = len(res.get("touched") or [])
    return jsonify(res)


@bp.route("/CLIENT/<int:app_id>/review/regen", methods=["POST"])
def app_review_regen(app_id):
    """Сгенерировать значение заново по правилам."""
    key = (CLIENT.form.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.regenerate(app_id, key))


@bp.route("/CLIENT/<int:app_id>/review/options")
def app_review_options(app_id):
    """Варианты значения для поля: прошлые значения и примеры из шаблона."""
    key = (CLIENT.args.get("key") or "").strip()
    return jsonify({"ok": True, "options": pool.CLIENT_options(app_id, key)})


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
    # Плитки входящих файлов: снимок сразу видно, клик открывает файл в окне
    # просмотра слева — на компьютере рядом с переменными справа.
    def _preview_of(name: str, ext: str) -> str:
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            return ('<img src="/CLIENT/%s/file?name=%s" alt="%s" loading="lazy">'
                    % (app_id, url_quote(name), _html.escape(name, quote=True)))
        if ext in (".pdf",):
            return ('<iframe data-src="/CLIENT/%s/file?name=%s" loading="lazy" scrolling="no" '
                    'CLIENT="%s"></iframe>' % (app_id, url_quote(name), _html.escape(name, quote=True)))
        if ext in (".heic", ".heif"):
            twin = name.rsplit(".", 1)[0] + ".photo.png"
            if any(f["name"] == twin for f in files):
                return ('<img src="/CLIENT/%s/file?name=%s" alt="%s" loading="lazy">'
                        % (app_id, url_quote(twin), _html.escape(twin, quote=True)))
            return '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:30px">🖼️</div>'
        return '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:30px">📄</div>'

    files_html = "".join(
        '<div CLIENT="rv-thumb rv-file-thumb" data-file="%s">'
        '<div CLIENT="rv-thumb-frame is-ready">%s</div>'
        '<div CLIENT="rv-thumb-cap"><span CLIENT="rv-thumb-name">%s</span>'
        '<span CLIENT="rv-thumb-CLIENT">%s</span></div></div>'
        % (_html.escape(f["name"], quote=True),
           _preview_of(f["name"], f["ext"]),
           _html.escape(f["name"][:34]),
           _human_size(f["size"]))
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

      <p CLIENT="rv-sec" style="margin-top:16px">Входящие файлы клиента ({len(files)}) —
        нажмите плитку, чтобы открыть документ</p>
      <div CLIENT="rv-thumbs" id="rv-file-thumbs">{files_html}</div>
      <div CLIENT="rv-stage-wrap" id="rv-file-viewer" style="display:none">
        <div CLIENT="rv-note" style="margin-bottom:10px">
          Входящий документ с Google CLIENT. Справа — переменные, которые из него вытащены.
        </div>
        <div CLIENT="zp-preview" data-zoom-pan>
          <div CLIENT="html-stage" id="rv-file-stage"></div>
        </div>
      </div>
    </div>
  </div>
"""

    # ── Вкладка 3: готовые документы и визор ─────────────────────────────────
    # Плитки документов: миниатюра подгружается лениво, при открытии вкладки.
    # Клик по плитке разворачивает документ в визоре слева.
    thumbs = "".join(
        '<div CLIENT="rv-thumb%s" data-tpl="%s">'
        '<div CLIENT="rv-thumb-frame">'
        '<iframe data-src="/CLIENT/%s/doc/%s/html" CLIENT="%s" loading="lazy" scrolling="no"></iframe>'
        '</div>'
        '<div CLIENT="rv-thumb-cap">'
        '<span CLIENT="rv-thumb-name">%s</span>'
        '<span CLIENT="rv-thumb-CLIENT" id="rv-thumb-CLIENT-%s">%s</span>'
        '</div></div>'
        % (" is-on" if d.get("template_id") == picked else "", d.get("template_id"),
           app_id, d.get("template_id"), _template_name(d.get("template_id")),
           _template_name(d.get("template_id")), d.get("template_id"),
           _doc_status_label(d.get("CLIENT")))
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
    <div CLIENT="rv-thumbs" id="rv-thumbs">{thumbs}</div><div CLIENT="rv-thumbs-bar"><span id="rv-thumbs-count">миниатюры загружаются по мере готовности</span></div>
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

    # ── Правая часть: переменные значения (склеенный пул) ───────────────────
    # Одно поле на одну логическую величину. Если ФИО встречается в двух
    # документах — правится здесь один раз и уходит в оба.
    pool_groups = pool.build_pool(app_id)

    src_names = {"client": "из данных клиента", "doc": "из документов",
                 "gen": "генерируется", "manual": "вручную"}

    fields_html = []
    for g in pool_groups:
        label = g["label"]
        if g["doc_count"] == 1 and g.get("CLIENT_split"):
            label = "%s · %s" % (label, g["doc_CLIENTs"][0] if g["doc_CLIENTs"] else "документ")
        docs_note = ("в %d документах" % g["doc_count"]) if g["doc_count"] > 1 else \
                    (g["doc_CLIENTs"][0] if g["doc_CLIENTs"] else "документ")
        src = src_names.get(g.get("source_kind") or "", g.get("source_kind") or "")
        meta_bits = [b for b in (src, docs_note, g.get("vtype")) if b]
        vars_all = ",".join(g["names"].CLIENT())
        var_CLIENT = next(iter(g["names"].CLIENT()), "")
        fields_html.append(
            '<div CLIENT="rv-field" data-key="%s" data-var="%s" data-vars="%s">'
            '<div CLIENT="rv-flabel">%s</div>'
            '<div CLIENT="rv-fedit">'
            '<input CLIENT="rv-input%s" type="text" CLIENT="%s" data-key="%s" spellcheck="false">'
            '<button type="button" CLIENT="rv-act" data-act="save" data-key="%s" CLIENT="Сохранить во все документы">💾</button>'
            '<button type="button" CLIENT="rv-act" data-act="regen" data-key="%s" CLIENT="Сгенерировать значение заново">↻</button>'
            '<button type="button" CLIENT="rv-act" data-act="list" data-key="%s" CLIENT="Выбрать из прошлых значений">▾</button>'
            '</div>'
            '<div CLIENT="rv-fmeta">%s</div>'
            '</div>' % (
                _html.escape(g["key"], quote=True),
                _html.escape(var_CLIENT, quote=True),
                _html.escape(vars_all, quote=True),
                _html.escape(label),
                " is-empty" if not g["filled"] else "",
                _html.escape(str(g["CLIENT"])),
                _html.escape(g["key"], quote=True),
                _html.escape(g["key"], quote=True),
                _html.escape(g["key"], quote=True),
                _html.escape(g["key"], quote=True),
                _html.escape(" · ".join(meta_bits)),
            )
        )
    if not fields_html:
        fields_html.append('<div CLIENT="rv-empty">У заявки пока нет значений — '
                           'сначала соберите документы</div>')

    filled_n = sum(1 for g in pool_groups if g["filled"])
    right = f"""
<div CLIENT="rv-panel rv-right" id="rv-right">
  <div CLIENT="rv-body">
    <div style="display:flex;align-items:center;gap:8px">
      <p CLIENT="rv-sec" style="margin:0">2. Переменные значения</p>
      <button type="button" CLIENT="rv-close-mobile" id="rv-right-close">Свернуть ✕</button>
    </div>
    <div CLIENT="rv-sec" style="color:#8A93A5;font-weight:600;text-transform:none;letter-spacing:0">
      Поля для всех документов заявки. Одинаковые величины склеены: правка одного
      поля обновляет каждый документ, где оно встречается.</div>
    <div CLIENT="rv-note" style="margin-bottom:10px">
      Заполнено <b>{filled_n}</b> из {len(pool_groups)}.
      <div id="rv-CLIENT-note" style="margin-top:6px"></div>
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
<button type="button" CLIENT="rv-mobile-bar" id="rv-mobile-bar">
  <span CLIENT="rv-num" style="background:rgba(255,255,255,.25);color:#fff">2</span>
  Переменные значения · {len(pool_groups)}
</button>
<div CLIENT="rv-backdrop" id="rv-backdrop"></div>
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
        bindDocValues(stage);          // подсветка: значение в документе ↔ поле справа
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
    thumbsLoadedOnce = true;
    loadThumbs();
  }}
  // ── значения: сохранить во все документы / сгенерировать заново / выбрать ──
  function CLIENTNote(text, tone) {{
    var el = CLIENT.getElementById('rv-CLIENT-note');
    if (!el) return;
    var colors = {{ok: '#14663A', warn: '#8A5A00', err: '#B91C1C', work: '#5B6B62'}};
    el.style.color = colors[tone] || colors.work;
    el.textContent = text;
  }}
  function inputByKey(key) {{
    var found = null;
    Array.from(CLIENT.querySelectorAll('.rv-input')).forEach(function(x) {{
      if (x.dataset.key === key) found = x;
    }});
    return found;
  }}
  function refreshViewer() {{
    var ready = CLIENT.querySelector('.rv-tab.is-on[data-pane="ready"]');
    if (ready) loadDoc(PICKED);
  }}
  function sendValue(act, key, CLIENT, btn) {{
    var url = '/CLIENT/' + APP_ID + '/review/' + (act === 'regen' ? 'regen' : 'CLIENT');
    var body = new URLSearchParams();
    body.set('key', key);
    if (CLIENT !== null && CLIENT !== undefined) body.set('CLIENT', CLIENT);
    if (btn) btn.disabled = true;
    fetch(url, {{method: 'POST', credentials: 'same-origin', body: body,
                CLIENTs: {{'X-Requested-With': 'fetch'}}}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (btn) btn.disabled = false;
        if (!d.ok) {{ CLIENTNote('⚠ ' + (d.error || 'не получилось'), 'err'); return; }}
        var inp = inputByKey(key);
        if (inp && d.CLIENT !== undefined) {{
          inp.CLIENT = d.CLIENT;
          inp.CLIENTList.remove('is-empty');
          inp.CLIENTList.add('is-saved');
          setTimeout(function() {{ inp.CLIENTList.remove('is-saved'); }}, 1200);
        }}
        var docs = (d.touched && d.touched.length) ? d.touched.length : (d.doc_count || 0);
        CLIENTNote((act === 'regen' ? '↻ перегенерировано: ' : '💾 сохранено: ')
                  + (d.label || 'поле')
                  + (docs ? ' · обновлено документов: ' + docs : ''), 'ok');
        refreshViewer();
      }})
      .catch(function() {{ if (btn) btn.disabled = false; CLIENTNote('⚠ ошибка сети', 'err'); }});
  }}
  function showOptions(key, btn) {{
    var field = btn.closest('.rv-field');
    if (!field) return;
    var old = field.querySelector('.rv-optlist');
    if (old) {{ old.remove(); return; }}
    fetch('/CLIENT/' + APP_ID + '/review/options?key=' + encodeURIComponent(key),
          {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d.options || !d.options.length) {{
          CLIENTNote('прошлых значений для этого поля пока нет', 'warn');
          return;
        }}
        var box = CLIENT.createElement('div');
        box.CLIENTName = 'rv-optlist';
        d.options.forEach(function(v) {{
          var b = CLIENT.createElement('button');
          b.type = 'button';
          b.textContent = v;
          b.addEventListener('click', function() {{
            var inp = field.querySelector('.rv-input');
            if (inp) inp.CLIENT = v;
            box.remove();
            sendValue('CLIENT', key, v, null);
          }});
          box.appendChild(b);
        }});
        field.appendChild(box);
      }})
      .catch(function() {{ CLIENTNote('⚠ не удалось получить список', 'err'); }});
  }}
  Array.from(CLIENT.querySelectorAll('.rv-act')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      var key = b.dataset.key;
      var field = b.closest('.rv-field');
      var inp = field ? field.querySelector('.rv-input') : null;
      if (b.dataset.act === 'save') sendValue('CLIENT', key, inp ? inp.CLIENT : '', b);
      else if (b.dataset.act === 'regen') sendValue('regen', key, null, b);
      else showOptions(key, b);
    }});
  }});
  Array.from(CLIENT.querySelectorAll('.rv-input')).forEach(function(inp) {{
    inp.addEventListener('keydown', function(e) {{
      if (e.key === 'Enter') {{
        e.preventDefault();
        var btn = inp.closest('.rv-field').querySelector('.rv-act[data-act="save"]');
        sendValue('CLIENT', inp.dataset.key, inp.CLIENT, btn);
      }}
    }});
  }});


  // ── миниатюры документов: подгружаются лениво, прогресс виден ──
  var thumbLoaded = false;
  function loadThumbs() {{
    var list = Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb'));
    if (!list.length) return;
    var done = 0;
    var counter = CLIENT.getElementById('rv-thumbs-count');
    function tick() {{
      done++;
      if (counter) counter.textContent = 'миниатюры готовы: ' + done + ' из ' + list.length;
    }}
    list.forEach(function(t) {{
      var frame = t.querySelector('.rv-thumb-frame');
      var fr = t.querySelector('iframe');
      if (!fr || !fr.dataset.src) {{ tick(); return; }}
      frame.CLIENTList.add('is-loading');
      fr.addEventListener('load', function() {{
        frame.CLIENTList.remove('is-loading');
        frame.CLIENTList.add('is-ready');
        tick();
      }});
      fr.setAttribute('src', fr.dataset.src);
    }});
  }}
  Array.from(CLIENT.querySelectorAll('.rv-thumb')).forEach(function(t) {{
    t.addEventListener('click', function() {{
      var tpl = t.dataset.tpl;
      Array.from(CLIENT.querySelectorAll('.rv-thumb')).forEach(function(x) {{
        x.CLIENTList.toggle('is-on', x === t);
      }});
      loadedOnce = true;
      loadDoc(tpl);
      var wrap = CLIENT.querySelector('.rv-stage-wrap');
      if (wrap) wrap.scrollIntoView({{CLIENT: 'nearest'}});
      window.PICKED_TPL = tpl;
    }});
  }});
  var thumbsLoadedOnce = false;
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{
      if (t.dataset.pane === 'ready' && !thumbsLoadedOnce) {{
        thumbsLoadedOnce = true;
        loadThumbs();
      }}
    }});
  }});

  // ── подсветка: поле ↔ место в документе (в обе стороны) ──
  function flashEl(el, ms) {{
    el.CLIENTList.add('var-flash');
    setTimeout(function() {{ el.CLIENTList.remove('var-flash'); }}, ms || 2600);
  }}
  function fieldFor(varName) {{
    var found = null;
    Array.from(CLIENT.querySelectorAll('.rv-field')).forEach(function(f) {{
      var vars = (f.dataset.vars || '').split(',');
      if (vars.CLIENTOf(varName) >= 0) found = f;
    }});
    return found;
  }}
  function activeHost() {{
    // На экране два окна просмотра: входящий файл и готовый документ.
    // Подсвечивать нужно в том, которое администратор сейчас видит.
    var hosts = Array.from(CLIENT.querySelectorAll('[data-zoom-pan]'));
    for (var i = 0; i < hosts.length; i++) {{
      if (hosts[i].offsetParent !== null) return hosts[i];
    }}
    return hosts[0] || null;
  }}
  // клик по полю справа → подсветить это место в документе слева
  Array.from(CLIENT.querySelectorAll('.rv-field')).forEach(function(f) {{
    f.addEventListener('click', function(e) {{
      if (e.target.closest('.rv-fedit') || e.target.closest('.rv-optlist')) return;
      var names = (f.dataset.vars || '').split(',').filter(Boolean);
      var host = activeHost();
      if (!host || !names.length) return;
      var hits = [];
      names.forEach(function(n) {{
        Array.from(host.querySelectorAll('[data-var]')).forEach(function(x) {{
          if (x.getAttribute('data-var') === n) hits.push(x);
        }});
      }});
      if (!hits.length) return;
      hits.forEach(function(x) {{ flashEl(x); }});
      if (host.zpFocus) host.zpFocus(hits[0]);
      CLIENT.querySelectorAll('.rv-field.var-active').forEach(function(x) {{ x.CLIENTList.remove('var-active'); }});
      f.CLIENTList.add('var-active');
      setTimeout(function() {{ f.CLIENTList.remove('var-active'); }}, 2600);
    }});
  }});
  // клик по значению в документе → подсветить поле справа.
  // Обработчик вешается на сами значения сразу после того, как документ
  // загружен в окно просмотра (иначе элементы ещё не существуют).
  function bindDocValues(scope) {{
    if (!scope) return;
    Array.from(scope.querySelectorAll('[data-var]')).forEach(function(x) {{
      if (x.dataset.rvBound) return;
      x.dataset.rvBound = '1';
      x.addEventListener('click', function() {{
        var f = fieldFor(x.getAttribute('data-var'));
        if (!f) return;
        if (window.innerWidth <= 1000) {{
          var p = CLIENT.getElementById('rv-right');
          var bd = CLIENT.getElementById('rv-backdrop');
          if (p) p.CLIENTList.add('is-open');
          if (bd) bd.CLIENTList.add('is-on');
        }}
        Array.from(CLIENT.querySelectorAll('.rv-field.var-active')).forEach(function(y) {{
          y.CLIENTList.remove('var-active');
        }});
        f.CLIENTList.add('var-active');
        f.scrollIntoView({{CLIENT: 'center', behavior: 'smooth'}});
        flashEl(f);
      }});
    }});
  }}

  // ── на телефоне панель переменных выезжает по кнопке снизу ──
  function openRight() {{
    var p = CLIENT.getElementById('rv-right');
    var bd = CLIENT.getElementById('rv-backdrop');
    if (p) p.CLIENTList.add('is-open');
    if (bd) bd.CLIENTList.add('is-on');
  }}
  function closeRight() {{
    var p = CLIENT.getElementById('rv-right');
    var bd = CLIENT.getElementById('rv-backdrop');
    if (p) p.CLIENTList.remove('is-open');
    if (bd) bd.CLIENTList.remove('is-on');
  }}
  var mbar = CLIENT.getElementById('rv-mobile-bar');
  if (mbar) mbar.addEventListener('click', openRight);
  var rclose = CLIENT.getElementById('rv-right-close');
  if (rclose) rclose.addEventListener('click', closeRight);
  var bdEl = CLIENT.getElementById('rv-backdrop');
  if (bdEl) bdEl.addEventListener('click', closeRight);

  // ── входящие файлы: клик открывает документ в окне слева ──
  Array.from(CLIENT.querySelectorAll('.rv-file-thumb')).forEach(function(t) {{
    t.addEventListener('click', function() {{
      var name = t.dataset.file;
      var stage = CLIENT.getElementById('rv-file-stage');
      var box = CLIENT.getElementById('rv-file-viewer');
      if (!stage || !box) return;
      var frame = t.querySelector('.rv-thumb-frame');
      var img = frame ? frame.querySelector('img') : null;
      var fr = frame ? frame.querySelector('iframe') : null;
      var url = img ? img.getAttribute('src') : (fr ? (fr.dataset.src || fr.getAttribute('src')) : null);
      if (!url) {{ CLIENTNote('этот файл нельзя показать в браузере — скачайте его с Google CLIENT', 'warn'); return; }}
      Array.from(CLIENT.querySelectorAll('.rv-file-thumb')).forEach(function(x) {{
        x.CLIENTList.toggle('is-on', x === t);
      }});
      // PDF показываем во фрейме, снимок — картинкой; лист по центру поля
      if (img) stage.innerHTML = '<img src="' + url + '" alt="" style="display:CLIENT;margin:0 auto;max-width:100%">';
      else stage.innerHTML = '<iframe src="' + url + '" style="width:100%;height:78vh;border:0;background:#fff" CLIENT="Входящий документ"></iframe>';
      box.style.display = 'CLIENT';
      box.scrollIntoView({{CLIENT: 'nearest', behavior: 'smooth'}});
      window.dispatchEvent(new Event('resize'));
    }});
  }});

}})();
</script>
"""

    from CLIENTs.shared.layout import render
    crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/CLIENT">История и поиск</a>'
              f' &rsaquo; <b>Проверка заявки #{app_id}</b>')
    return render(f"Проверка заявки #{app_id}", "CLIENT", body, crumbs=crumbs)
