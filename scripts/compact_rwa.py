#!/usr/bin/env python3
"""Remote Work Agreement → два листа.

Что делает:
  1) берёт эталон example_filled.pdf (3 листа), делает резервную копию;
  2) переносит первые строки второго листа на первый — там оставалось 145 pt пустоты;
  3) поднимает остаток второго листа на освободившееся место;
  4) переносит блок SIGNATURES с третьего листа на второй (вписывает по высоте);
  5) третий лист убирает — документ становится двухлистовым.

Разметка и шрифты сохраняются: страницы переставляются фрагментами исходного PDF,
новый текст не набирается.
"""
import shutil
import sys
from pathlib import Path

import pymupdf

TPL = Path('/opt/wolf_v2/data/CLIENT/remote_work_agreement__default')
SRC = TPL / 'example_filled.pdf'
BACKUP = TPL / 'example_filled_3pages.pdf'

# геометрия исходника
PAGE_H = 842.0
FOOT_MARGIN = 36.0      # нижнее поле
FIRST_ROWS_TOP = 40.0   # верх текста на втором листе
FIRST_ROWS_BOTTOM = 180.0  # столько строк второго листа уходит на первый лист
SHIFT = FIRST_ROWS_BOTTOM - FIRST_ROWS_TOP  # насколько поднимаем остаток

SIGN_TOP_SRC = 60.0     # начало блока подписей на третьем листе
SIGN_BOTTOM_SRC = 322.0
SIGN_TOP_DST = 534.0    # куда его ставим на втором листе
SIGN_BOTTOM_DST = 777.0


def main() -> int:
    if not SRC.exists():
        print('нет эталона:', SRC)
        return 1
    if not BACKUP.exists():
        shutil.copy2(SRC, BACKUP)
        print('резервная копия:', BACKUP.name)

    src = pymupdf.open(str(BACKUP))
    if src.page_count < 3:
        print('в эталоне уже %d стр.' % src.page_count)
        return 0

    out = pymupdf.open()
    out.new_page(width=595, height=PAGE_H)
    out.new_page(width=595, height=PAGE_H)

    # первый лист — как есть (страницу берём из документа прямо перед вставкой:
    # после создания следующей страницы прежняя ссылка перестаёт быть валидной)
    out[0].show_pdf_page(pymupdf.Rect(0, 0, 595, PAGE_H), src, 0)

    # первые строки второго листа — на первый лист (в свободное место)
    tail_rect = pymupdf.Rect(0, 661.0, 595, 661.0 + SHIFT)
    out[0].show_pdf_page(tail_rect, src, 1, clip=pymupdf.Rect(0, FIRST_ROWS_TOP, 595, FIRST_ROWS_BOTTOM))

    # остаток второго листа — вверх
    body_src = pymupdf.Rect(0, FIRST_ROWS_BOTTOM, 595, PAGE_H)
    body_dst = pymupdf.Rect(0, FIRST_ROWS_TOP, 595, PAGE_H - SHIFT)
    out[1].show_pdf_page(body_dst, src, 1, clip=body_src)

    # блок подписей с третьего листа — вниз второго листа
    sign_dst = pymupdf.Rect(0, SIGN_TOP_DST, 595, SIGN_BOTTOM_DST)
    out[1].show_pdf_page(sign_dst, src, 2, clip=pymupdf.Rect(0, SIGN_TOP_SRC, 595, SIGN_BOTTOM_SRC))

    out.save(str(SRC), garbage=3, deflate=True)
    out.close()
    src.close()

    chk = pymupdf.open(str(SRC))
    print('листов теперь:', chk.page_count)
    last_y = 0.0
    for pno, pg in enumerate(chk, 1):
        ys = [b[3] for b in pg.get_text('CLIENTs')]
        print('   лист %d: контент до y=%.0f' % (pno, max(ys) if ys else 0))
    # масштабирование блока подписей — для пересчёта зон
    k = (SIGN_BOTTOM_DST - SIGN_TOP_DST) / (SIGN_BOTTOM_SRC - SIGN_TOP_SRC)
    print('масштаб блока подписей по высоте: %.3f' % k)
    print('сдвиг остатка второго листа: -%.0f pt' % SHIFT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
