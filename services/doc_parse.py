"""Извлечение значений из текста документов БЕЗ языковой модели.

Работает на правилах: паспорт РФ (включая машиночитаемую зону), банковские
справки, справки о движении средств. Это базовый контур — он даёт значения
даже когда все LLM недоступны. Если правил не хватило, вызывающий код может
дополнительно спросить модель.
"""
from __future__ import annotations

_NOISE_BAD = ('NATURE OF ENGAGEMENT', 'ENGAGEMENT', 'MARITAL STATUS', 'SIGNATURE', 'OCCUPATION')


def looks_like_noise(value: str) -> bool:
    """Похоже ли значение на мусор от распознавания (одна буква в разных регистрах и т.п.).

    Ловит «Cccccceceeecececcce», «CCCCCCECEEECECECCCE» и подобные простыни, которые
    сканер отдаёт вместо отчества или места рождения. Такие значения нельзя
    записывать клиенту: они уходят в документы как часть ФИО.
    """
    v = (value or '').strip()
    if not v:
        return False
    up = v.upper()
    if any(x in up for x in _NOISE_BAD):
        return True
    letters = [ch for ch in up if ch.isalpha()]
    if len(letters) >= 6:
        same = max(letters.count(ch) for ch in set(letters)) / float(len(letters))
        vowels = sum(1 for ch in letters if ch in 'AEIOUY')
        if same >= 0.45:                      # больше половины — одна и та же буква
            return True
        if vowels == 0:                       # вообще нет гласных — не слово
            return True
        for word in up.split():
            wl = [c for c in word if c.isalpha()]
            if len(wl) >= 8 and len(set(wl)) <= 3:   # «CECEEECECECCCE»
                return True
    return False


import re

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

BANK_MARKERS = {
    "TBANK": ("тбанк", "tbank", "t-bank", "тинькофф", "tinkoff", "т-банк"),
    "SBER": ("сбербанк", "sberbank", "пао сбербанк", "sber"),
}


def _lines(text: str) -> list:
    return [ln.strip() for ln in (text or "").splitlines()]


def _latin_only(s: str) -> str:
    return re.sub(r"[^A-Za-z\- ]", "", s or "").strip()


def _ru_only(s: str) -> str:
    return re.sub(r"[^А-Яа-яЁё\- ]", "", s or "").strip()


def parse_mrz(text: str) -> dict:
    """Машиночитаемая зона паспорта РФ — самый надёжный источник.

    Строка вида  P<RUSAKHMADEEV<<CLIENT<<<<<<<<<<<<<<<<<<<<<<
                 0000000000RUS8911023M3304042<<<<<<<<<<<<<<08
    """
    out = {}
    for raw in (text or "").splitlines():
        ln = raw.replace(" ", "").upper()
        if ln.startswith("P<") and "<<" in ln and len(ln) > 25:
            rest = ln[2:]
            code = rest[:3]
            if code.isalpha():
                out["passport_country"] = code
                rest = rest[3:]
            names = [x for x in rest.split("<<") if x]
            if names:
                out["surname_latin"] = _latin_only(names[0]).title()
            if len(names) > 1:
                out["name_latin"] = _latin_only(names[1]).title()
            if len(names) > 2:
                # В паспорте РФ отчества в MRZ обычно нет: третья часть бывает
                # обрывком соседней строки («...RUS8911023M3304042...»). Берём её,
                # только если это чистое слово из букв.
                third = _latin_only(names[2]).strip()
                if re.fullmatch(r"[A-Za-z]{4,}", third or ""):
                    out["patronymic_latin"] = third.title()
        m = re.search(r"(\d{9})(\d)([A-Z]{3})(\d{2})(\d{2})(\d{2})", ln)
        if m:
            out.setdefault("passport_number", m.group(1))
            yy, mm, dd = m.group(4), m.group(5), m.group(6)
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                century = "19" if int(yy) > 30 else "20"
                out.setdefault("birth_date", f"{dd}.{mm}.{century}{yy}")
    return out


