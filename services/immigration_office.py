"""Какой иммиграционный офис обслуживает адрес клиента.

Письма в иммиграцию существуют в двух вариантах: Ngurah Rai и Denpasar
(плюс третий — Singaraja, вне нашего комплекта). В заявке должен остаться
ровно ОДИН вариант: тот, в чьей зоне обслуживания находится адрес проживания
клиента. Адрес берём из карточки (адрес проживания, затем адрес регистрации,
затем индекс), сверяем с базой `data/immigration_offices.json`.

Правило разбора адреса, от сильного признака к слабому:
  1) индекс (kode pos): 803xx → Ngurah Rai; 801/802/805/806/807/821xx → Denpasar;
  2) кабупатен (kabupaten/kota): Badung → Ngurah Rai, остальные наши → Denpasar;
  3) kecamatan и известные районы (Canggu, Ubud, Sanur, ...).

Адрес в зоне Singaraja (Buleleng, Karangasem, Jembrana) в наш комплект не входит —
такая заявка помечается как «требуется ручное решение».
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

BASE = Path("/opt/wolf_v2")
DATA_FILE = BASE / "data" / "immigration_offices.json"
DB_FILE = BASE / "data" / "wolf.db"

OFFICE_SUFFIXES = ("ngurahrai", "denpasar", "tabanan")
# Письмо теперь одно на тип: офис подставляется переменными addressee_office /
# addressee_line1..3 по адресу клиента (было по копии шаблона на каждый офис —
# копии расходились и требовали правок в трёх местах).
PAIRS = {
    "bridging": {"ngurahrai": "bridging_request_letter__default",
                 "denpasar": "bridging_request_letter__default",
                 "tabanan": "bridging_request_letter__default"},
    "conversion": {"ngurahrai": "conversion_request_letter__default",
                   "denpasar": "conversion_request_letter__default"},
}

_data_cache: dict | None = None


def data() -> dict:
    global _data_cache
    if _data_cache is None:
        try:
            _data_cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            _data_cache = {"postal_office": {}, "kabupaten": {}, "kecamatan": {},
                           "areas": {}, "offices": {}}
    return _data_cache


def addressee_for(code: str | None) -> dict:
    """Три строки адресата и название офиса для писем (по офису, определённому адресом)."""
    if not code:
        return {}
    o = (data().get("offices", {}).get(code, {}) or {})
    lines = o.get("addressee") or []
    if len(lines) < 3:
        return {}
    return {"line1": lines[0], "line2": lines[1], "line3": lines[2],
            "office": o.get("name") or o.get("short") or ""}


def office_name(code: str | None) -> str:
    if not code:
        return ""
    return (data().get("offices", {}).get(code, {}) or {}).get("short", code)


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("\u00a0", " ")
    t = re.sub(r"[.,;]", " ", t)
    return re.sub(r"\s+", " ", t)


def _by_postal(text: str) -> tuple[str | None, str]:
    """Индекс Бали — 5 цифр, начинается на 8 (801xx…822xx)."""
    for m in re.finditer(r"\b(8\d{4})\b", text):
        code = m.group(1)
        table = data().get("postal_office", {})
        office = table.get(code[:3])
        if office:
            return office, "индекс %s" % code
    return None, ""


def _by_kabupaten(text: str) -> tuple[str | None, str]:
    table = data().get("kabupaten", {})
    for m in re.finditer(r"(?:kabupaten|kab|kota)\s+([a-z ]{3,24}?)(?=\s*(?:,|$|\d|\bbali\b|kec|kel))", text):
        name = m.group(1).strip()
        for key, office in table.items():
            if name.startswith(key) or key.startswith(name):
                return office, "кабупатен %s" % name.title()
    for key, office in table.items():
        if re.search(r"\b%s\b" % re.escape(key), text):
            return office, "кабупатен %s" % key.title()
    return None, ""


def _by_kecamatan(text: str) -> tuple[str | None, str]:
    table = data().get("kecamatan", {})
    for m in re.finditer(r"(?:kecamatan|kec)\s+([a-z ]{3,24}?)(?=\s*(?:,|$|\d|\bkab\b|\bbali\b))", text):
        name = m.group(1).strip()
        if name in table:
            return table[name], "kecamatan %s" % name.title()
    return None, ""


def _by_area(text: str) -> tuple[str | None, str]:
    for key, office in sorted(data().get("areas", {}).items(),
                              key=lambda kv: -len(kv[0])):
        if re.search(r"\b%s\b" % re.escape(key), text):
            return office, "район %s" % key.title()
    return None, ""


def resolve_text(*texts: str) -> dict:
    """Определить офис по произвольным строкам адреса.

    Приоритет — от явного текста к цифре: кабупатен/kota, затем kecamatan,
    затем известный район, и только потом индекс. Индекс в заявках бывает
    указан неверно (напр. адрес в Tabanan с индексом 80351 Mengwi), поэтому
    текстовое название административной единицы сильнее кода.
    """
    joined = _norm(" ".join(t for t in texts if t))
    if not joined:
        return {"office": None, "why": "адрес не заполнен"}
    found: dict[str, tuple[str, str]] = {}
    for key, finder in (("kabupaten", _by_kabupaten), ("kecamatan", _by_kecamatan),
                        ("area", _by_area), ("postal", _by_postal)):
        office, why = finder(joined)
        if office:
            found[key] = (office, why)
    for key in ("kabupaten", "kecamatan", "area", "postal"):
        if key in found:
            office, why = found[key]
            conflict = ""
            if key != "postal" and "postal" in found and found["postal"][0] != office:
                conflict = ", индекс %s противоречит (не учитываем)" % found["postal"][1]
            return {"office": office, "why": why + conflict, "address": joined[:200]}
    return {"office": None, "why": "адрес вне зон Бали (не распознан)", "address": joined[:200]}


def resolve_for_app(app_id: int) -> dict:
    """Офис по адресу проживания клиента заявки."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT c.address_live, c.address_reg, c.address_zip, c.city, c.country
                 FROM applications a JOIN clients c ON c.id = a.client_id
                WHERE a.id = ?""", (app_id,)).fetchone()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return {"office": None, "why": "адрес недоступен: %s" % str(exc)[:80]}
    if not row:
        return {"office": None, "why": "заявка не найдена"}
    return resolve_text(row["address_live"], row["address_zip"], row["city"])


def resolve_for_client(conn, client_id: int) -> dict:
    """Офис по адресу клиента (когда соединение уже открыто)."""
    try:
        row = conn.execute(
            "SELECT address_live, address_reg, address_zip, city FROM clients WHERE id=?",
            (client_id,)).fetchone()
    except Exception as exc:  # noqa: BLE001
        return {"office": None, "why": "адрес недоступен: %s" % str(exc)[:80]}
    if not row:
        return {"office": None, "why": "клиент не найден"}
    return resolve_text(row["address_live"], row["address_zip"], row["city"])


def office_allows(template_code: str, office: str | None) -> bool:
    """Оставлять ли шаблон для заявки с известным офисом.

    Варианты писем (Ngurah Rai / Denpasar) — взаимоисключающие: нужен ровно
    один. Если офис не определён — оставляем оба, решит администратор.
    """
    code = (template_code or "").lower()
    tail = code.rsplit("__", 1)[-1] if "__" in code else ""
    if tail in OFFICE_SUFFIXES:
        if not office:
            return True
        return office == tail
    return True


def apply_pair_rule(app_id: int, office: str | None = None) -> dict:
    """Отметить в заявке лишний вариант пары (bridging / conversion) крестиком.

    Документ НЕ удаляем: он остаётся в списке миниатюр с красным крестиком и
    пометкой, почему исключён, — так администратор видит решение системы и
    может его перепроверить. В работу (сборка, отправка) он не идёт: статус
    `rejected`.
    """
    info = resolve_for_app(app_id)
    office = office or info.get("office")
    result = {"app_id": app_id, "office": office,
              "office_name": office_name(office), "why": info.get("why"),
              "kept": [], "marked": [], "removed": []}
    if not office:
        return result
    keep_codes: set[str] = set()
    drop_codes: set[str] = set()
    for variants in PAIRS.values():
        codes = set(variants.values())
        if office in variants:
            keep_codes.add(variants[office])
            drop_codes |= codes - {variants[office]}
        else:
            # для этого офиса варианта письма нет (например, conversion для Tabanan)
            # — вся группа в работу не идёт
            drop_codes |= codes
    _why = info.get("why") or ""
    reason = "исключено автоматически: адрес клиента — зона %s%s" % (
        office_name(office), (", " + _why) if _why else "")
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT ad.id, ad.status, t.code FROM application_documents ad
                 JOIN templates t ON t.id = ad.template_id
                WHERE ad.application_id = ?""", (app_id,)).fetchall()
        for r in rows:
            code = (r["code"] or "").lower()
            if code in keep_codes:
                result["kept"].append(code)
            elif code in drop_codes:
                if (r["status"] or "") != "rejected":
                    conn.execute(
                        "UPDATE application_documents SET status='rejected', error=? WHERE id=?",
                        (reason, r["id"]))
                    result["marked"].append(code)
                else:
                    result["removed"].append(code)   # уже был помечен
            elif code.rsplit("__", 1)[-1] in OFFICE_SUFFIXES:
                result["kept"].append(code)
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:120]
    return result


def prune_pair_documents(app_id: int, office: str | None = None) -> dict:
    """Совместимость: то же, что apply_pair_rule (документы помечаются, не удаляются)."""
    return apply_pair_rule(app_id, office)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(resolve_for_app(int(sys.argv[1])), ensure_ascii=False, indent=2))
    else:
        for sample in ("Kapu Kapu Ubud, Kecamatan Ubud, Kabupaten Gianyar, Bali 80552",
                       "Jl. Raya Munggu No.10, Kec. Mengwi, Kabupaten Badung, Bali 80351",
                       "Jl. Pantai Batu Bolong, Canggu, Badung 80363",
                       "Jalan Danau Tamblingan, Sanur, Denpasar Selatan",
                       "г. Москва, ул. Тверская, д. 1"):
            print(sample[:60], "→", json.dumps(resolve_text(sample), ensure_ascii=False))
