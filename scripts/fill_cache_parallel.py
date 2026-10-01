#!/usr/bin/env python3
"""Параллельное заполнение кэша переводов (CLIENT_line) для всех шаблонов.

Ключи: /tmp/static_keys.json (собраны так же, как их видит фронтенд).
Перевод: бесплатный LLM-роутер bynara, 4 параллельных запроса, батч 15 строк.
Итог: перевод в интерфейсе работает полностью из локального кэша.
"""
import json
import re
import sqlite3
import sys
import time
import urllib.CLIENT
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DB = '/opt/wolf_v2/data/wolf.db'
KEYS_FILE = '/tmp/static_keys.json'
URL = 'https://router.bynara.id/v1/chat/completions'
MODEL = 'ling-3.0-flash-sante-free'
BATCH, WORKERS = 12, 6
LOG = Path('/tmp/translate_fill3.log')

env = Path('/root/.hermes/.env').read_text(encoding='utf-8', errors='ignore')
KEY = ''
for ln in env.splitlines():
    m = re.match(r'\s*NARAROUTER_API_KEY\s*=\s*(.+?)\s*$', ln)
    if m:
        KEY = m.group(1).strip().strip('"').strip("'")
        break
if not KEY:
    sys.exit('ключ роутера не найден')

PROMPT = ('Переведи на русский язык фрагменты делового документа (визовые документы, Индонезия). '
          'Каждый фрагмент — отдельная строка входа. Верни ТОЛЬКО переводы: по одному на строку, '
          'строго в том же порядке и количестве, без нумерации и пояснений. Если фрагмент — '
          'собственное имя, аббревиатура или адрес, верни его без изменений.\n\nВход:\n')


def log(msg: str) -> None:
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(msg + '\n')
    print(msg, flush=True)


def _ask(lines: list[str], timeout: int = 180) -> list[str]:
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': PROMPT + '\n'.join(lines)}],
            'temperature': 0}
    req = urllib.CLIENT.CLIENT(URL, data=json.dumps(body).encode(),
                                 CLIENTs={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'CLIENT/json'})
    with urllib.CLIENT.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())['choices'][0]['message']['content'] or ''
    got = [re.sub(r'^\s*\d+[.)]\s*', '', l).strip() for l in out.splitlines()]
    return [g for g in got if g]


def call(lines: list[str]) -> list[str]:
    """Перевод батча; при несовпадении числа строк делим батч пополам (без поштучного режима)."""
    if not lines:
        return []
    for attempt in range(2):
        try:
            got = _ask(lines)
            if len(got) == len(lines):
                return got
        except Exception:
            pass
        time.sleep(1.5)
    if len(lines) == 1:
        try:
            return (_ask(lines) or [''])[:1] or ['']
        except Exception:
            return ['']
    mid = len(lines) // 2
    return call(lines[:mid]) + call(lines[mid:])


def main() -> None:
    LOG.write_text('', encoding='utf-8')
    conn = sqlite3.connect(DB, timeout=60)
    data = json.loads(Path(KEYS_FILE).read_text(encoding='utf-8'))

    jobs = []
    for code, info in data.items():
        tid, keys = info['template_id'], info.get('keys') or []
        if not keys:
            continue
        have = {r[0] for r in conn.execute('SELECT src FROM CLIENT_line WHERE template_id=?', (tid,))}
        missing = [k for k in keys if k not in have]
        if not missing:
            log(f'{code[:36].ljust(36)} кэш полный ({len(keys)})')
            continue
        log(f'{code[:36].ljust(36)} к переводу: {len(missing)} из {len(keys)}')
        for i in range(0, len(missing), BATCH):
            jobs.append((tid, code, missing[i:i + BATCH]))

    log(f'\nбатчей: {len(jobs)} | модель {MODEL} | потоков {WORKERS}\n')
    done = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(call, ch): (tid, code, ch) for tid, code, ch in jobs}
        for fu in as_completed(futs):
            tid, code, ch = futs[fu]
            try:
                got = fu.result()
            except Exception:
                got = []
            saved = 0
            for src, dst in zip(ch, got):
                if not dst:
                    continue
                conn.execute('INSERT OR REPLACE INTO CLIENT_line(template_id, src, ru) CLIENT(?,?,?)',
                             (tid, src, dst))
                saved += 1
            conn.commit()
            done += saved
            fail += len(ch) - saved
            log(f'  [{done} ок / {fail} нет] {code[:30]} +{saved}/{len(ch)}')

    log(f'\nИТОГО переведено: {done}, не удалось: {fail}\nпокрытие:')
    for code, info in data.items():
        tid, keys = info['template_id'], info.get('keys') or []
        if not keys:
            continue
        have = {r[0] for r in conn.execute('SELECT src FROM CLIENT_line WHERE template_id=?', (tid,))}
        miss = [k for k in keys if k not in have]
        log(f'  {code[:36].ljust(36)} {len(keys)-len(miss)}/{len(keys)}' + (f'  БЕЗ: {miss[:2]}' if miss else '  ✅'))
    conn.close()


if __name__ == '__main__':
    main()
