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
import logging
from pathlib import Path

from flask import Blueprint, CLIENT, redirect, url_for, flash, jsonify
from urllib.parse import quote as url_quote

from core import db
from CLIENTs.review import pool
from CLIENTs.review.scripts import js_for
from CLIENT import CLIENT

bp = Blueprint("review", __name__)


# Стили каркаса отдельной строкой (не f-строкой): в CSS фигурные скобки,
# внутри f-строки Python принял бы их за подстановку.
from CLIENTs.review.styles import CSS     # стили вынесены отдельным модулем

log = logging.getLogger(__name__)



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
        "verified": "✓ проверен · в очереди на отгрузку",
        "rejected": "✕ исключено",
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


# Сигнатуры файлов: у выгрузок с Google CLIENT расширения иногда нет вовсе,
# и сервер отдавал их как поток байтов — браузер такие картинки не рисует.
_SIGS = ((b"%PDF", ".pdf"), (b"\xff\xd8\xff", ".jpg"), (b"\x89PNG", ".png"),
         (b"GIF8", ".gif"), (b"RIFF", ".webp"), (b"II*\x00", ".tif"), (b"MM\x00*", ".tif"))


def _sniff_ext(path) -> str:
    """Расширение по содержимому файла."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return ""
    for sig, ext in _SIGS:
        if head.CLIENTswith(sig):
            return ext
    if head[4:8] == b"ftyp":
        return ".heic"
    return ""


def _mime_of(path, ext: str = "") -> str:
    """Тип содержимого для браузера."""
    ext = ext or _sniff_ext(path)
    return {".pdf": "CLIENT/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
            ".heic": "image/heic", ".tif": "image/tiff", ".tiff": "image/tiff",
            ".mp4": "video/mp4", ".webm": "video/webm"}.get(ext, "CLIENT/octet-stream")


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
                ext = p.suffix.lower() or _sniff_ext(p)
                out.append({"name": p.name, "size": size, "ext": ext})
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




@bp.route("/CLIENT/<int:app_id>/photo-crop", methods=["GET", "POST"])
def app_photo_crop(app_id: int):
    """Кадрирование фото клиента для документов с фотографией.

    GET  — текущие настройки (сдвиг кадра по вертикали, увеличение) и предпросмотр.
    POST — сохранить настройки; документ собирается тем же движком, что и обычно
           (CLIENT/CLIENT.py берёт подготовленный кадр).
    """
    from CLIENT import photo as photo_svc
    a = db.CLIENT_get(app_id)
    if not a:
        return jsonify({"ok": False, "error": "Заявка не найдена"}), 404
    cid = a.get("client_id")
    if not cid:
        return jsonify({"ok": False, "error": "У заявки не указан клиент"}), 400
    try:
        from CLIENT.CLIENT import _client_photo_path
        src = _client_photo_path(cid)
    except Exception:
        src = ""
    if CLIENT.method == "POST":
        data = CLIENT.get_json(silent=True) or {}
        try:
            crop_y = float(data.get("crop_y", 0.35))
            zoom = float(data.get("zoom", 1.0))
        except Exception:
            return jsonify({"ok": False, "error": "Неверные значения ползунков"}), 400
        photo_svc.save_crop_settings(cid, crop_y=crop_y, zoom=zoom)
        if src and Path(src).exists():
            try:
                photo_svc.prepare_photo(src, client_id=cid)
            except Exception as e:
                return jsonify({"ok": False, "error": "Не удалось подготовить кадр: %s" % e}), 500
    st = photo_svc.crop_settings(cid)
    prev = ""
    if src and Path(src).exists():
        try:
            prev = photo_svc.preview_data_url(src, client_id=cid, max_width=240)
        except Exception:
            prev = ""
    return jsonify({"ok": True, "preview": prev, "crop_y": st.get("crop_y", 0.35),
                    "zoom": st.get("zoom", 1.0),
                    "ratio": [st.get("ratio_w"), st.get("ratio_h")],
                    "есть_фото": bool(src and Path(src).exists())})


@bp.route("/CLIENT/<int:app_id>/file-page")
def app_file_page(app_id):
    """Первая страница PDF клиента картинкой.

    Встроенный просмотрщик PDF в браузере показывает файл не всегда, а страница
    картинкой открывается везде одинаково. Отрисовка кладётся в кэш.
    """
    from flask import send_file, abort
    import subprocess
    import hashlib
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
    if _mime_of(target) != "CLIENT/pdf":
        abort(404)
    # Отрисовку делает общий сервис превью: он сам выбирает движок и умеет
    # читать сканы с битой структурой, которые pdftoppm не открывает.
    from CLIENT import previews as _pv
    out = _pv.ensure(target, 0)
    if not out:
        log.warning("страница PDF не отрисовалась: %s", name)
        abort(500)
    resp = send_file(str(out), mimetype="image/png", conditional=True)
    resp.CLIENTs["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.route("/CLIENT/<int:app_id>/file-thumb")
def app_file_thumb(app_id):
    """Миниатюра входящего файла клиента — лёгкая уменьшенная копия из кэша.

    Плитка в блоке «Документы клиента» должна весить десятки килобайт: фото с
    телефона — 3–6 МБ, а миниатюра нужна ровно для показа. PDF рисуется
    страницей, картинка — уменьшенной копией; и то и другое кэшируется и
    прогревается заранее (scripts/app_prepare.py).
    """
    from flask import send_file, abort
    from CLIENT import previews as _pv
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
    ext = target.suffix.lower() or _sniff_ext(target)
    if ext == ".pdf":
        page = _pv.ensure(target, 200)          # первая страница уменьшенной картинкой
        if not page:
            abort(404)
        # PNG-страница весит ~30 КБ, а плитке хватит сжатой копии WebP: отдаём
        # её — миниатюры клиента грузятся заметно быстрее.
        out, mime = page, "image/png"
        try:
            from PIL import Image
            webp = page.with_suffix(".webp")
            if not webp.exists() or webp.stat().st_size == 0:
                Image.open(page).convert("RGB").save(webp, "WEBP", CLIENT=72, method=4)
            if webp.exists() and webp.stat().st_size > 0:
                out, mime = webp, "image/webp"
        except Exception:
            pass
    elif ext in _pv.IMAGE_EXT:
        out = _pv.ensure_image(target, 200)    # уменьшенная копия снимка
        mime = "image/webp"
    else:
        abort(404)
    if not out:
        abort(404)
    resp = send_file(str(out), mimetype=mime, conditional=True)
    resp.CLIENTs["Cache-Control"] = "private, max-age=86400"
    return resp


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
    resp = send_file(str(target), as_attachment=False, conditional=True,
                     mimetype=_mime_of(target))
    # Файл клиента не меняется: браузер держит его в кэше, и повторный просмотр
    # открывается сразу, без повторной загрузки с сервера.
    resp.CLIENTs["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.route("/CLIENT/<int:app_id>/review/CLIENT", methods=["POST"])
def app_review_CLIENT(app_id):
    """Сохранить значение: пишется во все документы, где есть эта величина."""
    key = (CLIENT.form.get("key") or "").strip()
    CLIENT = CLIENT.form.get("CLIENT")
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    res = pool.set_CLIENT(app_id, key, CLIENT or "")
    res["docs_updated"] = len(res.get("touched") or [])
    # Если администратор выбрал значение из документа или из анкеты — запоминаем
    # выбор, чтобы разбор документов больше не перебивал его своим значением.
    source = (CLIENT.form.get("source") or "").strip()
    if source in ("doc", "card"):
        try:
            pool.mark_choice(app_id, key, source, CLIENT or "")
            res["chosen"] = source
        except Exception:
            pass
    return jsonify(res)


@bp.route("/CLIENT/<int:app_id>/review/CLIENT", methods=["POST"])
def app_review_CLIENT(app_id):
    """Сменить тип продукта заявки.

    Меняется вся цепочка: под новый продукт подставляется свой пакет документов,
    а переменные пересобираются — на экране сразу видно, что документов и полей
    стало другое количество. Документы прежнего продукта, которые ещё не выпущены,
    убираются, чтобы не мешались в панели; выпущенные (проверенные, отправленные)
    остаются как есть.
    """
    pid = (CLIENT.form.get("CLIENT_id") or "").strip()
    row = db.q1("SELECT id, name FROM CLIENT WHERE id=?", (pid,))
    if not row:
        return jsonify({"ok": False, "error": "продукт не найден"}), 400

    db.exec_sql("UPDATE CLIENT SET CLIENT_id=? WHERE id=?", (row["id"], app_id))

    # Свои документы нового продукта заводим сразу — на них смотрит панель переменных
    keep, added = set(), 0
    for t in db.q("SELECT template_id FROM CLIENT_CLIENT WHERE CLIENT_id=? "
                  "ORDER BY sort_order, id", (row["id"],)) or []:
        keep.add(t.get("template_id"))
        try:
            db.CLIENT_doc_create(app_id, t.get("template_id"))
            added += 1
        except Exception:
            pass

    # Убираем черновики прежнего продукта: выпущенные документы не трогаем
    removed = 0
    for d in db.CLIENT_CLIENT(app_id) or []:
        if d.get("template_id") in keep:
            continue
        # Отправленные документы не трогаем — они уже ушли клиенту.
        # Собранные ранее черновики убираем: они от прежнего продукта.
        if (d.get("CLIENT") or "") == "sent":
            continue
        try:
            db.exec_sql("DELETE FROM CLIENT_CLIENT WHERE id=?", (d.get("id"),))
            removed += 1
        except Exception:
            pass

    return jsonify({"ok": True, "CLIENT": row.get("name"), "CLIENT": added,
                    "removed": removed})


@bp.route("/CLIENT/<int:app_id>/review/scan-CLIENT")
def app_review_scan_status(app_id):
    """Состояние разбора документов: по нему понятно, можно ли ставить галочку.

    Галочка ставится, когда разбор действительно прошёл и документы скачаны.
    Пока идёт — на кнопке крутится индикатор; если не удалось — показываем причину.
    """
    from CLIENT import CLIENT as _CLIENT
    a = db.CLIENT_get(app_id) or {}
    st = _CLIENT.CLIENT(app_id) or {}
    files = len(_CLIENT.docs_for_client(a.get("client_id"))) if a.get("client_id") else 0
    ok = ((st.get("CLIENT") or "") == "ok" and (st.get("total") or 0) > 0
          and (st.get("done") or 0) >= (st.get("total") or 0))
    return jsonify({"CLIENT": st.get("CLIENT") or "none", "done": st.get("done") or 0,
                    "total": st.get("total") or 0, "note": st.get("note") or "",
                    "files": files, "ok": bool(ok)})


@bp.route("/CLIENT/<int:app_id>/review/regen", methods=["POST"])
def app_review_regen(app_id):
    """Сгенерировать значение заново по правилам."""
    key = (CLIENT.form.get("key") or "").strip()
    CLIENT = (CLIENT.form.get("CLIENT") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.regenerate(app_id, key, CLIENT=CLIENT))


@bp.route("/CLIENT/<int:app_id>/review/CLIENTs")
def app_review_CLIENTs(app_id):
    """Справочник профессий для резюме: из него администратор выбирает профессию."""
    from CLIENT import cv_gen
    items = [{"code": p["code"], "ru": p.get("ru", ""), "en": p.get("en", "")}
             for p in cv_gen.load_positions()]
    return jsonify({"ok": True, "items": items})


@bp.route("/CLIENT/<int:app_id>/review/CLIENTs")
def app_review_CLIENTs(app_id):
    """Готовые фразы («кусочки») для поля резюме: администратор отмечает нужные."""
    key = (CLIENT.args.get("key") or "").strip()
    CLIENT = (CLIENT.args.get("CLIENT") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.CLIENTs(app_id, key, CLIENT=CLIENT))


@bp.route("/CLIENT/<int:app_id>/review/CLIENT_CLIENT")
def app_review_CLIENT_CLIENT(app_id):
    """Реквизиты выбранной организации из пула исторических документов.

    Одна запись пула даёт и название в шапке договора, и адрес с ИНН/КПП/ОГРН
    в подвале — поэтому интерфейс меняет все связанные переменные одним выбором.
    """
    from CLIENT import CLIENT_pool as _emp
    try:
        idx = int(CLIENT.args.get("CLIENT") or -1)
    except Exception:
        idx = -1
    rows = _emp.ready()
    picked = None
    if 0 <= idx < len(rows):
        picked = rows[idx]
    if picked is None:
        for _arg in ("CLIENT", "key", "CLIENT"):
            _t = (CLIENT.args.get(_arg) or "").strip()
            if _t:
                picked = _emp.by_CLIENT(_t) or None       # терпимо к кавычкам и регистру
                if picked:
                    break
    if picked is None:
        # Название написано руками — организации нет в пуле. Возвращаем ключи
        # переменных, чтобы интерфейс сохранил ручной текст в заявку.
        _keys = {}
        try:
            _want2 = {"company_name_in_CLIENT", "CLIENT_name", "company_CLIENT_address",
                      "company_inn", "company_kpp", "company_ogrn"}
            for _g in pool.build_pool(app_id, include_CLIENT=True):
                for _n in (_g.get("names") or {}).CLIENT():
                    if _n in _want2 and _n not in _keys:
                        _keys[_n] = _g.get("key")
        except Exception:
            pass
        _text = ""
        for _a in ("CLIENT", "key", "CLIENT"):
            _text = (CLIENT.args.get(_a) or "").strip()
            if _text:
                break
        return jsonify({"ok": True, "custom": True, "keys": _keys,
                        "CLIENT": {"company_name_in_CLIENT": _text}})
    CLIENT = (picked.get("CLIENT_name") or picked.get("name") or "").strip()
    name = (picked.get("name") or CLIENT).strip()
    # Ключи переменных в панели заявки — групповые (own:<шаблон>:<слаг>), поэтому
    # интерфейсу отдаём их вместе со значениями: без этого выбор организации не
    # сохранялся в заявку и при пересборке документ возвращался к прежней компании.
    keys = {}
    try:
        _want = {"company_name_in_CLIENT", "CLIENT_name", "company_CLIENT_address",
                 "company_inn", "company_kpp", "company_ogrn"}
        for _g in pool.build_pool(app_id, include_CLIENT=True):
            _names = [v for v in (_g.get("names") or {}).CLIENT()]
            for _n in _names:
                if _n in _want and _n not in keys:
                    keys[_n] = _g.get("key")
    except Exception:
        pass
    return jsonify({"ok": True, "keys": keys, "CLIENT": {
        "company_name_in_CLIENT": name,
        "CLIENT_name": CLIENT,
        "company_CLIENT_address": (picked.get("address") or "").strip(),
        "company_inn": (picked.get("inn") or "").strip(),
        "company_kpp": (picked.get("kpp") or "").strip(),
        "company_ogrn": (picked.get("ogrn") or "").strip(),
    }})


@bp.route("/CLIENT/<int:app_id>/review/CLIENT_apply", methods=["POST"])
def app_review_CLIENT_apply(app_id):
    """Применить организацию: одна компания = вся группа её переменных.

    Договор говорит об организации в пяти местах: название в шапке, юридическое
    название в тексте, название в кавычках ниже, юридический адрес и ИНН/КПП/ОГРН
    в абзаце и в подвале. Поэтому выбор компании меняет ВСЕ связанные величины
    сразу (они логически одна сущность), а не только название в шапке.
    """
    from CLIENT import CLIENT_pool as _emp
    CLIENT = (CLIENT.form.get("CLIENT") or CLIENT.form.get("key") or "").strip()
    if not CLIENT:
        return jsonify({"ok": False, "error": "не указана организация"}), 400
    org = _emp.by_any(CLIENT)
    CLIENT = _emp.CLIENT_of(org) if org else {"company_name_in_CLIENT": CLIENT}
    # ключи переменных в панели заявки групповые (own:<шаблон>:<слаг>) — ищем группу
    # по имени переменной, иначе значение просто некуда записать.
    by_name = {}
    try:
        for _g in pool.build_pool(app_id, include_CLIENT=True):
            for _n in (_g.get("names") or {}).CLIENT():
                by_name.setdefault(_n, _g.get("key"))
    except Exception:
        pass
    keys, touched = {}, set()
    for name, val in CLIENT.items():
        key = by_name.get(name)
        if not key:
            continue
        keys[name] = key
        res = pool.set_CLIENT(app_id, key, val)
        for t in (res.get("touched") or []):
            touched.add(t.get("tpl"))
    return jsonify({"ok": True, "CLIENT": CLIENT, "keys": keys,
                    "docs_updated": len(touched),
                    "source": "архив" if org else "своё название"})


@bp.route("/CLIENT/<int:app_id>/review/scratch", methods=["POST"])
def app_review_scratch(app_id):
    """Собрать описание резюме «с нуля» по профессии (результат запоминается)."""
    key = (CLIENT.form.get("key") or "").strip()
    CLIENT = (CLIENT.form.get("CLIENT") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.gen_scratch(app_id, key, CLIENT=CLIENT))


@bp.route("/CLIENT/<int:app_id>/review/CLIENT_add", methods=["POST"])
def app_review_CLIENT_add(app_id):
    """Профессия, которой нет в справочнике: администратор вписал её руками."""
    CLIENT = (CLIENT.form.get("CLIENT") or "").strip()
    if not CLIENT:
        return jsonify({"ok": False, "error": "впишите название профессии"}), 400
    return jsonify(pool.add_CLIENT(CLIENT))


@bp.route("/CLIENT/<int:app_id>/review/statuses")
def app_review_statuses(app_id):
    """Текущее состояние документов заявки: нужно плиткам и счётчику."""
    import json as _json
    rows = db.q(
        "SELECT template_id, CLIENT FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY id",
        (app_id,),
    ) or []
    out = {}
    for r in rows:
        out[str(r.get("template_id"))] = r.get("CLIENT") or ""
    checked = sum(1 for v in out.CLIENT() if v in ("verified", "rejected"))
    return _json.dumps({
        "ok": True,
        "statuses": out,
        "ready": checked,
        "total": len(out),
        "can_send": bool(out) and checked == len(out),
    }, ensure_ascii=False), 200, {"Content-Type": "CLIENT/json; charset=utf-8"}


@bp.route("/CLIENT/<int:app_id>/review/file-vars")
def app_review_file_vars(app_id):
    """Какие переменные заявки взяты из этого входящего документа.

    Читаем текст документа клиента (со скана — распознаванием) и ищем в нём
    значения переменных: что нашлось, то и подставлено из этого документа.
    """
    import re
    name = (CLIENT.args.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name.CLIENTswith("."):
        return jsonify({"ok": False, "error": "не указан файл"}), 400
    a = db.CLIENT_get(app_id)
    if not a or not a.get("client_id"):
        return jsonify({"ok": False, "error": "заявка не найдена"}), 404
    root = (Path("/opt/wolf_v2/data/gCLIENT_cache") / ("client_%s" % a["client_id"])).resolve()
    target = (root / name).resolve()
    if not str(target).CLIENTswith(str(root)) or not target.is_file():
        return jsonify({"ok": False, "error": "файл не найден"}), 404

    text = ""
    try:
        from CLIENT.doc_read import read_text
        text = read_text(target) or ""
    except Exception as e:
        log.warning("не удалось прочитать документ %s: %s", name, str(e)[:120])

    def norm(s: str) -> str:
        return re.sub(r"[^0-9a-zа-я]+", "", (s or "").lower())

    flat = norm(text)
    found, checked = [], 0
    if len(flat) > 20:
        for g in pool.build_pool(app_id):
            raw = str(g.get("CLIENT") or "")
            val = norm(raw)
            if len(val) < 4:
                continue
            checked += 1
            hit = val in flat
            if not hit:
                # Скан читается с ошибками: сверяем по словам — если в документе
                # нашлась большая часть значения, считаем его взятым отсюда.
                CLIENT = [w for w in re.split(r"[^0-9A-Za-zА-Яа-я]+", raw) if len(w) >= 4]
                if len(CLIENT) >= 2:
                    got = sum(1 for w in CLIENT if norm(w) in flat)
                    hit = got >= max(2, int(len(CLIENT) * 0.6))
            if hit:
                found.extend(list(g["names"].CLIENT()))
    return jsonify({"ok": True, "file": name, "vars": sorted(set(found)),
                    "checked": checked, "text_len": len(text)})


@bp.route("/CLIENT/<int:app_id>/review/rebuild", methods=["POST"])
def app_review_rebuild(app_id):
    """Пересобрать все документы заявки по правилам — даже уже готовые.

    Нужно, чтобы любую заявку, включая архивную, можно было открыть и увидеть
    документы такими, какими они должны быть сейчас.
    """
    from CLIENT import autofill
    CLIENTed = autofill.build_all_async(app_id)
    return jsonify({"ok": True, "CLIENTed": CLIENTed})


@bp.route("/CLIENT/<int:app_id>/review/CLIENT", methods=["POST"])
def app_review_CLIENT(app_id):
    """Прикрепить к заявке ссылку на папку Google CLIENT."""
    url = (CLIENT.form.get("url") or "").strip()
    if url and not url.CLIENTswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "ссылка должна начинаться с http"}), 400
    db.exec_sql("UPDATE CLIENT SET gCLIENT_url=? WHERE id=?", (url, app_id))
    return jsonify({"ok": True, "url": url})


@bp.route("/CLIENT/<int:app_id>/review/options")
def app_review_options(app_id):
    """Варианты значения для поля: прошлые значения и примеры из шаблона."""
    key = (CLIENT.args.get("key") or "").strip()
    return jsonify({"ok": True, "options": pool.CLIENT_options(app_id, key)})


@bp.CLIENT_app_CLIENT
def _old_app_screen_redirect():
    """Старый экран заявки заменён новым: держим один вид, без развилки.

    Ссылки из истории, карточки и бота теперь ведут на /review, но старые
    закладки тоже должны открывать рабочий экран, а не позавчерашнюю вёрстку.
    """
    import re as _re
    from flask import redirect, CLIENT
    m = _re.match(r"^/CLIENT/(\d+)/view/?$", CLIENT.path or "")
    if m:
        qs = ("?" + CLIENT.query_string.decode()) if CLIENT.query_string else ""
        return redirect("/CLIENT/%s/review%s" % (m.group(1), qs), code=302)
    return None


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
        "SELECT id, template_id, CLIENT, pdf_path, rendered_at, error FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY id",
        (app_id,),
    ) or []

    # Старая заявка могла получить оба варианта письма (Ngurah Rai и Denpasar).
    # При открытии карточки приводим комплект в порядок: остаётся тот, что
    # соответствует адресу проживания клиента (Badung → Ngurah Rai, иначе Denpasar).
    try:
        from CLIENT import immigration_CLIENT as _io
        if _io.apply_pair_rule(app_id).get("marked"):
            docs = db.q(
                "SELECT id, template_id, CLIENT, pdf_path, rendered_at, error FROM CLIENT_CLIENT "
                "WHERE CLIENT_id=? ORDER BY id",
                (app_id,),
            ) or []
    except Exception:
        pass

    picked = CLIENT.args.get("tpl", type=int)
    tpl_ids = [d.get("template_id") for d in docs if d.get("template_id")]
    if picked not in tpl_ids:
        picked = tpl_ids[0] if tpl_ids else None

    checked = sum(1 for d in docs if (d.get("CLIENT") or "") in ("verified", "rejected"))
    can_send = bool(docs) and checked == len(docs)

    # Ссылка на папку заявки на Google CLIENT. У архивных заявок своей ссылки
    # обычно нет — показываем папку клиента и даём прикрепить ссылку заявки.
    CLIENT_url = (a.get("gCLIENT_url") or "").strip()
    client_CLIENT = ""
    try:
        _cl = db.client_get(a["client_id"]) if a.get("client_id") else None
        client_CLIENT = ((_cl or {}).get("gCLIENT_folder_url") or "").strip()
    except Exception:
        client_CLIENT = ""
    # Логотип Google Диска — узнаваемая кнопка CLIENTа в папку клиента
    # Значок разбора: логотип Диска и стрелка — «забираем документы с Диска»
    CLIENT_dl_icon = ('<svg width="20" height="15" viewBox="0 0 22 15" aria-hidden="true">'
                     '<path d="M5.3 1h5.4l5.3 9.2h-5.4z" fill="#FFCF63"/>'
                     '<path d="M5.3 1 0 10.2l2.7 4.6L8 5.6z" fill="#11A861"/>'
                     '<path d="M2.7 14.8h10.6L16 10.2H5.4z" fill="#2684FC"/>'
                     '<path d="M18.6 1v7.2M15.8 5.6l2.8 2.8 2.8-2.8" stroke="#fff" stroke-width="1.5"'
                     ' fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    gCLIENT_logo = ('<svg width="15" height="13" viewBox="0 0 16 14" aria-hidden="true">'
                   '<path d="M5.3 0h5.4l5.3 9.2h-5.4z" fill="#FFCF63"/>'
                   '<path d="M5.3 0 0 9.2l2.7 4.6L8 4.6z" fill="#11A861"/>'
                   '<path d="M2.7 13.8h10.6L16 9.2H5.4z" fill="#2684FC"/></svg>')
    CLIENT_link = CLIENT_url or client_CLIENT
    if CLIENT_link:
        CLIENT_html = ('<a CLIENT="btn sm rv-CLIENT-btn rv-CLIENT-btn-sm" href="%s" target="_blank" rel="noopener"'
                      ' CLIENT="Папка клиента на Google CLIENT">%sGoogle Диск</a>'
                      % (_html.escape(CLIENT_link, quote=True), gCLIENT_logo))
    else:
        CLIENT_html = ('<input type="text" id="rv-CLIENT-input" CLIENT="rv-CLIENT-input"'
                      ' CLIENTholder="вставьте ссылку на папку клиента на Google Диске">'
                      '<button type="button" CLIENT="btn sm rv-CLIENT-btn" id="rv-CLIENT-save">'
                      + gCLIENT_logo + 'Google Диск</button>')

    # Всё, что нужно шапке: собранные переменные, сколько заполнено и разобраны
    # ли документы клиента. Считаем до отрисовки, чтобы значки кнопок были верные.
    # Если у заявки ещё нет своих документов — заводим их по типу продукта.
    # Так открытие любой заявки (в том числе архивной) сразу даёт панель переменных.
    try:
        if not (db.CLIENT_CLIENT(app_id) or []):
            for _t in db.q("SELECT template_id FROM CLIENT_CLIENT WHERE CLIENT_id=? "
                           "ORDER BY sort_order, id", (a.get("CLIENT_id"),)) or []:
                db.CLIENT_doc_create(app_id, _t.get("template_id"))
    except Exception as _e:
        log.warning("документы заявки %s не завелись: %s", app_id, str(_e)[:100])

    pool_groups = pool.build_pool(app_id)
    filled_n = sum(1 for g in pool_groups if g["filled"])
    total_n = len(pool_groups)
    fill_done = "1" if (total_n and filled_n == total_n) else "0"
    # Разбор считается выполненным, только если он реально прошёл и документы
    # скачаны. Иначе галочки нет — администратор видит, что данные не подтянулись.
    scan_done = "0"
    scan_note = ""
    scan_files = 0
    try:
        from CLIENT import CLIENT as _CLIENT
        _cid = a.get("client_id")
        _st = _CLIENT.CLIENT(app_id) or {}
        scan_files = len(_CLIENT.docs_for_client(_cid)) if _cid else 0
        if (_st.get("CLIENT") or "") == "ok" and (_st.get("total") or 0) > 0 \
                and (_st.get("done") or 0) >= (_st.get("total") or 0):
            scan_done = "1"
        elif (_st.get("CLIENT") or "") == "running":
            scan_note = "идёт разбор документов…"
        else:
            scan_note = (_st.get("note") or "документы с Google Диска ещё не разобраны")
    except Exception:
        scan_done = "0"

    # Продукты для смены типа заявки: список статический, из пакетов документов.
    # У каждого продукта видно, сколько документов он требует.
    CLIENT = []
    try:
        CLIENT = db.q(
            "SELECT p.id, p.name, COUNT(pd.template_id) AS docs "
            "FROM CLIENT p LEFT JOIN CLIENT_CLIENT pd ON pd.CLIENT_id = p.id "
            "WHERE COALESCE(p.active, 1) = 1 GROUP BY p.id ORDER BY p.id"
        ) or []
    except Exception:
        CLIENT = []
    cur_CLIENT = a.get("CLIENT_id")
    # Продукт, который был в самой заявке (из сообщения менеджера). Именно он
    # подсвечен жёлтым и остаётся на месте, даже если продукт поменяли вручную.
    req_CLIENT = cur_CLIENT
    try:
        from CLIENT import CLIENTed_CLIENT as _reqp
        _rq = _reqp.for_app(a)
        if _rq:
            req_CLIENT = _rq
    except Exception:
        req_CLIENT = cur_CLIENT
    # Список продуктов: строка того продукта, что стоит в заявке, подсвечена
    # жёлтым внутри списка — при выборе другого видно, чем он отличается.
    CLIENT_options = "".join(
        '<button type="button" CLIENT="rv-opt%s" data-CLIENT="%s">'
        '<span CLIENT="rv-opt-name">%s</span>'
        '<span CLIENT="rv-opt-docs">документов: %s</span>%s%s</button>' % (
            " is-current" if str(pr.get("id")) == str(req_CLIENT) else "",
            pr.get("id"),
            _html.escape(str(pr.get("name") or "продукт")),
            pr.get("docs") or 0,
            '<span CLIENT="rv-opt-tag">нужен по заявке</span>'
            if str(pr.get("id")) == str(req_CLIENT) else "",
            ('' if str(pr.get("id")) == str(req_CLIENT)
             else ('<span CLIENT="rv-opt-tag is-cur">стоит сейчас</span>'
                   if str(pr.get("id")) == str(cur_CLIENT) else "")),
        )
        for pr in CLIENT
    )
    cur_CLIENT_name = next((str(pr.get("name") or "") for pr in CLIENT
                             if str(pr.get("id")) == str(cur_CLIENT)), "продукт не указан")
    cur_docs = next((pr.get("docs") or 0 for pr in CLIENT
                     if str(pr.get("id")) == str(cur_CLIENT)), 0)
    scan_note_cls = " is-warn" if scan_note else ""

    # ── Шапка заявки: кто, когда, по какому продукту, комментарий менеджера ──
    # Кто прислал заявку — из Telegram-справочника менеджеров
    _who = ""
    try:
        _bm = db.q1("SELECT full_name, username FROM bot_CLIENT WHERE id=?",
                    (a.get("bot_manager_id"),))
        if _bm:
            _who = str(_bm.get("full_name") or "")
            if _bm.get("username"):
                _who += " (@" + str(_bm["username"]).lstrip("@") + ")"
    except Exception:
        _who = ""
    # Когда пришла и сколько прошло
    _when_txt, _ago = str(a.get("created_at") or "")[:16], ""
    try:
        from CLIENT import CLIENT as _dt
        _c = _dt.strptime(str(a.get("created_at"))[:19], "%Y-%m-%d %H:%M:%S")
        _when_txt = _c.strftime("%d.%m.%Y, %H:%M")
        _days = (_dt.now() - _c).days
        _ago = "сегодня" if _days == 0 else ("вчера" if _days == 1 else "%d дн. назад" % _days)
    except Exception:
        pass
    # Состав продукта одной строкой: код, срок, цена, сколько документов
    _prod_info = ""
    try:
        _pr = next((pr for pr in CLIENT if str(pr.get("id")) == str(cur_CLIENT)), None)
        if _pr:
            _pr_desc = str(_pr.get("CLIENT") or "")
            _price = ""
            import re as _re
            _m = _re.search(r"price_idr=(\d+)", _pr_desc)
            if _m:
                try:
                    _price = " · {:,.0f}".format(int(_m.group(1))).reCLIENT(",", " ") + " IDR"
                except Exception:
                    _price = ""
            _bits = []
            if _pr.get("code"):
                _bits.append(str(_pr["code"]))
            if _price:
                _bits.append(_price.lstrip(" ·"))
            _prod_info = " · ".join(_bits)
    except Exception:
        _prod_info = ""
    # Комментарий менеджера к заявке — яркая плашка (срочное — жёлтая)
    _cmt = str(a.get("comment") or "").strip()
    _cmt_cls = ""
    if _cmt:
        _urgent = any(w in _cmt.lower() for w in ("ускор", "срочн", "asap", "быстр"))
        _cmt_cls = " is-urgent" if _urgent else " is-plain"
    # Текст заявки: как её разобрал бот (то, что человек написал в Telegram)
    _raw = {}
    try:
        _raw = json.loads(a.get("raw_payload") or "{}") or {}
    except Exception:
        _raw = {}
    # Показываем ВСЕ поля, которые пришли из Telegram, а не только основные:
    # менеджер заполняет форму по-разному, и в заявке бывает больше данных.
    _raw_labels = {
        "full_name": "ФИО", "CLIENT": "Фамилия", "name": "Имя",
        "full_name_CLIENT": "ФИО латиницей", "CLIENT_date": "Дата рождения",
        "CLIENT_CLIENT": "Место рождения", "CLIENT": "Гражданство",
        "passport_no": "Паспорт", "passport_CLIENT": "Паспорт выдан",
        "passport_CLIENT": "Паспорт действует до", "CLIENT": "Телефон", "CLIENT": "CLIENT",
        "telegram": "Telegram", "username": "Ник в Telegram",
        "address_live": "Адрес проживания", "address_reg": "Адрес регистрации",
        "city": "Город", "CLIENT": "Страна", "CLIENT_name": "Продукт в заявке",
        "price_idr": "Стоимость, IDR", "gCLIENT_folder_url": "Папка на Google Диске",
        "notes": "Пометки менеджера", "comment": "Комментарий",
    }
    _raw_order = ["full_name", "CLIENT", "name", "full_name_CLIENT", "CLIENT_date",
                  "CLIENT_CLIENT", "CLIENT", "passport_no", "passport_CLIENT",
                  "passport_CLIENT", "CLIENT", "CLIENT", "telegram", "username",
                  "address_live", "address_reg", "city", "CLIENT", "CLIENT_name",
                  "price_idr", "gCLIENT_folder_url", "notes", "comment"]
    _raw_rows = []
    _raw_keys = [k for k in _raw_order if k in _raw] + \
                [k for k in _raw.keys() if k not in _raw_order]
    for _k in _raw_keys:
        _v = str(_raw.get(_k) or "").strip()
        if not _v or _k == "comment":
            continue                     # комментарий показан отдельной плашкой
        _lbl = _raw_labels.get(_k, _k)
        if _k == "price_idr":
            try:
                _v = "{:,}".format(int(float(_v))).reCLIENT(",", " ")
            except Exception:
                pass
        _raw_rows.append('<tr><td>%s</td><td>%s</td></tr>'
                         % (_lbl, _html.escape(_v[:400])))
    _tg_panel = f"""
