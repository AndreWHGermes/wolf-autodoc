#!/usr/bin/env python3
"""Разметка зон резюме (cv__format_*) по строкам эталона.

Резюме — одностраничный бланк: имя, должность, личные данные, summary в три строки,
опыт работы, образование, навыки, языки. Зоны задаются по координатам строк эталона;
многострочные поля (summary, обязанности, навыки) помечаются как зона на несколько
строк — тогда полоса целиком вырезается в подложке и наш текст печатается один раз.

    map_cv_fields.py [code] [--apply]
"""
import argparse
import json
import os
import pathlib

ROOT = pathlib.Path("/opt/wolf_v2")

# (переменная, [x0, y0, x1, y1], сколько строк эталона покрывает)
ZONES = [
    ("cv_name",            [243.16, 49.0, 380.0, 68.0], 1),
    ("cv_profession",      [251.70, 71.5, 560.0, 84.0], 1),
    ("cv_place_of_birth",  [264.00, 86.6, 360.0, 99.0], 1),
    ("cv_date_of_birth",   [171.00, 100.0, 230.0, 112.5], 1),
    ("cv_nationality",     [282.00, 100.0, 380.0, 112.5], 1),
    ("cv_passport_no",     [455.00, 100.0, 560.0, 112.5], 1),
    ("cv_summary",         [47.50, 142.9, 560.0, 179.0], 3),
    ("cv_job1_title",      [47.50, 210.6, 300.0, 223.0], 1),
    ("cv_job1_period",     [400.00, 210.6, 560.0, 223.0], 1),
    ("cv_job1_company",    [47.50, 223.4, 560.0, 236.0], 1),
    ("cv_job1_bullets",    [47.50, 237.8, 560.0, 326.0], 7),
    ("cv_education_school", [47.50, 357.3, 480.0, 370.0], 1),
    ("cv_education_years", [480.00, 357.3, 560.0, 370.0], 1),
    ("cv_education_degree", [47.50, 370.0, 400.0, 383.0], 1),
    ("cv_skills_soft",     [47.50, 412.7, 560.0, 480.0], 5),
    ("cv_languages",       [47.50, 509.7, 400.0, 522.5], 1),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", default="cv__format_CLIENT")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    tdir = ROOT / "data" / "templates" / a.code
    fp = tdir / "fields.json"
    fields = json.loads(fp.read_text(encoding="utf-8"))
    zones = fields["zones"] if isinstance(fields, dict) else fields

    known = {z.get("var") for z in zones}
    for var, bbox, rows in ZONES:
        for z in zones:
            if z.get("var") == var:
                z["bbox"] = bbox
                break
        else:
            zones.append({"var": var, "bbox": bbox})
        print("   %-22s %s (%d стр.)%s" % (var, bbox, rows, "" if var in known else "  ← новая"))

    if a.apply:
        fp.write_text(json.dumps(fields, ensure_ascii=False, indent=1), encoding="utf-8")
        print("записано:", fp)


if __name__ == "__main__":
    main()
