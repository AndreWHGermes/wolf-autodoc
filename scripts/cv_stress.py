#!/usr/bin/env python3
"""Стресс-тест резюме: длинные реальные значения переменных.

Проверяем, как каркас резюме ведёт себя, когда описание профессии, обязанности и
опыт работы приходят большими (несколько строк, много пунктов): текст должен
переноситься внутри своего блока, не залезать на соседние разделы и не уходить
за правое поле.

    cv_stress.py [code] [app_id] [--apply-html]
"""
import argparse
import importlib.util
import pathlib
import subprocess
import sys

BASE = pathlib.Path("/opt/wolf_v2")
OUT = pathlib.Path("/tmp/wordrun")
OUT.mkdir(parents=True, exist_ok=True)

# Длинные значения: реальные формулировки, которые заказчик может вписать руками.
LONG = {
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
    "cv_job1_company": (
        'LLC "PICKUP FILM PRODUCTION COMPANY", Zelenograd, Moscow, Russia | '
        "www.pickupfilm-production.ru | +7 495 123-45-67"
    ),
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
    "cv_skills_soft": (
        "production planning, budget management, crew leadership, contract negotiation, risk "
        "assessment, attention to detail, time management, teamwork, clear communication, "
        "responsibility, mentoring, conflict resolution, remote team coordination"
    ),
    "cv_languages": "Russian (Native), English (Advanced, C1), Indonesian (Basic, A2), German (Basic, A1)",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", default="cv__format_CLIENT")
    ap.add_argument("app", nargs="?", type=int, default=89)
    a = ap.parse_args()

    sys.path.insert(0, str(BASE))
    import logging
    logging.basicConfig(level=logging.WARNING)
    from services import html_frame

    pdf = OUT / ("%s_stress.pdf" % a.code)
    # Собираем напрямую каркасом: паспорт качества (frame/quality.json) для резюме ещё
    # не выдан, а проверить поведение формы на длинных значениях нужно уже сейчас.
    from services import html_frame
    from services.render import render_pdf
    m = html_frame._flow()
    vals = html_frame.values_with_frames(a.code, dict(LONG), a.app)
    layout = m.build_layout(a.code, dict(vals))
    html = m.render_html(a.code, layout)
    render_pdf(html, base_dir=str(BASE / "data" / "templates" / a.code / "frame"), out_path=str(pdf))
    ok = True
    pr = m.problems_of(layout["blocks"])
    if pr:
        print("замечания каркаса:", "; ".join(pr)[:300])
    print("сборка:", "ок" if ok else "не удалось", "→", pdf)
    if not ok:
        return 1

    png = OUT / ("%s_stress.png" % a.code)
    import pymupdf
    d = pymupdf.open(str(pdf))
    print("страниц:", len(d))
    d[0].get_pixmap(dpi=115).save(str(png))
    over = []
    for pno, pg in enumerate(d, 1):
        for blk in pg.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                if ln["bbox"][2] > pg.rect.width - 20:
                    over.append((pno, round(ln["bbox"][1], 1), round(ln["bbox"][2], 1),
                                 " ".join(s["text"] for s in ln["spans"])[:40]))
    print("строк за правым полем:", over if over else "нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