def parse_passport(text: str) -> dict:
    """Паспорт РФ: поля идут парами «подпись → значение»."""
    out = {}
    out.update({k: v for k, v in parse_mrz(text).items() if v})
    ls = _lines(text)

    JUNK = (r"(фамилия|surname|имя|given|пол|sex|дата|date|гражданство|nationality|"
            r"выдачи|issue|окончания|expiry|подпись|signature|^[mMжЖ]\s*[/|]\s*[mMжЖ]$|^\W*$)")

    def after(label_kw, max_shift=3):
        """Значение, идущее после подписи поля (учитываем шум распознавания)."""
        for i, ln in enumerate(ls):
            low = ln.lower()
            if any(k in low for k in label_kw):
                for j in range(i + 1, min(i + 1 + max_shift, len(ls))):
                    cand = ls[j]
                    if not cand or re.search(JUNK, cand.lower(), re.I):
                        continue
                    cleaned = re.sub(r"^[^A-Za-zА-Яа-яЁё]+", "", cand).strip()
                    # распознавание любит подрисовать лишний символ перед значением:
                    # «т" ИЛЬДАРОВИЧ» → «ИЛЬДАРОВИЧ»
                    cleaned = re.sub(r'^[A-Za-zА-Яа-яЁё]["\'«»]?\s+(?=[А-ЯЁA-Z]{2,})', "", cleaned).strip()
                    cleaned = re.sub(r"^(?=[MМЖжFf][\s/|]+[A-Za-zА-Яа-яЁё])[MМЖжFf][\s/|]+", "", cleaned).strip()
                    if cleaned:
                        return cleaned
        return ""

    surname_raw = after(["фамилия", "surname"])
    name_raw = after(["имя", "given"], 3)
    # «АХМАДЕЕВ / AKHMADEEV» → берём обе части
    for tok, target in ((surname_raw, "surname"), (name_raw, "name")):
        if not tok:
            continue
        ru, lat = "", ""
        for part in re.split(r"[/|]", tok):
            p = part.strip()
            if re.search(r"[А-Яа-яЁё]", p) and not ru:
                ru = _ru_only(p)
            elif re.search(r"[A-Za-z]", p) and not lat:
                lat = _latin_only(p)
        if ru:
            # в поле имени часто идёт «ИМЯ ОТЧЕСТВО» — отчество выделяем отдельно
            parts_ru = ru.split()
            if target == "name" and len(parts_ru) >= 2:
                out.setdefault("name", parts_ru[0])
                _pat = " ".join(parts_ru[1:])
                # отчество из сканера бывает мусором («Cccccceceeecececcce») —
                # такое не пишем, иначе оно уедет в ФИО документов
                if not looks_like_noise(_pat):
                    out.setdefault("patronymic", _pat)
            else:
                out.setdefault(target, ru)
        if lat:
            out.setdefault(target + "_latin", lat.title())

    # Паспорт РФ: в поле «Имя» стоит «ИМЯ ОТЧЕСТВО». Если распознавание потеряло
    # первое слово, в имени остаётся только отчество — и тогда в документ уходило
    # два слова вместо трёх. Ловим это по окончанию и переносим куда следует.
    nm = (out.get("name") or "").strip()
    if nm:
        nm_parts = nm.split()
        tail = nm_parts[-1]
        if len(nm_parts) == 1 and _PATRONYMIC_END.search(tail):
            out["patronymic"] = nm
            out["name"] = ""
            out["name_missing"] = "1"
        elif len(nm_parts) >= 2 and _PATRONYMIC_END.search(tail):
            # «ДАНИЭЛЬ ИЛЬДАРОВИЧ» → имя и отчество по отдельности
            out["name"] = " ".join(nm_parts[:-1])
            out["patronymic"] = tail

    # Имя кириллицей потерялось при распознавании — пробуем узнать его из
    # латинского написания в машиночитаемой зоне (там оно есть всегда).
    if out.get("name_missing") and out.get("name_latin"):
        cand = _name_from_latin(ls, out["name_latin"], out.get("surname") or "")
        if cand:
            out["name"] = cand
            out.pop("name_missing", None)

    pl = after(["место рождения", "place of birth"], 3)
    if pl:
        # в одной строке часто идут и пол, и место рождения: «M/M KASAHb / USSR»
        pl = re.sub(r"^[MМЖжFf][\s/|]+[MМЖжFf]?[\s/|]*", "", pl).strip()
    if pl and re.search(r"[A-Za-zА-Яа-яЁё]{3,}", pl):
        _bp = (_ru_only(pl.split("/")[0]) or pl.split("/")[0].strip())
        # мусор вроде одной буквы «K» из строки пола в место рождения не годится
        if len(re.sub(r"[^A-Za-zА-Яа-яЁё]", "", _bp)) >= 3:
            out.setdefault("birth_place", _bp)

    # Серия и номер загранпаспорта РФ: 2 знака серии + 7 знаков номера
    # («66 7183114»). Внутренний паспорт — 4+6. OCR легко путает разделители
    # и вставляет «№», поэтому допускаем любые разделители и ищем в первую
    # очередь рядом со словом «паспорт»/«Passport No».
    _t = text or ""
    _pn = ""
    for _pat in (r"\b(\d{2})\s*[№#N]?\s*(\d{7})\b", r"\b(\d{4})\s*[№#N]?\s*(\d{6})\b"):
        _near = re.search(r"(?:passport\s*no|паспорт|№)[^\n]{0,40}?" + _pat, _t, re.I)
        _m = _near or re.search(_pat, _t)
        if _m:
            _pn = _m.group(1) + _m.group(2)
            break
    if _pn:
        out.setdefault("passport_number", _pn)
    # серия отдельной переменной: 2 знака у загранпаспорта, 4 у внутреннего
    if out.get("passport_number") and not out.get("passport_series"):
        _digits = re.sub(r"\D", "", out["passport_number"])
        if len(_digits) >= 10:
            out["passport_series"] = _digits[:4]
        elif len(_digits) >= 9:
            out["passport_series"] = _digits[:2]
    # кем выдан и когда — подписи полей в обоих вариантах написания
    _ib = after(["кем выдан", "выдан", "issued by"], 4)
    if _ib and len(_ib) > 8:
        out.setdefault("passport_issued_by", (_ru_only(_ib) or _ib)[:120])
    _idt = after(["дата выдачи", "date of issue", "выдачи"], 2)
    _m = re.search(r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})", _idt or "")
    if _m:
        out.setdefault("passport_issue_date", _m.group(1))
    # страховка: если номер не найден, пробуем вытащить его из машиночитаемой зоны
    if not out.get("passport_number"):
        for _line in (text or "").splitlines():
            _l = _line.strip()
            if _l[:2].upper() in ("P<", "P<RU") and "<<" in _l:
                _m2 = re.search(r"([A-Z0-9]{9})", _l[3:])
                if _m2:
                    _cand = re.sub(r"\D", "", _m2.group(1))
                    if len(_cand) >= 9:
                        out["passport_number"] = _cand[:2] + _cand[2:9]
                        break
    m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", text or "")
    if m:
        out.setdefault("birth_date", m.group(1))
    if re.search(r"МИД РОССИИ|MVD|ОВД|УФМС", text or "", re.I):
        m = re.search(r"(МИД РОССИИ[^\n]{0,20}|[А-Я]{2,}\s?\d{3,6})", text or "")
        if m:
            out.setdefault("passport_authority", m.group(1).strip())
    if re.search(r"РОССИЙСКАЯ ФЕДЕРАЦИЯ|RUSSIAN FEDERATION", text or "", re.I):
        out.setdefault("citizenship", "РОССИЙСКАЯ ФЕДЕРАЦИЯ")

    # ФИО латиницей целиком — из машиночитаемой зоны (там порядок имя+фамилия)
    ln, sn = out.get("name_latin"), out.get("surname_latin")
    if ln and sn:
        out["full_name_latin"] = f"{ln} {sn}".upper()
        out["full_name_ru"] = " ".join(x for x in (out.get("surname"), out.get("name"),
                                                   out.get("patronymic")) if x)
    return {k: v for k, v in out.items() if v}


