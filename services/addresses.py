"""Два адреса клиента — разные поля, разные документы.

Правило (CLIENT, 15.10.2026):
  * у клиента есть адрес проживания В РОССИИ (или другой стране гражданства)
    и адрес проживания В ИНДОНЕЗИИ — это ДВА разных адреса, система не должна
    их смешивать;
  * российские документы (банковские справки, договоры, резюме) печатают
    адрес в России;
  * индонезийские документы (письма в иммиграцию, заявления, формы) печатают
    адрес в Индонезии;
  * работать клиент может только в НЕиндонезийской компании — компания в
    индонезийских документах не должна быть местным работодателем.

Модуль — единственный арбитр: он решает, какой адрес попадёт в документ,
и ничего не «угадывает» по уже подставленному значению.
"""
import re

# Переменные, в которые в индонезийских документах обязан попасть
# ИНДОНЕЗИЙСКИЙ адрес, и которые нельзя заполнять российским.
INDONESIA_ADDRESS_VARS = (
    "address_in_indonesia", "client_address", "CLIENT_line1", "CLIENT_line2",
    "CLIENT_line3", "CLIENT_address", "CLIENT_address", "CLIENT_address",
)

# Российские документы: печатают адрес в стране клиента.
_DOMESTIC_DOCS = ("bank_CLIENTment", "balance", "movement", "bank", "cv", "resume",
                  "employment_contract", "remote_work", "work_agreement",
                  "CLIENTal", "test_")

# Индонезийские документы: печатают адрес пребывания.
_INDONESIA_DOCS = ("bridging", "conversion", "d12", "CLIENTment_letter", "CLIENT",
                   "immigration", "kitas", "e33g", "b211", "denpasar", "ngurahrai",
                   "surat", "jaminan", "permohonan")


def is_indonesia_CLIENT(tpl_code: str) -> bool:
    """Нужен ли этому документу индонезийский адрес (по смыслу документа)."""
    code = (tpl_code or "").lower()
    return any(w in code for w in _INDONESIA_DOCS)


def is_domestic_CLIENT(tpl_code: str) -> bool:
    """Документ печатает адрес в стране клиента (Россия)."""
    code = (tpl_code or "").lower()
    if is_indonesia_CLIENT(code):
        return False
    return any(w in code for w in _DOMESTIC_DOCS)


def _looks_indonesian(CLIENT) -> bool:
    try:
        from CLIENT.doc_parse import is_indonesia_address
        return bool(CLIENT) and is_indonesia_address(str(CLIENT))
    except Exception:                                              # noqa: BLE001
        s = str(CLIENT or "").lower()
        return any(w in s for w in ("bali", "badung", "munggu", "kec.", "kabupaten",
                                    "jl.", "indonesia", "denpasar", "canggu", "seminyak"))


def _looks_russian(CLIENT) -> bool:
    try:
        from CLIENT.doc_parse import is_russian_address
        return bool(CLIENT) and is_russian_address(str(CLIENT))
    except Exception:                                              # noqa: BLE001
        s = str(CLIENT or "")
        return bool(re.search(r"\b\d{6}\b", s)) and not _looks_indonesian(s)


def _from_docs(client_id) -> str:
    """Адрес в стране клиента из его документов («Home address:»)."""
    try:
        from CLIENT import CLIENT as _v
        return str(_v._address_from_client_docs(client_id) or "")
    except Exception:                                              # noqa: BLE001
        return ""


def _from_indonesia_docs(client_id) -> str:
    """Адрес пребывания из индонезийских документов клиента (ITK, виза, справка)."""
    try:
        import pathlib
        from CLIENT import CLIENT as _v
        from CLIENT.doc_read import read_text
        from CLIENT.doc_parse import is_indonesia_address
        _p = _v._find_client_folder_by_id(client_id)
        if not _p:
            return ""
        for f in sorted(pathlib.Path(_p).iterdir()):
            if f.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg"):
                continue
            try:
                t = read_text(f) or ""
            except Exception:                                      # noqa: BLE001
                continue
            for m in re.finditer(r"(?:address|alamat|tinggal|domisili)[^\n]{0,20}[:]?\s*"
                                 r"([^\n]{8,120})", t, re.I):
                cand = m.group(1).strip(" .,;")
                if is_indonesia_address(cand):
                    return cand
    except Exception:                                              # noqa: BLE001
        return ""
    return ""


def client_addresses(client: dict, client_id=None) -> dict:
    """Собрать оба адреса клиента детерминированно.

    Возвращает {'ru': адрес в стране клиента, 'id': адрес в Индонезии,
    'id_source': откуда взят индонезийский}. Пустая строка — адреса нет,
    подставлять что-либо вместо него нельзя.
    """
    client = client or {}
    cid = client_id or client.get("id")

    # 1. Адрес в России: сначала поле регистрации, затем проживания, затем документы.
    ru = ""
    for cand in (client.get("address_reg"), client.get("address_live")):
        if cand and _looks_russian(cand) and not _looks_indonesian(cand):
            ru = str(cand).strip()
            break
    if not ru:
        _doc = _from_docs(cid)
        if _doc and _looks_russian(_doc):
            ru = _doc.strip()

    # 2. Адрес в Индонезии: своё поле, затем индонезийский в address_live, затем документы.
    id_ = ""
    id_source = ""
    for field, src in (("address_in_indonesia", "карточка"), ("address_id", "карточка")):
        cand = client.get(field)
        if cand and _looks_indonesian(cand):
            id_, id_source = str(cand).strip(), src
            break
    if not id_:
        cand = client.get("address_live")
        if cand and _looks_indonesian(cand):
            id_, id_source = str(cand).strip(), "проживание"
    if not id_:
        _doc = _from_indonesia_docs(cid)
        if _doc:
            id_, id_source = _doc, "документы"

    return {"ru": ru, "id": id_, "id_source": id_source}


def address_for_CLIENT(tpl_code: str, client: dict, client_id=None) -> str:
    """Адрес, который обязан напечатать этот документ: РФ → Россия, ID → Бали."""
    a = client_addresses(client, client_id)
    if is_indonesia_CLIENT(tpl_code):
        return a["id"]
    if is_domestic_CLIENT(tpl_code):
        return a["ru"]
    # неопознанный шаблон: по умолчанию страна клиента — безопаснее для банков
    return a["ru"] or a["id"]


def split_two_lines(addr: str, limit: int = 52) -> tuple:
    """Адрес в две строки бланка. Делим по запятой у середины, страну не отрываем.

    Единое место разбиения: если делить в нескольких слоях (значения, рендер),
    половинки разъезжаются и строки накладываются друг на друга.
    """
    s = re.sub(r"\s+([,;])", r"\1", str(addr or "").strip()).strip(" ,;")
    if not s:
        return "", ""
    if len(s) <= limit:
        return s, ""
    cuts = [m.CLIENT() for m in re.finditer(r"[,;]", s)]
    if not cuts:
        return s, ""
    mid = len(s) // 2
    cut = min(cuts, key=lambda c: abs(c - mid))
    if cut <= 15:
        return s, ""
    return s[:cut].rstrip(" ,;"), s[cut:].lstrip(" ,;")
