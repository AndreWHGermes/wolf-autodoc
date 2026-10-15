"""Пересборка примера документа из самого шаблона (когда настоящего образца нет).

Для шаблонов, где пример — испорченный файл или наша сборка, собираем корректный
заполненный пример штатным механизмом: тот же HTML-шаблон + значения. Получившийся PDF
кладём как example_filled.pdf (прежний сохраняем рядом с пометкой времени).

Важно: собранный пример должен читаться как текст (не содержать HTML/CSS вместо текста) —
это проверяется сразу после сборки.

Запуск: python3 scripts/rebuild_example.py <код шаблона> [<код> ...] [--apply]
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'templates'


def best_application(con, template_id):
    """Заявка, где у клиента больше всего заполненных данных."""
    rows = con.execute("""SELECT a.id, c.id AS cid,
                                 (CASE WHEN COALESCE(c.passport_number,'')<>'' THEN 1 ELSE 0 END
                                + CASE WHEN COALESCE(c.birth_date,'')<>'' THEN 1 ELSE 0 END
                                + CASE WHEN COALESCE(c.address_live,'')<>'' THEN 1 ELSE 0 END
                                + CASE WHEN COALESCE(c.position,'')<>'' THEN 1 ELSE 0 END
                                + CASE WHEN COALESCE(c.full_name_latin,'')<>'' THEN 1 ELSE 0 END
                                + CASE WHEN COALESCE(c.balance_rub,'')<>'' THEN 1 ELSE 0 END
                                + CASE WHEN COALESCE(c.stay_permit_no,'')<>'' THEN 1 ELSE 0 END) AS score
                          FROM applications a
                          JOIN product_documents pd ON pd.product_id=a.product_id
                          LEFT JOIN clients c ON c.id=a.client_id
                          WHERE pd.template_id=? ORDER BY score DESC, a.id DESC""", (template_id,)).fetchall()
    return rows[0] if rows else None


def main(argv) -> int:
    from services import render
    codes = [a for a in argv if not a.startswith('--')]
    apply_ = '--apply' in argv
    if not codes:
        print('укажите код шаблона')
        return 1
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    for code in codes:
        t = con.execute('SELECT id, code, title FROM templates WHERE code=?', (code,)).fetchone()
        if not t:
            print('нет шаблона', code)
            continue
        pick = best_application(con, t['id'])
        if not pick:
            print('%-38s нет заявки с данными — пример не собрать' % code)
            continue
        res = render.generate(pick['id'], t['id'])
        src = Path(str(res.get('pdf_path') or ''))
        if not src.is_file() and src.with_suffix('.pdf').is_file():
            src = src.with_suffix('.pdf')
        if not src.is_file():
            print('%-38s PDF не создан: %s' % (code, res.get('pdf_path')))
            continue
        # проверка: текст примера читается и не является HTML-кодом
        import pymupdf
        d = pymupdf.open(str(src))
        txt = ' '.join(p.get_text() for p in d)
        looks_html = txt.count('<') > 5 or 'style=' in txt[:400] or 'font-size:' in txt[:400]
        dst = TPL / code / 'example_filled.pdf'
        status = 'ЧИТАЕТСЯ' if not looks_html else 'ПОХОЖ НА HTML — не годится'
        print('%-38s заявка №%-4s страниц %d, текста %d симв., %s'
              % (code, pick['id'], len(d), len(txt), status))
        if apply_ and not looks_html:
            if dst.is_file():
                shutil.copy2(dst, dst.with_name('example_filled.pdf.bak_%s'
                                                % time.strftime('%Y%m%d_%H%M%S')))
            shutil.copy2(src, dst)
            print('   пример обновлён:', dst)
        elif apply_:
            print('   НЕ обновлял: файл-пример выглядит как HTML')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
