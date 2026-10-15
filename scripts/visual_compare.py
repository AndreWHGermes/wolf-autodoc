"""Визуальная сверка: оригинальный пример против нашей сборки, страница к странице.

Для каждого документа собирает картинку: слева — оригинальный заполненный пример,
справа — то, что собирает система (штатный render.generate по самой наполненной заявке).
Картинки кладутся в /tmp/visual/<код>.png — их смотрим глазами.

Запуск: python3 scripts/visual_compare.py [коды...]
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'templates'
OUT = Path('/tmp/visual')


def best_application(con, template_id):
    return con.execute("""SELECT a.id FROM applications a
                          JOIN product_documents pd ON pd.product_id=a.product_id
                          LEFT JOIN clients c ON c.id=a.client_id
                          WHERE pd.template_id=?
                          ORDER BY (CASE WHEN COALESCE(c.passport_number,'')<>'' THEN 1 ELSE 0 END
                                  + CASE WHEN COALESCE(c.address_live,'')<>'' THEN 1 ELSE 0 END
                                  + CASE WHEN COALESCE(c.balance_rub,'')<>'' THEN 1 ELSE 0 END
                                  + CASE WHEN COALESCE(c.position,'')<>'' THEN 1 ELSE 0 END) DESC,
                                   a.id DESC LIMIT 1""", (template_id,)).fetchone()


def page_png(pdf: Path, tag: str, dpi=105):
    import pymupdf
    d = pymupdf.open(str(pdf))
    pix = d[0].get_pixmap(dpi=dpi)
    f = OUT / ('%s.png' % tag)
    pix.save(str(f))
    return f


def side_by_side(a: Path, b: Path, out: Path, label_a: str, label_b: str):
    from PIL import Image, ImageDraw, ImageFont
    ia, ib = Image.open(a), Image.open(b)
    h = max(ia.height, ib.height) + 30
    canvas = Image.new('RGB', (ia.width + ib.width + 24, h), 'white')
    canvas.paste(ia, (0, 30))
    canvas.paste(ib, (ia.width + 24, 30))
    dr = ImageDraw.Draw(canvas)
    font = None
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'):
        try:
            font = ImageFont.truetype(path, 14)
            break
        except Exception:  # noqa: BLE001
            continue
    dr.text((8, 8), label_a, fill='black', font=font)
    dr.text((ia.width + 32, 8), label_b, fill='black', font=font)
    canvas.save(out)
    return out


def main(argv) -> int:
    from services import render
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    codes = [a for a in argv if not a.startswith('-')]
    rows = con.execute("""SELECT id, code, doc_index FROM templates
                          WHERE COALESCE(status,'ok') NOT IN ('merged','hidden')
                          ORDER BY COALESCE(doc_index,999)""").fetchall()
    made = []
    for t in rows:
        if codes and t['code'] not in codes:
            continue
        sample = TPL / t['code'] / 'example_filled.pdf'
        if not sample.is_file():
            print('%-38s нет примера — пропуск' % t['code'])
            continue
        pick = best_application(con, t['id'])
        if not pick:
            print('%-38s нет заявки с данными — пропуск' % t['code'])
            continue
        try:
            res = render.generate(pick['id'], t['id'])
        except Exception as e:  # noqa: BLE001
            print('%-38s сборка упала: %s' % (t['code'], str(e)[:80]))
            continue
        ours = Path(str(res.get('pdf_path') or ''))
        if not ours.is_file() and ours.with_suffix('.pdf').is_file():
            ours = ours.with_suffix('.pdf')
        if not ours.is_file():
            print('%-38s PDF не создан' % t['code'])
            continue
        f = side_by_side(page_png(sample, t['code'] + '_sample'),
                         page_png(ours, t['code'] + '_ours'),
                         OUT / (t['code'] + '.png'),
                         'ОРИГИНАЛ (пример)', 'НАША СБОРКА (заявка №%s)' % pick['id'])
        made.append(str(f))
        print('%-38s %s' % (t['code'], f))
    print('\nвсего сравнений:', len(made))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