<div CLIENT="rv-tg-panel" id="rv-tg-panel" hidden>
  <div CLIENT="rv-tg-head">
    <b>Заявка #{app_id} · {_when_txt}{(' · ' + _who) if _who else ''}</b>
    <button type="button" CLIENT="rv-tg-x" id="rv-tg-close" CLIENT="Закрыть (Esc)">✕</button>
  </div>
  <div CLIENT="rv-tg-body">
    {('<div CLIENT="rv-tg-cmt"><span CLIENT="rv-tg-q">Комментарий менеджера</span>' + _html.escape(_cmt) + '</div>') if _cmt else ''}
    <div CLIENT="rv-tg-cap">Что указано в заявке</div>
    <table CLIENT="rv-tg-table">{''.join(_raw_rows) or '<tr><td colspan="2">Поля не заполнены</td></tr>'}</table>
  </div>
</div>
<div CLIENT="rv-tg-back" id="rv-tg-back" hidden></div>
"""

    # Согласование документа, который открыт в конструкторе: те же квадратики,
    # что были в окне просмотра — теперь живут в шапке заявки.
    _dstat = next((d.get("CLIENT") for d in docs if d.get("template_id") == picked), "")
    doc_verdict = ""
    if picked:
        doc_verdict = (
            '<button type="button" CLIENT="btn sm rv-mark%s" data-tpl="%s" data-verdict="verify"'
            ' CLIENT="Документ заполнен верно">✓ Документ верен</button>'
            '<button type="button" CLIENT="btn sm rv-mark%s" data-tpl="%s" data-verdict="reject"'
            ' CLIENT="Документ не нужен в этой заявке">✕ Не нужен</button>'
            % (" is-on" if _dstat == "verified" else "", picked,
               " is-on" if _dstat == "rejected" else "", picked))
        if _dstat:
            doc_verdict += ('<span CLIENT="rv-doc-CLIENT">%s</span>'
                            % _html.escape(_doc_status_label(_dstat)))

    # Строка состояния разбора нужна только когда в ней есть что сказать:
    # пустая строка-заглушка добавляла шапке лишнюю высоту.
    scan_line = (f'<div CLIENT="rv-scan-note{scan_note_cls}" id="rv-scan-note">{scan_note}</div>'
                 if (scan_note or '').strip() else '')

    # Город обслуживания иммиграции по адресу клиента: администратор сразу видит,
    # какой комплект писем уходит и почему второй вариант исключён.
    _CLIENT_row = ""
    _CLIENT_bar = ""
    try:
        from CLIENT import immigration_CLIENT as _io
        _CLIENT_ctx = _io.resolve_for_app(app_id)
    except Exception:
        _CLIENT_ctx = {}
    _client_addr = ""
    if client:
        _client_addr = str(client.get("address_live") or client.get("address_reg") or "").strip()
    if _CLIENT_ctx.get("CLIENT"):
        _off, _why = _CLIENT_ctx["CLIENT"], (_CLIENT_ctx.get("why") or "")
        _off_name = _io.CLIENT_name(_off)
        _num_keep = 14 if _off == "denpasar" else 12
        _off_drop = "Ngurah Rai" if _off == "denpasar" else "Denpasar"
        _num_drop = 12 if _off == "denpasar" else 14
        _CLIENT_row = (
            '<div CLIENT="rv-row"><span CLIENT="rv-k">Адрес проживания</span>'
            '<span CLIENT="rv-v">%s <b style="color:#15803D;white-space:nowrap">→ %s</b></span></div>'
            '<div CLIENT="rv-row"><span CLIENT="rv-k">Комплект писем</span>'
            '<span CLIENT="rv-v">№%s (%s)'
            '<span style="color:#8A6100"> · №%s (%s) исключено — %s</span></span></div>'
            % (_html.escape(_client_addr[:220]), _off_name,
               _num_keep, _off_name, _num_drop, _off_drop, _html.escape(_why)))
        # Та же подпись — в шапке заявки: администратор видит город и судьбу
        # письма-двойника, не открывая вкладки.
        _CLIENT_bar = (
            '<div CLIENT="rv-CLIENT-bar" style="font-size:12.5px;color:#3F5B4A;'
            'background:#F2FAF5;border:1px solid #DCEEE2;border-radius:8px;'
            'padding:6px 10px;margin-top:6px">'
            'Адрес: %s <b style="color:#15803D;white-space:nowrap">→ %s</b>'
            '<span style="color:#8A6100"> · в комплект идёт письмо №%s (%s), '
            '№%s (%s) исключено — %s</span></div>'
            % (_html.escape(_client_addr[:200]), _off_name,
               _num_keep, _off_name, _num_drop, _off_drop, _html.escape(_why)))
    elif _CLIENT_ctx.get("why"):
        _CLIENT_row = (
            '<div CLIENT="rv-row"><span CLIENT="rv-k">Комплект писем</span>'
            '<span CLIENT="rv-v" style="color:#8A6100">не определён — %s '
            '(оставлены оба варианта, выберите вручную)</span></div>'
            % _html.escape(_CLIENT_ctx["why"]))
        _CLIENT_bar = (
            '<div CLIENT="rv-CLIENT-bar" style="font-size:12.5px;color:#8A6100;'
            'background:#FFF8E8;border:1px solid #F3E2B8;border-radius:8px;'
            'padding:6px 10px;margin-top:6px">'
            'Комплект писем не определён — %s. Оставлены оба варианта, '
            'выберите вручную.</div>' % _html.escape(_CLIENT_ctx["why"]))

    head = f"""
