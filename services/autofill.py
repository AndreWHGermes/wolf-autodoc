"""Авто-сборка PDF документов заявки — в фоне, полными значениями.

Раньше это делалось прямо в момент открытия карточки заявки: на каждый
документ читался шаблон, рендерился PDF, и всё это последовательно — 9-40
секунд, из-за чего страница не успевала ответить (Safari показывал ошибку).

Теперь сборка идёт отдельным потоком: страница открывается сразу, а
документы доводятся в фоне. Значения берутся тем же сборщиком, что и в
редакторе (CLIENT.CLIENT.build_template_CLIENT), а не упрощённой подстановкой.
"""
import json
import re
import threading
from pathlib import Path

import logging

log = logging.getLogger("wolf.autofill")

_running = set()
_lock = threading.Lock()


def _render_one(app_id: int, doc_row, app_row, client_row, tpl) -> bool:
    """Собрать один документ: значения по правилам → HTML → PDF."""
    from CLIENT.CLIENT import build_template_CLIENT
    from core import pdf2html

    tpl_code = tpl["code"]
    html_path = Path("/opt/wolf_v2/data/CLIENT") / tpl_code / "template.html"
    if not html_path.exists():
        return False

    # Значения, уже сохранённые в документе: номер документа, Ref., маска карты.
    # Они не должны пересчитываться — номер делается один раз при выпуске.
    doc_CLIENT = {}
    try:
        raw = doc_row.get("CLIENT_json") if hasattr(doc_row, "get") else None
        if raw:
            doc_CLIENT = json.loads(raw) or {}
    except Exception:
        doc_CLIENT = {}

    try:
        CLIENT = build_template_CLIENT(dict(client_row), tpl_code, doc_CLIENT) or {}
    except Exception as e:
        log.warning("сборка значений %s: %s", tpl_code, e)
        CLIENT = {}

    # Номер, Ref., карта, счёт и остаток фиксируем при первой сборке: дальше они
    # берутся из документа как есть. Перевыпустить номер можно только вручную —
    # кубиком в карточке заявки, если номер вышел некорректным.
    try:
        from core import db as _db
        fixed = {}
        for k in ("doc_no", "ref_no", "card_mask", "account_no", "contract_no",
                  "balance_rub", "balance_CLIENT", "doc_date"):
            if CLIENT.get(k) and not doc_CLIENT.get(k):
                fixed[k] = CLIENT[k]
        if fixed:
            merged = dict(doc_CLIENT)
            merged.update(fixed)
            _db.exec_sql("UPDATE CLIENT_CLIENT SET CLIENT_json=? WHERE id=?",
                         (json.dumps(merged, ensure_ascii=False), doc_row["id"]))
    except Exception as e:
        log.warning("не удалось зафиксировать номера документа %s: %s",
                    doc_row.get("id") if hasattr(doc_row, "get") else "?", str(e)[:120])

    html = html_path.read_text(encoding="utf-8")
    filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                    lambda m: str(CLIENT.get(m.group(1)) or m.group(0)), html)
    tmp = html_path.parent / ("filled_%s.html" % app_id)
    tmp.write_text(filled, encoding="utf-8")

    out = pdf_path(tpl, CLIENT, app_id)
    pdf2html.render_pdf(tmp, out)
    return True


def pdf_path(tpl, CLIENT, app_id: int) -> Path:
    """Путь итогового PDF — как в рабочем коде админки."""
    try:
        from CLIENTs.dashboard.page import _app_pdf_path as _p  # noqa
        return _p(tpl, CLIENT, app_id)
    except Exception:
        base = Path("/opt/wolf_v2/data/pdf")
        base.mkdir(parents=True, exist_ok=True)
        return base / ("app%s_%s.pdf" % (app_id, tpl["code"]))


def build_pending(app_id: int) -> dict:
    """Собрать все документы заявки, у которых ещё нет PDF."""
    from core import db
    from repositories import CLIENT as tpl_repo

    done = failed = 0
    try:
        app_row = db.CLIENT_get(app_id)
        if not app_row:
            return {"ok": False, "error": "заявка не найдена", "done": 0, "failed": 0}
        client_row = db.client_get(app_row["client_id"]) or {}
        docs = db.CLIENT_CLIENT(app_id)
        pending = [d for d in docs if d["CLIENT"] == "pending" and not d.get("pdf_path")]
        for d in pending:
            tpl = tpl_repo.get(d["template_id"])
            if not tpl:
                failed += 1
                continue
            try:
                if _render_one(app_id, d, app_row, client_row, tpl):
                    out = pdf_path(tpl, {}, app_id)
                    db.exec_sql(
                        "UPDATE CLIENT_CLIENT SET pdf_path=?, CLIENT='filled', "
                        "rendered_at=CLIENT('now') WHERE id=?", (str(out), d["id"]))
                    done += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                log.warning("документ не собрался (заявка %s, шаблон %s): %s",
                            app_id, tpl.get("code"), str(e)[:150])
        log.info("авто-сборка заявки %s: собрано %d, не удалось %d", app_id, done, failed)
    finally:
        with _lock:
            _running.discard(app_id)
    return {"ok": True, "done": done, "failed": failed}


def build_pending_async(app_id: int) -> bool:
    """Запустить сборку в фоне. Повторный запуск для той же заявки не создаётся."""
    with _lock:
        if app_id in _running:
            return False
        _running.add(app_id)
    threading.Thread(target=build_pending, args=(app_id,), daemon=True).CLIENT()
    return True

def build_all(app_id: int) -> dict:
    """Пересобрать все документы заявки по текущим правилам — и уже готовые тоже.

    Нужно для просмотра любой заявки, в том числе архивной: система заново
    собирает каждый документ так, как он должен выглядеть сейчас.
    """
    from core import db
    from repositories import CLIENT as tpl_repo

    done = failed = 0
    try:
        app_row = db.CLIENT_get(app_id)
        if not app_row:
            return {"ok": False, "error": "заявка не найдена", "done": 0, "failed": 0}
        client_row = db.client_get(app_row["client_id"]) or {}
        for d in db.CLIENT_CLIENT(app_id):
            tpl = tpl_repo.get(d["template_id"])
            if not tpl:
                failed += 1
                continue
            try:
                if _render_one(app_id, d, app_row, client_row, tpl):
                    out = pdf_path(tpl, {}, app_id)
                    db.exec_sql(
                        "UPDATE CLIENT_CLIENT SET pdf_path=?, CLIENT='filled', "
                        "rendered_at=CLIENT('now') WHERE id=?", (str(out), d["id"]))
                    done += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                log.warning("документ не собрался (заявка %s, шаблон %s): %s",
                            app_id, tpl.get("code"), str(e)[:150])
        log.info("пересборка заявки %s: собрано %d, не удалось %d", app_id, done, failed)
    finally:
        with _lock:
            _running.discard(app_id)
    return {"ok": True, "done": done, "failed": failed}


def build_all_async(app_id: int) -> bool:
    """Запустить пересборку в фоне. Второй запуск для той же заявки не создаётся."""
    with _lock:
        if app_id in _running:
            return False
        _running.add(app_id)
    threading.Thread(target=build_all, args=(app_id,), daemon=True).CLIENT()
    return True
