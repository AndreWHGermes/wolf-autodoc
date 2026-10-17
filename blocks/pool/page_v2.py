# -*- coding: utf-8 -*-
"""Блок «База значений»: три справочника, из которых берутся значения документов.

  * Профессии — удалённые профессии: слева английская версия, справа русская
    (название, обязанности, навыки). Отсюда берётся содержание резюме.
  * Организации — реальные компании: ИНН, адрес, ФИО генерального директора,
    город, краткое описание деятельности, логотип и печать.
  * Учебные заведения — вузы по городам и направлениям, из которых берётся
    образование в резюме.

Три уровня связаны: профессия → вуз (по городу и направлению) → организация.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, redirect, request, send_file, url_for

from blocks.shared.layout import render
from core.auth import login_required
from core.config import BASE_DIR

bp = Blueprint("pool", __name__)

DATA = Path(BASE_DIR) / "data"
ASSETS = DATA / "pool_assets"
DB = DATA / "wolf.db"

SECTOR_RU = {
    "ecommerce_retail": "Электронная коммерция и розница",
    "services_agency": "Услуги и агентства",
    "it_software": "ИТ и разработка ПО",
    "logistics": "Логистика",
    "construction": "Строительство",
    "manufacturing": "Производство",
    "finance": "Финансы",
    "education": "Образование",
    "healthcare": "Медицина",
    "media_education": "Медиа и образование",
    "logistics_trade": "Логистика и торговля",
    "bank_insurance": "Банки и страхование",
    "household_service": "Бытовые услуги",
    "construction_architecture": "Строительство и архитектура",
    "industry_production": "Производство и промышленность",
    "": "Прочие профессии",
    "other": "Прочие профессии",
}
SECTOR_DESC = {
    "ecommerce_retail": "розничная торговля и продажи через маркетплейсы и интернет-магазины",
    "services_agency": "услуги для бизнеса: консалтинг, администрирование, работа с клиентами",
    "it_software": "разработка и поддержка ПО и веб-сервисов",
    "logistics": "перевозки, складская логистика, таможенное оформление",
    "construction": "строительство, ремонт и проектирование",
    "manufacturing": "производство и промышленность",
    "finance": "финансовые и бухгалтерские услуги",
    "education": "образовательные услуги",
    "healthcare": "медицинские услуги",
}
SECTOR_DUTIES_RU = {
    "ecommerce_retail": ["ведение ежедневных продаж и ассортимента интернет-магазина",
                         "переговоры с поставщиками и контроль сроков поставки",
                         "анализ продаж и подготовка регулярных отчётов",
                         "согласование акций и маркетинговых кампаний",
                         "работа с обращениями клиентов и урегулирование претензий"],
    "services_agency": ["обработка запросов клиентов и подготовка коммерческих предложений",
                        "подготовка и контроль договоров и сопровождающих документов",
                        "ведение отчётности и внутреннего документооборота",
                        "координация работы подрядчиков и поставщиков",
                        "подготовка регулярных отчётов для руководства"],
    "it_software": ["разработка и поддержка веб-сервисов и внутренних инструментов",
                    "участие в анализе требований и техническом проектировании",
                    "тестирование, ревью и документирование кода",
                    "поддержка продуктивной среды и устранение инцидентов",
                    "взаимодействие с бизнес-подразделениями по новым функциям"],
    "logistics": ["планирование маршрутов и контроль сроков доставки",
                  "работа с перевозчиками, экспедиторами и таможенными брокерами",
                  "контроль складских операций и точности остатков",
                  "подготовка транспортных и таможенных документов",
                  "оптимизация транспортных расходов"],
    "construction": ["руководство строительно-монтажными работами на объекте",
                     "контроль соответствия проектной документации и нормативам",
                     "планирование графика, материалов и техники",
                     "координация субподрядчиков и поставщиков",
                     "подготовка исполнительной документации"],
    "manufacturing": ["организация производственного процесса на участке",
                      "контроль качества выпускаемой продукции",
                      "планирование загрузки оборудования и персонала",
                      "работа с поставщиками сырья и комплектующих",
                      "ведение производственной отчётности"],
    "finance": ["ведение бухгалтерского и налогового учёта",
                "подготовка финансовой и управленческой отчётности",
                "планирование бюджета и контроль расходов",
                "работа с банками и контрагентами",
                "прохождение проверок и подготовка документов"],
    "education": ["разработка учебных программ и материалов",
                  "проведение занятий и оценка результатов",
                  "методическая работа и повышение квалификации",
                  "взаимодействие с учащимися и их родителями",
                  "ведение учебной документации"],
    "healthcare": {"duties": ["приём пациентов и ведение медицинской документации",
                              "назначение и контроль обследований и лечения",
                              "соблюдение санитарных норм и стандартов",
                              "взаимодействие с коллегами и профильными отделениями",
                              "повышение квалификации и освоение новых методик"],
                   "skills": "клиническая практика, документация, стандарты"},
    "media_education": {"duties": ["подготовка и размещение материалов в медиа и соцсетях",
                                   "работа с аудиторией и обратная связь",
                                   "организация учебных и медийных проектов",
                                   "анализ охватов и подготовка отчётов",
                                   "взаимодействие с партнёрами и подрядчиками"],
                        "skills": "контент, соцсети, аналитика, коммуникация"},
    "logistics_trade": {"duties": ["планирование поставок и контроль сроков",
                                   "работа с поставщиками и перевозчиками",
                                   "подготовка товаросопроводительных документов",
                                   "контроль складских остатков",
                                   "отчётность по поставкам и расходам"],
                        "skills": "поставки, документы, склад, Excel"},
    "bank_insurance": {"duties": ["работа с клиентами по продуктам банка или страховой компании",
                                  "подготовка и проверка документов",
                                  "сопровождение договоров и заявок",
                                  "консультирование по условиям продуктов",
                                  "ведение отчётности по портфелю"],
                       "skills": "продажи, документы, CRM, отчётность"},
    "household_service": {"duties": ["приём и обработка заявок клиентов",
                                     "организация и контроль выполнения работ",
                                     "работа с подрядчиками и персоналом",
                                     "контроль качества услуг",
                                     "расчёты с клиентами и отчётность"],
                          "skills": "клиентский сервис, координация, контроль качества"},
}
SECTOR_SKILLS_RU = {
    "ecommerce_retail": "продажи, маркетплейсы, переговоры, отчётность, Excel",
    "services_agency": "работа с клиентами, договоры, отчётность, CRM, MS Office",
    "it_software": "Python, SQL, REST API, Git, Linux, тестирование",
    "logistics": "экспедирование, таможенные документы, склад, маршруты",
    "construction": "стройконтроль, проектная документация, AutoCAD, сметы",
    "manufacturing": "организация производства, контроль качества, планирование",
    "finance": "бухгалтерский учёт, налоги, отчётность, 1С, Excel",
    "education": "методика преподавания, программы, оценка знаний",
    "healthcare": "клиническая практика, документация, стандарты",
}

# Часть отраслей описана парами {"duties": [...], "skills": "..."} — приводим к двум словарям
for _k, _v in list(SECTOR_DUTIES_RU.items()):
    if isinstance(_v, dict):
        SECTOR_DUTIES_RU[_k] = _v.get("duties") or []
        SECTOR_SKILLS_RU[_k] = _v.get("skills") or SECTOR_SKILLS_RU.get(_k, "")
MAJOR_RU = {"technical": "технические", "medical": "медицинские", "economics": "экономические",
            "humanities": "гуманитарные", "general": "общие", "it": "ИТ"}


def _majors(text: str) -> str:
    parts = [MAJOR_RU.get(x.strip(), x.strip()) for x in str(text or "").split(",")
             if x.strip() and not x.strip().startswith("_")]
    return " · ".join(parts)


UNI_RU = {
    "Lomonosov Moscow State University": "МГУ имени М. В. Ломоносова",
    "Higher School of Economics": "Высшая школа экономики",
    "MGIMO University": "МГИМО",
    "Bauman Moscow State Technical University": "МГТУ имени Н. Э. Баумана",
    "Plekhanov Russian University of Economics": "РЭУ имени Г. В. Плеханова",
    "Financial University under the Government of the Russian Federation": "Финансовый университет при Правительстве РФ",
    "RUDN University": "РУДН",
    "Moscow Aviation Institute": "Московский авиационный институт",
    "Sechenov First Moscow State Medical University": "Первый МГМУ имени И. М. Сеченова",
    "Saint Petersburg State University": "Санкт-Петербургский государственный университет",
    "Peter the Great St. Petersburg Polytechnic University": "Политехнический университет Петра Великого",
    "ITMO University": "ИТМО",
    "HSE University Saint Petersburg": "НИУ ВШЭ — Санкт-Петербург",
    "Saint Petersburg State University of Economics": "СПбГЭУ",
    "Herzen State Pedagogical University": "РГПУ имени А. И. Герцена",
    "Bonch-Bruevich Saint Petersburg State University of Telecommunications": "СПбГУТ имени Бонч-Бруевича",
    "Kazan Federal University": "Казанский федеральный университет",
    "Kazan National Research Technical University": "КНИТУ-КАИ",
    "Kazan National Research Technological University": "КНИТУ",
    "Kazan State Medical University": "Казанский ГМУ",
    "Kazan Innovative University": "Казанский инновационный университет",
    "Novosibirsk State University": "Новосибирский государственный университет",
    "Novosibirsk State Technical University": "НГТУ",
    "Siberian State University of Telecommunications and Information Sciences": "СибГУТИ",
    "Novosibirsk State University of Economics and Management": "НГУЭУ",
    "Ural Federal University": "Уральский федеральный университет",
    "Ural State University of Economics": "Уральский государственный экономический университет",
    "Ural State Mining University": "Уральский государственный горный университет",
    "Ural State Pedagogical University": "Уральский государственный педагогический университет",
    "Lobachevsky State University of Nizhny Novgorod": "ННГУ имени Н. И. Лобачевского",
    "Nizhny Novgorod State Technical University": "НГТУ имени Р. Е. Алексеева",
    "HSE University Nizhny Novgorod": "НИУ ВШЭ — Нижний Новгород",
    "Nizhny Novgorod State University of Architecture and Civil Engineering": "ННГАСУ",
    "Samara National Research University": "Самарский национальный исследовательский университет",
    "Samara State Technical University": "Самарский государственный технический университет",
    "Samara State University of Economics": "Самарский государственный экономический университет",
    "Southern Federal University": "Южный федеральный университет",
    "Don State Technical University": "Донской государственный технический университет",
    "Rostov State University of Economics": "Ростовский государственный экономический университет",
    "Rostov State Medical University": "Ростовский государственный медицинский университет",
    "Voronezh State University": "Воронежский государственный университет",
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pool_organizations(
            id INTEGER PRIMARY KEY, inn TEXT UNIQUE, kpp TEXT, ogrn TEXT,
            name TEXT, name_en TEXT, legal_form_en TEXT, city TEXT, address TEXT,
            director TEXT, sector TEXT, domain TEXT, description TEXT,
            logo_path TEXT, seal_path TEXT, source TEXT, updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS pool_professions(
            id INTEGER PRIMARY KEY, code TEXT UNIQUE, title_ru TEXT, title_en TEXT,
            sector TEXT, duties TEXT, duties_ru TEXT, skills TEXT, skills_ru TEXT,
            description TEXT, keys TEXT, remote INTEGER DEFAULT 1, source TEXT, updated_at TEXT)""")
        cols = {r[1] for r in c.execute("PRAGMA table_info(pool_professions)")}
        for col in ("duties_ru", "skills_ru"):
            if col not in cols:
                c.execute(f"ALTER TABLE pool_professions ADD COLUMN {col} TEXT")
        c.execute("""CREATE TABLE IF NOT EXISTS pool_universities(
            id INTEGER PRIMARY KEY, name_en TEXT UNIQUE, name_ru TEXT, city_ru TEXT,
            city_en TEXT, majors TEXT, site TEXT, logo_path TEXT, source TEXT, updated_at TEXT)""")


