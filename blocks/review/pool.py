"""Пул переменных заявки: склейка одинаковых по смыслу полей разных документов.

Задача от заказчика: администратор не должен править одно и то же значение в
каждом документе отдельно. Если ФИО клиента встречается в шести документах под
шестью разными именами переменных — в правой панели это ОДНО поле, и правка
уходит во все документы сразу.

Как определяется «одно и то же»:

1. По подписи переменной (label): «ФИО клиента» в двух шаблонах — одна величина.
   Сравнение нормализованное: регистр, пробелы и знаки препинания не важны.
2. По имени переменной, если подпись не заполнена.
3. Дополнительно по совпадающему значению: разные подписи, но одинаковое непустое
   значение в разных документах — тоже одна величина.

Важное исключение: если подписи совпадают, а значения РАЗНЫЕ (например, «Номер
документа» у Т-Банка и у Сбера — это разные номера), величины не склеиваются.
Каждая показывается отдельно, с указанием своего документа. Иначе правка одного
номера переписала бы номер во втором банке.
"""
import json
from pathlib import Path
import time
import re

from core import db


# Зависимые переменные: считаются сами от других значений, в панели не показываются.
# Начало периода = дата оформления минус 3 или 12 месяцев; сумма прописью = из суммы
# цифрами; полная дата = из короткой. Руками их править нельзя — разъедутся.
DEPENDENT = {"period_from", "period_to", "balance_words", "date_full"}


# Числовые и кодовые поля: склеиваем по значению только при полном совпадении,
# случайные совпадения чисел и кодов здесь недопустимы.
NO_VALUE_MERGE = {
    "balance_rub", "balance_words", "balance", "amount", "amount_words",
    "doc_no", "ref_no", "card_mask", "account_no", "inn", "snils",
}

FALLBACK_LABEL = {
    "client_name": "ФИО клиента",
    "full_name": "ФИО клиента",
    "full_name_latin": "ФИО латиницей",
    "surname": "Фамилия",
    "name": "Имя",
    "patronymic": "Отчество",
    "birth_date": "Дата рождения",
    "place_of_birth": "Место рождения",
    "address_live": "Адрес проживания",
    "address_reg": "Адрес регистрации",
    "card_mask": "Номер карты (маска)",
    "doc_no": "Номер документа",
    "ref_no": "Исходящий номер (Ref.)",
    "balance_rub": "Остаток на счёте (руб.)",
    "balance_words": "Остаток на счёте (прописью)",
    "period_from": "Период с",
    "period_to": "Период по",
    "doc_date": "Дата документа",
    "passport_number": "Номер паспорта",
    "passport_issued_by": "Кем выдан паспорт",
    "passport_issue_date": "Дата выдачи паспорта",
    "phone": "Телефон",
    "email": "Почта",
}

# Служебные значения: не показываем в списке для правки
SERVICE_NAMES = {
    "address_generated", "activity", "address_city", "address_pool_size",
    "photo_url", "photo_path", "client_photo", "client_photo_url",
    "values_source", "rendered_at",
}


def _norm(text) -> str:
    return re.sub(r"[^a-zа-я0-9]+", "", str(text or "").lower())


def _clean(value) -> str:
    return str(value or "").strip()


def product_templates(product_id) -> list:
    """Шаблоны документов, которые нужно изготовить по продукту."""
    return db.q(
        "SELECT template_id, slot_code, required, sort_order FROM product_documents "
        "WHERE product_id=? ORDER BY sort_order, id",
        (product_id,),
    ) or []


def _value_sources(app_id: int) -> list:
    out = []
    for r in db.q(
        "SELECT template_id, values_json FROM application_documents "
        "WHERE application_id=? ORDER BY id",
        (app_id,),
    ) or []:
        try:
            vals = json.loads(r.get("values_json") or "{}")
        except Exception:
            vals = {}
        out.append({"tpl": r.get("template_id"), "values": vals or {}})
    return out


def _template_titles() -> dict:
    out = {}
    for r in db.q("SELECT id, code, title FROM templates") or []:
        out[r.get("id")] = r.get("title") or r.get("code") or ("шаблон %s" % r.get("id"))
    return out


