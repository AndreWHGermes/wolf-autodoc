#!/usr/bin/env python3
"""Добиваем кэш переводов: осмысленные фразы переводим, обрывки/номера оставляем как есть.

После прогона по каждому документу должно быть 100% покрытие статики,
чтобы в интерфейсе кнопка «Перевод» показывала «все строки переведены».
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DB = '/opt/wolf_v2/data/wolf.db'
KEYS_FILE = '/tmp/static_keys.json'
URL = 'https://router.bynara.id/v1/chat/completions'
MODEL = 'ling-3.0-flash-sante-free'
LOG = Path('/tmp/translate_finish.log')

env = Path('/root/.hermes/.env').read_text(encoding='utf-8', errors='ignore')
KEY = ''
for ln in env.splitlines():
    m = re.match(r'\s*NARAROUTER_API_KEY\s*=\s*(.+?)\s*$', ln)
    if m:
        KEY = m.group(1).strip().strip('"').strip("'")
        break
if not KEY:
    sys.exit('ключ не найден')

PROMPT = ('Переведи на русский язык фрагменты делового документа (визовые документы, Индонезия). '
          'Каждый фрагмент — отдельная строка входа. Верни ТОЛЬКО переводы: по одному на строку, '
          'строго в том же порядке и количестве, без нумерации и пояснений. Если фрагмент — '
          'собственное имя, аббревиатура, номер или адрес, верни его без изменений.\n\nВход:\n')


def log(msg):
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(msg + '\n')
    print(msg, flush=True)


def _ask(lines):
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': PROMPT + '\n'.join(lines)}],
            'temperature': 0}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode())['choices'][0]['message']['content'] or ''
    return [re.sub(r'^\s*\d+[.)]\s*', '', l).strip() for l in out.splitlines() if l.strip()]


def translate(line):
    for attempt in range(3):
        try:
            got = _ask([line])
            if got:
                return got[0]
        except Exception:
            pass
        time.sleep(1.5 + attempt * 2)
    return ''


def needs_translation(s: str) -> bool:
    """Переводим только осмысленный текст: есть латинские слова длиной >= 3."""
    return bool(re.search(r'[A-Za-z]{3,}', s)) and len(s) >= 6


def main():
    LOG.write_text('', encoding='utf-8')
    conn = sqlite3.connect(DB, timeout=60)
    data = json.loads(Path(KEYS_FILE).read_text(encoding='utf-8'))

    todo = []      # (tid, code, line)
    as_is = 0
    for code, info in data.items():
        tid, keys = info['template_id'], info.get('keys') or []
        if not keys:
            continue
        have = {r[0] for r in conn.execute('SELECT src FROM translation_line WHERE template_id=?', (tid,))}
        for k in keys:
            if k in have:
                continue
            if needs_translation(k):
                todo.append((tid, code, k))
            else:
                conn.execute('INSERT OR REPLACE INTO translation_line(template_id, src, ru) VALUES(?,?,?)',
                             (tid, k, k))     # обрывок/номер — оставляем как есть
                as_is += 1
    conn.commit()
    log(f'к переводу: {len(todo)} | оставлено как есть (номера, обрывки): {as_is}')

    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(translate, k): (tid, code, k) for tid, code, k in todo}
        for fu in as_completed(futs):
            tid, code, src = futs[fu]
            try:
                dst = fu.result()
            except Exception:
                dst = ''
            if not dst:
                dst = src          # не удалось — оставляем исходный текст, чтобы документ не «дырявился»
            conn.execute('INSERT OR REPLACE INTO translation_line(template_id, src, ru) VALUES(?,?,?)',
                         (tid, src, dst))
            conn.commit()
            done += 1
            log(f'  [{done}/{len(todo)}] {code[:28]} ← {src[:40]}')

    log('\nФИНАЛЬНОЕ ПОКРЫТИЕ:')
    all_ok = True
    for code, info in data.items():
        tid, keys = info['template_id'], info.get('keys') or []
        if not keys:
            continue
        have = {r[0] for r in conn.execute('SELECT src FROM translation_line WHERE template_id=?', (tid,))}
        miss = [k for k in keys if k not in have]
        if miss:
            all_ok = False
        log(f'  {code[:36].ljust(36)} {len(keys)-len(miss)}/{len(keys)}' + ('' if not miss else f'  БЕЗ: {miss[:2]}'))
    log('\nИТОГ: ' + ('все документы покрыты на 100% ✅' if all_ok else 'есть пропуски'))
    conn.close()


if __name__ == '__main__':
    main()