def _load(name: str, default):
    p = DATA / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _city_of(address: str) -> str:
    a = str(address or "").lower()
    if "москв" in a:
        return "Москва"
    if "санкт-петербург" in a or "петербург" in a:
        return "Санкт-Петербург"
    return ""


def import_pools() -> dict:
    ensure_schema()
    now = datetime.now().isoformat(timespec="seconds")
    orgs = profs = unis = 0
    with _db() as c:
        pool = _load("orgs_pool.json", {}) or {}
        items = pool.get("organizations") or []
        extra = (_load("organizations.json", {}) or {}).get("organizations") or []
        for o in list(items) + list(extra):
            inn = str(o.get("inn") or "").strip()
            if not inn:
                continue
            c.execute("""INSERT INTO pool_organizations
                (inn,kpp,ogrn,name,name_en,legal_form_en,city,address,director,sector,domain,
                 description,source,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(inn) DO UPDATE SET
                  name=COALESCE(NULLIF(excluded.name,''), pool_organizations.name),
                  name_en=COALESCE(NULLIF(excluded.name_en,''), pool_organizations.name_en),
                  legal_form_en=COALESCE(NULLIF(excluded.legal_form_en,''), pool_organizations.legal_form_en),
                  city=COALESCE(NULLIF(excluded.city,''), pool_organizations.city),
                  address=COALESCE(NULLIF(excluded.address,''), pool_organizations.address),
                  director=COALESCE(NULLIF(excluded.director,''), pool_organizations.director),
                  sector=COALESCE(NULLIF(excluded.sector,''), pool_organizations.sector),
                  domain=COALESCE(NULLIF(excluded.domain,''), pool_organizations.domain),
                  updated_at=excluded.updated_at""",
                      (inn, o.get("kpp") or "", o.get("ogrn") or "", o.get("name") or "",
                       o.get("name_en") or "", o.get("legal_form_en") or "",
                       o.get("city") or _city_of(o.get("address")), o.get("address") or "",
                       o.get("director") or "", o.get("sector") or "", o.get("domain") or "",
                       "", o.get("logo") or "orgs_pool", now))
            orgs += 1
            logo = str(o.get("logo") or "").strip()
            if logo:
                c.execute("UPDATE pool_organizations SET logo_path=? WHERE inn=? AND "
                          "(logo_path IS NULL OR logo_path='')", (logo, inn))

        pos = (_load("cv_positions.json", {}) or {}).get("positions") or []
        for p in pos:
            blocks = p.get("blocks") or {}
            duties = blocks.get("long") or blocks.get("medium") or blocks.get("short") or ""
            sector = p.get("sector") or ""
            if not sector:
                try:
                    from services import org_pool
                    sector = org_pool.sector_of_profession(p.get("en") or p.get("ru") or "")
                except Exception:
                    sector = ""
            duties_ru = "\n".join(SECTOR_DUTIES_RU.get(sector) or SECTOR_DUTIES_RU["services_agency"])
            skills = ", ".join(p.get("skills") or []) if isinstance(p.get("skills"), list) else (p.get("skills") or "")
            c.execute("""INSERT INTO pool_professions
                (code,title_ru,title_en,sector,duties,duties_ru,skills,skills_ru,description,keys,remote,source,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET
                  title_ru=excluded.title_ru, title_en=excluded.title_en, sector=excluded.sector,
                  duties=excluded.duties, duties_ru=excluded.duties_ru, skills=excluded.skills,
                  skills_ru=excluded.skills_ru, updated_at=excluded.updated_at""",
                      (p.get("code") or re.sub(r"\W+", "_", str(p.get("en") or "")).lower(),
                       p.get("ru") or "", p.get("en") or "", sector, duties, duties_ru,
                       skills, SECTOR_SKILLS_RU.get(sector) or SECTOR_SKILLS_RU["services_agency"],
                       (blocks.get("medium") or "").strip(), ", ".join(p.get("keys") or []),
                       1, "cv_positions", now))
            profs += 1

        remote = (_load("remote_professions.json", {}) or {}).get("sectors") or {}
        for sector, titles in remote.items():
            duties_ru = "\n".join(SECTOR_DUTIES_RU.get(sector) or SECTOR_DUTIES_RU["services_agency"])
            for t in titles or []:
                code = re.sub(r"\W+", "_", str(t)).strip("_").lower()[:60]
                if not code:
                    continue
                c.execute("""INSERT INTO pool_professions
                    (code,title_ru,title_en,sector,duties,duties_ru,skills,skills_ru,description,keys,remote,source,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(code) DO UPDATE SET
                      sector=COALESCE(NULLIF(excluded.sector,''), pool_professions.sector),
                      duties=CASE WHEN COALESCE(pool_professions.duties,'')='' THEN excluded.duties ELSE pool_professions.duties END,
                      duties_ru=CASE WHEN COALESCE(pool_professions.duties_ru,'')='' THEN excluded.duties_ru ELSE pool_professions.duties_ru END,
                      skills=CASE WHEN COALESCE(pool_professions.skills,'')='' THEN excluded.skills ELSE pool_professions.skills END,
                      skills_ru=CASE WHEN COALESCE(pool_professions.skills_ru,'')='' THEN excluded.skills_ru ELSE pool_professions.skills_ru END""",
                          (code, str(t), str(t), sector, "", duties_ru, "", SECTOR_SKILLS_RU.get(sector, ""),
                           "", "", 1, "remote_professions", now))
                profs += 1

        uni = _load("cv_universities.json", {}) or {}
        for city_key, city in (uni.get("cities") or {}).items():
            for name in city.get("universities") or []:
                c.execute("""INSERT INTO pool_universities
                    (name_en,name_ru,city_ru,city_en,majors,source,updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(name_en) DO UPDATE SET
                      name_ru=COALESCE(NULLIF(excluded.name_ru,''), pool_universities.name_ru),
                      city_ru=excluded.city_ru, city_en=excluded.city_en,
                      majors=excluded.majors, updated_at=excluded.updated_at""",
                          (name, UNI_RU.get(name, ""), city.get("ru") or "", city.get("en") or "",
                           ", ".join(__import__("services.pool_uni", fromlist=["majors_of"]).majors_of(name)),
                           "cv_universities", now))
                unis += 1
    return {"organizations": orgs, "professions": profs, "universities": unis}


