"""Работа с документами клиента из Google Drive.

Отвечает за: выгрузку папки клиента (gdown) и поиск в локальной выгрузке, чтение
документов моделью с привязкой значений к переменным, состояние и отчёт разбора.
Каталоги берутся из конфигурации проекта, а не из жёстких путей — иначе копия
системы работала бы с данными оригинала.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core import db
from core.config import BASE_DIR, DATA_DIR

CACHE_DIR = Path(DATA_DIR) / "gdrive_cache"
EXAMPLES_DIR = Path(DATA_DIR) / "gdrive_examples"
SCAN_SCRIPT = Path(BASE_DIR) / "scripts" / "drive_scan.py"


def docs_for_client(client_id: int) -> list:
    """Документы клиента: кэш → выгрузка папки по ссылке → локальная выгрузка."""
    client = db.q1("SELECT * FROM clients WHERE id=?", (client_id,)) or {}
    url = (client.get("gdrive_folder_url") or "").strip()
    cache = CACHE_DIR / f"client_{client_id}"
    have = [f for f in cache.rglob("*") if f.is_file()] if cache.is_dir() else []
    # Скачивание при открытии страницы не запускаем: Google режет частые обращения,
    # и страница ждала бы минутами. Данные клиента подтягивает разбор документов
    # в фоне (шаг «Разобрать документы»), после него плитки появляются сами.
    _ = url
    # Подстановку «примеров» убрали: она показывала файлы там, где у клиента
    # на самом деле ничего не скачано, и по ней ставилась ложная галочка разбора.
    return [f for f in have if not f.name.startswith(".")
            and f.name.lower() not in (".ds_store", "thumbs.db")][:24]


def extract_one(path: Path) -> dict:
    """Читает документ (PDF, скан, фото, HEIC — через OCR) и вытаскивает значения."""
    from bot.ai_parser import _call_llm
    try:
        from services.doc_read import read_text
        text = read_text(path) or ""
    except Exception:  # noqa: BLE001
        import pymupdf
        text = ""
        if str(path).lower().endswith(".pdf"):
            d = pymupdf.open(str(path))
            text = "\n".join(d[i].get_text() for i in range(min(3, len(d))))
            d.close()
    if not text.strip():
        text = "(текст из документа извлечь не удалось)"
    prompt = (
        "Ты обрабатываешь документы клиента визового агентства. Ниже текст документа.\n"
        "Вытащи ВСЕ значимые данные (ФИО, дата рождения, паспорт, адрес, банк, суммы, номера, даты, компании).\n"
        "Для каждого значения укажи, какой переменной конструктора оно соответствует по смыслу "
        "(например: full_name_latin, passport_number, date_of_birth, balance_rub, doc_no, bank_name).\n"
        "Ответ строго списком: `значение | переменная | короткое пояснение`. Без вступлений.\n\n"
        "ДОКУМЕНТ:\n" + text[:6000]
    )
    out = _call_llm([{"role": "user", "content": prompt}], timeout=120, json_mode=False) or ""
    return {"file": path.name, "kind": path.suffix.lstrip("."), "text_len": len(text), "found": out.strip()}


def last_scan(app_id: int):
    try:
        return db.q1("SELECT * FROM drive_scans WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))
    except Exception:
        return None


def throttle_state() -> dict:
    """Состояние ограничителя обращений к Google Диску — для интерфейса."""
    from services import drive_throttle as t
    return t.state()


def start_scan(app_id: int, client_id: int) -> dict:
    """Решение о запуске разбора: не запускаем повторно, если уже вытащено.

    Перед запуском спрашиваем ограничитель: если Google недавно отказал или
    исчерпан лимит заходов в час, разбор откладывается — так мы не долбим Диск
    и не продлеваем себе же блокировку.
    """
    from services import drive_throttle as thr
    from services import gdrive_api as api
    can, why = (True, '') if api.available() else thr.can_call()
    if not can:
        db.exec_sql("UPDATE drive_scans SET status='fail', note=? "
                    "WHERE application_id=? AND status='running'", (why, app_id))
        return {"ok": False, "note": why}
    try:
        db.exec_sql("UPDATE drive_scans SET status='fail', note='прервано' "
                    "WHERE application_id=? AND status='running'", (app_id,))
    except Exception:
        pass
    prev = last_scan(app_id)
    if prev:
        status = (prev["status"] or "").lower()
        done = int(prev["docs_done"] or 0)
        total = int(prev["docs_total"] or 0)
        if status == "running":
            return {"ok": True, "already": True, "running": True,
                    "note": "Разбор уже идёт — дождитесь окончания"}
        if status == "ok" and done > 0 and done >= total:
            return {"ok": True, "already": True, "done": done, "total": total,
                    "note": f"Документы уже вытащены ({done} из {total}) — повторный разбор не нужен, "
                            f"нейросеть не тратим"}
    db.exec_sql("INSERT INTO drive_scans(application_id, client_id, status, docs_total, docs_done, note) "
                "VALUES(?,?,?,?,?,?)", (app_id, client_id, "running", 0, 0, "разбор запущен"))
    try:
        # Разбор документов идёт в фоне и с пониженным приоритетом: пока
        # администратор работает в сайте, разбор не должен отбирать у него
        # процессор. Дочерние процессы (OCR) наследуют этот приоритет.
        subprocess.Popen(["/usr/bin/nice", "-n", "15", "/usr/bin/python3",
                          str(SCAN_SCRIPT), str(app_id)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:  # noqa: BLE001
        db.exec_sql("UPDATE drive_scans SET status='fail', note=? "
                    "WHERE application_id=? AND status='running'",
                    (f"не удалось запустить разбор: {e}", app_id))
        return {"ok": False, "note": "не удалось запустить разбор"}
    return {"ok": True, "note": "разбор запущен"}


def status(app_id: int) -> dict:
    r = last_scan(app_id)
    if not r:
        return {"status": "none", "note": "ещё не разбиралось", "done": 0, "total": 0}
    return {"status": r["status"], "note": r["note"],
            "done": r["docs_done"] or 0, "total": r["docs_total"] or 0}


def report_html(app_id: int) -> str:
    rows = db.q("SELECT * FROM drive_scans WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))
    if not rows:
        return "<div style='padding:14px;color:#6B7C70'>Разбор ещё не запускался.</div>"
    r = rows[0]
    try:
        payload = json.loads(r.get("payload") or "[]")
    except Exception:
        payload = []
    if not payload:
        return "<div style='padding:14px;color:#6B7C70'>" + (r.get("note") or "нет данных") + "</div>"
    html = ['<div class="muted" style="margin-bottom:10px">' + (r.get("note") or "") + "</div>"]
    for it in payload:
        html.append('<div style="border:1px solid #E3EEE7;border-radius:10px;padding:10px 12px;margin-bottom:10px">')
        try:
            from scripts.drive_scan import doc_kind_name, DOC_KIND_RU
            _kr = DOC_KIND_RU.get(it.get("doc_type") or doc_kind_name(it.get("file") or ""), "")
        except Exception:
            _kr = ""
        _ext = (it.get("kind") or "").upper()
        html.append('<div style="font-weight:600;margin-bottom:2px">📄 ' + str(it.get("file") or "?")
                    + ((" · " + _ext) if _ext else "") + "</div>")
        if _kr:
            html.append('<div style="font-size:12px;color:#3A6B4E;margin-bottom:6px">тип: '
                        + _kr + "</div>")
        body = it.get("found") or it.get("error") or it.get("note") or "—"
        html.append('<div style="white-space:pre-wrap;font-size:13px;line-height:1.45">' + str(body) + "</div>")
        html.append("</div>")
    return "".join(html)

PASSPORT_HINTS = ("паспорт", "passport", "pasport", "загран", "zagran")


def check_folder(app_id: int, client_id: int) -> dict:
    """Проверяет папку клиента на Google Drive: есть ли файлы и есть ли паспорт.

    Вызывается сразу после приёма заявки: если менеджер дал ссылку, мы обязаны
    убедиться, что оттуда реально можно взять данные клиента.
    """
    files = docs_for_client(client_id)
    names = [f.name.lower() for f in files]
    passport = [nm for nm in names if any(h in nm for h in PASSPORT_HINTS)]
    res = {
        "files": len(files),
        "passport": len(passport) > 0,
        "names": [f.name for f in files][:12],
        "ok": bool(files) and bool(passport),
    }
    try:
        db.exec_sql("""INSERT INTO drive_scans (application_id, status, docs_total, docs_done, note)
                       VALUES (?,?,?,?,?)""",
                    (app_id, "checked" if res["ok"] else "warn", res["files"], 0,
                     ("паспорт найден, файлов " + str(res["files"])) if res["passport"]
                     else ("паспорт не найден среди " + str(res["files"]) + " файлов")))
    except Exception:
        pass
    return res
