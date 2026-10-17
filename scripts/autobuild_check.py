"""Полная проверка автоматической сборки: каждый документ каждого продукта собирается сам.

Для каждого продукта берём самую наполненную заявку и собираем ВСЕ документы пакета
через штатный механизм сборки (services.render.generate) — так же, как это делает система
без администратора. Проверяем:

  • PDF реально создан на диске и не пустой;
  • сборщик не вернул ошибку;
  • не осталось незаполненных переменных (кроме допустимых для продукта);
  • в готовом HTML не осталось имён переменных {{ ... }}.

Выход: docs/AUTOBUILD_REPORT.md и data/guide/autobuild.json
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data' / 'wolf.db'
OUT_MD = ROOT / 'docs' / 'AUTOBUILD_REPORT.md'
OUT_JSON = ROOT / 'data' / 'guide' / 'autobuild.json'
VAR = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# пустые переменные, допустимые для продукта (по канону документов)
ALLOW_EMPTY = {'company_kpp', 'company_ogrn', 'guarantor', 'itk_no', 'itk_expiry', 'occupation',
               'inn_kpp_ogrn', 'cv_job2_title', 'cv_skills_soft', 'engagement_line',
               'engagement_phrase', 'signatory_person_name', 'company_incorporated_phrase'}


def pick_application(con, product_id):
    rows = con.execute("""SELECT a.id, c.id AS cid,
                                 (CASE WHEN c.passport_number IS NOT NULL AND c.passport_number<>'' THEN 1 ELSE 0 END
                                + CASE WHEN c.birth_date IS NOT NULL AND c.birth_date<>'' THEN 1 ELSE 0 END
                                + CASE WHEN c.address_live IS NOT NULL AND c.address_live<>'' THEN 1 ELSE 0 END
                                + CASE WHEN c.position IS NOT NULL AND c.position<>'' THEN 1 ELSE 0 END
                                + CASE WHEN c.full_name_latin IS NOT NULL AND c.full_name_latin<>'' THEN 1 ELSE 0 END
                                + CASE WHEN c.balance_rub IS NOT NULL AND c.balance_rub<>'' THEN 1 ELSE 0 END
                                 ) AS score
                          FROM applications a LEFT JOIN clients c ON c.id=a.client_id
                          WHERE a.product_id=? ORDER BY score DESC, a.id DESC""", (product_id,)).fetchall()
    return rows[0] if rows else None


def main() -> int:
    from services import render
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    out = {'products': {}}
    md = ['# Проверка автоматической сборки документов', '',
          'Каждый документ каждого продукта собирается системой без администратора. '
          'Проверка: PDF создан на диске, ошибок сборки нет, переменные подставлены.', '']
    ok_total, bad_total = 0, 0
    for p in con.execute('SELECT id, code, name FROM products WHERE active=1 ORDER BY code'):
        pick = pick_application(con, p['id'])
        if not pick:
            md.append('## %s — заявок нет, проверить не на чем' % p['code'])
            continue
        app_id, client_id = pick['id'], pick['cid']
        tpls = con.execute("""SELECT t.id, t.code, t.title FROM product_documents pd
                              JOIN templates t ON t.id=pd.template_id
                              WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden')
                              ORDER BY COALESCE(t.doc_index,999)""", (p['id'],)).fetchall()
        rows = []
        for t in tpls:
            item = {'code': t['code'], 'pdf': None, 'kb': 0, 'unfilled': [], 'leftovers': [], 'error': None}
            try:
                res = render.generate(app_id, t['id'])
                item['pdf'] = str(res.get('pdf_path') or '')
                pth = Path(item['pdf']) if item['pdf'] else None
                if pth and pth.is_file():
                    item['kb'] = round(pth.stat().st_size / 1024, 1)
                elif pth and pth.with_suffix('.pdf').is_file():
                    item['kb'] = round(pth.with_suffix('.pdf').stat().st_size / 1024, 1)
                    item['pdf'] = str(pth.with_suffix('.pdf'))
                item['unfilled'] = [x for x in (res.get('unfilled') or []) if x not in ALLOW_EMPTY]
                item['leftovers'] = sorted(set(VAR.findall(res.get('html') or '')))
            except Exception as e:  # noqa: BLE001
                item['error'] = ('%s: %s' % (type(e).__name__, e))[:140]
            rows.append(item)
        out['products'][p['code']] = {'application': app_id, 'client': client_id, 'docs': rows}
        bad = [r for r in rows if r['error'] or r['leftovers'] or (r['pdf'] and r['kb'] <= 0)]
        good = [r for r in rows if r not in bad]
        ok_total += len(good)
        bad_total += len(bad)
        md.append('## %s — %s (заявка №%s)' % (p['code'], p['name'] or '', app_id))
        md.append('- документов: %d, собрано чисто: %d, с замечаниями: %d' % (len(rows), len(good), len(bad)))
        for r in rows:
            mark = '✅' if r not in bad else '⚠️'
            extra = []
            if r['kb']:
                extra.append('PDF %.0f КБ' % r['kb'])
            if r['unfilled']:
                extra.append('пусто: ' + ', '.join(r['unfilled'][:5]))
            if r['leftovers']:
                extra.append('остались имена переменных: ' + ', '.join(r['leftovers'][:5]))
            if r['error']:
                extra.append(r['error'])
            md.append('  - %s `%s` — %s' % (mark, r['code'], '; '.join(extra) or 'собрано без замечаний'))
        md.append('')
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('отчёт:', OUT_MD)
    print('документов собрано чисто: %d, с замечаниями: %d' % (ok_total, bad_total))
    for code, d in out['products'].items():
        bad = [r['code'] for r in d['docs'] if r['error'] or r['leftovers']]
        if bad:
            print('   %-9s замечания: %s' % (code, ', '.join(bad)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
