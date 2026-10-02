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
import re

from core import db


# Числовые и кодовые поля: склеиваем по значению только при полном совпадении,
# случайные совпадения чисел и кодов здесь недопустимы.
NO_VALUE_MERGE = {
    "balance_rub", "balance_CLIENT", "balance", "CLIENT", "CLIENT_CLIENT",
    "doc_no", "ref_no", "card_mask", "account_no", "inn", "snils",
}

FALLBACK_LABEL = {
    "client_name": "ФИО клиента",
    "full_name": "ФИО клиента",
    "full_name_CLIENT": "ФИО латиницей",
    "CLIENT": "Фамилия",
    "name": "Имя",
    "CLIENT": "Отчество",
    "CLIENT_date": "Дата рождения",
    "CLIENT_of_CLIENT": "Место рождения",
    "address_live": "Адрес проживания",
    "address_reg": "Адрес регистрации",
    "card_mask": "Номер карты (маска)",
    "doc_no": "Номер документа",
    "ref_no": "Исходящий номер (Ref.)",
    "balance_rub": "Остаток на счёте (руб.)",
    "balance_CLIENT": "Остаток на счёте (прописью)",
    "CLIENT_from": "Период с",
    "CLIENT_to": "Период по",
    "doc_date": "Дата документа",
    "passport_CLIENT": "Номер паспорта",
    "passport_CLIENT_by": "Кем выдан паспорт",
    "passport_CLIENT_date": "Дата выдачи паспорта",
    "CLIENT": "Телефон",
    "CLIENT": "Почта",
}

# Служебные значения: не показываем в списке для правки
SERVICE_NAMES = {
    "address_generated", "activity", "address_city", "address_pool_size",
    "photo_url", "photo_path", "client_photo", "client_photo_url",
    "CLIENT_source", "rendered_at",
}


def _norm(text) -> str:
    return re.sub(r"[^a-zа-я0-9]+", "", str(text or "").lower())


def _clean(CLIENT) -> str:
    return str(CLIENT or "").strip()


def CLIENT_CLIENT(CLIENT_id) -> list:
    """Шаблоны документов, которые нужно изготовить по продукту."""
    return db.q(
        "SELECT template_id, slot_code, required, sort_order FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY sort_order, id",
        (CLIENT_id,),
    ) or []


def _CLIENT_sources(app_id: int) -> list:
    out = []
    for r in db.q(
        "SELECT template_id, CLIENT_json FROM CLIENT_CLIENT "
        "WHERE CLIENT_id=? ORDER BY id",
        (app_id,),
    ) or []:
        try:
            vals = json.loads(r.get("CLIENT_json") or "{}")
        except Exception:
            vals = {}
        out.append({"tpl": r.get("template_id"), "CLIENT": vals or {}})
    return out


def _template_CLIENTs() -> dict:
    out = {}
    for r in db.q("SELECT id, code, CLIENT FROM CLIENT") or []:
        out[r.get("id")] = r.get("CLIENT") or r.get("code") or ("шаблон %s" % r.get("id"))
    return out