def _orgs(city: str = "", q: str = "") -> list[dict]:
    sql = "SELECT * FROM pool_organizations WHERE 1=1"
    args: list = []
    if city:
        sql += " AND city=?"
        args.append(city)
    if q:
        sql += " AND (name LIKE ? OR name_en LIKE ? OR inn LIKE ? OR director LIKE ? OR address LIKE ?)"
        args += ["%%%s%%" % q] * 5
    sql += " ORDER BY name"
    with _db() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _profs(q: str = "") -> list[dict]:
    sql = "SELECT * FROM pool_professions WHERE remote=1"
    args: list = []
    if q:
        sql += " AND (title_ru LIKE ? OR title_en LIKE ? OR duties LIKE ? OR duties_ru LIKE ?)"
        args += ["%%%s%%" % q] * 4
    sql += " ORDER BY title_en"
    with _db() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _unis(city: str = "", q: str = "") -> list[dict]:
    sql = "SELECT * FROM pool_universities WHERE 1=1"
    args: list = []
    if city:
        sql += " AND city_ru=?"
        args.append(city)
    if q:
        sql += " AND (name_en LIKE ? OR name_ru LIKE ?)"
        args += ["%%%s%%" % q] * 2
    sql += " ORDER BY city_ru, name_en"
    with _db() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _cities() -> list[str]:
    with _db() as c:
        rows = [r[0] for r in c.execute("SELECT DISTINCT city FROM pool_organizations WHERE city<>''")]
    return sorted(rows, key=lambda x: (x != "Москва", x != "Санкт-Петербург", x))


