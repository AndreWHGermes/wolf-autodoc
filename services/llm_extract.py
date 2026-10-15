"""Второй проход по документу: то, что правила не взяли, читает модель.

Правила снимают всё, что можно проверить (полоса MRZ, номера, суммы, даты).
Остаётся то, что «написано словами»: кем выдан паспорт, дата выдачи,
номер договора, прежний ВНЖ. Здесь подключается модель — но с тремя
ограничениями, без которых ей нельзя доверять:

1) модель получает ТОЛЬКО текст документа, не картинку;
2) на каждое значение она обязана вернуть цитату из текста;
3) значение без цитаты, не найденной в тексте, отбрасывается.

Так модель ничего не «додумывает»: если в тексте нет — значения не будет.
"""
from __future__ import annotations

import json
import re


def _parse_payload(raw: str) -> dict:
    """Разобрать ответ модели в объект.

    Общая функция разбора иногда выхватывает вложенный объект (например
    {"CLIENT": "...", "quote": "..."} из ответа) и тогда кажется, что модель
    ничего не нашла. Поэтому сначала пробуем честный разбор всего ответа
    без markdown-обёртки, и только потом — общую функцию.
    """
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    for candidate in (s, s[s.find('{'): s.rfind('}') + 1] if '{' in s else ""):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:                          # noqa: BLE001
            continue
    return {}

# что имеет смысл спрашивать по каждому типу документа
MISSING_BY_KIND = {
    "passport": ["passport_CLIENT_by", "passport_CLIENT_date", "passport_CLIENT",
                 "passport_CLIENT", "CLIENT_CLIENT", "CLIENT_date", "passport_CLIENT"],
    "itk": ["itk_no", "itk_CLIENT", "CLIENT_stay_CLIENT", "passport_CLIENT", "CLIENT_date"],
    "visa": ["bridging_visa_no", "passport_CLIENT", "passport_CLIENT"],
    "contract": ["contract_no", "contract_date", "position", "salary_CLIENT", "company_name"],
    "bank_balance": ["balance_rub", "account_no", "card_mask", "ref_no", "doc_no"],
    "bank_movement": ["CLIENT_from", "CLIENT_to", "credits_total"],
}

