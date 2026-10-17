"""Пересборка банковских справок по настоящему образцу: HTML 1:1 + переменные.

Рецепт (отработан на bank_statement_3m__tbank и bank_statement_3m__sber):
  raw PDF→HTML (scripts/pdf_to_template.py) → данные клиента заменяются на {{переменные}}
  → длинные подстановки переводятся в перенос → «хвосты» удаляются → поля в БД
  получают короткие реальные значения из образца.

Запуск:
    /usr/bin/python3 scripts/rebuild_bank_statement.py <code> [--apply]
"""
from __future__ import annotations

import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
RIGHT_EDGE = 539.0

# по каждому шаблону: raw-файл, правила замен (по плоскому тексту блока) и значения полей
CONF = {
    "bank_statement_3m__sber": {
        "raw": "/tmp/sber3m_raw.html",
        "rules": [
            ("ae32271197", "{{doc_no}}", "sub"),
            ("for beliaev konstantin alekseevich.", "for {{client_name}}.", "sub"),
            ("220070******2837", "{{card_mask}}", "sub"),
            ("beliaev konstantin alekseevich", "{{client_name}}", "upper"),
            ("russian federation, republic of karelia", "{{address_live}}"),
            ("the deposit balance is", "As from {{period_from}} to {{period_to}} the deposit balance is "
                                       "{{balance_rub}} rubles ({{balance_words}})."),
            ("b19289961adl 17.08.2026", "{{ref_no}} {{doc_date}}"),
        ],
        "drop": ["krasnaya st, d. 36, kv. 5", "five hundred eight rubles 00 kopeks)."],
        "values": {
            "ref_no": ("Исходящий номер банка (Ref.)", "B19289961ADL"),
            "doc_date": ("Дата документа (в строке Ref.)", "17.08.2026"),
            "doc_no": ("Номер документа банка", "ae32271197"),
            "client_name": ("ФИО клиента (латиницей, в документе печатается заглавными)", "Beliaev Konstantin Alekseevich"),
            "address_live": ("Адрес проживания клиента", "Russian Federation, Republic of Karelia, Petrozavodsk, Krasnaya St, D. 36, Kv. 5"),
            "card_mask": ("Номер карты (маска вида 1234******5678)", "220070******2837"),
            "period_from": ("Начало периода справки (дд.мм.гггг)", "17.05.2025"),
            "period_to": ("Конец периода справки (дд.мм.гггг)", "17.08.2026"),
            "balance_rub": ("Остаток на счёте, рубли", "1 235 508, 00"),
            "balance_words": ("Остаток на счёте прописью (как в банке)",
                              "one million two hundred thirty five thousand five hundred eight rubles 00 kopeks"),
        },
    },
    "bank_statement_12m__tbank": {
        "raw": "/tmp/tbank12m_raw.html",
        "rules": [
            ("b19289961adl 24.09.2026", "{{ref_no}} {{doc_date}}"),
            ("ae32271197", "{{doc_no}}", "sub"),
            ("evgenii poliakov.", "{{client_name}}.", "sub"),
            ("220070******7233", "{{card_mask}}", "sub"),
            ("evgenii poliakov", "{{client_name}}", "upper"),
            ("apartment 144, 16 vernadskogo avenue", "{{address_live}}"),
            ("the deposit balance is", "As from {{period_from}} to {{period_to}} the deposit balance is "
                                       "{{balance_rub}} rubles ({{balance_words}})."),
        ],
        "drop": ["119571, russia.", "thousand three hundred nine rubles ninety-eight kopeks)."],
        "values": {
            "ref_no": ("Исходящий номер банка (Ref.)", "B19289961ADL"),
            "doc_date": ("Дата документа (в строке Ref.)", "24.09.2026"),
            "doc_no": ("Номер документа банка", "ae32271197"),
            "client_name": ("ФИО клиента (латиницей, как в паспорте)", "Evgenii Poliakov"),
            "address_live": ("Адрес проживания клиента", "Apartment 144, 16 Vernadskogo Avenue, Moscow, 119571, Russia."),
            "card_mask": ("Номер карты (маска вида 1234******5678)", "220070******7233"),
            "period_from": ("Начало периода справки (дд.мм.гггг)", "24.09.2025"),
            "period_to": ("Конец периода справки (дд.мм.гггг)", "24.09.2026"),
            "balance_rub": ("Остаток на счёте, рубли", "7 121 309, 98"),
            "balance_words": ("Остаток на счёте прописью (как в банке)",
                              "seven million one hundred twenty one thousand three hundred nine rubles ninety-eight kopeks"),
        },
    },
}


def flat(inner: str) -> str:
    t = re.sub(r"<[^>]+>", "", inner).replace("\u00a0", " ")
    return " ".join(t.split()).lower()