def _asset(oid: int, kind: str, path: str | None) -> str:
    if not path:
        return ""
    if str(path).startswith(("http://", "https://")):
        return str(path)
    return url_for("pool.asset", oid=oid, kind=kind)


PF_CSS = """
<style>
.pf-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 14px}
.pf-bar input,.pf-bar select{padding:9px 12px;border:1px solid #DCE7EE;border-radius:10px;background:#fff;font-family:inherit;font-size:14px}
.pf-bar input{flex:1 1 200px;min-width:150px}.pf-bar .btn{margin-left:auto}
.pf-fold{border:1px solid #DCE7EE;border-radius:16px;background:#fff;margin:0 0 14px;overflow:hidden;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.pf-fold>summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:14px 16px;cursor:pointer;list-style:none;border-left:5px solid var(--acc,#1F6BFF)}
.pf-fold>summary::-webkit-details-marker{display:none}
.pf-fold[open]>summary{background:var(--acc-tint,#F1F6FF);border-bottom:1px solid #E4EAF3}
.pf-ico{width:30px;height:30px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;font-size:16px;background:#fff;border:1px solid var(--acc,#1F6BFF);flex:none}
.pf-title{font-size:17px;font-weight:800;letter-spacing:-.01em}
.pf-note{flex:1 1 260px;color:#5B6472;font-size:12.5px;line-height:1.35}
.pf-count{font-size:12px;font-weight:800;padding:3px 10px;border-radius:999px;background:#fff;border:1px solid var(--acc,#1F6BFF);color:var(--acc,#1F6BFF)}
.pf-fold>summary .chev{color:var(--acc,#1F6BFF);font-size:20px;line-height:1;transition:transform .18s}
.pf-fold[open]>summary .chev{transform:rotate(90deg)}
.pf-body{padding:12px 14px 6px;background:#FBFCFF}
.pf-grp{border:1px solid #E1E8F2;border-radius:12px;background:#fff;margin:0 0 8px;overflow:hidden}
.pf-grp>summary{display:flex;align-items:center;gap:8px;padding:10px 12px;cursor:pointer;list-style:none;font-size:14px;font-weight:700;color:#1F2937}
.pf-grp>summary::-webkit-details-marker{display:none}
.pf-grp[open]{border-color:var(--acc,#1F6BFF);box-shadow:0 2px 10px rgba(16,24,40,.08)}
.pf-grp[open]>summary{background:var(--acc-tint,#EFF5FF);border-bottom:1px solid #DCE7F7;color:var(--acc,#1D4ED8)}
.pf-grp>summary .chev{margin-left:auto;color:#8A94A6;font-size:16px;transition:transform .18s}
.pf-grp[open]>summary .chev{transform:rotate(90deg);color:var(--acc,#1D4ED8)}
.pf-grp .cnt{font-size:11px;font-weight:800;color:#4B5563;background:#EEF1F6;border-radius:999px;padding:2px 8px}
.pf-rows{padding:2px 4px 4px}
.pf-row{border:1px solid transparent;border-top:1px solid #EEF1F6;padding:8px 8px;border-radius:9px}
.pf-row:first-child{border-top:none}
.pf-row>summary{display:flex;gap:8px;align-items:baseline;cursor:pointer;list-style:none;flex-wrap:wrap}
.pf-row>summary::-webkit-details-marker{display:none}
.pf-en{font-weight:700;font-size:14px}
.pf-ru{color:#4B5563;font-size:13px}
.pf-row[open]{border-color:var(--acc,#B9D2FF);background:#F8FBFF}
.pf-cols{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-top:8px;border:1px solid #E1E8F2;border-radius:10px;overflow:hidden;background:#fff}
.pf-col{padding:10px 12px}
.pf-col+.pf-col{border-left:1px solid #E1E8F2;background:#FAFCFF}
.pf-col h4{margin:0 0 6px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#6B7280}
.pf-col p{margin:0 0 5px;font-size:13.5px;line-height:1.45}
.pf-skills{margin-top:7px;padding-top:6px;border-top:1px dashed #E1E8F2;font-size:12.5px;color:#374151}
.pf-org{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.pf-logo{width:40px;height:40px;object-fit:contain;border:1px solid #E1E8F2;border-radius:9px;background:#fff;flex:none}
.pf-meta{color:#6B7280;font-size:12.5px}
.pf-kv{margin:6px 0 0;font-size:13.5px;line-height:1.55}
.pf-kv b{color:#111827}
.pf-uni{margin:0 0 6px;padding:8px 10px;border:1px solid #EEF1F6;border-left:3px solid #7C3AED;border-radius:8px;background:#fff}
.pf-uni b{font-size:13.5px}
.pf-uni .en{color:#6B7280;font-size:12.5px}
.pf-uni .tags{color:#6B7280;font-size:11.5px}
.pf-up{margin-top:5px}
.pf-up>summary{display:flex;align-items:center;gap:6px;cursor:pointer;list-style:none;font-size:12px;font-weight:700;color:#5B21B6}
.pf-up>summary::-webkit-details-marker{display:none}
.pf-up>summary .cnt{font-size:10.5px;font-weight:800;color:#5B21B6;background:#F1E9FF;border-radius:999px;padding:1px 7px}
.pf-up>summary .chev{margin-left:auto;transition:transform .18s;font-size:14px;color:#7C3AED}
.pf-up[open]>summary .chev{transform:rotate(90deg)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin:5px 0 0}
.chip{font-size:11.5px;padding:2px 7px;border-radius:999px;background:#F6F2FF;color:#4C1D95;border:1px solid #E4D8FF}
@media(max-width:620px){.pf-cols{grid-template-columns:1fr}.pf-col+.pf-col{border-left:none;border-top:1px solid #E1E8F2}.pf-note{flex-basis:100%}}
</style>
"""

