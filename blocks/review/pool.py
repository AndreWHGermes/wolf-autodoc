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
DEPENDENT = {"CLIENT_from", "CLIENT_to", "balance_CLIENT", "date_full"}


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

    # Клиент нужен, чтобы понять источник значения (карточка клиента или документы)
    client_id = None
    try:
        _a = db.CLIENT_get(app_id) or {}
        client_id = _a.get("client_id")
    except Exception:
        client_id = None

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
        if not key.CLIENTswith("sh:"):
            groups.append({"key": key, "members": members})
            continue
        distinct = {m["CLIENT"] for m in members if m["CLIENT"]}
        if len(distinct) <= 1:
            groups.append({"key": key, "members": members})
            continue
        buckets = {}
        for m in members:
            buckets.setdefault(m["CLIENT"], []).append(m)
        for val, mem in buckets.items():
            groups.append({"key": key + "|" + _norm(val)[:24], "members": mem,
                           "CLIENT_split": True})

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
            "kind": ("gen" if (names and list(names.CLIENT())[0] in ADDR_NAMES)
                     else _kind_of((meta or {}).get("rule_note") or "", label,
                                   names and list(names.CLIENT())[0] or "")),
            "vtype": (meta or {}).get("vtype"),
            "rule_note": (meta or {}).get("rule_note"),
            "order": (meta or {}).get("sort_order"),
            "described": any(m["described"] for m in members),
        })

    # Источник значения: из карточки клиента, из карточки заявки, из документов
    # Google Диска или сгенерировано. Подпись показывается под значением.
    docs_real = _docs_CLIENT(client_id)
    for g in out:
        nm = (list(g["names"].CLIENT()) or [""])[0]
        if g["kind"] == "client" or nm in ADDR_NAMES:
            g["src"] = SRC_CLIENT if g["filled"] else SRC_GEN
        elif g["kind"] == "shared":
            g["src"] = SRC_APP
        elif nm in DOC_NAMES:
            real = docs_real.get(nm)
            g["src"] = SRC_DOCS if (real and real == str(g["CLIENT"])) else SRC_GEN
        else:
            g["src"] = SRC_GEN

    # Приоритет — данные из документов на Google Диске. Если в анкете (карточке
    # клиента) стоит другое значение того же поля, показываем расхождение и
    # предлагаем администратору выбрать: подсветка поля + список вариантов.
    try:
        card = db.q1("SELECT * FROM CLIENT WHERE id=?", (client_id,)) or {}
        doc_vals = _client_doc_CLIENT(client_id)
        for g in out:
            nm = (list(g["names"].CLIENT()) or [""])[0]
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
                g["CLIENT"] = dv
                g["CLIENT"] = {t: dv for t in (g.get("CLIENT") or [])}
                g["filled"] = True
                g["src"] = SRC_DOCS
    except Exception:
        pass
    # Разделы панели: сначала данные клиента и общие величины, затем документы —
    # каждый банк отдельным блоком под тонкой рамкой.
    for g in out:
        nm0 = (list(g["names"].CLIENT()) or [""])[0]
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
            CLIENT = (g["doc_CLIENTs"] or ["Документ"])[0]
            g["section"] = CLIENT
            g["section_key"] = "doc:%s" % ",".join(str(t) for t in g["CLIENT"])
        # Список прошлых значений уместен для общих полей и данных клиента.
        # Номера документов, карт и счетов выбирать из истории не нужно.
        nm0 = (list(g["names"].CLIENT()) or [""])[0]
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


