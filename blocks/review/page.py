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

Старый экран (/applications/<id>/view) не меняется. Визор готовых документов —
зафиксированный движок из blocks/shared/layout.py: контейнер с data-zoom-pan
и .html-stage внутри, тулбар движок строит сам.
"""
import html as _html
import json
import logging
from pathlib import Path

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from urllib.parse import quote as url_quote

from core import db
from blocks.review import pool
from blocks.review.scripts import js_for
from services import marks

bp = Blueprint("review", __name__)


# Стили каркаса отдельной строкой (не f-строкой): в CSS фигурные скобки,
# внутри f-строки Python принял бы их за подстановку.
from blocks.review.styles import CSS     # стили вынесены отдельным модулем

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
        name = (client.get("full_name_latin") or client.get("full_name")
                or " ".join(x for x in (client.get("surname"), client.get("name")) if x))
        if name:
            return name
    return " ".join(x for x in (a.get("surname"), a.get("name")) if x) or "без имени"


# Сигнатуры файлов: у выгрузок с Google Drive расширения иногда нет вовсе,
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
        if head.startswith(sig):
            return ext
    if head[4:8] == b"ftyp":
        return ".heic"
    return ""


def _mime_of(path, ext: str = "") -> str:
    """Тип содержимого для браузера."""
    ext = ext or _sniff_ext(path)
    return {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
            ".heic": "image/heic", ".tif": "image/tiff", ".tiff": "image/tiff",
            ".mp4": "video/mp4", ".webm": "video/webm"}.get(ext, "application/octet-stream")


def _client_files(client_id):
    """Файлы клиента из локального кэша Google Drive."""
    root = Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % client_id)
    out = []
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
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


def _doc_values_by_template(app_id: int) -> dict:
    """Значения по каждому документу заявки: {template_id: {имя: значение}}."""
    out = {}
    for r in db.q(
        "SELECT template_id, values_json FROM application_documents "
        "WHERE application_id=? ORDER BY id",
        (app_id,),
    ) or []:
        try:
            vals = json.loads(r.get("values_json") or "{}")
        except Exception:
            vals = {}
        if vals:
            out[r.get("template_id")] = vals
    return out


def _template_meta(template_id: int) -> list:
    """Описания переменных шаблона: подпись, тип, откуда берётся."""
    return db.q(
        "SELECT name, label, vtype, source_kind, sort_order FROM template_variables "
        "WHERE template_id=? ORDER BY sort_order, id",
        (template_id,),
    ) or []


def _template_name(template_id) -> str:
    if not template_id:
        return "—"
    row = db.q1("SELECT code, title FROM templates WHERE id=?", (template_id,))
    if isinstance(row, dict):
        return row.get("title") or row.get("code") or ("шаблон %s" % template_id)
    return "шаблон %s" % template_id




@bp.route("/applications/<int:app_id>/photo-crop", methods=["GET", "POST"])
def app_photo_crop(app_id: int):
    """Кадрирование фото клиента для документов с фотографией.

    GET  — текущие настройки (сдвиг кадра по вертикали, увеличение) и предпросмотр.
    POST — сохранить настройки; документ собирается тем же движком, что и обычно
           (services/values.py берёт подготовленный кадр).
    """
    from services import photo as photo_svc
    a = db.application_get(app_id)
    if not a:
        return jsonify({"ok": False, "error": "Заявка не найдена"}), 404
    cid = a.get("client_id")
    if not cid:
        return jsonify({"ok": False, "error": "У заявки не указан клиент"}), 400
    try:
        from services.values import _client_photo_path
        src = _client_photo_path(cid)
    except Exception:
        src = ""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
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


@bp.route("/applications/<int:app_id>/file-page")
def app_file_page(app_id):
    """Первая страница PDF клиента картинкой.

    Встроенный просмотрщик PDF в браузере показывает файл не всегда, а страница
    картинкой открывается везде одинаково. Отрисовка кладётся в кэш.
    """
    from flask import send_file, abort
    import subprocess
    import hashlib
    name = (request.args.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        abort(404)
    a = db.application_get(app_id)
    if not a or not a.get("client_id"):
        abort(404)
    root = (Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % a["client_id"])).resolve()
    target = (root / name).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        abort(404)
    if _mime_of(target) != "application/pdf":
        abort(404)
    # Отрисовку делает общий сервис превью: он сам выбирает движок и умеет
    # читать сканы с битой структурой, которые pdftoppm не открывает.
    from services import previews as _pv
    out = _pv.ensure(target, 0)
    if not out:
        log.warning("страница PDF не отрисовалась: %s", name)
        abort(500)
    resp = send_file(str(out), mimetype="image/png", conditional=True)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.route("/applications/<int:app_id>/file-thumb")
def app_file_thumb(app_id):
    """Миниатюра входящего файла клиента — лёгкая уменьшенная копия из кэша.

    Плитка в блоке «Документы клиента» должна весить десятки килобайт: фото с
    телефона — 3–6 МБ, а миниатюра нужна ровно для показа. PDF рисуется
    страницей, картинка — уменьшенной копией; и то и другое кэшируется и
    прогревается заранее (scripts/app_prepare.py).
    """
    from flask import send_file, abort
    from services import previews as _pv
    name = (request.args.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        abort(404)
    a = db.application_get(app_id)
    if not a or not a.get("client_id"):
        abort(404)
    root = (Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % a["client_id"])).resolve()
    target = (root / name).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
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
                Image.open(page).convert("RGB").save(webp, "WEBP", quality=72, method=4)
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
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.route("/applications/<int:app_id>/file")
def app_file(app_id):
    """Отдаёт входящий файл клиента из локального кэша Google Drive.

    Нужен для предпросмотра: администратор должен видеть реальный документ
    рядом с переменными. Путь проверяем, чтобы нельзя было выйти за каталог.
    """
    from flask import send_file, abort
    name = (request.args.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        abort(404)
    a = db.application_get(app_id)
    if not a or not a.get("client_id"):
        abort(404)
    root = (Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % a["client_id"])).resolve()
    target = (root / name).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        abort(404)
    resp = send_file(str(target), as_attachment=False, conditional=True,
                     mimetype=_mime_of(target))
    # Файл клиента не меняется: браузер держит его в кэше, и повторный просмотр
    # открывается сразу, без повторной загрузки с сервера.
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.route("/applications/<int:app_id>/review/value", methods=["POST"])
def app_review_value(app_id):
    """Сохранить значение: пишется во все документы, где есть эта величина."""
    key = (request.form.get("key") or "").strip()
    value = request.form.get("value")
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    res = pool.set_value(app_id, key, value or "")
    res["docs_updated"] = len(res.get("touched") or [])
    # Если администратор выбрал значение из документа или из анкеты — запоминаем
    # выбор, чтобы разбор документов больше не перебивал его своим значением.
    source = (request.form.get("source") or "").strip()
    if source in ("doc", "card"):
        try:
            pool.mark_choice(app_id, key, source, value or "")
            res["chosen"] = source
        except Exception:
            pass
    return jsonify(res)


@bp.route("/applications/<int:app_id>/review/product", methods=["POST"])
def app_review_product(app_id):
    """Сменить тип продукта заявки.

    Меняется вся цепочка: под новый продукт подставляется свой пакет документов,
    а переменные пересобираются — на экране сразу видно, что документов и полей
    стало другое количество. Документы прежнего продукта, которые ещё не выпущены,
    убираются, чтобы не мешались в панели; выпущенные (проверенные, отправленные)
    остаются как есть.
    """
    pid = (request.form.get("product_id") or "").strip()
    row = db.q1("SELECT id, name FROM products WHERE id=?", (pid,))
    if not row:
        return jsonify({"ok": False, "error": "продукт не найден"}), 400

    db.exec_sql("UPDATE applications SET product_id=? WHERE id=?", (row["id"], app_id))

    # Свои документы нового продукта заводим сразу — на них смотрит панель переменных
    keep, added = set(), 0
    for t in db.q("SELECT template_id FROM product_documents WHERE product_id=? "
                  "ORDER BY sort_order, id", (row["id"],)) or []:
        keep.add(t.get("template_id"))
        try:
            db.application_doc_create(app_id, t.get("template_id"))
            added += 1
        except Exception:
            pass

    # Убираем черновики прежнего продукта: выпущенные документы не трогаем
    removed = 0
    for d in db.application_documents(app_id) or []:
        if d.get("template_id") in keep:
            continue
        # Отправленные документы не трогаем — они уже ушли клиенту.
        # Собранные ранее черновики убираем: они от прежнего продукта.
        if (d.get("status") or "") == "sent":
            continue
        try:
            db.exec_sql("DELETE FROM application_documents WHERE id=?", (d.get("id"),))
            removed += 1
        except Exception:
            pass

    return jsonify({"ok": True, "product": row.get("name"), "documents": added,
                    "removed": removed})


@bp.route("/applications/<int:app_id>/review/scan-status")
def app_review_scan_status(app_id):
    """Состояние разбора документов: по нему понятно, можно ли ставить галочку.

    Галочка ставится, когда разбор действительно прошёл и документы скачаны.
    Пока идёт — на кнопке крутится индикатор; если не удалось — показываем причину.
    """
    from services import drive as _drive
    a = db.application_get(app_id) or {}
    st = _drive.status(app_id) or {}
    files = len(_drive.docs_for_client(a.get("client_id"))) if a.get("client_id") else 0
    ok = ((st.get("status") or "") == "ok" and (st.get("total") or 0) > 0
          and (st.get("done") or 0) >= (st.get("total") or 0))
    return jsonify({"status": st.get("status") or "none", "done": st.get("done") or 0,
                    "total": st.get("total") or 0, "note": st.get("note") or "",
                    "files": files, "ok": bool(ok)})


@bp.route("/applications/<int:app_id>/review/regen", methods=["POST"])
def app_review_regen(app_id):
    """Сгенерировать значение заново по правилам."""
    key = (request.form.get("key") or "").strip()
    profession = (request.form.get("profession") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.regenerate(app_id, key, profession=profession))


@bp.route("/applications/<int:app_id>/review/professions")
def app_review_professions(app_id):
    """Справочник профессий для резюме: из него администратор выбирает профессию."""
    from services import cv_gen
    items = [{"code": p["code"], "ru": p.get("ru", ""), "en": p.get("en", "")}
             for p in cv_gen.load_positions()]
    return jsonify({"ok": True, "items": items})


@bp.route("/applications/<int:app_id>/review/phrases")
def app_review_phrases(app_id):
    """Готовые фразы («кусочки») для поля резюме: администратор отмечает нужные."""
    key = (request.args.get("key") or "").strip()
    profession = (request.args.get("profession") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.phrases(app_id, key, profession=profession))


@bp.route("/applications/<int:app_id>/review/employer_values")
def app_review_employer_values(app_id):
    """Реквизиты выбранной организации из пула исторических документов.

    Одна запись пула даёт и название в шапке договора, и адрес с ИНН/КПП/ОГРН
    в подвале — поэтому интерфейс меняет все связанные переменные одним выбором.
    """
    from services import employer_pool as _emp
    try:
        idx = int(request.args.get("index") or -1)
    except Exception:
        idx = -1
    rows = _emp.ready()
    picked = None
    if 0 <= idx < len(rows):
        picked = rows[idx]
    if picked is None:
        for _arg in ("title", "key", "value"):
            _t = (request.args.get(_arg) or "").strip()
            if _t:
                picked = _emp.by_title(_t) or None       # терпимо к кавычкам и регистру
                if picked:
                    break
    if picked is None:
        # Название написано руками — организации нет в пуле. Возвращаем ключи
        # переменных, чтобы интерфейс сохранил ручной текст в заявку.
        _keys = {}
        try:
            _want2 = {"company_name_in_quotes", "employer_name", "company_registered_address",
                      "company_inn", "company_kpp", "company_ogrn"}
            for _g in pool.build_pool(app_id, include_service=True):
                for _n in (_g.get("names") or {}).values():
                    if _n in _want2 and _n not in _keys:
                        _keys[_n] = _g.get("key")
        except Exception:
            pass
        _text = ""
        for _a in ("title", "key", "value"):
            _text = (request.args.get(_a) or "").strip()
            if _text:
                break
        return jsonify({"ok": True, "custom": True, "keys": _keys,
                        "values": {"company_name_in_quotes": _text}})
    legal = (picked.get("legal_name") or picked.get("name") or "").strip()
    name = (picked.get("name") or legal).strip()
    # Ключи переменных в панели заявки — групповые (own:<шаблон>:<слаг>), поэтому
    # интерфейсу отдаём их вместе со значениями: без этого выбор организации не
    # сохранялся в заявку и при пересборке документ возвращался к прежней компании.
    keys = {}
    try:
        _want = {"company_name_in_quotes", "employer_name", "company_registered_address",
                 "company_inn", "company_kpp", "company_ogrn"}
        for _g in pool.build_pool(app_id, include_service=True):
            _names = [v for v in (_g.get("names") or {}).values()]
            for _n in _names:
                if _n in _want and _n not in keys:
                    keys[_n] = _g.get("key")
    except Exception:
        pass
    return jsonify({"ok": True, "keys": keys, "values": {
        "company_name_in_quotes": name,
        "employer_name": legal,
        "company_registered_address": (picked.get("address") or "").strip(),
        "company_inn": (picked.get("inn") or "").strip(),
        "company_kpp": (picked.get("kpp") or "").strip(),
        "company_ogrn": (picked.get("ogrn") or "").strip(),
    }})


@bp.route("/applications/<int:app_id>/review/employer_apply", methods=["POST"])
def app_review_employer_apply(app_id):
    """Применить организацию: одна компания = вся группа её переменных.

    Договор говорит об организации в пяти местах: название в шапке, юридическое
    название в тексте, название в кавычках ниже, юридический адрес и ИНН/КПП/ОГРН
    в абзаце и в подвале. Поэтому выбор компании меняет ВСЕ связанные величины
    сразу (они логически одна сущность), а не только название в шапке.
    """
    from services import employer_pool as _emp
    title = (request.form.get("title") or request.form.get("key") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "не указана организация"}), 400
    org = _emp.by_any(title)
    values = _emp.values_of(org) if org else {"company_name_in_quotes": title}
    # ключи переменных в панели заявки групповые (own:<шаблон>:<слаг>) — ищем группу
    # по имени переменной, иначе значение просто некуда записать.
    by_name = {}
    try:
        for _g in pool.build_pool(app_id, include_service=True):
            for _n in (_g.get("names") or {}).values():
                by_name.setdefault(_n, _g.get("key"))
    except Exception:
        pass
    keys, touched = {}, set()
    for name, val in values.items():
        key = by_name.get(name)
        if not key:
            continue
        keys[name] = key
        res = pool.set_value(app_id, key, val)
        for t in (res.get("touched") or []):
            touched.add(t.get("tpl"))
    return jsonify({"ok": True, "values": values, "keys": keys,
                    "docs_updated": len(touched),
                    "source": "архив" if org else "своё название"})


@bp.route("/applications/<int:app_id>/review/scratch", methods=["POST"])
def app_review_scratch(app_id):
    """Собрать описание резюме «с нуля» по профессии (результат запоминается)."""
    key = (request.form.get("key") or "").strip()
    profession = (request.form.get("profession") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "не указано поле"}), 400
    return jsonify(pool.gen_scratch(app_id, key, profession=profession))


@bp.route("/applications/<int:app_id>/review/profession_add", methods=["POST"])
def app_review_profession_add(app_id):
    """Профессия, которой нет в справочнике: администратор вписал её руками."""
    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "впишите название профессии"}), 400
    return jsonify(pool.add_profession(title))


@bp.route("/applications/<int:app_id>/review/statuses")
def app_review_statuses(app_id):
    """Текущее состояние документов заявки: нужно плиткам и счётчику."""
    import json as _json
    rows = db.q(
        "SELECT template_id, status FROM application_documents "
        "WHERE application_id=? ORDER BY id",
        (app_id,),
    ) or []
    out = {}
    for r in rows:
        out[str(r.get("template_id"))] = r.get("status") or ""
    checked = sum(1 for v in out.values() if v in ("verified", "rejected"))
    return _json.dumps({
        "ok": True,
        "statuses": out,
        "ready": checked,
        "total": len(out),
        "can_send": bool(out) and checked == len(out),
    }, ensure_ascii=False), 200, {"Content-Type": "application/json; charset=utf-8"}


@bp.route("/applications/<int:app_id>/review/file-vars")
def app_review_file_vars(app_id):
    """Какие переменные заявки взяты из этого входящего документа.

    Читаем текст документа клиента (со скана — распознаванием) и ищем в нём
    значения переменных: что нашлось, то и подставлено из этого документа.
    """
    import re
    name = (request.args.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return jsonify({"ok": False, "error": "не указан файл"}), 400
    a = db.application_get(app_id)
    if not a or not a.get("client_id"):
        return jsonify({"ok": False, "error": "заявка не найдена"}), 404
    root = (Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % a["client_id"])).resolve()
    target = (root / name).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return jsonify({"ok": False, "error": "файл не найден"}), 404

    text = ""
    try:
        from services.doc_read import read_text
        text = read_text(target) or ""
    except Exception as e:
        log.warning("не удалось прочитать документ %s: %s", name, str(e)[:120])

    def norm(s: str) -> str:
        return re.sub(r"[^0-9a-zа-я]+", "", (s or "").lower())

    flat = norm(text)
    found, checked = [], 0
    if len(flat) > 20:
        for g in pool.build_pool(app_id):
            raw = str(g.get("value") or "")
            val = norm(raw)
            if len(val) < 4:
                continue
            checked += 1
            hit = val in flat
            if not hit:
                # Скан читается с ошибками: сверяем по словам — если в документе
                # нашлась большая часть значения, считаем его взятым отсюда.
                words = [w for w in re.split(r"[^0-9A-Za-zА-Яа-я]+", raw) if len(w) >= 4]
                if len(words) >= 2:
                    got = sum(1 for w in words if norm(w) in flat)
                    hit = got >= max(2, int(len(words) * 0.6))
            if hit:
                found.extend(list(g["names"].values()))
    return jsonify({"ok": True, "file": name, "vars": sorted(set(found)),
                    "checked": checked, "text_len": len(text)})


@bp.route("/applications/<int:app_id>/review/rebuild", methods=["POST"])
def app_review_rebuild(app_id):
    """Пересобрать все документы заявки по правилам — даже уже готовые.

    Нужно, чтобы любую заявку, включая архивную, можно было открыть и увидеть
    документы такими, какими они должны быть сейчас.
    """
    from services import autofill
    started = autofill.build_all_async(app_id)
    return jsonify({"ok": True, "started": started})


@bp.route("/applications/<int:app_id>/review/drive", methods=["POST"])
def app_review_drive(app_id):
    """Прикрепить к заявке ссылку на папку Google Drive."""
    url = (request.form.get("url") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "ссылка должна начинаться с http"}), 400
    db.exec_sql("UPDATE applications SET gdrive_url=? WHERE id=?", (url, app_id))
    return jsonify({"ok": True, "url": url})


@bp.route("/applications/<int:app_id>/review/options")
def app_review_options(app_id):
    """Варианты значения для поля: прошлые значения и примеры из шаблона."""
    key = (request.args.get("key") or "").strip()
    return jsonify({"ok": True, "options": pool.history_options(app_id, key)})


@bp.before_app_request
def _old_app_screen_redirect():
    """Старый экран заявки заменён новым: держим один вид, без развилки.

    Ссылки из истории, карточки и бота теперь ведут на /review, но старые
    закладки тоже должны открывать рабочий экран, а не позавчерашнюю вёрстку.
    """
    import re as _re
    from flask import redirect, request
    m = _re.match(r"^/applications/(\d+)/view/?$", request.path or "")
    if m:
        qs = ("?" + request.query_string.decode()) if request.query_string else ""
        return redirect("/applications/%s/review%s" % (m.group(1), qs), code=302)
    return None


@bp.route("/applications/<int:app_id>/review")
def app_review(app_id: int):
    a = db.application_get(app_id)
    if not a:
        flash("Заявка не найдена", "error")
        return redirect(url_for("dashboard.page"))

    client = db.client_get(a["client_id"]) if a.get("client_id") else None
    client_name = _client_display(a, client)
    files = _client_files(a["client_id"]) if a.get("client_id") else []

    docs = db.q(
        "SELECT id, template_id, status, pdf_path, rendered_at, error FROM application_documents "
        "WHERE application_id=? ORDER BY id",
        (app_id,),
    ) or []

    # Старая заявка могла получить оба варианта письма (Ngurah Rai и Denpasar).
    # При открытии карточки приводим комплект в порядок: остаётся тот, что
    # соответствует адресу проживания клиента (Badung → Ngurah Rai, иначе Denpasar).
    try:
        from services import immigration_office as _io
        if _io.apply_pair_rule(app_id).get("marked"):
            docs = db.q(
                "SELECT id, template_id, status, pdf_path, rendered_at, error FROM application_documents "
                "WHERE application_id=? ORDER BY id",
                (app_id,),
            ) or []
    except Exception:
        pass

    picked = request.args.get("tpl", type=int)
    tpl_ids = [d.get("template_id") for d in docs if d.get("template_id")]
    if picked not in tpl_ids:
        picked = tpl_ids[0] if tpl_ids else None

    checked = sum(1 for d in docs if (d.get("status") or "") in ("verified", "rejected"))
    can_send = bool(docs) and checked == len(docs)

    # Ссылка на папку заявки на Google Drive. У архивных заявок своей ссылки
    # обычно нет — показываем папку клиента и даём прикрепить ссылку заявки.
    drive_url = (a.get("gdrive_url") or "").strip()
    client_drive = ""
    try:
        _cl = db.client_get(a["client_id"]) if a.get("client_id") else None
        client_drive = ((_cl or {}).get("gdrive_folder_url") or "").strip()
    except Exception:
        client_drive = ""
    # Логотип Google Диска — узнаваемая кнопка перехода в папку клиента
    # Значок разбора: логотип Диска и стрелка — «забираем документы с Диска»
    drive_dl_icon = ('<svg width="20" height="15" viewBox="0 0 22 15" aria-hidden="true">'
                     '<path d="M5.3 1h5.4l5.3 9.2h-5.4z" fill="#FFCF63"/>'
                     '<path d="M5.3 1 0 10.2l2.7 4.6L8 5.6z" fill="#11A861"/>'
                     '<path d="M2.7 14.8h10.6L16 10.2H5.4z" fill="#2684FC"/>'
                     '<path d="M18.6 1v7.2M15.8 5.6l2.8 2.8 2.8-2.8" stroke="#fff" stroke-width="1.5"'
                     ' fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    gdrive_logo = ('<svg width="15" height="13" viewBox="0 0 16 14" aria-hidden="true">'
                   '<path d="M5.3 0h5.4l5.3 9.2h-5.4z" fill="#FFCF63"/>'
                   '<path d="M5.3 0 0 9.2l2.7 4.6L8 4.6z" fill="#11A861"/>'
                   '<path d="M2.7 13.8h10.6L16 9.2H5.4z" fill="#2684FC"/></svg>')
    drive_link = drive_url or client_drive
    if drive_link:
        drive_html = ('<a class="btn sm rv-drive-btn rv-drive-btn-sm" href="%s" target="_blank" rel="noopener"'
                      ' title="Папка клиента на Google Drive">%sGoogle Диск</a>'
                      % (_html.escape(drive_link, quote=True), gdrive_logo))
    else:
        drive_html = ('<input type="text" id="rv-drive-input" class="rv-drive-input"'
                      ' placeholder="вставьте ссылку на папку клиента на Google Диске">'
                      '<button type="button" class="btn sm rv-drive-btn" id="rv-drive-save">'
                      + gdrive_logo + 'Google Диск</button>')

    # Всё, что нужно шапке: собранные переменные, сколько заполнено и разобраны
    # ли документы клиента. Считаем до отрисовки, чтобы значки кнопок были верные.
    # Если у заявки ещё нет своих документов — заводим их по типу продукта.
    # Так открытие любой заявки (в том числе архивной) сразу даёт панель переменных.
    try:
        # Состав документов заявки сверяется с составом продукта при каждом открытии:
        # пропавший документ (например договор для мостовой визы) заводится заново
        # и больше не «теряется» из пакета.
        _added = db.ensure_product_documents(app_id)
        if _added:
            log.warning("в заявке %s восстановлены документы по продукту: %s",
                        app_id, ", ".join(_added))
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
        from services import drive as _drive
        _cid = a.get("client_id")
        _st = _drive.status(app_id) or {}
        scan_files = len(_drive.docs_for_client(_cid)) if _cid else 0
        if (_st.get("status") or "") == "ok" and (_st.get("total") or 0) > 0 \
                and (_st.get("done") or 0) >= (_st.get("total") or 0):
            scan_done = "1"
        elif (_st.get("status") or "") == "running":
            scan_note = "идёт разбор документов…"
        else:
            scan_note = (_st.get("note") or "документы с Google Диска ещё не разобраны")
    except Exception:
        scan_done = "0"

    # Продукты для смены типа заявки: список статический, из пакетов документов.
    # У каждого продукта видно, сколько документов он требует.
    products = []
    try:
        products = db.q(
            "SELECT p.id, p.name, COUNT(pd.template_id) AS docs "
            "FROM products p LEFT JOIN product_documents pd ON pd.product_id = p.id "
            "WHERE COALESCE(p.active, 1) = 1 GROUP BY p.id ORDER BY p.id"
        ) or []
    except Exception:
        products = []
    cur_product = a.get("product_id")
    # Продукт, который был в самой заявке (из сообщения менеджера). Именно он
    # подсвечен жёлтым и остаётся на месте, даже если продукт поменяли вручную.
    req_product = cur_product
    try:
        from services import requested_product as _reqp
        _rq = _reqp.for_app(a)
        if _rq:
            req_product = _rq
    except Exception:
        req_product = cur_product
    # Список продуктов: строка того продукта, что стоит в заявке, подсвечена
    # жёлтым внутри списка — при выборе другого видно, чем он отличается.
    product_options = "".join(
        '<button type="button" class="rv-opt%s" data-value="%s">'
        '<span class="rv-opt-name">%s</span>'
        '<span class="rv-opt-docs">документов: %s</span>%s%s</button>' % (
            " is-current" if str(pr.get("id")) == str(req_product) else "",
            pr.get("id"),
            _html.escape(str(pr.get("name") or "продукт")),
            pr.get("docs") or 0,
            '<span class="rv-opt-tag">нужен по заявке</span>'
            if str(pr.get("id")) == str(req_product) else "",
            ('' if str(pr.get("id")) == str(req_product)
             else ('<span class="rv-opt-tag is-cur">стоит сейчас</span>'
                   if str(pr.get("id")) == str(cur_product) else "")),
        )
        for pr in products
    )
    cur_product_name = next((str(pr.get("name") or "") for pr in products
                             if str(pr.get("id")) == str(cur_product)), "продукт не указан")
    # Название продукта из заявки: в карточке заявки показываем именно его,
    # а ручную правку менеджера — отдельной пометкой.
    req_product_name = next((str(pr.get("name") or "") for pr in products
                             if str(pr.get("id")) == str(req_product)), cur_product_name)
    _prod_row = _html.escape(req_product_name or "—")
    if str(cur_product) != str(req_product):
        _prod_row += (' <span class="rv-prod-note">менеджер поставил: %s</span>'
                      % _html.escape(cur_product_name or "—"))
    cur_docs = next((pr.get("docs") or 0 for pr in products
                     if str(pr.get("id")) == str(cur_product)), 0)
    scan_note_cls = " is-warn" if scan_note else ""

    # ── Шапка заявки: кто, когда, по какому продукту, комментарий менеджера ──
    # Кто прислал заявку — из Telegram-справочника менеджеров
    _who = ""
    try:
        _bm = db.q1("SELECT full_name, username FROM bot_managers WHERE id=?",
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
        from datetime import datetime as _dt
        _c = _dt.strptime(str(a.get("created_at"))[:19], "%Y-%m-%d %H:%M:%S")
        _when_txt = _c.strftime("%d.%m.%Y, %H:%M")
        _days = (_dt.now() - _c).days
        _ago = "сегодня" if _days == 0 else ("вчера" if _days == 1 else "%d дн. назад" % _days)
    except Exception:
        pass
    # Состав продукта одной строкой: код, срок, цена, сколько документов
    _prod_info = ""
    try:
        _pr = next((pr for pr in products if str(pr.get("id")) == str(cur_product)), None)
        if _pr:
            _pr_desc = str(_pr.get("description") or "")
            _price = ""
            import re as _re
            _m = _re.search(r"price_idr=(\d+)", _pr_desc)
            if _m:
                try:
                    _price = " · {:,.0f}".format(int(_m.group(1))).replace(",", " ") + " IDR"
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
        "full_name": "ФИО", "surname": "Фамилия", "name": "Имя",
        "full_name_latin": "ФИО латиницей", "birth_date": "Дата рождения",
        "birth_place": "Место рождения", "citizenship": "Гражданство",
        "passport_no": "Паспорт", "passport_issued": "Паспорт выдан",
        "passport_expiry": "Паспорт действует до", "phone": "Телефон", "email": "Email",
        "telegram": "Telegram", "username": "Ник в Telegram",
        "address_live": "Адрес проживания", "address_reg": "Адрес регистрации",
        "city": "Город", "country": "Страна", "product_name": "Продукт в заявке",
        "price_idr": "Стоимость, IDR", "gdrive_folder_url": "Папка на Google Диске",
        "notes": "Пометки менеджера", "comment": "Комментарий",
    }
    _raw_order = ["full_name", "surname", "name", "full_name_latin", "birth_date",
                  "birth_place", "citizenship", "passport_no", "passport_issued",
                  "passport_expiry", "phone", "email", "telegram", "username",
                  "address_live", "address_reg", "city", "country", "product_name",
                  "price_idr", "gdrive_folder_url", "notes", "comment"]
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
                _v = "{:,}".format(int(float(_v))).replace(",", " ")
            except Exception:
                pass
        _raw_rows.append('<tr><td>%s</td><td>%s</td></tr>'
                         % (_lbl, _html.escape(_v[:400])))
    _tg_panel = f"""
