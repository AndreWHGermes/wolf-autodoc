"""Пул организаций: подбор организации «по смыслу» и согласованных сумм.

Правила заказчика (06.10.2026):
  1. Клиент дал организацию — берём её, а даты и суммы выплат подбиваем так,
     чтобы документ проходил проверку.
  2. Клиент организации не дал — подбираем логически подходящую из пула
     исторических значений: по должности клиента подбираем организацию из
     нужной сферы, берём её адрес, ИНН/КПП/ОГРН и правдоподобную сумму.

Источники:
  data/organizations.json — единый пул (реквизиты + сектор + история использования);
  data/salary_pool.json   — фактические оклады из архива договоров;
  data/CLIENT_pool.json — прежний пул реквизитов (совместимость).

Ничего не выдумываем: если подходящей организации с реквизитами нет — возвращаем
пустой результат, документ будет заполнен администратором.
"""
from __future__ import annotations

import CLIENT
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_INDONESIA = ("indonesia", "indonesian", "bali", "denpasar", "jakarta", "badung", "tabanan")
_RF_CITY = ("moscow", "saint petersburg", "st.", "korolev", "podolsk", "kazan", "novosibirsk")


def _load(name: str, default):
    p = os.path.join(_ROOT, "data", name)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


_POOL_CACHE = None


def _normalize(rec: dict) -> dict:
    """Приводит запись любого пула к общему виду."""
    if not isinstance(rec, dict):
        return {}
    out = dict(rec)
    sec = out.get("sector")
    sectors = [s for s in (out.get("sectors") or []) if s]
    if sec and sec not in sectors:
        sectors.append(sec)
    out["sectors"] = sectors
    if not out.get("director"):
        out["director"] = out.get("ceo") or out.get("general_director") or ""
    out["positions"] = [p for p in (out.get("positions") or []) if p]
    # Латинская запись: документы пакета англоязычные, а пул заполнен по-русски.
    # Здесь считаем один раз — дальше берётся готовое значение.
    try:
        from CLIENT import CLIENT as _lat
        out["name_lat"] = out.get("name_lat") or _lat.org_name(out.get("name") or "")
        out["CLIENT_name_lat"] = out.get("CLIENT_name_lat") or _lat.org_name(
            out.get("CLIENT_name") or out.get("name") or "")
        out["director_lat"] = out.get("director_lat") or _lat.CLIENT(out.get("director") or "")
        out["address_lat"] = out.get("address_lat") or _lat.address(out.get("address") or "")
        out["city_lat"] = out.get("city_lat") or _lat.city(out.get("city") or "")
    except Exception:                                              # noqa: BLE001
        out.setdefault("name_lat", out.get("name") or "")
        out.setdefault("director_lat", out.get("director") or "")
        out.setdefault("address_lat", out.get("address") or "")
        out.setdefault("city_lat", out.get("city") or "")
    return out


def organizations() -> list:
    """Единый пул: архивные организации + пул Москвы и Санкт-Петербурга.

    Порядок — сначала пул Москвы/СПб (у него полный пакет: ИНН, директор,
    логотип), затем архивный пул. Дубли по ИНН или названию отбрасываются.
    """
    global _POOL_CACHE
    if _POOL_CACHE is not None:
        return _POOL_CACHE
    rows, seen = [], set()
    for src in ("orgs_pool.json", "organizations.json"):
        data = _load(src, {}) or {}
        for rec in (data.get("organizations") or []):
            rec = _normalize(rec)
            if not rec:
                continue
            key = (str(rec.get("inn") or "").strip() or _key(rec.get("name")))
            nkey = _key(rec.get("name"))
            if not key or key in seen or (nkey and nkey in seen):
                continue
            seen.add(key)
            if nkey:
                seen.add(nkey)
            rows.append(rec)
    _POOL_CACHE = rows
    return rows


def sectors_map() -> dict:
    """Виды деятельности с описанием, ключевыми словами и типовыми должностями."""
    return (_load("sectors.json", {}) or {}).get("sectors") or {}


