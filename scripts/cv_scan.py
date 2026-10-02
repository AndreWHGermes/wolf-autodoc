"""Сбор всех резюме (CV) из архива Wolf: тексты в один файл для анализа паттернов.

Проходит по папкам клиентов, архивным папкам и примерам, вытаскивает текст и
отбирает те документы, где действительно резюме (по характерным заголовкам).
Результат: docs/cv_corpus.json (структура) и docs/cv_corpus.md (тексты для чтения).

Запуск: /usr/bin/python3 scripts/cv_scan.py [сколько файлов]
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from CLIENT.doc_read import read_text   # noqa: E402

DIRS = [Path('/opt/wolf_v2/data/gCLIENT_cache'),
        Path('/opt/wolf_v2/data/gCLIENT_archive'),
        Path('/opt/wolf_v2/data/gCLIENT_examples')]
EXT = ('.pdf', '.docx', '.doc', '.txt', '.html', '.rtf')
KEYS = ['CLIENTal experience', 'work experience', 'employment CLIENT',
        'CLIENTal CLIENT', 'curriculum vitae', 'резюме', 'опыт работы',
        'key CLIENT', 'CLIENT', 'обязанности']

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
out, seen = [], set()
files = []
for d in DIRS:
    if d.is_dir():
        files += [f for f in d.rglob('*') if f.is_file() and f.suffix.lower() in EXT]

print(f'файлов к проверке: {len(files)}', flush=True)
for i, f in enumerate(files, 1):
    if f in seen:
        continue
    seen.add(f)
    try:
        txt = read_text(f) or ''
    except Exception:
        continue
    if len(txt.strip()) < 200:
        continue
    low = txt.lower()
    hits = sum(1 for k in KEYS if k in low)
    name_hint = any(k in f.name.lower() for k in ('resume', 'cv', 'резюме'))
    if hits >= 2 or name_hint:
        out.append({'file': str(f), 'name': f.name, 'hits': hits,
                    'chars': len(txt), 'text': txt.strip()})
        print(f'  [+] {f.name[:52]:<52} совпадений {hits} | {len(txt)} симв.', flush=True)
    if limit and len(out) >= limit:
        break

Docs = Path('/opt/wolf_v2/docs')
Docs.mkdir(parents=True, exist_ok=True)
(Docs / 'cv_corpus.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

md = ['# Резюме из архива Wolf — собранные тексты', '',
      f'Всего документов-резюме: {len(out)}', '']
for r in out:
    md += [f"## {r['name']}", f"файл: `{r['file']}` | символов: {r['chars']}", '',
           '```', r['text'][:6000], '```', '']
(Docs / 'cv_corpus.md').write_text('\n'.join(md), encoding='utf-8')
print(f'итог: резюме найдено {len(out)} → docs/cv_corpus.json и docs/cv_corpus.md')