<div class="rv-tg-panel" id="rv-tg-panel" hidden>
  <div class="rv-tg-head">
    <b>Заявка #{app_id} · {_when_txt}{(' · ' + _who) if _who else ''}</b>
    <button type="button" class="rv-tg-x" id="rv-tg-close" title="Закрыть (Esc)">✕</button>
  </div>
  <div class="rv-tg-body">
    {('<div class="rv-tg-cmt"><span class="rv-tg-q">Комментарий менеджера</span>' + _html.escape(_cmt) + '</div>') if _cmt else ''}
    <div class="rv-tg-cap">Что указано в заявке</div>
    <table class="rv-tg-table">{''.join(_raw_rows) or '<tr><td colspan="2">Поля не заполнены</td></tr>'}</table>
    <div class="rv-tg-brief">
      <div class="rv-tg-cap">Комментарий для сборки документов</div>
      <textarea id="rv-tg-brief" rows="3" spellcheck="false"
        placeholder="Например: Должность: артист-продюсер (Artist / Producer). Сфера: кинопроизводство"></textarea>
      <div class="rv-tg-briefrow">
        <button type="button" class="btn sm" id="rv-tg-brief-save">Сохранить и пересобрать</button>
        <span class="rv-spin" id="rv-tg-brief-spin" hidden title="пересобираю документы"></span>
        <span class="rv-brief-timer" id="rv-tg-brief-timer" hidden>0 сек</span>
        <button type="button" class="rv-brief-close" id="rv-tg-brief-close" hidden>Закрыть окно</button>
        <span class="rv-tg-briefnote" id="rv-tg-brief-note"></span>
      </div>
    </div>
  </div>
