# -*- coding: utf-8 -*-
"""Блок «База значений»: справочники, из которых берутся значения документов.

Две вкладки:
  * Профессии — удалённые профессии, их обязанности и навыки (cv_positions.json,
    remote_professions.json). Отсюда берётся содержание резюме.
  * Организации — реальные компании с ИНН, адресом, ФИО генерального директора,
    городом и описанием деятельности (orgs_pool.json, organizations.json).
    К каждой можно прикрепить логотип и печать: логотип ставится в шапку договора,
    печать — на подпись.

Файлы картинок лежат в data/pool_assets/<ИНН>/logo.* и seal.* и отдаются через
/pool/asset/<id>/<kind>, чтобы не пересобирать статику.
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
    "services_agency": "Услуги, агентство",
    "it_software": "ИТ и разработка ПО",
    "logistics": "Логистика и перевозки",
    "construction": "Строительство",
    "finance": "Финансы",
    "media": "Медиа и реклама",
    "education": "Образование",
    "medical": "Медицина",
    "manufacturing": "Производство",
}
CITY_ORDER = ("Москва", "Санкт-Петербург")

SECTOR_DESC = {
    "ecommerce_retail": "розничная торговля и продажи через маркетплейсы и интернет-магазины",
    "services_agency": "услуги для бизнеса: консалтинг, администрирование, работа с клиентами",
    "it_software": "разработка и поддержка программного обеспечения и веб-сервисов",
    "logistics": "перевозки, складская логистика и таможенное оформление",
    "construction": "строительство, ремонт и проектирование объектов",
    "finance": "финансовые и бухгалтерские услуги",
    "media": "медиа, реклама и маркетинг",
    "education": "образовательные услуги и обучение",
    "medical": "медицинские услуги и клиники",
    "manufacturing": "производство и промышленность",
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pool_organizations(
            id INTEGER PRIMARY KEY,
            inn TEXT UNIQUE, kpp TEXT, ogrn TEXT,
            name TEXT, name_en TEXT, legal_form_en TEXT,
            city TEXT, address TEXT, director TEXT,
            sector TEXT, domain TEXT, description TEXT,
            logo_path TEXT, seal_path TEXT, source TEXT, updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS pool_professions(
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE, title_ru TEXT, title_en TEXT, sector TEXT,
            duties TEXT, skills TEXT, description TEXT, keys TEXT,
            remote INTEGER DEFAULT 1, source TEXT, updated_at TEXT)""")


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
    """Переносит пулы в базу. Повторный запуск обновляет записи, не дублирует."""
    ensure_schema()
    now = datetime.now().isoformat(timespec="seconds")
    orgs = 0
    profs = 0
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
                 description,source,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                       o.get("city") or _city_of(o.get("address")), o.get("address") or "", o.get("director") or "",
                       o.get("sector") or "", o.get("domain") or "",
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
            skills = ", ".join(p.get("skills") or []) if isinstance(p.get("skills"), list) else (p.get("skills") or "")
            sector = p.get("sector") or ""
            if not sector:
                try:
                    from services import org_pool
                    sector = org_pool.sector_of_profession(p.get("en") or p.get("ru") or "")
                except Exception:
                    sector = ""
            c.execute("""INSERT INTO pool_professions
                (code,title_ru,title_en,sector,duties,skills,description,keys,remote,source,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET
                  title_ru=excluded.title_ru, title_en=excluded.title_en, sector=excluded.sector,
                  duties=excluded.duties, skills=excluded.skills, keys=excluded.keys,
                  updated_at=excluded.updated_at""",
                      (p.get("code") or re.sub(r"\W+", "_", str(p.get("en") or "")).lower(),
                       p.get("ru") or "", p.get("en") or "", sector, duties, skills,
                       (blocks.get("medium") or "").strip(), ", ".join(p.get("keys") or []),
                       1, "cv_positions", now))
            profs += 1

        remote = (_load("remote_professions.json", {}) or {}).get("sectors") or {}
        try:
            from services import cv_content
        except Exception:
            cv_content = None

        def _pack(sector: str) -> dict:
            if not cv_content:
                return {}
            packs = cv_content.BY_SECTOR
            if sector in packs:
                return packs[sector]
            for key, val in packs.items():
                if sector.startswith(key) or key in sector:
                    return val
            return getattr(cv_content, "_DEFAULT", {})

        for sector, titles in remote.items():
            pack = _pack(sector)
            for t in titles or []:
                code = re.sub(r"\W+", "_", str(t)).strip("_").lower()[:60]
                if not code:
                    continue
                duties = "\n".join(x.strip() for x in str(pack.get("bullets") or "").split("\n") if x.strip())
                c.execute("""INSERT INTO pool_professions
                    (code,title_ru,title_en,sector,duties,skills,description,keys,remote,source,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(code) DO UPDATE SET
                      sector=COALESCE(NULLIF(excluded.sector,''), pool_professions.sector),
                      duties=CASE WHEN COALESCE(pool_professions.duties,'')='' THEN excluded.duties ELSE pool_professions.duties END,
                      skills=CASE WHEN COALESCE(pool_professions.skills,'')='' THEN excluded.skills ELSE pool_professions.skills END""",
                          (code, str(t), str(t), sector, duties, pack.get("hard") or "",
                           "Типовые обязанности по отрасли" if duties else "",
                           "", 1, "remote_professions", now))
                profs += 1
    return {"organizations": orgs, "professions": profs}