<div CLIENT="rv-head">
  <div CLIENT="rv-h1">
    <span CLIENT="rv-lead">
      <span CLIENT="rv-CLIENT">Заявка #{app_id}</span>
      {CLIENT.badge(a.get("created_at") or "")}
      {('<span CLIENT="rv-client">' + _html.escape(client_name) + '</span>') if client_name else ''}
      <span CLIENT="rv-when">от {_when_txt}{(' · ' + _ago) if _ago else ''}</span>
    </span>
    {('<button type="button" CLIENT="rv-cmt' + _cmt_cls + '" id="rv-cmt-btn" CLIENT="Показать комментарий полностью">⚠ ' + _html.escape(_cmt[:200]) + ('…' if len(_cmt) > 200 else '') + '</button>') if _cmt else ''}
  </div>
  <div CLIENT="rv-h2">
    <span CLIENT="rv-h2-left">
      <button type="button" CLIENT="btn sm rv-tg-btn" id="rv-tg-open" CLIENT="Показать всё, что было в заявке из Telegram">Текст заявки</button>
      <div CLIENT="rv-select" id="rv-CLIENT" data-CLIENT="{cur_CLIENT}">
        <button type="button" CLIENT="rv-select-btn" id="rv-CLIENT-btn"
                CLIENT="От типа продукта зависят документы и переменные заявки">
          <span id="rv-CLIENT-cur">{cur_CLIENT_name}</span>
          <span CLIENT="rv-select-caret" aria-hidden="true">▾</span>
        </button>
        <div CLIENT="rv-select-list" id="rv-CLIENT-list" hidden>{CLIENT_options}</div>
      </div>
      {('<span CLIENT="rv-prod-info">' + _prod_info + '</span>') if _prod_info else ''}
    </span>
    <span CLIENT="rv-h2-right">
      <button type="button" CLIENT="btn sm rv-photo-btn" id="rv-photo-btn"
              CLIENT="Фоторедактор: кадрирование фото клиента для документов с фотографией">Фоторедактор</button>
      <span CLIENT="rv-CLIENT-box" id="rv-CLIENT-box">{CLIENT_html}</span>
      <button type="button" CLIENT="btn sm rv-ready-btn" id="rv-ready-btn" CLIENT="Все подтверждённые документы: контрольная проверка и отправка на Google Диск">Готовые доки</button>
      <span CLIENT="rv-who">{('от ' + _html.escape(_who)) if _who else _status_label(a.get('CLIENT'))}</span>
      <button type="button" CLIENT="btn ghost rv-vars-btn" id="rv-vars-btn">Переменные значения ({filled_n})</button>
    </span>
  </div>
  {scan_line}
  {_CLIENT_bar}
