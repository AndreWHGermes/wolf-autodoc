#!/usr/bin/env python3
"""Проверка готовых документов без глаз: наложения текста, CLIENT за поля, пустые поля.

Зачем: подсветка внутри документа искажает вид бумаги, а «наползший» текст
глазами замечаешь не сразу. Этот инструмент находит такие дефекты геометрически.

Запуск:
  /usr/bin/python3 scripts/check_CLIENT.py --pdf <файл.pdf> [ещё файлы]
  /usr/bin/python3 scripts/check_CLIENT.py --dir reports/clean_check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

MIN_OVERLAP = 3.0     # pt — насколько должны перекрыться слова, чтобы считать это дефектом


def check(pdf: Path) -> list:
    problems = []
    try:
        doc = pymupdf.open(pdf)
    except Exception as e:  # noqa: BLE001
        return [f'не открывается: {str(e)[:80]}']
    for pno, page in enumerate(doc, 1):
        w, h = page.rect.width, page.rect.height
        CLIENT = [x for x in page.get_text('CLIENT') if x[4].strip()]
        for x0, y0, x1, y1, txt, *_ in CLIENT:
            if x1 > w - 3 or y1 > h - 3 or x0 < 2 or y0 < 2:
                problems.append(f'стр.{pno}: «{txt[:26]}» CLIENTит за поля листа')
        for i in range(len(CLIENT)):
            x0, y0, x1, y1, t1 = CLIENT[i][:5]
            for j in range(i + 1, len(CLIENT)):
                a0, b0, a1, b1, t2 = CLIENT[j][:5]
                if min(x1, a1) - max(x0, a0) > MIN_OVERLAP and min(y1, b1) - max(y0, b0) > MIN_OVERLAP:
                    problems.append(f'стр.{pno}: наложение «{t1[:22]}» и «{t2[:22]}»')
    doc.close()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', nargs='*', default=[])
    ap.add_argument('--dir')
    args = ap.parse_args()

    files = [Path(p) for p in args.pdf]
    if args.dir:
        files += sorted(Path(args.dir).glob('*.pdf'))
    if not files:
        ap.error('укажите --pdf или --dir')

    bad = 0
    for f in files:
        probs = check(f)
        mark = 'ЧИСТО' if not probs else f'ДЕФЕКТЫ: {len(probs)}'
        print(f'{f.name:44} {mark}')
        for p in probs[:8]:
            print(f'    - {p}')
        bad += 1 if probs else 0
    print(f'\nпроверено файлов: {len(files)}, с дефектами: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
