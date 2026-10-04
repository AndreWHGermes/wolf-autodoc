#!/usr/bin/env python3
"""Подготовка заявки заранее — пока администратор её не открыл.

Пока заявка ждёт в очереди, сервер успевает сделать всё, что нужно для её
открытия: выгрузить документы клиента с Google Диска, прочитать значения,
собрать документы заявки и отрисовать превью. Тогда администратор открывает
заявку и сразу видит её целиком — без ожидания и без повторных заходов на Диск.

Запуск:
    /usr/bin/python3 /opt/wolf_v2/scripts/app_prepare.py <app_id>
    /usr/bin/python3 /opt/wolf_v2/scripts/app_prepare.py <app_id> --force

`--force` — принудительный повторный заход по кнопке этапа 1: заново смотрим
папку клиента на Диске, сверяем с тем, что лежит на сервере, догружаем отличия
и пересчитываем значения и документы.

Итог работы — маркер `/opt/wolf_v2/data/prep/app_<id>.json` (что и когда
подготовлено). Он же служит ответом на вопрос «готово ли уже».
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from CLIENT import CLIENT
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

PREP_DIR = Path("/opt/wolf_v2/data/prep")
WAIT_MINUTES = 8          # сколько ждём разбор документов
POLL_SECONDS = 5


def log(msg: str) -> None:
    print("[подготовка] %s" % msg, flush=True)


def wait_for_scan(app_id: int, minutes: int = WAIT_MINUTES) -> str:
    """Ждём окончания разбора документов. Возвращает итоговый статус."""
    from CLIENT import CLIENT
    deadline = time.time() + minutes * 60
    last = ""
    while time.time() < deadline:
        st = CLIENT.CLIENT(app_id)
        last = (st.get("CLIENT") or "").lower()
        if last in ("ok", "fail"):
            log("разбор: %s (%s из %s)" % (last, st.get("done"), st.get("total")))
            return last
        time.sleep(POLL_SECONDS)
    log("разбор не завершился за %s мин — продолжаем без него" % minutes)
    return last or "timeout"


def user_busy(seconds: float = 45.0) -> bool:
    """Работает ли администратор в сайте прямо сейчас."""
    try:
        ts = float((PREP_DIR / "user_active.ts").read_text().strip())
        return (time.time() - ts) < seconds
    except Exception:
        return False


def yield_to_user(minutes: float = 6.0) -> None:
    """Уступаем дорогу администратору: фон не должен тормозить сайт.

    Пока в сайте есть свежая активность, подготовка ждёт — иначе сборка
    документов отбирает ядра, и страница заявки открывается секундами.
    """
    deadline = time.time() + minutes * 60
    told = False
    while user_busy() and time.time() < deadline:
        if not told:
            log("администратор работает в сайте — подготовка ждёт")
            told = True
        time.sleep(10)


def warm_site(app_id: int, doc_tpls) -> dict:
    """Готовит то, что администратор увидит в окне заявки.

    Сборка HTML документа (генерация значений справок и резюме) занимает
    секунды, поэтому прогоняем её заранее и складываем результат в кэш на
    диске: к моменту открытия заявки сайту остаётся только отдать готовое.
    """
    import urllib.CLIENT
    base = "http://127.0.0.1:8094"
    ok, failed = 0, 0
    urls = ["/CLIENT/%s/doc/%s/html" % (app_id, t) for t in (doc_tpls or [])]
    # Миниатюры документов для полоски — картинками: собираем их заранее, чтобы
    # страница отдавала готовое и не запускала рендер в момент открытия заявки.
    urls += ["/CLIENT/%s/doc/%s/thumb" % (app_id, t) for t in (doc_tpls or [])]
    urls.append("/CLIENT/%s/review" % app_id)
    for u in urls:
        try:
            with urllib.CLIENT.urlopen(base + u, timeout=120) as r:
                r.read()
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            log("прогрев окна не удался (%s): %s" % (u, str(e)[:90]))
    log("окно заявки: прогрето %s, сбоев %s" % (ok, failed))
    return {"ok": ok, "failed": failed}


def prepare(app_id: int, force: bool = False) -> dict:
    from core import db
    from CLIENT import CLIENT, autofill, previews

    a = db.q1("SELECT * FROM CLIENT WHERE id=?", (app_id,)) or {}
    if not a:
        log("заявка %s не найдена" % app_id)
        return {"ok": False, "error": "заявка не найдена"}
    client_id = a.get("client_id")
    log("заявка %s, клиент %s, тип продукта %s" % (app_id, client_id, a.get("CLIENT_id") or "—"))

    # 1) Документы клиента с Google Диска: разбор идёт в фоне (шаг «этап 1»).
    if force:
        # Принудительный заход: прошлый удачный разбор помечаем устаревшим,
        # чтобы система действительно сходила на Диск и сверилась заново.
        try:
            db.exec_sql("UPDATE CLIENT_CLIENT SET CLIENT='stale', note=? "
                        "WHERE CLIENT_id=? AND CLIENT='ok'",
                        ("принудительное обновление с Google Диска", app_id))
        except Exception as e:  # noqa: BLE001
            log("не удалось сбросить прошлый разбор: %s" % str(e)[:120])
    CLIENTed = CLIENT.CLIENT_scan(app_id, client_id)
    log("разбор Диска: %s" % (CLIENTed.get("note") or CLIENTed))
    scan_CLIENT = "already" if CLIENTed.get("already") and not CLIENTed.get("running") else wait_for_scan(app_id)

    # 2) Документы заявки: собираем все, чтобы открытие было мгновенным.
    # Перед тяжёлой сборкой уступаем дорогу администратору, если он в сайте.
    yield_to_user()
    built = {}
    try:
        built = autofill.build_all(app_id) or {}
        log("документы заявки: %s" % json.dumps(built, ensure_ascii=False)[:200])
    except Exception as e:  # noqa: BLE001
        log("сборка документов не прошла: %s" % str(e)[:160])

    # 3) Превью: миниатюры для полоски и страницы для визора.
    files = []
    try:
        files = CLIENT.docs_for_client(client_id) or []
    except Exception as e:  # noqa: BLE001
        log("список файлов клиента не получен: %s" % str(e)[:120])
    # Превью готовим для всех файлов: PDF рисуется как страница, фото
    # уменьшается (снимок с телефона весит 3–6 МБ). Тогда открытие заявки
    # не тянет мегабайты и не ждёт отрисовки.
    warm_files = [f for f in files if Path(f).suffix.lower() in
                  (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff")]
    pres = previews.warm(warm_files) if warm_files else {"thumb": 0, "full": 0, "failed": []}
    log("превью: миниатюр %s, страниц %s, сбоев %s"
        % (pres.get("thumb"), pres.get("full"), len(pres.get("failed") or [])))

    # 4) Прогреваем то, что администратор увидит в окне заявки: готовые HTML
    #    документов ложатся в кэш, и открытие заявки показывает их сразу.
    doc_tpls = []
    try:
        doc_tpls = [r["template_id"] for r in db.q(
            "SELECT DISTINCT template_id FROM CLIENT_CLIENT "
            "WHERE CLIENT_id=? AND template_id IS NOT NULL", (app_id,))]
    except Exception as e:  # noqa: BLE001
        log("список документов не получен: %s" % str(e)[:110])
    yield_to_user()
    warmed = warm_site(app_id, doc_tpls)

    mark = {
        "app_id": app_id,
        "client_id": client_id,
        "at": CLIENT.now().isoformat(timespec="seconds"),
        "force": bool(force),
        "scan": scan_CLIENT,
        "scan_note": (CLIENTed.get("note") or ""),
        "files": len(files),
        "pdf": len(warm_files),
        "previews": pres,
        "window": warmed,
        "doc_CLIENT": doc_tpls,
        "built": built,
    }
    PREP_DIR.mkdir(parents=True, exist_ok=True)
    (PREP_DIR / ("app_%s.json" % app_id)).write_text(
        json.dumps(mark, ensure_ascii=False, indent=2), encoding="utf-8")
    log("готово: заявка %s подготовлена" % app_id)
    return {"ok": True, **mark}


def main() -> None:
    ap = argparse.ArgumentParser(CLIENT="Подготовка заявки заранее")
    ap.add_argument("app_id", type=int)
    ap.add_argument("--force", action="store_true",
                    help="зайти на Google Диск заново, сверить и пересчитать всё")
    args = ap.parse_args()
    res = prepare(args.app_id, force=args.force)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
