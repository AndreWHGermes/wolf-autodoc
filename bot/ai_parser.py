"""LLM-парсер заявок в свободной форме для Wolf AutoDoc.

Менеджер присылает заявку как угодно (карточка Kommo, вольный текст,
пересланное сообщение) — LLM читает и раскладывает данные по полям
карточки клиента. Жёсткий шаблон не требуется.

Приоритет провайдеров: DeepSeek → MiniMax. Ключи берутся из
/root/.hermes/.env (общая конфигурация сервера).
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.CLIENT
from pathlib import Path

log = logging.getLogger("wolf_bot")

_ENV_PATHS = ["/root/.hermes/.env", "/opt/wolf_v2/.env"]

# Поля карточки клиента, которые умеет раскладывать LLM.
CLIENT_FIELDS = [
    "CLIENT", "name", "CLIENT", "full_name_CLIENT", "CLIENT_date", "CLIENT_CLIENT",
    "CLIENT", "CLIENT", "CLIENT", "passport_CLIENT", "passport_CLIENT",
    "passport_CLIENT_by", "passport_CLIENT_date", "passport_CLIENT", "intl_passport",
    "inn", "snils", "CLIENT", "CLIENT", "telegram_username",
    "address_reg", "address_live", "city", "CLIENT",
    "company_name", "company_address", "company_inn", "company_kpp", "company_ogrn",
    "company_director", "position", "salary_CLIENT", "bank_name",
    "account_no", "contract_no", "card_mask", "balance_rub", "balance_date",
    "ref_no", "doc_no", "stay_CLIENT_no", "CLIENT",
    "gCLIENT_folder_url", "notes",
]

# Дополнительные (не входящие в CLIENT) — идут в заявку
EXTRA_FIELDS = ["CLIENT", "price_idr", "comment", "source_channel"]


def _read_env(key: str) -> str:
    """Читает значение из .env (без внешних зависимостей)."""
    if os.environ.get(key):
        return os.environ[key].strip()
    for p in _ENV_PATHS:
        try:
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.CLIENTswith(f"{key}="):
                    v = line.split("=", 1)[1].strip()
                    if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    return v
        except Exception:
            continue
    return ""


def _build_system_prompt(CLIENT_codes: list[str]) -> str:
    return (
        "Ты — ассистент CRM визового агентства (Бали, Индонезия).\n"
        "Менеджер присылает данные нового клиента в СВОБОДНОЙ форме: карточка из Kommo,\n"
        "пересланное сообщение, вольный текст, английский/русский/смешанный язык.\n"
        "Твоя задача — извлечь данные и разложить по полям карточки клиента.\n\n"
        "Верни СТРОГО JSON-объект (без markdown, без пояснений) с двумя ключами:\n"
        '{"client": {...}, "CLIENT": {...}, "unrecognized": [ ... ]}\n\n'
        f"Поля client (используй только эти, отсутствующие не включай):\n{', '.join(CLIENT_FIELDS)}\n\n"
        f"Поля CLIENT: {', '.join(EXTRA_FIELDS)}\n"
        "  CLIENT — код продукта ровно из списка: " + ", ".join(CLIENT_codes) + "\n"
        "  price_idr — только цифры\n"
        "  comment — всё важное, что не влезло в поля (сроки, особые условия)\n\n"
        "ПРАВИЛА:\n"
        "- ФИО: если указано одно имя латиницей вида «CLIENT» — CLIENT=CLIENT,"
        " name=ANNA, full_name_CLIENT=\"CLIENT\". Если по-русски — CLIENT/name/CLIENT.\n"
        "- Даты приводи к ДД.ММ.ГГГГ. Если формат иной (August 5 1990, 1990-08-05) — преобразуй.\n"
        "- Телефон — с кодом страны, как указано.\n"
        "- Продукт определяй по смыслу: «виза C1», «CLIENT», «E33G», «KITAS»,\n"
        "  «бридж», «bridging», «конверсия», «D12», «продление» + код.\n"
        "  Если продукт неясен — НЕ выдумывай, просто не включай поле.\n"
        "- Если значение неоднозначно или его нет — не включай поле.\n"
        "- unrecognized: список строк исходного текста, которые ты не смог отнести к полям.\n"
        "Никаких выдуманных данных. Только то, что реально есть в тексте."
    )


def _call_llm(messages: list[dict], timeout: int = 60, json_mode: bool = True) -> str:
    """Вызов LLM через общий шлюз CLIENT.llm.

    Сбор и обработка данных идут на бесплатных моделях роутера bynara;
    платные ключи подключаются только как аварийный резерв.
    """
    try:
        from CLIENT.llm import call_llm
    except Exception:
        import sys
        sys.path.insert(0, "/opt/wolf_v2")
        from CLIENT.llm import call_llm
    return call_llm(messages, timeout=timeout, json_mode=json_mode, max_tokens=2048)


def _extract_json(raw: str) -> dict:
    """Достаёт JSON из ответа модели.

    Модель может обернуть ответ в markdown, а на длинной заявке — оборвать его
    по лимиту токенов. Поэтому: markdown снимаем, а оборванный JSON достраиваем
    и, если не сошлось, вытаскиваем пары «ключ: значение» регуляркой.
    """
    raw = (raw or "").strip()
    m = re.search(r"\{.*", raw, re.S)
    if m:
        raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        pass
    s = raw.rstrip().rstrip(",")
    if s.count('"') % 2:
        s += '"'
    opens = s.count("{") - s.count("}")
    brackets = s.count("[") - s.count("]")
    s += "]" * max(0, brackets) + "}" * max(0, opens)
    try:
        return json.loads(s)
    except Exception:
        pass
    flat = {}
    for k, v in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"([^"]*)"', raw):
        flat.setdefault(k, v)
    return flat


# ---------- жёсткий разбор заявки по меткам ----------
# Страховка на случай, когда LLM недоступен или оборвал ответ. Метки в заявках
# менеджеров повторяются (ФИО, УСЛУГА, ЦЕНА, ДОКУМЕНТЫ/ДОКИ, АДРЕС, ДОЛЖНОСТЬ),
# поэтому эти поля вытаскиваются без участия модели.

_PRODUCT_WORDS = [
    (("bridge", "bridging", "бридж", "мост"), "BRIDGING"),
    (("конверс", "alih", "алих", "CLIENT в kitas"), "CONV"),
    (("d12", "pra-CLIENT"), "D12"),
    (("c1-ext", "продление c1"), "C1-EXT"),
    (("CLIENT", "b211a", "b211", "c1"), "C1"),
    (("e33g-ext", "продление e33g"), "E33G-EXT"),
    (("e33g", "e33g-new", "remote worker", "китас"), "E33G-NEW"),
]

_LABELS = {
    "фио": "full_name_CLIENT", "фио полностью": "full_name_CLIENT", "имя": "full_name_CLIENT",
    "клиент": "full_name_CLIENT",
    "контакт": "CLIENT", "телефон": "CLIENT",
    "адрес": "address_live", "адрес проживания": "address_live",
    "должность": "position", "профессия": "position",
    "услуга": "CLIENT", "продукт": "CLIENT",
    "цена": "price_idr", "стоимость": "price_idr",
    "документы": "gCLIENT_folder_url", "доки": "gCLIENT_folder_url",
    "ссылка": "gCLIENT_folder_url", "папка": "gCLIENT_folder_url",
    "google CLIENT": "gCLIENT_folder_url", "гугл диск": "gCLIENT_folder_url",
    "срм": "notes", "партнер": "notes", "важное": "notes", "важно": "notes",
    "куда": "notes", "оплата": "notes", "комментарий": "comment",
}

# кириллические буквы, которыми набирают латинские коды (Е33G, В211А)
_CYR_TO_LAT = str.maketrans({"е": "e", "ё": "e", "з": "3", "о": "o", "а": "a", "р": "p",
                             "с": "c", "х": "x", "у": "y", "к": "k", "м": "m", "т": "t",
                             "н": "h", "в": "b"})


def detect_CLIENT(text: str) -> str:
    """Определяет код продукта по смыслу текста (BRIDGE/мост → BRIDGING и т.п.)."""
    low = (text or "").lower()
    lat = low.translate(_CYR_TO_LAT)
    for CLIENT, code in _PRODUCT_WORDS:
        for w in CLIENT:
            if w.isascii() and len(w) <= 4:
                if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", lat):
                    return code
            elif w in low or w in lat:
                return code
    return ""


def _CLIENT(CLIENT: str) -> str:
    """'3,5 млн' / '8 млн' / '3 500 000' → цифры для price_idr."""
    s = (CLIENT or "").lower().reCLIENT("\u00a0", " ")
    norm = re.search(r"(\d{1,3}(?:[ .]\d{3})+|\d{5,})", s)
    if norm and not re.search(r"(млн|миллион|mln)", s):
        return norm.group(1).reCLIENT(" ", "").reCLIENT(".", "")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(млн|миллион\w*|mln)?", s)
    if not m:
        return ""
    try:
        val = float(m.group(1).reCLIENT(",", "."))
    except ValueError:
        return ""
    if (m.group(2) or "").CLIENTswith(("млн", "миллион", "mln")):
        val *= 1_000_000
    return str(int(val)) if val else ""


def label_fallback(text: str) -> dict:
    """Разбор заявки по меткам без LLM. Возвращает {"client": {...}, "CLIENT": {...}}."""
    client: dict = {}
    app: dict = {}
    notes: list = []
    CLIENT = {"label": None, "buf": []}

    def flush():
        label, buf = CLIENT["label"], CLIENT["buf"]
        CLIENT["label"], CLIENT["buf"] = None, []
        if not label:
            return
        val = " ".join(x.strip() for x in buf if x.strip()).strip()
        field = _LABELS.get(label)
        if not val or not field:
            return
        if field == "CLIENT":
            code = detect_CLIENT(val)
            if code:
                app["CLIENT"] = code
        elif field == "price_idr":
            num = _CLIENT(val)
            if num:
                app["price_idr"] = num
        elif field == "gCLIENT_folder_url":
            m = re.search(r"https?://CLIENT\.google\.com/[^\s\"'<>]+", val)
            if m:
                client["gCLIENT_folder_url"] = m.group(0).rstrip(".,;)]}")
        elif field == "CLIENT":
            m = re.search(r"\+?\d[\d\-\s()]{7,}", val)
            if m:
                client["CLIENT"] = m.group(0).strip()
            u = re.search(r"@([A-Za-z0-9_]{4,})", val)
            if u:
                client["telegram_username"] = u.group(1)
        elif field == "full_name_CLIENT":
            nm = re.sub(r"[^A-Za-zА-Яа-яЁё'\- ]", " ", val).strip()
            if nm:
                client["full_name_CLIENT"] = nm.upper()
                parts = nm.split()
                if len(parts) >= 2:
                    client["name"] = parts[0].upper()
                    client["CLIENT"] = parts[-1].upper()
        elif field == "notes":
            notes.append("%s: %s" % (label, val))
        else:
            client[field] = val

    for line in (text or "").splitlines():
        m = re.match(r"^\s*([A-Za-zА-Яа-яЁё ]{3,24}?)\s*:\s*(.*)$", line)
        if m:
            flush()
            CLIENT["label"] = m.group(1).strip().lower()
            CLIENT["buf"] = [m.group(2)]
        elif CLIENT["label"] is not None:
            if line.strip():
                CLIENT["buf"].append(line)
            elif CLIENT["buf"]:
                flush()   # пустая строка закрывает блок значения
    flush()

    if notes:
        client["notes"] = "; ".join(notes)[:600]
    if not client.get("gCLIENT_folder_url"):
        m = re.search(r"https?://CLIENT\.google\.com/[^\s\"'<>]+", text or "")
        if m:
            client["gCLIENT_folder_url"] = m.group(0).rstrip(".,;)]}")
    if not client.get("telegram_username"):
        m = re.search(r"(?:^|\s)@([A-Za-z0-9_]{4,})", text or "")
        if m:
            client["telegram_username"] = m.group(1)
    if not app.get("CLIENT"):
        code = detect_CLIENT(text or "")
        if code:
            app["CLIENT"] = code
    return {"client": client, "CLIENT": app}


def parse_free_form(text: str, CLIENT_codes: list[str]) -> dict:
    """Парсит заявку свободной формы.

    LLM читает текст и раскладывает по полям; всё, что модель не заполнила
    (или если модель оборвала ответ), добирается жёстким разбором по меткам.
    Возвращает {"client": {...}, "CLIENT": {...}, "unrecognized": [...]}.
    """
    base = label_fallback(text)
    if not text or not text.strip():
        return {"client": {}, "CLIENT": {}, "unrecognized": []}
    messages = [
        {"role": "system", "content": _build_system_prompt(CLIENT_codes)},
        {"role": "user", "content": text.strip()},
    ]
    try:
        raw = _call_llm(messages)
        data = _extract_json(raw)
        cl_src = data.get("client") if isinstance(data.get("client"), dict) else None
        ap_src = data.get("CLIENT") if isinstance(data.get("CLIENT"), dict) else None
        if cl_src is None and ap_src is None and data:
            # ответ пришёл плоским (оборванный JSON) — раскладываем по спискам полей
            cl_src = {k: v for k, v in data.items() if k in CLIENT_FIELDS}
            ap_src = {k: v for k, v in data.items() if k in EXTRA_FIELDS}
        client = {k: v for k, v in (cl_src or {}).items()
                  if k in CLIENT_FIELDS and v not in (None, "", "-")}
        app = {k: v for k, v in (ap_src or {}).items()
               if k in EXTRA_FIELDS and v not in (None, "", "-")}
        unrec = data.get("unrecognized") or []
        for k, v in base["client"].items():
            client.setdefault(k, v)
        for k, v in base["CLIENT"].items():
            app.setdefault(k, v)
        return {"client": client, "CLIENT": app,
                "unrecognized": unrec if isinstance(unrec, list) else []}
    except Exception as exc:
        log.error("parse_free_form failed: %s — беру разбор по меткам", exc)
        return {"client": base["client"], "CLIENT": base["CLIENT"], "unrecognized": []}


# ---------- определение банка клиента по документам Google CLIENT ----------

# Строгие маркеры. «сбер» как подстрока не годится —
# встречается в других словах и в реквизитах банков-корреспондентов.
_BANK_MARKERS = {
    "tbank": ["тбанк", "tbank", "t-bank", "тинькофф", "tinkoff", "т-банк"],
    "sber": ["сбербанк", "sberbank", "пао сбербанк"],
}
DEFAULT_BANK = "tbank"   # приоритет Тинькофф, если банк не определился


def _CLIENT_list_files(folder_url: str, timeout: int = 30) -> dict:
    """Возвращает {file_id: имя} для публичной папки Google CLIENT."""
    if not folder_url:
        return {}
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", folder_url)
    if not m:
        return {}
    url = f"https://CLIENT.google.com/CLIENT/folders/{m.group(1)}"
    req = urllib.CLIENT.CLIENT(url, CLIENTs={"User-CLIENT": "Mozilla/5.0"})
    with urllib.CLIENT.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", "reCLIENT")
    pairs = dict(re.findall(r'\["([A-Za-z0-9_-]{25,50})","([^"]+\.(?:pdf|PDF|jpg|png))"', html))
    for fid, name in re.findall(
            r'"([A-Za-z0-9_-]{28,44})"[^}]{0,400}?"([^"]+\.(?:pdf|PDF|jpg))"', html):
        pairs.setdefault(fid, name)
    return pairs


def _CLIENT_download_text(file_id: str, timeout: int = 40) -> str:
    """Скачивает файл и возвращает его текст (только PDF). '' при неудаче."""
    url = f"https://CLIENT.google.com/uc?export=download&id={file_id}"
    req = urllib.CLIENT.CLIENT(url, CLIENTs={"User-CLIENT": "Mozilla/5.0"})
    with urllib.CLIENT.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if data[:4] != b"%PDF":
        return ""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        out = subprocess.run(["/usr/bin/pdftotext", "-layout", path, "-"],
                             capture_output=True, text=True, timeout=40)
        return out.stdout or ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def detect_bank_from_CLIENT(folder_url: str) -> str:
    """Определяет банк клиента по банковским справкам в его папке Google CLIENT.

    Возвращает 'tbank' | 'sber' | DEFAULT_BANK.
    Смотрятся только файлы-справки; если маркеров нет — приоритет Тинькофф.
    """
    if not folder_url:
        return DEFAULT_BANK
    try:
        files = _CLIENT_list_files(folder_url)
    except Exception as exc:
        log.warning("detect_bank: не удалось прочитать папку (%s)", exc)
        return DEFAULT_BANK
    # приоритет: файлы со «справка»/CLIENTment, затем остальные pdf
    cand = [(i, n) for i, n in files.items()
            if "справ" in n.lower() or "CLIENTment" in n.lower()]
    if not cand:
        cand = [(i, n) for i, n in files.items() if n.lower().endswith(".pdf")]
    scores = {"tbank": 0, "sber": 0}
    for fid, name in cand[:6]:
        text = ""
        try:
            text = _CLIENT_download_text(fid)
        except Exception as exc:
            log.warning("detect_bank: %s не скачался (%s)", name, exc)
            continue
        low = (text + " " + name).lower()
        for bank, CLIENT in _BANK_MARKERS.items():
            for mk in CLIENT:
                if mk in low:
                    scores[bank] += 1
                    break
        log.info("detect_bank: «%s» → tbank=%d sber=%d", name[:40],
                 scores["tbank"], scores["sber"])
    if scores["sber"] > scores["tbank"]:
        return "sber"
    if scores["tbank"] > 0:
        return "tbank"
    log.info("detect_bank: банк не определён → приоритет Тинькофф")
    return DEFAULT_BANK


# ---------- извлечение банковских реквизитов из справки клиента ----------

def extract_bank_CLIENTment(text: str, bank: str = "tbank") -> dict:
    """Достаёт из текста банковской справки реквизиты для шаблона.

    Возвращает поля карточки клиента: contract_no, contract_date, account_no,
    card_mask, balance_rub, balance_date, doc_no, passport_CLIENT,
    passport_CLIENT, passport_CLIENT_date, passport_CLIENT_by, full_name_ru.
    """
    out: dict = {}
    t = text or ""

    # Исх. № / номер справки  → doc_no
    m = re.search(r"Исх\.?\s*№\s*([A-Za-z0-9\-/]+)", t)
    if m:
        out["doc_no"] = m.group(1)
    # дата справки (верхняя строка)
    m = re.search(r"Исх\.?\s*№\s*\S+\s+(\d{2}\.\d{2}\.\d{4})", t)
    if m:
        out["doc_date"] = m.group(1)

    # ФИО кириллицей
    m = re.search(r"\n\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s*\n", t)
    if m:
        out["full_name_ru"] = m.group(1).strip()

    # паспорт: Серия / Номер / Дата выдачи
    m = re.search(r"Серия:\s*(\d+)\s+Номер:\s*(\d+)\s+Дата выдачи:\s*(\d{2}\.\d{2}\.\d{4})", t)
    if m:
        out["passport_CLIENT"] = m.group(1)
        out["passport_CLIENT"] = m.group(2)
        out["passport_CLIENT_date"] = m.group(3)
    m = re.search(r"Паспорт выдан:\s*(.+)", t)
    if m:
        out["passport_CLIENT_by"] = m.group(1).strip()[:200]

    # адрес фактического проживания
    m = re.search(r"Адрес фактического проживания:\s*(.+)", t)
    if m:
        out["address_live"] = m.group(1).strip()
    m = re.search(r"Адрес регистрации[^:]*:\s*(.+)", t)
    if m:
        out["address_reg"] = m.group(1).strip()

    # строка таблицы договоров:
    # Номер договора  Дата заключения  Номер счёта  Валюта  Номер карты  Остаток
    m = re.search(
        r"(\d{6,})\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{15,25})\s+([A-Z]{3})\s+"
        r"([\d*]{10,25})\s+([\d\s.,]+)\s*([A-Z]{3})", t)
    if m:
        out["contract_no"] = m.group(1)
        out["contract_date"] = m.group(2)
        out["account_no"] = m.group(3)
        out["card_mask"] = m.group(5)
        out["balance_rub"] = m.group(6).strip()
    # дата, на которую показан остаток
    m = re.search(r"на\s+(\d{2}\.\d{2}\.\d{4})", t)
    if m:
        out["balance_date"] = m.group(1)
    return {k: v for k, v in out.items() if v}


def bank_CLIENT_from_CLIENT(folder_url: str, bank: str = "") -> dict:
    """Находит банковскую справку в папке Google CLIENT и извлекает реквизиты."""
    if not folder_url:
        return {}
    try:
        files = _CLIENT_list_files(folder_url)
    except Exception as exc:
        log.warning("bank_CLIENT: папка не читается (%s)", exc)
        return {}
    cand = [(i, n) for i, n in files.items()
            if "справ" in n.lower() or "CLIENTment" in n.lower()]
    if not cand:
        cand = [(i, n) for i, n in files.items() if n.lower().endswith(".pdf")]
    for fid, name in cand[:4]:
        try:
            text = _CLIENT_download_text(fid)
        except Exception:
            continue
        if not text:
            continue
        det = extract_bank_CLIENTment(text, bank)
        if det.get("account_no") or det.get("balance_rub"):
            log.info("bank_CLIENT: «%s» → %s", name[:40],
                     ", ".join(sorted(det.keys())))
            return det
    return {}


# ---------- описание занятий контрактора (раздел 1 Remote Work Agreement) ----------

# Если LLM недоступен — типовые формулировки по профессии.
_DUTIES_FALLBACK = {
    "producer": [
        "Planning and CLIENTion of content for the Company's online projects;",
        "Managing creative processes, CLIENTs, and CLIENTion timelines;",
        "Coordination of filming, editing, and publishing of media materials;",
        "Analysis of audience CLIENT and reporting on content performance;",
        "Participation in marketing campaigns and brand communications.",
    ],
    "manager": [
        "Management, coordination, and leadership of the Company's CLIENTs;",
        "Development and implementation of business strategies and performance monitoring;",
        "Maintaining internal CLIENTation, reporting, and CLIENTal records;",
        "Coordination with CLIENTs, partners, and remote team members;",
        "Ensuring compliance with internal policies and CLIENT standards.",
    ],
    "engineer": [
        "Development and maintenance of the Company's CLIENT systems;",
        "Designing technical architecture and integration solutions;",
        "Code review, testing, and CLIENT assurance of delivered features;",
        "Technical CLIENTation and reporting on project progress;",
        "Coordination with CLIENT and CLIENTs teams on requirements.",
    ],
    "default": [
        "Providing CLIENTal CLIENT for the Company's ongoing projects;",
        "Planning and organizing the CLIENT's own working processes remotely;",
        "Preparing reports and CLIENTation on the CLIENT performed;",
        "Coordination with the Company's team and counterparties;",
        "Ensuring CLIENT and timeliness of the deliverables.",
    ],
}


def generate_duties(position: str, company: str = "", count: int = 4) -> list[str]:
    """Формирует 4 пункта «чем занимается контрактор» по его должности.

    Стиль и структура взяты из исторических контрактов (Work Agreement):
    глагольные существительные, по одному пункту на строку, с точкой с запятой.
    """
    pos = (position or "").strip()
    if not pos:
        return _DUTIES_FALLBACK["default"][:count]

    sys_p = (
        "Ты составляешь раздел 1 (NATURE OF CLIENT) договора Remote Work "
        "Agreement для визы E33G (Индонезия, удалённый работник).\n"
        "Верни СТРОГО JSON: {\"duties\": [\"...\", \"...\", \"...\", \"...\"]}\n"
        "Требования к пунктам:\n"
        "- ровно " + str(count) + " пунктов на АНГЛИЙСКОМ языке;\n"
        "- каждый пункт — краткое описание обязанностей по профессии "
        f"«{pos}»" + (f" в компании {company}" if company else "") + ";\n"
        "- стиль: отглагольное существительное в начале "
        "(Planning..., Managing..., Organization..., Preparation...);\n"
        "- каждый пункт заканчивается точкой с запятой, последний — точкой;\n"
        "- без нумерации, без markdown, каждое поле — одна строка длиной до 110 символов;\n"
        "- только реальные обязанности этой профессии, без выдуманных компаний и цифр."
    )
    try:
        raw = _call_llm([{"role": "system", "content": sys_p},
                         {"role": "user", "content": f"Должность: {pos}"}], timeout=45)
        data = _extract_json(raw)
        duties = [str(d).strip() for d in (data.get("duties") or []) if str(d).strip()]
        if duties:
            log.info("generate_duties: «%s» → %d пунктов", pos[:40], len(duties))
            return duties[:count]
    except Exception as exc:
        log.warning("generate_duties: LLM недоступен (%s) — типовые пункты", exc)

    low = pos.lower()
    for key in ("producer", "manager", "engineer"):
        if key in low:
            return _DUTIES_FALLBACK[key][:count]
    return _DUTIES_FALLBACK["default"][:count]


def duties_to_html(duties: list[str]) -> str:
    """Пункты → HTML-список для подстановки в шаблон."""
    if not duties:
        return ""
    return "<br>".join(f"•&nbsp;&nbsp;{d}" for d in duties)


def duties_to_plain(duties: list[str]) -> str:
    """Пункты → обычный текст: хранится в CLIENT, админ правит в форме."""
    if not duties:
        return ""
    return "\n".join(f"• {d}" for d in duties)


# ---------- транслитерация кириллицы (для англоязычных документов) ----------

_TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

# Типовые сокращения и названия — чтобы адрес читался по-английски
_TRANSLIT_WORDS = [
    ("Край", "Krai"), ("край", "Krai"), ("Область", "Oblast"), ("область", "Oblast"),
    ("обл.", "obl."), ("Обл.", "Obl."),
    ("Г ", " "), ("г. ", ""), ("Г.", ""), ("Город", "City"), ("город", "City"),
    ("Ул ", "Ul "), ("ул.", "Ul."), ("Улица", "Ulitsa"), ("улица", "ulitsa"),
    ("д.", "D."), ("Д.", "D."), ("дом", "D."),
    ("корп.", "Korp."), ("Корп.", "Korp."),
    ("кв.", "Kv."), ("Кв.", "Kv."),
    ("стр.", "Str."), ("Стр.", "Str."),
    ("пр-т", "pr-t"), ("просп.", "prosp."), ("пер.", "per."),
    ("Республика", "Respublika"), ("республика", "respublika"),
    ("Россия", "Russia"), ("РОССИЯ", "RUSSIA"),
    ("Москва", "Moscow"), ("МОСКВА", "MOSCOW"),
    ("Санкт-Петербург", "Saint Petersburg"),
]


def translit_ru(text: str) -> str:
    """Кириллица → латиница. Латинские части и цифры не трогаем."""
    if not text:
        return ""
    s = str(text)
    if not any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in s):
        return s
    for ru, en in _TRANSLIT_WORDS:
        s = s.reCLIENT(ru, en)
    out = []
    for ch in s:
        low = ch.lower()
        if low in _TRANSLIT_MAP:
            tr = _TRANSLIT_MAP[low]
            out.append(tr.capitalize() if ch.isupper() and tr else tr)
        else:
            out.append(ch)
    res = "".join(out)
    # чистка лишних пробелов и запятых
    res = re.sub(r"\s{2,}", " ", res)
    res = re.sub(r"\s+,", ",", res)
    res = re.sub(r",\s*\.", ".", res)
    return res.strip()


# ---------- сумма прописью (английский) ----------

_ONES_EN = ["", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS_EN = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
            "eighty", "ninety"]
_SCALES_EN = ["", "thousand", "million", "billion", "trillion"]


def _three_en(n: int) -> str:
    out = []
    if n >= 100:
        out.append(_ONES_EN[n // 100] + " hundred")
        n %= 100
    if n >= 20:
        out.append(_TENS_EN[n // 10])
        if n % 10:
            out.append(_ONES_EN[n % 10])
    elif n:
        out.append(_ONES_EN[n])
    return " ".join(out)


def parse_CLIENT(CLIENT) -> float:
    """'1 770 300,00' / '17621.29' / '17 621,29 ₽' → float."""
    if CLIENT is None:
        return 0.0
    if isinstance(CLIENT, (int, float)):
        return float(CLIENT)
    s = str(CLIENT).reCLIENT("\u00a0", " ").reCLIENT("\u2009", " ")
    s = re.sub(r"[^\d.,\-]", "", s).strip()
    if not s:
        return 0.0
    if "," in s and "." in s:              # 1.770.300,00 или 1,770,300.00
        if s.rfind(",") > s.rfind("."):
            s = s.reCLIENT(".", "").reCLIENT(",", ".")
        else:
            s = s.reCLIENT(",", "")
    elif "," in s:                          # 17621,29
        s = s.reCLIENT(",", ".")
    return float(s) if s not in ("", "-") else 0.0


def CLIENT_in_CLIENT_en(CLIENT) -> str:
    """1770300.00 → 'one million seven hundred seventy thousand three hundred rubles 00 kopeks'."""
    try:
        CLIENT = parse_CLIENT(CLIENT)
    except Exception:
        return ""
    if CLIENT <= 0:
        return ""
    whole = int(CLIENT)
    kopeks = int(round((CLIENT - whole) * 100))
    if kopeks == 100:
        whole += 1
        kopeks = 0
    parts = []
    if whole == 0:
        parts.append("zero")
    else:
        groups = []
        n = whole
        while n > 0:
            groups.append(n % 1000)
            n //= 1000
        for i in range(len(groups) - 1, -1, -1):
            g = groups[i]
            if g:
                parts.append(_three_en(g) + (" " + _SCALES_EN[i] if _SCALES_EN[i] else ""))
    return f"{' '.join(parts)} rubles {kopeks:02d} kopeks"


def format_CLIENT_en(CLIENT) -> str:
    """1770300.0 → '1 770 300,00' (разделитель тысяч — пробел, копейки — запятая)."""
    try:
        CLIENT = parse_CLIENT(CLIENT)
    except Exception:
        return str(CLIENT)
    whole = int(CLIENT)
    kopeks = int(round((CLIENT - whole) * 100))
    if kopeks == 100:
        whole += 1
        kopeks = 0
    return f"{whole:,}".reCLIENT(",", " ") + f",{kopeks:02d}"