def _orgs(city: str = "", q: str = "") -> list[dict]:
    sql = "SELECT * FROM pool_organizations WHERE 1=1"
    args: list = []
    if city:
        sql += " AND city=?"
        args.append(city)
    if q:
        sql += " AND (name LIKE ? OR name_en LIKE ? OR inn LIKE ? OR director LIKE ? OR address LIKE ?)"
        args += ["%%%s%%" % q] * 5
    sql += " ORDER BY CASE city WHEN 'Москва' THEN 0 WHEN 'Санкт-Петербург' THEN 1 ELSE 2 END, name"
    with _db() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _profs(q: str = "") -> list[dict]:
    sql = "SELECT * FROM pool_professions WHERE remote=1"
    args: list = []
    if q:
        sql += " AND (title_ru LIKE ? OR title_en LIKE ? OR duties LIKE ?)"
        args += ["%%%s%%" % q] * 3
    sql += " ORDER BY title_en"
    with _db() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _cities() -> list[str]:
    with _db() as c:
        rows = [r[0] for r in c.execute("SELECT DISTINCT city FROM pool_organizations WHERE city<>''")]
    return sorted(rows, key=lambda x: (CITY_ORDER.index(x) if x in CITY_ORDER else 9, x))


def _asset_url(oid: int, kind: str, path: str | None) -> str:
    if not path:
        return ""
    if str(path).startswith(("http://", "https://")):
        return str(path)
    return url_for("pool.asset", oid=oid, kind=kind)


def _tabs(active: str, city: str, q: str) -> str:
    def link(tab: str, label: str) -> str:
        cls = "btn" if tab == active else "btn ghost"
        return (f'<a class="{cls} sm" href="{url_for("pool.pool_page", tab=tab, city=city, q=q)}">'
                f'{label}</a>')
    return ('<div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px">'
            + link("professions", "Профессии и обязанности")
            + link("organizations", "Организации") + "</div>")