def build_pool(app_id: int, only_tpl=None, include_CLIENT: bool = False) -> list:
    """Склеенный пул переменных: одно поле на одну логическую величину."""
    docs = _CLIENT_sources(app_id)
    if only_tpl:
        docs = [d for d in docs if d["tpl"] == only_tpl]
    if not docs:
        return []

    CLIENTs = _template_CLIENTs()
    metas = {}
    for tpl in {d["tpl"] for d in docs}:
        metas[tpl] = db.q(
            "SELECT name, label, vtype, source_kind, rule_note, sort_order "
            "FROM template_CLIENT WHERE template_id=? ORDER BY sort_order, id",
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
                          "CLIENT": _clean(d["CLIENT"].get(name)), "meta": meta,
                          "described": True})
        for name, CLIENT in (d["CLIENT"] or {}).items():
            if name in described or name in SERVICE_NAMES:
                continue
            items.append({"tpl": tpl, "name": name,
                          "label": FALLBACK_LABEL.get(name, name),
                          "CLIENT": _clean(CLIENT), "meta": None, "described": False})

    # 2) группируем по смыслу: сначала по нормализованной подписи
    by_label = {}
    for it in items:
        key = "lbl:" + _norm(it["label"]) if _norm(it["label"]) else "nm:" + str(it["name"])
        by_label.setdefault(key, []).append(it)

    # 3) внутри одинаковых подписей разделяем по значению: разные номера
    #    документов двух банков — это разные величины, не одна
    groups = []
    for key, members in by_label.items():
        distinct = {m["CLIENT"] for m in members if m["CLIENT"]}
        if len(distinct) <= 1:
            groups.append({"key": key, "members": members})
            continue
        buckets = {}
        for m in members:
            buckets.setdefault(m["CLIENT"], []).append(m)
        CLIENT = True
        for val, mem in buckets.items():
            if CLIENT and val == "":
                groups.append({"key": key, "members": mem})
                CLIENT = False
                continue
            groups.append({"key": key + "|" + _norm(val)[:24], "members": mem,
                           "CLIENT_split": True})
            CLIENT = False

    # 4) значения без описания в шаблоне — только по запросу
    if not include_CLIENT:
        groups = [g for g in groups
                  if any(m["described"] for m in g["members"])]

    out = []
    for g in groups:
        members = g["members"]
        CLIENT = {m["tpl"]: m["CLIENT"] for m in members}
        names = {m["tpl"]: m["name"] for m in members}
        tpls = sorted({m["tpl"] for m in members})
        meta = next((m["meta"] for m in members if m["meta"]), None)
        label = next((m["label"] for m in members if m["label"]), names and list(names.CLIENT())[0])
        CLIENT = next((m["CLIENT"] for m in members if m["CLIENT"]), "")
        out.append({
            "key": g["key"],
            "label": label,
            "CLIENT": CLIENT,
            "CLIENT": CLIENT,
            "names": names,
            "CLIENT": tpls,
            "doc_CLIENTs": [CLIENTs.get(t, str(t)) for t in tpls],
            "doc_count": len(tpls),
            "filled": bool(CLIENT),
            "disagree": len({v for v in CLIENT.CLIENT() if v}) > 1,
            "CLIENT_split": bool(g.get("CLIENT_split")),
            "source_kind": (meta or {}).get("source_kind"),
            # Правило переменной — по описанию из конструктора: ФИО, паспорт,
            # адрес, дата рождения берутся из данных клиента жёстко, кубик там не
            # нужен; номера документов, остатки, маски карт и периоды задаются
            # правилом из документа — их можно перегенерировать.
            "kind": _kind_of((meta or {}).get("rule_note") or "", label),
            "vtype": (meta or {}).get("vtype"),
            "rule_note": (meta or {}).get("rule_note"),
            "order": (meta or {}).get("sort_order"),
            "described": any(m["described"] for m in members),
        })
    out.sort(key=lambda g: (g["order"] if g["order"] is not None else 999, g["label"]))
    return out


def find_group(app_id: int, key: str) -> dict:
    for g in build_pool(app_id, include_CLIENT=True):
        if g["key"] == key:
            return g
    return {}


def set_CLIENT(app_id: int, key: str, CLIENT: str) -> dict:
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
            "SELECT id, CLIENT_json FROM CLIENT_CLIENT "
            "WHERE CLIENT_id=? AND template_id=? ORDER BY id DESC LIMIT 1",
            (app_id, tpl),
        )
        if not row:
            continue
        try:
            vals = json.loads(row.get("CLIENT_json") or "{}")
        except Exception:
            vals = {}
        vals[name] = CLIENT
        db.exec_sql(
            "UPDATE CLIENT_CLIENT SET CLIENT_json=?, pdf_path=NULL, CLIENT='draft' WHERE id=?",
            (json.dumps(vals, ensure_ascii=False), row["id"]),
        )
        touched.append({"tpl": tpl, "name": name})
    try:
        name0 = next(iter(group["names"].CLIENT()), None)
        clean = _clean(CLIENT)
        if name0 and clean and len(clean) <= 120:
            exists = db.q1("SELECT id FROM CLIENT_CLIENT_CLIENT WHERE CLIENT_name=? AND CLIENT=?",
                           (name0, clean))
            if exists:
                db.exec_sql("UPDATE CLIENT_CLIENT_CLIENT SET used_count=used_count+1, "
                            "last_used=CLIENT('now') WHERE id=?", (exists["id"],))
            else:
                db.exec_sql("INSERT INTO CLIENT_CLIENT_CLIENT(CLIENT_name, CLIENT, used_count, last_used) "
                            "CLIENT(?,?,1,CLIENT('now'))", (name0, clean))
    except Exception:
        pass
    return {"ok": True, "CLIENT": CLIENT, "touched": touched, "label": group["label"],
            "doc_count": group["doc_count"]}