TAB_STYLE = {
    "professions": ("💼", "#1F6BFF", "#EFF5FF",
                    "Удалённые профессии: слева английская версия, справа русская. Отсюда берётся содержание резюме."),
    "organizations": ("🏢", "#0E9F6E", "#ECFAF3",
                      "Реальные компании: реквизиты, генеральный директор, деятельность, логотип и печать."),
    "universities": ("🎓", "#7C3AED", "#F4EEFF",
                     "Вузы по городам и направлениям — отсюда берётся образование в резюме."),
}


def _big_tab(key: str, count: int, active: str, body: str) -> str:
    icon, acc, tint, note = TAB_STYLE[key]
    titles = {"professions": "Профессии и обязанности", "organizations": "Организации",
              "universities": "Учебные заведения"}
    opened = " open" if key == active else ""
    return (f'<details class="pf-fold"{opened} style="--acc:{acc};--acc-tint:{tint}">'
            f'<summary><span class="pf-ico">{icon}</span>'
            f'<span class="pf-title">{titles[key]}</span>'
            f'<span class="pf-note">{note}</span>'
            f'<span class="pf-count">{count}</span><span class="chev">›</span></summary>'
            f'<div class="pf-body">{body}</div></details>')


def _group(title: str, rows_html: str, count: int) -> str:
    return (f'<details class="pf-grp"><summary>{title}<span class="cnt">{count}</span>'
            f'<span class="chev">›</span></summary><div class="pf-rows">{rows_html}</div></details>')


