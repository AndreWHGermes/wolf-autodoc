#!/usr/bin/env python3
"""Подгонка Remote Work Agreement под плотность подлинника: 3 страницы, как в real.pdf."""
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from docx import Document
from docx.shared import Cm, Pt

CODE = 'remote_work_agreement__default'
TPL = Path('/opt/wolf_v2/data/templates') / CODE / 'word' / 'template.docx'

doc = Document(str(TPL))
for st in ('Normal',):
    s = doc.styles[st]
    s.font.size = Pt(12)
    pf = s.paragraph_format
    pf.line_spacing = 1.15
    pf.space_after = Pt(6)

for sec in doc.sections:
    sec.top_margin = sec.bottom_margin = Cm(2.5)
    sec.left_margin, sec.right_margin = Cm(2.5), Cm(2.0)

# Кегль в рунах, заданный явно (16 pt и т. п.), не трогаем — только мелкий текст
for p in doc.paragraphs:
    for r in p.runs:
        if r.font.size and r.font.size < Pt(12) and len(p.text) > 60:
            r.font.size = Pt(12)

if TPL.exists():
    shutil.copy2(TPL, TPL.with_name(f'template.docx.bak_{datetime.now():%Y%m%d_%H%M}'))
doc.save(str(TPL))
print('RWA обновлён:', TPL.stat().st_size, 'байт')
