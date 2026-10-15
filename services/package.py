"""Итоговый пакет документов: что реально подаём в иммиграцию.

Принцип заказчика: пакет — это НЕ всё, что система умеет собрать, и НЕ всё, что
клиент принёс. В пакет входит только то, что:

  1. требует регламент этого продукта (services.requirements), и
  2. относится к этому клиенту.

Практический случай, из-за которого модуль появился: в продукте C1-EXT в наборе
лежали ОБЕ банковские справки — Т-Банка и Сбербанка, обе как обязательные. Система
собирала две справки и обе отправляла, хотя справка об остатке нужна одна, а банк
у клиента один. Лишняя справка в пакете — замечание иммиграции, поэтому
«выключение» обязательно, а не косметика.

Модуль отвечает на два вопроса:
  - selected(product, client) -> какие документы идут в подачу;
  - excluded(product, client) -> что выключили и почему (для легенды и лога).
"""
from __future__ import annotations

import sqlite3

DB = "/opt/wolf_v2/data/wolf.db"

# Слоты, внутри которых допустим ТОЛЬКО ОДИН документ.
# Значение — как выбрать нужный вариант по данным клиента.
SINGLE_SLOTS = {
    "bank_statement": "bank",      # справка об остатке — по банку клиента
    "letter": "office",            # письмо в иммиграцию — по офису подачи
    "contract": "contract",        # договор — один на клиента, по продукту
    "cv": "single",
    "photo": "single",
}

# Договор: в пакете он ОДИН, но это два РАЗНЫХ документа, а не замена одного
# другим. Remote Work Agreement — удалённая работа на компанию вне Индонезии,
# печатает годовой доход (закрывает требование E33G: доход 60 000 USD и договор
# с зарубежной компанией). Employment Contract — трудовой договор: должность,
# оклад. Для E33G и D12 выбор однозначен (по архиву — 13 из 13 Remote Work).
CONTRACT_BY_PRODUCT = {
    "E33G-NEW": "remote_work_agreement__default",
    "E33G-EXT": "remote_work_agreement__default",
    "D12": "remote_work_agreement__default",
}
# Для визитных продуктов (C1, C1-EXT, BRIDGING, CONV) в архиве встречаются оба:
# 4 клиента получили Remote Work, 4 — трудовой договор. Выбор идёт по тому, как
# человек работает, то есть по его документам.


def _contract_by_client(client_id):
    """Какой договор уместен этому клиенту — по его документам."""
    try:
        folder = _find_client_folder(client_id)
        if not folder:
            return ""
        names = [f.name.lower() for f in folder.iterdir() if f.is_file()]
        if any(("remote" in n) for n in names):
            return "remote_work_agreement__default"
        if any(("трудовой" in n or "employment" in n or "contract" in n) for n in names):
            return "employment_contract__default"
    except Exception:                                          # noqa: BLE001
        pass
    return ""


def _find_client_folder(client_id):
    try:
        from services import values as _v
        return _v._find_client_folder_by_id(client_id)
    except Exception:                                          # noqa: BLE001
        return None

# Банк клиента (clients.bank_name) -> код шаблона
BANK_TEMPLATES = {
    "TBANK": "bank_statement_3m__tbank",
    "T-BANK": "bank_statement_3m__tbank",
    "TINKOFF": "bank_statement_3m__tbank",
    "SBER": "bank_statement_3m__sber",
    "SBERBANK": "bank_statement_3m__sber",
    "СБЕРБАНК": "bank_statement_3m__sber",
    "ТБАНК": "bank_statement_3m__tbank",
}


def _requirements(product_code) -> dict:
    """Требования продукта (services.requirements) — источник истины по составу."""
    try:
        from services import requirements as _req
        return _req.for_product(product_code) or {}
    except Exception:                                          # noqa: BLE001
        return {}


# Слот набора -> флаг требований, который его включает.
# Визитные продукты (C1, C1-EXT, BRIDGING, CONV) договор, резюме и форму клиента
# НЕ подают: работа по визитной визе запрещена. Если флаг выключен, документ в
# пакет не попадает — иначе система печатает договор с пустыми полями, проверка
# оформления бракует его навсегда и заявка намертво встаёт в «сборке».
NEEDS_BY_SLOT = {
    "contract": "needs_contract",
    "work_agreement": "needs_contract",
    "cv": "needs_cv",
    "e02": "needs_e02",
}


def _slot_off_by_product(product_code, slot: str) -> bool:
    """Слот выключен требованиями продукта?"""
    flag = NEEDS_BY_SLOT.get(slot or "")
    if not flag:
        return False
    rq = _requirements(product_code)
    if flag not in rq:
        return False
    return not bool(rq.get(flag))


def _conn():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    return c


