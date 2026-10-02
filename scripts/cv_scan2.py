"""Сбор резюме (CV) из архива Wolf — параллельно, с защитой от зависаний.

Проходит по папкам клиентов, архиву и примерам, вытаскивает тексты и отбирает
документы, где действительно резюме. Результаты пишутся построчно в
docs/cv_found.jsonl (чтобы ничего не потерялось при обрыве), затем собираются
в docs/cv_corpus.md для чтения и анализа паттернов.

Запуск: /usr/bin/python3 scripts/cv_scan2.py [воркеров]
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

DIRS = [Path('/opt/wolf_v2/data/gCLIENT_cache'),
        Path('/opt/wolf_v2/data/gCLIENT_archive'),
        Path('/opt/wolf_v2/data/gCLIENT_examples')]
EXT = ('.pdf', '.docx', '.doc', '.txt', '.html', '.rtf')
KEYS = ['CLIENTal experience', 'work experience', 'employment CLIENT',
        'CLIENTal CLIENT', 'curriculum vitae', 'резюме', 'опыт работы',
        'key CLIENT', 'CLIENT', 'обязанности']

OUT = Path('/opt/wolf_v2/docs/cv_found.jsonl')
DOCS = Path('/opt/wolf_v2/docs')


def check(path_str: str):
    """Читает один файл и решает, резюме это или нет."""
    import sys as _s
    _s.path.insert(0, '/opt/wolf_v2')
    f = Path(path_str)
    try:
        from CLIENT.doc_read import read_text
        txt = read_text(f) or ''
    except Exception:
        return None
    if len(txt.strip()) < 200:
        return None
    low = txt.lower()
    hits = sum(1 for k in KEYS if k in low)
    name_hint = any(k in f.name.lower() for k in ('resume', 'cv', 'резюме'))
    if hits >= 2 or name_hint:
        return {'file': str(f), 'name': f.name, 'hits': hits,
                'chars': len(txt), 'text': txt.strip()}
    return None


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    files = []
    for d in DIRS:
        if d.is_dir():
            files += [str(f) for f in d.rglob('*')
                      if f.is_file() and f.suffix.lower() in EXT]
    print(f'файлов к проверке: {len(files)} | воркеров: {workers}', flush=True)

    done = found = 0
    t0 = time.time()
    with OUT.open('w', encoding='utf-8') as out:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(check, p): p for p in files}
            for fut in as_completed(futures):
                done += 1
                try:
                    res = fut.result()
                except Exception:
                    res = None
                if res:
                    found += 1
                    out.write(json.dumps(res, ensure_ascii=False) + '\n')
                    out.flush()
                    print(f'  [+] {res["name"][:50]:<50} совпадений {res["hits"]} | {res["chars"]} симв.', flush=True)
                if done % 25 == 0:
                    print(f'  ...{done}/{len(files)} файлов, найдено {found}, '
                          f'{int(time.time() - t0)} с', flush=True)

    rows = [json.loads(l) for l in OUT.read_text(encoding='utf-8').splitlines() if l.strip()]
    md = ['# Резюме из архива Wolf — собранные тексты', '',
          f'Всего документов-резюме: {len(rows)}', '']
    for r in sorted(rows, key=lambda x: x['name']):
        md += [f"## {r['name']}", f"файл: `{r['file']}` | символов: {r['chars']}", '',
               '```', r['text'][:8000], '```', '']
    (DOCS / 'cv_corpus.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'итог: резюме найдено {len(rows)} из {len(files)} файлов за {int(time.time() - t0)} с')
    print('файлы: docs/cv_found.jsonl, docs/cv_corpus.md')


if __name__ == '__main__':
    main()
