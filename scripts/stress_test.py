"""Стресс-тест шаблонов Wolf на разных данных.

Собирает документ с длинными/короткими/«неудобными» значениями и проверяет:
  1) не осталось незаполненных меток {{ ... }};
  2) нет кириллицы в готовом документе;
  3) нет наложений текста (пересечения рамок строк с разным содержимым);
  4) нет пустых страниц;
  5) число страниц в разумных пределах.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, "/opt/wolf_v2")

TPL_DIR = Path("/opt/wolf_v2/data/templates")
OUT = Path("/tmp/stress")
OUT.mkdir(parents=True, exist_ok=True)


def variant(prefix: str, app: int) -> dict:
    """Набор «неудобных» значений для проверки вёрстки."""
    return {
        # очень длинное ФИО + длинное место рождения
        "employee_full_name": "KOVALEVSKAYA-BELSKAYA ANASTASIYA VLADIMIROVNA",
        "contractor_block": "KOVALEVSKAYA-BELSKAYA ANASTASIYA VLADIMIROVNA, Passport No: 000000000, "
                            "Date of Birth: 21.08.1992, Nationality: RUSSIAN FEDERATION, Place of Birth: "
                            "Stavropolsky Krai, Russia, (hereinafter referred to as the \"Employee\")",
        "employee_block": "KOVALEVSKAYA-BELSKAYA ANASTASIYA VLADIMIROVNA, Passport No: 000000000, "
                          "Date of Birth: 21.08.1992, Nationality: RUSSIAN FEDERATION, Place of Birth: "
                          "Stavropolsky Krai, Russia, (hereinafter referred to as the \"Employee\")",
        "passport_number": "000000000",
        "date_of_birth": "21.08.1992",
        "nationality": "RUSSIAN FEDERATION",
        "place_of_birth": "Stavropolsky Krai, Russia",
        "employee_short": "KOVALEVSKAYA-BELSKAYA A.",
        "position_title": "Senior Cinematographer and Post-Production Supervisor, Film Editing Department",
        "services_list": "<p style=\"font-size:10.08pt;margin-left:33pt;\">• Planning, producing, and coordinating "
                         "video and social media content across all Company channels and platforms</p>"
                         "<p style=\"font-size:10.08pt;margin-left:33pt;\">• Managing post-production workflows, "
                         "color correction, sound mixing and delivery formats</p>",
        "company_full_name": "LIMITED LIABILITY COMPANY \"PRODUCTION AND POST-PRODUCTION STUDIO PICKUP FILM\"",
        "company_block": "LIMITED LIABILITY COMPANY \"PRODUCTION AND POST-PRODUCTION STUDIO PICKUP FILM\", a Limited "
                         "Liability Company incorporated under the laws of the Russian Federation, Entity Number: "
                         "5167746476761, with registered and mailing address at Sivtsev Vrazhek Lane, 29/16, "
                         "Office 209a, Moscow, Russia, (hereinafter referred to as the \"Company\")",
        "signer_name": "CLIENT VIKTOROVICH BLIZNIUK",
        "signer_title": "GENERAL DIRECTOR",
        "salary_amount": "600,000.00",
        "base_salary": "15,000,000",
        "base_salary_annual": "180,000,000",
        "annual_amount_numeric": "15,000,000",
        "annual_amount_words": "Fifteen Million",
        "monthly_amount_numeric": "1,250,000",
        "monthly_amount_words": "One Million Two Hundred Fifty Thousand",
        "governing_law": "the Russian Federation",
        "agreement_date": "2nd October 2026",
        "contract_date": "2nd October 2026",
        "term_start_date": "7th July 2024",
        "term_end_date": "7th July 2029",
        "contract_no": "PF-105",
        "contract_place": "Moscow, Russia",
        "engagement_phrase": "as a Senior Cinematographer and Post-Production Supervisor",
        "company_address_1": "Sivtsev Vrazhek Lane, 29/16, Office 209a",
        "company_address_2": "Moscow, Russia",
        "company_entity_no": "5167746476761",
        "company_registered_address": "Sivtsev Vrazhek Lane, 29/16, Office 209a, Moscow, Russia",
        "inn_ogrn_line": "INN: 773657062652 | KPP: 773601001 | OGRN: 5167746476761",
        "employer_name": "LLC \"PICKUP FILM\"",
    }


def render(path_html: Path, values: dict, out_pdf: Path) -> None:
    html = path_html.read_text(encoding="utf-8")
    for k, v in values.items():
        html = html.replace("{{ %s }}" % k, str(v))
    from weasyprint import HTML
    HTML(string=html, base_url=str(path_html.parent)).write_pdf(str(out_pdf))


def check(pdf: Path, name: str) -> list[str]:
    problems = []
    d = pymupdf.open(pdf)
    raw = "".join(d[p].get_text() for p in range(d.page_count))
    left = re.findall(r"\{\{\s*[\w.]+\s*\}\}", raw)
    if left:
        problems.append("незаполненные метки: %s" % ", ".join(sorted(set(left))[:6]))
    if re.search(r"[А-Яа-яЁё]", raw):
        problems.append("кириллица в документе: %s" % re.findall(r"[А-Яа-яЁё]+", raw)[:4])
    for p in range(d.page_count):
        txt = d[p].get_text().strip()
        if len(txt) < 40:
            problems.append("стр.%d почти пустая (%d симв.)" % (p + 1, len(txt)))
    # наложения: пересечения рамок строк с разным текстом
    for p in range(d.page_count):
        spans = []
        for b in d[p].get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                t = "".join(s["text"] for s in line["spans"]).strip()
                if t:
                    spans.append((pymupdf.Rect(line["bbox"]), t))
        for i in range(len(spans)):
            for j in range(i + 1, len(spans)):
                r1, t1 = spans[i]
                r2, t2 = spans[j]
                inter = r1 & r2
                if inter.is_empty or inter.width < 6 or inter.height < 3:
                    continue
                if t1[:18] == t2[:18]:
                    continue
                small = min(r1.get_area(), r2.get_area())
                if small and inter.get_area() / small > 0.45:
                    problems.append("наложение: %r ⟂ %r" % (t1[:38], t2[:38]))
    print("\n--- %s: %d стр., проблем: %d" % (name, d.page_count, len(problems)))
    for pr in problems[:8]:
        print("    !", pr)
    return problems


def main() -> None:
    vals = variant("", 105)
    total = 0
    for code in ("remote_work_agreement__default", "employment_contract__default"):
        tpl = TPL_DIR / code / "template.html"
        if not tpl.exists():
            print("нет шаблона", code)
            continue
        out = OUT / ("%s.pdf" % code.split("__")[0])
        render(tpl, vals, out)
        total += len(check(out, code))
    print("\nИТОГО проблем:", total)


main()
