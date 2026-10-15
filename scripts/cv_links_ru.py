#!/usr/bin/env python3
"""Русские подписи для связей: должности, обязанности по сферам, контекст.

Интерфейс администратора — русский, документ — английский. Переводы считаются
один раз рабочим ключом и складываются в data/cv_links_ru.json.
"""
import json
import sys

sys.path.insert(0, '/opt/wolf_v2')
from services import translate as T

LINKS = '/opt/wolf_v2/data/cv_links.json'
OUT = '/opt/wolf_v2/data/cv_links_ru.json'

data = json.load(open(LINKS, encoding='utf-8'))
src = []
for lst in (data.get('profession_titles') or {}).values():
    src.extend(lst)
for lst in (data.get('sector_duties') or {}).values():
    src.extend(lst)
src.extend((data.get('sector_context') or {}).values())
src = list(dict.fromkeys([x for x in src if x and x.strip()]))
print('строк на перевод:', len(src))

got = T.translate_by_reserve(src)
mapping = {s: (g or '') for s, g in zip(src, got)}
print('переведено:', sum(1 for v in mapping.values() if v))

out = {'titles': {}, 'duties': {}, 'context': {}}
for lst in (data.get('profession_titles') or {}).values():
    for x in lst:
        out['titles'][x] = mapping.get(x, '')
for lst in (data.get('sector_duties') or {}).values():
    for x in lst:
        out['duties'][x] = mapping.get(x, '')
for x in (data.get('sector_context') or {}).values():
    out['context'][x] = mapping.get(x, '')

json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('сохранено:', OUT)
for x in ['Sales Manager', 'Head of Sales']:
    print('  %s → %s' % (x, out['titles'].get(x, '')))
for x in list((data.get('sector_duties') or {}).get('ecommerce_retail') or [])[:2]:
    print('  ', out['duties'].get(x, '')[:88])