def _prof_rows(rows: list[dict]) -> str:
    by_sector: dict[str, list[dict]] = {}
    for p in rows:
        by_sector.setdefault(p.get("sector") or "other", []).append(p)
    out = []
    for sector, items in sorted(by_sector.items(), key=lambda kv: -len(kv[1])):
        inner = []
        for p in items:
            def paras(text: str) -> str:
                return "".join(f"<p>{line}</p>" for line in (text or "").split("\n") if line.strip()) or "<p>—</p>"
            skills_en = f'<div class="pf-skills"><b>Skills:</b> {p["skills"]}</div>' if p.get("skills") else ""
            skills_ru = f'<div class="pf-skills"><b>Навыки:</b> {p["skills_ru"]}</div>' if p.get("skills_ru") else ""
            inner.append(
                f'<details class="pf-row"><summary>'
                f'<span class="pf-en">{p.get("title_en")}</span>'
                f'<span class="pf-ru">· {p.get("title_ru") or ""}</span></summary>'
                f'<div class="pf-cols">'
                f'<div class="pf-col"><h4>English</h4>{paras(p.get("duties") or "")}{skills_en}</div>'
                f'<div class="pf-col"><h4>Русский</h4>{paras(p.get("duties_ru") or "")}{skills_ru}</div>'
                f'</div></details>')
        out.append(_group(SECTOR_RU.get(sector, sector), "".join(inner), len(items)))
    return "".join(out)


