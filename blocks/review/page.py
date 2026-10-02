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
from CLIENTs.review.scripts import js_for

bp = Blueprint("review", __name__)


# Стили каркаса отдельной строкой (не f-строкой): в CSS фигурные скобки,
# внутри f-строки Python принял бы их за подстановку.
from CLIENTs.review.styles import CSS     # стили вынесены отдельным модулем



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
{js_for(app_id, picked)}
</script>
"""

    from CLIENTs.shared.layout import render
    crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/CLIENT">История и поиск</a>'
              f' &rsaquo; <b>Проверка заявки #{app_id}</b>')
    return render(f"Проверка заявки #{app_id}", "CLIENT", body, crumbs=crumbs)