def build_pool(app_id: int, only_tpl=None, include_service: bool = False) -> list:
    """Склеенный пул переменных: одно поле на одну логическую величину."""
    import time as _t
    _pk = ("pool", app_id, only_tpl, include_service)
    _ph = _POOL_CACHE.get(_pk)
    if _ph and (_t.time() - _ph[0]) < 30:
        return [dict(x) for x in _ph[1]]
    _pr = _build_pool_uncached(app_id, only_tpl, include_service)
    _POOL_CACHE[_pk] = (_t.time(), [dict(x) for x in _pr])
    return _pr


def _build_pool_uncached(app_id: int, only_tpl=None, include_service: bool = False) -> list:
    docs = _value_sources(app_id)
    if only_tpl:
        docs = [d for d in docs if d["tpl"] == only_tpl]
    if not docs:
        return []

    # Клиент нужен, чтобы понять источник значения (карточка клиента или документы)
    client_id = None
    try:
        _a = db.application_get(app_id) or {}
        client_id = _a.get("client_id")
    except Exception:
        client_id = None

    titles = _template_titles()
    metas = {}
    for tpl in {d["tpl"] for d in docs}:
        metas[tpl] = db.q(
            "SELECT name, label, vtype, source_kind, rule_note, sort_order "
            "FROM template_variables WHERE template_id=? ORDER BY sort_order, id",
            (tpl,),
        ) or []

    # 1) собираем все величины: (подпись, имя, документ, значение, описание)
    items = []
    for d in docs:
        tpl = d["tpl"]
        described = {m.get("name") for m in metas.get(tpl, [])}
        for meta in metas.get(tpl, []):
            name = meta.get("name")
            label = meta.get("label") or FALLBACK_LABEL.get(name, name)
            items.append({"tpl": tpl, "name": name, "label": label,
                          "value": _clean(d["values"].get(name)), "meta": meta,
                          "described": True})
        for name, value in (d["values"] or {}).items():
            if name in described or name in SERVICE_NAMES:
                continue
            items.append({"tpl": tpl, "name": name,
                          "label": FALLBACK_LABEL.get(name, name),
                          "value": _clean(value), "meta": None, "described": False})

    # 2) склеиваем только общие величины (ФИО, адрес, период). Всё, что относится
    #    к конкретному банку — номер карты, документа, счёта, остаток, Ref. —
    #    живёт отдельным полем у своего документа: у Сбера и Т-Банка они разные.
    by_label = {}
    for it in items:
        nm = str(it["name"] or "")
        if nm in DEPENDENT:
            # зависимая переменная: считается сама, в панели не нужна
            continue
        if nm in SHARED_NAMES:
            key = "sh:" + (_norm(it["label"]) or nm)
        else:
            # Внутри одного документа одинаковые по смыслу величины — одно поле:
            # «Номер документа» не должен появляться дважды.
            key = "own:%s:%s" % (it["tpl"], _norm(it["label"]) or nm)
        by_label.setdefault(key, []).append(it)

    # 3) внутри общих величин одинаковой подписи разделяем по значению: если
    #    адрес в документах разошёлся, это два разных поля, а не одно
    groups = []
    for key, members in by_label.items():
        if not key.startswith("sh:"):
            groups.append({"key": key, "members": members})
            continue
        distinct = {m["value"] for m in members if m["value"]}
        if len(distinct) <= 1:
            groups.append({"key": key, "members": members})
            continue
        buckets = {}
        for m in members:
            buckets.setdefault(m["value"], []).append(m)
        for val, mem in buckets.items():
            groups.append({"key": key + "|" + _norm(val)[:24], "members": mem,
                           "value_split": True})

    # 4) значения без описания в шаблоне — только по запросу
    if not include_service:
        groups = [g for g in groups
                  if any(m["described"] for m in g["members"])]

    out = []
    for g in groups:
        members = g["members"]
        values = {m["tpl"]: m["value"] for m in members}
        names = {m["tpl"]: m["name"] for m in members}
        tpls = sorted({m["tpl"] for m in members})
        meta = next((m["meta"] for m in members if m["meta"]), None)
        label = next((m["label"] for m in members if m["label"]), names and list(names.values())[0])
        value = next((m["value"] for m in members if m["value"]), "")
        out.append({
            "key": g["key"],
            "label": label,
            "value": value,
            "values": values,
            "names": names,
            "templates": tpls,
            "doc_titles": [titles.get(t, str(t)) for t in tpls],
            "doc_count": len(tpls),
            "filled": bool(value),
            "disagree": len({v for v in values.values() if v}) > 1,
            "value_split": bool(g.get("value_split")),
            "source_kind": (meta or {}).get("source_kind"),
            # Правило переменной — по описанию из конструктора: ФИО, паспорт,
            # адрес, дата рождения берутся из данных клиента жёстко, кубик там не
            # нужен; номера документов, остатки, маски карт и периоды задаются
            # правилом из документа — их можно перегенерировать.
            "kind": ("gen" if (names and list(names.values())[0] in ADDR_NAMES)
                     else _kind_of((meta or {}).get("rule_note") or "", label,
                                   names and list(names.values())[0] or "")),
            "vtype": (meta or {}).get("vtype"),
            "rule_note": (meta or {}).get("rule_note"),
            "order": (meta or {}).get("sort_order"),
            "described": any(m["described"] for m in members),
        })

    # Источник значения: из карточки клиента, из карточки заявки, из документов
    # Google Диска или сгенерировано. Подпись показывается под значением.
    docs_real = _docs_values(client_id)
    for g in out:
        nm = (list(g["names"].values()) or [""])[0]
        if g["kind"] == "client" or nm in ADDR_NAMES:
            g["src"] = SRC_CLIENT if g["filled"] else SRC_GEN
        elif g["kind"] == "shared":
            g["src"] = SRC_APP
        elif nm in DOC_NAMES:
            real = docs_real.get(nm)
            g["src"] = SRC_DOCS if (real and real == str(g["value"])) else SRC_GEN
        else:
            g["src"] = SRC_GEN

    # Приоритет — данные из документов на Google Диске. Если в анкете (карточке
    # клиента) стоит другое значение того же поля, показываем расхождение и
    # предлагаем администратору выбрать: подсветка поля + список вариантов.
    try:
        card = db.q1("SELECT * FROM clients WHERE id=?", (client_id,)) or {}
        doc_vals = _client_doc_values(client_id)
        for g in out:
            nm = (list(g["names"].values()) or [""])[0]
            if not nm:
                continue
            dv = doc_vals.get(nm) or doc_vals.get(CLIENT_ALIAS.get(nm, ""))
            cv = _clean(card.get(nm)) if (card and nm in card.keys()) else _clean(card.get(CLIENT_ALIAS.get(nm, "")))
            if not dv or not cv:
                continue
            if _norm(dv) == _norm(cv):
                continue
            g["conflict"] = {"doc": dv, "card": cv, "name": nm,
                             "from": (doc_vals.get("_from", {}).get(nm) or "")}
            # в бланк идёт значение из документа — оно приоритетнее анкеты
            if not g.get("chosen_from_card"):
                g["value"] = dv
                g["values"] = {t: dv for t in (g.get("templates") or [])}
                g["filled"] = True
                g["src"] = SRC_DOCS
    except Exception:
        pass
    # Разделы панели: сначала данные клиента и общие величины, затем документы —
    # каждый банк отдельным блоком под тонкой рамкой.
    for g in out:
        nm0 = (list(g["names"].values()) or [""])[0]
        if nm0 in ADDR_NAMES:
            # адрес — данные клиента, но с кубиком: если в карточке пусто, генерируем
            g["section"] = "Данные клиента"
            g["section_key"] = "client"
            g["list_allowed"] = False
            continue
        if g["kind"] == "client":
            g["section"] = "Данные клиента"
            g["section_key"] = "client"
        elif g["kind"] == "shared":
            g["section"] = "Общее для всех документов"
            g["section_key"] = "shared"
        else:
            title = (g["doc_titles"] or ["Документ"])[0]
            g["section"] = title
            g["section_key"] = "doc:%s" % ",".join(str(t) for t in g["templates"])
        # Список прошлых значений уместен для общих полей и данных клиента.
        # Номера документов, карт и счетов выбирать из истории не нужно.
        nm0 = (list(g["names"].values()) or [""])[0]
        g["list_allowed"] = (g["kind"] in ("client", "shared")
                             and nm0 not in ADDR_NAMES)

    def _section_rank(g):
        # Порядок блоков: данные клиента, общее, затем документы. Адрес попадает
        # в блок клиента, хотя у него есть кубик, — иначе блок «Данные клиента»
        # появлялся на экране дважды.
        return {"client": 0, "shared": 1}.get(g.get("section_key") or "", 2)

    # Сначала данные клиента, потом общие величины, затем документы — каждый
    # своим блоком (иначе поля Т-Банка и Сбера шли вперемешку).
    out.sort(key=lambda g: (_section_rank(g),
                            g.get("section_key") or "",
                            g["order"] if g["order"] is not None else 999,
                            g["label"]))
    return out


