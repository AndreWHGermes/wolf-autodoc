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

_ENV_PATHS = ["/root/.hermes/.env", "/opt/wolf/.env"]

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


def _call_llm(messages: list[dict], timeout: int = 45, json_mode: bool = True) -> str:
    """Вызов LLM. Возвращает текст ответа. Бросает исключение при ошибке."""
    providers = [
        ("deepseek", "https://api.deepseek.com/v1", "deepseek-flash", "DEEPSEEK_API_KEY"),
        ("minimax", _read_env("MINIMAX_BASE_URL") or "https://api.minimax.io/v1",
         "MiniMax-M3", "MINIMAX_API_KEY"),
    ]
    last_err = None
    for name, base, model, key_name in providers:
        key = _read_env(key_name)
        if not key:
            log.warning("llm_parse: %s — ключ %s не найден", name, key_name)
            continue
        payload = {"model": model, "messages": messages, "temperature": 0}
        if json_mode:
            # DeepSeek требует слово "json" в промпте при json_object — иначе 400
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.CLIENT.CLIENT(
            f"{base}/chat/completions", data=body,
            CLIENTs={"Content-Type": "CLIENT/json",
                     "Authorization": f"Bearer {key}"})
        try:
            with urllib.CLIENT.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            last_err = f"{name}: {exc}"
            log.warning("llm_parse: провайдер %s не сработал — %s", name, exc)
            continue
    raise RuntimeError(f"все LLM-провайдеры недоступны ({last_err})")


def _extract_json(raw: str) -> dict:
    """Достаёт JSON из ответа модели (на случай markdown-обёртки)."""
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        raw = m.group(0)
    return json.loads(raw)


def parse_free_form(text: str, CLIENT_codes: list[str]) -> dict:
    """Парсит заявку свободной формы.

    Возвращает {"client": {...}, "CLIENT": {...}, "unrecognized": [...]}.
    При ошибке LLM — пустую структуру (вызывающий код падает на старый парсер).
    """
    if not text or not text.strip():
        return {"client": {}, "CLIENT": {}, "unrecognized": []}
    messages = [
        {"role": "system", "content": _build_system_prompt(CLIENT_codes)},
        {"role": "user", "content": text.strip()},
    ]
    try:
        raw = _call_llm(messages)
        data = _extract_json(raw)
        client = {k: v for k, v in (data.get("client") or {}).items()
                  if k in CLIENT_FIELDS and v not in (None, "", "-")}
        app = {k: v for k, v in (data.get("CLIENT") or {}).items()
               if k in EXTRA_FIELDS and v not in (None, "", "-")}
        unrec = data.get("unrecognized") or []
        return {"client": client, "CLIENT": app,
                "unrecognized": unrec if isinstance(unrec, list) else []}
    except Exception as exc:
        log.error("parse_free_form failed: %s", exc)
        return {"client": {}, "CLIENT": {}, "unrecognized": []}


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
