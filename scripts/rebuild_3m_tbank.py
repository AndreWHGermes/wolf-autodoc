"""Документ №1 (Банковская справка 3 мес., Т-Банк): пересборка HTML по оригиналу.

Поломки старого шаблона (он же «текст прыгает друг на друга»):
  - {{ client_name }}{{ address_live }} склеены в один блок 11pt — наложение;
  - всего 15 блоков вместо 26: потеряны разделительная линия, вторая строка адреса,
    продолжение строки про остаток («... rubles 00 kopeks)»), строка с ФИО в тексте;
  - кегли 7.65/7.92/9.12/11.04 вместо канонических 8/8.5/9/10 (старый масштаб 595.92pt);
  - координаты сдвинуты (Ref 145.71 vs 147.06, подпись 625.35 vs 614.99 и т.д.);
  - метки записаны с пробелами внутри {{ ... }}.

Что делает скрипт: берёт HTML, собранный из НАСТОЯЩЕГО эталона (pdf_to_template.py),
подменяет данные клиента на переменные системы, приводит стили переносимых блоков
к норме и записывает template.html. Эталон (example_filled.pdf) не трогается.
"""
from __future__ import annotations

import re
import shutil
import sys
import datetime
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
TPL = ROOT / "data/templates/bank_statement_3m__tbank"
RAW = Path("/tmp/tpl3m_raw.html")

# значения из настоящего эталона → переменные системы
REPLACE = [
    ("B19289961ADL 19.07.2026 ", "{{ref_no}} {{doc_date}}"),
    ("ae32271197", "{{doc_no}}"),
    ("Bodrov Aleksandr Aleksandrovich", "{{client_name}}"),
    ("9206******9432", "{{card_mask}}"),
]

# блоки, у которых текст длиннее исходного (переменная) — в перенос по правому полю
WRAP = ["{{address_live}}", "As from {{period_from}}", "{{doc_no}}", "{{client_name}}",
        "{{ref_no}}"]
RIGHT_EDGE = 539.0  # правый край полосы набора, pt


def tune(html: str) -> tuple[str, int]:
    """Переносимые блоки: white-space:normal + ширина до правого края + height:auto."""
    changed = 0

    def fix(m: re.Match) -> str:
        nonlocal changed
        style, inner = m.group(1), m.group(2)
        flat = re.sub(r"<[^>]+>", "", inner)
        if not any(w in flat for w in WRAP):
            return m.group(0)
        left = float(re.search(r"left:([\d.]+)pt", style).group(1))
        width = max(60.0, round(RIGHT_EDGE - left, 2))
        style = re.sub(r"width:[^;]+;", f"width:{width}pt;", style)
        style = re.sub(r"height:[^;]+;", "height:auto;", style)
        style = re.sub(r"white-space:[^;\"]+", "white-space:normal", style)
        if "width:" not in style:
            style += f"width:{width}pt;"
        if "height:" not in style:
            style += "height:auto;"
        if "white-space:" not in style:
            style += "white-space:normal;"
        if "{{address_live}}" in flat:
            # в эталоне первая строка адреса набрана 9pt (вторая — 8pt); берём 9pt
            inner = re.sub(r"font-size:[\d.]+pt", "font-size:9.00pt", inner)
        changed += 1
        return f'<div class="txt" style="{style}">{inner}</div>'

    html = re.sub(r'<div class="txt" style="([^"]+)">(.*?)</div>', fix, html, flags=re.S)
    return html, changed