def tune(html: str) -> tuple:
    n = 0

    def fix(m: re.Match) -> str:
        nonlocal n
        style, inner = m.group(1), m.group(2)
        if "{{" not in inner:
            return m.group(0)
        left = float(re.search(r"left:([\d.]+)pt", style).group(1))
        width = max(60.0, round(RIGHT_EDGE - left, 2))
        style = re.sub(r"width:[^;]+;", f"width:{width}pt;", style)
        style = re.sub(r"height:[^;]+;", "height:auto;", style)
        style = re.sub(r"white-space:[^;\"]+", "white-space:normal", style)
        for need, add in (("width:", f"width:{width}pt;"), ("height:", "height:auto;"),
                          ("white-space:", "white-space:normal;")):
            if need not in style:
                style += add
        n += 1
        return f'<div class="txt" style="{style}">{inner}</div>'

    return re.sub(r'<div class="txt" style="([^"]+)">(.*?)</div>', fix, html, flags=re.S), n


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in CONF:
        print("укажи код шаблона:", ", ".join(CONF))
        return 2
    code = sys.argv[1]
    cfg = CONF[code]
    tpl_dir = ROOT / "data/templates" / code
    raw = Path(cfg["raw"])
    if not raw.exists():
        subprocess.run(["/usr/bin/python3", str(ROOT / "scripts/pdf_to_template.py"),
                        str(tpl_dir / "example_filled.pdf"), str(raw)], check=True)
    html = raw.read_text(encoding="utf-8")

    # 1) плоские замены блоков целиком (данные бывают разбиты на несколько span)
    n_rep = 0

    def rep(m: re.Match) -> str:
        nonlocal n_rep
        style, inner = m.group(1), m.group(2)
        f = flat(inner)
        for rule in cfg["rules"]:
            key, new = rule[0], rule[1]
            mode = rule[2] if len(rule) > 2 else "block"
            if key not in f:
                continue
            if mode == "sub":
                # заменить только фрагмент, остальной текст блока сохранить
                plain = " ".join(re.sub(r"<[^>]+>", "", inner).split())
                text = re.sub(re.escape(key), new, plain, flags=re.I)
                fs = re.search(r"font-family:([^;\"]+);font-size:([\d.]+pt);color:(#[0-9A-Fa-f]{6})", inner)
                span = (f'<span style="font-family:{fs.group(1)};font-size:{fs.group(2)};'
                        f'color:{fs.group(3)}">{text}</span>') if fs else text
                n_rep += 1
                return f'<div class="txt" style="{style}">{span}</div>'
            fs = re.search(r"font-family:([^;\"]+);font-size:([\d.]+pt);color:(#[0-9A-Fa-f]{6})", inner)
            css = "text-transform:uppercase;" if mode == "upper" else ""
            span = (f'<span style="font-family:{fs.group(1)};font-size:{fs.group(2)};'
                    f'color:{fs.group(3)};{css}">{new}</span>') if fs else new
            n_rep += 1
            return f'<div class="txt" style="{style}">{span}</div>'
        return m.group(0)

    html = re.sub(r'<div class="txt" style="([^"]+)">(.*?)</div>', rep, html, flags=re.S)

    # 2) убрать «хвосты», которые теперь даёт переменная
    n_drop = 0
    for frag in cfg["drop"]:
        pat = re.compile(r'<div class="txt" style="[^"]*">(?:<span[^>]*>)*[^<]*' +
                         re.escape(frag) + r'[^<]*(?:</span>)*</div>', re.I)
        html, k = pat.subn("", html)
        n_drop += k

    html, n_wrap = tune(html)
    print("замен: %d | убрано хвостов: %d | блоков с переносом: %d" % (n_rep, n_drop, n_wrap))

    if "--apply" not in sys.argv:
        Path("/tmp/%s_new.html" % code).write_text(html, encoding="utf-8")
        print("пример: /tmp/%s_new.html (без --apply шаблон не тронут)" % code)
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(tpl_dir / "template.html", tpl_dir / f"template.html.bak_rebuild_{stamp}")
    (tpl_dir / "template.html").write_text(html, encoding="utf-8")
    print("шаблон перезаписан, слепок: template.html.bak_rebuild_%s" % stamp)

    sys.path.insert(0, str(ROOT))
    from core import db as D
    t = D.q1("SELECT id FROM templates WHERE code=?", (code,))
    n = 0
    for name, (label, default) in cfg["values"].items():
        cur = D.q1("SELECT id FROM template_variables WHERE template_id=? AND name=?", (t["id"], name))
        if cur:
            D.exec_sql("UPDATE template_variables SET label=?, default_value=? WHERE id=?",
                       (label, default, cur["id"]))
        else:
            D.exec_sql("INSERT INTO template_variables (template_id, name, label, default_value) VALUES (?,?,?,?)",
                       (t["id"], name, label, default))
        n += 1
    print("полей приведено в порядок:", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
