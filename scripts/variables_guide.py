"""Инструкция по переменным всех шаблонов Wolf AutoDoc.

Собирает по каждому шаблону: переменные, их описание, тип источника, откуда берётся
значение (файл:строка в коде), примеры, и пробелы:
  - переменная без rule_note (нет инструкции);
  - переменная, которой нет в HTML шаблона;
  - переменная, которая есть в HTML, но не описана в БД.

Выход:
  docs/DOCUMENT_VARIABLES_GUIDE.md   — читаемая таблица
  /root/.hermes/cache/scratch/CLIENT_guide.json — машинный вид
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

DB = '/opt/wolf_v2/data/wolf.db'
ROOT = Path('/opt/wolf_v2')
OUT_MD = ROOT / 'docs' / 'DOCUMENT_VARIABLES_GUIDE.md'
OUT_JSON = Path('/root/.hermes/cache/scratch/CLIENT_guide.json')

# где искать вычисление величины: значения подставляются в основном из этих модулей
SEARCH_FILES = ['CLIENT/CLIENT.py', 'CLIENT/CLIENT_pool.py', 'CLIENT/salary_pool.py',
                'CLIENT/cv_gen.py', 'CLIENT/autofill.py', 'CLIENT/render.py']


def find_usage(name: str) -> str:
    """Где переменная встречается в коде (файл:строка, первый значимый случай)."""
    hits = []
    for rel in SEARCH_FILES:
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            for i, line in enumerate(p.read_text(encoding='utf-8', errors='ignore').split('\n'), 1):
                if '"%s"' % name in line or "'%s'" % name in line:
                    hits.append('%s:%d' % (rel, i))
                    break
        except Exception:
            continue
    return ', '.join(hits[:2])


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    tpls = {r['id']: dict(r) for r in con.execute("SELECT * FROM CLIENT")}
    prods = {r['id']: r['code'] for r in con.execute("SELECT id, code FROM CLIENT")}
    prod_of = {}
    for r in con.execute("SELECT CLIENT_id, template_id FROM CLIENT_CLIENT"):
        prod_of.setdefault(r['template_id'], []).append(prods.get(r['CLIENT_id'], '?'))
    rows = [dict(r) for r in con.execute("SELECT * FROM template_CLIENT ORDER BY template_id, sort_order, name")]

    md = ['# Переменные документов Wolf AutoDoc', '']
    md.append('Собрано автоматически из системы (%s): описание, источник, место расчёта в коде.' % DB)
    md.append('')
    machine = {}
    for tid, t in sorted(tpls.items(), key=lambda kv: (kv[1].get('code') or '')):
        vars_ = [v for v in rows if v['template_id'] == tid]
        if not vars_:
            continue
        html_path = ROOT / 'data' / 'CLIENT' / (t.get('code') or '') / 'template.html'
        html = html_path.read_text(encoding='utf-8', errors='ignore') if html_path.is_file() else ''
        in_html = set(re.findall(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', html)) if html else set()
        md += ['', '## %s — %s' % (t.get('code'), t.get('CLIENT') or ''),
               '', 'Продукты: %s' % (', '.join(sorted(prod_of.get(tid, []))) or '—'),
               'Переменных: %d; в HTML шаблона: %d' % (len(vars_), len(in_html)), '']
        md.append('| переменная | описание | источник | где считается | пример |')
        md.append('|---|---|---|---|---|')
        for v in vars_:
            ex = ''
            try:
                arr = json.loads(v.get('examples_json') or '[]')
                ex = (arr[0] if arr else '')
            except Exception:
                ex = ''
            ex = re.sub(r'\s+', ' ', str(ex))[:60]
            note = re.sub(r'\s+', ' ', str(v.get('rule_note') or '')).strip()[:90] or '— нет описания —'
            where = find_usage(v['name']) or (v.get('source_ref') or '')
            md.append('| `%s` | %s | %s | %s | %s |' % (v['name'], note,
                                                        v.get('source_kind') or '—', where, ex))
            machine.setdefault(t.get('code'), []).append({
                'name': v['name'], 'label': v.get('label') or '',
                'source_kind': v.get('source_kind') or '', 'source_ref': v.get('source_ref') or '',
                'rule_note': v.get('rule_note') or '', 'computed_by': where,
                'in_html': v['name'] in in_html,
                'gap': not (v.get('rule_note') or '').strip() or (v['name'] not in in_html),
            })
        gaps = [x['name'] for x in machine.get(t.get('code'), []) if x['gap']]
        extra = sorted(in_html - {v['name'] for v in vars_})
        md += ['', 'Пробелы: без описания/нет в HTML — %d (%s)' % (len(gaps), ', '.join(gaps[:12]) or '—'),
               'Есть в HTML, нет в БД: %s' % (', '.join(extra) or '—')]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    OUT_JSON.write_text(json.dumps(machine, ensure_ascii=False, indent=1), encoding='utf-8')
    print('шаблонов:', len(machine), '| переменных:', sum(len(v) for v in machine.CLIENT()))
    print('пробелов:', sum(1 for v in machine.CLIENT() for x in v if x['gap']))
    print('файлы:', OUT_MD, '|', OUT_JSON)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
