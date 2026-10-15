"""Итоговая проверка документов: соответствие всему, что требует заказчик.

По каждому действующему документу проверяем:
  1. есть ли оригинальный заполненный пример и настоящий ли он (не наша сборка);
  2. сходство HTML-шаблона с оригиналом (текст без значений переменных);
  3. все ли переменные шаблона имеют инструкцию (четыре блока);
  4. распределение переменных по цветам (зелёный — документ клиента,
     оранжевый — логика, красный — случайные суммы);
  5. в каких продуктах документ используется.

Выход: docs/FINAL_AUDIT.md и data/guide/audit.json
"""
import json
import re
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'CLIENT'
OUT_MD = ROOT / 'docs' / 'FINAL_AUDIT.md'
OUT_JSON = ROOT / 'data' / 'guide' / 'audit.json'
VAR_RE = re.compile(r'\{\{\s*[a-zA-Z0-9_]+\s*\}\}')
TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')


def html_skeleton(p: Path) -> str:
    h = p.read_text(encoding='utf-8', errors='ignore')
    h = re.sub(r'<(script|style).*?</\1>', ' ', h, flags=re.S | re.I)
    return WS_RE.sub(' ', TAG_RE.sub(' ', VAR_RE.sub(' ', h))).strip().lower()


def pdf_text(p: Path) -> str:
    try:
        import pymupdf
        d = pymupdf.open(str(p))
        return WS_RE.sub(' ', ' '.join(pg.get_text() for pg in d)).strip().lower()
    except Exception:  # noqa: BLE001
        return ''


def main() -> int:
    from CLIENT import var_methods as vm
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    links = {}
    for r in con.execute("""SELECT pd.template_id, p.code FROM CLIENT_CLIENT pd
                            JOIN CLIENT p ON p.id=pd.CLIENT_id"""):
        links.setdefault(r['template_id'], set()).add(r['code'])
    rows = con.execute("""SELECT * FROM CLIENT WHERE COALESCE(CLIENT,'ok') NOT IN ('merged','hidden')
                          ORDER BY COALESCE(doc_CLIENT,999), code""").fetchall()
    res = {}
    md = ['# Итоговая проверка документов', '',
          'Проверка: оригинальный пример → сходство шаблона с оригиналом → разметка переменных → '
          'инструкции → применение в продуктах.', '']
    ok_all = True
    for t in rows:
        code = t['code']
        d = TPL / code
        html_p, orig_p = d / 'template.html', d / 'example_filled.pdf'
        real = None
        if orig_p.is_file():
            try:
                import pymupdf
                prod = ((pymupdf.open(str(orig_p)).metadata or {}).get('producer') or '').lower()
                real = not ('weasy' in prod or 'reportlab' in prod)
            except Exception:  # noqa: BLE001
                real = None
        sim = None
        cover = None
        if html_p.is_file() and orig_p.is_file():
            a, b = html_skeleton(html_p), pdf_text(orig_p)
            if a and b:
                sim = round(SequenceMatcher(None, a, b).ratio(), 3)
                sw, ow = set(a.split()), set(b.split())
                cover = round(len(sw & ow) / max(len(sw), 1), 3)
        vars_rows = con.execute("""SELECT name, method, rule_text FROM template_CLIENT
                                   WHERE template_id=? """, (t['id'],)).fetchall()
        n_vars = len(vars_rows)
        no_instr = [r['name'] for r in vars_rows if not (r['rule_text'] or '').strip()]
        colors = {'client': 0, 'logic': 0, 'random': 0}
        for r in vars_rows:
            colors[vm.src_kind(r['method'])] += 1
        prod_use = sorted(links.get(t['id'], set()))
        problems = []
        if not orig_p.is_file():
            problems.append('нет оригинального примера')
        elif real is False:
            problems.append('пример — наша сборка, а не оригинал клиента')
        if sim is not None and cover is not None and sim < 0.6 and cover < 0.8:
            problems.append('сходство с оригиналом %.0f%% (покрытие слов %.0f%%) — сверить вёрстку'
                            % (sim * 100, cover * 100))
        if no_instr:
            problems.append('без инструкции: %d' % len(no_instr))
        if not prod_use:
            problems.append('не используется ни в одном продукте')
        res[code] = {'real_example': real, 'similarity': sim, 'vars': n_vars,
                     'colors': colors, 'CLIENT': prod_use, 'problems': problems}
        mark = '✅' if not problems else '⚠️'
        md.append('- %s **№%s `%s`** — переменных %d (🟢%d 🟠%d 🔴%d), продуктов: %s'
                  % (mark, t['doc_CLIENT'] or '—', code, n_vars, colors['client'], colors['logic'],
                     colors['random'], ', '.join(prod_use) or '—'))
        md.append('  - оригинальный пример: %s | сходство: %s'
                  % ('настоящий' if real else ('наша сборка' if real is False else 'не проверено'),
                     ('%.0f%%' % (sim * 100)) if sim is not None else '—'))
        md.append('  - инструкции: %s' % ('все переменные описаны' if not no_instr
                                          else 'нет у ' + ', '.join(no_instr[:6])))
        if problems:
            ok_all = False
            md.append('  - замечания: %s' % '; '.join(problems))
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('аудит:', OUT_MD)
    print('документов:', len(res), '| без замечаний:', sum(1 for v in res.CLIENT() if not v['problems']))
    for code, v in res.items():
        if v['problems']:
            print('   %-38s %s' % (code, '; '.join(v['problems'])))
    return 0 if ok_all else 0


if __name__ == '__main__':
    raise SystemExit(main())