def detect_bank(text: str) -> str:
    low = (text or "").lower()
    for code, keys in BANK_MARKERS.items():
        if any(k in low for k in keys):
            return code
    return ""


def parse_bank_statement(text: str) -> dict:
    """Банковская справка: ФИО латиницей, адрес, счёт, банк, остаток, период."""
    out, t = {}, text or ""
    m = re.search(r"^((?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+)\s*$", t, re.M)  # Ivan Ivanov Ivanovich
    # в шапке справки встречается название самого документа — в ФИО оно не годится
    _noise = ("bank", "statement", "balance", "certificate", "incorporation", "incumbency",
              "account", "document", "agreement", "limited", "company", "details")
    if m and not any(w in m.group(1).lower() for w in _noise):
        out["full_name_latin"] = m.group(1).strip()
    m = re.search(r"([А-Я][а-яё]+\s+[А-Я][а-яё]+\s+[А-Я][а-яё]+)", t)
    if m:
        out["full_name_ru"] = m.group(1)
    bank = detect_bank(t)
    if bank:
        out["bank_name"] = bank
    # Адрес проживания для банковской справки — это адрес в СТРАНЕ КЛИЕНТА,
    # а не место пребывания в Индонезии. Берём его в первую очередь из строки
    # «Home address:» (там адрес из прошлой справки/анкеты), затем из
    # «Registration address:», и только потом — любой похожий на адрес блок.
    m = re.search(r"Registration address[:\s]*([^\n]{5,120})", t, re.I)
    if m:
        out["address_reg"] = m.group(1).strip(" .;")
    m = re.search(r"Home address[:\s]*([^\n«]{5,120})", t, re.I)
    if m:
        # после адреса в справке сразу идёт текст банка — обрезаем по нему
        _a = re.split(r"\s*(?:«|RUB|The card|the Bank)\b", m.group(1))[0]
        out["address_live"] = _a.strip(" .,;")
    if not out.get("address_live"):
        m = re.search(r"(\d{6},\s?[^\n]{5,90})", t)                    # 442770, Penzenskaya Obl, ...
        if m:
            out["address_live"] = m.group(1).strip()
    m = re.search(r"(?:IBAN|Счет|Account)[^\n]{0,10}([A-Z]{2}\d{2}[A-Z0-9]{8,26})", t, re.I)
    if m:
        out["account_no"] = m.group(1)
    m = re.search(r"(\d{1,3}(?:[ .,]\d{3})+[ .,]\d{2})\s*(?:IDR|IDR\.|Rp)", t, re.I)
    if m:
        out["balance_idr"] = m.group(1).replace(" ", "")
    m = re.search(r"[Pр]ериод[^\n]{0,40}?(\d{2}[.\-/]\d{2}[.\-/]\d{4})[^\d]{0,20}(\d{2}[.\-/]\d{2}[.\-/]\d{4})", t, re.I)
    if m:
        out["period_from"], out["period_to"] = m.group(1), m.group(2)

    # Справка Т-Банка о карте: «As from 21.09.2025 to 21.09.2026 the deposit
    # balance is 6 921 309, 00 rubles (six million … rubles 00 kopeks)»
    if not out.get("period_from"):
        m = re.search(r"As\s+from\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})\s+to\s+"
                      r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})", t, re.I)
        if m:
            out["period_from"], out["period_to"] = m.group(1), m.group(2)
    if not out.get("balance_rub"):
        m = re.search(r"deposit\s+balance\s+is\s+([\d\s\u00a0]{3,}(?:[.,]\s?\d{2})?)\s*rub", t, re.I)
        if m:
            digits = re.sub(r"\D", "", m.group(1))
            # в справке остаток печатают с копейками: «6 921 309, 00» —
            # в документы идёт сумма в рублях, без копеек
            if len(digits) > 2 and re.search(r"[.,]\s?\d{2}\s*$", m.group(1)):
                digits = digits[:-2]
            out["balance_rub"] = digits or m.group(1).strip()
    if not out.get("balance_words"):
        m = re.search(r"deposit\s+balance\s+is[^(]{0,60}\(([^)]{10,})\)", t, re.I)
        if m:
            # строку рвёт переносом: «twenty-one \nthousand …» — склеиваем в одну
            out["balance_words"] = re.sub(r"\s+", " ", m.group(1)).strip().capitalize()
    if not out.get("balance_date") and out.get("period_to"):
        out["balance_date"] = out["period_to"]
    # Итоговые строки выписки — приоритетнее промежуточных оборотов
    if not out.get("balance_rub"):
        m = (re.search(r"(?:total\s+balance|итого|остаток\s+на\s+конец|остаток\s+по\s+сч[её]ту)"
                       r"[^\n]{0,60}?([\d\s\u00a0]{4,18}[.,]\d{2})", t, re.I)
             or re.search(r"(?:Итого|ИТОГО)[^\n]{0,80}?([\d\s\u00a0]{4,18}[.,]\d{2})\s*(?:₽|RUB|руб)", t))
        if m:
            out["balance_rub"] = m.group(1).replace(" ", "").replace("\u00a0", "")
    # --- выписка Т-Банка (и похожие англоязычные) ---------------------------
    # «Amount of available balance as 17.09.2026: 2 757 201.00 ₽»
    # сумма бывает и с одной цифрой после запятой («2 622 457,8 ₽») —
    # из-за жёсткого требования двух знаков такие справки раньше оставались без остатка
    if not out.get("balance_rub"):
        m = (re.search(r"available balance[^\n]{0,40}?(\d{2}[.\-/]\d{2}[.\-/]\d{4}):\s*"
                       r"([\d\s]{1,18}[.,]\d{1,2})", t, re.I)
             or re.search(r"(?:balance|остаток)[^\n]{0,30}?(\d{2}[.\-/]\d{2}[.\-/]\d{4}):\s*"
                          r"([\d\s]{1,18}[.,]\d{1,2})", t, re.I))
        if m:
            out["balance_rub"] = m.group(2).replace(" ", "").replace("\u00a0", "")
    # --- справка о доступном остатке (Т-Банк, русское имя файла) -------------
    # «Available balance on 14.10.2026 … RUB The card was not issued 294778.42 RUB»
    # Сумма стоит перед словом RUB и может быть далеко от заголовка: между
    # «Available balance» и числом лежат счёт, валюта и примечание о карте.
    if not out.get("balance_rub"):
        # «available balance» встречается в самом заголовке («Document on the
        # available balance № …»), поэтому ищем по всему тексту и берём
        # ПОСЛЕДНЕЕ число с копейками перед RUB — именно оно и есть остаток.
        _cands = re.findall(r"(\d[\d\s\u00a0]{0,12}[.,]\d{2})\s*(?:RUB|₽)", t, re.I)
        if _cands:
            out["balance_rub"] = (_cands[-1].replace(" ", "").replace("\u00a0", "")
                                  .replace(",", "."))
    if not out.get("balance_date"):
        m = re.search(r"available\s+balance\s+on\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})", t, re.I)
        if m:
            out["balance_date"] = m.group(1)
    # маска карты: «5519 60** **** 0587», «****0587», «551960******0587»
    if not out.get("card_mask"):
        m = re.search(r"((?:\d{2,4}[\s-]?){1,4}[*\u2022]{2,}[\s-]?(?:[*\u2022]{2,}[\s-]?){0,4}\d{4})", t)
        if not m:
            m = re.search(r"([*\u2022]{4,}\s?\d{4})", t)
        if m:
            out["card_mask"] = re.sub(r"\s+", " ", m.group(1)).strip()
    # сумма прописью — считаем из цифр остатка, детерминированно, без модели
    if out.get("balance_rub") and not out.get("balance_words"):
        try:
            from bot.ai_parser import amount_in_words_en, parse_amount
            _v = parse_amount(out["balance_rub"])
            if _v:
                out["balance_words"] = amount_in_words_en(_v)
        except Exception:                                  # noqa: BLE001
            pass
    # дата, на которую показан остаток
    if out.get("balance_rub") and not out.get("balance_date"):
        m = re.search(r"(?:available balance|balance|остаток)[^\n]{0,40}?"
                      r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})", t, re.I)
        if m:
            out["balance_date"] = m.group(1)
    # «Movement of funds for the period from 17.09.2025 to 17.09.2026»
    if not out.get("period_from"):
        m = re.search(r"(?:period|период)[^\n]{0,30}?from\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})\s+to\s+"
                      r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})", t, re.I)
        if m:
            out["period_from"], out["period_to"] = m.group(1), m.group(2)
    # «Personal account number: 40817810800103411506»
    if not out.get("account_no"):
        m = re.search(r"(?:personal|account|счёт|счет)[^\n]{0,20}?(?:number|no\.?|№)?[:\s]*"
                      r"(\d{15,25})", t, re.I)
        if m:
            out["account_no"] = m.group(1)
    # «17.09.2026 № b8a75f3a» — дата выписки и её номер
    m = re.search(r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})\s*[№N]\s*([A-Za-z0-9]{4,20})", t)
    if m:
        out.setdefault("statement_date", m.group(1))
        out.setdefault("doc_no", m.group(2))
    # исходящая ссылка банка со датой: «Ref. B19289961ADL 02.10.2026» —
    # именно она стоит в наших справках в поле исходящего номера
    m = re.search(r"Ref\.?\s*:?\s*([A-Z0-9]{6,20})\s*(\d{2}[.\-/]\d{2}[.\-/]\d{4})?", t)
    if m:
        out.setdefault("ref_no", m.group(1))
        if m.group(2):
            out.setdefault("ref_date", m.group(2))
    # номер документа: «No ae32271197» / «№ 9061»
    m = re.search(r"\bNo\.?\s*:?\s*([a-z]{0,2}\d{4,14})\b", t, re.I)
    if m:
        out.setdefault("doc_no", m.group(1))
    # договор клиента с банком: «Date of conclusion of the contract: 11.10.2021»,
    # «Contract number: 5516584280» — в наших справках это отдельные переменные
    m = (re.search(r"date of conclusion of the? contract[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4})", t, re.I)
         or re.search(r"date of (?:the )?(?:contract|agreement)[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4})", t, re.I))
    if m:
        out.setdefault("contract_date", m.group(1))
    m = re.search(r"contract number[:\s]*([A-Za-z0-9\-/]{4,24})", t, re.I)
    if m:
        out.setdefault("contract_no", m.group(1).strip())
    return {k: v for k, v in out.items() if v}