def _org_rows(rows: list[dict]) -> str:
    by_city: dict[str, list[dict]] = {}
    for o in rows:
        by_city.setdefault(o.get("city") or "Другие города", []).append(o)
    out = []
    for city, items in sorted(by_city.items(), key=lambda kv: (kv[0] != "Москва", kv[0] != "Санкт-Петербург", kv[0])):
        inner = []
        for o in items:
            logo = _asset(o["id"], "logo", o.get("logo_path"))
            seal = _asset(o["id"], "seal", o.get("seal_path"))
            logo_html = f'<img class="pf-logo" src="{logo}" alt="">' if logo else ""
            desc = SECTOR_DESC.get(o.get("sector") or "", o.get("description") or "")
            inner.append(
                f'<details class="pf-row"><summary><span class="pf-org">{logo_html}'
                f'<span><b>{o.get("name")}</b><br><span class="pf-meta">ИНН {o.get("inn")}'
                f'{(" · " + o["director"]) if o.get("director") else ""}</span></span></span></summary>'
                f'<div class="pf-kv">'
                f'<p><b>Официальное название:</b> {o.get("name_en") or o.get("name")}</p>'
                f'<p><b>ИНН / КПП:</b> {o.get("inn")} / {o.get("kpp") or "—"} · <b>ОГРН:</b> {o.get("ogrn") or "—"}</p>'
                f'<p><b>Адрес:</b> {o.get("address") or "—"}</p>'
                f'<p><b>Генеральный директор:</b> {o.get("director") or "—"}</p>'
                f'<p><b>Деятельность:</b> {desc or "—"}</p>'
                + (f'<p><img src="{seal}" alt="seal" style="width:64px;height:64px;object-fit:contain"></p>' if seal else "")
                + f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">'
                  f'<form method="post" enctype="multipart/form-data" action="{url_for("pool.upload", oid=o["id"], kind="logo")}" style="display:flex;gap:6px">'
                  f'<input type="file" name="file" accept="image/*" required><button class="btn sm" type="submit">Логотип</button></form>'
                  f'<form method="post" enctype="multipart/form-data" action="{url_for("pool.upload", oid=o["id"], kind="seal")}" style="display:flex;gap:6px">'
                  f'<input type="file" name="file" accept="image/*" required><button class="btn sm ghost" type="submit">Печать</button></form>'
                  f'</div></div></details>')
        out.append(_group(city, "".join(inner), len(items)))
    return "".join(out)


def _uni_rows(rows: list[dict]) -> str:
    from services import pool_uni
    all_profs = pool_uni.all_titles()
    by_city: dict[str, list[dict]] = {}
    for u in rows:
        by_city.setdefault(u.get("city_ru") or "Другие города", []).append(u)
    out = []
    for city, items in sorted(by_city.items(), key=lambda kv: (kv[0] != "Москва", kv[0] != "Санкт-Петербург", kv[0])):
        inner = []
        for u in items:
            titles = all_profs.get(u["id"], [])
            prof_html = ""
            if titles:
                first = " · ".join(titles[:6])
                rest = "".join(f"<span class='chip'>{t}</span>" for t in titles)
                prof_html = (
                    f'<details class="pf-up"><summary>Профессии этого вуза '
                    f'<span class="cnt">{len(titles)}</span><span class="chev">›</span></summary>'
                    f'<div class="chips">{rest}</div></details>'
                    f'<div class="tags" style="margin-top:4px">например: {first}</div>')
            inner.append(
                f'<div class="pf-uni"><b>{u.get("name_ru") or u.get("name_en")}</b>'
                f'<div class="en">{u.get("name_en")}</div>'
                f'<div class="tags">город: {u.get("city_ru")} · направления: {_majors(u.get("majors")) or "—"}</div>'
                f'{prof_html}</div>')
        out.append(_group(city, "".join(inner), len(items)))
    return "".join(out)