def mark_choice(app_id: int, key: str, source: str, value: str) -> None:
    """Запомнить выбор администратора: значение из документа или из анкеты.

    Пока выбор стоит, разбор документов не перезаписывает это поле — иначе
    решение человека затиралось бы при каждом заходе на заявку.
    """
    a = db.q1("SELECT client_id FROM applications WHERE id=?", (app_id,)) or {}
    cid = a.get("client_id")
    if not cid:
        return
    f = Path("/opt/wolf_v2/data/doc_values/client_%s.json" % cid)
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    groups = find_group(app_id, key) or {}
    nm = ((list((groups.get("names") or {}).values()) or [""])[0]) or key
    # Выбор администратора — тоже обучающий сигнал: запоминаем с приоритетом
    if value and len(_clean(value)) <= 120:
        _remember(nm, value, approved=True)
    if source == "card":
        data[nm] = {"value": value, "chosen": "card", "at": time.time()}
    else:
        cell = data.get(nm) or {}
        if isinstance(cell, str):
            cell = {"value": cell}
        cell.pop("chosen", None)
        cell["value"] = value
        data[nm] = cell
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def find_group(app_id: int, key: str) -> dict:
    for g in build_pool(app_id, include_service=True):
        if g["key"] == key:
            return g
    return {}