# Адрес в Индонезии — это место пребывания (отель, вилла, пермит), а не адрес
# проживания для банковских документов: там всегда должна быть страна клиента.
_INDONESIA_RE = re.compile(
    r"bali|indonesia|indonez|kabupaten|kecamatan|kec\.|kelurahan|denpasar|badung|"
    r"\bjl\.?\s|provinsi|munggu|ubud|kuta|canggu|seminyak|sanur|\bidr\b",
    re.I)


def is_indonesia_address(value: str) -> bool:
    """Похож ли адрес на индонезийский (место пребывания, а не страна клиента)."""
    return bool(_INDONESIA_RE.search(str(value or "")))


# Российский адрес: индекс из 6 цифр в начале или явные приметы страны.
_RUSSIA_RE = re.compile(
    r"^\s*\d{6}\b|russia|russian federation|moscow|moskva|saint petersburg|"
    r"\bobl\b|\bkrai\b|resp |респ|обл|край|москва|санкт|росси",
    re.I)


def is_russian_address(value: str) -> bool:
    """Адрес в России — именно такой нужен банковским справкам (Сбер, Т-Банк)."""
    return bool(_RUSSIA_RE.search(str(value or ""))) and not is_indonesia_address(value)


# ---------------------------------------------------------------- виза / eVisa
# Индонезийская eVisa (E33G, B211, C1) — отдельный тип документа со своими
# переменными: номер визы, тип, срок, кем выдана. Именно отсюда берётся
# номер визы, которого нет ни в паспорте, ни в карточке ВНЖ.
_VISA_FIELDS = {
    "visa_no": (r"visa\s*no[^:]{0,20}[:.]?\s*([A-Z0-9\-/]{8,24})",),
    "reference_no": (r"reference\s*no[^:]{0,20}[:.]?\s*([A-Z0-9\-/]{8,26})",),
    "visa_type": (r"visa\s*type[^:]{0,20}[:.]?\s*([A-Za-z ]{4,40})",),
    "date_of_issue": (r"date of issue[^:]{0,24}[:.]?\s*([0-3]?\d[./-][01]?\d[./-]\d{4})",),
    "valid_until": (r"(?:valid until|expiry date|berlaku sampai|expired)[^:]{0,24}[:.]?\s*"
                    r"([0-3]?\d[./-][01]?\d[./-]\d{4})",),
    "place_of_birth": (r"place of birth[^:]{0,24}[:.]?\s*([A-Za-zА-Яа-я ,.\-]{3,40})",),
    "date_of_birth": (r"date of birth[^:]{0,24}[:.]?\s*([0-3]?\d[./-][01]?\d[./-]\d{4})",),
    "client_gender": (r"(?:sex|jenis kelamin)[^:]{0,20}[:.]?\s*(MALE|FEMALE|LAKI-LAKI|PEREMPUAN)",),
    "nationality": (r"nationality[^:]{0,24}[:.]?\s*([A-Za-zА-Яа-я ]{3,30})",),
}