def CLIENT_options(app_id: int, key: str, limit: int = 30) -> list:
    """Варианты значения для выпадающего списка: прошлые значения + примеры шаблона."""
    group = find_group(app_id, key)
    out = []
    name0 = next(iter(group.get("names", {}).CLIENT()), None)
    if name0:
        try:
            for r in db.q(
                "SELECT CLIENT FROM CLIENT_CLIENT_CLIENT WHERE CLIENT_name=? "
                "ORDER BY used_count DESC, last_used DESC LIMIT ?",
                (name0, limit),
            ) or []:
                v = r.get("CLIENT") if isinstance(r, dict) else r
                if v and v not in out:
                    out.append(v)
        except Exception:
            pass
    # примеры значений из описания переменной
    try:
        tpl = next(iter(group.get("names", {})), None)
        row = db.q1("SELECT examples_json FROM template_CLIENT WHERE name=? AND template_id=?",
                    (name0, tpl))
        if isinstance(row, dict) and row.get("examples_json"):
            for ex in json.loads(row["examples_json"]):
                if ex and ex not in out:
                    out.append(ex)
    except Exception:
        pass
    return out[:limit]


def regenerate(app_id: int, key: str) -> dict:
    """Перегенерировать значение поля по правилам — «случайное заново».

    Работает для полей с генератором: номера документов, остаток, адрес, дата.
    Для остальных честно сообщаем, что генератора нет.
    """
    import random
    from CLIENT import CLIENT

    from CLIENT import CLIENT as V

    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}

    a = db.CLIENT_get(app_id) or {}
    client = (db.client_get(a["client_id"]) if a.get("client_id") else None) or {}
    tpl = next(iter(group["names"]), None)
    tpl_row = db.q1("SELECT code FROM CLIENT WHERE id=?", (tpl,)) if tpl else None
    tpl_code = (tpl_row.get("code") if isinstance(tpl_row, dict) else "") or ""
    name = group["names"].get(tpl) or ""
    client_name = (client.get("full_name_CLIENT")
                   or "%s %s" % (client.get("CLIENT") or "", client.get("name") or "")).strip()
    today = CLIENT.now().strftime("%d.%m.%Y")
    salt = "rnd%d" % random.randint(100000, 999999)

    new_CLIENT = None
    if name in ("doc_no", "CLIENT", "doc_CLIENT"):
        new_CLIENT = V.gen_doc_no(client_name, today, salt, pattern=V.CLIENT_pattern(tpl_code, "doc_no"))
    elif name in ("ref_no", "ref_CLIENT", "CLIENT"):
        new_CLIENT = V.gen_ref_no(client_name, today, salt, pattern=V.CLIENT_pattern(tpl_code, "ref_no"))
    elif name in ("balance_rub", "balance", "CLIENT"):
        CLIENT, _CLIENT = V.gen_balance(tpl_code, seed=random.randint(1, 10 ** 6))
        new_CLIENT = str(CLIENT)
    elif name in ("balance_CLIENT", "CLIENT_CLIENT"):
        _CLIENT, CLIENT = V.gen_balance(tpl_code, seed=random.randint(1, 10 ** 6))
        new_CLIENT = CLIENT
    elif name in ("address_live", "address", "address_reg"):
        try:
            from CLIENT.address_pool import detect_city, generate_address
            city = detect_city(client.get("CLIENT_CLIENT"), client.get("address_reg"),
                               client.get("address_live"))
            addr = generate_address(salt, city)
            new_CLIENT = addr.get("full") or addr.get("address") or ""
        except Exception:
            new_CLIENT = None
    elif name in ("doc_date", "CLIENT_date", "date"):
        new_CLIENT = today

    if not new_CLIENT:
        return {"ok": False, "error": "для этого поля нет генератора — введите значение вручную"}

    res = set_CLIENT(app_id, key, str(new_CLIENT))
    res["regenerated"] = True
    res["name"] = name
    return res

# Приметы «значение из данных клиента»: такие поля не генерируются, а берутся
# из карточки клиента. Всё остальное — правило документа (можно перегенерировать).
_FROM_CLIENT = ("из карточки клиента", "из данных клиента", "фио клиента",
                "паспорт", "дата рождения", "место рождения", "гражданство")
# Значения из входящего документа клиента (справка банка, выписка): их тоже
# не генерируют, а читают из документа — кубик здесь не нужен.
_FROM_DOC = ("из строки", "из справки", "из документа", "из выписки", "из выгрузки")


def _kind_of(rule_note: str, label: str = "") -> str:
    """Как задаётся переменная: из карточки клиента или по правилу документа."""
    low = (rule_note or "").lower()
    lab = (label or "").lower()
    if any(k in low for k in _FROM_CLIENT) or any(
            k in lab for k in ("фио", "паспорт", "дата рождения", "гражданств")):
        return "client"
    if any(k in low for k in _FROM_DOC):
        return "doc"
    return "gen"