def _remember(name: str, value: str, approved: bool = False) -> None:
    """Запомнить формулировку: в следующий раз она предлагается администратору.

    approved=True — так решил человек. Такие значения получают приоритет при
    сборке следующих документов (система учится на подтверждённых вариантах).
    """
    try:
        db.remember_value(name, value, approved=approved)
    except Exception:
        pass


def set_value(app_id: int, key: str, value: str) -> dict:
    """Записать значение во все документы, где встречается эта величина.

    Документ помечается несобранным (pdf_path = NULL), чтобы при следующем
    просмотре он пересобрался с новым значением.
    """
    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}
    touched = []
    for tpl, name in group["names"].items():
        row = db.q1(
            "SELECT id, values_json FROM application_documents "
            "WHERE application_id=? AND template_id=? ORDER BY id DESC LIMIT 1",
            (app_id, tpl),
        )
        if not row:
            continue
        try:
            vals = json.loads(row.get("values_json") or "{}")
        except Exception:
            vals = {}
        vals[name] = value
        _remember(name, value, approved=True)
        # Подтверждённый (зафиксированный галочкой) документ не трогаем: он уже
        # сохранён в заявке вместе со своими значениями и не должен сбрасываться
        # при правке общей переменной — иначе галочка «слетает» сама по себе.
        db.exec_sql(
            "UPDATE application_documents SET values_json=?, pdf_path=NULL, status='draft' "
            "WHERE id=? AND IFNULL(status,'') NOT IN ('verified','sent')",
            (json.dumps(vals, ensure_ascii=False), row["id"]),
        )
        touched.append({"tpl": tpl, "name": name})
    try:
        # подтверждённое администратором значение запоминаем с повышенным весом:
        # при сборке следующих документов оно имеет приоритет над автогенерацией
        name0 = next(iter(group["names"].values()), None)
        clean = _clean(value)
        if name0 and clean and len(clean) <= 120:
            _remember(name0, clean, approved=True)
    except Exception:
        pass
    return {"ok": True, "value": value, "touched": touched, "label": group["label"],
            "doc_count": group["doc_count"]}