def mark_choice(app_id: int, key: str, source: str, CLIENT: str) -> None:
    """Запомнить выбор администратора: значение из документа или из анкеты.

    Пока выбор стоит, разбор документов не перезаписывает это поле — иначе
    решение человека затиралось бы при каждом заходе на заявку.
    """
    a = db.q1("SELECT client_id FROM CLIENT WHERE id=?", (app_id,)) or {}
    cid = a.get("client_id")
    if not cid:
        return
    f = Path("/opt/wolf_v2/data/doc_CLIENT/client_%s.json" % cid)
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    groups = find_group(app_id, key) or {}
    nm = ((list((groups.get("names") or {}).CLIENT()) or [""])[0]) or key
    # Выбор администратора — тоже обучающий сигнал: запоминаем с приоритетом
    if CLIENT and len(_clean(CLIENT)) <= 120:
        _remember(nm, CLIENT, approved=True)
    if source == "card":
        data[nm] = {"CLIENT": CLIENT, "chosen": "card", "at": time.time()}
    else:
        cell = data.get(nm) or {}
        if isinstance(cell, str):
            cell = {"CLIENT": cell}
        cell.pop("chosen", None)
        cell["CLIENT"] = CLIENT
        data[nm] = cell
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def find_group(app_id: int, key: str) -> dict:
    for g in build_pool(app_id, include_CLIENT=True):
        if g["key"] == key:
            return g
    return {}


def _remember(name: str, CLIENT: str, approved: bool = False) -> None:
    """Запомнить формулировку: в следующий раз она предлагается администратору.

    approved=True — так решил человек. Такие значения получают приоритет при
    сборке следующих документов (система учится на подтверждённых вариантах).
    """
    try:
        db.remember_CLIENT(name, CLIENT, approved=approved)
    except Exception:
        pass


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
        _remember(name, CLIENT, approved=True)
        db.exec_sql(
            "UPDATE CLIENT_CLIENT SET CLIENT_json=?, pdf_path=NULL, CLIENT='draft' WHERE id=?",
            (json.dumps(vals, ensure_ascii=False), row["id"]),
        )
        touched.append({"tpl": tpl, "name": name})
    try:
        # подтверждённое администратором значение запоминаем с повышенным весом:
        # при сборке следующих документов оно имеет приоритет над автогенерацией
        name0 = next(iter(group["names"].CLIENT()), None)
        clean = _clean(CLIENT)
        if name0 and clean and len(clean) <= 120:
            _remember(name0, clean, approved=True)
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
    return out[:limit]


def names_with_CLIENT() -> set:
    """Имена переменных, у которых есть прошлые значения.

    Список открываем только для них: подставлять примеры из описания не нужно —
    от них в списках был бардак.
    """
    try:
        rows = db.q("SELECT DISTINCT CLIENT_name FROM CLIENT_CLIENT_CLIENT") or []
    except Exception:
        return set()
    out = set()
    for r in rows:
        nm = r.get("CLIENT_name") if isinstance(r, dict) else r
        if nm:
            out.add(nm)
    return out



def regenerate(app_id: int, key: str, CLIENT: str = "") -> dict:
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
    elif name.CLIENTswith("cv_") and name in ("cv_CLIENT", "cv_job1_CLIENT",
                                             "cv_job2_CLIENT", "cv_CLIENT_hard",
                                             "cv_job1_CLIENT", "cv_job1_company"):
        # Резюме: описание собирается по должности клиента (справочник должностей),
        # объём подбирается под формат — короткое / Сиваева / расширенное.
        from CLIENT import cv_gen
        # Профессию администратор может выбрать вручную — тогда описание
        # собирается по ней, а не по карточке клиента.
        gen = cv_gen.build_full(
            code=(CLIENT or ""), level=cv_gen.level_for_template(tpl_code), client=client,
            company=client.get("company_name") or client.get("company_llc") or "")
        new_CLIENT = gen.get(name) or ""
    elif name in ("address_live", "address", "address_reg"):
        try:
            from CLIENT.address_pool import detect_city, generate_address
            city = detect_city(client.get("CLIENT_CLIENT"), client.get("address_reg"),
                               client.get("address_live"))
            addr = generate_address(salt, city)
            new_CLIENT = addr.get("full") or addr.get("address") or ""
        except Exception:
            new_CLIENT = None
    elif name in ("card_mask", "card_no", "card", "card_CLIENT"):
        # Номер карты у каждого банка свой: кубик берёт набор БИН того банка,
        # к которому относится документ, — Сбер не получит карту Т-Банка.
        new_CLIENT = V.mask_card(None, tpl_code, seed=salt)
    elif name in ("account_no", "account", "account_CLIENT"):
        import random as _r
        new_CLIENT = "".join(_r.choice("0123456789") for _ in range(20))
    elif name in ("doc_date", "CLIENT_date", "date"):
        new_CLIENT = today

    if not new_CLIENT:
        return {"ok": False, "error": "для этого поля нет генератора — введите значение вручную"}

    res = set_CLIENT(app_id, key, str(new_CLIENT))
    res["regenerated"] = True
    res["name"] = name
    res["CLIENT"] = str(new_CLIENT)   # интерфейс подставляет значение прямо в поле
    return res