_VISA_MARKERS = ("evisa", "visa no", "limited stay visa", "kementerian imigrasi",
                 "direktorat jenderal imigrasi", "nomor visa")


def parse_visa(text: str) -> dict:
    """Индонезийская виза: номер, тип, сроки, кто выдан."""
    out, t = {}, text or ""
    for var, pats in _VISA_FIELDS.items():
        for p in pats:
            m = re.search(p, t, re.I)
            if m:
                val = re.sub(r"\s+", " ", m.group(1)).strip(" .;,")
                if val and len(val) >= 2:
                    out.setdefault(var, val)
                    break
    # «Nomor Visa : 26E33G881594» — номер может стоять и без слова Visa No
    if not out.get("visa_no"):
        m = re.search(r"\b(\d{2}E33G\d{6}|\d{2}[A-Z]{3}\d{6})\b", t)
        if m:
            out["visa_no"] = m.group(1)
    if out.get("visa_no"):
        out.setdefault("bridging_visa_no", out["visa_no"])
    return {k: v for k, v in out.items() if v}


def is_visa_text(text: str) -> bool:
    """Это визовый документ.

    Одного слова «visa» или «E33G» мало: они встречаются в письмах-поручительствах
    и договорах, и по ним документ ошибочно разбирался как виза — «находился»
    номер визы в письме родителя. Признак должен быть визовый по существу:
    либо поле «Visa No / Nomor Visa», либо шапка иммиграционной службы.
    """
    low = (text or "").lower()[:1500]
    if "visa no" in low or "nomor visa" in low or "evisa" in low:
        return True
    return "kementerian imigrasi" in low and "visa type" in low