def _pool_name_ok(name: str) -> bool:
    """Поля, где уместен типовой пул вариантов из шаблона.

    Только формулировки: языки, навыки, степень, гражданство, периоды работы.
    Для ФИО, паспортов, адресов, номеров документов и дат примеры не подставляем —
    там значения всегда свои, и чужие подсказки в этих полях недопустимы.
    """
    n = (name or "").lower()
    if not n:
        return False
    bad = ("passport", "birth", "address", "phone", "email", "name", "card",
           "account", "inn", "snils", "doc_no", "ref_no", "letter_no", "permit",
           "itk", "expiry", "issue")
    if any(b in n for b in bad):
        return False
    good = ("cv_languages", "cv_skills", "cv_education_degree", "cv_nationality",
            "cv_job", "subject", "purpose", "duration", "terms", "notice",
            "currency", "compensation")
    return any(g in n for g in good)


def history_options(app_id: int, key: str, limit: int = 30) -> list:
    """Варианты значения для выпадающего списка: типовые из шаблона + прошлые значения."""
    group = find_group(app_id, key)
    out = []
    name0 = next(iter(group.get("names", {}).values()), None)

    # 1) Типовой пул из описания переменной («что подходит под это поле»).
    #    Показываем первым: администратор выбирает готовую формулировку вместо ввода.
    if name0 and _pool_name_ok(name0):
        try:
            row = db.q1("SELECT examples_json FROM template_variables WHERE name=? LIMIT 1",
                        (name0,))
            raw = (row or {}).get("examples_json") or "[]"
            for v in json.loads(raw):
                v = str(v).strip()
                if v and v not in out:
                    out.append(v)
        except Exception:
            pass

    # 2) Прошлые значения по заявкам.
    if name0:
        try:
            for r in db.q(
                "SELECT value FROM variable_value_history WHERE variable_name=? "
                "ORDER BY used_count DESC, last_used DESC LIMIT ?",
                (name0, limit),
            ) or []:
                v = r.get("value") if isinstance(r, dict) else r
                if v and v not in out:
                    out.append(v)
        except Exception:
            pass
    return out[:limit]


def names_with_history() -> set:
    """Имена переменных, у которых есть прошлые значения.

    Список открываем только для них: подставлять примеры из описания не нужно —
    от них в списках был бардак.
    """
    try:
        rows = db.q("SELECT DISTINCT variable_name FROM variable_value_history") or []
    except Exception:
        return set()
    out = set()
    for r in rows:
        nm = r.get("variable_name") if isinstance(r, dict) else r
        if nm:
            out.add(nm)
    return out