def _professions_html(rows: list[dict]) -> str:
    if not rows:
        return "<p class='muted'>Пусто. Запустите импорт пулов.</p>"
    out = [f"<p class='muted'>Профессий: {len(rows)}. Обязанности берутся в резюме.</p>"]
    for p in rows:
        duties = (p.get("duties") or "").replace("\n", "<br>")
        out.append(
            f'<details class="card"><summary><span><b>{p.get("title_en") or p.get("title_ru")}</b>'
            f' <span class="muted">{p.get("title_ru") or ""}</span></span><span class="chev">›</span></summary>'
            f'<div class="body"><p class="muted">{SECTOR_RU.get(p.get("sector") or "", p.get("sector") or "")}</p>'
            f'<div style="white-space:normal">{duties or "<i>обязанности не заполнены</i>"}</div>'
            + (f'<p style="margin-top:8px"><b>Навыки:</b> {p.get("skills")}</p>' if p.get("skills") else "")
            + f'<details style="margin-top:10px"><summary class="muted">Изменить профессию</summary>'
              f'<form method="post" action="{url_for("pool.edit_prof", pid=p["id"])}" style="display:grid;gap:6px;margin-top:8px">'
              f'<input name="title_en" value="{p.get("title_en") or ""}" placeholder="Название (англ.)">'
              f'<input name="title_ru" value="{p.get("title_ru") or ""}" placeholder="Название (рус.)">'
              f'<input name="sector" value="{p.get("sector") or ""}" placeholder="Отрасль (код)">'
              f'<textarea name="duties" rows="5" placeholder="Обязанности (по строке)">{p.get("duties") or ""}</textarea>'
              f'<input name="skills" value="{p.get("skills") or ""}" placeholder="Навыки">'
              f'<input name="description" value="{p.get("description") or ""}" placeholder="Описание">'
              f'<button class="btn sm" type="submit">Сохранить</button></form></details>'
            + "</div></details>")
    return "".join(out)


def _orgs_html(rows: list[dict], city: str, q: str) -> str:
    if not rows:
        return "<p class='muted'>Ничего не найдено.</p>"
    out = [f"<p class='muted'>Организаций: {len(rows)}</p>"]
    for o in rows:
        logo = _asset_url(o["id"], "logo", o.get("logo_path"))
        seal = _asset_url(o["id"], "seal", o.get("seal_path"))
        logo_html = (f'<img src="{logo}" alt="logo" style="width:64px;height:64px;object-fit:contain;'
                     f'border:1px solid var(--line);border-radius:10px;background:#fff">'
                     if logo else '<div style="width:64px;height:64px;border:1px dashed var(--line);'
                                  'border-radius:10px;display:grid;place-items:center;color:#9AA3B2;font-size:11px">logo</div>')
        seal_html = (f'<img src="{seal}" alt="seal" style="width:56px;height:56px;object-fit:contain;'
                     f'border:1px solid var(--line);border-radius:50%;background:#fff">' if seal else "")
        desc = SECTOR_DESC.get(o.get("sector") or "", SECTOR_RU.get(o.get("sector") or "", o.get("sector") or ""))
        out.append(f"""<details class="card"><summary>
            <span style="display:flex;gap:10px;align-items:center">{logo_html}
            <span><b>{o.get('name')}</b><br><span class="muted">{o.get('city') or '—'} · ИНН {o.get('inn')}</span></span></span>
            <span class="chev">›</span></summary>
            <div class="body">
              <p><b>Официальное название:</b> {o.get('name_en') or '—'}</p>
              <p><b>ИНН / КПП:</b> {o.get('inn')} / {o.get('kpp') or '—'} · <b>ОГРН:</b> {o.get('ogrn') or '—'}</p>
              <p><b>Адрес:</b> {o.get('address') or '—'}</p>
              <p><b>Генеральный директор:</b> {o.get('director') or '— не заполнен —'}</p>
              <p><b>Деятельность:</b> {desc or '—'}{(' · ' + o.get('domain')) if o.get('domain') else ''}</p>
              <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
                {seal_html}
                <form method="post" enctype="multipart/form-data" action="{url_for('pool.upload', oid=o['id'], kind='logo')}"
                      style="display:flex;gap:6px;align-items:center">
                  <input type="file" name="file" accept="image/*" required>
                  <button class="btn sm" type="submit">Загрузить логотип</button>
                </form>
                <form method="post" enctype="multipart/form-data" action="{url_for('pool.upload', oid=o['id'], kind='seal')}"
                      style="display:flex;gap:6px;align-items:center">
                  <input type="file" name="file" accept="image/*" required>
                  <button class="btn sm ghost" type="submit">Загрузить печать</button>
                </form>
              </div>
              <details style="margin-top:10px"><summary class="muted">Изменить данные организации</summary>
                <form method="post" action="{url_for('pool.edit_org', oid=o['id'])}"
                      style="display:grid;gap:6px;margin-top:8px">
                  <input name="name" value="{o.get('name') or ''}" placeholder="Название">
                  <input name="name_en" value="{o.get('name_en') or ''}" placeholder="Название латиницей">
                  <input name="city" value="{o.get('city') or ''}" placeholder="Город">
                  <input name="address" value="{o.get('address') or ''}" placeholder="Адрес">
                  <input name="director" value="{o.get('director') or ''}" placeholder="ФИО генерального директора">
                  <input name="domain" value="{o.get('domain') or ''}" placeholder="Сайт (домен)">
                  <input name="sector" value="{o.get('sector') or ''}" placeholder="Отрасль (код)">
                  <input name="description" value="{o.get('description') or ''}" placeholder="Краткое описание деятельности">
                  <button class="btn sm" type="submit">Сохранить</button>
                </form>
              </details>
            </div></details>""")
    return "".join(out)


