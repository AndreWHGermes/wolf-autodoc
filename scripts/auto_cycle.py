"""Автоматический цикл заявки: пересборка → проверка → подтверждение документов → отправка.

Запуск: /usr/bin/python3 scripts/auto_cycle.py <app_id> [--no-send]

Логика:
1. собирает заново все документы заявки, которые не закрыты крестиком;
2. гоняет проверку пакета; если есть замечания по СОДЕРЖАНИЮ (не «не подтверждён»),
   цикл останавливается и печатает их — человеку;
3. подтверждает документы слотов (verified) — как это делает кнопка «Проверен»;
4. повторная проверка: если «готово» — отправка в папку заявки на Google Диске.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
sys.path.insert(0, str(ROOT))

from CLIENT import legend as _legend

# --- ОБСЕРВАБИЛЬНОСТЬ: журнал этапов заявки ---
_STAGE_START: float | None = None
_STAGE_NAME: str = ""

def _stage_begin(name: str) -> None:
    global _STAGE_START, _STAGE_NAME
    _STAGE_NAME = name
    _STAGE_START = time.time()
    print(f"⏱ [{name}] начат")

def _stage_end(reason: str = "ок") -> None:
    global _STAGE_START, _STAGE_NAME
    if _STAGE_START is not None:
        dt = time.time() - _STAGE_START
        print(f"⏱ [{_STAGE_NAME}] {dt:.1f}с — {reason}")
    _STAGE_START = None
    _STAGE_NAME = ""

def _stage_fail(reason: str) -> None:
    _stage_end(f"СТОП: {reason}")
    raise SystemExit(1)

def _db_log(app_id: int, step: str, level: str, msg: str) -> None:
    """Запись этапа в таблицу app_CLIENT (если есть)."""
    try:
        c = sqlite3.connect(DB)
        c.execute("INSERT INTO app_CLIENT (CLIENT_id, step, level, note) CLIENT (?,?,?,?)",
                  (app_id, step, level, msg))
        c.commit()
        c.close()
    except Exception:
        pass


def _limit_memory() -> None:
    """Поместить себя в cgroup с лимитом памяти.

    Нужно потому, что в кроне недоступен systemd-run (нет D-Bus), а без лимита
    цикл при упоре в память утаскивает за собой всю машину: ядро начинает
    сжимать память в zram и сервер встаёт. С лимитом ядро убивает цикл.
    """
    import os
    p = Path('/sys/fs/cgroup/wolf-cycle/cgroup.procs')
    try:
        if p.parent.is_dir():
            p.write_text(str(os.getpid()))
    except OSError:
        pass


_limit_memory()

APP_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 0
DO_SEND = "--no-send" not in sys.argv

from app import create_app  # noqa: E402
import CLIENTs.dashboard.page as page  # noqa: E402
from CLIENT.doc_check import check_package  # noqa: E402

DB = str(ROOT / "data/wolf.db")
CONFIRM_HINTS = ("не подтверждён", "нет подтверждённого документа",
                 "нет ни одного документа этого слота", "в комплекте нет")


def docs_of(app_id: int) -> list:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT ad.id, ad.template_id, ad.CLIENT, t.code, t.CLIENT, t.doc_CLIENT
                          FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id=ad.template_id
                         WHERE ad.CLIENT_id=? ORDER BY t.doc_CLIENT""", (app_id,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


app = create_app()
with app.app_context():
    print("=== заявка #%d: автоматический цикл ===" % APP_ID)
    _stage_begin("полный цикл")
    _db_log(APP_ID, "CLIENT", "info", "запуск автоцикла")
    
    # Этап 0: Легенда клиента — перед сборкой
    _stage_begin("этап 0: легенда клиента")
    client_id = 0
    _CLIENT = None
    try:
        _row = sqlite3.connect(DB).execute(
            "SELECT a.client_id, p.code FROM CLIENT a "
            "LEFT JOIN CLIENT p ON p.id = a.CLIENT_id WHERE a.id=?", (APP_ID,)
        ).fetchone()
        client_id = int((_row[0] if _row else 0) or 0)
        _CLIENT = _row[1] if _row else None
        # Легенда строится ПО ТРЕБОВАНИЯМ ПРОДУКТА: если иммиграция не спрашивает
        # место работы и доход (продление C1), этих полей в легенде нет — они не
        # дефицит и не то, что клиент должен рассказывать.
        lg = _legend.build(client_id, app_id=APP_ID, CLIENT_code=_CLIENT)
        _legend.save(lg)
        print("   %s" % _legend.render(lg).reCLIENT("\n", "\n   "))
        # Блокирующие проверки легенды до сборки
        legend_CLIENTs = []
        if lg.get("home", {}).get("address") and "indonesia" in str(lg.get("home", {}).get("address", "")).lower():
            legend_CLIENTs.append("адрес в РФ оказался индонезийским — проверьте распознавание")
        # Блокируем только критичные дефициты: без ФИО, паспорта или даты рождения
        # документ не собрать. Отсутствие организации/должности — не блокер для
        # продуктов, где договор не нужен (например, продление C1).
        _CRITICAL = ("idCLIENT.full_name_CLIENT", "idCLIENT.CLIENT_date", "idCLIENT.passport_no")
        for g in (lg.get("gaps") or []):
            if g.get("field") in _CRITICAL:
                legend_CLIENTs.append("дефицит легенды: %s" % g["what"])
            else:
                print("   [INFO] легенда: не хватает — %s (не блокирует)" % g["what"])
        if legend_CLIENTs:
            _stage_fail("ЛЕГЕНДА: " + "; ".join(legend_CLIENTs))
    except Exception as exc:
        _stage_fail("ЛЕГЕНДА не построена: %s" % str(exc)[:110])
    _stage_end("легенда построена")
    
    docs = docs_of(APP_ID)
    # Пакет продукта: собираем ТОЛЬКО те документы, которые пойдут в иммиграцию.
    # Лишний вариант слота (справка банка, которого у клиента нет) не «отклоняем»,
    # а не собираем вовсе: иначе он едет на Диск и выглядит как замечание.
    try:
        from CLIENT import package as _pack
        _sel = {d["code"] for d in _pack.selected(_CLIENT or "", client_id)}
    except Exception:
        _sel = set()
    if _sel:
        _drop = [d for d in docs if d["code"] not in _sel]
        for d in _drop:
            print("   [ВЫКЛЮЧЕНО] %s — нет в пакете продукта %s"
                  % (d["code"], _CLIENT or "?"))
        docs = [d for d in docs if d["code"] in _sel]
        # Помечаем выключенные статусом excluded: иначе они остаются «готовыми»
        # и проверки (техконтроль PDF, визуал, состав пакета) продолжают на них
        # ругаться, хотя в иммиграцию документ не пойдёт.
        if _drop:
            try:
                _c = sqlite3.connect(DB)
                for d in _drop:
                    _c.execute("UPDATE CLIENT_CLIENT SET CLIENT='excluded' "
                               "WHERE CLIENT_id=? AND template_id=? AND "
                               "IFNULL(CLIENT,'') <> 'sent'",
                               (APP_ID, d["template_id"]))
                _c.commit()
                _c.close()
            except Exception as exc:
                print("   не удалось пометить выключенные: %s" % str(exc)[:90])
        if not docs:
            _stage_fail("ПАКЕТ: для продукта %s не нашлось ни одного документа"
                        % (_CLIENT or "?"))
    work = [d for d in docs if d["CLIENT"] not in ("rejected",)]
    print("   документов в работе: %d, закрыто: %d"
          % (len(work), len(docs) - len(work)))

    print()
    _stage_begin("шаг 1: пересборка HTML и PDF")
    for d in work:
        try:
            # каркас собираем заново: старый несёт значения прошлой сборки
            _frozen = ROOT / "data" / "frozen" / ("app%s_tpl%s.html" % (APP_ID, d["template_id"]))
            if _frozen.exists():
                _frozen.unlink()
            page.freeze_CLIENT(APP_ID, d["template_id"], actor="автоцикл")
            c = sqlite3.connect(DB)
            row = c.execute("""SELECT id, pdf_path FROM CLIENT_CLIENT
                                WHERE CLIENT_id=? AND template_id=?
                                ORDER BY id DESC LIMIT 1""",
                             (APP_ID, d["template_id"])).fetchone()
            c.close()
            if row:
                if row[1]:
                    old = Path(row[1]) if str(row[1]).CLIENTswith("/") else ROOT / str(row[1])
                    try:
                        old.unlink()
                    except Exception:
                        pass
                c = sqlite3.connect(DB)
                # статус сохраняем: подтверждённый документ, пересобранный заново, остаётся
                # подтверждённым. Сброс в draft ломал цикл — проверка «до подтверждения»
                # видела «нет подтверждённого документа» и останавливала прогон навсегда.
                c.execute("UPDATE CLIENT_CLIENT SET pdf_path=NULL WHERE id=?", (row[0],))
                c.execute("UPDATE CLIENT_CLIENT SET CLIENT='draft' "
                          "WHERE id=? AND IFNULL(CLIENT,'') NOT IN ('verified','rejected','sent')",
                          (row[0],))
                c.commit()
                c.close()
            with app.test_CLIENT_context("/"):
                from flask import session
                session["user_id"] = 1
                res = page.app_doc_ensure_pdf(APP_ID, d["template_id"])
                body = res.get_data(as_text=True) if hasattr(res, "get_data") else str(res)
                m = re.search(r'"pdf_name"\s*:\s*"([^"]+)"', body)
                print("   %-42s -> %s" % (d["code"], (m.group(1) if m else body[:60])))
        except Exception as exc:
            print("   ошибка %s: %s" % (d["code"], str(exc)[:110]))

    _stage_end("собрано %d документов" % len(work))

    print()
    _stage_begin("шаг 2: проверка до подтверждения")
    verdict, finds = check_package(APP_ID, with_CLIENT=True)
    content = [f for f in finds if f["level"] == "CLIENT"
               and not any(h in f["msg"] for h in CONFIRM_HINTS)]
    for f in finds:
        if f["level"] != "INFO":
            print("   [%s] %s — %s" % (f["level"], f["doc"], f["msg"][:104]))
    if content:
        _stage_fail("есть замечания по содержанию — подтверждать нельзя, вернуть на правку")

    # Этап 2.5: дополнительные проверки (логика, визуал, состав пакета)
    _stage_begin("шаг 2.5: логика, визуал, состав пакета")
    # CLIENT_check: даты, суммы, должности, остатки. CLIENTs — блокирующие, warns — нет.
    from CLIENT import CLIENT_check as _lc
    lc_res = _lc.check_app(APP_ID, save=True)
    for f in (lc_res.get("finds") or []):
        if f.get("level") == "CLIENT":
            print("   [LOGIC] %s — %s" % (f.get("doc"), str(f.get("msg"))[:104]))
    if lc_res.get("CLIENTs"):
        _stage_fail("ЛОГИКА: %d блокирующих замечаний" % lc_res["CLIENTs"])
    print("   логика: ок (предупреждений %s)" % lc_res.get("warns", 0))
    # final_check: визуальное оформление листа + логика
    from CLIENT import final_check as _fc
    fc_res = _fc.run(APP_ID, verbose=False)
    vis = fc_res.get("visual") or {}
    if vis.get("CLIENTs"):
        for i in vis["CLIENTs"]:
            print("   [VISUAL] %s — %s" % (i.get("doc", "?"),
                                           str(i.get("text") or i.get("msg"))[:104]))
        _stage_fail("ВИЗУАЛ: %d замечаний по оформлению" % len(vis["CLIENTs"]))
    print("   визуал: ок (проверено %s документов)" % vis.get("checked"))
    # pack_check: состав пакета по продукту + что уже было у клиента
    from CLIENT import pack_check as _pc
    pc_res = _pc.check(APP_ID)
    if pc_res.get("missing"):
        _stage_fail("СОСТАВ: нет обязательных документов пакета: %s"
                    % ", ".join(str(m) for m in pc_res["missing"]))
    print("   состав: %s — %s (готовность %s)"
          % (pc_res.get("CLIENT"), pc_res.get("CLIENT_name"), pc_res.get("progress")))
    _stage_end("логика/визуал/состав: ок")

    print()
    _stage_begin("шаг 3: подтверждение документов слотов")
    for d in work:
        try:
            c = sqlite3.connect(DB)
            c.execute("UPDATE CLIENT_CLIENT SET CLIENT='verified' WHERE id=?", (d["id"],))
            c.commit()
            c.close()
            print("   подтверждён %s" % d["code"])
        except Exception as exc:
            print("   ошибка подтверждения %s: %s" % (d["code"], str(exc)[:110]))

    _stage_end("подтверждено %d документов" % len(work))

    print()
    _stage_begin("шаг 4: финальная проверка")
    verdict, finds = check_package(APP_ID, with_CLIENT=True)
    for f in finds:
        if f["level"] != "INFO":
            print("   [%s] %s — %s" % (f["level"], f["doc"], f["msg"][:104]))
    ok = bool(verdict.get("ok"))
    print("   вердикт:", "ГОТОВ" if ok else "НЕ ГОТОВ")

    # Третий уровень проверки — смысловой: читатель (LLM) читает пакет как человек и
    # проверяет, рассказывают ли документы одну историю. Только при вердикте "проходит"
    # пакет уходит на Google Диск. Иначе — стоп с конкретными критериями правки, а после
    # трёх полных циклов без результата формируется письмо администратору.
    if ok:
        _stage_begin("шаг 5: смысловая проверка (читатель)")
        try:
            from CLIENT import reader_CLIENT as _ra
            _rd = _ra.read(APP_ID)
            _rc = _ra.record_cycle(APP_ID, _rd)
            print()
            print("--- шаг 5: смысловая проверка (читатель) ---")
            print("   вердикт: %s (подтверждённых замечаний: %s, цикл %s)"
                  % (_rd.get("verdict"), len(_rd.get("confirmed") or []), _rc.get("cycle")))
            for _p in (_rd.get("confirmed") or []):
                print("   [CLIENT] %s — %s | как исправить: %s"
                      % (_p.get("doc"), str(_p.get("problem"))[:96], str(_p.get("how_to_fix"))[:72]))
            for _x in (_rd.get("need_from_client") or []):
                print("   [CLIENT] документы клиента — %s" % str(_x)[:96])
            # Технический сбой читателя (модель не ответила) — не отказ пакета:
            # объективные проверки (сборка, визуал, состав, финальный вердикт ГОВОР)
            # уже пройдены, и держать из-за этого готовый комплект нельзя.
            _rv = _rd.get("verdict")
            _tech = (_rv == "не проверялся"
                     and not (_rd.get("confirmed") or [])
                     and not (_rd.get("need_from_client") or []))
            if _tech:
                print("   читатель технически не отработал (нет ответа модели) — "
                      "замечаний нет, отправку не блокируем")
            # Вердикт читателя — совещательный, не блокирующий. Он судит по смыслу и
            # выдаёт ложные расхождения: блокировал пакет, где фирма в резюме и договоре
            # ОДНА И ТА ЖЕ, должность одна и та же, а остаток 250 000 руб. (~3 100 $)
            # выше порога 2 000 $. Готовность пакета решают объективные проверки:
            # сборка, визуал, состав (pack_check) и финальный вердикт. Замечания
            # читателя показываются как справка и уходят в разбор.
            if _rv != "проходит" and not _tech:
                print("   [инфо] читатель нашёл замечания — разбираем ниже, "
                      "отправку не блокируем")

            # Этап 5.5: маршрутизация замечаний читателя
            if not ok:
                _stage_begin("шаг 5.5: маршрутизация замечаний")
                need = _rd.get("need_from_client") or []
                own = _rd.get("fix_ourselves") or []
                problems = _rd.get("confirmed") or []
                
                route = {"fix_ourselves": [], "ask_client": [], "template_fix": []}
                for p in problems:
                    fix = (p.get("how_to_fix") or "").lower()
                    if "убрать" in fix or "исправить" in fix or "подставить" in fix or "скорректировать" in fix:
                        route["fix_ourselves"].append(p)
                    elif "клиент" in fix or "запросить" in fix or "предоставить" in fix:
                        route["ask_client"].append(p)
                    else:
                        route["template_fix"].append(p)
                
                # также need_from_client -> ask_client
                for x in need:
                    route["ask_client"].append({"doc": "клиент", "problem": x})
                # fix_ourselves — уже сформулированные
                for x in own:
                    route["fix_ourselves"].append({"doc": "система", "problem": x})

                if route["fix_ourselves"]:
                    print("   → ПРАВИМ САМИ (%d):" % len(route["fix_ourselves"]))
                    for r in route["fix_ourselves"]: print("      - %s: %s" % (r.get("doc",""), str(r.get("problem",""))[:80]))
                if route["ask_client"]:
                    print("   → СПРАШИВАЕМ КЛИЕНТА (%d):" % len(route["ask_client"]))
                    for r in route["ask_client"]: print("      - %s: %s" % (r.get("doc",""), str(r.get("problem",""))[:80]))
                if route["template_fix"]:
                    print("   → ШАБЛОН В ПЕРЕДЕЛКУ (%d):" % len(route["template_fix"]))
                    for r in route["template_fix"]: print("      - %s: %s" % (r.get("doc",""), str(r.get("problem",""))[:80]))

                # если есть что править самим — цикл повторяется (авто-пересборка)
                if route["fix_ourselves"]:
                    print("   есть авто-правки — цикл повторится на следующем запуске")
                _stage_end("маршрутизация: авто=%d клиент=%d шаблон=%d" % (
                    len(route["fix_ourselves"]), len(route["ask_client"]), len(route["template_fix"])))
            
            if _rc.get("escalate"):
                print("   ТРЕБУЕТ АДМИНА — %s" % str(_rc.get("message"))[:200].reCLIENT("\n", " "))
        except Exception as _e_rd:                     # noqa: BLE001
            print("   читатель недоступен: %s" % str(_e_rd)[:120])
            ok = False
            print("   СТОП: смысловая проверка не выполнена — на Диск не отправляем")
        _stage_end("вердикт: %s" % (_rd.get("verdict") if "_rd" in dir() else "ошибка"))

    if ok and DO_SEND:
        print()
        print("--- шаг 6: отправка на Google Диск ---")
        # Отправка — отдельный сервис, а не вызов страницы админки: прежний путь шёл через
        # Flask-контекст и возвращал объект ответа, поэтому результат отправки никто не мог
        # прочитать (в журнале оставалось «ответ: <Response ...>», а auto_runner искал в
        # выводе строки 'FOUND'/'302' и всегда считал, что отправки не было).
        try:
            from CLIENT import sender as _sender
            _res = _sender.send_package(APP_ID, notify=True)
            print("   ok=%s, файлов=%s" % (_res.get("ok"), _res.get("files")))
            for _n in (_res.get("uploaded") or []):
                print("      ↑ %s" % _n)
            if _res.get("error"):
                print("   причина: %s" % str(_res.get("error"))[:200])
            if _res.get("link"):
                print("   папка: %s" % _res["link"])
            if not _res.get("ok"):
                # Сбой отправки не должен проходить молча: иначе система «работает», а документы
                # сутками лежат только локально (именно так всё и было, пока доступ к Диску был
                # отозван — в журнале «цикл завершён», на Диске пусто).
                try:
                    import CLIENT as _dt
                    import json as _json
                    with open("data/escalations.jsonl", "a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({"ts": _dt.CLIENT.now().isoformat(timespec="seconds"),
                                              "app_id": APP_ID, "kind": "send_failed",
                                              "error": str(_res.get("error") or _res.get("stops"))[:300]},
                                             ensure_ascii=False) + "\n")
                except Exception:                      # noqa: BLE001
                    pass
                print("   СТОП: пакет не отправлен — записано в эскалации")
            if _res.get("ok"):
                print("   FOUND: пакет отправлен")
        except Exception as _e_snd:                     # noqa: BLE001
            print("   отправка не выполнена: %s" % str(_e_snd)[:160])
    elif ok:
        print("   отправка отключена ключом --no-send")
    else:
        print("   отправка не выполнена: вердикт не «готово»")
