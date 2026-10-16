"""Авто-сборка PDF документов заявки — в фоне, полными значениями.

Раньше это делалось прямо в момент открытия карточки заявки: на каждый
документ читался шаблон, рендерился PDF, и всё это последовательно — 9-40
секунд, из-за чего страница не успевала ответить (Safari показывал ошибку).

Теперь сборка идёт отдельным потоком: страница открывается сразу, а
документы доводятся в фоне. Значения берутся тем же сборщиком, что и в
редакторе (services.values.build_template_values), а не упрощённой подстановкой.
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
    from services.values import build_template_values
    from core import pdf2html

    tpl_code = tpl["code"]
    html_path = Path("/opt/wolf_v2/data/templates") / tpl_code / "template.html"
    if not html_path.exists():
        return False

    # Значения, уже сохранённые в документе: номер документа, Ref., маска карты.
    # Они не должны пересчитываться — номер делается один раз при выпуске.
    doc_values = {}
    try:
        raw = doc_row.get("values_json") if hasattr(doc_row, "get") else None
        if raw:
            doc_values = json.loads(raw) or {}
    except Exception:
        doc_values = {}

    try:
        values = build_template_values(dict(client_row), tpl_code, doc_values, app_id=app_id) or {}
    except Exception as e:
        log.warning("сборка значений %s: %s", tpl_code, e)
        values = {}

    # Пустой набор значений — не собирать документ. Сборка значений может упасть или
    # выполниться до того, как у заявки появились данные; при этом документ всё равно
    # сохранялся, а его values_json оставался пустым (так ушли документы заявки 102:
    # 4 из 5 с пустыми значениями, в резюме — имена переменных вместо данных). Пустой
    # документ хуже несобранного: его могут отправить клиенту.
    if len(values) < 5:
        log.warning("документ %s не выпущен: собрано значений %d (ожидались десятки)",
                    tpl_code, len(values))
        try:
            from core import db as _db
            _db.exec_sql("UPDATE application_documents SET error=? WHERE id=?",
                         ("не собраны значения документа (получено %d)" % len(values),
                          (doc_row or {}).get("id") if hasattr(doc_row, "get") else None))
        except Exception:      # noqa: BLE001
            pass
        try:
            from datetime import datetime as _dt
            rec = {"at": _dt.now().isoformat(timespec="seconds"), "kind": "no_values",
                   "template": tpl_code, "values": len(values)}
            with Path("/opt/wolf_v2/data/cycle_problems.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:      # noqa: BLE001
            pass
        return False

    # Карточка клиента — источник правды для банковских реквизитов документа.
    # Значения в карточке появляются из настоящей справки клиента, поэтому они сильнее
    # и заполнителей шаблона, и значений, зафиксированных при первой сборке (раньше из-за
    # этого в готовую справку уходил чужой остаток из образца, а номер счёта не попадал вовсе).
    _cl = dict(client_row) or {}
    try:
        # ref_no и doc_no сюда НЕ входят намеренно: у них свои форматы
        # (Ref. = заглавная + 8 цифр + 3 заглавные, No = две строчные + 8 цифр),
        # их берут из настоящей справки с проверкой формата или генерируют.
        for _k in ('account_no', 'contract_no', 'contract_date', 'card_mask', 'bank_name'):
            _v = str(_cl.get(_k) or '').strip()
            if _v:
                values[_k] = _v
                doc_values[_k] = _v
    except Exception:
        pass

    # Настоящая справка клиента сильнее любого ранее зафиксированного значения:
    # если она появилась, сумма и дата остатка берутся из неё, а не из генерации.
    try:
        if "bank_statement" in (tpl_code or ""):
            from services.values import read_client_bank_statement, _num2words_en, _fmt_money
            _real = read_client_bank_statement((dict(client_row) or {}).get("id"))
            _amt = str(_cl.get('balance_rub') or '').strip() or _real.get("balance_rub")
            _bdate = str(_cl.get('balance_date') or '').strip() or _real.get("balance_date")
            if _amt:
                _amt_txt = str(_amt).replace("\u00a0", "").replace(" ", "").replace(",", ".")
                _amt_fmt = _fmt_money(_amt, tpl_code)
                doc_values["balance_rub"] = _amt_fmt
                values["balance_rub"] = _amt_fmt
                if _bdate:
                    doc_values["balance_date"] = _bdate
                    values["balance_date"] = _bdate
                try:
                    _int = int(float(_amt_txt.replace(",", ".")))
                    _kop = int(round((float(_amt_txt.replace(",", ".")) - _int) * 100))
                    values["balance_words"] = _num2words_en(_int)
                    doc_values["balance_words"] = values["balance_words"]
                    # Копейки обязаны идти от той же суммы, что и цифры: иначе в строке
                    # стоит «29 919,94», а прописью печатается «00 kopeks».
                    values["balance_cents"] = "%02d" % _kop
                    doc_values["balance_cents"] = values["balance_cents"]
                except Exception:
                    pass
    except Exception:
        pass

    # Номер, Ref., карта, счёт и остаток фиксируем при первой сборке: дальше они
    # берутся из документа как есть. Перевыпустить номер можно только вручную —
    # кубиком в карточке заявки, если номер вышел некорректным.
    try:
        from core import db as _db
        fixed = {}
        for k in ("doc_no", "ref_no", "card_mask", "account_no", "contract_no",
                  "balance_rub", "balance_words", "doc_date"):
            if values.get(k) and not doc_values.get(k):
                fixed[k] = values[k]
        # остальные подставленные значения тоже сохраняем: иначе в карточке заявки
        # поля выглядят незаполненными, хотя в документе текст уже стоит
        for k, v in values.items():
            if k == "doc_values" or k in fixed or k in doc_values:
                continue
            if v is None or str(v).strip() == "":
                continue
            if isinstance(v, (str, int, float)):
                fixed[k] = v
        if fixed:
            merged = dict(doc_values)
            merged.update(fixed)
            _db.exec_sql("UPDATE application_documents SET values_json=? WHERE id=?",
                         (json.dumps(merged, ensure_ascii=False), doc_row["id"]))
    except Exception as e:
        log.warning("не удалось зафиксировать номера документа %s: %s",
                    doc_row.get("id") if hasattr(doc_row, "get") else "?", str(e)[:120])

    html = html_path.read_text(encoding="utf-8")
    # Незаполненные переменные в готовом документе не показываем: в резюме и справках
    # пустые блоки (например, второе место работы) должны просто отсутствовать.
    # В формах иммиграции (Statement Letter) пустое поле печатается прочерком.
    _dash = str(tpl_code or "").startswith("statement_letter")
    filled = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
                    lambda m: str(values.get(m.group(1)) or ("-" if _dash else "")), html)
    # Разводка текста для печати: значение, которое не влезает в строку, переносится
    # вниз по правилам переноса, а не уезжает за край листа. Ни одно имя переменной
    # в готовый документ не попадает.
    try:
        from services.render import tidy_for_pdf
        filled = tidy_for_pdf(filled)
    except Exception as _e:
        log.warning("разводка текста не применилась: %s", str(_e)[:120])
    tmp = html_path.parent / ("filled_%s.html" % app_id)
    tmp.write_text(filled, encoding="utf-8")

    out = pdf_path(tpl, values, app_id)
    # Договоры (и трудовой, и remote) печатаем прямо из HTML-шаблона: их прежний каркас
    # держался на растровых подложках со старым текстом эталона, из-за чего в документе
    # были наложения фраз, чужая сумма и остатки подписи. Шаблоны пересобраны по образцу.
    if str(tpl_code or '').startswith(('employment_contract', 'remote_work_agreement')):
        try:
            pdf2html.render_pdf(tmp, out)
            return _finish(out, tpl_code, doc_row)
        except Exception as _e:      # noqa: BLE001
            log.warning('прямая сборка договора не сработала (%s) — пробуем каркас', str(_e)[:140])
    # Новый путь сборки: HTML-каркас A4 (координаты + шрифты из оригинала + перенос как в Word).
    # Если для шаблона каркас подготовлен — собираем по нему; иначе прежним способом.
    try:
        from services import html_frame
        if html_frame.build_pdf(tpl_code, values, out, app_id=app_id):
            return _finish(out, tpl_code, doc_row)
    except Exception as _e:      # noqa: BLE001
        log.warning("каркас недоступен (%s) — собираем прежним способом", str(_e)[:140])
    pdf2html.render_pdf(tmp, out)
    return _finish(out, tpl_code, doc_row)


def pdf_path(tpl, values, app_id: int) -> Path:
    """Путь итогового PDF — как в рабочем коде админки."""
    try:
        from blocks.dashboard.page import _app_pdf_path as _p  # noqa
        return _p(tpl, values, app_id)
    except Exception:
        base = Path("/opt/wolf_v2/data/pdf")
        base.mkdir(parents=True, exist_ok=True)
        return base / ("app%s_%s.pdf" % (app_id, tpl["code"]))


def _finish(out: Path, code: str, doc_row):
    """Путь собранного PDF при успехе, None — если документ не прошёл заслон."""
    return out if _gate_unfilled(out, code, doc_row) else None


def _gate_unfilled(pdf: Path, code: str, doc_row) -> bool:
    """Не признавать документ готовым, если в нём остались имена переменных.

    Сборка идёт тремя движками — подстановка в HTML, каркас по зонам, потоковая вёрстка
    резюме — и не все убирают метки, для которых значения не нашлось. В свежих сборках так
    уходили {{ cv_name }}, {{ company_full_name }}, {{ doc_no }}, {{ agreement_date }},
    {{ sponsor_company }}: документ был выпущен с незаполненным полем. Здесь ставим заслон
    на выходе: пусть лучше документ останется несобранным с понятной причиной, чем уйдёт
    клиенту с пустым полем.
    """
    try:
        import pymupdf
        d = pymupdf.open(str(pdf))
        text = '\n'.join(p.get_text() for p in d)
        d.close()
    except Exception:      # noqa: BLE001
        return True        # прочитать не смогли — сборку не блокируем
    left = sorted(set(re.findall(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', text)))
    if not left:
        return True
    log.warning("документ %s не выпущен: не заполнены переменные %s", code, ", ".join(left[:12]))
    try:
        from core import db as _db
        _db.exec_sql("UPDATE application_documents SET error=? WHERE id=?",
                     ("не заполнены переменные: " + ", ".join(left[:20]),
                      (doc_row or {}).get("id") if hasattr(doc_row, "get") else None))
    except Exception:      # noqa: BLE001
        pass
    try:
        from datetime import datetime as _dt
        rec = {"at": _dt.now().isoformat(timespec="seconds"), "kind": "unfilled",
               "template": code, "problems": left[:20]}
        with Path("/opt/wolf_v2/data/cycle_problems.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:      # noqa: BLE001
        pass
    return False


def build_pending(app_id: int) -> dict:
    """Собрать все документы заявки, у которых ещё нет PDF."""
    from core import db
    from repositories import templates as tpl_repo

    done = failed = 0
    try:
        app_row = db.application_get(app_id)
        if not app_row:
            return {"ok": False, "error": "заявка не найдена", "done": 0, "failed": 0}
        client_row = db.client_get(app_row["client_id"]) or {}
        docs = db.application_documents(app_id)
        pending = [d for d in docs if d["status"] == "pending" and not d.get("pdf_path")]
        for d in pending:
            tpl = tpl_repo.get(d["template_id"])
            if not tpl:
                failed += 1
                continue
            try:
                out = _render_one(app_id, d, app_row, client_row, tpl)
                if out:
                    # Путь к собранному PDF пишем ВСЕГДА: он нужен всем трём проверкам и отправке.
                    # Раньше путь и статус писались одним запросом с условием
                    # NOT IN ('verified','sent'), из-за чего запрос отменялся целиком и путь
                    # оставался пустым у 405 записей из 419 — читатель проверял пустые тексты.
                    db.exec_sql(
                        "UPDATE application_documents SET pdf_path=?, rendered_at=datetime('now') "
                        "WHERE id=?", (str(out), d["id"]))
                    db.exec_sql(
                        "UPDATE application_documents SET status='filled' WHERE id=? "
                        "AND IFNULL(status,'') NOT IN ('verified','sent')", (d["id"],))
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
    threading.Thread(target=build_pending, args=(app_id,), daemon=True).start()
    return True

def build_all(app_id: int) -> dict:
    """Пересобрать все документы заявки по текущим правилам — и уже готовые тоже.

    Нужно для просмотра любой заявки, в том числе архивной: система заново
    собирает каждый документ так, как он должен выглядеть сейчас.
    """
    from core import db
    from repositories import templates as tpl_repo

    done = failed = 0
    try:
        app_row = db.application_get(app_id)
        if not app_row:
            return {"ok": False, "error": "заявка не найдена", "done": 0, "failed": 0}
        client_row = db.client_get(app_row["client_id"]) or {}
        for d in db.application_documents(app_id):
            # документ, снятый с заявки (например, справка не того банка), заново не собираем
            if str(d.get("status") or "").lower() == "rejected":
                continue
            tpl = tpl_repo.get(d["template_id"])
            if not tpl:
                failed += 1
                continue
            try:
                out = _render_one(app_id, d, app_row, client_row, tpl)
                if out:
                    # Путь к собранному PDF пишем ВСЕГДА: он нужен всем трём проверкам и отправке.
                    # Раньше путь и статус писались одним запросом с условием
                    # NOT IN ('verified','sent'), из-за чего запрос отменялся целиком и путь
                    # оставался пустым у 405 записей из 419 — читатель проверял пустые тексты.
                    db.exec_sql(
                        "UPDATE application_documents SET pdf_path=?, rendered_at=datetime('now') "
                        "WHERE id=?", (str(out), d["id"]))
                    db.exec_sql(
                        "UPDATE application_documents SET status='filled' WHERE id=? "
                        "AND IFNULL(status,'') NOT IN ('verified','sent')", (d["id"],))
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
    threading.Thread(target=build_all, args=(app_id,), daemon=True).start()
    return True