@bp.route("/pool")
@login_required
def pool_page():  # noqa: ANN201
    ensure_schema()
    tab = request.args.get("tab") or "professions"
    open_tab = request.args.get("open") or ""
    city = request.args.get("city") or ""
    q = (request.args.get("q") or "").strip()
    with _db() as c:
        n_org = c.execute("SELECT COUNT(*) FROM pool_organizations").fetchone()[0]
        n_prof = c.execute("SELECT COUNT(*) FROM pool_professions").fetchone()[0]
        n_uni = c.execute("SELECT COUNT(*) FROM pool_universities").fetchone()[0]
    from services import pool_uni
    try:
        with _db() as c:
            has_links = c.execute("SELECT COUNT(*) FROM pool_uni_professions").fetchone()[0]
    except sqlite3.OperationalError:
        has_links = 0
    if not has_links:
        pool_uni.build_links()
    if n_org == 0 and n_prof == 0:
        import_pools()
        with _db() as c:
            n_org = c.execute("SELECT COUNT(*) FROM pool_organizations").fetchone()[0]
            n_prof = c.execute("SELECT COUNT(*) FROM pool_professions").fetchone()[0]
            n_uni = c.execute("SELECT COUNT(*) FROM pool_universities").fetchone()[0]

    def bar(extra: str = "") -> str:
        return (f'<form method="get" action="{url_for("pool.pool_page")}" class="pf-bar">'
                f'<input type="hidden" name="tab" value="{tab}">'
                f'<input name="q" value="{q}" placeholder="Поиск по названию, ИНН, обязанностям">'
                f'{extra}<button class="btn sm" type="submit">Найти</button></form>')

    profs_body = bar() + _prof_rows(_profs(q))
    city_sel = (f'<select name="city" onchange="this.form.submit()">'
                f'<option value="">Все города</option>'
                + "".join(f'<option value="{c}"{" selected" if c == city else ""}>{c}</option>'
                          for c in _cities()) + "</select>")
    orgs_body = bar(city_sel) + _org_rows(_orgs(city, q))
    unis_body = bar() + _uni_rows(_unis("" if tab != "universities" else city, q))

    body = (PF_CSS + "<h2>База значений</h2>"
            "<p class=\'muted\'>Три справочника связаны: профессия → учебное заведение → организация. "
            "Из них система берёт значения для резюме и договора.</p>"
            + _big_tab("professions", n_prof if not q else len(_profs(q)), open_tab, profs_body)
            + _big_tab("organizations", n_org if not (q or city) else len(_orgs(city, q)), open_tab, orgs_body)
            + _big_tab("universities", n_uni if not q else len(_unis(city, q)), open_tab, unis_body))
    return render("База значений", "pool", body)


def _save_image(file, inn: str, kind: str) -> str:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
        abort(400, "только png/jpg/webp/svg")
    folder = ASSETS / re.sub(r"[^0-9A-Za-z_-]", "_", inn or "unknown")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{kind}{ext}"
    file.save(dest)
    return str(dest.relative_to(DATA))


@bp.route("/pool/org/<int:oid>/upload/<kind>", methods=["POST"])
@login_required
def upload(oid: int, kind: str):  # noqa: ANN201
    if kind not in ("logo", "seal"):
        abort(404)
    f = request.files.get("file")
    if not f:
        abort(400, "нет файла")
    with _db() as c:
        row = c.execute("SELECT inn FROM pool_organizations WHERE id=?", (oid,)).fetchone()
        if not row:
            abort(404)
        rel = _save_image(f, row["inn"], kind)
        c.execute(f"UPDATE pool_organizations SET {kind}_path=?, updated_at=? WHERE id=?",
                  (rel, datetime.now().isoformat(timespec="seconds"), oid))
    return redirect(url_for("pool.pool_page", open="organizations"))


@bp.route("/pool/asset/<int:oid>/<kind>")
@login_required
def asset(oid: int, kind: str):  # noqa: ANN201
    if kind not in ("logo", "seal"):
        abort(404)
    with _db() as c:
        row = c.execute("SELECT logo_path, seal_path FROM pool_organizations WHERE id=?",
                        (oid,)).fetchone()
    if not row:
        abort(404)
    rel = row["logo_path"] if kind == "logo" else row["seal_path"]
    if not rel:
        abort(404)
    p = Path(rel)
    if not p.is_absolute():
        p = DATA / rel
    if not p.exists():
        abort(404)
    return send_file(p, max_age=3600)
