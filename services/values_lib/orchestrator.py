# services/values/orchestrator.py
"""
Оркестратор значений: главная точка входа build_template_values().

Здесь собираются значения из всех источников:
- services/values/personal.py    — ФИО, паспорт, даты
- services/values/finance.py     — суммы, остатки
- services/values/registry.py    — паспорта переменных
- services/templates/            — правила по конкретным бланкам

Эта функция перенесена из старого services/values.py с минимальными правками:
- personal.py и finance.py импортируются как подмодули
- старая цепочка импортов заменена на новую

Если правило для переменной есть в паспорте (data/variables/<name>.yaml),
применяется template_overrides (формат по шаблону).
"""

from __future__ import annotations
from typing import Dict, Any


def build_template_values(client: dict, tpl_code: str, doc_values: dict = None) -> Dict[str, Any]:
    """Главная точка входа: собрать значения для конкретного шаблона.

    Args:
        client: данные клиента (из core/db.client_get)
        tpl_code: код шаблона (например, 'bank_statement_3m__tbank')
        doc_values: ранее сохранённые значения документа (values_json) или None

    Returns:
        Словарь значений для подстановки в шаблон документа.
    """
    client = client or {}
    doc_values = doc_values or {}
    vals: Dict[str, Any] = {}

    # === Персональные данные ===
    from .personal import _fio_full_latin, _smart_title
    vals["client_name"] = _fio_full_latin(client, tpl_code)
    vals["full_name"] = vals["client_name"]
    vals["full_name_latin"] = vals["client_name"]
    vals["surname"] = _smart_title(client.get("surname") or "")
    vals["name"] = _smart_title(client.get("name") or "")
    vals["patronymic"] = _smart_title(client.get("patronymic") or "")
    vals["for_name"] = vals["client_name"]
    vals["cv_name"] = vals["client_name"]
    vals["employee_name"] = vals["client_name"]
    vals["employee_full_name"] = vals["client_name"]
    vals["employee_full_name_latin"] = vals["client_name"]
    vals["birth_date"] = client.get("birth_date")
    vals["date_of_birth"] = client.get("birth_date")
    vals["place_of_birth"] = client.get("birth_place")
    vals["birth_place"] = client.get("birth_place")
    vals["gender"] = client.get("gender")
    vals["citizenship"] = client.get("citizenship")
    vals["nationality"] = client.get("nationality") or client.get("citizenship")
    vals["passport_series"] = client.get("passport_series")
    vals["passport_number"] = client.get("passport_number")
    vals["passport_no"] = client.get("passport_number")
    vals["passport_issued_by"] = client.get("passport_issued_by")
    vals["passport_issue_date"] = client.get("passport_issue_date")
    vals["passport_expiry"] = client.get("passport_expiry")
    vals["inn"] = client.get("inn")
    vals["snils"] = client.get("snils")
    vals["intl_passport"] = client.get("intl_passport")
    vals["phone"] = "00"
    vals["email"] = client.get("email") or ""

    # === Финансы (для банковских справок) ===
    if (tpl_code or "").startswith("bank_statement"):
        from .finance import bank_amount_for, _fmt_money, _balance_words_from, gen_doc_no, gen_ref_no, mask_card, number_pattern, num_ok, _no_busy
        client_id = client.get("id")
        amt = bank_amount_for(client_id, tpl_code)
        if amt:
            try:
                f = float(str(amt).replace(" ", "").replace(",", "."))
                intpart = int(f)
                cents = int(round((f - intpart) * 100))
                vals["balance_rub"] = _fmt_money(amt, tpl_code)
                vals["balance_words"] = _balance_words_from(intpart, cents)
                vals["balance_cents"] = f"{cents:02d}"
            except Exception:
                vals["balance_rub"] = str(amt)
        # Doc No / Ref No
        d = vals.get("doc_date") or "17.10.2026"
        dn_pat = number_pattern(tpl_code, "doc_no")
        rn_pat = number_pattern(tpl_code, "ref_no")
        vals["doc_no"] = gen_doc_no(vals["client_name"], d, tpl_code, dn_pat)
        vals["ref_no"] = gen_ref_no(vals["client_name"], d, tpl_code, rn_pat)

    # === Наложение сохранённых значений (values_json) ===
    _DERIVED8 = {
        "services_list", "company_block", "contractor_block", "employee_block",
        "position_title", "engagement_phrase", "governing_law", "company_tail",
        "base_salary", "annual_amount_numeric", "annual_amount_words",
        "monthly_amount_numeric", "monthly_amount_words",
    }
    if doc_values:
        for k, v in doc_values.items():
            if not v or k in _DERIVED8:
                continue
            vals[k] = v

    # === Применяем паспорта переменных (правила по шаблону) ===
    from .registry import apply_passport_rules, list_known
    for var_name in list_known():
        if var_name in vals:
            vals[var_name] = apply_passport_rules(var_name, vals[var_name], tpl_code)

    return vals