@bp.route("/pool")
@login_required
def pool_page():  # noqa: ANN201
    ensure_schema()
    tab = request.args.get("tab") or "professions"
    city = request.args.get("city") or ""
    q = (request.args.get("q") or "").strip()
    with _db() as c:
        n_org = c.execute("SELECT COUNT(*) FROM pool_organizations").fetchone()[0]
        n_prof = c.execute("SELECT COUNT(*) FROM pool_professions").fetchone()[0]
    if n_org == 0 and n_prof == 0:
        import_pools()

    body = [f"<h2>База значений</h2><p class='muted'>Организаций: {n_org} · профессий: {n_prof}. "
            f"Отсюда система берёт значения для резюме и договора.</p>",
            _tabs(tab, city, q),
            f"""<form method="get" action="{url_for('pool.pool_page')}" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
                 <input type="hidden" name="tab" value="{tab}">
                 <input name="q" value="{q}" placeholder="поиск: название, ИНН, директор" style="flex:1;min-width:180px">
                 <select name="city" onchange="this.form.submit()">
                   <option value="">Все города</option>
                   {''.join(f'<option value="{c}"{" selected" if c == city else ""}>{c}</option>' for c in _cities())}
                 </select>
                 <button class="btn" type="submit">Найти</button>
               </form>"""]

    if tab == "organizations":
        body.append(_orgs_html(_orgs(city, q), city, q))
    else:
        body.append(_professions_html(_profs(q)))
    return render("База значений", "pool", "".join(body))


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
    return redirect(url_for("pool.pool_page", tab="organizations"))


@bp.route("/pool/org/<int:oid>/edit", methods=["POST"])
@login_required
def edit_org(oid: int):  # noqa: ANN201
    fields = ("name", "name_en", "city", "address", "director", "sector", "domain", "description")
    data = {k: (request.form.get(k) or "").strip() for k in fields}
    with _db() as c:
        if not c.execute("SELECT 1 FROM pool_organizations WHERE id=?", (oid,)).fetchone():
            abort(404)
        c.execute("""UPDATE pool_organizations SET name=?, name_en=?, city=?, address=?,
                     director=?, sector=?, domain=?, description=?, updated_at=? WHERE id=?""",
                  (data["name"], data["name_en"], data["city"], data["address"], data["director"],
                   data["sector"], data["domain"], data["description"],
                   datetime.now().isoformat(timespec="seconds"), oid))
    return redirect(url_for("pool.pool_page", tab="organizations"))


@bp.route("/pool/prof/<int:pid>/edit", methods=["POST"])
@login_required
def edit_prof(pid: int):  # noqa: ANN201
    fields = ("title_ru", "title_en", "sector", "duties", "skills", "description")
    data = {k: (request.form.get(k) or "").strip() for k in fields}
    with _db() as c:
        if not c.execute("SELECT 1 FROM pool_professions WHERE id=?", (pid,)).fetchone():
            abort(404)
        c.execute("""UPDATE pool_professions SET title_ru=?, title_en=?, sector=?, duties=?,
                     skills=?, description=?, updated_at=? WHERE id=?""",
                  (data["title_ru"], data["title_en"], data["sector"], data["duties"],
                   data["skills"], data["description"],
                   datetime.now().isoformat(timespec="seconds"), pid))
    return redirect(url_for("pool.pool_page", tab="professions"))


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
