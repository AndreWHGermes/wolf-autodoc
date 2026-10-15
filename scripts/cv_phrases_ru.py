#!/usr/bin/env python3
"""Русские переводы пула фраз («кусочков») — напрямую через DeepSeek, батчами.

Администратор видит «кусочки» на русском, в документ подставляется английский.
Переводы считаются один раз и складываются в файл + в штатный кэш переводов.
"""
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

os.chdir('/opt/wolf_v2')
sys.path.insert(0, '/opt/wolf_v2')
from services import cv_gen

OUT = '/opt/wolf_v2/data/cv_phrases_ru.json'
CACHE_TPL = 5
BATCH = 12


def env_key(name):
    if os.environ.get(name):
        return os.environ[name].strip()
    for p in ('/root/.hermes/.env', '/opt/wolf_v2/.env'):
        try:
            for line in Path(p).read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line.startswith(name + '='):
                    v = line.split('=', 1)[1].strip()
                    return v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in '"\' ' else v
        except Exception:
            continue
    return ''


KEY = env_key('DEEPSEEK_API_KEY_ANDREYL') or env_key('DEEPSEEK_API_KEY')
if not KEY:
    raise SystemExit('нет ключа DeepSeek')

PROMPT = ('Переведи на русский язык строки из резюме (деловой английский). '
          'Сохрани порядок и количество строк: каждая строка входа — ровно одна строка выхода. '
          'Без пояснений, без нумерации. Профессии и должности переводи как принято в русских резюме.')


def ask(lines):
    body = json.dumps({
        'model': 'deepseek-chat',
        'messages': [{'role': 'system', 'content': PROMPT},
                     {'role': 'user', 'content': '\n'.join(lines)}],
        'temperature': 0,
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request('https://api.deepseek.com/v1/chat/completions', data=body,
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + KEY})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode('utf-8'))
    text = (data['choices'][0]['message'].get('content') or '').strip()
    got = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return (got + [''] * len(lines))[:len(lines)]


positions = cv_gen.load_positions() or []
print('профессий: %d' % len(positions))

src_all = []
for p in positions:
    code = p.get('code') or ''
    if code:
        src_all.extend(cv_gen.position_phrases(code) or [])
src_all = list(dict.fromkeys([s for s in src_all if s and s.strip()]))
print('уникальных предложений: %d' % len(src_all))

mapping = {}
conn = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
for i in range(0, len(src_all), BATCH):
    chunk = src_all[i:i + BATCH]
    try:
        got = ask(chunk)
    except Exception as e:
        print('ошибка батча %d: %s' % (i // BATCH + 1, e))
        continue
    for src, ru in zip(chunk, got):
        if ru:
            mapping[src] = ru
            try:
                conn.execute('INSERT OR REPLACE INTO translation_line(template_id, src, ru) '
                             'VALUES(?,?,?)', (CACHE_TPL, src, ru))
            except Exception:
                pass
    conn.commit()
    print('  батч %d/%d — переведено %d' % (i // BATCH + 1, (len(src_all) + BATCH - 1) // BATCH, len(mapping)))
conn.close()

result = {}
for p in positions:
    code = p.get('code') or ''
    if not code:
        continue
    ph = cv_gen.position_phrases(code) or []
    result[code] = {'ru': p.get('ru') or '', 'en': p.get('en') or '',
                    'phrases': ph, 'phrases_ru': [mapping.get(x, '') for x in ph]}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print('сохранено: %s | всего переводов: %d' % (OUT, len(mapping)))
print()
sm = result.get('sales_manager') or {}
for en, ru in list(zip(sm.get('phrases') or [], sm.get('phrases_ru') or []))[:5]:
    print('  EN:', en[:86])
    print('  RU:', ru[:86])
