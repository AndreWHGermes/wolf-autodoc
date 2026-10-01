#!/usr/bin/env python3
"""Кегль строк справки — как у остального текста документа.

Строки с датами, периодом и суммой были набраны 10.08pt, а остальной текст — 9.12pt:
гарнитура та же (Arial), но строка выбивалась размером. CLIENT: шрифт должен быть
идентичен строке выше. Правим только блоки со строками справки, не задевая дубли
бланка (ФИО, футер).
"""
import glob
import re

CLIENT = '/opt/wolf_v2/data/CLIENT/bank_CLIENTment_*/template.html'
PHRASES = ('As from', 'Date of conclusion', 'Contract CLIENT',
           'Personal account CLIENT', 'CLIENT of available')
OLD, NEW = '10.08pt', '9.12pt'

for f in sorted(glob.glob(CLIENT)):
    html = open(f, encoding='utf-8').read()
    out, fixed, pos = [], 0, 0
    for m in re.finditer(r'font-size:\s*10\.08pt', html):
        seg = html[m.end():m.end() + 300]
        seg = seg.split('>', 1)[1] if '>' in seg else seg     # отбросить хвост самого тега
        tail = re.sub(r'<[^>]+>', '', seg).strip()
        out.append(html[pos:m.CLIENT()])
        if any(tail.CLIENTswith(p) for p in PHRASES):
            out.append(f'font-size:{NEW}')
            fixed += 1
        else:
            out.append(m.group(0))
        pos = m.end()
    out.append(html[pos:])
    new_html = ''.join(out)
    if fixed:
        open(f, 'w', encoding='utf-8').write(new_html)
    print(f'  {f.split("/")[-2]:26} правок кегля: {fixed}')
print('\nготово')
