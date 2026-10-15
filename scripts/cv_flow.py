#!/usr/bin/env python3
"""Резюме (cv__format_*) потоковой вёрсткой: формат как в образце, текст течёт.

Почему так: резюме — не форма с фиксированными полями, а документ с переменным объёмом.
Координатная сборка (по зонам бланка) не выдерживает длинных описаний: блоки налезают друг
на друга, длинные пункты печатаются по слову в строке. Здесь текст идёт потоком: шапка,
разделы с линиями, абзацы, — сколько бы ни было пунктов обязанностей и организаций.

Стиль снят с образца data/templates/<code>/example_filled.pdf:
  имя       Arial Bold 18pt   #1e3764, по центру
  должность Arial 12pt        чёрный, по центру
  город     Arial 10.08pt     по центру
  личные    Arial 10.08pt     по центру
  заголовки Arial Bold 11.04pt #1e3764 + линия 0.72pt #1e3764 (x 46.1–549.3)
  опыт      должность Bold 10.08 / компания Italic 10.08 / период справа
  пункты    Times New CLIENT 10.08pt, отступ 7.5pt

    cv_flow.py [code] [--app 89] [--stress] [--out file.pdf]
"""
import argparse
import html as _html
import importlib.util
import pathlib
import re
import subprocess
import sys

BASE = pathlib.Path("/opt/wolf_v2")
OUT = pathlib.Path("/tmp/wordrun")

STRESS = {
    "cv_profession": "Senior Cinematographer, Film Editor and Post-Production Supervisor",
    "cv_summary": (
        "Senior Cinematographer and Film Editor with over fourteen years of experience in feature "
        "films, commercial production, documentary projects and streaming series across Europe, "
        "the Middle East and South-East Asia. Led camera departments of up to eighteen people, "
        "planned shooting schedules, managed equipment budgets and supervised post-production "
        "delivery for international distributors. Works fully remotely and independently for a "
        "Russian production company, coordinating crews and vendors across several time zones."
    ),
    "cv_job1_title": "Executive Director / Head of Production Department",
    "cv_job1_company": ('LLC "PICKUP FILM PRODUCTION COMPANY", Zelenograd, Moscow, Russia | '
                        "www.pickupfilm-production.ru | +7 495 123-45-67"),
    "cv_job1_bullets": (
        "\u2022  Managing the day-to-day operations of the production company, including budgeting, "
        "scheduling, procurement and compliance with internal policies and local regulations.\n"
        "\u2022  Developing and implementing the company's long-term business strategy, annual "
        "production plans and partnerships with distributors in Europe and Asia.\n"
        "\u2022  Overseeing sales, procurement, supply chain and customer relations, negotiating "
        "contracts with suppliers, studios and freelance crews.\n"
        "\u2022  Supervising staff, monitoring financial performance, preparing quarterly reports and "
        "ensuring the company meets all statutory requirements.\n"
        "\u2022  Leading pre-production planning for eight feature projects simultaneously, including "
        "location scouting, casting support and equipment logistics.\n"
        "\u2022  Managing post-production pipelines, quality control and delivery of final masters to "
        "international streaming platforms and cinema distributors.\n"
        "\u2022  Implementing cost-control measures that reduced production expenses by 18% over two "
        "consecutive financial years without affecting quality.\n"
        "\u2022  Building and mentoring a team of thirty specialists, running internal training and "
        "safety programmes for on-set crews."
    ),
    "cv_education_school": "Gerasimov Russian State University of Cinematography (VGIK), Moscow, Russia",
    "cv_education_degree": "Master of Arts in Cinematography and Post-Production Management",
    "cv_skills_soft": ("production planning, budget management, crew leadership, contract negotiation, "
                       "risk assessment, attention to detail, time management, teamwork, clear "
                       "communication, responsibility, mentoring, conflict resolution, remote team "
                       "coordination"),
    "cv_languages": "Russian (Native), English (Advanced, C1), Indonesian (Basic, A2), German (Basic, A1)",
}

CSS = """
@page { size: A4; margin: 47pt 46.1pt 40pt 46.1pt; }
* { box-sizing: border-box; }
body { font-family: "Liberation Sans", Arial, sans-serif; font-size: 10.08pt; color: #000;
       line-height: 1.22; margin: 0; }
.name { font-size: 18pt; font-weight: 700; color: #1e3764; text-align: center; line-height: 1.15;
        text-transform: uppercase; }
.prof { font-size: 12pt; text-align: center; margin-top: 4pt; }
.city { font-size: 10.08pt; text-align: center; margin-top: 3pt; text-transform: uppercase; }
.personal { font-size: 10.08pt; text-align: center; margin-top: 5pt; }
h2 { font-size: 11.04pt; font-weight: 700; color: #1e3764; margin: 15pt 0 0; padding-bottom: 3.5pt;
     border-bottom: 0.72pt solid #1e3764; }
.job { margin-top: 6pt; }
.jobhead { display: flex; justify-content: space-between; align-items: baseline; }
.jobtitle { font-weight: 700; }
.jobperiod { font-weight: 700; }
.company { font-style: italic; margin-top: 1pt; }
ul { margin: 3pt 0 0 0; padding-left: 0; list-style: none; }
li { font-family: "Times New CLIENT", serif; margin: 0 0 2pt 0; padding-left: 7.5pt; text-indent: -7.5pt; }
.edu { margin-top: 6pt; }
.eduschool { font-weight: 700; }
.edurow { display: flex; justify-content: space-between; align-items: baseline; }
.skills { margin-top: 6pt; }
.langs { margin-top: 6pt; }
"""


