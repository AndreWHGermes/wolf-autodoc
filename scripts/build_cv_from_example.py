"""Резюме (cv__format_CLIENT): HTML-шаблон строго по образцу, строка за строкой.

Строки образца идут сверху вниз; для каждой известно, что с ней делать: оставить как есть
(заголовки разделов), заменить на {{ переменную }} (данные клиента) или убрать (продолжения
многострочных блоков — их содержимое целиком уходит в переменную).

Запуск:
    /usr/bin/python3 scripts/build_cv_from_example.py           # показать
    /usr/bin/python3 scripts/build_cv_from_example.py --apply   # записать
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
CODE = 'cv__format_CLIENT'
BLOCK = re.compile(r'<div class="txt"\s+style="([^"]+)"[^>]*>(.*?)</div>', re.S)

# действия по строкам образца (сверху вниз): KEEP — заголовок, VAR — переменная, DROP — убрать
PLAN = [
    'VAR cv_name',
    'VAR cv_profession',
    'VAR cv_place_of_birth',
    'INLINE',                      # строка DOB | Nationality | Passport — три переменные внутри
    'KEEP',                        # PROFESSIONAL SUMMARY
    'VAR cv_summary',
    'DROP', 'DROP',
    'KEEP',                        # WORK EXPERIENCE
    'VAR cv_job1_title',
    'VAR cv_job1_period',
    'VAR cv_job1_company',
    'VAR cv_job1_bullets',
    'DROP', 'DROP', 'DROP', 'DROP', 'DROP', 'DROP',
    'KEEP',                        # EDUCATION
    'VAR cv_education_school',
    'VAR cv_education_years',
    'VAR cv_education_degree',
    'KEEP',                        # SKILLS
    'VAR cv_skills_hard',
    'DROP', 'DROP',
    'VAR cv_skills_soft',
    'DROP',
    'KEEP',                        # LANGUAGES
    'VAR cv_languages',
]

VALS = {
    'cv_summary': ('Executive Director with a degree in Business Management from Lomonosov '
                   'Moscow State University.\nExperienced in managing company operations, '
                   'business strategy, sales and team leadership. Works fully remotely and '
                   'independently for a Russian company.'),
    'cv_job1_title': 'Executive Director',
    'cv_job1_period': 'September 2025 – Present',
    'cv_job1_company': 'LLC "INGREDIENTTRADE", Zelenograd, Moscow, Russia',
    'cv_job1_bullets': ('• Managing the day-to-day operations of the Company and ensuring the '
                        'objectives.\n• Developing and implementing the Company\'s business '
                        'strategy, annual plans and budgets.\n• Overseeing sales, procurement, '
                        'supply chain and customer relations; negotiating with key partners and '
                        'suppliers.\n• Supervising staff, monitoring financial performance and '
                        'ensuring compliance with applicable laws and internal policies.'),
    'cv_education_school': 'Lomonosov Moscow State University',
    'cv_education_years': '2017 – 2022',
    'cv_education_degree': 'Business Management – Bachelor Degree',
    'cv_skills_hard': ('• Strategic planning and business development\n• Operations, sales and '
                       'supply chain management\n• Budgeting, financial planning and performance '
                       'analysis\n• MS Office, CRM systems, remote collaboration tools'),
    'cv_skills_soft': '• Team leadership and negotiations',
    'cv_languages': 'Russian — native; English — B1',
    'cv_name': 'IVAN CLIENT',
    'cv_profession': 'Executive Director',
    'cv_place_of_birth': 'Moscow, Russia',
    'cv_date_of_birth': '08.01.1999',
    'cv_nationality': 'Russian Federation',
    'cv_passport_no': '769773904',
    'full_name_latin': 'IVAN CLIENT',
}
# у многострочных значений строки должны переноситься, как в образце
MULTILINE = ('cv_summary', 'cv_job1_bullets', 'cv_skills_hard', 'cv_skills_soft')


def blocks_in_order(html: str):
    out = []
    for style, inner in BLOCK.findall(html):
        if 'left' not in style or 'top' not in style:
            continue
        txt = ' '.join(re.sub(r'<[^>]+>', ' ', inner).split())
        if not txt:
            continue
        mt = re.search(r'top\s*:\s*([0-9.]+)pt', style)
        out.append({'style': style, 'inner': inner, 'text': txt,
                    'top': float(mt.group(1)) if mt else None})
    return out


def main(argv) -> int:
    apply = '--apply' in argv
    tdir = ROOT / 'data' / 'templates' / CODE
    ex, dst = tdir / 'example_filled.pdf', tdir / 'template.html'
    raw = Path('/tmp/cv_raw.html')
    subprocess.run(['/usr/bin/python3', str(ROOT / 'scripts' / 'pdf_to_template.py'),
                    str(ex), str(raw)], check=True, capture_output=True)
    html = raw.read_text(encoding='utf-8', errors='ignore')
    bs = blocks_in_order(html)
    print('строк с текстом в образце: %d, действий в плане: %d' % (len(bs), len(PLAN)))
    if len(bs) != len(PLAN):
        print('!! план не сходится со строками образца — правка не записана')
        for i, b in enumerate(bs):
            print('   %2d %s' % (i, b['text'][:60]))
        return 1
    head = html[:html.find('<div class="txt"')]
    tail = html[html.rfind('</div>') + len('</div>'):]
    parts, made = [], 0
    LEAD: dict = {}
    CENTER = ('cv_name', 'cv_profession', 'cv_place_of_birth')
    # многострочные значения собираем ИЗ СТРОК ОБРАЗЦА: тогда переносы в документе встанут
    # ровно там же, где в образце (автоперенос по ширине так не совпадёт никогда)
    i = 0
    while i < len(PLAN):
        if PLAN[i].startswith('VAR '):
            var = PLAN[i].split()[1]
            if var in MULTILINE:
                lines = [bs[i]['text']]
                j = i + 1
                while j < len(PLAN) and PLAN[j] == 'DROP':
                    lines.append(bs[j]['text'])
                    j += 1
                VALS[var] = '\n'.join(lines)
                # междустрочный интервал — как в образце: иначе блок при переносе «раздувается»
                # и налезает на следующий раздел
                tops = [bb['top'] for aa, bb in zip(PLAN[i:], bs[i:])
                        if aa == 'DROP' or aa.startswith('VAR ')]
                tops = [t for t in tops if isinstance(t, (int, float))]
                if len(tops) > 1:
                    step = (tops[len(lines) - 1] - tops[0]) / max(1, len(lines) - 1)
                    LEAD[var] = round(step, 2)
                # последний пункт навыков стоит в образце после «Team leadership» — возвращаем
                # его в тот же блок навыков, иначе строка теряется
                if var == 'cv_skills_soft':
                    extra = [bb['text'] for aa, bb in zip(PLAN, bs)
                             if aa == 'DROP' and 'MS Office' in bb['text']]
                    if extra and 'MS Office' not in VALS[var]:
                        VALS[var] = VALS[var] + '\n' + extra[0]
        i += 1
    i = 0
    while i < len(PLAN):
        act = PLAN[i]
        b = bs[i]
        i += 1
        kind = act.split()[0]
        if kind == 'KEEP':
            parts.append('<div class="txt" style="%s">%s</div>' % (b['style'], b['inner']))
        elif kind == 'DROP':
            continue
        elif kind == 'VAR':
            var = act.split()[1]
            style = b['style']
            if var in MULTILINE:
                # строки значения переносим ровно как в образце: white-space:pre сохраняет
                # переводы строк, но НЕ добавляет своих автопереносов (иначе блок «раздувается»)
                style = re.sub(r'white-space\s*:\s*pre-wrap', 'white-space:pre', style)
                if 'white-space' not in style:
                    style = style.rstrip('; ') + ';white-space:pre'
                if var in LEAD:
                    style = re.sub(r'line-height\s*:\s*[0-9.]+(pt)?;?', '', style)
                    style = style.rstrip('; ') + ';line-height:%.2fpt' % LEAD[var]
            if var in CENTER:
                # шапка резюме в образце по центру листа
                style = re.sub(r'left\s*:\s*[0-9.]+pt', 'left:0pt', style)
                style = re.sub(r'width\s*:\s*[0-9.]+pt;?', '', style)
                style = style.rstrip('; ') + ';width:595.28pt;text-align:center'
            parts.append('<div class="txt" style="%s">{{ %s }}</div>' % (style, var))
            made += 1
        elif kind == 'INLINE':
            # строку «Date of Birth … | Nationality … | Passport No …» собираем заново в том же
            # шрифте: в образце она разрезана на много span'ов, по частям её не подменить
            st = re.search(r'<span[^>]*style="([^"]*)"', b['inner'])
            style_span = st.group(1) if st else 'font-family:Arial;font-size:11.00pt;color:#000000'
            new_inner = ('<span style="%s">Date of Birth: {{ cv_date_of_birth }} | Nationality: '
                         '{{ cv_nationality }} | Passport No: {{ cv_passport_no }}</span>' % style_span)
            parts.append('<div class="txt" style="%s">%s</div>' % (b['style'], new_inner))
            made += 3
    out = head + '\n'.join(parts) + '\n' + tail
    got = sorted({m for m in re.findall(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', out)})
    print('переменных в шаблоне: %d — %s' % (len(got), ', '.join(got)))
    print('блоков в шаблоне: %d (заголовков разделов: %d)'
          % (len(re.findall(r'<div class="txt"', out)),
             sum(1 for a in PLAN if a == 'KEEP')))
    if apply:
        bak = dst.with_name('template.html.bak_cv_%s' % time.strftime('%Y%m%d_%H%M%S'))
        if dst.is_file():
            shutil.copy2(dst, bak)
        dst.write_text(out, encoding='utf-8')
        con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
        con.row_factory = sqlite3.Row
        tid = con.execute('SELECT id FROM templates WHERE code=?', (CODE,)).fetchone()['id']
        n = 0
        for name, val in VALS.items():
            row = con.execute('SELECT id FROM template_variables WHERE template_id=? AND name=?',
                              (tid, name)).fetchone()
            if row:
                con.execute('UPDATE template_variables SET default_value=?, examples_json=? WHERE id=?',
                            (val, json.dumps([val], ensure_ascii=False), row['id']))
                n += 1
        con.commit()
        print('записано: template.html (бэкап %s) + %d значений' % (bak.name, n))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
