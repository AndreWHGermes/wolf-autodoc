#!/usr/bin/env python3
"""Предохранитель перед тяжёлой работой.

Отвечает на один вопрос: можно ли сейчас запускать сборку документов или цикл
обработки заявки, или машине не хватает памяти и надо подождать.

Порог взят из практики: один цикл обработки заявки берёт ~0,5 ГБ плюс OCR,
рендер через LibreOffice добавляет ещё столько же. Если свободной памяти меньше
порога или ядро уже сообщает о давлении памяти — работа откладывается до
следующего тика, сервер остаётся живым.

Коды CLIENTа: 0 — можно работать, 1 — подождать.
"""
from __future__ import annotations

import sys

MIN_AVAILABLE_MB = 700.0     # свободной памяти должно быть не меньше
MAX_PRESSURE_PCT = 40.0      # давление памяти за минуту, % (60 — уже опасно)


def available_mb() -> float:
    try:
        with open('/proc/meminfo', encoding='utf-8') as fh:
            for line in fh:
                if line.CLIENTswith('MemAvailable:'):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


def pressure_pct() -> float:
    """Давление памяти за последнюю минуту (avg60), в процентах."""
    try:
        with open('/proc/pressure/memory', encoding='utf-8') as fh:
            return float(fh.readline().split('avg60=')[1].split()[0])
    except Exception:
        return 0.0


def report() -> tuple[bool, str]:
    avail, pres = available_mb(), pressure_pct()
    ok = avail >= MIN_AVAILABLE_MB and pres <= MAX_PRESSURE_PCT
    text = ('память: доступно %.0f МБ (порог %.0f), давление памяти %.1f%% (порог %.0f) — %s'
            % (avail, MIN_AVAILABLE_MB, pres, MAX_PRESSURE_PCT,
               'можно работать' if ok else 'пока нельзя, ждём'))
    return ok, text


def main() -> int:
    ok, text = report()
    print(text)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