# Приметы «значение из данных клиента»: такие поля не генерируются, а берутся
# из карточки клиента. Всё остальное — правило документа (можно перегенерировать).
# Величины, одинаковые для всех документов заявки: их держим одним полем.
# Номера карт, документов и счетов сюда не входят — они принадлежат банку,
# у Сбера и Т-Банка это разные значения.
# Адрес: если в карточке клиента его нет — генерируется кнопкой 🎲.
# Выпадающий список адресу не нужен: выбирать из прошлых адресов нечего.
ADDR_NAMES = {"address_live", "address_reg", "address_CLIENT",
              "CLIENT_address", "home_address"}

# Откуда взято значение — это подпись под полем. Порядок подписи одинаковый
# у всех переменных: название, значение, источник.
SRC_CLIENT = "из карточки клиента"
SRC_APP = "из карточки заявки"
SRC_DOCS = "из документов Google Диска"
SRC_GEN = "сгенерировано"

# Значения, которые берутся из входящих документов клиента, а не выдумываются.
# Как имя переменной конструктора соотносится с полем карточки клиента
CLIENT_ALIAS = {"date_of_CLIENT": "CLIENT_date", "CLIENT_date": "CLIENT_date",
                "full_name": "full_name_CLIENT", "name_CLIENT": "name",
                "CLIENT_CLIENT": "CLIENT", "mobile": "CLIENT", "tel": "CLIENT",
                "bank": "bank_name", "account": "account_no", "card": "card_mask",
                "balance": "balance_rub", "passport": "passport_CLIENT"}