</div>
<div class="rv-tg-back" id="rv-tg-back" hidden></div>
"""

    # Согласование документа, который открыт в конструкторе: те же квадратики,
    # что были в окне просмотра — теперь живут в шапке заявки.
    _dstat = next((d.get("status") for d in docs if d.get("template_id") == picked), "")
    doc_verdict = ""
    if picked:
        doc_verdict = (
            '<button type="button" class="btn sm rv-mark%s" data-tpl="%s" data-verdict="verify"'
            ' title="Документ заполнен верно">✓ Документ верен</button>'
            '<button type="button" class="btn sm rv-mark%s" data-tpl="%s" data-verdict="reject"'
            ' title="Документ не нужен в этой заявке">✕ Не нужен</button>'
            % (" is-on" if _dstat == "verified" else "", picked,
               " is-on" if _dstat == "rejected" else "", picked))
        if _dstat:
            doc_verdict += ('<span class="rv-doc-state">%s</span>'
                            % _html.escape(_doc_status_label(_dstat)))

    # Строка состояния разбора нужна только когда в ней есть что сказать:
    # пустая строка-заглушка добавляла шапке лишнюю высоту.
    scan_line = (f'<div class="rv-scan-note{scan_note_cls}" id="rv-scan-note">{scan_note}</div>'
                 if (scan_note or '').strip() else '')

    # Город обслуживания иммиграции по адресу клиента: администратор сразу видит,
    # какой комплект писем уходит и почему второй вариант исключён.
    _office_row = ""
    _office_bar = ""
    try:
        from services import immigration_office as _io
        _office_ctx = _io.resolve_for_app(app_id)
    except Exception:
        _office_ctx = {}
    _client_addr = ""
    if client:
        _client_addr = str(client.get("address_live") or client.get("address_reg") or "").strip()
    if _office_ctx.get("office"):
        _off, _why = _office_ctx["office"], (_office_ctx.get("why") or "")
        _off_name = _io.office_name(_off)
        _num_keep = 14 if _off == "denpasar" else 12
        _off_drop = "Ngurah Rai" if _off == "denpasar" else "Denpasar"
        _num_drop = 12 if _off == "denpasar" else 14
        _office_row = (
            '<div class="rv-row"><span class="rv-k">Адрес проживания</span>'
            '<span class="rv-v">%s <b style="color:#15803D;white-space:nowrap">→ %s</b></span></div>'
            '<div class="rv-row"><span class="rv-k">Комплект писем</span>'
            '<span class="rv-v">№%s (%s)'
            '<span style="color:#8A6100"> · №%s (%s) исключено — %s</span></span></div>'
            % (_html.escape(_client_addr[:220]), _off_name,
               _num_keep, _off_name, _num_drop, _off_drop, _html.escape(_why)))
        # Та же подпись — в шапке заявки: администратор видит город и судьбу
        # письма-двойника, не открывая вкладки.
        _office_bar = (
            '<div class="rv-office-bar" style="font-size:12.5px;color:#3F5B4A;'
            'background:#F2FAF5;border:1px solid #DCEEE2;border-radius:8px;'
            'padding:6px 10px;margin-top:6px">'
            'Адрес: %s <b style="color:#15803D;white-space:nowrap">→ %s</b>'
            '<span style="color:#8A6100"> · в комплект идёт письмо №%s (%s), '
            '№%s (%s) исключено — %s</span></div>'
            % (_html.escape(_client_addr[:200]), _off_name,
               _num_keep, _off_name, _num_drop, _off_drop, _html.escape(_why)))
    elif _office_ctx.get("why"):
        _office_row = (
            '<div class="rv-row"><span class="rv-k">Комплект писем</span>'
            '<span class="rv-v" style="color:#8A6100">не определён — %s '
            '(оставлены оба варианта, выберите вручную)</span></div>'
            % _html.escape(_office_ctx["why"]))
        _office_bar = (
            '<div class="rv-office-bar" style="font-size:12.5px;color:#8A6100;'
            'background:#FFF8E8;border:1px solid #F3E2B8;border-radius:8px;'
            'padding:6px 10px;margin-top:6px">'
            'Комплект писем не определён — %s. Оставлены оба варианта, '
            'выберите вручную.</div>' % _html.escape(_office_ctx["why"]))

    head = f"""
