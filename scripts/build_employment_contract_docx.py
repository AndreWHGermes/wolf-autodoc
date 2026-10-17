#!/usr/bin/env python3
"""Сборка Word-шаблона трудового договора (№11) из образца Employment_Contract.docx.

Юридический текст образца сохраняется дословно; данные конкретного человека и компании
заменяются переменными. Замена идёт по тексту абзаца (сначала по рунам, затем, если
значение разбито на руны, пересобирается абзац) — форматирование абзаца сохраняется.

Запуск: /usr/bin/python3 scripts/build_employment_contract_docx.py [--render]
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from docx import Document

ROOT = Path('/opt/wolf_v2')
SRC = Path('/root/.hermes/cache/documents/doc_03df040a36cd_Employment_Contract.docx')
CODE = 'employment_contract__default'
TPL = ROOT / 'data' / 'templates' / CODE / 'word' / 'template.docx'

# (что в образце, чем заменяем). Порядок важен: сначала длинные строки.
PAIRS = [
    ('OOO “Internet Resheniya” (Internet Solutions LLC)', '{{ employer_name }}'),
    ('Beliaev Konstantin Alekseevich', '{{ contractor_full_name }}'),
    ('Okmyanskaya Olga Yurievna', '{{ employer_representative }}'),
    ('Internet Marketing Specialist', '{{ position }}'),
    ('Advertising and Marketing', '{{ structural_unit }}'),
    ('1248', '{{ contract_no }}'),
    ('150,000', '{{ salary_amount }}'),
    ('one hundred fifty thousand', '{{ salary_words }}'),
]

# Реквизиты сторон в конце договора — переписываем целиком, иначе остаются данные образца.
REQUISITES = [
    ('EMPLOYER', ['EMPLOYER',
                  'Наименование: {{ employer_name }}',
                  'ИНН / КПП: {{ inn_kpp }}',
                  'ОГРН: {{ ogrn }}',
                  'Юридический адрес: {{ company_registered_address }}',
                  'Подпись: ______________________',
                  'М.П.']),
    ('EMPLOYEE', ['EMPLOYEE',
                  'Ф. И. О.: {{ contractor_full_name }}',
                  'Дата рождения: {{ birth_date }}',
                  'Паспорт: {{ passport_number }}',
                  'Адрес регистрации: {{ registration_address }}',
                  'Подпись: ______________________']),
]


def rewrite_cell(cell, lines):
    """Заменяет содержимое ячейки, сохраняя формат первого абзаца."""
    first = cell.paragraphs[0]
    base_run = first.runs[0] if first.runs else None
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    for r in list(first.runs):
        r.text = ''
    first.add_run(lines[0])
    if base_run is not None and base_run.font.size:
        first.runs[-1].font.size = base_run.font.size
    for line in lines[1:]:
        new_p = cell.add_paragraph()
        new_p.paragraph_format.space_before = None
        run = new_p.add_run(line)
        if base_run is not None and base_run.font.size:
            run.font.size = base_run.font.size



def replace_in_paragraph(par, old: str, new: str) -> bool:
    """Замена внутри абзаца: сначала по рунам, потом по всему тексту абзаца."""
    for run in par.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)
            return True
    if old in par.text:
        full = par.text.replace(old, new)
        if not par.runs:
            par.add_run(full)
        else:
            par.runs[0].text = full
            for r in par.runs[1:]:
                r.text = ''
        return True
    return False


def walk(document):
    for p in document.paragraphs:
        yield p
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p


def build() -> Path:
    doc = Document(str(SRC))
    # Реквизиты сторон — переписываем до общих замен
    if doc.tables:
        for row in doc.tables[-1].rows:
            for cell in row.cells:
                head = cell.text.strip().split('\n')[0].strip()
                for key, lines in REQUISITES:
                    if head == key and ('Наименование' in cell.text or 'Ф. И. О.' in cell.text):
                        rewrite_cell(cell, lines)
    # Даты образца («12» January 2026) и подпись сотрудника в строке получения копии
    for par in walk(doc):
        full = par.text
        if not full:
            continue
        new = re.sub(r'[“"]\s*\d{1,2}\s*[”"]\s*(?:January|February|March|April|May|June|July|August|'
                     r'September|October|November|December)\s*\d{2,4}\s*\.?', '{{ contract_date }}', full)
        new = re.sub(r'\bBeliaev\s+K\.\s*A\.', '{{ contractor_full_name }}', new)
        if new != full:
            r0 = par.runs[0] if par.runs else par.add_run('')
            r0.text = new
            for r in par.runs[1:]:
                r.text = ''
    hits = {old: 0 for old, _ in PAIRS}
    for par in walk(doc):
        for old, new in PAIRS:
            if old in par.text or any(old in r.text for r in par.runs):
                if replace_in_paragraph(par, old, new):
                    hits[old] += 1

    TPL.parent.mkdir(parents=True, exist_ok=True)
    if TPL.exists():
        shutil.copy2(TPL, TPL.with_name(f'template.docx.bak_{datetime.now():%Y%m%d_%H%M}'))
    doc.save(str(TPL))
    print('собрано:', TPL.stat().st_size, 'байт')
    for old, n in hits.items():
        print(f'  {"OK " if n else "НЕ НАЙДЕНО"} {n}× {old[:44]}')
    return TPL


def render() -> None:
    import sqlite3
    sys.path.insert(0, str(ROOT))
    import pymupdf
    from services.values import build_template_values
    from services import doc_engine

    c = sqlite3.connect(ROOT / 'data' / 'wolf.db')
    c.row_factory = sqlite3.Row
    r = c.execute('''SELECT a.id FROM applications a JOIN product_documents pd ON pd.product_id=a.product_id
                     JOIN templates t ON t.id=pd.template_id WHERE t.code=?
                     ORDER BY a.id DESC LIMIT 1''', (CODE,)).fetchone()
    app = r['id']
    a = dict(c.execute('SELECT * FROM applications WHERE id=?', (app,)).fetchone())
    cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone()) if a.get('client_id') else {}
    vals = build_template_values(cl, CODE, {}, app) or {}
    res = doc_engine.build_document(CODE, vals, ROOT / 'data' / 'renders', engine='word', name='employment_check')
    d = pymupdf.open(res['pdf'])
    d[0].get_pixmap(dpi=100).save(ROOT / 'data' / 'renders' / 'employment_check.png')
    print(f"заявка {app}: страниц={len(d)} пусто={res['missing']} ph={res['placeholders']}")


if __name__ == '__main__':
    build()
    if '--render' in sys.argv:
        render()
