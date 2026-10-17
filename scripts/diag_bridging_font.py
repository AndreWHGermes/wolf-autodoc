#!/usr/bin/env python3
"""Диагностика кегля тела письма Bridging: почему 5pt вместо 11."""
import re
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
import docxtpl
import pymupdf
from services.values import build_template_values

CODE = 'bridging_request_letter__default'
TPL = Path('/opt/wolf_v2/data/templates') / CODE / 'word' / 'template.docx'
OUT = Path('/opt/wolf_v2/data/renders/diag_body.docx')

c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row
a = dict(c.execute('SELECT * FROM applications WHERE id=107').fetchone())
cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone())
vals = build_template_values(cl, CODE, {}, 107) or {}
body = str(vals.get('body_request_line') or '')
print('длина значения:', len(body), '| переносов:', body.count('\n'))

t = docxtpl.DocxTemplate(str(TPL))
t.render({k: ('' if v is None else str(v)) for k, v in vals.items()})
t.save(str(OUT))

xml = zipfile.ZipFile(OUT).read('word/document.xml').decode()
i = xml.find('Bridging Visa 60 hari')
print('--- XML вокруг подставленного текста ---')
print(re.sub(r'><', '>\n<', xml[max(0, i - 420):i + 60])[:1200])

subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', str(OUT),
                '--outdir', str(OUT.parent)], check=True, stdout=subprocess.DEVNULL)
doc = pymupdf.open(OUT.with_suffix('.pdf'))
for b in doc[0].get_text('dict')['blocks']:
    for l in b.get('lines', []):
        txt = ''.join(s['text'] for s in l['spans'])
        if 'Bridging Visa 60 hari' in txt or 'selaku penerima' in txt:
            print('КЕГЛЬ:', [round(s['size'], 1) for s in l['spans']], '|', txt[:50])
