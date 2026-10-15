"""Быстрый сбор резюме из архива Wolf: только текстовый слой PDF, с таймаутами.

Отличия от первой версии:
- сначала быстрый pdftotext (первые страницы), OCR запускается только для мелких
  сканов — иначе один тяжёлый файл держит очередь минуты;
- жёсткий таймаут на файл (SIGALRM), зависшие чтения обрываются;
- результат по каждому найденному резюме сразу пишется в docs/cv_found.jsonl;
- текстовый кэш на диске (docs/txt_cache) — повторный запуск идёт мгновенно.

Запуск: /usr/bin/python3 scripts/cv_scan3.py [воркеров]
"""
import hashlib
import json
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

DIRS = [Path('/opt/wolf_v2/data/gdrive_cache'),
        Path('/opt/wolf_v2/data/gdrive_archive'),
        Path('/opt/wolf_v2/data/gdrive_examples')]
EXT = ('.pdf', '.docx', '.doc', '.txt', '.html', '.rtf')
KEYS = ['professional experience', 'work experience', 'employment history',
        'professional summary', 'curriculum vitae', 'резюме', 'опыт работы',
        'key skills', 'education', 'обязанности']
MAX_MB = 12          # крупные сканы пропускаем — это не резюме
FILE_TIMEOUT = 25    # секунд на файл
DOCS = Path('/opt/wolf_v2/docs')
CACHE = DOCS / 'txt_cache'


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def _pdf_fast(p: Path) -> str:
    """Текстовый слой PDF без OCR — быстро."""
    try:
        r = subprocess.run(['pdftotext', '-l', '4', str(p), '-'],
                           capture_output=True, timeout=FILE_TIMEOUT)
        return r.stdout.decode('utf-8', 'ignore')
    except Exception:
        return ''


def check(path_str: str):
    f = Path(path_str)
    try:
        if f.stat().st_size > MAX_MB * 1024 * 1024:
            return None
    except Exception:
        return None

    key = hashlib.sha1(str(f).encode() + str(f.stat().st_mtime_ns).encode()).hexdigest()[:20]
    cpath = CACHE / (key + '.txt')
    txt = ''
    if cpath.exists():
        try:
            txt = cpath.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            txt = ''

    if not txt:
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(FILE_TIMEOUT)
        try:
            if f.suffix.lower() == '.pdf':
                txt = _pdf_fast(f)
                if len(txt.strip()) < 120:      # скан без текстового слоя
                    sys.path.insert(0, '/opt/wolf_v2')
                    from services.doc_read import read_text
                    txt = read_text(f) or ''
            else:
                sys.path.insert(0, '/opt/wolf_v2')
                from services.doc_read import read_text
                txt = read_text(f) or ''
        except (_Timeout, Exception):
            txt = ''
        finally:
            signal.alarm(0)
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            cpath.write_text(txt, encoding='utf-8')
        except Exception:
            pass

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
    out_path = DOCS / 'cv_found.jsonl'
    done = found = 0
    t0 = time.time()
    with out_path.open('w', encoding='utf-8') as out:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(check, p): p for p in files}
            for fut in as_completed(futs):
                done += 1
                try:
                    res = fut.result()
                except Exception:
                    res = None
                if res:
                    found += 1
                    out.write(json.dumps(res, ensure_ascii=False) + '\n')
                    out.flush()
                    print(f'  [+] {res["name"][:50]:<50} hits {res["hits"]} | {res["chars"]} симв.', flush=True)
                if done % 50 == 0:
                    print(f'  ...{done}/{len(files)}, найдено {found}, {int(time.time()-t0)} с', flush=True)

    rows = [json.loads(l) for l in out_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    md = ['# Резюме из архива Wolf — собранные тексты', '', f'Всего: {len(rows)}', '']
    for r in sorted(rows, key=lambda x: x['name']):
        md += [f"## {r['name']}", f"файл: `{r['file']}` | символов: {r['chars']}", '',
               '```', r['text'][:8000], '```', '']
    (DOCS / 'cv_corpus.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'итог: найдено {len(rows)} резюме из {len(files)} файлов за {int(time.time()-t0)} с')


if __name__ == '__main__':
    main()