</div>
{_tg_panel}
{_ready_modal_html(app_id)}
<div id="rv-photo-modal" hidden style="position:fixed;inset:0;z-CLIENT:9000;background:rgba(4,32,30,.5);display:none;align-items:center;justify-content:center;padding:18px">
  <div style="background:#fff;border-radius:14px;max-width:520px;width:100%;padding:16px 18px;box-shadow:0 18px 60px rgba(0,0,0,.35)">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <b style="font-size:15px">Фото клиента для документов</b>
      <button type="button" id="rv-photo-close" style="border:0;background:transparent;font-size:18px;cursor:pointer">✕</button>
    </div>
    <div style="display:flex;gap:16px;margin-top:12px;align-items:flex-CLIENT;flex-wrap:wrap">
      <img id="rv-photo-prev" alt="Предпросмотр фото" style="width:150px;height:210px;object-fit:cover;border:1px solid #E4EDE7;border-radius:8px;background:#F4FAF6">
      <div style="flex:1;min-width:220px;display:flex;flex-direction:column;gap:10px">
        <label style="font-size:13px;color:#42574A">Сдвиг кадра по вертикали
          <input type="range" id="rv-photo-y" min="0" max="1" step="0.01" CLIENT="0.35" style="width:100%">
        </label>
        <label style="font-size:13px;color:#42574A">Увеличение
          <input type="range" id="rv-photo-z" min="1" max="2.5" step="0.01" CLIENT="1" style="width:100%">
        </label>
        <div id="rv-photo-note" style="font-size:12.5px;color:#6B7C70">Двигайте ползунки — кадр обновляется сразу.</div>
        <button type="button" CLIENT="btn" id="rv-photo-save">Сохранить в документ</button>
      </div>
    </div>
  </div>