<div class="rv-head">
  <div class="rv-h1">
    <span class="rv-lead">
      <span class="rv-title">Заявка #{app_id}</span>
      {marks.badge(a.get("created_at") or "")}
      {('<span class="rv-client">' + _html.escape(client_name) + '</span>') if client_name else ''}
      <span class="rv-when">от {_when_txt}{(' · ' + _ago) if _ago else ''}</span>
    </span>
    {('<button type="button" class="rv-cmt' + _cmt_cls + '" id="rv-cmt-btn" title="Показать комментарий полностью">⚠ ' + _html.escape(_cmt[:200]) + ('…' if len(_cmt) > 200 else '') + '</button>') if _cmt else ''}
  </div>
  <div class="rv-h2">
    <span class="rv-h2-left">
      <button type="button" class="btn sm rv-tg-btn" id="rv-tg-open" title="Показать всё, что было в заявке из Telegram">Текст заявки</button>
      <div class="rv-select" id="rv-product" data-value="{cur_product}">
        <button type="button" class="rv-select-btn" id="rv-product-btn"
                title="От типа продукта зависят документы и переменные заявки">
          <span id="rv-product-cur">{cur_product_name}</span>
          <span class="rv-select-caret" aria-hidden="true">▾</span>
        </button>
        <script>window.RV_REQ_PID={req_product or 0};</script>
        <div class="rv-select-list" id="rv-product-list" hidden>{product_options}</div>
      </div>
      {('<span class="rv-prod-info">' + _prod_info + '</span>') if _prod_info else ''}
    </span>
    <span class="rv-h2-right">
      <button type="button" class="btn sm rv-photo-btn" id="rv-photo-btn"
              title="Фоторедактор: кадрирование фото клиента для документов с фотографией">Фоторедактор</button>
      <span class="rv-drive-box" id="rv-drive-box">{drive_html}</span>
      <button type="button" class="btn sm rv-ready-btn" id="rv-ready-btn" title="Все подтверждённые документы: контрольная проверка и отправка на Google Диск">Готовые доки</button>
      <span class="rv-who">{('от ' + _html.escape(_who)) if _who else _status_label(a.get('status'))}</span>
      <button type="button" class="btn ghost rv-vars-btn" id="rv-vars-btn">Переменные значения ({filled_n})</button>
    </span>
  </div>
  {scan_line}
  {_office_bar}
</div>
{_tg_panel}
{_ready_modal_html(app_id)}
<div id="rv-photo-modal" hidden style="position:fixed;inset:0;z-index:9000;background:rgba(4,32,30,.5);display:none;align-items:center;justify-content:center;padding:18px">
  <div style="background:#fff;border-radius:14px;max-width:520px;width:100%;padding:16px 18px;box-shadow:0 18px 60px rgba(0,0,0,.35)">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <b style="font-size:15px">Фото клиента для документов</b>
      <button type="button" id="rv-photo-close" style="border:0;background:transparent;font-size:18px;cursor:pointer">✕</button>
    </div>
    <div style="display:flex;gap:16px;margin-top:12px;align-items:flex-start;flex-wrap:wrap">
      <img id="rv-photo-prev" alt="Предпросмотр фото" style="width:150px;height:210px;object-fit:cover;border:1px solid #E4EDE7;border-radius:8px;background:#F4FAF6">
      <div style="flex:1;min-width:220px;display:flex;flex-direction:column;gap:10px">
        <label style="font-size:13px;color:#42574A">Сдвиг кадра по вертикали
          <input type="range" id="rv-photo-y" min="0" max="1" step="0.01" value="0.35" style="width:100%">
        </label>
        <label style="font-size:13px;color:#42574A">Увеличение
          <input type="range" id="rv-photo-z" min="1" max="2.5" step="0.01" value="1" style="width:100%">
        </label>
        <div id="rv-photo-note" style="font-size:12.5px;color:#6B7C70">Двигайте ползунки — кадр обновляется сразу.</div>
        <button type="button" class="btn" id="rv-photo-save">Сохранить в документ</button>
      </div>
    </div>
  </div>
