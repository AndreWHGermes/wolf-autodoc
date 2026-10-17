"""Наполнение резюме (документ «Резюме Сиваева»): образование, опыт работы, профиль.

Требование заказчика (06.10.2026): резюме должно быть заполнено по образцу —
город, учебное заведение, специальность, места работы и обязанности — из базы
вариантов системы, и быть правдоподобным для проверки в иммиграционной службе.

Правила:
  * выбор вариантов детерминированный (seed по клиенту и заявке) — при повторной
    сборке документа резюме не меняется;
  * компания текущего места работы берётся из заявки/договора, прошлое место — из
    пула компаний по сфере профессии (data/cv_companies.json);
  * учебное заведение — по городу клиента (data/cv_universities.json, 35 городов),
    специальность — по профилю профессии;
  * ничего не выдумывается сверх пулов: тексты обязанностей — из описаний профессии
    (data/cv_positions.json, блоки short/medium/long).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

BASE = Path("/opt/wolf_v2")
DB = BASE / "data" / "wolf.db"

# Сфера для прошлого места работы — по коду профессии.
PROFESSION_SECTOR = {
    "artist_producer": "media_education",
    "designer": "it_software",
    "graphic_designer": "it_software",
    "ui_ux_designer": "it_software",
    "web_developer": "it_software",
    "programmer": "it_software",
    "software_engineer": "it_software",
    "sysadmin": "it_software",
    "qa_engineer": "it_software",
    "data_analyst": "it_software",
    "marketer": "services_agency",
    "smm_manager": "services_agency",
    "sales_manager": "logistics_trade",
    "logistics_manager": "logistics_trade",
    "accountant": "bank_insurance",
    "economist": "bank_insurance",
    "lawyer": "services_agency",
    "doctor": "services_agency",
    "teacher": "media_education",
    "translator": "media_education",
    "project_manager": "services_agency",
    "engineer": "industry_production",
    "builder": "construction_architecture",
    "cook": "food_service",
    "driver": "logistics_trade",
    "nurse": "household_service",
}

# Профиль специальности по профессии (ключи majors из cv_universities.json).
PROFESSION_MAJORS = {
    "artist_producer": ["Cultural Studies", "Journalism", "Marketing", "Management"],
    "designer": ["Information Technology", "Marketing", "Management"],
    "graphic_designer": ["Information Technology", "Marketing"],
    "ui_ux_designer": ["Information Technology", "Marketing"],
    "web_developer": ["Information Technology", "Applied Mathematics"],
    "programmer": ["Information Technology", "Applied Mathematics"],
    "software_engineer": ["Information Technology", "Applied Mathematics"],
    "sysadmin": ["Information Technology"],
    "qa_engineer": ["Information Technology"],
    "data_analyst": ["Applied Mathematics", "Information Technology"],
    "marketer": ["Marketing", "Management"],
    "smm_manager": ["Marketing", "Journalism"],
    "sales_manager": ["Management", "Economics"],
    "accountant": ["Economics", "Finance"],
    "economist": ["Economics", "Finance"],
    "lawyer": ["Law", "International Relations"],
    "teacher": ["Pedagogy", "Linguistics"],
    "translator": ["Linguistics", "International Relations"],
    "doctor": ["General Medicine", "Public Health"],
    "nurse": ["Public Health"],
}

# Прошлое (младшее) название должности — для второго места работы.
JUNIOR_TITLE = {
    "artist_producer": ("Assistant Producer", "Junior Producer", "Production Coordinator"),
    "designer": ("Junior Designer", "Design Assistant", "Visual Designer"),
    "programmer": ("Junior Developer", "Software Developer", "Backend Developer"),
    "marketer": ("Marketing Assistant", "Marketing Specialist", "Digital Marketing Specialist"),
    "sales_manager": ("Sales Assistant", "Sales Specialist", "Account Manager"),
    "accountant": ("Assistant Accountant", "Accounting Specialist", "Bookkeeper"),
    "default": ("Specialist", "Assistant Specialist", "Coordinator"),
}

MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")


# Название должности → код профессии. Нужен, когда position_code у клиента пуст:
# без него резюме берёт дефолтный профиль и в документ попадают чужие навыки.
TITLE_TO_CODE = (
    ("sales manager", "sales_manager"), ("sales", "sales_manager"),
    ("marketing", "marketer"), ("smm", "smm_manager"),
    ("design", "designer"), ("developer", "programmer"),
    ("programmer", "programmer"), ("engineer", "engineer"),
    ("accountant", "accountant"), ("lawyer", "lawyer"),
    ("translator", "translator"), ("project manager", "project_manager"),
    ("producer", "artist_producer"), ("teacher", "teacher"),
    ("doctor", "doctor"), ("nurse", "nurse"),
    ("cook", "cook"), ("driver", "driver"),
)


# Сфера деятельности для описания в резюме — по коду профессии.
SPHERE_BY_CODE = {
    "sales_manager": "B2B and online sales",
    "marketer": "digital marketing",
    "smm_manager": "social media marketing",
    "designer": "design",
    "graphic_designer": "graphic design",
    "ui_ux_designer": "UX/UI design",
    "programmer": "software development",
    "web_developer": "web development",
    "software_engineer": "software engineering",
    "sysadmin": "IT infrastructure",
    "qa_engineer": "software testing",
    "data_analyst": "data analysis",
    "accountant": "accounting",
    "economist": "economics",
    "lawyer": "legal practice",
    "logistics_manager": "logistics",
    "project_manager": "project management",
    "artist_producer": "media production",
    "teacher": "education",
    "translator": "translation",
    "engineer": "engineering",
    "builder": "construction",
    "cook": "food service",
    "driver": "transport",
    "nurse": "healthcare",
    "doctor": "healthcare",
}


def _code_by_title(title) -> str:
    t = str(title or "").lower()
    for word, code in TITLE_TO_CODE:
        if word in t:
            return code
    return ""


def _seed(*parts) -> int:
    key = "|".join(str(p or "") for p in parts)
    return int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:12], 16)


def _load(name: str, default):
    try:
        with open(BASE / "data" / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _positions() -> list:
    d = _load("cv_positions.json", [])
    if isinstance(d, dict):
        d = d.get("positions") or d.get("items") or [v for v in d.values() if isinstance(v, dict)]
    return d or []


def _position(code: str) -> dict:
    return next((r for r in _positions() if isinstance(r, dict) and r.get("code") == code), {}) or {}


def _client(client_id: int) -> dict:
    try:
        c = sqlite3.connect(str(DB))
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        c.close()
        return dict(row) if row else {}
    except Exception:
        return {}


def _bullets(text: str, limit: int) -> str:
    """Описание профессии → пункты обязанностей: каждый с новой строки, с точкой.

    Разделитель — перевод строки (в шаблоне у блока включён pre-wrap): тег <br>
    при сборке PDF вырезался, и все пункты слипались в одну строку через «•».
    """
    parts = [p.strip() for p in re.split(r"(?<=[.;])\s+", str(text or "")) if p.strip()]
    out = []
    for p in parts[:limit]:
        p = p.rstrip(".;")
        if not p:
            continue
        p = p[0].upper() + p[1:]
        out.append("\u2022 " + p + ".")
    return "\n".join(out)


def _city_key(client: dict) -> str:
    """Город для выбора учебного заведения — по месту рождения клиента.

    Адрес проживания в Индонезии для этого не годится: там вуз выпадал в Ubud/Bali,
    а в резюме нужен учебный город из личных данных клиента (как в образце).
    """
    unis = _load("cv_universities.json", {}) or {}
    cities = unis.get("cities") or {}
    # 1) город проживания в РФ (адрес из документов клиента);
    # 2) если не вышло — место рождения.
    # Не-российские отделения (Бали, Турция, Узбекистан) из адреса проживания
    # не берём: вуз в резюме должен быть в России.
    _non_ru = ("indonesia", "turkey", "uzbekistan")
    hay_addr = " ".join(str(client.get(k) or "") for k in
                        ("address_live", "address_reg")).lower()
    hay_birth = " ".join(str(client.get(k) or "") for k in
                         ("birth_place", "citizenship", "nationality")).lower()
    for hay, skip_non_ru in ((hay_addr, True), (hay_birth, False)):
        if not hay.strip():
            continue
        for key, info in cities.items():
            if skip_non_ru and key in _non_ru:
                continue
            aliases = [str(a).lower() for a in (info.get("aliases") or [])]
            aliases += [str(info.get("en") or "").lower(), str(info.get("ru") or "").lower()]
            for alias in aliases:
                if alias and alias in hay:
                    return key
    return ""


def _years(client: dict, seed: int) -> str:
    """Годы обучения: возраст − 22, четыре года обучения."""
    bd = str(client.get("birth_date") or "")
    year = None
    m = re.search(r"(19|20)\d{2}", bd)
    if m:
        year = int(m.group(0))
    if not year:
        year = 1990
    start = year + 18 + (seed % 2)
    return "%d \u2013 %d" % (start, start + 4)


def fill_for(app_id: int = 0, client: dict | None = None, code: str = "",
             company: str = "", start_year: int | None = None) -> dict:
    """Значения cv_* для резюме. Пустая строка вместо значения — поле не заполнено."""
    try:
        client = dict(client or {})
        if not client and app_id:
            row = None
            try:
                c = sqlite3.connect(str(DB))
                c.row_factory = sqlite3.Row
                row = c.execute("SELECT client_id FROM applications WHERE id=?", (app_id,)).fetchone()
                c.close()
            except Exception:
                row = None
            if row:
                client = _client(row["client_id"])
        if not code:
            code = str(client.get("position_code") or "") or _code_by_title(client.get("position"))
        seed = _seed(client.get("id"), app_id, code)
        rec = _position(code)

        unis = _load("cv_universities.json", {}) or {}
        ck = _city_key(client)
        city = (unis.get("cities") or {}).get(ck) or {}
        schools = city.get("universities") or []
        if not schools:
            schools = unis.get("default") or []
        school = schools[seed % len(schools)] if schools else ""

        majors_pool = PROFESSION_MAJORS.get(code) or (unis.get("majors") or {}).get("general") or []
        majors_pool = [m for m in majors_pool if m] or ["Business Management"]
        major = majors_pool[seed % len(majors_pool)]
        degrees = unis.get("degrees") or ["Bachelor's Degree"]
        degree = degrees[seed % len(degrees)]

        blocks = (rec.get("blocks") or {}) if isinstance(rec, dict) else {}
        cur_title = str(rec.get("en") or client.get("position") or "").strip()
        cur_company = str(company or "").strip()
        # Организацию не выдумываем: если она не пришла из заявки — в резюме её не будет
        # (название подставит values.py из единого источника заявки).
        cur_period = ("%s \u2013 Present" % start_year) if start_year else "%d \u2013 Present" % (2019 + seed % 4)

        # Прошлое место работы — только реальные данные клиента (job2_company/job3_company).
        # Раньше здесь бралась случайная компания из справочника — в документы попадали
        # чужие названия (Eduwave Learning LLC, Linguamarina, Inc).
        prev_company = str(client.get("job2_company") or client.get("job3_company") or "").strip()
        prev_title = str(client.get("job2_position") or "").strip() or (JUNIOR_TITLE.get(code) or JUNIOR_TITLE["default"])[seed % len(JUNIOR_TITLE.get(code) or JUNIOR_TITLE["default"])]
        p0 = 2016 + seed % 2
        prev_period = "%d \u2013 %d" % (p0, p0 + 3) if prev_company else ""

        skills = str(rec.get("skills") or "").strip()
        # Профиль: сферу берём из первого навыка, а из перечня навыков её убираем —
        # иначе выходит «across music and video production. Skilled in Music and video
        # production, …» (одна и та же фраза дважды подряд).
        # Сфера — осмысленная фраза по профессии. Раньше брался первый навык,
        # и описание рвалось по запятой внутри скобок: «across crm (bitrix24.
        # Skilled in amoCRM), negotiations...».
        _sphere = SPHERE_BY_CODE.get(code) or "the industry"
        _rest = skills
        years_n = max(3, min(12, (2019 + seed % 4) - (2016 + seed % 2) + 3))
        summary = ("%s professional with over %d years of experience across %s. Skilled in %s. "
                   "Works fully remotely and independently for a Russian company."
                   % (cur_title or "Specialist", years_n, _sphere, _rest))
        return {
            "cv_education_school": school,
            "cv_education_degree": major,
            "cv_education_years": _years(client, seed),
            "cv_job1_title": cur_title,
            "cv_job1_company": cur_company,
            "cv_job1_period": cur_period,
            "cv_job1_bullets": _bullets(blocks.get("long") or blocks.get("medium") or "", 4),
            "cv_job2_title": prev_title,
            "cv_job2_company": prev_company,
            "cv_job2_period": prev_period,
            "cv_job2_bullets": _bullets(blocks.get("medium") or blocks.get("short") or "", 3),
            "cv_summary": summary,
            "cv_skills_hard": skills,
        }
    except Exception:
        return {}


if __name__ == "__main__":
    import sys
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    code = sys.argv[2] if len(sys.argv) > 2 else "artist_producer"
    res = fill_for(app_id=aid, code=code)
    for k, v in res.items():
        print("%-22s %s" % (k, str(v)[:120]))