def regenerate(app_id: int, key: str, profession: str = "") -> dict:
    """Перегенерировать значение поля по правилам — «случайное заново».

    Работает для полей с генератором: номера документов, остаток, адрес, дата.
    Для остальных честно сообщаем, что генератора нет.
    """
    import random
    from datetime import datetime

    from services import values as V

    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}

    a = db.application_get(app_id) or {}
    client = (db.client_get(a["client_id"]) if a.get("client_id") else None) or {}
    tpl = next(iter(group["names"]), None)
    tpl_row = db.q1("SELECT code FROM templates WHERE id=?", (tpl,)) if tpl else None
    tpl_code = (tpl_row.get("code") if isinstance(tpl_row, dict) else "") or ""
    name = group["names"].get(tpl) or ""
    client_name = (client.get("full_name_latin")
                   or "%s %s" % (client.get("surname") or "", client.get("name") or "")).strip()
    today = datetime.now().strftime("%d.%m.%Y")
    salt = "rnd%d" % random.randint(100000, 999999)

    new_value = None
    if name in ("doc_no", "number", "doc_number"):
        new_value = V.gen_doc_no(client_name, today, salt, pattern=V.number_pattern(tpl_code, "doc_no"))
    elif name in ("ref_no", "ref_number", "reference"):
        new_value = V.gen_ref_no(client_name, today, salt, pattern=V.number_pattern(tpl_code, "ref_no"))
    elif name in ("balance_rub", "balance", "amount"):
        amount, _words = V.gen_balance(tpl_code, seed=random.randint(1, 10 ** 6))
        new_value = str(amount)
    elif name in ("balance_words", "amount_words"):
        _amount, words = V.gen_balance(tpl_code, seed=random.randint(1, 10 ** 6))
        new_value = words
    elif name.startswith("cv_") and name in ("cv_summary", "cv_job1_bullets",
                                             "cv_job2_bullets", "cv_skills_hard",
                                             "cv_job1_title", "cv_job1_company"):
        # Резюме: описание собирается по должности клиента (справочник должностей),
        # объём подбирается под формат — короткое / Сиваева / расширенное.
        from services import cv_gen
        # Профессию администратор может выбрать вручную — тогда описание
        # собирается по ней, а не по карточке клиента.
        gen = cv_gen.build_full(
            code=(profession or ""), level=cv_gen.level_for_template(tpl_code), client=client,
            company=client.get("company_name") or client.get("company_llc") or "")
        new_value = gen.get(name) or ""
    elif name in ("address_live", "address", "address_reg"):
        try:
            from services.address_pool import detect_city, generate_address
            city = detect_city(client.get("birth_place"), client.get("address_reg"),
                               client.get("address_live"))
            addr = generate_address(salt, city)
            new_value = addr.get("full") or addr.get("address") or ""
        except Exception:
            new_value = None
    elif name in ("card_mask", "card_no", "card", "card_number"):
        # Номер карты у каждого банка свой: кубик берёт набор БИН того банка,
        # к которому относится документ, — Сбер не получит карту Т-Банка.
        new_value = V.mask_card(None, tpl_code, seed=salt)
    elif name in ("account_no", "account", "account_number"):
        import random as _r
        new_value = "".join(_r.choice("0123456789") for _ in range(20))
    elif name in ("doc_date", "issue_date", "date"):
        new_value = today

    if not new_value:
        return {"ok": False, "error": "для этого поля нет генератора — введите значение вручную"}

    res = set_value(app_id, key, str(new_value))
    res["regenerated"] = True
    res["name"] = name
    res["value"] = str(new_value)   # интерфейс подставляет значение прямо в поле
    return res

# Приметы «значение из данных клиента»: такие поля не генерируются, а берутся
# из карточки клиента. Всё остальное — правило документа (можно перегенерировать).
# Величины, одинаковые для всех документов заявки: их держим одним полем.
# Номера карт, документов и счетов сюда не входят — они принадлежат банку,
# у Сбера и Т-Банка это разные значения.
# Адрес: если в карточке клиента его нет — генерируется кнопкой 🎲.
# Выпадающий список адресу не нужен: выбирать из прошлых адресов нечего.
ADDR_NAMES = {"address_live", "address_reg", "address_registration",
              "employee_address", "home_address"}

# Откуда взято значение — это подпись под полем. Порядок подписи одинаковый
# у всех переменных: название, значение, источник.
SRC_CLIENT = "из карточки клиента"
SRC_APP = "из карточки заявки"
SRC_DOCS = "из документов Google Диска"
SRC_GEN = "сгенерировано"

# Значения, которые берутся из входящих документов клиента, а не выдумываются.
# Как имя переменной конструктора соотносится с полем карточки клиента
CLIENT_ALIAS = {"date_of_birth": "birth_date", "birth_date": "birth_date",
                "full_name": "full_name_latin", "name_latin": "name",
                "surname_latin": "surname", "mobile": "phone", "tel": "phone",
                "bank": "bank_name", "account": "account_no", "card": "card_mask",
                "balance": "balance_rub", "passport": "passport_number"}