def parse_any(text: str, doc_type: str) -> dict:
    """Значения из текста с учётом типа документа (без модели)."""
    t = text or ""
    _up = t.upper()[:700]
    # визу проверяем раньше всего: её текст содержит и «stay permit», и «passport»
    # (в полях разрешения), из-за чего она раньше уходила в ветку ВНЖ или паспорта
    _is_visa = doc_type == "visa" or is_visa_text(t)

    if _is_visa:
        vals = parse_visa(t)
    elif doc_type == "itk" or "PERMIT NUMBER" in _up or "STAY PERMIT EXPIRY" in _up:
        try:
            from services.itk_doc import parse_itk_text
            vals = {k: v for k, v in (parse_itk_text(t) or {}).items() if v}
        except Exception:                          # noqa: BLE001
            vals = {}
        # имена, которыми пользуются шаблоны писем и E-02
        if vals.get("permit_no"):
            vals.setdefault("itk_no", vals["permit_no"])
            vals.setdefault("stay_permit_no", vals["permit_no"])
        if vals.get("permit_expiry"):
            vals.setdefault("itk_expiry", vals["permit_expiry"])
    elif doc_type == "passport" or "PASSPORT" in _up or "ФАМИЛИЯ" in _up or "SURNAME" in _up:
        vals = parse_passport(t)
    elif doc_type in ("bank_balance", "bank_movement"):
        vals = parse_bank_statement(t)
    elif doc_type in ("photo", "other", "contract", "resume"):
        # корпоративные бумаги, фото, договоры и резюме: своих переменных здесь нет,
        # а свободный поиск по тексту давал мусор (название компании попадало в ФИО)
        vals = {}
    else:
        vals = {}
        vals.update(parse_mrz(t))
        vals.update(parse_bank_statement(t))

    # отсекаем индонезийские адреса: для банковских документов нужен адрес
    # в стране клиента, а Индонезия — это место пребывания
    if vals.get("address_live") and is_indonesia_address(vals["address_live"]):
        vals["address_indonesia"] = vals.pop("address_live")
    if vals.get("address_indonesia") and vals.get("address_reg") \
            and not is_indonesia_address(vals["address_reg"]):
        vals["address_live"] = vals["address_reg"]
    # одно и то же значение в шаблонах живёт под разными именами: паспорт РФ —
    # passport_number, письма и E-02 — passport_no; ВНЖ — permit_no и itk_no
    if vals.get("passport_number") and not vals.get("passport_no"):
        vals["passport_no"] = vals["passport_number"]
    if vals.get("passport_expiry") and not vals.get("passport_valid_until"):
        vals["passport_valid_until"] = vals["passport_expiry"]
    if vals.get("itk_no") and not vals.get("stay_permit_no"):
        vals["stay_permit_no"] = vals["itk_no"]
    if vals.get("itk_expiry") and not vals.get("stay_permit_expiry"):
        vals["stay_permit_expiry"] = vals["itk_expiry"]
    return vals


