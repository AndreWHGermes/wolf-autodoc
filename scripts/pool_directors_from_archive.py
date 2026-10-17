#!/usr/bin/env python3
"""Ищем ФИО генеральных директоров в локальном архиве договоров.

В договорах рядом с реквизитами стоят ИНН и подпись руководителя. Ищем по тексту:
ИНН организации и ФИО в шаблоне «в лице Генерального директора Иванова Ивана Ивановича»
(или Director Ivan Ivanov). Найденное дописываем в базу только там, где директор пуст.
"""
import re
import sqlite3
from pathlib import Path

import pymupdf

DATA = Path('/opt/wolf_v2/data')
CACHE = DATA / 'gdrive_cache'
DB = DATA / 'wolf.db'

FIO = r'([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:вич|евич|ич|овна|евна|ична)\s+[А-ЯЁ][а-яё]+)'
PATTERNS = [
    re.compile(r'Генеральн\w+\s+директор\w*[^А-ЯЁ\n]{0,30}' + FIO),
    re.compile(r'в\s+лице\s+[^А-ЯЁ\n]{0,40}директор\w*[^А-ЯЁ\n]{0,20}' + FIO),
    re.compile(r'Director[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+)'),
]
INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')

directors: dict[str, str] = {}
seen = 0
for pdf in CACHE.rglob('*.pdf'):
    try:
        doc = pymupdf.open(pdf)
    except Exception:
        continue
    text = ''
    for page in doc[:6]:
        text += page.get_text()
    doc.close()
    if not text:
        continue
    seen += 1
    found = None
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            found = ' '.join(m.group(1).split())
            break
    if not found:
        continue
    for inn in set(INN_RE.findall(text)):
        directors.setdefault(inn, found)

print('просмотрено договоров:', seen, '| ИНН с директором:', len(directors))

c = sqlite3.connect(DB)
updated = 0
for inn, fio in directors.items():
    cur = c.execute("SELECT id FROM pool_organizations WHERE inn=? AND COALESCE(director,'')=''", (inn,))
    if cur.fetchone():
        c.execute('UPDATE pool_organizations SET director=? WHERE inn=?', (fio, inn))
        updated += 1
c.commit()
print('заполнено директоров:', updated)
print('всего без директора:', c.execute("SELECT COUNT(*) FROM pool_organizations WHERE COALESCE(director,'')=''").fetchone()[0])
