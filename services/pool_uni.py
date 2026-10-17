# -*- coding: utf-8 -*-
"""Связь «вуз ↔ профессии»: где человек мог учиться по своей профессии.

Профессия относится к отрасли, отрасль — к направлению обучения. Вуз получает
направления по своему профилю (медицинский, технический, экономический,
гуманитарный), поэтому из него и берётся образование в резюме: клиент учился
в конкретном вузе и получил профессию, по которой работает.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "wolf.db"

MAJOR_BY_SECTOR = {
    "it_software": "technical",
    "construction": "technical",
    "construction_architecture": "technical",
    "manufacturing": "technical",
    "industry_production": "technical",
    "logistics": "economics",
    "logistics_trade": "economics",
    "finance": "economics",
    "bank_insurance": "economics",
    "ecommerce_retail": "economics",
    "healthcare": "medical",
    "education": "humanities",
    "media_education": "humanities",
    "services_agency": "humanities",
    "household_service": "humanities",
}

MED = ("medical", "medic", "sechenov", "медиц")
TECH = ("technical", "polytechnic", "engineering", "aviation", "mining", "telecom",
        "transport", "construction", "architecture", "oil", "energy", "bauman",
        "misis", "atomic")
ECON = ("econom", "financ", "trade", "management", "plekhanov", "gsom", "business")
HUM = ("pedagog", "humanit", "linguist", "international", "mgimo", "rudn", "herzen",
       "culture", "art", "teacher")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def majors_of(name_en: str) -> list[str]:
    n = (name_en or "").lower()
    if any(k in n for k in MED):
        return ["medical"]
    majors = []
    if any(k in n for k in TECH):
        majors.append("technical")
    if any(k in n for k in ECON):
        majors.append("economics")
    if any(k in n for k in HUM):
        majors.append("humanities")
    return majors or ["technical", "economics", "humanities"]


def build_links() -> int:
    """Заполнить связку вуз↔профессия (идемпотентно)."""
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pool_uni_professions(
            university_id INTEGER NOT NULL, profession_code TEXT NOT NULL,
            sector TEXT, major TEXT, PRIMARY KEY(university_id, profession_code))""")
        c.execute("DELETE FROM pool_uni_professions")
        unis = [dict(r) for r in c.execute("SELECT id, name_en, city_ru FROM pool_universities")]
        profs = [dict(r) for r in c.execute(
            "SELECT code, sector FROM pool_professions WHERE remote=1 AND COALESCE(sector,'')<>''")]
        n = 0
        for u in unis:
            majors = majors_of(u["name_en"])
            for m in majors:
                for p in profs:
                    if MAJOR_BY_SECTOR.get(p["sector"] or "") != m:
                        continue
                    c.execute("INSERT OR IGNORE INTO pool_uni_professions"
                              "(university_id, profession_code, sector, major) VALUES (?,?,?,?)",
                              (u["id"], p["code"], p["sector"], m))
                    n += 1
    return n


def professions_for(uni_id: int, limit: int | None = None) -> list[str]:
    sql = ("SELECT p.title_ru FROM pool_uni_professions l "
           "JOIN pool_professions p ON p.code=l.profession_code "
           "WHERE l.university_id=? ORDER BY p.title_ru")
    with _db() as c:
        rows = [r[0] for r in c.execute(sql, (uni_id,))]
    return rows[:limit] if limit else rows


def all_titles() -> dict[int, list[str]]:
    """Все связки одним запросом: {id вуза: [профессии]} — чтобы не 117 запросов на страницу."""
    out: dict[int, list[str]] = {}
    with _db() as c:
        for uid, title in c.execute(
                "SELECT l.university_id, p.title_ru FROM pool_uni_professions l "
                "JOIN pool_professions p ON p.code=l.profession_code ORDER BY p.title_ru"):
            out.setdefault(uid, []).append(title)
    return out


def count_for(uni_id: int) -> int:
    with _db() as c:
        return c.execute("SELECT COUNT(*) FROM pool_uni_professions WHERE university_id=?",
                         (uni_id,)).fetchone()[0]


def pick(sector: str, city: str = "") -> dict:
    """Вуз под профессию и город клиента: сначала его город, затем Москва/СПб."""
    major = MAJOR_BY_SECTOR.get(sector or "", "humanities")
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM pool_universities WHERE majors LIKE ?", ("%%%s%%" % major,))]
    if not rows:
        with _db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM pool_universities LIMIT 50")]
    keywords = {"medical": MED, "technical": TECH, "economics": ECON, "humanities": HUM}
    primary = {"medical": ("medical", "medic"), "technical": ("technical", "polytechnic", "bauman"),
               "economics": ("econom", "financ", "trade"), "humanities": ("pedagog", "teacher", "humanit")}
    words, first = keywords.get(major, ()), primary.get(major, ())

    def score(u: dict) -> tuple:
        name = (u.get("name_en") or "").lower()
        return (u.get("city_ru") == city, any(k in name for k in first), any(k in name for k in words),
                major in majors_of(u.get("name_en") or ""), u.get("city_ru") == "Москва",
                u.get("city_ru") == "Санкт-Петербург")
    rows.sort(key=score, reverse=True)
    return rows[0] if rows else {}


if __name__ == "__main__":
    print("связей:", build_links())