# переменная конструктора -> колонка карточки клиента
TO_CLIENT = {
    "surname": "surname", "name": "name", "patronymic": "patronymic",
    "surname_latin": "surname", "name_latin": "name", "patronymic_latin": "patronymic",
    "full_name_latin": "full_name_latin", "full_name_ru": "full_name_ru",
    "birth_date": "birth_date", "birth_place": "birth_place",
    "passport_number": "passport_number", "citizenship": "citizenship",
    "address_live": "address_live", "bank_name": "bank_name",
}

_PATRONYMIC_END = re.compile(r"(ович|евич|ьевич|овна|евна|ична|инична|овны|евич)$", re.I)


def _name_from_latin(lines: list, name_latin: str, surname_ru: str) -> str:
    """Кириллическое имя по латинскому написанию из MRZ.

    Ищем в тексте кириллические слова, которые не фамилия и не отчество, и
    сверяем их с латиницей по началу слова (ДАН→DAN). Совпало ровно одно —
    берём его; иначе лучше оставить пусто, чем подставить неверное.
    """
    key = re.sub(r"[^A-Za-z]", "", (name_latin or "")).upper()[:3]
    if len(key) < 3:
        return ""
    sur_key = re.sub(r"[^А-Яа-яЁё]", "", (surname_ru or "")).upper()
    hits = []
    for ln in lines:
        for word in re.findall(r"[А-ЯЁ][А-Яа-яЁё\-]{2,}", ln or ""):
            w = word.upper()
            if w == sur_key or _PATRONYMIC_END.search(w):
                continue
            if any(w.startswith(x) for x in ("ФАМИЛИЯ", "ИМЯ", "ОТЧЕСТВО", "РОССИЙСКАЯ",
                                             "ГРАЖДАНСТВО", "ПАСПОРТ", "ПОЛ", "МЕСТО",
                                             "ДАТА", "ВЫДАЧИ", "ОКОНЧАНИЯ", "ОРГАН")):
                continue
            hits.append(w)
    # сопоставляем начало слова с латиницей: ДАНИЭЛЬ → DAN
    fits = [w for w in hits if _cyr_to_latin_head(w, len(key)) == key]
    if len(set(fits)) == 1:
        return fits[0].title()
    return ""


def _cyr_to_latin_head(word: str, n: int) -> str:
    """Первые n латинских букв транслитерации кириллического слова."""
    table = {"А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
             "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
             "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
             "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
             "Ы": "Y", "Э": "E", "Ю": "YU", "Я": "YA", "Ь": "", "Ъ": ""}
    out = ""
    for ch in (word or "").upper():
        out += table.get(ch, "")
        if len(out) >= n:
            break
    return out[:n]
