"""Значения из документов клиента — в приоритете над карточкой.

Правило заказчика (06.10.2026): часть данных берётся из документов клиента (паспорт,
KITAS/ИТК, банковская справка), часть — из карточки. Если значения расходятся, в документ
идёт значение из документа клиента.

Источник — последний успешный скан папки клиента на Google Диске (drive_scans.payload):
записи вида «значение | переменная | откуда взято». Перекрываем только клиентские
переменные: суммы, сроки, номера документов и тексты система считает сама.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

DB = Path('/opt/wolf_v2/data/wolf.db')

# что можно брать из документов клиента (остальное система считает сама)
ALLOW = re.compile(
    r'^(passport_(no|number|series|issued_by|issue_date|expiry)|intl_passport|passport_code|'
    r'full_name_latin|full_name_title|surname|client_name|date_of_birth|birth_date|'
    r'place_of_birth|birth_place|nationality|citizenship|client_nationality|client_gender|gender|'
    r'address_(live|reg|zip)|address_in_indonesia|city|country|email|phone|'
    r'itk_(no|expiry)|stay_permit_no|existing_stay_permit|visa_no|bridging_visa_no|'
    r'balance_(rub|date|words)|period_(from|to)|doc_no|ref_no|contract_no|contract_date|'
    r'card_mask|account_no|bank_name|cv_[a-z0-9_]+)$')

_cache: dict[int, dict] = {}

# Явный мусор: распознавание иногда вытаскивает не значение, а кусок текста договора
# или бланка («682220, ИНН 774314450192, именуемый в дальнейшем «Заказчик»»). Такие
# значения в документы не пускаем — иначе правило «документ клиента сильнее карточки»
# портит готовый документ.
_JUNK = re.compile(r'именуем|далее\s+«?заказчик|заказчик|исполнитель|настоящ(ий|его)\s+договор|'
                   r'\bинн\b|\bогрн\b|\bкпп\b|подпис|доверенност|…{2,}|_{3,}|\.{4,}', re.I)
# адрес должен быть похож на адрес: цифры + адресный признак
_ADDR_HINT = re.compile(r'\d', re.U)
_ADDR_WORD = re.compile(r'\b(st|street|ave|avenue|ul|ulitsa|d\.|dom|kv|apt|korp|korpus|blvd|road|rd|'
                        r'jl|jln|jalan|kec|kabupaten|kota|desa|kel|rt|rw|no|zip|мкр|ул|д\.|кв|корп|обл|г\.)\b',
                        re.I)


def _sane(var: str, val: str) -> str:
    """Отбросить мусорные значения: они не должны попадать в документы."""
    v = ' '.join(str(val or '').split())
    if not v or len(v) < 3:
        return ''
    if _JUNK.search(v):
        return ''
    if var.startswith(('address_', 'city', 'country')) or var == 'address_in_indonesia':
        # адрес: обязателен номер дома/индекс и хотя бы одно адресное слово
        if not (_ADDR_HINT.search(v) and _ADDR_WORD.search(v)):
            return ''
    if var.startswith('passport') and re.search(r'[«»]', v):
        return ''
    if len(v) > 120:
        return ''
    return v


def parse_payload(payload) -> dict:
    """«значение | переменная | источник» из payload скана → {переменная: значение}."""
    out: dict[str, str] = {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload or '[]')
        except Exception:  # noqa: BLE001
            return out
    if not isinstance(payload, list):
        return out
    for item in payload:
        if not isinstance(item, dict):
            continue
        for line in str(item.get('found') or '').splitlines():
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 2:
                continue
            val, var = parts[0], parts[1]
            if not val or val in ('—', '-'):
                continue
            if not ALLOW.match(var or ''):
                continue
            val = _sane(var, val)
            if not val:
                continue
            src = parts[2].lower() if len(parts) > 2 else ''
            # значение из документа клиента приоритетнее карточки
            if var not in out or 'документ' in src:
                out[var] = val
    return out


def for_application(app_id: int, use_cache: bool = True) -> dict:
    """Значения из документов клиента для заявки (последний удачный скан)."""
    if use_cache and app_id in _cache:
        return _cache[app_id]
    vals: dict[str, str] = {}
    try:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT payload FROM drive_scans WHERE application_id=? AND payload IS NOT NULL "
                           "AND payload<>'' ORDER BY id DESC LIMIT 3", (app_id,)).fetchall()
        con.close()
        for r in rows:
            got = parse_payload(r['payload'])
            for k, v in got.items():
                vals.setdefault(k, v)
            if vals:
                break
    except Exception:  # noqa: BLE001
        return {}
    if use_cache:
        _cache[app_id] = vals
    return vals


def apply(vals: dict, app_id: int, only_missing: bool = False) -> tuple[dict, list]:
    """Наложить значения из документов клиента поверх собранных значений.

    only_missing=False — документ клиента сильнее карточки (правило заказчика).
    Возвращает (значения, список перекрытых переменных).
    """
    doc = for_application(app_id)
    if not doc:
        return vals, []
    changed = []
    for k, v in doc.items():
        if v in (None, ''):
            continue
        if only_missing and vals.get(k) not in (None, ''):
            continue
        if str(vals.get(k) or '') != str(v):
            changed.append(k)
        vals[k] = v
    return vals, changed
