"""Дополнительная проверка: сопоставить наши документы с документами менеджера.

Запуск:  python3 scripts/compare_with_manager.py <app_id> [--png]

Что делает:
 1) берёт папку клиента из заявки (applications.gdrive_url) и читает её через Drive API;
 2) отделяет документы менеджера (лежали раньше) от нашей папки «Wolf AutoDoc*»;
 3) сопоставляет пары по типу документа (справка банка / договор / письмо / резюме);
 4) сверяет смысловые сущности: ФИО, паспорт, дата рождения, должность, суммы, организация,
    номера и даты; выводит совпадения и расхождения;
 5) по ключу --png склеивает первые страницы «наш | менеджер» в картинку для зрительной сверки.

Ничего не меняет: только чтение с Диска и локальных сборок.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

import pymupdf  # noqa: E402

from services import gdrive_api  # noqa: E402

DB = "/opt/wolf_v2/data/wolf.db"
OUT = Path("/tmp/compare_app")
TYPE_HINTS = [
    ("bank_statement", ("bank", "statement", "balance", "справк", "personal", "tbank", "sber", "yandex")),
    ("remote_work_agreement", ("remote work", "remote_work", "rwa", "kitas")),
    ("employment_contract", ("employment", "contract", "договор")),
    ("cv", ("cv", "resume", "резюме")),
    ("letter", ("letter", "письмо", "bridging", "conversion", "e02", "sponsor")),
]
ENTITIES = {
    "паспорт": r"\b\d{2}\s?\d{2}\s?\d{6}\b",
    "ИНН": r"\b(?:ИНН|INN)[:\s]*(\d{10,12})",
    "сумма": r"\b\d[\d\s.,]{4,}\s?(?:rub|rubles|RUB|руб)",
    "дата": r"\b\d{2}[./]\d{2}[./]\d{4}\b",
    "год": r"\b20\d{2}\b",
}


def doc_type(name: str, text: str) -> str:
    blob = (name + " " + text[:1200]).lower()
    for kind, hints in TYPE_HINTS:
        if any(h in blob for h in hints):
            return kind
    return "прочее"


def text_of(path: Path) -> str:
    try:
        d = pymupdf.open(path)
        return "\n".join(d[p].get_text() for p in range(min(d.page_count, 6)))
    except Exception:
        return ""


def entities(text: str) -> dict:
    out = {}
    for name, pat in ENTITIES.items():
        vals = re.findall(pat, text, flags=re.I)
        vals = [v if isinstance(v, str) else v[0] for v in vals]
        out[name] = sorted({re.sub(r"\s+", " ", v).strip() for v in vals if v})
    return out


def main() -> None:
    app_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    want_png = "--png" in sys.argv
    out_dir = OUT.with_name("compare_app%d" % app_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    app = c.execute("SELECT id, client_id, gdrive_url, created_at, status, product_id "
                    "FROM applications WHERE id=?", (app_id,)).fetchone()
    if not app:
        raise SystemExit("заявка не найдена")
    cl = c.execute("SELECT * FROM clients WHERE id=?", (app["client_id"],)).fetchone()
    client = dict(cl) if cl else {}
    folder = (app["gdrive_url"] or client.get("gdrive_folder_url") or "").strip()
    print("заявка #%d | клиент: %s | папка клиента: %s" % (
        app_id, (client.get("full_name") or "—"), folder or "— (ссылки нет)"))
    if not folder:
        raise SystemExit("в заявке нет ссылки на папку клиента")

    files = gdrive_api.list_files(folder, deep=True)
    ours, theirs = [], []
    for f in files:
        name = (f.get("name") or "")
        path = (f.get("path") or "")
        if "Wolf AutoDoc" in name or "Wolf AutoDoc" in path:
            ours.append(f)
        elif name.lower().endswith((".pdf", ".docx", ".doc")):
            theirs.append(f)
    print("файлов на Диске: %d | наших: %d | менеджера: %d" % (len(files), len(ours), len(theirs)))

    # наши документы: локальные сборки заявки, а если файлов нет — наша папка на Диске
    our_docs = []
    for r in c.execute("""SELECT t.code, t.title, ad.pdf_path FROM application_documents ad
                          JOIN templates t ON t.id=ad.template_id
                          WHERE ad.application_id=?""", (app_id,)):
        p = Path(r["pdf_path"] or "")
        if r["pdf_path"] and p.exists():
            our_docs.append({"code": r["code"], "name": p.name, "path": p})
    if not our_docs:
        for f in ours:
            nm = (f.get("name") or "")
            if not nm.lower().endswith(".pdf"):
                continue
            dest = out_dir / ("our_" + nm)
            if not dest.exists() and not gdrive_api.download(f["id"], dest):
                continue
            our_docs.append({"code": doc_type(nm, ""), "name": nm, "path": dest})
    print("наших собранных документов: %d" % len(our_docs))

    # менеджерские — скачиваем; в имени держим id, иначе два файла с одинаковым названием
    # на Диске затирают друг друга и сравнение идёт «сам с собой»
    mgr_docs = []
    for f in theirs:
        safe = re.sub(r"[^\w.\- ]+", "_", (f.get("name") or "file"))
        dest = out_dir / ("%s_%s" % (f["id"][:8], safe))
        if not dest.exists():
            ok = gdrive_api.download(f["id"], dest)
            if not ok:
                print("  ! не скачался: %s" % f.get("name"))
                continue
        mgr_docs.append({"id": f["id"], "name": f.get("name") or dest.name, "path": dest})
    # наши копии, оказавшиеся в папке клиента, из менеджерских исключаем
    our_blobs = [text_of(d["path"])[:400] for d in our_docs]
    mgr_docs = [d for d in mgr_docs
                if not any(b and b == text_of(d["path"])[:400] for b in our_blobs)]
    print("документов менеджера к сравнению: %d" % len(mgr_docs))

    def layout_stats(path):
        """Шрифты и вёрстка первой страницы: чем набран текст и как он разложен."""
        out = {}
        try:
            doc = pymupdf.open(path)
            pg = next((p for p in doc if p.get_text().strip()), doc[0])
            fonts, sizes, xs, ys, ys_prev = {}, {}, [], [], None
            lead = []
            for b in pg.get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    lxs = [s["bbox"][0] for s in line["spans"]]
                    lys = [s["bbox"][1] for s in line["spans"]]
                    if not lxs:
                        continue
                    xs += [min(lxs), max(s["bbox"][2] for s in line["spans"])]
                    y = min(lys)
                    if ys_prev is not None and 0 < (y - ys_prev) < 40:
                        lead.append(y - ys_prev)
                    ys_prev = y
                    ys.append(y)
                    for s in line["spans"]:
                        if not s["text"].strip():
                            continue
                        key = (s["font"], round(s["size"], 2), "bold" if "Bold" in s["font"] else "")
                        fonts[key] = fonts.get(key, 0) + len(s["text"].strip())
                        sizes[round(s["size"], 2)] = sizes.get(round(s["size"], 2), 0) + 1
            out = {
                "шрифты": ["%s %.2fpt%s — %d зн." % (f[0], f[1], (" " + f[2]) if f[2] else "", n)
                           for f, n in sorted(fonts.items(), key=lambda kv: -kv[1])[:6]],
                "кегли": ["%.2fpt×%d" % (s, n) for s, n in sorted(sizes.items(), key=lambda kv: -kv[1])[:6]],
                "текстовый_блок_pt": [round(min(xs), 1), round(max(xs), 1)] if xs else [],
                "отступ_строк_pt": round(sum(lead) / len(lead), 2) if lead else None,
                "строк": len(ys),
                "лист_pt": [round(pg.rect.width, 1), round(pg.rect.height, 1)],
            }
        except Exception as e:  # noqa: BLE001
            out = {"ошибка": str(e)[:80]}
        return out

    def layout_diff(ours, mgr):
        """Что в вёрстке и шрифтах расходится с документом менеджера."""
        if ours.get("ошибка") or mgr.get("ошибка"):
            return {"ошибка": ours.get("ошибка") or mgr.get("ошибка")}
        diff = {}
        if ours.get("шрифты") and mgr.get("шрифты"):
            of = {x.split(" — ")[0].strip() for x in ours["шрифты"]}
            mf = {x.split(" — ")[0].strip() for x in mgr["шрифты"]}
            if not (of & mf):
                diff["шрифты"] = {"наш": ours["шрифты"][:3], "менеджер": mgr["шрифты"][:3]}
        osz = {float(x.split("pt")[0]) for x in ours.get("кегли", [])}
        msz = {float(x.split("pt")[0]) for x in mgr.get("кегли", [])}
        if osz and msz and not (osz & msz):
            diff["кегли"] = {"наш": ours["кегли"][:4], "менеджер": mgr["кегли"][:4]}
        ob, mb = ours.get("текстовый_блок_pt") or [], mgr.get("текстовый_блок_pt") or []
        if ob and mb:  # заметный сдвиг полей/ширины набора
            if abs(ob[0] - mb[0]) > 4 or abs(ob[1] - mb[1]) > 8:
                diff["поля_текста"] = {"наш": ob, "менеджер": mb}
        ol, ml = ours.get("отступ_строк_pt"), mgr.get("отступ_строк_pt")
        if ol and ml and abs(ol - ml) > 1.2:
            diff["межстрочный"] = {"наш": ol, "менеджер": ml}
        return diff

    report = {"app_id": app_id, "client": client.get("full_name"), "pairs": [], "only_ours": [],
              "only_manager": []}
    used = set()
    for od in our_docs:
        otext = text_of(od["path"])
        otype = doc_type(od["code"], otext)
        match = None
        for md in mgr_docs:
            if md["id"] in used:
                continue
            mtext = text_of(md["path"])
            if doc_type(md["name"], mtext) == otype:
                match = md
                break
        if not match:
            report["only_ours"].append({"наш": od["code"], "тип": otype})
            continue
        used.add(match["id"])
        mtext = text_of(match["path"])
        oe, me = entities(otext), entities(mtext)
        diff = {}
        for k in ENTITIES:
            only_o = [v for v in oe[k] if v not in me[k]]
            only_m = [v for v in me[k] if v not in oe[k]]
            if only_o or only_m:
                diff[k] = {"только_у_нас": only_o[:6], "только_у_менеджера": only_m[:6]}
        report["pairs"].append({
            "тип": otype,
            "наш_файл": od["name"],
            "файл_менеджера": match["name"],
            "символов_наш": len(otext), "символов_менеджер": len(mtext),
            "расхождения": diff,
        })
        ldiff = layout_diff(layout_stats(od["path"]), layout_stats(match["path"]))
        report["pairs"][-1]["вёрстка"] = ldiff
        if ldiff:
            print("   шрифты/вёрстка — расхождения:")
            for k, v in ldiff.items():
                if isinstance(v, dict):
                    print("      %s: наш=%s | менеджер=%s" % (k, v.get("наш"), v.get("менеджер")))
                else:
                    print("      %s: %s" % (k, v))
        else:
            print("   шрифты/вёрстка: основные признаки совпадают")
        if want_png:
            try:
                d1, d2 = pymupdf.open(od["path"]), pymupdf.open(match["path"])
                # страницу менеджера берём первую непустую: в сканах бывает пустой лист-обложка
                pg2 = next((i for i in range(d2.page_count) if d2[i].get_text().strip()
                            or d2[i].get_images()), 0)
                pg1 = next((i for i in range(d1.page_count) if d1[i].get_text().strip()
                            or d1[i].get_images()), 0)
                p1 = d1[pg1].get_pixmap(dpi=110)
                p2 = d2[pg2].get_pixmap(dpi=110)
                # приводим оба к одному цветовому пространству: иначе вторая страница
                # вклеивается прозрачной и на картинке выглядит пустой
                if p1.alpha or p1.colorspace != pymupdf.csRGB:
                    p1 = pymupdf.Pixmap(pymupdf.csRGB, p1)
                if p2.alpha or p2.colorspace != pymupdf.csRGB:
                    p2 = pymupdf.Pixmap(pymupdf.csRGB, p2)
                w = p1.width + p2.width + 20
                h = max(p1.height, p2.height)
                sheet = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h))
                sheet.set_rect(sheet.irect, (255, 255, 255))
                sheet.copy(p1, pymupdf.IRect(0, 0, p1.width, p1.height))
                sheet.copy(p2, pymupdf.IRect(p1.width + 20, 0, p1.width + 20 + p2.width, p2.height))
                png = out_dir / ("side_%s.png" % otype)
                sheet.save(str(png))
                print("   картинка: %s (наш стр.%d | менеджер стр.%d, всего у менеджера %d)"
                      % (png, pg1 + 1, pg2 + 1, d2.page_count))
            except Exception as e:  # noqa: BLE001
                print("   ! картинка не собралась: %s" % str(e)[:90])
    for md in mgr_docs:
        if md["id"] not in used:
            report["only_manager"].append({"файл_менеджера": md["name"],
                                           "тип": doc_type(md["name"], text_of(md["path"]))})

    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n=== сопоставление ===")
    for p in report["pairs"]:
        print("\n[%s] наш: %s | менеджер: %s" % (p["тип"], p["наш_файл"], p["файл_менеджера"]))
        if not p["расхождения"]:
            print("   расхождений по сущностям нет")
        for k, v in p["расхождения"].items():
            print("   %s: только у нас %s | только у менеджера %s"
                  % (k, v["только_у_нас"][:4], v["только_у_менеджера"][:4]))
    if report["only_ours"]:
        print("\nбез пары у менеджера:", report["only_ours"])
    if report["only_manager"]:
        print("без пары у нас:", report["only_manager"])
    print("\nотчёт:", out_dir / "report.json")


main()
