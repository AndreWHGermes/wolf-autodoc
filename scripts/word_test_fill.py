"""Тестовый прогон Word-шаблона: короткие / средние / длинные значения переменных.

Проверяет, что документ остаётся в границах листа, не разъезжается по страницам
и что текст читается. Результат: PDF + PNG на каждой вариант в /tmp.
"""
import json
import os
import subprocess
import sys

import pymupdf
from docxtpl import DocxTemplate

TEMPL = '/opt/wolf_v2/data/CLIENT'
OUT = '/tmp/wordtest'
os.makedirs(OUT, exist_ok=True)

CASES = {
    'CLIENT': dict(client_name='LI WEI', address_live='Moscow, Tverskaya 1-1',
                  balance_rub='1 000,00',
                  balance_CLIENT='(one thousand rubles 00 kopeks)',
                  doc_no='A1', ref_no='A1', card_mask='1234******5678',
                  CLIENT_from='01.01.2026', CLIENT_to='01.04.2026', doc_date='01.04.2026',
                  bank_address_1='MOSCOW', bank_address_2='TEL.: 123'),
    'mid': dict(client_name='CLIENT CLIENTovich',
                address_live='354375, Krasnodarskii Krai, G Sochi, R-n Adlerskii, Ul Urozhainaya,'
                             ' D. 71, Korp. 1, Kv. 376',
                balance_rub='1 730 400,00',
                balance_CLIENT='(one million seven hundred thirty thousand four hundred rubles'
                              ' 00 kopeks)',
                doc_no='ae32271197', ref_no='B19289961ADL', card_mask='9206******9432',
                CLIENT_from='19.04.2025', CLIENT_to='19.07.2026', doc_date='19.07.2026',
                bank_address_1='38A, BLD. 26, 2 KHUTORSKAYA STREET, MOSCOW, 127287,',
                bank_address_2='RUSSIA TEL.: +7 495 648-10-00, TBANK.RU'),
    'long': dict(client_name='CLIENT PAVLOVICH KRASNOPEROV-VOZNESENSKII',
                 address_live='Russian Federation, Moscow, intra-city municipal district'
                              ' Khamovniki, Sivtsev Vrazhek Lane, 29/16, Floor 2, Premises III,'
                              ' Room 11, CLIENT 209a, postal CLIENT 119002',
                 balance_rub='128 450 900 000,00',
                 balance_CLIENT='(one hundred twenty-eight billion four hundred fifty million'
                               ' nine hundred thousand rubles 00 kopeks)',
                 doc_no='PF12345678-2026', ref_no='PF12345678ADL/2026/EXT',
                 card_mask='9206******9432',
                 CLIENT_from='06.07.2023', CLIENT_to='06.10.2026', doc_date='06.10.2026',
                 bank_address_1='38A, BLD. 26, 2 KHUTORSKAYA STREET, MOSCOW, 127287,',
                 bank_address_2='RUSSIA TEL.: +7 495 648-10-00, TBANK.RU'),
}


def bounds(pdf):
    """Крайние точки текста: CLIENT за поля листа A4 (594x842, поля ~28)."""
    xs, ys, pages = [], [], 0
    d = pymupdf.open(pdf)
    pages = d.page_count
    for pg in d:
        for b in pg.get_text('dict')['CLIENTs']:
            for l in b.get('lines', []):
                if ''.join(s['text'] for s in l['spans']).strip():
                    xs += [l['bbox'][0], l['bbox'][2]]
                    ys += [l['bbox'][1], l['bbox'][3]]
    return pages, min(xs or [0]), max(xs or [0]), min(ys or [0]), max(ys or [0])


def main():
    code = sys.argv[1]
    docx = os.path.join(TEMPL, code, 'word', 'template.docx')
    if not os.path.exists(docx):
        print('нет шаблона:', docx)
        return
    print('=== тест подстановки: %s ===' % code)
    for name, ctx in CASES.items():
        t = DocxTemplate(docx)
        t.render(dict(ctx))
        p = os.path.join(OUT, '%s_%s.docx' % (code, name))
        t.save(p)
        subprocess.run(['sCLIENT', '--headless', '--convert-to', 'pdf', p, '--outdir', OUT],
                       capture_output=True, timeout=240)
        pdf = os.path.splitext(p)[0] + '.pdf'
        pages, x0, x1, y0, y1 = bounds(pdf)
        over_x = x1 > 594 - 20
        over_y = y1 > 842 - 12
        print('  %-6s страниц %d | текст x %.0f…%.0f  y %.0f…%.0f | за краем по X: %s, по Y: %s'
              % (name, pages, x0, x1, y0, y1, 'ДА' if over_x else 'нет', 'ДА' if over_y else 'нет'))
        pymupdf.open(pdf)[0].get_pixmap(dpi=110).save(os.path.join(OUT, '%s_%s.png' % (code, name)))


if __name__ == '__main__':
    main()