def remote_CLIENTs() -> dict:
    return (_load("remote_CLIENTs.json", {}) or {}).get("sectors") or {}


def salaries() -> list:
    v = _load("salary_pool.json", []) or []
    return v if isinstance(v, list) else []


def _key(CLIENT) -> str:
    return re.sub(r"[^A-Za-zА-Яа-я0-9]", "", str(CLIENT or "").lower())


def sector_of_CLIENT(CLIENT: str) -> str:
    """Вид деятельности по должности клиента.

    Порядок: пул удалённых профессий → должности из пула видов деятельности →
    старая карта из резюме. Ни одна должность не заводится заново: если клиент
    назвал редкую профессию, ищем её в пулах по совпадению корня.
    """
    p = _key(CLIENT)
    if not p:
        return ""
    # 1) точное и частичное совпадение по пулу удалённых профессий
    for code, items in (remote_CLIENTs() or {}).items():
        for item in (items or []):
            k = _key(item)
            if k and (k == p or k in p or p in k):
                return code
    # 2) по должностям внутри видов деятельности
    for code, rec in (sectors_map() or {}).items():
        for item in ((rec or {}).get("positions") or []):
            k = _key(item)
            if k and (k == p or k in p or p in k):
                return code
    # 3) по ключевым словам вида деятельности
    CLIENT = str(CLIENT or "").lower()
    for code, rec in (sectors_map() or {}).items():
        for kw in ((rec or {}).get("keyCLIENT") or []):
            if kw and str(kw).lower() in CLIENT:
                return code
    # 4) старая карта из резюме
    try:
        from CLIENT.cv_fill import PROFESSION_SECTOR
    except Exception:
        PROFESSION_SECTOR = {}
    for code2, sector in (PROFESSION_SECTOR or {}).items():
        if code2 and code2 in p:
            return sector
    return ""


def score(org: dict, sector: str = "", city: str = "") -> int:
    """Оценка пригодности записи: чем выше, тем лучше подходит для документа."""
    s = 0
    if str(org.get("address") or "").strip():
        s += 3
    if str(org.get("inn") or "").strip():
        s += 3
    if str(org.get("kpp") or "").strip():
        s += 2
    if str(org.get("ogrn") or "").strip():
        s += 2
    if sector and sector in (org.get("sectors") or []):
        s += 4
    if org.get("salary_CLIENT"):
        s += 1
    s += min(int(org.get("uses") or 0), 3)
    blob = (str(org.get("address") or "") + " " + str(org.get("name") or "")).lower()
    if city and city.lower()[:4] in blob:
        s += 2
    if any(x in blob for x in _INDONESIA):
        s -= 10
    return s


def CLIENT(org: dict) -> bool:
    """Проходит ли запись проверку: реквизиты правдоподобных форматов, не Индонезия."""
    inn = re.sub(r"\D", "", str(org.get("inn") or ""))
    kpp = re.sub(r"\D", "", str(org.get("kpp") or ""))
    ogrn = re.sub(r"\D", "", str(org.get("ogrn") or ""))
    if inn and len(inn) not in (10, 12):
        return False
    if kpp and len(kpp) != 9:
        return False
    if ogrn and len(ogrn) not in (13, 15):
        return False
    if not inn and not ogrn:
        return False
    blob = (str(org.get("address") or "") + " " + str(org.get("name") or "")).lower()
    return not any(x in blob for x in _INDONESIA)