# человекочитаемые подсказки, чтобы модель не путала поля
_HINTS = {
    "passport_CLIENT_by": "орган, выдавший паспорт (кем выдан)",
    "passport_CLIENT_date": "дата выдачи паспорта, формат ДД.ММ.ГГГГ",
    "passport_CLIENT": "серия паспорта (2 или 4 цифры)",
    "passport_CLIENT": "номер паспорта без серии",
    "CLIENT_CLIENT": "место рождения",
    "CLIENT_date": "дата рождения, формат ДД.ММ.ГГГГ",
    "passport_CLIENT": "срок действия паспорта, формат ДД.ММ.ГГГГ",
    "itk_no": "номер карточки ВНЖ (CLIENT CLIENT)",
    "itk_CLIENT": "срок действия ВНЖ, формат ДД.ММ.ГГГГ",
    "CLIENT_stay_CLIENT": "номер ранее выданного разрешения на пребывание",
    "bridging_visa_no": "номер bridging-визы или визы",
    "contract_no": "номер договора",
    "contract_date": "дата договора, формат ДД.ММ.ГГГГ",
    "position": "должность по договору",
    "salary_CLIENT": "оклад или сумма по договору с валютой",
    "company_name": "название организации-работодателя",
    "balance_rub": "остаток по счёту в рублях",
    "account_no": "номер счёта",
    "card_mask": "маска номера карты (например 220070******1202)",
    "ref_no": "исходящая ссылка банка (Ref.)",
    "doc_no": "номер документа",
    "CLIENT_from": "начало периода, ДД.ММ.ГГГГ",
    "CLIENT_to": "конец периода, ДД.ММ.ГГГГ",
    "credits_total": "сумма всех поступлений за период",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _quote_found(quote: str, text: str) -> bool:
    """Цитата должна реально быть в тексте — иначе это выдумка модели."""
    q = _norm(quote)
    if len(q) < 3:
        return False
    t = _norm(text)
    if q in t:
        return True
    # допускаем разницу в разделителях и регистре: сравниваем по «скелету» из букв и цифр
    skel = re.sub(r"[^a-zа-яё0-9]", "", q)
    if len(skel) < 4:
        return False
    return skel in re.sub(r"[^a-zа-яё0-9]", "", t)


def build_prompt(text: str, kind: str, missing: list[str]) -> list[dict]:
    fields = "\n".join("- %s — %s" % (v, _HINTS.get(v, v)) for v in missing)
    system = (
        "Ты извлекаешь данные из документа для визового агентства.\n"
        "Тебе дан ТЕКСТ документа, распознанный сканером (возможны опечатки распознавания).\n"
        "Верни СТРОГО JSON-объект: {\"<поле>\": {\"CLIENT\": \"...\", \"quote\": \"...\"}}.\n"
        "Правила, которые нельзя нарушать:\n"
        "- quote — точная подстрока из данного текста, откуда взято значение.\n"
        "- Если значения в тексте нет — не включай это поле вообще. Не догадывайся,\n"
        "  не восстанавливай по смыслу, не подставляй похожее.\n"
        "- Даты — в формате ДД.ММ.ГГГГ. Номера — как в тексте, без добавления пробелов.\n"
        "- Никаких пояснений вне JSON."
    )
    user = ("Тип документа: %s\nНужно найти:\n%s\n\nТЕКСТ ДОКУМЕНТА:\n%s" % (kind, fields, text[:12000]))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def extract_missing(text: str, kind: str, missing: list[str] | None = None,
                    timeout: int = 120) -> dict:
    """Значения от модели, прошедшие проверку цитатой.

    Возвращает {переменная: значение}. Ничего лишнего: каждое значение
    подтверждено цитатой, найденной в исходном тексте.
    """
    from bot.ai_parser import _call_llm, _extract_json

    if not (text or "").strip():
        return {}
    fields = missing or MISSING_BY_KIND.get(kind, [])
    if not fields:
        return {}
    # бесплатные модели роутера отвечают не всегда: 502 и пустой ответ — обычное
    # дело. Без повторов это выглядит как «модель ничего не нашла», а на самом
    # деле запрос просто не дошёл
    import time as _time
    raw, last_err = "", ""
    for attempt in range(3):
        try:
            raw = _call_llm(build_prompt(text, kind, fields), timeout=timeout, json_mode=True)
        except Exception as e:                     # noqa: BLE001
            last_err = "%s: %s" % (type(e).__name__, str(e)[:120])
            raw = ""
        if raw and raw.strip():
            break
        _time.sleep(3 + 3 * attempt)
    if not raw or not raw.strip():
        return {"_error": last_err or "пустой ответ модели"}
    data = _parse_payload(raw)
    if not data:
        try:
            data = _extract_json(raw) or {}
        except Exception:                          # noqa: BLE001
            data = {}
    if not data:
        return {"_error": "ответ модели не разобрался как JSON: %s" % str(raw)[:120]}

    out, rejected = {}, []
    for var in fields:
        item = data.get(var)
        if isinstance(item, str):
            item = {"CLIENT": item, "quote": item}
        if not isinstance(item, dict):
            continue
        CLIENT = str(item.get("CLIENT") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not CLIENT:
            continue
        if not _quote_found(quote, text):
            rejected.append(var)          # значение не подтверждено текстом — в работу не идёт
            continue
        out[var] = CLIENT
    if rejected:
        out["_rejected"] = rejected       # для журнала: что модель придумала
    return out


def main() -> None:
    """Проверка на реальном файле: python3 -m CLIENT.llm_extract <файл> [тип]"""
    import sys
    sys.path.insert(0, '/opt/wolf_v2')
    from pathlib import Path
    from CLIENT.doc_read import read_text
    from scripts.CLIENT_scan import doc_kind_name

    path = Path(sys.argv[1])
    text = read_text(path) or ''
    kind = sys.argv[2] if len(sys.argv) > 2 else doc_kind_name(path, text)
    print('файл:', path.name[:50], '| тип:', kind, '| символов:', len(text))
    got = extract_missing(text, kind)
    print('модель дала (после проверки цитатой):')
    for k, v in got.items():
        print('   %-22s %s' % (k, v))


if __name__ == '__main__':
    main()