def replace_blocks(html: str) -> tuple[str, int]:
    """Замены внутри блоков: данные эталона могут быть разбиты на несколько спанов,
    поэтому ищем по «плоскому» тексту блока и подменяем содержимое целиком."""
    rules = [
        (lambda f: "Bodrov Aleksandr Aleksandrovich" in f and f.strip().endswith("."),
         "{{client_name}}."),
        (lambda f: "354375" in f and "Adlerskii" in f, "{{address_live}}"),
        (lambda f: "deposit balance is" in f and "1 730 400,00" in f,
         "As from {{period_from}} to {{period_to}} the deposit balance is {{balance_rub}} "
         "rubles ({{balance_words}})."),
    ]
    n = 0

    def fix(m: re.Match) -> str:
        nonlocal n
        style, inner = m.group(1), m.group(2)
        flat = " ".join(re.sub(r"<[^>]+>", "", inner).split())
        for pred, new in rules:
            if pred(flat):
                # сохраняем шрифт исходного спана, меняем только текст
                fs = re.search(r"font-family:([^;\"]+);font-size:([\d.]+pt);color:(#[0-9A-Fa-f]{6})", inner)
                if fs:
                    span = (f'<span style="font-family:{fs.group(1)};font-size:{fs.group(2)};'
                            f'color:{fs.group(3)}">{new}</span>')
                else:
                    span = new
                n += 1
                return f'<div class="txt" style="{style}">{span}</div>'
        return m.group(0)

    html = re.sub(r'<div class="txt" style="([^"]+)">(.*?)</div>', fix, html, flags=re.S)
    return html, n


def drop_orphan_tail(html: str) -> tuple[str, int]:
    """Убирает «хвост» прописью и вторую строку адреса — их теперь даёт переменная."""
    killed = 0
    for frag in ("four hundred rubles 00 kopeks).", "D. 71, Korp. 1, Kv. 376"):
        pat = re.compile(r'<div class="txt" style="[^"]*">(?:<span[^>]*>)*\s*' +
                         re.escape(frag) + r'\s*(?:</span>)*</div>')
        html, n = pat.subn("", html)
        killed += n
    return html, killed


def main() -> int:
    if not RAW.exists():
        print("нет исходника", RAW, "— сначала прогнать pdf_to_template.py по эталону")
        return 2
    html = RAW.read_text(encoding="utf-8")
    html, n_blk = replace_blocks(html)
    n_rep = 0
    for old, new in REPLACE:
        if old in html:
            html = html.replace(old, new)
            n_rep += 1
        else:
            print("  ! не найдено в исходнике:", old[:60])
    html, n_drop = drop_orphan_tail(html)
    html, n_wrap = tune(html)
    print("блоков переписано: %d | замен: %d | убрано хвостов: %d | переносимых блоков: %d"
          % (n_blk, n_rep, n_drop, n_wrap))
    if "--apply" not in sys.argv:
        Path("/tmp/tpl3m_new.html").write_text(html, encoding="utf-8")
        print("пример записан в /tmp/tpl3m_new.html (без --apply шаблон не тронут)")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(TPL / "template.html", TPL / f"template.html.bak_rebuild_{stamp}")
    (TPL / "template.html").write_text(html, encoding="utf-8")
    (TPL / "example_filled.pdf")  # эталон не трогаем
    print("шаблон перезаписан, слепок: template.html.bak_rebuild_%s" % stamp)
    # чистка переменных в БД: подписи и значения по умолчанию под форму
    sys.path.insert(0, str(ROOT))
    from core import db as D
    t = D.q1("SELECT id FROM templates WHERE code='bank_statement_3m__tbank'")
    fixes = {
        "ref_no": ("Исходящий номер банка (Ref.)", "B19289961ADL"),
        "doc_date": ("Дата документа (в строке Ref.)", ""),
        "doc_no": ("Номер документа банка", ""),
        "client_name": ("ФИО клиента (латиницей, как в паспорте)", ""),
        "address_live": ("Адрес проживания клиента", ""),
        "card_mask": ("Номер карты (маска вида 1234******5678)", ""),
        "period_from": ("Начало периода справки (дд.мм.гггг)", ""),
        "period_to": ("Конец периода справки (дд.мм.гггг)", ""),
        "balance_rub": ("Остаток на счёте, рубли", ""),
        "balance_words": ("Остаток на счёте прописью (как в банке)", ""),
    }
    n = 0
    for name, (label, default) in fixes.items():
        cur = D.q1("SELECT id, label, default_value FROM template_variables WHERE template_id=? AND name=?",
                   (t["id"], name))
        if cur:
            D.exec_sql("UPDATE template_variables SET label=?, default_value=? WHERE id=?",
                       (label, default, cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_variables (template_id, name, label, default_value) VALUES (?,?,?,?)",
                       (t["id"], name, label, default))
        n += 1
    print("переменных приведено в порядок:", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