def _client_doc_values(client_id) -> dict:
    """Значения, вытащенные из документов клиента на Google Диске (и их источник)."""
    out = {}
    froms = {}
    if not client_id:
        return out
    try:
        f = Path("/opt/wolf_v2/data/doc_values/client_%s.json" % client_id)
        if not f.exists():
            return out
        data = json.loads(f.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            val = v.get("value") if isinstance(v, dict) else v
            if val:
                out[k] = str(val)
                if isinstance(v, dict) and v.get("from"):
                    froms[k] = str(v.get("from"))
    except Exception:
        return out
    out["_from"] = froms
    return out


DOC_NAMES = {"doc_no", "number", "doc_number", "ref_no", "ref_number", "reference",
             "card_mask", "card_no", "card", "card_number", "account_no", "account",
             "account_number", "balance_rub", "balance", "amount", "period_from",
             "period_to"}


_POOL_CACHE = {}


def _docs_values(client_id) -> dict:
    """Реальные значения из документов клиента (Google Диск): номера, карта, остаток.

    Чтение PDF клиента идёт с диска и разбирается постранично (176 страниц за
    одно открытие). Кэш на 2 минуты: переключение документов в заявке больше
    не перечитывает всё заново (Андрей, 17.10.2026: «очень долго подгружает»).
    """
    import time as _t
    if not client_id:
        return {}
    _key = ("dv", client_id)
    _hit = _POOL_CACHE.get(_key)
    if _hit and (_t.time() - _hit[0]) < 120:
        return dict(_hit[1])
    _res = _docs_values_uncached(client_id)
    _POOL_CACHE[_key] = (_t.time(), dict(_res))
    return _res


def _docs_values_uncached(client_id) -> dict:
    out = {}
    if not client_id:
        return out
    try:
        from services import values as V
    except Exception:
        return out
    for fn, key in ((getattr(V, "read_client_doc_numbers", None), None),
                    (getattr(V, "read_client_card_mask", None), "card_mask"),
                    (getattr(V, "read_client_bank_amount", None), "balance_rub")):
        if not fn:
            continue
        try:
            got = fn(client_id)
        except Exception:
            continue
        if isinstance(got, dict):
            out.update({k: str(v) for k, v in got.items() if v})
        elif key and got:
            out[key] = str(got)
    return out


SHARED_NAMES = {
    "client_name", "client_fio", "fio", "name_latin", "surname", "name", "patronymic",
    "birth_date", "birth_place", "citizenship", "passport_no", "passport_number",
    "passport_date", "passport_issued", "inn", "phone", "email",
    "address_live", "address_reg", "period_from", "period_to", "doc_date",
    "contract_date", "product_name", "visa_type", "entry_date",
}

_FROM_CLIENT = ("из карточки клиента", "из данных клиента", "фио клиента",
                "паспорт", "дата рождения", "место рождения", "гражданство")
# Значения из входящего документа клиента (справка банка, выписка): их тоже
# не генерируют, а читают из документа — кубик здесь не нужен.
_FROM_DOC = ("из строки", "из справки", "из документа", "из выписки", "из выгрузки")


def _kind_of(rule_note: str, label: str = "", name: str = "") -> str:
    """Как задаётся переменная.

    client — берётся из карточки клиента (жёстко, без кубика и без списка);
    shared — одинаковая для всех документов (период, дата): можно выбрать из
             прошлых значений;
    gen    — номер карты, документа, счёта, остаток, Ref: у каждого банка своё,
             значение перевыпускается кубиком 🎲.
    """
    low = (rule_note or "").lower()
    lab = (label or "").lower()
    if name in SHARED_NAMES:
        if any(k in low for k in _FROM_CLIENT) or any(
                k in lab for k in ("фио", "паспорт", "дата рождения", "гражданств",
                                   "адрес")):
            return "client"
        return "shared"
    if any(k in low for k in _FROM_CLIENT) or any(
            k in lab for k in ("фио", "паспорт", "дата рождения", "гражданств")):
        return "client"
    return "gen"

def phrases(app_id: int, key: str, profession: str = "") -> dict:
    """Готовые фразы («кусочки») для поля резюме: из пула профессии и из истории.

    Администратор отмечает нужные — из них собирается текст описания.
    """
    from services import cv_gen
    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}
    tpl = next(iter(group["names"]))
    name = group["names"][tpl]
    app_row = db.application_get(app_id) or {}
    client = db.client_get(app_row.get("client_id")) or {}
    code = profession or (cv_gen.resolve_profession(client) or {}).get("code") or ""
    items = []
    try:
        items = cv_gen.position_phrases(code, name) or []
    except Exception:
        items = []
    history = []
    try:
        history = db.get_suggestions(name, 30) or []
    except Exception:
        history = []
    seen = {i.strip().lower() for i in items}
    for h in history:
        v = (h.get("value") or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            items.append(v)
    # пары для «кусочков»: администратор читает русский вариант,
    # в документ подставляется английский
    try:
        pairs = cv_gen.position_phrases_pairs(code, name) if code else []
    except Exception:
        pairs = []
    known = {p["en"] for p in pairs}
    for h in history:
        v = (h.get("value") or "").strip()
        if v and v not in known:
            pairs.append({"en": v, "ru": v})
            known.add(v)
    return {"ok": True, "key": key, "profession": code, "items": items[:60], "pairs": pairs[:60],
            "history": [{"value": (h.get("value") or ""), "used": h.get("used_count") or 0}
                        for h in history[:20]]}


def gen_scratch(app_id: int, key: str, profession: str = "") -> dict:
    """Собрать описание «с нуля»: фразы по профессии, которых ещё не было в работе.

    Готовый текст сразу запоминается — если администратор его примет, в следующий
    раз он предлагается первым.
    """
    from services import cv_gen
    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}
    tpl = next(iter(group["names"]))
    name = group["names"][tpl]
    app_row = db.application_get(app_id) or {}
    client = db.client_get(app_row.get("client_id")) or {}
    code = profession or (cv_gen.resolve_profession(client) or {}).get("code") or ""
    if not code:
        return {"ok": False, "error": "профессия не определена — выберите её из списка"}

    level = cv_gen.level_for_template(tpl_code_of(group)) or "medium"
    used = set()
    try:
        for h in (db.get_suggestions(name, 50) or []):
            for line in (h.get("value") or "").split("\n"):
                if line.strip():
                    used.add(line.strip().lower())
    except Exception:
        used = set()

    all_ph = cv_gen.position_phrases(code, name) or []
    prof = [x for x in all_ph if not x.startswith("•")]
    bullets = [x for x in all_ph if x.startswith("•")]
    fresh_b = [b for b in bullets if b.strip().lower() not in used] or bullets
    limit = {"short": 2, "medium": 3, "long": 5}.get(level, 3)

    if "summary" in name or "profile" in name:
        # «кубик рандома»: описание собирается из нескольких предложений пула,
        # уже использованные формулировки уходят в конец очереди
        n_sent = {"short": 2, "medium": 3, "long": 4}.get(level, 3)
        text = (cv_gen.summary_random(code, n=n_sent, avoid=used)
                or cv_gen.summary_for(code) or (prof[0] if prof else ""))
    elif "skill" in name:
        p = cv_gen.position_by_code(code) or {}
        text = p.get("skills", "")
    else:
        text = "\n".join(fresh_b[:limit])
    if not text:
        return {"ok": False, "error": "нет готовых фраз для этой профессии"}
    res = set_value(app_id, key, text)
    res["regenerated"] = True
    res["from_scratch"] = True
    res["name"] = name
    res["value"] = text
    return res


def tpl_code_of(group: dict) -> str:
    """Код шаблона — по нему определяется нужный объём описания."""
    try:
        tid = next(iter(group["names"]))
        row = db.q1("SELECT code FROM templates WHERE id=?", (tid,))
        return (row or {}).get("code", "") or ""
    except Exception:
        return ""


def add_profession(title: str) -> dict:
    """Добавить профессию, которой нет в справочнике: генератор сразу умеет по ней писать.

    Профессия сохраняется в пул — дальше она доступна в списке у всех заявок.
    """
    from services import cv_gen
    t = cv_gen.clean_position(title)
    if not t:
        return {"ok": False, "error": "название профессии пустое"}
    try:
        out = cv_gen.add_custom_position(t)
        return {"ok": True, "code": out.get("code"), "title": t}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}