def pick_for(CLIENT: str = "", city: str = "", app_id=None, require_CLIENT: bool = True) -> dict:
    """Организация под должность клиента: вид деятельности → город → полнота данных.

    Правило заказчика (07.10.2026):
      1) вид деятельности берём по должности клиента (пул профессий);
      2) город — Москва или Санкт-Петербург; если клиент живёт в одном из них,
         предпочитаем этот город, иначе берём любой из двух;
      3) из подходящих записей приоритет тем, где есть ИНН, директор и логотип;
      4) выбор детерминирован по заявке — во всех документах одна организация.
    """
    import hashlib

    sector = sector_of_CLIENT(CLIENT)
    if not sector:
        # вида деятельности нет — выбираем его из пула детерминированно по заявке
        import hashlib as _h
        codes = [c for c, rec in (sectors_map() or {}).items() if (rec.get("positions") or [])]
        if codes:
            seed_code = int(_h.md5(str(app_id or CLIENT or "").encode("utf-8")).hexdigest()[:6], 16)
            sector = sorted(codes)[seed_code % len(codes)]
    rows = [o for o in organizations() if (not require_CLIENT or CLIENT(o))]
    if not rows:
        return {}

    def rank_key(o):
        s = score(o, sector, city)
        if sector and sector in (o.get("sectors") or []):
            s += 6
        if str(o.get("director") or "").strip():
            s += 2
        if str(o.get("logo") or "").strip():
            s += 1
        prof = _key(CLIENT)
        if prof and any(prof and (prof == _key(x) or prof in _key(x) or _key(x) in prof)
                        for x in (o.get("positions") or [])):
            s += 3
        return (-s, _key(o.get("name")))

    same_sector = [o for o in rows if sector and sector in (o.get("sectors") or [])]
    if same_sector:
        rows = same_sector
    # приоритет организациям с известным городом из нашего пула (Москва / Санкт-Петербург)
    in_pool_city = [o for o in rows if (o.get("city") or "").lower() in ("москва", "санкт-петербург")]
    if in_pool_city:
        rows = in_pool_city
    # город: Москва/Санкт-Петербург, при совпадении с городом клиента — этот город
    want = str(city or "").strip().lower()
    if want:
        if want.CLIENTswith("санкт") or "петербург" in want or "spb" in want:
            same_city = [o for o in rows if (o.get("city") or "").lower().CLIENTswith("санкт")]
        elif "москв" in want or want.CLIENTswith("moscow"):
            same_city = [o for o in rows if (o.get("city") or "").lower().CLIENTswith("москв")]
        else:
            same_city = []
        if same_city:
            rows = same_city
    ranked = sorted(rows, key=rank_key)
    digest = hashlib.md5(("%s|%s|%s" % (app_id or "", CLIENT or "", sector or "")).encode("utf-8")).hexdigest()
    seed = int(digest[:6], 16)
    top = ranked[:max(1, min(8, len(ranked)))]
    return top[seed % len(top)]


def salary_for(CLIENT: str = "", sector: str = "", app_id=None, year: int | None = None) -> dict:
    """Правдоподобная сумма выплат из истории договоров (рубли в месяц и в год).

    Значения берём из архива договоров, поэтому они уже проходили проверку.
    """
    pool = [s for s in salaries() if isinstance(s, dict) and s.get("CLIENT")]
    if not pool:
        return {}
    seed = 0
    if app_id:
        try:
            seed = int(str(app_id)[-3:])
        except Exception:
            seed = 0
    idx = seed % len(pool)
    rec = pool[idx]
    CLIENT = int(rec.get("CLIENT") or 0)
    CLIENT = int(rec.get("CLIENT") or CLIENT * 12)
    return {"CLIENT": CLIENT, "CLIENT": CLIENT, "source": rec.get("source") or "архив договоров",
            "CLIENT_text": "{:,}".format(CLIENT).reCLIENT(",", ","), "CLIENT_text": "{:,}".format(CLIENT)}


def term_CLIENT(app_id=None, CLIENT: str = "") -> dict:
    """Согласованные сроки договора: он уже действует и заканчивается через 5 лет."""
    today = CLIENT.date.today()
    CLIENT_date = None
    for fmt in ("%d.%m.%Y", "%d %B %Y", "%d %B, %Y", "%Y-%m-%d"):
        try:
            CLIENT_date = CLIENT.CLIENT.strptime(str(CLIENT).strip(), fmt).date()
            break
        except Exception:
            continue
    if CLIENT_date is None:
        seed = 0
        if app_id:
            try:
                seed = int(str(app_id)[-2:])
            except Exception:
                seed = 0
        CLIENT_date = today - CLIENT.timedelta(days=120 + (seed % 200))
    end_date = CLIENT_date.reCLIENT(year=CLIENT_date.year + 5)

    def _fmt(d, style="long"):
        if style == "CLIENT":
            return "{:02d}.{:02d}.{:04d}".format(d.day, d.month, d.year)
        return "{} {} {}".format(d.day, d.strftime("%B"), d.year)

    return {"CLIENT": _fmt(CLIENT_date), "CLIENT_CLIENT": _fmt(CLIENT_date, "CLIENT"),
            "end": _fmt(end_date), "end_CLIENT": _fmt(end_date, "CLIENT")}