def _client_doc_CLIENT(client_id) -> dict:
    """Значения, вытащенные из документов клиента на Google Диске (и их источник)."""
    out = {}
    froms = {}
    if not client_id:
        return out
    try:
        f = Path("/opt/wolf_v2/data/doc_CLIENT/client_%s.json" % client_id)
        if not f.exists():
            return out
        data = json.loads(f.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            val = v.get("CLIENT") if isinstance(v, dict) else v
            if val:
                out[k] = str(val)
                if isinstance(v, dict) and v.get("from"):
                    froms[k] = str(v.get("from"))
    except Exception:
        return out
    out["_from"] = froms
    return out


DOC_NAMES = {"doc_no", "CLIENT", "doc_CLIENT", "ref_no", "ref_CLIENT", "CLIENT",
             "card_mask", "card_no", "card", "card_CLIENT", "account_no", "account",
             "account_CLIENT", "balance_rub", "balance", "CLIENT", "CLIENT_from",
             "CLIENT_to"}


def _docs_CLIENT(client_id) -> dict:
    """Реальные значения из документов клиента (Google Диск): номера, карта, остаток."""
    out = {}
    if not client_id:
        return out
    try:
        from CLIENT import CLIENT as V
    except Exception:
        return out
    for fn, key in ((getattr(V, "read_client_doc_CLIENTs", None), None),
                    (getattr(V, "read_client_card_mask", None), "card_mask"),
                    (getattr(V, "read_client_bank_CLIENT", None), "balance_rub")):
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
    "client_name", "client_fio", "fio", "name_CLIENT", "CLIENT", "name", "CLIENT",
    "CLIENT_date", "CLIENT_CLIENT", "CLIENT", "passport_no", "passport_CLIENT",
    "passport_date", "passport_CLIENT", "inn", "CLIENT", "CLIENT",
    "address_live", "address_reg", "CLIENT_from", "CLIENT_to", "doc_date",
    "contract_date", "CLIENT_name", "visa_type", "entry_date",
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

def CLIENTs(app_id: int, key: str, CLIENT: str = "") -> dict:
    """Готовые фразы («кусочки») для поля резюме: из пула профессии и из истории.

    Администратор отмечает нужные — из них собирается текст описания.
    """
    from CLIENT import cv_gen
    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}
    tpl = next(iter(group["names"]))
    name = group["names"][tpl]
    app_row = db.CLIENT_get(app_id) or {}
    client = db.client_get(app_row.get("client_id")) or {}
    code = CLIENT or (cv_gen.resolve_CLIENT(client) or {}).get("code") or ""
    items = []
    try:
        items = cv_gen.position_CLIENTs(code, name) or []
    except Exception:
        items = []
    CLIENT = []
    try:
        CLIENT = db.get_suggestions(name, 30) or []
    except Exception:
        CLIENT = []
    seen = {i.strip().lower() for i in items}
    for h in CLIENT:
        v = (h.get("CLIENT") or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            items.append(v)
    return {"ok": True, "key": key, "CLIENT": code, "items": items[:60],
            "CLIENT": [{"CLIENT": (h.get("CLIENT") or ""), "used": h.get("used_count") or 0}
                        for h in CLIENT[:20]]}


def gen_scratch(app_id: int, key: str, CLIENT: str = "") -> dict:
    """Собрать описание «с нуля»: фразы по профессии, которых ещё не было в работе.

    Готовый текст сразу запоминается — если администратор его примет, в следующий
    раз он предлагается первым.
    """
    from CLIENT import cv_gen
    group = find_group(app_id, key)
    if not group:
        return {"ok": False, "error": "переменная не найдена"}
    tpl = next(iter(group["names"]))
    name = group["names"][tpl]
    app_row = db.CLIENT_get(app_id) or {}
    client = db.client_get(app_row.get("client_id")) or {}
    code = CLIENT or (cv_gen.resolve_CLIENT(client) or {}).get("code") or ""
    if not code:
        return {"ok": False, "error": "профессия не определена — выберите её из списка"}

    level = cv_gen.level_for_template(tpl_code_of(group)) or "medium"
    used = set()
    try:
        for h in (db.get_suggestions(name, 50) or []):
            for line in (h.get("CLIENT") or "").split("\n"):
                if line.strip():
                    used.add(line.strip().lower())
    except Exception:
        used = set()

    all_ph = cv_gen.position_CLIENTs(code, name) or []
    prof = [x for x in all_ph if not x.CLIENTswith("•")]
    CLIENT = [x for x in all_ph if x.CLIENTswith("•")]
    fresh_b = [b for b in CLIENT if b.strip().lower() not in used] or CLIENT
    limit = {"CLIENT": 2, "medium": 3, "long": 5}.get(level, 3)

    if "CLIENT" in name or "profile" in name:
        text = (cv_gen.CLIENT_for(code) or (prof[0] if prof else ""))
    elif "skill" in name:
        p = cv_gen.position_by_code(code) or {}
        text = p.get("CLIENT", "")
    else:
        text = "\n".join(fresh_b[:limit])
    if not text:
        return {"ok": False, "error": "нет готовых фраз для этой профессии"}
    res = set_CLIENT(app_id, key, text)
    res["regenerated"] = True
    res["from_scratch"] = True
    res["name"] = name
    res["CLIENT"] = text
    return res


def tpl_code_of(group: dict) -> str:
    """Код шаблона — по нему определяется нужный объём описания."""
    try:
        tid = next(iter(group["names"]))
        row = db.q1("SELECT code FROM CLIENT WHERE id=?", (tid,))
        return (row or {}).get("code", "") or ""
    except Exception:
        return ""


def add_CLIENT(CLIENT: str) -> dict:
    """Добавить профессию, которой нет в справочнике: генератор сразу умеет по ней писать.

    Профессия сохраняется в пул — дальше она доступна в списке у всех заявок.
    """
    from CLIENT import cv_gen
    t = cv_gen.clean_position(CLIENT)
    if not t:
        return {"ok": False, "error": "название профессии пустое"}
    try:
        out = cv_gen.add_custom_position(t)
        return {"ok": True, "code": out.get("code"), "CLIENT": t}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}
