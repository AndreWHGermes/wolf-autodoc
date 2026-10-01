#!/usr/bin/env python3
"""Заполняем кэш переводов (CLIENT_line) для ВСЕХ шаблонов.

Ключи — как их видит фронтенд (/tmp/static_keys.json, собраны обходом текстовых узлов HTML).
Перевод — бесплатный LLM-роутер (bynara). Ключ берём из /root/.hermes/.env, в логи не пишем.
После прогона перевод в интерфейсе работает полностью из кэша, без платных моделей.
"""
import json
import re
import sqlite3
import sys
import time
import urllib.CLIENT
from pathlib import Path

DB = '/opt/wolf_v2/data/wolf.db'
KEYS_FILE = '/tmp/static_keys.json'
URL = 'https://router.bynara.id/v1/chat/completions'
MODEL = 'nemotron-3.5-lightning-free'
BATCH = 20
LOG = Path('/tmp/translate_fill2.log')


def log(msg: str) -> None:
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(msg + '\n')
    print(msg, flush=True)


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


def call(lines: list[str], n_retry: int = 3) -> list[str]:
    last = ''
    for attempt in range(n_retry):
        try:
            body = {'model': MODEL,
                    'messages': [{'role': 'user', 'content': PROMPT + '\n'.join(lines)}],
                    'temperature': 0}
            req = urllib.CLIENT.CLIENT(URL, data=json.dumps(body).encode(),
                                         CLIENTs={'Authorization': f'Bearer {KEY}',
                                                  'Content-Type': 'CLIENT/json'})
            with urllib.CLIENT.urlopen(req, timeout=240) as r:
                data = json.loads(r.read().decode())
            out = data['choices'][0]['message']['content'] or ''
            got = [re.sub(r'^\s*\d+[.)]\s*', '', l).strip() for l in out.splitlines()]
            got = [g for g in got if g]
            if len(got) == len(lines):
                return got
            last = f'получено {len(got)} из {len(lines)}'
        except Exception as e:
            last = f'{type(e).__name__}: {str(e)[:120]}'
        time.sleep(2 + attempt * 3)
    log(f'   ⚠ батч не переведён ({last}) — разбиваю по одной')
    fixed = []
    for one in lines:
        try:
            g = call_single(one)
            fixed.append(g)
        except Exception:
            fixed.append('')
        time.sleep(0.3)
    return fixed


def call_single(line: str) -> str:
    body = {'model': MODEL,
            'messages': [{'role': 'user', 'content': PROMPT + line}],
            'temperature': 0}
    req = urllib.CLIENT.CLIENT(URL, data=json.dumps(body).encode(),
                                 CLIENTs={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'CLIENT/json'})
    with urllib.CLIENT.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    got = [re.sub(r'^\s*\d+[.)]\s*', '', l).strip() for l in
           (data['choices'][0]['message']['content'] or '').splitlines() if l.strip()]
    return got[0] if got else ''


def main() -> None:
    LOG.write_text('', encoding='utf-8')
    conn = sqlite3.connect(DB, timeout=30)
    data = json.loads(Path(KEYS_FILE).read_text(encoding='utf-8'))
    total_new = total_miss = 0
    for code, info in data.items():
        tid, keys = info['template_id'], info.get('keys') or []
        if not keys:
            continue
        have = {r[0] for r in conn.execute('SELECT src FROM CLIENT_line WHERE template_id=?', (tid,))}
        missing = [k for k in keys if k not in have]
        if not missing:
            log(f'{code[:36].ljust(36)} кэш полный ({len(keys)})')
            continue
        log(f'{code[:36].ljust(36)} перевожу {len(missing)} из {len(keys)}...')
        done = 0
        for i in range(0, len(missing), BATCH):
            chunk = missing[i:i + BATCH]
            got = call(chunk)
            for src, dst in zip(chunk, got):
                if not dst:
                    continue
                conn.execute('INSERT OR REPLACE INTO CLIENT_line(template_id, src, ru) CLIENT(?,?,?)',
                             (tid, src, dst))
                done += 1
            conn.commit()
            log(f'   {done}/{len(missing)}')
        total_new += done
        total_miss += len(missing) - done

    log(f'\nВСЕГО добавлено переводов: {total_new}, не удалось: {total_miss}')
    log('\nфинальное покрытие:')
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