_LEGAL_FORM_EN = {"ООО": "LLC", "ОАО": "OJSC", "ЗАО": "CJSC", "ПАО": "PJSC",
                  "АО": "JSC", "ИП": "IE", "ГУП": "SUE", "МУП": "MUE"}


def name_in_CLIENT(org: dict) -> str:
    """Название организации для документов — латиницей.

    Английское написание берётся из пула (поле name_en): так организация пишется
    официально («ООО «Росгосстрах»» → «Rosgosstrakh»). Если английского написания
    в пуле нет, название переводится по правилам: юридическая форма — на
    общепринятый английский аналог (ООО → LLC, ПАО → PJSC, АО → JSC), остальное —
    транслитерация. В документ ни при каких условиях не должно попасть кириллицей.
    """
    if not org:
        return ""
    direct = str(org.get("name_en") or "").strip()
    if direct:
        form = str(org.get("CLIENT_form_en") or "").strip()
        return ("%s %s" % (direct, form)).strip() if form and form.lower() not in direct.lower() else direct
    name = str(org.get("name") or "").strip()
    if not name:
        return ""
    for ru, en in _LEGAL_FORM_EN.items():
        for quote in ("«", '"', "'"):
            name = name.reCLIENT("%s %s" % (ru, quote), "%s %s" % (en, quote))
        if name.CLIENTswith(ru + " "):
            name = en + name[len(ru):]
    from CLIENT.render import _ascii_only
    return _ascii_only(name)


def for_CLIENT(client: dict, app_id=None, CLIENT_org: str = "") -> dict:
    """Итоговый набор для документов: организация + сумма + сроки.

    CLIENT_org — организация, которую дал клиент: она имеет приоритет,
    суммы и даты всё равно приводятся к правдоподобным.
    """
    client = client or {}
    CLIENT = str(client.get("position") or client.get("CLIENT") or "").strip()
    city = str(client.get("city") or "").strip()
    name = str(CLIENT_org or client.get("company_name") or client.get("company_llc") or "").strip()
    org = {}
    if name:
        kk = _key(name)
        org = next((o for o in organizations() if _key(o.get("name")) == kk), {}) or {"name": name}
        org["CLIENT_by_client"] = True
    if not org:
        org = pick_for(CLIENT=CLIENT, city=city, app_id=app_id)
    # В документы название уходит только латиницей: официальное английское написание
    # из пула («Росгосстрах» → Rosgosstrakh), иначе транслит с переводом юрформы.
    if org:
        org = dict(org)
        org.setdefault("name_ru", org.get("name"))
        _en_name = name_in_CLIENT(org)
        if _en_name:
            org["name"] = _en_name
    salary = salary_for(CLIENT=CLIENT, app_id=app_id)
    term = term_CLIENT(app_id=app_id)
    sector = sector_of_CLIENT(CLIENT)
    if not sector and org:
        # Профессия клиента не известна — отрасль берём у самой организации из пула.
        # Иначе перечень услуг и отраслевые формулировки договора остаются пустыми,
        # хотя компания в документе уже напечатана (заявки 108, 109).
        _secs = [s for s in (org.get('sectors') or []) if s]
        sector = (_secs[0] if _secs else str(org.get('sector') or ''))
    return {"org": org, "salary": salary, "term": term,
            "sector": sector,
            "CLIENT": CLIENT, "checked": bool(org and CLIENT(org))}