def esc(v):
    return _html.escape(str(v if v is not None else ""))


def bullets_html(raw):
    raw = str(raw or "").replace("\r", "")
    items = []
    for line in raw.split("\n"):
        t = line.strip()
        if not t:
            continue
        if t.startswith("\u2022"):
            t = t.lstrip("\u2022 ").strip()
            items.append(t)
        elif items:
            items[-1] = items[-1] + " " + t
        else:
            items.append(t)
    return "".join("<li>\u2022&nbsp;&nbsp;%s</li>" % esc(i) for i in items)


def build_html(v):
    parts = ['<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>' % CSS]
    parts.append('<div class="name">%s</div>' % esc(v.get("cv_name")))
    if v.get("cv_profession"):
        parts.append('<div class="prof">%s</div>' % esc(v["cv_profession"]))
    if v.get("cv_place_of_birth"):
        parts.append('<div class="city">%s</div>' % esc(v["cv_place_of_birth"]))
    personal = []
    if v.get("cv_date_of_birth"):
        personal.append("Date of Birth: %s" % esc(v["cv_date_of_birth"]))
    if v.get("cv_nationality"):
        personal.append("Nationality: %s" % esc(v["cv_nationality"]))
    if v.get("cv_passport_no"):
        personal.append("Passport: %s" % esc(v["cv_passport_no"]))
    if personal:
        parts.append('<div class="personal">%s</div>' % "&nbsp;|&nbsp;".join(personal))

    if v.get("cv_summary"):
        parts.append("<h2>PROFESSIONAL SUMMARY</h2>")
        parts.append("<div>%s</div>" % esc(v["cv_summary"]))

    jobs = []
    for i in (1, 2, 3):
        t, c, p, b = (v.get("cv_job%d_title" % i), v.get("cv_job%d_company" % i),
                      v.get("cv_job%d_period" % i), v.get("cv_job%d_bullets" % i))
        if any([t, c, p, b]):
            jobs.append((t, c, p, b))
    if jobs:
        parts.append("<h2>WORK EXPERIENCE</h2>")
        for t, c, p, b in jobs:
            parts.append('<div class="job">')
            parts.append('<div class="jobhead"><span class="jobtitle">%s</span>'
                         '<span class="jobperiod">%s</span></div>' % (esc(t), esc(p)))
            if c:
                parts.append('<div class="company">%s</div>' % esc(c))
            if b:
                parts.append("<ul>%s</ul>" % bullets_html(b))
            parts.append("</div>")

    if v.get("cv_education_school") or v.get("cv_education_degree"):
        parts.append("<h2>EDUCATION</h2>")
        parts.append('<div class="edu">')
        parts.append('<div class="edurow"><span class="eduschool">%s</span>'
                     '<span>%s</span></div>' % (esc(v.get("cv_education_school")), esc(v.get("cv_education_years"))))
        if v.get("cv_education_degree"):
            parts.append("<div>%s</div>" % esc(v["cv_education_degree"]))
        parts.append("</div>")

    skills = str(v.get("cv_skills_soft") or "").strip()
    if skills:
        parts.append("<h2>SKILLS</h2>")
        skills = re.sub(r"[;\n]+", ", ", skills)
        parts.append('<div class="skills">%s</div>' % esc(skills))

    if v.get("cv_languages"):
        parts.append("<h2>LANGUAGES</h2>")
        parts.append('<div class="langs">%s</div>' % esc(v["cv_languages"]))

    parts.append("</body></html>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", default="cv__format_CLIENT")
    ap.add_argument("--app", type=int, default=89)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--docx", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, str(BASE))
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    spec = importlib.util.spec_from_file_location("pf", str(BASE / "scripts" / "pdf_fill.py"))
    pf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pf)

    vals = dict(pf.values_for(a.app, a.code) or {})
    if a.stress:
        vals.update(STRESS)
    vals = {k: ("" if val is None else str(val)) for k, val in vals.items()}
    for k in list(vals):
        if k.startswith("cv_") and re.search(r"\([^)]*[А-Яа-яЁё][^)]*\)", vals[k]):
            vals[k] = re.sub(r"\s*\([^)]*[А-Яа-яЁё][^)]*\)", "", vals[k])

    html = build_html(vals)
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "_stress" if a.stress else ""
    pdf = pathlib.Path(a.out) if a.out else (OUT / ("%s_flow%s.pdf" % (a.code, suffix)))
    from services.render import render_pdf
    render_pdf(html, base_dir=str(BASE), out_path=str(pdf))

    # Word-версия: тот же HTML конвертируем в DOCX (LibreOffice), чтобы в Word документ
    # выглядел так же, как в просмотре, и тоже тёк, а не налезал.
    if a.docx:
        html_path = OUT / ("%s_flow%s.html" % (a.code, suffix))
        html_path.write_text(html, encoding="utf-8")
        subprocess.run(["soffice", "--headless", "--convert-to", "docx", "--outdir", str(OUT), str(html_path)],
                       check=False, capture_output=True, timeout=180)
        print("DOCX:", str(html_path).replace(".html", ".docx"))

    import pymupdf
    d = pymupdf.open(str(pdf))
    print("страниц:", len(d), "→", pdf)
    d[0].get_pixmap(dpi=115).save(str(pdf).replace(".pdf", ".png"))
    over = []
    for pno, pg in enumerate(d, 1):
        for blk in pg.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                if ln["bbox"][2] > pg.rect.width - 20:
                    over.append((pno, round(ln["bbox"][1], 1), " ".join(s["text"] for s in ln["spans"])[:40]))
    print("строк за правым полем:", over if over else "нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
