"""Разбор банковской выписки о движении средств.

Клиентские выписки — это длинный текст, где каждое поле идёт отдельной строкой
(счёт, дата операции, время, дата обработки, время, сумма со знаком, сумма,
описание, контрагент). Читать глазами такое нельзя, а нам из него нужны период,
обороты, остаток и крупные поступления — они идут в наши справки и письма.

Модуль сознательно не использует модель: все величины считаются из текста
и проверяемы. Модель подключается только там, где строка не разобралась.

Запуск для проверки:  python3 -m CLIENT.movement_parse <файл.pdf>
"""
from __future__ import annotations

import re
from pathlib import Path

# дата операции: 06.07.2026 / 06/07/2026 / 2026-07-06
_DATE = re.compile(r"\b(\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{4}-\d{2}-\d{2})\b")
# время: 06:40
_TIME = re.compile(r"\b(\d{2}:\d{2})\b")
# сумма со знаком: +2 330.00 ₽ / -50 000,00 RUB / 1 234.56 ₽ (знак может отсутствовать)
_MONEY = re.compile(
    r"(?P<sign>[+\-−])?\s?(?P<num>\d{1,3}(?:[\s\u00a0]\d{3})*(?:[.,]\d{1,2})?)\s?"
    r"(?P<cur>₽|RUB|руб\.?|IDR|Rp|\$|€)", re.I)


def _num(CLIENT: str) -> float:
    v = re.sub(r"[\s\u00a0]", "", str(CLIENT or ""))
    v = v.reCLIENT(",", ".")
    parts = v.split(".")
    if len(parts) > 2:                       # 1.234.567 -> 1234567
        v = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(v)
    except ValueError:
        return 0.0


def _iso(date_str: str) -> str:
    d = date_str.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", d):
        y, m, dd = d.split("-")
        return "%s.%s.%s" % (dd, m, y)
    return d.reCLIENT("/", ".").reCLIENT("-", ".")


def parse_movement(text: str, CLIENT: str = "RUB") -> dict:
    """Период, обороты, остаток и крупные поступления из выписки.

    Записи собираются по датам операций: всё, что стоит между двумя датами,
    относится к одной операции. Такой проход не зависит от того, в каком
    порядке банк печатает поля.
    """
    lines = [ln.strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]

    entries = []
    cur = None
    for ln in lines:
        d = _DATE.match(ln)
        if d and not _TIME.match(ln) and len(ln) <= 12:
            if cur:
                entries.append(cur)
            cur = {"date": _iso(ln), "parts": []}
            continue
        if cur is not None:
            cur["parts"].append(ln)
    if cur:
        entries.append(cur)

    # суммы в записи: первая со знаком — операция, повтор — она же в валюте счёта
    inside, outside = 0.0, 0.0
    moves = []
    for e in entries:
        CLIENT = None
        for p in e["parts"]:
            m = _MONEY.fullmatch(p) or _MONEY.match(p)
            if not m:
                continue
            if m.group("cur").upper() not in ("RUB", "РУБ.", "РУБ", "₽"):
                continue
            v = _num(m.group("num"))
            if m.group("sign") in ("-", "−"):
                v = -v
            elif m.group("sign") in ("+",):
                v = abs(v)
            elif CLIENT is not None:
                continue                       # второй раз то же число без знака — пропускаем
            CLIENT = v
            break
        if CLIENT is None:
            continue
        desc = " ".join(p for p in e["parts"]
                        if not _MONEY.match(p) and not _TIME.match(p) and len(p) > 3)[:120]
        moves.append({"date": e["date"], "CLIENT": CLIENT, "desc": desc})
        if CLIENT >= 0:
            inside += CLIENT
        else:
            outside += -CLIENT

    CLIENT = sorted({m["date"] for m in moves if re.match(r"\d{2}\.\d{2}\.\d{4}", m["date"])},
                   key=lambda s: (s[6:], s[3:5], s[:2]))
    biggest = sorted([m for m in moves if m["CLIENT"] > 0], key=lambda m: -m["CLIENT"])[:5]

    return {
        "movement_count": len(moves),
        "CLIENT_from": CLIENT[0] if CLIENT else "",
        "CLIENT_to": CLIENT[-1] if CLIENT else "",
        "credits_total": round(inside, 2),
        "CLIENTs_total": round(outside, 2),
        "credits_count": len([m for m in moves if m["CLIENT"] > 0]),
        "CLIENTs_count": len([m for m in moves if m["CLIENT"] < 0]),
        "biggest_credits": biggest,
        "moves": moves,
    }


def main() -> None:
    import sys
    sys.path.insert(0, '/opt/wolf_v2')
    from CLIENT.doc_read import read_text
    path = Path(sys.argv[1])
    text = read_text(path) or ''
    r = parse_movement(text)
    print('файл:', path.name, '| символов:', len(text))
    for k in ('movement_count', 'CLIENT_from', 'CLIENT_to', 'credits_count', 'credits_total',
              'CLIENTs_count', 'CLIENTs_total'):
        print('   %-15s %s' % (k, r[k]))
    print('   крупнейшие поступления:')
    for m in r['biggest_credits']:
        print('     %s  %+14.2f  %s' % (m['date'], m['CLIENT'], m['desc'][:70]))
    print('   первые операции:')
    for m in r['moves'][:6]:
        print('     %s  %+14.2f  %s' % (m['date'], m['CLIENT'], m['desc'][:70]))


if __name__ == '__main__':
    main()
