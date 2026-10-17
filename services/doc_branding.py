#!/usr/bin/env python3
"""Логотип и печать организации в договоре.

Логотип ставится в шапку документа (первый абзац, по центру), печать — возле
подписи работодателя. Картинки берутся из базы «База значений»
(pool_organizations.logo_path / seal_path).

Файлы ищутся в data/pool_assets/<ИНН>/. SVG для Word не годится — конвертируется
в PNG при загрузке; здесь поддерживаются png/jpg/webp.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

DATA = Path('/opt/wolf_v2/data')
DB = DATA / 'wolf.db'


def _norm(name: str) -> str:
    s = str(name or '').lower()
    s = re.sub(r'[«»"\']', '', s)
    s = re.sub(r'\b(llc|ltd|inc|ооо|оао|зао|пао|ип)\b', '', s)
    s = re.sub(r'[^a-zа-я0-9]+', ' ', s)
    return ' '.join(s.split())


def find_org(vals: dict) -> dict | None:
    """Организация договора: по ИНН, иначе по названию."""
    inn = ''
    for key in ('inn_kpp', 'inn_kpp_ogrn', 'company_inn', 'inn'):
        m = re.search(r'(\d{10}|\d{12})', str(vals.get(key) or ''))
        if m:
            inn = m.group(1)
            break
    names = [vals.get('company_name_in_quotes'), vals.get('company_name'),
             vals.get('employer_name'), vals.get('company_full_name')]
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        if inn:
            row = c.execute('SELECT * FROM pool_organizations WHERE inn=?', (inn,)).fetchone()
            if row:
                return dict(row)
        rows = c.execute("SELECT * FROM pool_organizations WHERE COALESCE(logo_path,'')<>'' "
                         "OR COALESCE(seal_path,'')<>''").fetchall()
        wanted = {_norm(n) for n in names if n}
        for row in rows:
            if _norm(row['name']) in wanted or _norm(row['name_en'] or '') in wanted:
                return dict(row)
    finally:
        c.close()
    return None


def _img(rel: str | None) -> Path | None:
    if not rel or str(rel).startswith(('http://', 'https://')):
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = DATA / rel
    if p.exists() and p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
        return p
    return None


def apply(docx_path: Path, code: str, vals: dict) -> dict:
    """Возвращает {'logo': bool, 'seal': bool} — что реально вставлено."""
    if code not in ('employment_contract__default', 'remote_work_agreement__default'):
        return {'logo': False, 'seal': False}
    org = find_org(vals)
    if not org:
        return {'logo': False, 'seal': False}
    logo, seal = _img(org.get('logo_path')), _img(org.get('seal_path'))
    if not logo and not seal:
        return {'logo': False, 'seal': False}

    doc = Document(str(docx_path))
    done = {'logo': False, 'seal': False}

    if logo:
        par = doc.paragraphs[0]
        new = par.insert_paragraph_before()
        new.alignment = WD_ALIGN_PARAGRAPH.CENTER
        new.add_run().add_picture(str(logo), width=Cm(3.2))
        done['logo'] = True

    if seal:
        def paras():
            for p in doc.paragraphs:
                yield p
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for p in cell.paragraphs:
                            yield p
        for par in paras():
            low = par.text.strip().lower()
            if low.startswith('signature:') or low.startswith('подпись:'):
                run = par.add_run('  ')
                run.add_picture(str(seal), width=Cm(2.6))
                done['seal'] = True
                break

    if any(done.values()):
        doc.save(str(docx_path))
    return done