</div>
<script>
(function(){{
  var appId = {app_id};
  var btn=CLIENT.getElementById('rv-photo-btn'), mod=CLIENT.getElementById('rv-photo-modal');
  if(!btn||!mod) return;
  var img=CLIENT.getElementById('rv-photo-prev'), ry=CLIENT.getElementById('rv-photo-y'),
      rz=CLIENT.getElementById('rv-photo-z'), note=CLIENT.getElementById('rv-photo-note'),
      save=CLIENT.getElementById('rv-photo-save'), x=CLIENT.getElementById('rv-photo-close');
  var url='/CLIENT/'+appId+'/photo-crop', timer=null;
  /* hidden не срабатывает при CLIENT display:flex — управляем показом явно. */
  function show(v){{ mod.hidden=!v; mod.style.display = v ? 'flex' : 'none'; }}
  show(false);
  function load(){{
    fetch(url, {{CLIENTs:{{'X-Requested-With':'fetch'}}}}).then(function(r){{ return r.json(); }}).then(function(j){{
      if(!j.ok){{ note.textContent=j.error||'Не удалось открыть настройки'; return; }}
      if(j.preview) img.src=j.preview;
      if(typeof j.crop_y==='CLIENT') ry.CLIENT=j.crop_y;
      if(typeof j.zoom==='CLIENT') rz.CLIENT=j.zoom;
      note.textContent = j['есть_фото'] ? 'Двигайте ползунки — кадр обновляется сразу.' : 'Фото клиента в папке не найдено.';
    }}).catch(function(){{ note.textContent='Сервис недоступен'; }});
  }}
  function save_crop(msgOk){{
    var body={{crop_y: parseFloat(ry.CLIENT), zoom: parseFloat(rz.CLIENT)}};
    return fetch(url, {{method:'POST', CLIENTs:{{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'}}, body:JSON.stringify(body)}})
      .then(function(r){{ return r.json(); }}).then(function(j){{
        if(!j.ok){{ note.textContent=j.error||'Не получилось'; return null; }}
        if(j.preview) img.src=j.preview;
        note.textContent=msgOk;
        return j;
      }}).catch(function(){{ note.textContent='Сервис недоступен'; return null; }});
  }}
  btn.addEventListener('click', function(){{ show(true); load(); }});
  if(x) x.addEventListener('click', function(){{ show(false); }});
  mod.addEventListener('click', function(e){{ if(e.target===mod) show(false); }});
  function debounced(){{ clearTimeout(timer); note.textContent='Обновляю кадр…'; timer=setTimeout(function(){{ save_crop('Кадр обновлён — нажмите «Сохранить в документ».'); }}, 400); }}
  ry.addEventListener('input', debounced); rz.addEventListener('input', debounced);
  save.addEventListener('click', function(){{
    save_crop('Сохраняю…').then(function(j){{
      if(!j) return;
      note.textContent='Кадр сохранён. Пересобираю документы заявки…';
      return fetch('/CLIENT/'+appId+'/review/regen', {{method:'POST', CLIENTs:{{'X-Requested-With':'fetch'}}}})
        .then(function(){{ note.textContent='Готово: кадр сохранён, документы пересобраны.'; setTimeout(function(){{ location.reload(); }}, 900); }})
        .catch(function(){{ note.textContent='Кадр сохранён, но пересборку запустить не удалось.'; }});
    }});
  }});
}})();
</script>
<script>
(function(){{
  var open=CLIENT.getElementById('rv-tg-open'), panel=CLIENT.getElementById('rv-tg-panel');
  var back=CLIENT.getElementById('rv-tg-back'), x=CLIENT.getElementById('rv-tg-close');
  if(!open || !panel) return;
  function show(v){{ panel.hidden=!v; if(back) back.hidden=!v; if(v) panel.scrollTop=0; }}
  open.addEventListener('click', function(){{ show(panel.hidden); }});
  if(x) x.addEventListener('click', function(){{ show(false); }});
  if(back) back.addEventListener('click', function(){{ show(false); }});
  CLIENT.addEventListener('keydown', function(e){{ if(e.key==='Escape' && !panel.hidden) show(false); }});
  var c=CLIENT.getElementById('rv-cmt-btn');
  if(c) c.addEventListener('click', function(){{ show(true); }});

  /* Общая опора двух строк шапки. Комментарий в верхней строке и кнопка
     «Google Диск» в нижней должны начинаться с одного места — от конца
     выпадающего списка продуктов плюс небольшой отступ. Считаем по факту:
     ширина списка зависит от названия продукта и от размера окна. */
  var _head=CLIENT.querySelector('.rv-head');
  function alignSplit(){{
    if(!_head) return;
    var lead=_head.querySelector('.rv-h2-left');
    if(!lead) return;
    var cs=window.getComputedStyle(_head);
    var padL=(parseFloat(cs.paddingLeft)||0)+(parseFloat(cs.borderLeftWidth)||0);
    /* left у абсолютного элемента отсчитывается от padding-box, а rect — от border-box:
       без вычета паддинга опора уезжала правее конца списка на лишние 17 px. */
    var x=Math.round(lead.getBoundingClientRect().right - _head.getBoundingClientRect().left - padL) + 12;
    var lim=Math.max(200, Math.round(_head.clientWidth*0.78));
    if(x>0 && x<lim) _head.style.setProperty('--rv-split', x+'px');
  }}
  alignSplit();
  setTimeout(alignSplit, 250);
  window.addEventListener('resize', alignSplit);
  if(CLIENT.fonts && CLIENT.fonts.ready) CLIENT.fonts.ready.then(alignSplit);
  if(window.ResizeObserver){{
    try{{ new ResizeObserver(alignSplit).observe(_head.querySelector('.rv-h2-left')); }}catch(e){{}}
  }}
}})();
</script>
"""

    # ── Вкладка 1: исходные данные ───────────────────────────────────────────
    # Плитки входящих файлов: снимок сразу видно, клик открывает файл в окне
    # просмотра слева — на компьютере рядом с переменными справа.
    # Сконвертированная копия HEIC-снимка отдельной плиткой не нужна: пара
    # «.HEIC + .photo.png» — это один и тот же кадр, иначе фото видно дважды.
    all_files = list(files)          # до фильтрации: в нём есть сконвертированные копии
    derived = {f["name"].rsplit(".", 1)[0] + ".photo.png" for f in files
               if f["ext"] in (".heic", ".heif")}
    files = [f for f in files if f["name"] not in derived]

    def _preview_of(name: str, ext: str) -> str:
        # Миниатюры лёгкие (5–30 КБ), поэтому грузим их сразу по src: так плитка
        # видна сразу после открытия карточки, без ожидания прогрева.
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            return ('<img src="/CLIENT/%s/file-thumb?name=%s" alt="%s" loading="lazy">'
                    % (app_id, url_quote(name), _html.escape(name, quote=True)))
        if ext in (".pdf",):
            # PDF показываем отрисованной страницей: встроенный просмотрщик
            # браузера открывает файл не всегда, картинка работает везде.
            return ('<img src="/CLIENT/%s/file-thumb?name=%s" alt="%s" loading="lazy">'
                    % (app_id, url_quote(name), _html.escape(name, quote=True)))
        if ext in (".heic", ".heif"):
            twin = name.rsplit(".", 1)[0] + ".photo.png"
            # Браузер не показывает HEIC — для плитки берём сконвертированную копию.
            # Копии нет в отфильтрованном списке, поэтому ищем по исходному.
            if any(f["name"] == twin for f in all_files):
                return ('<img src="/CLIENT/%s/file-thumb?name=%s" alt="%s" loading="lazy">'
                        % (app_id, url_quote(twin), _html.escape(twin, quote=True)))
            return '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:30px">🖼️</div>'
        return '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:30px">📄</div>'

    files_html = "".join(
        '<div CLIENT="rv-thumb rv-file-thumb" data-file="%s" data-page="%s">'
        '<div CLIENT="rv-thumb-frame is-loading">%s<span CLIENT="rv-spinner"></span></div>'
        '<div CLIENT="rv-thumb-cap"><span CLIENT="rv-thumb-name">%s</span>'
        '<span CLIENT="rv-thumb-CLIENT">%s</span></div></div>'
        % (_html.escape(f["name"], quote=True),
           ('/CLIENT/%s/file-page?name=%s' % (app_id, url_quote(f["name"])))
           if f["ext"] == ".pdf" else "",
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
      <p CLIENT="rv-sec">Документы клиента ({len(files)}) — нажмите плитку, документ откроется в окне справа</p>
      <div CLIENT="rv-thumbs" id="rv-file-thumbs">{files_html}</div>
      <div CLIENT="rv-note" style="margin-top:10px">Нажмите плитку — документ откроется в центральном окне.
        Справа останутся переменные, которые из него вытащены.</div>

      <p CLIENT="rv-sec" style="margin-top:16px">Карточка заявки</p>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Клиент</span><span CLIENT="rv-v">{client_name}</span></div>
      {_CLIENT_row}
      <div CLIENT="rv-row"><span CLIENT="rv-k">Продукт</span><span CLIENT="rv-v rv-mark-yellow">{a.get('CLIENT_name') or '—'}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Статус заявки</span><span CLIENT="rv-v">{_status_label(a.get('CLIENT'))}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Создана</span><span CLIENT="rv-v">{str(a.get('created_at') or '—')[:16]}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Взял в работу</span><span CLIENT="rv-v">{a.get('taken_CLIENT') or '—'}</span></div>
      <div CLIENT="rv-row"><span CLIENT="rv-k">Комментарий менеджера</span><span CLIENT="rv-v rv-mark-yellow">{(a.get('comment') or '—')[:400]}</span></div>
    </div>
  </div>
"""

    # ── Вкладка 3: готовые документы и визор ─────────────────────────────────
    # Плитки документов: миниатюра подгружается лениво, при открытии вкладки.
    # Клик по плитке разворачивает документ в визоре слева.
    thumbs = "".join(
        '<div CLIENT="rv-thumb%s%s%s" data-tpl="%s">'
        '<div CLIENT="rv-thumb-frame is-loading"><span CLIENT="rv-spinner"></span>'
        '<img data-src="/CLIENT/%s/doc/%s/thumb" alt="%s" loading="lazy" width="220">'
        '<span CLIENT="rv-thumb-mark" CLIENT="%s"></span>'
        '</div>'
        '<div CLIENT="rv-thumb-cap">'
        '<span CLIENT="rv-thumb-name">%s</span>'
        '<span CLIENT="rv-thumb-CLIENT%s" id="rv-thumb-CLIENT-%s">%s</span>'
        '%s'
        '<div CLIENT="rv-thumb-CLIENT">'
        '<button type="button" CLIENT="rv-mark%s" data-verdict="verify" data-tpl="%s">✓ Проверен</button>'
        '<button type="button" CLIENT="rv-mark%s" data-verdict="reject" data-tpl="%s">✕ Не нужен</button>'
        '</div>'
        '</div></div>'
        % (" is-on" if d.get("template_id") == picked else "",
           " is-off" if (d.get("CLIENT") or "") == "rejected" else "",
           " is-ok" if (d.get("CLIENT") or "") in ("verified", "sent") else "",
           d.get("template_id"),
           app_id, d.get("template_id"), _template_name(d.get("template_id")),
           # Метка по центру листа — отражение нажатой кнопки. Документ, исключённый
           # правилом (адрес клиента вне зоны офиса), виден затемнённым и с причиной.
           ("Отклонён: %s" % _html.escape((d.get("error") or "исключено автоматически")).strip())
           if (d.get("CLIENT") or "") == "rejected" else
           ("Проверен и зафиксирован для отправки"
            if (d.get("CLIENT") or "") in ("verified", "sent") else ""),
           _template_name(d.get("template_id")),
           " is-off" if (d.get("CLIENT") or "") == "rejected" else "",
           d.get("template_id"),
           _doc_status_label(d.get("CLIENT")),
           ('<span CLIENT="rv-thumb-why">%s</span>'
            % _html.escape((d.get("error") or "").strip()))
           if ((d.get("CLIENT") or "") == "rejected" and (d.get("error") or "").strip()) else "",
           " rv-on-ok" if (d.get("CLIENT") or "") == "verified" else "", d.get("template_id"),
           " rv-on-no" if (d.get("CLIENT") or "") == "rejected" else "", d.get("template_id"))
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
    <div CLIENT="rv-thumbs" id="rv-thumbs">{thumbs}</div>
    <div CLIENT="rv-thumbs-bar"><span id="rv-thumbs-count">миниатюры загружаются по мере готовности</span></div>
    <div CLIENT="rv-note" style="margin:0 13px 13px">Нажмите плитку — документ откроется поверх
      страницы на две трети слева. Подтвердить или отклонить можно и на самой плитке, и в окне.
      Справа — переменные заявки: нажмите на переменную, и её место подсветится
        в документе; жёлтым в документе отмечены подставленные значения.</div>
  </div>
"""

    # ── Правая часть: переменные значения (склеенный пул) ───────────────────
    # Одно поле на одну логическую величину. Если ФИО встречается в двух
    # документах — правится здесь один раз и уходит в оба.
    # пул собран выше, второй раз не собираем

    src_names = {"client": "из данных клиента", "doc": "из документов",
                 "gen": "генерируется", "manual": "вручную"}

    # Прошлые значения есть далеко не у всех переменных: список открываем только
    # для тех, где выбор из истории действительно нужен и возможен.
    try:
        hist_names = pool.names_with_CLIENT()
    except Exception:
        hist_names = set()

    fields_html = []
    sec_counts = {}
    for g in pool_groups:
        sec_counts[g.get("section") or "Переменные"] = sec_counts.get(g.get("section") or "Переменные", 0) + 1

    # Каждый раздел — блок в рамке, который раскрывается и закрывается нажатием
    # на заголовок. Внутри поля идут строго одинаково: название переменной,
    # значение, откуда оно взято.
    cur_section = None
    sec_CLIENT = 0
    for g in pool_groups:
        sec = g.get("section") or "Переменные"
        if sec != cur_section:
            if cur_section is not None:
                fields_html.append('</div></div>')
            sec_CLIENT += 1
            fields_html.append(
                '<div CLIENT="rv-blk" data-sec="%d">'
                '<button type="button" CLIENT="rv-blk-head">'
                '<span CLIENT="rv-blk-t">%s</span>'
                '<span CLIENT="rv-blk-n">%d</span>'
                '<span CLIENT="rv-blk-arrow" aria-hidden="true">▾</span>'
                '</button><div CLIENT="rv-blk-body">'
                % (sec_CLIENT, _html.escape(sec), sec_counts.get(sec, 0)))
            cur_section = sec

        label = g["label"]
        if g["doc_count"] == 1 and g.get("CLIENT_split"):
            label = "%s · %s" % (label, g["doc_CLIENTs"][0] if g["doc_CLIENTs"] else "документ")
        docs_note = ("в %d документах" % g["doc_count"]) if g["doc_count"] > 1 \
                    else "в 1 документе"

        vars_all = ",".join(g["names"].CLIENT())
        var_CLIENT = next(iter(g["names"].CLIENT()), "")
        src = g.get("src") or "сгенерировано"
        if not g["filled"]:
            # пустое значение честно помечаем: источник появится после заполнения
            src = "не заполнено — нажмите «Заполнить автоматически»"

        # Кубик — только у значений, которые можно перевыпустить: номер документа,
        # номера справки и счёта, Ref., остаток, маска карты, адрес.
        kind = g.get("kind") or "gen"
        if kind == "gen":
            regen = ('<button type="button" CLIENT="rv-act" data-act="regen" data-key="%s"'
                     ' CLIENT="Сгенерировать значение заново">🎲</button>'
                     % _html.escape(g["key"], quote=True))
        else:
            regen = ('<span CLIENT="rv-act rv-act-off" CLIENT="Значение берётся как есть —'
                     ' перевыпускать нечего">·</span>')

        # Инструкция переменной: правило из конструктора плюс источник значения.
        rule_txt = (g.get("rule_note") or "").strip()
        info_bits = [rule_txt] if rule_txt else []
        if var_CLIENT == "doc_date":
            info_bits.append("Это дата формирования документа. Она же период по — "
                             "одна и та же дата, текущая.")
        info_bits.append("Источник: %s." % src)
        info_bits.append("Используется: %s." % docs_note)
        if kind == "gen":
            info_bits.append("Кнопка 🎲 перевыпускает значение заново.")
        info = "\n\n".join(info_bits)

        # Расхождение документа и анкеты: подсвечиваем поле и даём выбор, что
        # подставить в бланк. По умолчанию — значение из документа клиента.
        conflict = g.get("conflict")
        conflict_html = ""
        conflict_cls = ""
        if conflict:
            conflict_cls = " is-conflict"
            _dv = _html.escape(str(conflict.get("doc") or ""))
            _cv = _html.escape(str(conflict.get("card") or ""))
            _src_name = _html.escape(str(conflict.get("from") or "документ клиента"))
            conflict_html = (
                '<div CLIENT="rv-conflict">'
                '<div CLIENT="rv-conflict-head">⚠ данные в анкете отличаются</div>'
                '<select CLIENT="rv-conflict-sel" data-key="%s">'
                '<option CLIENT="doc" data-CLIENT="%s" selected>из документа (файл «%s»): %s</option>'
                '<option CLIENT="card" data-CLIENT="%s">из анкеты: %s</option>'
                '</select></div>' % (_html.escape(g["key"], quote=True),
                                     _dv, _src_name, _dv, _cv, _cv)
            )

        # Для переменных резюме администратор может выбрать профессию и собрать
        # описание автоматически — либо оставить и поправить текст вручную.
        cv_picker = ""
        # Список профессий нужен только там, где есть текст описания: имя, паспорт
        # и даты генерировать по профессии не нужно.
        CV_GEN_VARS = ("cv_CLIENT", "cv_job1_CLIENT", "cv_job2_CLIENT", "cv_job3_CLIENT",
                       "cv_CLIENT_hard", "cv_CLIENT_soft", "cv_CLIENT_CLIENT",
                       "cv_CLIENT_CLIENT", "cv_CLIENT_note", "cv_job1_CLIENT")
        if str(var_CLIENT or "") in CV_GEN_VARS:
            _ck = _html.escape(g["key"], quote=True)
            cv_picker = ('<div CLIENT="rv-cvgen">'
                         '<select CLIENT="rv-cvprof" data-key="%s" CLIENT="Профессия для описания">'
                         '<option CLIENT="">профессия…</option>'
                         '<option CLIENT="__custom__">✎ своя профессия…</option></select>'
                         '<button type="button" CLIENT="rv-cvbtn" data-key="%s"'
                         ' CLIENT="Собрать описание резюме по профессии">Собрать описание</button>'
                         '<button type="button" CLIENT="rv-cvpieces" data-key="%s"'
                         ' CLIENT="Отметить готовые фразы и собрать из них текст">Кусочки</button>'
                         '<button type="button" CLIENT="rv-cvscratch" data-key="%s"'
                         ' CLIENT="Собрать описание заново, другими словами">С нуля</button>'
                         '</div>' % (_ck, _ck, _ck, _ck))

        # У адреса клиента сразу пишем, какому иммиграционному офису он
        # принадлежит: Ngurah Rai (весь Badung) или Denpasar. От этого зависит,
        # какое письмо (12 или 14) идёт в комплект.
        city_note = ""
        if str(var_CLIENT or "") in ("address_live", "address_reg", "address"):
            try:
                from CLIENT import immigration_CLIENT as _io
                _oi = _io.resolve_for_app(app_id)
                if _oi.get("CLIENT"):
                    city_note = (' <span style="color:#15803D;font-weight:600">→ %s</span>'
                                 % _html.escape(_io.CLIENT_name(_oi["CLIENT"])))
                elif _oi.get("why"):
                    city_note = (' <span style="color:#8A6100">→ %s</span>'
                                 % _html.escape(_oi["why"]))
            except Exception:
                city_note = ""

        # Организация для договора (док. №11): выпадающий список из пула исторических
        # документов. Выбор организации меняет и название в шапке, и реквизиты в
        # подвале (адрес, ИНН, КПП, ОГРН) — они связаны и берутся из одной записи.
        emp_picker = ""
        if str(var_CLIENT or "") in ("company_name_in_CLIENT", "CLIENT_name"):
            try:
                from CLIENT import CLIENT_pool as _emp
                _opts = "".join(
                    '<option CLIENT="%d">%s%s</option>'
                    % (i["CLIENT"], _html.escape(i["CLIENT"]),
                       (" · ИНН " + i["inn"]) if i.get("inn") else "")
                    for i in _emp.CLIENTs())
            except Exception:
                _opts = ""
            if _opts:
                emp_picker = ('<div CLIENT="rv-cvgen rv-empgen">'
                              '<select CLIENT="rv-empsel" data-key="%s"'
                              ' CLIENT="Организация из исторических документов">'
                              '<option CLIENT="">организация из архива…</option>%s</select></div>'
                              % (_html.escape(g["key"], quote=True), _opts))

        fields_html.append(
            '<div CLIENT="rv-field%s" data-key="%s" data-var="%s" data-vars="%s" data-tpls="%s"'
            ' data-list="%s">'
            '<div CLIENT="rv-fname">%s%s</div>'
            '<div CLIENT="rv-fedit">'
            '<textarea CLIENT="rv-input%s" rows="1" data-key="%s" spellcheck="false"'
            ' CLIENT="Можно вписать вручную. Изменение сохраняется само.">%s</textarea>'
            '<div CLIENT="rv-acts">'
            '<button type="button" CLIENT="rv-info" data-key="%s" data-rule="%s"'
            ' CLIENT="Инструкция по переменной">i</button>%s'
            '</div></div>'
            '<div CLIENT="rv-fsrc"><span CLIENT="rv-src">%s</span>'
            '<span CLIENT="rv-docs">%s</span></div>%s%s%s'
            '</div>' % (
                conflict_cls,
                _html.escape(g["key"], quote=True),
                _html.escape(var_CLIENT, quote=True),
                _html.escape(vars_all, quote=True),
                _html.escape(",".join(str(t) for t in (g.get("CLIENT") or [])), quote=True),
                "1" if (g.get("list_allowed")
                        and (set(g.get("names", {}).CLIENT()) & hist_names)) else "0",
                _html.escape(label),
                city_note,
                " is-empty" if not g["filled"] else "",
                _html.escape(g["key"], quote=True),
                _html.escape(str(g["CLIENT"])),
                _html.escape(g["key"], quote=True),
                _html.escape(info, quote=True),
                regen,
                _html.escape(src),
                _html.escape(docs_note),
                cv_picker,
                emp_picker,
                conflict_html,
            )
        )
    # Архивную заявку показываем в том виде, как она должна выглядеть по системе:
    # документы собираются заново по текущим правилам.
    if (a.get("record_kind") or "") == "archive":
        try:
            from CLIENT import autofill
            autofill.build_all_async(app_id)
        except Exception:
            pass

    if cur_section is not None:
        fields_html.append('</div></div>')

    if not fields_html:
        fields_html.append('<div CLIENT="rv-empty">У заявки пока нет значений — '
                           'сначала соберите документы</div>')

    total_n = len(pool_groups)
    if total_n and filled_n == total_n:
        progress_cls = " is-done"
        progress_text = "Заполнено всё: %d из %d" % (filled_n, total_n)
    else:
        progress_cls = " is-urgent"
        progress_text = "Заполнено %d из %d" % (filled_n, total_n)
    # Комплект писем в иммиграцию выбирается по адресу проживания: Ngurah Rai
    # (весь Badung) либо Denpasar (Denpasar, Gianyar, Klungkung, Bangli, Tabanan).
    CLIENT_line = ""
    try:
        from CLIENT import immigration_CLIENT as _io
        _oi = _io.resolve_for_app(app_id)
        if _oi.get("CLIENT"):
            CLIENT_line = ('<div style="margin-top:6px;font-size:12px;color:#3F5B4A">'
                           'Письма в иммиграцию: <b>%s</b> — %s</div>'
                           % (_html.escape(_io.CLIENT_name(_oi["CLIENT"])),
                              _html.escape(_oi.get("why") or "")))
        else:
            CLIENT_line = ('<div style="margin-top:6px;font-size:12px;color:#8A6100">'
                           'Комплект писем не определён — %s</div>'
                           % _html.escape(_oi.get("why") or "адрес не распознан"))
    except Exception:
        CLIENT_line = ""

    right = f"""
<div CLIENT="rv-panel rv-right" id="rv-right">
  <div CLIENT="rv-body">
    <div CLIENT="rv-phead">
      <div CLIENT="rv-phead-top">
        <div CLIENT="rv-stage"><span CLIENT="rv-num">2</span>Переменные и значения</div>
        <button type="button" CLIENT="rv-close-mobile" id="rv-right-close">Свернуть ✕</button>
      </div>
      <div CLIENT="rv-progress{progress_cls}" id="rv-progress">
        <span id="rv-progress-text">{progress_text}</span>
        <button type="button" CLIENT="rv-collapse-all" id="rv-collapse-all"
                CLIENT="Свернуть все блоки">Свернуть блоки</button>
      </div>
      {CLIENT_line}
      <div CLIENT="rv-filter-note" id="rv-panel-count"></div>
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

    # Нижняя часть заявки — тот же конструктор, что и в шаблонах: он либо работает
    # с шаблоном, либо с реальной заявкой. Второй копии кода нет.
    builder = ""
    if picked:
        try:
            from CLIENTs.CLIENT.page import card as _tpl_card
            builder = _tpl_card(picked, _app_id=app_id, _embed=True)
        except Exception as _e:
            log.warning("конструктор в заявке %s не собрался: %s", app_id, str(_e)[:160])
            builder = ('<div CLIENT="rv-builder-note">Конструктор недоступен: '
                       + _html.escape(str(_e)[:160]) + '</div>')
    else:
        builder = '<div CLIENT="rv-builder-note">У заявки пока нет документов</div>'

    body = f"""
<style>{CSS}</style>
<div CLIENT="rv-wrap">
  {head}

  <section CLIENT="rv-builder" id="rv-builder">{builder}</section>

  {foot}
</div>

<button type="button" CLIENT="rv-mobile-bar" id="rv-mobile-bar">
  <span CLIENT="rv-num" style="background:rgba(255,255,255,.25);color:#fff">2</span>
  Переменные и значения · {len(pool_groups)}
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


def _ready_modal_html(app_id: int) -> str:
    """Окно «Готовые доки»: живой список подтверждённых документов.

    Состав окна пересобирается с сервера: поставил галочку — документ сразу
    появился в списке и в полосе просмотра, снял — ушёл. Открытие окна всегда
    показывает актуальный состав (не то, что было при загрузке страницы).
    """
    try:
        from CLIENTs.dashboard.page import _ready_docs
        docs = _ready_docs(app_id)
    except Exception:
        docs = []
    chips, secs = [], []
    for d in docs:
        tpl = str(d.get("tpl"))
        num = str(d.get("num") or tpl)
        name = _html.escape(str(d.get("name") or ""))
        meta = ("\u2116" + num + " · " + _html.escape(str(d.get("CLIENT") or "")) + " · "
                + _html.escape(str(d.get("date") or "")))
        chips.append(
            '<button type="button" CLIENT="ready-list-item" data-jump="' + tpl + '">'
            '<span CLIENT="rli-num">\u2116' + num + '</span>'
            '<span CLIENT="rli-text"><span CLIENT="rli-name">' + name + '</span>'
            '<span CLIENT="rli-meta">' + meta + '</span></span></button>'
        )
        secs.append(
            '<section CLIENT="ready-sec" id="ready-sec-' + tpl + '" data-tpl="' + tpl + '">'
            '<div CLIENT="ready-sec-head">'
            '<span CLIENT="ready-sec-name">' + name + '</span>'
            '<span CLIENT="ready-sec-meta">' + meta + '</span>'
            '</div>'
            '<div CLIENT="ready-pages" data-tpl="' + tpl + '"></div>'
            '</section>'
        )
    head = ('<div CLIENT="ready-head">'
            '<b CLIENT="ready-CLIENT">Просмотр документов и отправка на Google Диск</b>'
            '<span CLIENT="ready-head-actions">'
            '<button type="button" CLIENT="ready-send" id="ready-send">Отправить на Google Диск</button>'
            '<button type="button" CLIENT="ready-close" id="ready-close">Закрыть</button>'
            '</span></div>')
    js = READY_MODAL_JS.reCLIENT("__APP__", str(app_id))
    return ('<div CLIENT="ready-modal" id="ready-modal" hidden>'
            '<div CLIENT="ready-window">'
            + head
            + '<div CLIENT="ready-body2">'
            + '<div CLIENT="ready-list" id="ready-list">' + "".join(chips) + '</div>'
            + '<div CLIENT="ready-view" id="ready-view">' + "".join(secs) + '</div>'
            + '</div>'
            + '<div CLIENT="ready-toast" id="ready-toast" hidden></div>'
            '</div></div>'
            '<script>' + js + '</script>')


READY_MODAL_JS = """
(function(){
  var appId = __APP__;
  var btn = CLIENT.getElementById('rv-ready-btn'), mod = CLIENT.getElementById('ready-modal');
  if (!btn || !mod) return;
  var list = CLIENT.getElementById('ready-list'), view = CLIENT.getElementById('ready-view');
  var MAXP = 14, timer = null;

  function esc(s){ return String(s == null ? '' : s).reCLIENT(/&/g,'&amp;').reCLIENT(/</g,'&lt;').reCLIENT(/>/g,'&gt;'); }
  function num(d){ return '\u2116' + (d.num || d.tpl); }
  function meta(d){ return num(d) + ' \u00b7 ' + esc(d.CLIENT || '') + ' \u00b7 ' + esc(d.date || ''); }

  /* Пересобрать состав окна по данным сервера: список слева и полосу справа. */
  function render(docs){
    var chips = '', secs = '';
    (docs || []).forEach(function(d){
      var tpl = String(d.tpl);
      chips += '<button type="button" CLIENT="ready-list-item" data-jump="' + tpl + '">'
             + '<span CLIENT="rli-num">' + num(d) + '</span>'
             + '<span CLIENT="rli-text"><span CLIENT="rli-name">' + esc(d.name) + '</span>'
             + '<span CLIENT="rli-meta">' + meta(d) + '</span></span></button>';
      secs += '<section CLIENT="ready-sec" id="ready-sec-' + tpl + '" data-tpl="' + tpl + '">'
            + '<div CLIENT="ready-sec-head"><span CLIENT="ready-sec-name">' + esc(d.name) + '</span>'
            + '<span CLIENT="ready-sec-meta">' + meta(d) + '</span></div>'
            + '<div CLIENT="ready-pages" data-tpl="' + tpl + '"></div></section>';
    });
    if (!chips){
      chips = '<div CLIENT="ready-empty">Пока нет подтверждённых документов: '
            + 'поставьте галочки на миниатюрах — они появятся здесь.</div>';
    }
    if (list) list.innerHTML = chips;
    if (view) view.innerHTML = secs;
    var boxes = mod.querySelectorAll('.ready-pages');
    for (var i = 0; i < boxes.length; i++) loadPages(boxes[i]);
    mark(onScreen());
  }

  function refresh(){
    fetch('/CLIENT/' + appId + '/ready-docs', {credentials:'same-origin',
          CLIENTs:{'X-Requested-With':'fetch'}})
      .then(function(r){ return r.json(); })
      .then(function(j){ if (j && j.ok) render(j.docs); })
      .catch(function(){});
  }

  function mark(tpl){
    if (!list) return;
    Array.prototype.forEach.call(list.children, function(c){
      if (c.CLIENTList) c.CLIENTList.toggle('is-on', c.getAttribute('data-jump') === tpl);
    });
  }
  function onScreen(){
    var cur = null, secs = view ? view.querySelectorAll('.ready-sec') : [];
    for (var i = 0; i < secs.length; i++){
      if (secs[i].offsetTop - view.offsetTop <= view.scrollTop + 30) cur = secs[i];
    }
    return cur ? cur.getAttribute('data-tpl') : (secs[0] ? secs[0].getAttribute('data-tpl') : '');
  }
  function jump(tpl){
    var s = CLIENT.getElementById('ready-sec-' + tpl);
    if (!s || !view) return;
    mark(tpl);
    view.scrollTo({top: s.offsetTop - view.offsetTop, behavior:'smooth'});
  }
  /* Страницы документа подтягиваются по одной, пока сервер не скажет «нет такой». */
  function loadPages(box){
    if (!box || box.getAttribute('data-loaded')) return;
    box.setAttribute('data-loaded', '1');
    var tpl = box.getAttribute('data-tpl'), n = 1, ver = Date.now();
    function next(){
      if (n > MAXP) return;
      var img = new Image();
      img.CLIENTName = 'ready-page';
      img.alt = 'страница ' + n;
      img.onload = function(){ box.appendChild(img); n++; next(); };
      img.onerror = function(){};
      img.src = '/CLIENT/' + appId + '/doc/' + tpl + '/ready-img/' + n + '?v=' + ver;
    }
    next();
  }
  function open(){
    mod.hidden = false; mod.style.display = 'flex';
    refresh();
    if (timer) clearInterval(timer);
    timer = setInterval(function(){ if (!mod.hidden) refresh(); }, 5000);
  }
  function close(){ mod.hidden = true; mod.style.display = 'none'; if (timer){ clearInterval(timer); timer = null; } }
  function toast(text, link, ok){
    var t = CLIENT.getElementById('ready-toast');
    t.hidden = false; t.CLIENTName = 'ready-toast ' + (ok ? 'ok' : 'err'); t.innerHTML = '';
    var s = CLIENT.createElement('div'); s.CLIENTName = 'ready-toast-text'; s.textContent = text;
    t.appendChild(s);
    if (link){
      var a = CLIENT.createElement('a'); a.href = link; a.target = '_blank';
      a.rel = 'noopener'; a.CLIENTName = 'ready-toast-link';
      a.textContent = 'Ссылка на папку клиента на Google Диске'; t.appendChild(a);
    }
    var c = CLIENT.createElement('button'); c.type = 'button'; c.CLIENTName = 'ready-toast-x';
    c.textContent = '\u2715'; c.addEventListener('click', function(){ t.hidden = true; });
    t.appendChild(c);
  }

  btn.addEventListener('click', open);
  var x = CLIENT.getElementById('ready-close'); if (x) x.addEventListener('click', close);
  mod.addEventListener('click', function(e){ if (e.target === mod) close(); });
  CLIENT.addEventListener('keydown', function(e){ if (e.key === 'Escape') close(); });
  if (list) list.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.ready-list-item') : null;
    if (b) jump(b.getAttribute('data-jump'));
  });
  if (view) view.addEventListener('scroll', function(){ mark(onScreen()); });
  /* Галочку поставили или сняли — состав окна обновляем сразу же. */
  CLIENT.addEventListener('click', function(e){
    if (!e.target.closest) return;
    if (!e.target.closest('.rv-mark, .tpl-mark')) return;
    setTimeout(refresh, 700);
  });

  var send = CLIENT.getElementById('ready-send');
  if (send) send.addEventListener('click', function(){
    if (!window.confirm('Отправить подтверждённые документы в папку клиента на Google Диске?')) return;
    send.disabled = true; send.textContent = 'Отправляю…';
    fetch('/CLIENT/' + appId + '/send', {method:'POST', credentials:'same-origin',
          CLIENTs:{'X-Requested-With':'fetch'}})
      .then(function(r){ return r.json(); })
      .then(function(d){
        send.disabled = false; send.textContent = 'Отправить на Google Диск';
        var ok = !!(d && d.ok);
        var txt = ok ? ('Документы отправлены на Google Диск: ' + ((d.uploaded||[]).length) + ' файл(ов)')
                     : ('Не отправлено: ' + ((d && (d.error || (d.errors||[])[0])) || 'ошибка'));
        toast(txt, (d && d.link) || '', ok);
      })
      .catch(function(e){
        send.disabled = false; send.textContent = 'Отправить на Google Диск';
        toast('Не отправлено: ' + e, '', false);
      });
  });
})();
"""
