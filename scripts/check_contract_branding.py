#!/usr/bin/env python3
"""Проверка вставки логотипа и печати в договор (тестовые картинки, потом убираются)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from PIL import Image, ImageDraw
from docx import Document

from services.values import build_template_values
from services import doc_engine

DATA = Path('/opt/wolf_v2/data')
APP = 113

c = sqlite3.connect(DATA / 'wolf.db')
c.row_factory = sqlite3.Row
org = c.execute("SELECT * FROM pool_organizations WHERE name LIKE '%Логомашина%'").fetchone()
if not org:
    print('организация не найдена')
    sys.exit(1)
inn = org['inn']
folder = DATA / 'pool_assets' / inn
folder.mkdir(parents=True, exist_ok=True)

logo = Image.new('RGB', (300, 90), 'white')
d = ImageDraw.Draw(logo)
d.rectangle([0, 0, 299, 89], outline='black', width=2)
d.text((14, 34), org['name'][:26], fill='black')
logo.save(folder / 'logo.png')

seal = Image.new('RGBA', (240, 240), (255, 255, 255, 0))
d = ImageDraw.Draw(seal)
d.ellipse([10, 10, 230, 230], outline=(20, 40, 160, 220), width=6)
d.text((60, 110), 'SEAL TEST', fill=(20, 40, 160, 235))
seal.save(folder / 'seal.png')

c.execute("UPDATE pool_organizations SET logo_path=?, seal_path=? WHERE id=?",
          (f'pool_assets/{inn}/logo.png', f'pool_assets/{inn}/seal.png', org['id']))
c.commit()

cl = dict(c.execute('SELECT * FROM clients WHERE id=(SELECT client_id FROM applications WHERE id=?)',
                    (APP,)).fetchone())
vals = build_template_values(cl, 'employment_contract__default', {}, APP) or {}
res = doc_engine.build_document('employment_contract__default', vals, DATA / 'renders',
                                engine='word', name='contract_brand_check')
doc = Document(res['docx'])
print('картинок в DOCX:', len(doc.inline_shapes), '| pdf:', res['pdf'])
print('пусто:', res['missing'], '| ph:', res['placeholders'])

import pymupdf
pdf = pymupdf.open(res['pdf'])
imgs = sum(len(p.get_images(full=True)) for p in pdf)
print('страниц:', len(pdf), '| картинок в PDF:', imgs)
pdf[0].get_pixmap(dpi=100).save(DATA / 'renders' / 'contract_brand_p1.png')
last = pdf[-1]
last.get_pixmap(dpi=100).save(DATA / 'renders' / 'contract_brand_last.png')
print('png сохранены')
