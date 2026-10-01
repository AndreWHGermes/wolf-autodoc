#!/usr/bin/env python3
"""Цвет подставляемых значений = чёрный, как весь текст документа.

В банковских справках строка про период и сумму (и строки с номером договора/счёта)
были набраны цветом #2b3d4f — серо-синим. CLIENT: цвет дат и суммы должен быть
чисто чёрным, как во всём документе.
"""
import glob
import re

TPL = '/opt/wolf_v2/data/CLIENT'
BAD = {'#2b3d4f': '#000000'}          # серо-синий текст → чёрный

for f in sorted(glob.glob(f'{TPL}/*/template.html')):
    html = open(f, encoding='utf-8').read()
    src = html
    for bad, good in BAD.items():
        html = re.sub(r'color:\s*' + re.escape(bad), 'color:' + good, html, flags=re.I)
    if html != src:
        open(f, 'w', encoding='utf-8').write(html)
        code = f.split('/')[-2]
        n = len(re.findall(r'color:\s*#2b3d4f', src, flags=re.I))
        print(f'  поправлено {code}: {n} мест')
    else:
        print(f'  чисто: {f.split("/")[-2]}')
print('\nготово')
