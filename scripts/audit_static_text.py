#!/usr/bin/env python3
"""Уточнение ревизии: статичный текст из всего XML (включая текстбоксы и таблицы) + имена пустых переменных."""
import json
import re
import zipfile
from pathlib import Path

OUT = Path('/root/.hermes/cache/wolf_audit')
rows = json.loads((OUT / 'report.json').read_text(encoding='utf-8'))
TPL = Path('/opt/wolf_v2/data/templates')

for r in rows:
    if r['engine'] != 'word':
        continue
    p = TPL / r['code'] / 'word' / 'template.docx'
    if not p.exists():
        print(f"{r['doc_index']:>2} {r['code']:<38} НЕТ ФАЙЛА")
        continue
    xml = zipfile.ZipFile(p).read('word/document.xml').decode()
    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', xml)
    full = ''.join(texts)
    static = re.sub(r'\{\{[^}]*\}\}', '', full)
    names = sorted(set(re.findall(r'\{\{\s*([A-Za-z_]\w*)\s*\}\}', full)))
    print(f"{r['doc_index']:>2} {r['code']:<38} перем={len(names):<3} статич={len(static.strip()):<6} "
          f"пусто={len(r['missing'])}: {', '.join(r['missing'][:6])}")