def _rows(product_code: str) -> list:
    """Документы набора продукта: слот, код шаблона, обязательность, порядок."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT pd.slot_code, pd.required, pd.is_default, pd.sort_order, "
            "       t.code AS tcode, t.title, t.status "
            "FROM product_documents pd "
            "JOIN products p ON p.id = pd.product_id "
            "JOIN templates t ON t.id = pd.template_id "
            "WHERE p.code = ? AND IFNULL(t.status,'') <> 'hidden' "
            "ORDER BY pd.sort_order, t.code", (product_code,)).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _client_bank(client_id) -> str:
    """Банк клиента — из его карточки (clients.bank_name).

    Именно он решает, какую из готовых справок подаём: Т-Банка или Сбербанка.
    """
    if not client_id:
        return ""
    try:
        c = _conn()
        r = c.execute("SELECT bank_name FROM clients WHERE id=?", (client_id,)).fetchone()
        c.close()
        if r and r["bank_name"]:
            return str(r["bank_name"]).upper()
    except Exception:
        pass
    return ""


def _slot_key(row: dict) -> str:
    """Ключ слота: явный slot_code, иначе — по коду шаблона.

    В БД слоты названы по-разному (`bank_stmt_3m`, `bank_statement_3m__tbank`),
    поэтому имя слота приводим к одному виду: иначе выбор одного варианта из
    слота не срабатывает и в пакет попадают обе справки — и Т-Банка, и Сбера.
    """
    slot = (row.get("slot_code") or "").strip().lower()
    code = (row.get("tcode") or "").lower()
    for src in (slot, code):
        if not src:
            continue
        if "bank" in src:
            return "bank_statement"
        if "e02" in src or "statement_letter" in src:
            return "e02"             # форма клиента — свой слот, не альтернатива письму
        if "letter" in src:
            return "letter"
        if "cv" in src:
            return "cv"
        # Для E33G нужны ОБА документа: контракт (Employment Contract) и договор
        # с организацией (Remote Work Agreement). Раньше они сваливались в один слот
        # «contract», и система считала их альтернативами — один всегда исключался.
        if "remote_work" in src or "work_agreement" in src:
            return "work_agreement"
        if "contract" in src or "agreement" in src:
            return "contract"
        if "photo" in src:
            return "photo"
    return slot or code


def selected(product_code: str, client_id=None) -> list:
    """Документы, которые идут в подачу (по одному на слот)."""
    rows = _rows(product_code)
    if not rows:
        return []
    bank = _client_bank(client_id) if client_id else ""

    by_slot: dict = {}
    order: list = []
    for r in rows:
        slot = _slot_key(r)
        if slot not in by_slot:
            by_slot[slot] = []
            order.append(slot)
        by_slot[slot].append(r)

    out = []
    for slot in order:
        group = by_slot[slot]
        # Документ слота не требуется регламентом продукта (например договор для
        # визитной визы) — в подачу он не идёт.
        if _slot_off_by_product(product_code, slot):
            continue
        pick = None
        if len(group) == 1:
            pick = group[0]
        elif slot == "bank_statement" and bank:
            want = BANK_TEMPLATES.get(bank, "")
            if want:
                pick = next((g for g in group if g["tcode"] == want), None)
            if pick is None:
                # банк клиента не совпал ни с одним шаблоном: берём по умолчанию,
                # чтобы справка вообще была (лучше один документ, чем ни одного)
                pick = next((g for g in group if g.get("is_default")), None)
        elif slot == "bank_statement" and not bank:
            pick = next((g for g in group if g.get("is_default")), None)
        elif slot == "contract":
            want = (CONTRACT_BY_PRODUCT.get((product_code or "").upper(), "")
                    or _contract_by_client(client_id)
                    or "employment_contract__default")
            if want:
                pick = next((g for g in group if g["tcode"] == want), None)
            if pick is None:
                pick = next((g for g in group if g.get("is_default")), None)
        if pick is None:
            pick = group[0]
        out.append({"code": pick["tcode"], "title": pick["title"] or pick["tcode"],
                    "slot": slot, "required": bool(pick.get("required"))})
    return out


def excluded(product_code: str, client_id=None) -> list:
    """Что выключили из пакета и почему — для легенды и журнала.

    Клиентские документы, не проходящие по регламенту, в пакет не попадают: их
    место занимает документ, собранный системой под проходные значения.
    """
    rows = _rows(product_code)
    keep = {d["code"] for d in selected(product_code, client_id)}
    bank = _client_bank(client_id) if client_id else ""
    out = []
    for r in rows:
        if r["tcode"] in keep:
            continue
        slot = _slot_key(r)
        if slot == "bank_statement" and bank:
            reason = ("у клиента банк %s — справка другого банка в пакет не входит "
                      "(справка об остатке нужна одна)" % bank)
        elif slot == "contract":
            reason = ("в пакете нужен один договор — для продукта %s выбран другой "
                      "договор" % product_code)
        else:
            reason = "в слоте «%s» выбран другой документ" % slot
        out.append({"code": r["tcode"], "title": r["title"] or r["tcode"], "reason": reason})
    return out


def statement_template(client_id=None) -> str:
    """Какой шаблон банковской справки подаём этому клиенту (или '')."""
    for code in ("C1-EXT", "C1", "E33G-NEW", "E33G-EXT", "BRIDGING", "CONV", "D12"):
        for d in selected(code, client_id):
            if d["slot"] == "bank_statement" and d["code"]:
                return d["code"]
    return ""
