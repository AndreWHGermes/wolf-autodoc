"""Легенда клиента: связная модель человека, а не набор переменных.

Зачем. Механическая подстановка значений не понимает, ЧТО за документ мы делаем.
Из-за этого адрес в Индонезии попадал в банковскую справку, а русское название
организации — в английский договор.

Что делает модуль:
  1. Читает распознанные факты по всем документам клиента
     (data/doc_values/client_<id>.json — каждый факт со ссылкой на файл-источник).
  2. Раскладывает факты по слоям: личность, дом в РФ, пребывание в Индонезии,
     работа/доход, реквизиты.
  3. Строит временную линию (что выдано когда) и решает, какой адрес актуален.
  4. Отсекает OCR-мусор (например «Kkkkkkkkkkkk» из MRZ).
  5. Выдаёт адрес нужного типа под конкретный документ.

Ключевое правило (от заказчика):
  - документы, которые выдаёт РФ (справка банка, договор, резюме), —
    берут адрес проживания/регистрации в РОССИИ;
  - документы для индонезийской иммиграции (письма, E-02) —
    берут адрес проживания в ИНДОНЕЗИИ.
  Банк РФ не может выдать справку человеку с балийским адресом: он не в России.

Хранение: data/legends/client_<id>.json  (+ таблица client_legends, если есть)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_VALUES = ROOT / "data" / "doc_values"
LEGENDS = ROOT / "data" / "legends"

# ─── какие документы берут какой адрес ───────────────────────────────────────
# РФ-документы: справка банка, договор, резюме
RU_DOC_PREFIXES = (
    "bank_statement",
    "employment_contract",
    "remote_work_agreement",
    "cv__",
    "cv_",
)
# Иммиграционные документы: письма, E-02, D12
ID_DOC_PREFIXES = (
    "bridging_request_letter",
    "conversion_request_letter",
    "d12_cover_letter",
    "statement_letter_e02",
    "itk",
    "e02",
)

# ─── слои легенды ────────────────────────────────────────────────────────────
# имя факта в doc_values -> (слой, поле)
LAYERS = {
    # личность
    "full_name_ru": ("identity", "full_name_ru"),
    "full_name_latin": ("identity", "full_name_latin"),
    "surname": ("identity", "surname"),
    "name": ("identity", "name"),
    "surname_latin": ("identity", "surname_latin"),
    "name_latin": ("identity", "name_latin"),
    "birth_date": ("identity", "birth_date"),
    "date_of_birth": ("identity", "birth_date"),
    "birth_place": ("identity", "birth_place"),
    "place_of_birth": ("identity", "birth_place"),
    "citizenship": ("identity", "citizenship"),
    "nationality": ("identity", "citizenship"),
    "client_gender": ("identity", "gender"),
    "passport_number": ("identity", "passport_no"),
    "passport_no": ("identity", "passport_no"),
    "passport_country": ("identity", "passport_country"),
    "passport_expiry": ("identity", "passport_expiry"),
    "passport_valid_until": ("identity", "passport_expiry"),
    # дом в России
    "address_live": ("home", "address"),
    "address_reg": ("home", "address_reg"),
    "address_registration": ("home", "address_reg"),
    # Индонезия
    "address_in_indonesia": ("indonesia", "address"),
    "permit_no": ("indonesia", "permit_no"),
    "itk_no": ("indonesia", "permit_no"),
    "stay_permit_no": ("indonesia", "permit_no"),
    "permit_expiry": ("indonesia", "permit_expiry"),
    "itk_expiry": ("indonesia", "permit_expiry"),
    "stay_permit_expiry": ("indonesia", "permit_expiry"),
    "visa_no": ("indonesia", "visa_no"),
    "visa_type": ("indonesia", "visa_type"),
    "bridging_visa_no": ("indonesia", "bridging_visa_no"),
    # деньги
    "bank_name": ("finance", "bank"),
    "balance_rub": ("finance", "balance"),
    "balance_date": ("finance", "balance_date"),
    # работа
    "company_name_in_quotes": ("work", "organization"),
    "org_name": ("work", "organization"),
    "position_title": ("work", "position"),
    "annual_amount_numeric": ("work", "annual_amount"),
    "monthly_amount_numeric": ("work", "monthly_amount"),
}

# события для временной линии
TIMELINE_KEYS = {
    "passport_issue_date": "выдан паспорт",
    "passport_expiry": "истекает паспорт",
    "balance_date": "выдана справка банка",
    "doc_date": "выдана справка банка",
    "permit_expiry": "истекает разрешение на пребывание",
    "itk_expiry": "истекает разрешение на пребывание",
    "date_of_issue": "выдан документ",
}


def _is_garbage(value: str) -> bool:
    """OCR-мусор из MRZ: 'Kkkkkkkkkkkk', '=====', пустое.
    Признак — один и тот же символ повторяется подряд 4+ раз,
    либо нет ни одной гласной в длинном латинском слове."""
    if not value:
        return True
    s = str(value).strip()
    if len(s) < 2:
        return True
    if re.search(r"(.)\1{3,}", s):          # kkkk, 0000, IIII
        return True
    if re.fullmatch(r"[<>\-=_.\s]+", s):     # только разделители MRZ
        return True
    letters = re.sub(r"[^A-Za-zА-Яа-я]", "", s)
    if len(letters) >= 8 and not re.search(r"[AEIOUYaeiouyАЕИОУЫЭЮЯаеиоуыэюя]", letters):
        return True
    return False


def _kind_of(source: str) -> str:
    """Тип файла-источника по имени (грубо, для временной линии)."""
    name = (source or "").lower()
    if "паспорт" in name or "passport" in name:
        return "passport"
    if "остат" in name or "bank" in name or "выписк" in name:
        return "bank"
    if name.startswith("itk") or "itk" in name:
        return "itk"
    if name.startswith("viza") or "visa" in name or "виза" in name:
        return "visa"
    if "foto" in name or "photo" in name:
        return "photo"
    return "other"


def _facts(client_id: int) -> dict:
    """Распознанные факты клиента: {имя: {'value','from','at'}}."""
    for cand in (DOC_VALUES / f"client_{client_id}.json",
                 DOC_VALUES / f"{client_id}.json"):
        if cand.exists():
            try:
                return json.loads(cand.read_text(encoding="utf-8")) or {}
            except Exception:
                return {}
    return {}


def _val(facts: dict, *names: str) -> tuple:
    """Первое непустое и не мусорное значение среди имён. -> (value, source)"""
    for n in names:
        rec = facts.get(n)
        if isinstance(rec, dict):
            v, src = rec.get("value"), rec.get("from") or ""
        elif rec is not None:
            v, src = rec, ""
        else:
            continue
        if v and not _is_garbage(v):
            return str(v).strip(), src
    return "", ""


def doc_takes_address(tpl_code: str) -> str:
    """Какой адрес нужен документу: 'ru' | 'id' | ''."""
    code = (tpl_code or "").lower()
    if code.startswith(ID_DOC_PREFIXES):
        return "id"
    if code.startswith(RU_DOC_PREFIXES):
        return "ru"
    return ""


def build(client_id: int, app_id: int | None = None, client: dict | None = None,
          product_code: str | None = None) -> dict:
    """Собрать легенду клиента из распознанных документов и карточки.

    `product_code` — продукт заявки. Легенда строится ПО ЕГО ТРЕБОВАНИЯМ: если
    иммиграция не спрашивает место работы и доход (продление C1), этих полей в
    легенде нет вообще — иначе они выглядели бы дефицитом, который надо
    закрывать, и клиент читал бы про себя лишнее.
    """
    import sqlite3

    from services import requirements as _req

    req = _req.for_product(product_code)
    facts = _facts(client_id)
    legacy = {}

    # карточка клиента — источник «уже проверенных» значений
    if client is None:
        try:
            db = ROOT / "data" / "wolf.db"
            conn = sqlite3.connect(db, timeout=60)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            client = dict(row) if row else {}
            conn.close()
        except Exception:
            client = {}

    legend = {
        "client_id": client_id,
        "app_id": app_id,
        "identity": {},
        "home": {},
        "indonesia": {},
        "finance": {},
        "work": {},
        "timeline": [],
        "gaps": [],
        "contradictions": [],
        "provenance": {},
    }

    # 1. факты из документов
    for key, (layer, field) in LAYERS.items():
        v, src = _val(facts, key)
        if v and not legend[layer].get(field):
            legend[layer][field] = v
            legend["provenance"][f"{layer}.{field}"] = src

    # 2. карточка клиента добирает то, чего нет в документах (и уточняет)
    card_map = {
        ("identity", "full_name_ru"): ("full_name_title", "full_name", "surname"),
        ("identity", "full_name_latin"): ("full_name_latin",),
        ("identity", "birth_date"): ("birth_date",),
        ("identity", "birth_place"): ("birth_place",),
        ("identity", "citizenship"): ("citizenship",),
        ("identity", "passport_no"): ("passport_number",),
        ("identity", "passport_expiry"): ("passport_expiry", "passport_valid_to"),
        ("identity", "gender"): ("gender",),
        ("home", "address"): ("address_reg",),
        ("indonesia", "address"): ("address_live",),
        ("finance", "bank"): ("bank_name",),
    }
    for (layer, field), keys in card_map.items():
        if legend[layer].get(field):
            continue
        for k in keys:
            v = client.get(k)
            if v and not _is_garbage(v):
                legend[layer][field] = str(v).strip()
                legend["provenance"][f"{layer}.{field}"] = "карточка клиента"
                break

    # 3. развести адреса: индонезийский в карточке не должен стать домашним
    from services.doc_parse import is_indonesia_address, is_russian_address

    home = legend["home"].get("address", "")
    if home and is_indonesia_address(home) and not legend["indonesia"].get("address"):
        legend["indonesia"]["address"] = home
        legend["home"]["address"] = ""
        legend["provenance"]["indonesia.address"] = legend["provenance"].get("home.address", "")

    idn = legend["indonesia"].get("address", "")
    if idn and is_russian_address(idn):
        legend["contradictions"].append(
            "адрес Индонезии оказался российским — проверьте распознавание")

    if legend["home"].get("address") and not is_russian_address(legend["home"]["address"]):
        legend["contradictions"].append(
            "домашний адрес не похож на российский: %s" % legend["home"]["address"][:60])

    # 4. временная линия (события одного дня и одного смысла не дублируем:
    # «истекает ВНЖ/ИТК» и «истекает ИТК» — это одно событие)
    seen_events = set()
    for key, what in TIMELINE_KEYS.items():
        v, src = _val(facts, key)
        if not v:
            continue
        mark = (re.sub(r"\D", "", str(v)), what)   # 20/10/2026 и 20.10.2026 — один день
        if mark in seen_events:
            continue
        seen_events.add(mark)
        legend["timeline"].append({"date": v, "what": what, "source": src})
    legend["timeline"].sort(key=lambda e: str(e["date"])[-4:])

    # 4.2 оба адреса — из единого источника: карточка клиента приоритетнее
    # обрезанных фрагментов распознавания (в документах адрес часто обрывается:
    # «JL. PANTAI MUNGGU NO. , MUNGGU, KEC. MENGWI, KABUPATEN» без улицы и дома)
    try:
        from services import addresses as _AD
        _pair = _AD.client_addresses(client, client_id)
        if _pair.get("ru"):
            legend.setdefault("home", {})["address"] = _pair["ru"]
            legend["home"]["source"] = "карточка клиента / документы"
        if _pair.get("id"):
            legend.setdefault("indonesia", {})["address"] = _pair["id"]
            legend["indonesia"]["source"] = _pair.get("id_source") or "карточка"
    except Exception:
        pass

    # 4.1 остаток, который попадёт в документ: клиент должен рассказывать
    # именно те цифры, что стоят в справке, а не свои реальные
    # Клиентская справка о движении средств может не проходить порог (у 93: 488 руб.,
    # это ~6 $). По правилу заказчика такую сумму мы подставляем, поэтому в легенде
    # должна стоять сумма НАШЕЙ справки — иначе документ и легенда расходятся.
    try:
            from services import package as _pack
            from services.values import bank_amount_for
            tpl = _pack.statement_template(client_id)
            if tpl:
                amt = bank_amount_for(client_id, tpl)
                if amt:
                    legend["finance"]["balance"] = str(amt)
                    legend["provenance"]["finance.balance"] = "справка собирается системой"
    except Exception:
        pass

    # ФИО: у разбора паспорта рвётся отчество (у 93 — «ЬЕВИЧ») и латиница выходит
    # мусором. Если карточка даёт полные три части — берём её.
    try:
        _s3 = str(client.get("surname") or "").strip()
        _n3 = str(client.get("name") or "").strip()
        _p3 = str(client.get("patronymic") or "").strip()
        if _s3 and _n3 and _p3 and not _is_garbage(_p3) and len(_p3) > 4:
            legend.setdefault("identity", {})["full_name_ru"] = " ".join((_s3, _n3, _p3))
            legend["provenance"]["identity.full_name_ru"] = "карточка клиента"
    except Exception:
        pass

    # 4.2 Работа: организация, должность, годы и доход — те же значения, что стоят
    # в договоре и контракте. Без этого рассказ клиенту не из чего собрать.
    try:
        from services import values as _v9
        _tpl9 = "remote_work_agreement__default"
        _v9v = _v9.build_template_values(client, _tpl9, app_id=app_id) or {}
        _w = legend.setdefault("work", {})
        _w["company"] = str(_v9v.get("company_full_name") or _v9v.get("company_name") or "").strip()
        _w["position"] = str(_v9v.get("position_title") or _v9v.get("position")
                            or (client or {}).get("position")
                            or (client or {}).get("position_ru") or "").strip()
        if not _w["position"]:
            _w["position"] = str(_v9v.get("cv_job1_title") or "").strip()
        if not _w["position"]:
            # должность берём прямо из карточки заявки — надёжнее, чем через словари значений
            try:
                import sqlite3 as _sq3
                _cn3 = _sq3.connect("/opt/wolf_v2/data/wolf.db", timeout=30)
                _rw3 = _cn3.execute("SELECT position FROM clients WHERE id=?", (client_id,)).fetchone()
                _cn3.close()
                _w["position"] = str((_rw3[0] if _rw3 else "") or "").strip()
            except Exception:
                pass
        _w["term_start"] = str(_v9v.get("term_start_date") or "").strip()
        _w["term_end"] = str(_v9v.get("term_end_date") or "").strip()
        _w["salary_year"] = str(_v9v.get("annual_amount_numeric") or "").strip()
        _w["salary_month"] = str(_v9v.get("monthly_amount_numeric") or "").strip()
        _w["contract_no"] = str(_v9v.get("contract_no") or "").strip()
        _w["remote"] = "полностью удалённо, вне Индонезии"
        # образование и прошлое место работы — из резюме: рассказ клиенту идёт по датам
        try:
            _cv9 = _v9.build_template_values(client, "cv__format_CLIENT", app_id=app_id) or {}
            _w["school"] = str(_cv9.get("cv_education_school") or "").strip()
            _w["degree"] = str(_cv9.get("cv_education_degree") or "").strip()
            _w["edu_years"] = str(_cv9.get("cv_education_years") or "").strip()
            _w["job2_company"] = str(_cv9.get("cv_job2_company") or "").strip()
            _w["job2_title"] = str(_cv9.get("cv_job2_title") or "").strip()
            _w["job1_period"] = str(_cv9.get("cv_job1_period") or "").strip()
        except Exception:
            pass
    except Exception:
        pass

    # 4.2б Итоговые суммы: в легенде должны стоять те же цифры, что в документах,
    # а не клиентские (клиентская справка в пакет не идёт — вместо неё наша).
    try:
        from services import values as _v7
        _cl7 = {
            "id": client_id,
        }
        _bank_amount = _v7.bank_amount_for(client_id, "bank_statement_12m__tbank")
        if _bank_amount:
            _num7 = str(_bank_amount).replace("\xa0", "").replace(" ", "").replace(",", ".")
            try:
                _f7 = float(_num7)
                legend.setdefault("finance", {})["balance"] = "{:,.2f}".format(_f7)
                legend.setdefault("finance", {})["bank"] = (
                    legend.get("finance", {}).get("bank") or "TBANK")
            except Exception:
                pass
    except Exception:
        pass

    # 4.3 Должность — отдельным шагом и вне общего try: внутри блока 4.2 она терялась,
    # и рассказ клиенту шёл без строки о работе.
    try:
        _w3 = legend.setdefault("work", {})
        if not str(_w3.get("position") or "").strip():
            _pos3 = ""
            try:
                import sqlite3 as _sq4
                _cn4 = _sq4.connect("/opt/wolf_v2/data/wolf.db", timeout=30)
                _rw4 = _cn4.execute("SELECT position FROM clients WHERE id=?",
                                    (client_id,)).fetchone()
                _cn4.close()
                _pos3 = str((_rw4[0] if _rw4 else "") or "").strip()
            except Exception:
                pass
            if not _pos3:
                try:
                    from services import values as _v3
                    _vv3 = _v3.build_template_values(client, "remote_work_agreement__default",
                                                    app_id=app_id) or {}
                    _pos3 = str(_vv3.get("position_title") or _vv3.get("position") or "").strip()
                except Exception:
                    pass
            if _pos3:
                _w3["position"] = _pos3
    except Exception:
        pass

    # 5. дефициты — ТОЛЬКО по требованиям продукта, и пакет документов,
    # который клиент получит на руки вместе с легендой.
    legend["product"] = req.get("code")
    legend["product_label"] = req.get("label")
    legend["product_note"] = req.get("note") or ""

    labels = {
        ("identity", "full_name_latin"): "ФИО латиницей (как в паспорте)",
        ("identity", "birth_date"): "дата рождения",
        ("identity", "citizenship"): "гражданство",
        ("identity", "passport_no"): "номер паспорта",
        ("identity", "passport_expiry"): "срок действия паспорта",
        ("home", "address"): "адрес проживания в РФ",
        ("indonesia", "address"): "адрес проживания в Индонезии",
        ("indonesia", "permit_no"): "номер ВНЖ/ИТК",
        ("indonesia", "permit_expiry"): "срок действия ВНЖ/ИТК",
        ("finance", "balance"): "подтверждение средств (остаток на счёте)",
        ("work", "organization"): "организация-работодатель",
        ("work", "position"): "должность",
        ("work", "annual_amount"): "подтверждение годового дохода",
    }
    for layer_field in req.get("fields") or []:
        layer, _, field = layer_field.partition(".")
        if not legend.get(layer, {}).get(field):
            legend["gaps"].append(
                {"field": layer_field, "what": labels.get((layer, field), layer_field)})

    # поля, которых продукт не требует, из легенды убираем: легенда — это то,
    # что клиент рассказывает иммиграции, лишнего в ней быть не должно
    for layer_field in req.get("not_needed") or []:
        layer, _, field = layer_field.partition(".")
        if field in (legend.get(layer) or {}) and layer_field not in (req.get("fields") or []):
            legend[layer][field] = ""
            legend["provenance"].pop("%s.%s" % (layer, field), None)

    # документы, которые реально пойдут в иммиграцию (из набора продукта)
    legend["docs"] = _package_docs(req.get("code"), app_id, client_id)
    legend["docs_excluded"] = _package_excluded(req.get("code"), client_id)
    # Имена файлов документов пакета + реальные документы клиента (копия паспорта, фото):
    # легенда — инструкция клиенту, он должен видеть, как называются файлы на руках.
    try:
        from services.render import doc_filename as _dfn
        from services import values as _v8
        _files, _extra = {}, []
        _cl8 = legend.get("client") or {}
        if not _cl8:
            import sqlite3 as _sq8
            _cn8 = _sq8.connect("/opt/wolf_v2/data/wolf.db", timeout=30)
            _cn8.row_factory = _sq8.Row
            _r8 = _cn8.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            _cl8 = dict(_r8) if _r8 else {}
            _cn8.close()
        _docs8 = legend.get("docs") or []
        if not _docs8:
            try:
                from services import package as _pk8
                _docs8 = _pk8.selected(str(legend.get("product") or ""), client_id) or []
                legend["docs"] = _docs8
            except Exception:
                _docs8 = []
        for _d in _docs8:
            _code = _d.get("code") or ""
            try:
                _vals8 = _v8.build_template_values(_cl8, _code, app_id=app_id) or {}
                _files[_code] = _dfn(_d.get("title") or _code, _vals8, ".pdf", _code)
            except Exception:
                pass
        _fio = str(_cl8.get("full_name_latin") or "").strip()
        _pass = str(_cl8.get("passport_number") or "").strip()
        _dt = str(legend.get("date") or "").strip()
        if not _dt:
            try:
                import sqlite3 as _sq9
                _cn9 = _sq9.connect("/opt/wolf_v2/data/wolf.db", timeout=30)
                _r9 = _cn9.execute("SELECT created_at FROM applications WHERE id=?", (app_id,)).fetchone()
                _cn9.close()
                _d9 = str((_r9[0] if _r9 else "") or "")[:10]
                _dt = ".".join(reversed(_d9.split("-"))) if _d9 else ""
            except Exception:
                pass
        for _title, _nm in (("Копия заграничного паспорта", "Passport copy"),
                            ("Фотография клиента", "Photo")):
            _pat = "passport" if "паспорт" in _title.lower() else None
            _dir8 = "/opt/wolf_v2/data/gdrive_cache/client_%s" % client_id
            import os as _os8
            if _os8.path.isdir(_dir8):
                for _f8 in sorted(_os8.listdir(_dir8)):
                    _l8 = _f8.lower()
                    if _pat and _l8.startswith("passport"):
                        _extra.append({"title": _title, "file": "%s %s %s %s" % (_nm, _fio, _pass, _dt)})
                        break
                    if not _pat and (_l8.startswith("foto") or _l8.startswith("photo")):
                        _extra.append({"title": _title, "file": "%s %s %s %s" % (_nm, _fio, _pass, _dt)})
                        break
        legend["doc_files"] = _files
        legend["extra_docs"] = _extra
    except Exception:
        pass

    legend["docs_note"] = (
        "Это полный пакет для подачи. Всё, что не перечислено, в иммиграцию "
        "не подаётся.")

    return legend


def _package_docs(product_code: str | None, app_id: int | None,
                  client_id: int | None = None) -> list:
    """Документы пакета: [{code, title, slot}] — что клиент получит на руки.

    Берём итоговый пакет продукта (services.package): один документ на слот,
    лишние варианты (справка банка, которого у клиента нет) выключены.
    """
    try:
        from services import package as _pack
        return _pack.selected(product_code or "", client_id)
    except Exception:
        return []


def _package_excluded(product_code: str | None, client_id: int | None) -> list:
    """Что выключили из пакета и почему — клиент видит, чего подавать не будут."""
    try:
        from services import package as _pack
        return _pack.excluded(product_code or "", client_id)
    except Exception:
        return []


def save(legend: dict) -> Path:
    LEGENDS.mkdir(parents=True, exist_ok=True)
    p = LEGENDS / f"client_{legend['client_id']}.json"
    p.write_text(json.dumps(legend, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load(client_id: int) -> dict:
    p = LEGENDS / f"client_{client_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def address_for(client_id: int, tpl_code: str) -> str:
    """Адрес, который должен стоять в этом документе."""
    kind = doc_takes_address(tpl_code)
    lg = load(client_id) or build(client_id)
    if kind == "ru":
        return lg.get("home", {}).get("address", "")
    if kind == "id":
        return lg.get("indonesia", {}).get("address", "")
    return ""


def _position_from_db(legend: dict) -> str:
    """Должность берём прямо из карточки клиента: в слоях легенды она терялась."""
    import sqlite3 as _sq
    _cid = None
    try:
        _cid = legend.get("client_id")
    except Exception:
        _cid = None
    _nm = str((legend.get("identity") or {}).get("full_name_latin") or "").strip()
    _cn = _sq.connect("/opt/wolf_v2/data/wolf.db", timeout=30)
    _r = None
    try:
        if _cid:
            _r = _cn.execute("SELECT position FROM clients WHERE id=?", (_cid,)).fetchone()
        if (not _r or not _r[0]) and _nm:
            _r = _cn.execute(
                "SELECT position FROM clients WHERE full_name_latin LIKE ? ORDER BY id DESC LIMIT 1",
                ("%" + _nm.split()[0] + "%",)).fetchone()
    finally:
        _cn.close()
    return str((_r[0] if _r else "") or "").strip()


def render_docx(legend: dict, path) -> str:
    """Легенда печатным документом: A4, обычный шрифт, заголовки разделов жирным.

    TXT клиент может не распечатать ровно — в Word формат A4 и шрифт заданы жёстко.
    """
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    text = render(legend)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)      # A4
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(2.0))
    sec.top_margin = sec.bottom_margin = Cm(1.5)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    heads = ("РАССКАЗ КЛИЕНТА", "ГДЕ ЭТО НАПИСАНО", "ДОКУМЕНТЫ ПАКЕТА",
             "ЗАМЕНЕНО", "ЛИЧНОСТЬ", "АДРЕС", "ИНДОНЕЗИЯ", "СРЕДСТВА",
             "РАБОТА И ДОХОД", "ВРЕМЕННАЯ ЛИНИЯ", "ПАКЕТ ДОКУМЕНТОВ")
    for line in text.split("\n"):
        ln = line.rstrip()
        p_ = doc.add_paragraph()
        body = ln.strip()
        if any(body.startswith(h) for h in heads):
            run = p_.add_run(body)
            run.bold = True
        else:
            p_.add_run(ln)
        p_.paragraph_format.space_after = Pt(2)
        if body.startswith("  -") or body.startswith("      файл:"):
            p_.paragraph_format.left_indent = Cm(0.6)
    doc.save(str(path))
    return str(path)


def render(legend: dict) -> str:
    try:
        _w2 = legend.setdefault("work", {})
        if not str(_w2.get("position") or "").strip():
            _p2 = _position_from_db(legend)
            if _p2:
                _w2["position"] = _p2
    except Exception:
        pass
    """Человекочитаемая легенда: её печатают и дают клиенту в руки.

    Клиент читает и понимает, какой у него пакет документов, как он связан и что
    он рассказывает иммиграции. Поэтому здесь только то, что требует продукт.
    """
    L = legend
    idn, home, ido, fin, work = (L.get("identity") or {}, L.get("home") or {},
                                 L.get("indonesia") or {}, L.get("finance") or {},
                                 L.get("work") or {})
    out = ["ЛЕГЕНДА КЛИЕНТА #%s — %s" % (L.get("client_id"), L.get("product_label") or "продукт не опознан")]
    if L.get("product_note"):
        out.append("  (%s)" % L["product_note"])

    # РАССКАЗ — то, что клиент читает и запоминает про себя. Собран только из
    # фактических значений, которые уходят в документы комплекта, чтобы рассказ
    # и документы не расходились.
    try:
        _nm = idn.get("full_name_latin") or idn.get("full_name_ru") or ""
        _nat = idn.get("citizenship") or ""
        _bd = idn.get("birth_date") or ""
        _pp = idn.get("passport_no") or ""
        _org = work.get("company") or ""
        _pos = work.get("position") or ""
        _ts = work.get("term_start") or ""
        _te = work.get("term_end") or ""
        _sy = work.get("salary_year") or ""
        _sm = work.get("salary_month") or ""
        _bank = fin.get("bank") or ""
        _bal = fin.get("balance") or ""
        _ru = home.get("address") or ""
        _idn = ido.get("address") or ""
        story = []
        _nat_ru = str(_nat or "").strip()
        if _nat_ru.upper().startswith(("РОССИЙСК", "RUSSIAN", "ROSSIYS", "РФ")):
            _nat_ru = "Российской Федерации"
        if _nm:
            story.append("Меня зовут %s%s%s." % (
                _nm,
                (", я гражданин %s" % _nat_ru) if _nat_ru else "",
                (", дата рождения %s" % _bd) if _bd else ""))
        if _pp:
            story.append("Мой паспорт: %s." % _pp)
        if _ru:
            story.append("Постоянно проживаю в России по адресу: %s." % _ru)
        if _org and _pos:
            line = "Я работаю в организации %s на должности %s" % (_org, _pos)
            if _ts:
                line += ", сотрудничаю с %s" % _ts
            if _te:
                line += ", действующий контракт заключён до %s" % _te
            story.append(line + ".")
        if _sy or _sm:
            money = []
            if _sm:
                money.append("%s руб. в месяц" % _sm)
            if _sy:
                money.append("%s руб. в год" % _sy)
            story.append("Мой доход — %s; его выплачивает работодатель%s." % (
                " и ".join(money),
                (" (%s)" % _org) if _org else ""))
        if work.get("school"):
            _ed = "Учился в %s" % work["school"]
            if work.get("edu_years"):
                _ed += " (%s)" % work["edu_years"]
            if work.get("degree"):
                _ed += ", специальность: %s" % work["degree"]
            story.append(_ed + ".")
        if work.get("job2_company"):
            story.append("До этого работал в %s%s." % (
                work["job2_company"],
                (" на должности %s" % work["job2_title"]) if work.get("job2_title") else ""))
        if _bal:
            try:
                _bal_f = "{:,.0f}".format(float(str(_bal).replace(",", "").replace(" ", ""))).replace(",", " ")
            except Exception:
                _bal_f = str(_bal)
            story.append("Деньги приходят на счёт в %s, остаток по счёту — %s руб." % (
                _bank or "банке", _bal_f))
        if _idn:
            story.append("В Индонезии я буду проживать по адресу: %s." % _idn)
        story.append("Работа полностью удалённая: я не работаю на индонезийские компании, "
                     "не оказываю услуги индонезийским заказчикам и не получаю доход "
                     "из источников в Индонезии.")
        if story:
            out.append("")
            out.append("РАССКАЗ КЛИЕНТА (прочитать и запомнить)")
            for _st in story:
                out.append("  %s" % _st)
            out.append("")
            out.append("ГДЕ ЭТО НАПИСАНО В ДОКУМЕНТАХ")
            out.append("  Работа, должность, срок контракта и доход — в договоре с организацией "
                       "и в трудовом контракте.")
            out.append("  Образование и предыдущие места работы — в резюме (CV).")
            out.append("  Остаток на счёте и банк — в банковской справке.")
    except Exception:
        pass

    row = []
    if idn.get("full_name_ru") or idn.get("full_name_latin"):
        row.append("  ФИО: %s / %s" % (idn.get("full_name_ru", "—"), idn.get("full_name_latin", "—")))
    if idn.get("birth_date") or idn.get("birth_place"):
        row.append("  Рождение: %s%s" % (
            idn.get("birth_date", "—"),
            (", " + idn["birth_place"]) if idn.get("birth_place") else ""))
    if idn.get("citizenship"):
        row.append("  Гражданство: %s" % idn["citizenship"])
    if idn.get("passport_no"):
        row.append("  Паспорт: %s, действует до %s" % (
            idn.get("passport_no"), idn.get("passport_expiry") or "—"))
    if row:
        out.append("ЛИЧНОСТЬ")
        out.extend(row)

    if home.get("address"):
        out.append("АДРЕС В РОССИИ — %s" % home["address"])

    row = []
    if ido.get("address"):
        row.append("  Адрес в Индонезии: %s" % ido["address"])
    if ido.get("permit_no"):
        row.append("  Разрешение на пребывание: %s, до %s" % (
            ido["permit_no"], ido.get("permit_expiry") or "—"))
    if row:
        out.append("ИНДОНЕЗИЯ")
        out.extend(row)

    row = []
    if fin.get("bank"):
        row.append("  Банк: %s" % fin["bank"])
    if fin.get("balance"):
        _b = str(fin["balance"])
        try:
            _num = float(re.sub(r"[^\d.]", "", _b.replace(",", "")))
            _b = "{:,.2f}".format(_num).replace(",", " ").replace(".", ",")
        except Exception:                                          # noqa: BLE001
            pass
        row.append("  Остаток на счёте: %s руб." % _b)
    if row:
        out.append("СРЕДСТВА")
        out.extend(row)

    if work.get("company") or work.get("position"):
        out.append("РАБОТА И ДОХОД")
        if work.get("company"):
            out.append("  Организация: %s" % work["company"])
        if work.get("position"):
            out.append("  Должность: %s" % work["position"])
        if work.get("term_start"):
            out.append("  Работает с: %s" % work["term_start"])
        if work.get("term_end"):
            out.append("  Контракт действует до: %s" % work["term_end"])
        if work.get("salary_month") or work.get("salary_year"):
            out.append("  Доход: %s руб./мес, %s руб./год" % (
                work.get("salary_month") or "—", work.get("salary_year") or "—"))

    if L.get("timeline"):
        out.append("ХРОНОЛОГИЯ")
        for e in L["timeline"]:
            out.append("  %s — %s" % (e["date"], e["what"]))

    if L.get("docs"):
        out.append("ПОРТФЕЛЬ ДОКУМЕНТОВ (это и есть подача)")
        for i, d in enumerate(L["docs"], 1):
            out.append("  %d. %s" % (i, d.get("title") or d.get("code")))
        # Что подаём и что заменили: клиент должен видеть, что его справка о движении
    # средств в пакет не идёт, а вместо неё подготовлена справка об остатке.
    # Портфель документов: в легенде перечисляем ВСЁ, что клиент печатает и подаёт,
    # с реальными именами файлов — чтобы он понимал, что у него на руках.
    _docs = L.get("docs") or []
    _files = L.get("doc_files") or {}
    if _docs:
        out.append("")
        out.append("ДОКУМЕНТЫ ПАКЕТА (что подаётся и как называются файлы)")
        for _d in _docs:
            _t = _d.get("title") or _d.get("code") or ""
            _f = _files.get(_d.get("code") or "") or ""
            if _t:
                out.append("  - %s%s" % (_t, ("\n      файл: %s" % _f) if _f else ""))
    for _extra in (L.get("extra_docs") or []):
        out.append("  - %s\n      файл: %s" % (_extra.get("title"), _extra.get("file")))
    _ex = L.get("docs_excluded") or []
    if _ex:
        out.append("")
        out.append("ЗАМЕНЕНО (вместо этих документов подготовлены другие)")
        for _d in _ex:
            _t = str(_d.get("title") or _d.get("code") or "")
            _r = str(_d.get("reason") or "").strip()
            if "движени" in _t.lower() or "bank" in str(_d.get("code") or "").lower():
                out.append("  - %s — не подаётся; вместо неё в пакет идёт банковская "
                           "справка об остатке на счёте" % _t)
            else:
                out.append("  - %s%s" % (_t, (" — %s" % _r) if _r else " — не подаётся"))

    if L.get("docs_note"):
            out.append("  %s" % L["docs_note"])

    if L.get("docs_excluded"):
        out.append("НЕ ПОДАЁТСЯ (выключено из пакета)")
        for d in L["docs_excluded"]:
            out.append("  - %s — %s" % (d.get("title") or d.get("code"), d.get("reason", "")))

    # Разделы «нужно уточнить у клиента» и «расхождения» в текст легенды не печатаем:
    # легенду клиент читает и запоминает, а данные и разбор остаются в системе.
    return "\n".join(out)


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m services.legend <client_id> [--save]")
        return
    cid = int(sys.argv[1])
    lg = build(cid)
    print(render(lg))
    if "--save" in sys.argv:
        print("\nсохранено: %s" % save(lg))


if __name__ == "__main__":
    main()