</div>
<script>
(function(){{
  var appId = {app_id};
  var btn=document.getElementById('rv-photo-btn'), mod=document.getElementById('rv-photo-modal');
  if(!btn||!mod) return;
  var img=document.getElementById('rv-photo-prev'), ry=document.getElementById('rv-photo-y'),
      rz=document.getElementById('rv-photo-z'), note=document.getElementById('rv-photo-note'),
      save=document.getElementById('rv-photo-save'), x=document.getElementById('rv-photo-close');
  var url='/applications/'+appId+'/photo-crop', timer=null;
  /* hidden не срабатывает при inline display:flex — управляем показом явно. */
  function show(v){{ mod.hidden=!v; mod.style.display = v ? 'flex' : 'none'; }}
  show(false);
  function load(){{
    fetch(url, {{headers:{{'X-Requested-With':'fetch'}}}}).then(function(r){{ return r.json(); }}).then(function(j){{
      if(!j.ok){{ note.textContent=j.error||'Не удалось открыть настройки'; return; }}
      if(j.preview) img.src=j.preview;
      if(typeof j.crop_y==='number') ry.value=j.crop_y;
      if(typeof j.zoom==='number') rz.value=j.zoom;
      note.textContent = j['есть_фото'] ? 'Двигайте ползунки — кадр обновляется сразу.' : 'Фото клиента в папке не найдено.';
    }}).catch(function(){{ note.textContent='Сервис недоступен'; }});
  }}
  function save_crop(msgOk){{
    var body={{crop_y: parseFloat(ry.value), zoom: parseFloat(rz.value)}};
    return fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json','X-Requested-With':'fetch'}}, body:JSON.stringify(body)}})
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
      return fetch('/applications/'+appId+'/review/regen', {{method:'POST', headers:{{'X-Requested-With':'fetch'}}}})
        .then(function(){{ note.textContent='Готово: кадр сохранён, документы пересобраны.'; setTimeout(function(){{ location.reload(); }}, 900); }})
        .catch(function(){{ note.textContent='Кадр сохранён, но пересборку запустить не удалось.'; }});
    }});
  }});
}})();
</script>
<script>
(function(){{
  var open=document.getElementById('rv-tg-open'), panel=document.getElementById('rv-tg-panel');
  var back=document.getElementById('rv-tg-back'), x=document.getElementById('rv-tg-close');
  if(!open || !panel) return;
  function show(v){{ panel.hidden=!v; if(back) back.hidden=!v; if(v) panel.scrollTop=0; }}
  open.addEventListener('click', function(){{ show(panel.hidden); }});
  if(x) x.addEventListener('click', function(){{ show(false); }});
  if(back) back.addEventListener('click', function(){{ show(false); }});
  document.addEventListener('keydown', function(e){{ if(e.key==='Escape' && !panel.hidden) show(false); }});
  var c=document.getElementById('rv-cmt-btn');
  if(c) c.addEventListener('click', function(){{ show(true); }});

  /* Комментарий для сборки документов: сохранить и пересобрать всю заявку.
     Правка комментария меняет должность (резюме, договор) и организацию по сфере. */
  var ta=document.getElementById('rv-tg-brief'), sBtn=document.getElementById('rv-tg-brief-save'),
      sNote=document.getElementById('rv-tg-brief-note'),
      sSpin=document.getElementById('rv-tg-brief-spin'),
      sTimer=document.getElementById('rv-tg-brief-timer'),
      sClose=document.getElementById('rv-tg-brief-close'),
      BKEY='wolf_brief_' + APP_ID;
  var tick=null, t0=0;
  function briefDraft(v){{ try{{ if(v===undefined) return localStorage.getItem(BKEY)||''; localStorage.setItem(BKEY, v); }}catch(e){{}} return ''; }}
  function timerOn(){{
    t0=Date.now();
    if(sTimer){{ sTimer.hidden=false; sTimer.textContent='0 сек'; }}
    if(tick) clearInterval(tick);
    tick=setInterval(function(){{
      var s=Math.round((Date.now()-t0)/1000);
      if(sTimer) sTimer.textContent=(s<60 ? s+' сек' : Math.floor(s/60)+' мин '+(s%60)+' сек');
    }}, 500);
  }}
  function timerOff(){{
    if(tick){{ clearInterval(tick); tick=null; }}
    if(sTimer) sTimer.hidden=true;
    if(sSpin) sSpin.hidden=true;
    if(sClose) sClose.hidden=true;
  }}
  function briefLoad(){{
    if(!ta) return;
    fetch('/applications/' + APP_ID + '/brief', {{credentials:'same-origin',
          headers:{{'X-Requested-With':'fetch'}}}})
      .then(function(r){{ return r.json(); }})
      .then(function(d){{
        if(!d || !d.ok) return;
        var srv=d.brief || '', draft=briefDraft();
        if(draft && draft !== srv){{
          /* В окне писали, но обновление страницы случилось до сохранения —
             возвращаем черновик и говорим об этом прямо. */
          ta.value=draft; ta.setAttribute('data-touched','1');
          if(sNote){{ sNote.textContent='Черновик восстановлен — нажмите «Сохранить и пересобрать»';
                     sNote.className='rv-tg-briefnote'; }}
        }} else {{
          ta.value=srv;
          if(draft && draft === srv) ta.setAttribute('data-touched','1');
        }}
      }})
      .catch(function(){{}});
  }}
  if(ta) ta.addEventListener('input', function(){{ ta.setAttribute('data-touched','1'); briefDraft(ta.value); }});
  if(sClose) sClose.addEventListener('click', function(){{ show(false); }});
  if(sBtn) sBtn.addEventListener('click', function(){{
    sBtn.disabled=true;
    if(sSpin) sSpin.hidden=false;
    if(sClose) sClose.hidden=false;
    timerOn();
    var _lbl=sBtn.textContent; sBtn.textContent='Пересобираю…';
    if(sNote){{ sNote.textContent='Сохраняю комментарий и пересобираю документы. Окно можно закрыть — сборка продолжится.'; sNote.className='rv-tg-briefnote'; }}
    fetch('/applications/' + APP_ID + '/brief', {{method:'POST', credentials:'same-origin',
          headers:{{'Content-Type':'application/json','X-Requested-With':'fetch'}},
          body: JSON.stringify({{brief: ta ? ta.value : ''}})}})
      .then(function(r){{ return r.json(); }})
      .then(function(d){{
        sBtn.disabled=false; sBtn.textContent=_lbl; timerOff();
        if(!d || !d.ok){{ if(sNote){{ sNote.textContent='Не сохранилось'; sNote.className='rv-tg-briefnote err'; }} return; }}
        var n=(d.rebuilt||[]).length, bad=(d.findings||[]).length;
        if(sNote){{
          sNote.textContent='Пересобрано документов: ' + n + (bad ? ' · замечаний проверки: ' + bad : ' · замечаний нет');
          sNote.className='rv-tg-briefnote ok';
        }}
        ta.setAttribute('data-touched','1');
        briefDraft(ta ? ta.value : '');
      }})
      .catch(function(){{ sBtn.disabled=false; sBtn.textContent=_lbl; timerOff();
        if(sNote){{ sNote.textContent='Ошибка сети'; sNote.className='rv-tg-briefnote err'; }} }});
  }});
  briefLoad();

  /* Общая опора двух строк шапки. Комментарий в верхней строке и кнопка
     «Google Диск» в нижней должны начинаться с одного места — от конца
     выпадающего списка продуктов плюс небольшой отступ. Считаем по факту:
     ширина списка зависит от названия продукта и от размера окна. */
  var _head=document.querySelector('.rv-head');
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
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(alignSplit);
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
            return ('<img src="/applications/%s/file-thumb?name=%s" alt="%s" loading="lazy">'
                    % (app_id, url_quote(name), _html.escape(name, quote=True)))
        if ext in (".pdf",):
            # PDF показываем отрисованной страницей: встроенный просмотрщик
            # браузера открывает файл не всегда, картинка работает везде.
            return ('<img src="/applications/%s/file-thumb?name=%s" alt="%s" loading="lazy">'
                    % (app_id, url_quote(name), _html.escape(name, quote=True)))
        if ext in (".heic", ".heif"):
            twin = name.rsplit(".", 1)[0] + ".photo.png"
            # Браузер не показывает HEIC — для плитки берём сконвертированную копию.
            # Копии нет в отфильтрованном списке, поэтому ищем по исходному.
            if any(f["name"] == twin for f in all_files):
                return ('<img src="/applications/%s/file-thumb?name=%s" alt="%s" loading="lazy">'
                        % (app_id, url_quote(twin), _html.escape(twin, quote=True)))
            return '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:30px">🖼️</div>'
        return '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:30px">📄</div>'

    files_html = "".join(
        '<div class="rv-thumb rv-file-thumb" data-file="%s" data-page="%s">'
        '<div class="rv-thumb-frame is-loading">%s<span class="rv-spinner"></span></div>'
        '<div class="rv-thumb-cap"><span class="rv-thumb-name">%s</span>'
        '<span class="rv-thumb-status">%s</span></div></div>'
        % (_html.escape(f["name"], quote=True),
           ('/applications/%s/file-page?name=%s' % (app_id, url_quote(f["name"])))
           if f["ext"] == ".pdf" else "",
           _preview_of(f["name"], f["ext"]),
           _html.escape(f["name"][:34]),
           _human_size(f["size"]))
        for f in files
    ) or '<div class="rv-empty">Файлы клиента в локальном кэше не найдены</div>'

    drive_link = (('<a href="%s" target="_blank" rel="noopener">папка заявки на Google Drive</a>'
                   % a.get("gdrive_url")) if a.get("gdrive_url") else "ссылка не указана")

    pane_src = f"""
  <div class="rv-pane is-on" id="pane-src">
    <div class="rv-body">
      <p class="rv-sec">Документы клиента ({len(files)}) — нажмите плитку, документ откроется в окне справа</p>
      <div class="rv-thumbs" id="rv-file-thumbs">{files_html}</div>
      <div class="rv-note" style="margin-top:10px">Нажмите плитку — документ откроется в центральном окне.
        Справа останутся переменные, которые из него вытащены.</div>

      <p class="rv-sec" style="margin-top:16px">Карточка заявки</p>
      <div class="rv-row"><span class="rv-k">Клиент</span><span class="rv-v">{client_name}</span></div>
      {_office_row}
      <div class="rv-row"><span class="rv-k">Продукт</span><span class="rv-v rv-mark-yellow">{_prod_row}</span></div>
      <div class="rv-row"><span class="rv-k">Статус заявки</span><span class="rv-v">{_status_label(a.get('status'))}</span></div>
      <div class="rv-row"><span class="rv-k">Создана</span><span class="rv-v">{str(a.get('created_at') or '—')[:16]}</span></div>
      <div class="rv-row"><span class="rv-k">Взял в работу</span><span class="rv-v">{a.get('taken_login') or '—'}</span></div>
      <div class="rv-row"><span class="rv-k">Комментарий менеджера</span><span class="rv-v rv-mark-yellow">{(a.get('comment') or '—')[:400]}</span></div>
    </div>
  </div>
"""

    # ── Вкладка 3: готовые документы и визор ─────────────────────────────────
    # Плитки документов: миниатюра подгружается лениво, при открытии вкладки.
    # Клик по плитке разворачивает документ в визоре слева.
    thumbs = "".join(
        '<div class="rv-thumb%s%s%s" data-tpl="%s">'
        '<div class="rv-thumb-frame is-loading"><span class="rv-spinner"></span>'
        '<img data-src="/applications/%s/doc/%s/thumb" alt="%s" loading="lazy" width="220">'
        '<span class="rv-thumb-mark" title="%s"></span>'
        '</div>'
        '<div class="rv-thumb-cap">'
        '<span class="rv-thumb-name">%s</span>'
        '<span class="rv-thumb-status%s" id="rv-thumb-status-%s">%s</span>'
        '%s'
        '<div class="rv-thumb-tools">'
        '<button type="button" class="rv-mark%s" data-verdict="verify" data-tpl="%s">✓ Проверен</button>'
        '<button type="button" class="rv-mark%s" data-verdict="reject" data-tpl="%s">✕ Не нужен</button>'
        '</div>'
        '</div></div>'
        % (" is-on" if d.get("template_id") == picked else "",
           " is-off" if (d.get("status") or "") == "rejected" else "",
           " is-ok" if (d.get("status") or "") in ("verified", "sent") else "",
           d.get("template_id"),
           app_id, d.get("template_id"), _template_name(d.get("template_id")),
           # Метка по центру листа — отражение нажатой кнопки. Документ, исключённый
           # правилом (адрес клиента вне зоны офиса), виден затемнённым и с причиной.
           ("Отклонён: %s" % _html.escape((d.get("error") or "исключено автоматически")).strip())
           if (d.get("status") or "") == "rejected" else
           ("Проверен и зафиксирован для отправки"
            if (d.get("status") or "") in ("verified", "sent") else ""),
           _template_name(d.get("template_id")),
           " is-off" if (d.get("status") or "") == "rejected" else "",
           d.get("template_id"),
           _doc_status_label(d.get("status")),
           ('<span class="rv-thumb-why">%s</span>'
            % _html.escape((d.get("error") or "").strip()))
           if ((d.get("status") or "") == "rejected" and (d.get("error") or "").strip()) else "",
           " rv-on-ok" if (d.get("status") or "") == "verified" else "", d.get("template_id"),
           " rv-on-no" if (d.get("status") or "") == "rejected" else "", d.get("template_id"))
        for d in docs
    ) or '<div class="rv-empty">У заявки пока нет документов</div>'

    verdict_rows = "".join(
        '<div class="rv-row" data-row-tpl="%s">'
        '<span class="rv-k">%s</span>'
        '<span class="rv-v" id="rv-status-%s">%s</span>'
        '<span style="margin-left:auto;display:flex;gap:6px">'
        '<button type="button" class="btn sm rv-mark" data-verdict="verify" data-tpl="%s">✓ Проверен</button>'
        '<button type="button" class="btn sm rv-mark" data-verdict="reject" data-tpl="%s">✕ Не нужен</button>'
        '</span></div>'
        % (d.get("template_id"), _template_name(d.get("template_id")),
           d.get("template_id"), _doc_status_label(d.get("status")),
           d.get("template_id"), d.get("template_id"))
        for d in docs
    ) or '<div class="rv-empty">Согласовывать пока нечего</div>'

    pane_ready = f"""
  <div class="rv-pane" id="pane-ready">
    <div class="rv-thumbs" id="rv-thumbs">{thumbs}</div>
    <div class="rv-thumbs-bar"><span id="rv-thumbs-count">миниатюры загружаются по мере готовности</span></div>
    <div class="rv-note" style="margin:0 13px 13px">Нажмите плитку — документ откроется поверх
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
        hist_names = pool.names_with_history()
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
    sec_index = 0
    for g in pool_groups:
        sec = g.get("section") or "Переменные"
        if sec != cur_section:
            if cur_section is not None:
                fields_html.append('</div></div>')
            sec_index += 1
            fields_html.append(
                '<div class="rv-blk" data-sec="%d">'
                '<button type="button" class="rv-blk-head">'
                '<span class="rv-blk-t">%s</span>'
                '<span class="rv-blk-n">%d</span>'
                '<span class="rv-blk-arrow" aria-hidden="true">▾</span>'
                '</button><div class="rv-blk-body">'
                % (sec_index, _html.escape(sec), sec_counts.get(sec, 0)))
            cur_section = sec

        label = g["label"]
        if g["doc_count"] == 1 and g.get("value_split"):
            label = "%s · %s" % (label, g["doc_titles"][0] if g["doc_titles"] else "документ")
        docs_note = ("в %d документах" % g["doc_count"]) if g["doc_count"] > 1 \
                    else "в 1 документе"

        vars_all = ",".join(g["names"].values())
        var_first = next(iter(g["names"].values()), "")
        src = g.get("src") or "сгенерировано"
        if not g["filled"]:
            # пустое значение честно помечаем: источник появится после заполнения
            src = "не заполнено — нажмите «Заполнить автоматически»"

        # Кубик — только у значений, которые можно перевыпустить: номер документа,
        # номера справки и счёта, Ref., остаток, маска карты, адрес.
        kind = g.get("kind") or "gen"
        if kind == "gen":
            regen = ('<button type="button" class="rv-act" data-act="regen" data-key="%s"'
                     ' title="Сгенерировать значение заново">🎲</button>'
                     % _html.escape(g["key"], quote=True))
        else:
            regen = ('<span class="rv-act rv-act-off" title="Значение берётся как есть —'
                     ' перевыпускать нечего">·</span>')

        # Инструкция переменной: правило из конструктора плюс источник значения.
        rule_txt = (g.get("rule_note") or "").strip()
        info_bits = [rule_txt] if rule_txt else []
        if var_first == "doc_date":
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
                '<div class="rv-conflict">'
                '<div class="rv-conflict-head">⚠ данные в анкете отличаются</div>'
                '<select class="rv-conflict-sel" data-key="%s">'
                '<option value="doc" data-value="%s" selected>из документа (файл «%s»): %s</option>'
                '<option value="card" data-value="%s">из анкеты: %s</option>'
                '</select></div>' % (_html.escape(g["key"], quote=True),
                                     _dv, _src_name, _dv, _cv, _cv)
            )

        # Для переменных резюме администратор может выбрать профессию и собрать
        # описание автоматически — либо оставить и поправить текст вручную.
        cv_picker = ""
        # Список профессий нужен только там, где есть текст описания: имя, паспорт
        # и даты генерировать по профессии не нужно.
        CV_GEN_VARS = ("cv_summary", "cv_job1_bullets", "cv_job2_bullets", "cv_job3_bullets",
                       "cv_skills_hard", "cv_skills_soft", "cv_skills_tools",
                       "cv_education_degree", "cv_education_note", "cv_job1_title")
        if str(var_first or "") in CV_GEN_VARS:
            _ck = _html.escape(g["key"], quote=True)
            cv_picker = ('<div class="rv-cvgen">'
                         '<select class="rv-cvprof" data-key="%s" title="Профессия для описания">'
                         '<option value="">профессия…</option>'
                         '<option value="__custom__">✎ своя профессия…</option></select>'
                         '<button type="button" class="rv-cvbtn" data-key="%s"'
                         ' title="Собрать описание резюме по профессии">Собрать описание</button>'
                         '<button type="button" class="rv-cvpieces" data-key="%s"'
                         ' title="Отметить готовые фразы и собрать из них текст">Кусочки</button>'
                         '<button type="button" class="rv-cvscratch" data-key="%s"'
                         ' title="Собрать описание заново, другими словами">С нуля</button>'
                         '</div>' % (_ck, _ck, _ck, _ck))

        # У адреса клиента сразу пишем, какому иммиграционному офису он
        # принадлежит: Ngurah Rai (весь Badung) или Denpasar. От этого зависит,
        # какое письмо (12 или 14) идёт в комплект.
        city_note = ""
        if str(var_first or "") in ("address_live", "address_reg", "address"):
            try:
                from services import immigration_office as _io
                _oi = _io.resolve_for_app(app_id)
                if _oi.get("office"):
                    city_note = (' <span style="color:#15803D;font-weight:600">→ %s</span>'
                                 % _html.escape(_io.office_name(_oi["office"])))
                elif _oi.get("why"):
                    city_note = (' <span style="color:#8A6100">→ %s</span>'
                                 % _html.escape(_oi["why"]))
            except Exception:
                city_note = ""

        # Организация для договора (док. №11): выпадающий список из пула исторических
        # документов. Выбор организации меняет и название в шапке, и реквизиты в
        # подвале (адрес, ИНН, КПП, ОГРН) — они связаны и берутся из одной записи.
        emp_picker = ""
        if str(var_first or "") in ("company_name_in_quotes", "employer_name"):
            try:
                from services import employer_pool as _emp
                _opts = "".join(
                    '<option value="%d">%s%s</option>'
                    % (i["index"], _html.escape(i["title"]),
                       (" · ИНН " + i["inn"]) if i.get("inn") else "")
                    for i in _emp.titles())
            except Exception:
                _opts = ""
            if _opts:
                emp_picker = ('<div class="rv-cvgen rv-empgen">'
                              '<select class="rv-empsel" data-key="%s"'
                              ' title="Организация из исторических документов">'
                              '<option value="">организация из архива…</option>%s</select></div>'
                              % (_html.escape(g["key"], quote=True), _opts))

        fields_html.append(
            '<div class="rv-field%s" data-key="%s" data-var="%s" data-vars="%s" data-tpls="%s"'
            ' data-list="%s">'
            '<div class="rv-fname">%s%s</div>'
            '<div class="rv-fedit">'
            '<textarea class="rv-input%s" rows="1" data-key="%s" spellcheck="false"'
            ' title="Можно вписать вручную. Изменение сохраняется само.">%s</textarea>'
            '<div class="rv-acts">'
            '<button type="button" class="rv-info" data-key="%s" data-rule="%s"'
            ' title="Инструкция по переменной">i</button>%s'
            '</div></div>'
            '<div class="rv-fsrc"><span class="rv-src">%s</span>'
            '<span class="rv-docs">%s</span></div>%s%s%s'
            '</div>' % (
                conflict_cls,
                _html.escape(g["key"], quote=True),
                _html.escape(var_first, quote=True),
                _html.escape(vars_all, quote=True),
                _html.escape(",".join(str(t) for t in (g.get("templates") or [])), quote=True),
                "1" if (g.get("list_allowed")
                        and (set(g.get("names", {}).values()) & hist_names)) else "0",
                _html.escape(label),
                city_note,
                " is-empty" if not g["filled"] else "",
                _html.escape(g["key"], quote=True),
                _html.escape(str(g["value"])),
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
            from services import autofill
            autofill.build_all_async(app_id)
        except Exception:
            pass

    if cur_section is not None:
        fields_html.append('</div></div>')

    if not fields_html:
        fields_html.append('<div class="rv-empty">У заявки пока нет значений — '
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
    office_line = ""
    try:
        from services import immigration_office as _io
        _oi = _io.resolve_for_app(app_id)
        if _oi.get("office"):
            office_line = ('<div style="margin-top:6px;font-size:12px;color:#3F5B4A">'
                           'Письма в иммиграцию: <b>%s</b> — %s</div>'
                           % (_html.escape(_io.office_name(_oi["office"])),
                              _html.escape(_oi.get("why") or "")))
        else:
            office_line = ('<div style="margin-top:6px;font-size:12px;color:#8A6100">'
                           'Комплект писем не определён — %s</div>'
                           % _html.escape(_oi.get("why") or "адрес не распознан"))
    except Exception:
        office_line = ""

    right = f"""
<div class="rv-panel rv-right" id="rv-right">
  <div class="rv-body">
    <div class="rv-phead">
      <div class="rv-phead-top">
        <div class="rv-stage"><span class="rv-num">2</span>Переменные и значения</div>
        <button type="button" class="rv-close-mobile" id="rv-right-close">Свернуть ✕</button>
      </div>
      <div class="rv-progress{progress_cls}" id="rv-progress">
        <span id="rv-progress-text">{progress_text}</span>
        <button type="button" class="rv-collapse-all" id="rv-collapse-all"
                title="Свернуть все блоки">Свернуть блоки</button>
      </div>
      {office_line}
      <div class="rv-filter-note" id="rv-panel-count"></div>
    </div>
    {''.join(fields_html)}
  </div>
</div>
"""

    # ── Низ: согласование и отправка ─────────────────────────────────────────
    foot = f"""
<div class="rv-foot">
  <div class="rv-state {'ok' if can_send else 'warn'}">
    {'✅ Все документы согласованы — можно отправлять' if can_send
     else '⛔ Отправить нельзя: согласовано %d из %d документов' % (checked, len(docs))}
  </div>
  <form method="post" action="/applications/{app_id}/send" class="rv-send"
        onsubmit="return confirm('Отправить документы в Google Drive?')">
    <button class="btn" type="submit"{' disabled' if not can_send else ''}
            title="{'Отправить документы на Google Диск' if can_send else 'Сначала согласуйте документы'}">
      📤 Отправить на Google Drive
    </button>
  </form>
</div>
"""

    # Нижняя часть заявки — тот же конструктор, что и в шаблонах: он либо работает
    # с шаблоном, либо с реальной заявкой. Второй копии кода нет.
    builder = ""
    if picked:
        try:
            from blocks.templates.page import card as _tpl_card
            builder = _tpl_card(picked, _app_id=app_id, _embed=True)
        except Exception as _e:
            log.warning("конструктор в заявке %s не собрался: %s", app_id, str(_e)[:160])
            builder = ('<div class="rv-builder-note">Конструктор недоступен: '
                       + _html.escape(str(_e)[:160]) + '</div>')
    else:
        builder = '<div class="rv-builder-note">У заявки пока нет документов</div>'

    body = f"""
<style>{CSS}</style>
<div class="rv-wrap">
  {head}

  <section class="rv-builder" id="rv-builder">{builder}</section>

  {foot}
</div>

<button type="button" class="rv-mobile-bar" id="rv-mobile-bar">
  <span class="rv-num" style="background:rgba(255,255,255,.25);color:#fff">2</span>
  Переменные и значения · {len(pool_groups)}
</button>
<div class="rv-backdrop" id="rv-backdrop"></div>
<script>
{js_for(app_id, picked)}
</script>
"""

    from blocks.shared.layout import render
    crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/history">История и поиск</a>'
              f' &rsaquo; <b>Проверка заявки #{app_id}</b>')
    return render(f"Проверка заявки #{app_id}", "history", body, crumbs=crumbs)


def _ready_modal_html(app_id: int) -> str:
    """Окно «Готовые доки»: живой список подтверждённых документов.

    Состав окна пересобирается с сервера: поставил галочку — документ сразу
    появился в списке и в полосе просмотра, снял — ушёл. Открытие окна всегда
    показывает актуальный состав (не то, что было при загрузке страницы).
    """
    try:
        from blocks.dashboard.page import _ready_docs
        docs = _ready_docs(app_id)
    except Exception:
        docs = []
    chips, secs = [], []
    for d in docs:
        tpl = str(d.get("tpl"))
        num = str(d.get("num") or tpl)
        name = _html.escape(str(d.get("name") or ""))
        meta = ("\u2116" + num + " · " + _html.escape(str(d.get("title") or "")) + " · "
                + _html.escape(str(d.get("date") or "")))
        chips.append(
            '<button type="button" class="ready-list-item" data-jump="' + tpl + '">'
            '<span class="rli-num">\u2116' + num + '</span>'
            '<span class="rli-text"><span class="rli-name">' + name + '</span>'
            '<span class="rli-meta">' + meta + '</span></span>'
            '<span class="rli-spin" title="загружаю документ"></span>'
            '<span class="rli-done" title="документ загружен">\u2713</span>'
            '<span class="rli-dl" data-dl="' + tpl + '" title="Скачать этот документ в PDF">\u2913</span>'
            '</button>'
        )
        secs.append(
            '<section class="ready-sec" id="ready-sec-' + tpl + '" data-tpl="' + tpl + '">'
            '<div class="ready-sec-head">'
            '<span class="ready-sec-name">' + name + '</span>'
            '<span class="ready-sec-meta">' + meta + '</span>'
            '</div>'
            '<div class="ready-pages" data-tpl="' + tpl + '"></div>'
            '</section>'
        )
    head = ('<div class="ready-head">'
            '<b class="ready-title">Просмотр документов и отправка на Google Диск</b>'
            '<span class="ready-head-actions">'
            '<button type="button" class="ready-send" id="ready-send">Отправить на Google Диск</button>'
            '<button type="button" class="ready-close" id="ready-close">Закрыть</button>'
            '</span></div>')
    js = READY_MODAL_JS.replace("__APP__", str(app_id))
    return ('<div class="ready-modal" id="ready-modal" hidden>'
            '<div class="ready-window">'
            + head
            + '<div class="ready-body2">'
            + '<div class="ready-list" id="ready-list">' + "".join(chips) + '</div>'
            + '<div class="ready-view" id="ready-view" data-sig="'
            + "|".join("%s:%s:%s" % (d.get("tpl"), d.get("status") or "", d.get("num") or "")
                        for d in docs)
            + '">' + "".join(secs) + '</div>'
            + '</div>'
            + '<div class="ready-toast" id="ready-toast" hidden></div>'
            '</div></div>'
            '<script>' + js + '</script>')


READY_MODAL_JS = """
(function(){
  var appId = __APP__;
  var btn = document.getElementById('rv-ready-btn'), mod = document.getElementById('ready-modal');
  if (!btn || !mod) return;
  var list = document.getElementById('ready-list'), view = document.getElementById('ready-view');
  var MAXP = 14, timer = null;
  var lastSig = (view && view.getAttribute('data-sig')) || '';
  var queue = [], pumping = false;

  function sig(docs){ return (docs || []).map(function(d){
      return d.tpl + ':' + (d.status || '') + ':' + (d.num || ''); }).join('|'); }
  function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function num(d){ return '\u2116' + (d.num || d.tpl); }
  function meta(d){ return num(d) + ' \u00b7 ' + esc(d.title || '') + ' \u00b7 ' + esc(d.date || ''); }

  /* Пересобираем состав окна только когда он правда изменился. */
  function render(docs){
    lastSig = sig(docs);
    var chips = '', secs = '';
    (docs || []).forEach(function(d){
      var tpl = String(d.tpl);
      chips += '<button type="button" class="ready-list-item" data-jump="' + tpl + '">'
             + '<span class="rli-num">' + num(d) + '</span>'
             + '<span class="rli-text"><span class="rli-name">' + esc(d.name) + '</span>'
             + '<span class="rli-meta">' + meta(d) + '</span></span>'
             + '<span class="rli-spin" title="загружаю документ"></span>'
             + '<span class="rli-done" title="документ загружен">\u2713</span>'
             + '<span class="rli-dl" data-dl="' + tpl + '" title="Скачать этот документ в PDF">\u2913</span>'
             + '</button>';
      secs += '<section class="ready-sec" id="ready-sec-' + tpl + '" data-tpl="' + tpl + '">'
            + '<div class="ready-sec-head"><span class="ready-sec-name">' + esc(d.name) + '</span>'
            + '<span class="ready-sec-meta">' + meta(d) + '</span></div>'
            + '<div class="ready-pages" data-tpl="' + tpl + '"></div></section>';
    });
    if (!chips){
      chips = '<div class="ready-empty">Пока нет подтверждённых документов: '
            + 'поставьте галочки на миниатюрах — они появятся здесь.</div>';
    }
    if (list) list.innerHTML = chips;
    if (view) view.innerHTML = secs;
    mark(onScreen());
    enqueueAll();
  }

  function refresh(){
    fetch('/applications/' + appId + '/ready-docs', {credentials:'same-origin',
          headers:{'X-Requested-With':'fetch'}})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if (!j || !j.ok) return;
        var s = sig(j.docs);
        if (s === lastSig) return;             /* состав тот же — окно не трогаем */
        var keep = view ? view.scrollTop : 0;
        render(j.docs);
        if (view) view.scrollTop = keep;
      })
      .catch(function(){});
  }

  function mark(tpl){
    if (!list) return;
    Array.prototype.forEach.call(list.children, function(c){
      if (c.classList) c.classList.toggle('is-on', c.getAttribute('data-jump') === tpl);
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
    var s = document.getElementById('ready-sec-' + tpl);
    if (!s || !view) return;
    mark(tpl);
    view.scrollTo({top: s.offsetTop - view.offsetTop, behavior:'smooth'});
  }

  /* Индикатор загрузки у пункта списка: крутится, пока листы не пришли. */
  function item(tpl){
    return list ? list.querySelector('.ready-list-item[data-jump="' + tpl + '"]') : null;
  }
  function spin(tpl, on, finished){
    var it = item(tpl);
    if (!it) return;
    it.classList.toggle('is-loading', !!on);
    var sp = it.querySelector('.rli-spin'); if (sp) sp.classList.toggle('is-on', !!on);
    if (finished) it.setAttribute('data-done', '1');
    var dn = it.querySelector('.rli-done');
    if (dn) dn.classList.toggle('is-on', !on && it.getAttribute('data-done') === '1');
  }

  /* Листы одного документа: страница за страницей, затем следующий документ. */
  function loadBox(box, done){
    if (!box){ if (done) done(); return; }
    if (box.getAttribute('data-loaded')){ if (done) done(); return; }
    box.setAttribute('data-loaded', '1');
    var tpl = box.getAttribute('data-tpl'), n = 1, ver = Date.now();
    function next(){
      if (n > MAXP){ if (done) done(); return; }
      var img = new Image();
      img.className = 'ready-page';
      img.alt = 'страница ' + n;
      img.onload = function(){ box.appendChild(img); n++; next(); };
      img.onerror = function(){ if (done) done(); };
      img.src = '/applications/' + appId + '/doc/' + tpl + '/ready-img/' + n + '?v=' + ver;
    }
    next();
  }
  function enqueueAll(){
    queue = Array.prototype.slice.call(mod.querySelectorAll('.ready-pages'))
              .filter(function(b){ return !b.getAttribute('data-loaded'); });
    pump();
  }
  function pump(){
    if (pumping) return;
    var box = queue.shift();
    if (!box){ pumping = false; return; }
    pumping = true;
    var tpl = box.getAttribute('data-tpl');
    spin(tpl, true);
    loadBox(box, function(){
      pumping = false;
      spin(tpl, false, true);
      pump();
    });
  }

  function open(){
    mod.hidden = false; mod.style.display = 'flex';
    refresh();
    enqueueAll();                     /* по очереди: верхний документ, затем следующий */
    if (timer) clearInterval(timer);
    timer = setInterval(function(){ if (!mod.hidden) refresh(); }, 5000);
  }
  function close(){ mod.hidden = true; mod.style.display = 'none'; if (timer){ clearInterval(timer); timer = null; } }
  function toast(text, link, ok){
    var t = document.getElementById('ready-toast');
    t.hidden = false; t.className = 'ready-toast ' + (ok ? 'ok' : 'err'); t.innerHTML = '';
    var s = document.createElement('div'); s.className = 'ready-toast-text'; s.textContent = text;
    t.appendChild(s);
    if (link){
      var a = document.createElement('a'); a.href = link; a.target = '_blank';
      a.rel = 'noopener'; a.className = 'ready-toast-link';
      a.textContent = 'Ссылка на папку клиента на Google Диске'; t.appendChild(a);
    }
    var c = document.createElement('button'); c.type = 'button'; c.className = 'ready-toast-x';
    c.textContent = '\u2715'; c.addEventListener('click', function(){ t.hidden = true; });
    t.appendChild(c);
  }

  btn.addEventListener('click', open);
  var x = document.getElementById('ready-close'); if (x) x.addEventListener('click', close);
  mod.addEventListener('click', function(e){ if (e.target === mod) close(); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') close(); });
  if (list) list.addEventListener('click', function(e){
    var dl = e.target.closest ? e.target.closest('.rli-dl') : null;
    if (dl){                                  /* скачать один документ, не открывая его */
      e.preventDefault(); e.stopPropagation();
      var t0 = dl.getAttribute('data-dl');
      var a0 = document.createElement('a');
      a0.href = '/applications/' + appId + '/doc/' + t0 + '/ready-pdf?download=1';
      a0.download = ''; document.body.appendChild(a0); a0.click(); a0.remove();
      return;
    }
    var b = e.target.closest ? e.target.closest('.ready-list-item') : null;
    if (b) jump(b.getAttribute('data-jump'));
  });
  if (view) view.addEventListener('scroll', function(){ mark(onScreen()); });
  /* Галочку поставили или сняли — состав окна обновляем сразу же. */
  document.addEventListener('click', function(e){
    if (!e.target.closest) return;
    if (!e.target.closest('.rv-mark, .tpl-mark')) return;
    setTimeout(refresh, 700);
  });

  var send = document.getElementById('ready-send');

  /* Карточка по центру экрана: подтверждение, ожидание, результат. */
  var cardEl = null;
  function card(kind, o){
    o = o || {};
    if (!cardEl){
      cardEl = document.createElement('div');
      mod.appendChild(cardEl);
    }
    while (cardEl.firstChild) cardEl.removeChild(cardEl.firstChild);
    cardEl.className = 'rv-card ' + kind;
    var box = document.createElement('div'); box.className = 'rv-card-box';
    if (kind === 'busy'){
      var sp = document.createElement('div'); sp.className = 'rv-spin-lg';
      box.appendChild(sp);
    } else if (o.icon){
      var ic = document.createElement('div'); ic.className = 'rv-card-ico';
      ic.textContent = o.icon; box.appendChild(ic);
    }
    if (o.title){
      var t = document.createElement('div'); t.className = 'rv-card-title';
      t.textContent = o.title; box.appendChild(t);
    }
    if (o.text){
      var p = document.createElement('div'); p.className = 'rv-card-text';
      p.textContent = o.text; box.appendChild(p);
    }
    if (o.lines && o.lines.length){
      var ul = document.createElement('div'); ul.className = 'rv-card-lines';
      for (var li = 0; li < o.lines.length; li++){
        var row = document.createElement('div'); row.className = 'rv-card-line';
        row.textContent = o.lines[li]; ul.appendChild(row);
      }
      box.appendChild(ul);
    }
    var btns = document.createElement('div'); btns.className = 'rv-card-btns';
    /* Кнопки действий, переданные вызывающим кодом: {label, cls, onClick}. */
    (o.actions || []).forEach(function(a){
      if (!a || !a.label) return;
      var b = document.createElement('button'); b.type = 'button';
      b.className = 'rv-card-btn ' + (a.cls || '');
      b.textContent = a.label;
      if (a.title) b.title = a.title;
      b.addEventListener('click', function(){ try { a.onClick && a.onClick(); } catch(e){} });
      btns.appendChild(b);
    });
    if (kind === 'confirm'){
      var yes = document.createElement('button'); yes.type = 'button';
      yes.className = 'rv-card-btn primary'; yes.textContent = o.okText || 'Да';
      yes.addEventListener('click', function(){ hideCard(); if (o.onOk) o.onOk(); });
      var no = document.createElement('button'); no.type = 'button';
      no.className = 'rv-card-btn'; no.textContent = 'Отмена';
      no.addEventListener('click', hideCard);
      btns.appendChild(yes); btns.appendChild(no);
    } else if (kind === 'done'){
      if (o.link){
        var a = document.createElement('a'); a.className = 'rv-card-btn primary';
        a.href = o.link; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Открыть папку на Google Диске'; btns.appendChild(a);
      }
      var ok2 = document.createElement('button'); ok2.type = 'button';
      ok2.className = 'rv-card-btn'; ok2.textContent = 'Закрыть';
      ok2.addEventListener('click', hideCard); btns.appendChild(ok2);
    } else if (kind === 'error'){
      var fb = document.createElement('button'); fb.type = 'button';
      fb.className = 'rv-card-btn primary'; fb.textContent = 'Понятно';
      fb.addEventListener('click', hideCard); btns.appendChild(fb);
    }
    if (btns.firstChild) box.appendChild(btns);
    cardEl.appendChild(box);
  }
  function hideCard(){ if (cardEl) cardEl.className = 'rv-card is-hidden'; }

  function askSend(){
    var n = 0;
    var items = mod.querySelectorAll('.ready-list-item');
    for (var i = 0; i < items.length; i++) n++;
    card('confirm', {
      icon: '\u2B06',
      title: 'Отправить документы на Google Диск?',
      text: 'Сначала система проверит весь пакет на соответствие — наши документы вместе с документами клиента на Google Диске (даты, паспорт, подписант, значения полей). Если нестыковок нет, ' + n + ' подтверждённых документ(ов) уйдут в папку заявки на Диске.',
      okText: 'Да, проверить и отправить',
      onOk: doSend
    });
  }

  function doSend(){
    send.disabled = true;
    /* Финишная проверка идёт первой: пока она не прошла, файлы на Диск не уходят. */
    card('busy', { title: 'Проверяю документы на соответствие',
                   text: 'Сверяю весь пакет: наши документы и документы клиента на Google Диске. Это займёт несколько секунд.' });
    fetch('/applications/' + appId + '/send', {method:'POST', credentials:'same-origin',
          headers:{'X-Requested-With':'fetch'}})
      .then(function(r){ return r.json(); })
      .then(function(d){
        send.disabled = false;
        var ok = !!(d && d.ok);
        if (ok){
          card('done', { icon: '\u2713',
            title: 'Документы проверены и отправлены на Google Диск',
            text: 'Загружено файлов: ' + ((d.uploaded || []).length) + '. Папка заявки с документами:',
            link: (d && d.link) || '' });
          refresh();
        } else if (d && d.check){
          var lines = [];
          (d.findings || []).forEach(function(f){
            lines.push('\u2022 ' + (f.doc || '') + ': ' + (f.msg || ''));
          });
          if (d.rework && d.rework.length){
            lines.push('Возвращены в редактор: ' + d.rework.join(', '));
          }
          card('error', { icon: '\u26D4',
            title: 'Пакет не прошёл проверку — на Google Диск не отправлен',
            text: (d.error || 'Есть нестыковки.') + ' Ниже по пунктам, что именно не стыкуется:',
            lines: lines,
            /* Кнопка исправления: пересобирает документы по текущим правилам
               (и сбрасывает осевшие значения) и сразу повторяет проверку. */
            actions: [{ label: '🔧 Исправить и проверить заново', cls: 'primary',
                        title: 'Пересобрать документы и повторить проверку',
                        onClick: function(){
                          card('busy', { title: 'Исправляю документы',
                                         text: 'Пересобираю документы заявки по текущим правилам и проверяю заново.' });
                          fetch('/applications/' + appId + '/fix-docs', {method:'POST', credentials:'same-origin',
                                headers:{'X-Requested-With':'fetch'}})
                            .then(function(r){ return r.json(); })
                            .then(function(f){
                              var failed = (f && f.failed) || [];
                              if (failed.length){
                                card('error', { icon: '!', title: 'Часть документов не удалось пересобрать',
                                                lines: failed });
                                return;
                              }
                              doSend();
                            })
                            .catch(function(){ card('error', { icon: '!', title: 'Исправить не удалось',
                                                               text: 'Ошибка сети. Попробуйте ещё раз.' }); });
                        } }] });
        } else {
          card('error', { icon: '!', title: 'Отправить не удалось',
            text: (d && (d.error || (d.errors || [])[0])) || 'неизвестная ошибка' });
        }
      })
      .catch(function(e){
        send.disabled = false;
        card('error', { icon: '!', title: 'Отправить не удалось', text: String(e) });
      });
  }

  if (send) send.addEventListener('click', askSend);
})();
"""
