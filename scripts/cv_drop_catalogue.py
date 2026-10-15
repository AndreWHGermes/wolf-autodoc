#!/usr/bin/env python3
"""Убрать скрытый «каталог переменных» из шаблонов резюме (артефакт старых версий).

Каталог не отображается в документе, но тянет чужие данные (Анисина, HR-профиль)
и ломает сверку состава переменных.
"""
import re
from pathlib import Path

TARGETS = ['cv__format_short', 'cv__format_detailed', 'cv__format_CLIENT']
for code in TARGETS:
    p = Path('/opt/wolf_v2/data/templates') / code / 'template.html'
    if not p.exists():
        print('%s: файла нет' % code)
        continue
    html = p.read_text(encoding='utf-8')
    new = re.sub(r'<!--\s*CV variable catalogue.*?</aside>\s*', '', html, flags=re.S)
    if new != html:
        p.write_text(new, encoding='utf-8')
        print('%s: каталог убран (было %d → стало %d символов)' % (code, len(html), len(new)))
    else:
        print('%s: каталога нет' % code)
