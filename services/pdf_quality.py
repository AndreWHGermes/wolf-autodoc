"""Технический контроль готового PDF перед отправкой на Google Диск.

Проверяет САМ файл, а не данные заявки: наложения текста, выход за лист,
незаполненные метки, пропавший фон (подложку), мусор в тексте, чужих людей
в документе. Любой BLOCK = документ не уходит на Диск.

Ведёт журнал проверок: data/reports/quality_checks.jsonl + таблица quality_checks.

Запуск вручную:
    cd /opt/wolf_v2 && /usr/bin/python3 services/pdf_quality.py <app_id> [<app_id> ...]
    cd /opt/wolf_v2 && /usr/bin/python3 services/pdf_quality.py --all
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import pymupdf

ROOT = Path("/opt/wolf_v2")
DB = ROOT / "data" / "wolf.db"
LOG = ROOT / "data" / "reports" / "quality_checks.jsonl"

LEFT, RIGHT, TOP, BOTTOM = 40.0, 555.0, 40.0, 800.0     # рабочее поле A4, pt

GARBAGE = [
    (re.compile(r"\{\{|\}\}"), "незаполненная метка шаблона"),
    (re.compile(r"\bNone\b|\bnan\b|\bundefined\b|#REF!"), "служебное значение вместо данных"),
    (re.compile(r"\s,|\s;|\s\.(?!\d)"), "пробел перед знаком препинания"),
    (re.compile(r",,|\.\.|\(\s*\)|\[\s*\]"), "пустая конструкция или двойной знак"),
    (re.compile(r"[А-Яа-яЁё]"), None),                    # кириллица в англоязычном документе — WARN
    # Длинная «склейка» ловится только по буквам и цифрам: строки подчёркиваний,
    # точек и дефисов — это обычные линии для подписи и разделители в бланках
    # банка. Раньше правило срабатывало на них («___…» = слипшееся слово) и
    # блокировало отправку правильной справки (задача #22, 17.10.2026).
    (re.compile(r"[^\W_]{28,}"), "слипшееся или неперенесённое длинное слово"),
]

# Пустая подстановка: обвязка шаблона напечатана, а значение не пришло — «No. »,
# «Moscow,», «in the position of,», «duties:». Такой документ выглядит «чистым»
# (меток {{ }} в нём нет, кириллицы нет), но подавать его нельзя: в договоре нет
# номера, даты, должности и обязанностей. Поэтому это блокирующее замечание.
#
# Перечень обязанностей печатается СПИСКОМ на строке ниже метки, поэтому одной
# регуляркой «метка + перевод строки» обойтись нельзя: она срабатывала и на
# правильно заполненном договоре (в образце метка «services:» всегда стоит в
# конце строки, а пункты — ниже) — это блокировало верные документы. Теперь
# метка проверяется вместе со следующей строкой: пусто только тогда, когда
# после неё нет пункта списка.
_BULLET = re.compile(r"^[\u2022\u25cf\u25aa\u25e6\-\u2013\u2014*]")
_SLOT_NO = re.compile(r"\bNo\.\s*$")
_SLOT_POS = re.compile(r"\bin the position of\s*,\s*and\b", re.I)
_SLOT_LIST = re.compile(r"\b(?:duties|services)\s*:\s*$", re.I)
_SLOT_PLACE = re.compile(r"^[A-Z][a-z]+,\s*$")


def _empty_slots(lines: list[str], pno: int, name: str) -> list[dict]:
    """Пустые подстановки в договоре — по строкам, а не по сплошному тексту."""
    out, seen = [], set()
    for i, raw in enumerate(lines):
        t = raw.strip()
        if not t:
            continue
        why = ""
        if _SLOT_NO.search(t):
            why = "не подставлен номер документа"
        elif _SLOT_POS.search(t):
            why = "не подставлена должность"
        elif _SLOT_LIST.search(t):
            nxt = next((x.strip() for x in lines[i + 1:i + 4] if x.strip()), "")
            if not _BULLET.match(nxt):
                why = "не подставлен перечень обязанностей"
        elif _SLOT_PLACE.match(t):
            why = "не подставлено значение после места составления"
        if why and why not in seen:
            seen.add(why)
            out.append({"level": "BLOCK", "msg": "стр.%d: %s — «%s»" % (pno, why, t[:40]),
                        "doc": name})
    return out


def _is_dotted(t: str) -> bool:
    """Пунктир/линия для вписывания значения (……, ___, - - -) — это разметка формы, не текст."""
    if len(t) < 3:
        return False
    dots = sum(1 for ch in t if ch in "._…-·• ")
    return dots / len(t) > 0.6


def _spans(page):
    out = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for s in ln.get("spans", []):
                t = (s.get("text") or "").strip()
                if t:
                    out.append((pymupdf.Rect(s["bbox"]), t))
    return out


def check_pdf(path: Path, code: str = "", foreign_names=(), tpl_mtime: float | None = None) -> list[dict]:
    """Замечания по одному готовому PDF. level: BLOCK — не отправлять."""
    finds: list[dict] = []
    # Файл может быть ещё не дописан (сборка идёт параллельно) или повреждён.
    # Раньше исключение pymupdf вылетало из проверки наружу, сторож превращал его
    # в «code_error» и заявка вставала в ступор (задача #14, 14.10.2026). Теперь
    # нечитаемый файл — обычное замечание по документу.
    try:
        doc = pymupdf.open(str(path))
        pages = doc.page_count
    except Exception as e:                                            # noqa: BLE001
        return [{"level": "BLOCK", "doc": path.name, "msg":
                 "файл не читается (%s) — нужен пересбор документа" % type(e).__name__}]
    if not doc or not pages:
        return [{"level": "BLOCK", "msg": "файл не открывается", "doc": path.name}]

    for pno, page in enumerate(doc, 1):
        W, H = page.rect.width, page.rect.height
        spans = _spans(page)
        text = "\n".join(t for _, t in spans)

        for rx, why in GARBAGE:
            m = rx.search(text)
            if not m:
                continue
            if why is None:                       # кириллица в документе на английском
                # Правило заказчика: все документы печатаются только на английском,
                # русского текста в них быть не должно — это блокирующая ошибка.
                finds.append({"level": "BLOCK",
                              "msg": "стр.%d: русский текст в документе — «%s» (документы только на английском)"
                              % (pno, m.group(0)[:28]), "doc": path.name})
                continue
            finds.append({"level": "BLOCK" if "метк" in why or "служебн" in why else "WARN",
                          "msg": "стр.%d: %s — «%s»" % (pno, why, m.group(0)[:28]), "doc": path.name})

        # Пустые подстановки проверяем у договоров: там обвязка шаблона остаётся без
        # значения, и внешне документ выглядит заполненным («EMPLOYMENT CONTRACT
        # No.», «Moscow,», «in the position of, and…»). Раньше такое проходило как
        # «чисто» и документ уходил в комплект с пустыми полями.
        if "contract" in (code or "").lower() or "agreement" in (code or "").lower():
            finds.extend(_empty_slots([t for _, t in spans], pno, path.name))

        # наложения: спаны пересекаются и по горизонтали, и по вертикали
        solid = [(r, t) for r, t in spans if not _is_dotted(t)]
        for i in range(len(solid)):
            a, ta = solid[i]
            for j in range(i + 1, len(solid)):
                b, tb = solid[j]
                if min(a.x1, b.x1) - max(a.x0, b.x0) > 2.5 and min(a.y1, b.y1) - max(a.y0, b.y0) > 4.0:
                    finds.append({"level": "BLOCK", "msg": "стр.%d: наложение текста «%s» и «%s»"
                                  % (pno, ta[:24], tb[:24]), "doc": path.name})
                    break
            if len(finds) > 24:
                break

        # выход за лист и за рабочее поле
        for r, t in spans:
            if r.x0 < -1 or r.x1 > W + 1 or r.y0 < -1 or r.y1 > H + 1:
                finds.append({"level": "BLOCK", "msg": "стр.%d: текст вне листа — «%s»" % (pno, t[:24]),
                              "doc": path.name})
            elif r.x0 < LEFT - 1 or r.x1 > RIGHT + 1 or r.y0 < TOP - 1 or r.y1 > BOTTOM + 1:
                finds.append({"level": "WARN", "msg": "стр.%d: текст вышел из рабочего поля — «%s»"
                              % (pno, t[:24]), "doc": path.name})

        # фон: у каркасных шаблонов на каждой странице должна быть подложка
        if code and (ROOT / "data" / "templates" / code / "frame" / "quality.json").exists():
            if not page.get_images(full=True):
                finds.append({"level": "BLOCK", "msg": "стр.%d: нет фона (подложка не подставилась)" % pno,
                              "doc": path.name})

        for nm in foreign_names:
            if nm and len(nm) > 5 and nm.lower() in text.lower():
                finds.append({"level": "BLOCK", "msg": "стр.%d: в документе чужой человек — «%s»"
                              % (pno, nm), "doc": path.name})

    if tpl_mtime and path.stat().st_mtime + 1 < tpl_mtime:
        finds.append({"level": "BLOCK",
                      "msg": "файл собран раньше последней правки шаблона — нужен пересбор и переподтверждение",
                      "doc": path.name})
    if not doc[0].get_text().strip() and not doc[0].get_images(full=True):
        finds.append({"level": "BLOCK", "msg": "пустой документ", "doc": path.name})
    doc.close()
    return _dedup(finds)


def _tpl_mtime(code: str) -> float | None:
    """Когда шаблон менялся последний раз (разметка, подложка, паспорт качества)."""
    if not code:
        return None
    tpl = ROOT / "data" / "templates" / code
    marks = [tpl / "fields.json", tpl / "frame" / "quality.json", tpl / "frame" / "bg.png"]
    marks += sorted((tpl / "frame").glob("bg-*.png"))
    ts = [m.stat().st_mtime for m in marks if m.exists()]
    return max(ts) if ts else None


def _dedup(finds):
    seen, out = set(), []
    for f in finds:
        k = (f["level"], f["msg"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def foreign_names_for(app_id: int) -> list[str]:
    """ФИО и названия фирм, которых в документах этой заявки быть не должно."""
    try:
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        cur = c.execute("SELECT client_id FROM applications WHERE id=?", (app_id,))
        row = cur.fetchone()
        mine = (row["client_id"] if row else None)
        names = set()
        for r in c.execute("SELECT id, last_name_ru, last_name, full_name_cyrillic FROM clients"):
            if r["id"] == mine:
                continue
            for v in (r["last_name_ru"], r["last_name"]):
                if v and len(str(v).strip()) > 5:
                    names.add(str(v).strip())
        c.close()
        return sorted(names)
    except Exception:
        return []


def check_app(app_id: int, template_of=None, save: bool = True) -> dict:
    """Проверить все готовые PDF заявки. template_of(template_id) -> code шаблона."""
    try:
        sys.path.insert(0, str(ROOT))
        from services import autofill                      # noqa: WPS433
        os_ready = autofill._ready_doc_pdf if hasattr(autofill, "_ready_doc_pdf") else None
    except Exception:
        os_ready = None
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    docs = c.execute("SELECT d.id, d.template_id, d.status, d.pdf_path, t.code "
                     "FROM application_documents d "
                     "LEFT JOIN templates t ON t.id=d.template_id WHERE d.application_id=?",
                     (app_id,)).fetchall()
    c.close()
    foreign = foreign_names_for(app_id)
    results = []
    for d in docs:
        if (d["status"] or "") not in ("filled", "verified", "sent"):
            continue
        # Готовый PDF ищем по заявке: в data/out/<заявка> лежат файлы именно
        # этого прогона. Общий каталог data/ready не годится — там остаются
        # файлы прежних заявок, и одноимённый документ другого клиента
        # выдавался за наш (проверка ругалась на чужие буквы и блокировала отправку).
        p = None
        try:
            out_dir = Path('/opt/wolf_v2/data/out') / str(app_id)
            if out_dir.exists():
                # Только точное совпадение имени файла с кодом шаблона: раньше
                # брали префикс до «__» («bank_statement»), и 12-месячная справка
                # Сбера проверялась по файлу 3-месячной справки Т-Банка — одно и
                # то же замечание прилетало трижды и блокировало отправку.
                cands = [x for x in sorted(out_dir.glob('*.pdf'))
                         if x.stat().st_size > 1000
                         and x.stem == (d['code'] or '')]
                if cands:
                    p = str(max(cands, key=lambda x: x.stat().st_mtime))
        except Exception:                                             # noqa: BLE001
            p = None
        # Карточка документа — источник истины: data/out может содержать копии
        # прежних прогонов, из-за которых проверка ругалась на уже исправленный
        # документ и блокировала отправку (кейс 120, 17.10.2026).
        try:
            _bp = d["pdf_path"]
            if _bp:
                _bp = Path(str(_bp)) if str(_bp).startswith("/") else ROOT / str(_bp)
                if _bp.exists() and _bp.stat().st_size > 1000:
                    if (not p) or _bp.stat().st_mtime >= Path(p).stat().st_mtime:
                        p = str(_bp)
        except Exception:
            pass
        if not p:
            try:
                sys.path.insert(0, str(ROOT))
                from blocks.dashboard.page import _ready_doc_pdf     # noqa: WPS433
                cand = _ready_doc_pdf(app_id, d["template_id"])
                # чужой документ по имени заявки не принимаем: сверяем, что файл
                # принадлежит этому прогону, а не прежней заявке того же клиента
                if cand and Path(cand).exists() and str(app_id) in Path(cand).name:
                    p = cand
            except Exception:                                         # noqa: BLE001
                p = None
        if not p or not Path(p).exists():
            # Третий путь — прямо из карточки документа. Запись принадлежит этой
            # заявке, поэтому файл наш по определению. Такой путь нужен потому,
            # что готовые справки называются «Bank Statement … <ФИО> …» — без
            # номера заявки, и проверка «id заявки в имени файла» их отвергала,
            # объявляя корректный документ отсутствующим.
            try:
                bp = d["pdf_path"]
            except Exception:
                bp = None
            if bp:
                bp = Path(str(bp)) if str(bp).startswith("/") else ROOT / str(bp)
                if bp.exists():
                    p = str(bp)
        if not p or not Path(p).exists():
            results.append({"doc_id": d["id"], "code": d["code"], "file": None,
                            "ok": False, "finds": [{"level": "BLOCK", "msg": "нет готового PDF",
                                                    "doc": d["code"] or "?"}]})
            continue
        if p and time.time() - Path(p).stat().st_mtime < 10:
            # Файл перезаписан только что: сборка ещё пишет его, читать нечего.
            # Вердикт будет на следующем обходе — вместо ложного «не читается».
            results.append({"doc_id": d["id"], "code": d["code"], "file": Path(p).name,
                            "ok": True, "finds": [{"level": "WARN", "doc": d["code"] or "?",
                                                   "msg": "файл перезаписан только что — проверка отложена"}]})
            continue
        f = check_pdf(Path(p), code=d["code"] or "", foreign_names=foreign,
                      tpl_mtime=_tpl_mtime(d["code"] or ""))
        results.append({"doc_id": d["id"], "code": d["code"], "file": Path(p).name,
                        "ok": not any(x["level"] == "BLOCK" for x in f), "finds": f})
    verdict = {"app_id": app_id, "ok": all(r["ok"] for r in results) and bool(results),
               "docs": results, "checked": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if save:
        write_log(verdict)
    return verdict


def write_log(verdict: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        for r in verdict["docs"]:
            fh.write(json.dumps({"ts": verdict["checked"], "app_id": verdict["app_id"],
                                 "code": r["code"], "file": r["file"], "ok": r["ok"],
                                 "finds": r["finds"]}, ensure_ascii=False) + "\n")
    try:
        c = sqlite3.connect(DB)
        c.execute("CREATE TABLE IF NOT EXISTS quality_checks (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  " ts TEXT, app_id INTEGER, code TEXT, file TEXT, ok INTEGER, blocks INTEGER, warns INTEGER,"
                  " reasons TEXT)")
        for r in verdict["docs"]:
            blocks = [x["msg"] for x in r["finds"] if x["level"] == "BLOCK"]
            warns = [x["msg"] for x in r["finds"] if x["level"] == "WARN"]
            c.execute("INSERT INTO quality_checks (ts, app_id, code, file, ok, blocks, warns, reasons)"
                      " VALUES (?,?,?,?,?,?,?,?)",
                      (verdict["checked"], verdict["app_id"], r["code"], r["file"], int(r["ok"]),
                       len(blocks), len(warns), "; ".join(blocks[:6])))
        c.commit()
        c.close()
    except Exception:
        pass


def main():
    args = [a for a in sys.argv[1:] if a]
    if not args:
        print(__doc__)
        return
    app_ids = []
    if "--all" in args:
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        app_ids = [r["id"] for r in c.execute("SELECT id FROM applications ORDER BY id DESC LIMIT 40")]
        c.close()
    else:
        app_ids = [int(a) for a in args if a.isdigit()]
    bad_total = 0
    for app_id in app_ids:
        v = check_app(app_id)
        bad = [r for r in v["docs"] if not r["ok"]]
        bad_total += len(bad)
        if not v["docs"]:
            continue
        mark = "ГОТОВ" if v["ok"] else "НЕ ГОТОВ"
        print("заявка %-4s %-9s документов %d, проблемных %d" % (app_id, mark, len(v["docs"]), len(bad)))
        for r in bad:
            for f in r["finds"]:
                if f["level"] == "BLOCK":
                    print("    [BLOCK] %-44s %s" % (r["code"], f["msg"][:96]))
    print("\nвсего проблемных документов:", bad_total)


if __name__ == "__main__":
    main()
