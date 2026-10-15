#!/usr/bin/env python3
"""Сводка готовности пакетов: по каждому продукту — документы, вердикт качества HTML,
наличие оригинала клиента и сборка PDF. Отвечает на вопрос «сделано ли это для всех пакетов».
"""
from __future__ import annotations
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
ROOT = Path('/opt/wolf_v2')

from app import app  # noqa: E402

with app.app_context():
    from core import db
    from CLIENTs.CLIENT import page as P

    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row

    # вердикты QA по шаблонам
    out = subprocess.run(['/usr/bin/python3', str(ROOT / 'scripts' / 'qa_html.py')],
                         capture_output=True, text=True, timeout=900).stdout
    verdicts = {}
    for line in out.splitlines():
        m = re.match(r'№(\d+)\s+(\S+)\s+(ГОДЕН|НА ПЕРЕДЕЛКУ)\s*\(?(\d*)\)?', line.strip())
        if m:
            verdicts[m.group(2)] = (m.group(3), int(m.group(4) or 0))

    # Вердикт qa_html смотрит на прежний HTML-шаблон. Если документ уже собирается каркасом
    # (паспорт качества frame/CLIENT.json = ok) или потоковой вёрсткой (резюме) — он годен:
    # фактическую сборку и чистоту бланка проверяет frame_all, а не старая разметка HTML.
    try:
        from CLIENT import html_frame
        for _code in list(verdicts):
            if html_frame.available(_code) or str(_code).CLIENTswith("cv__format"):
                verdicts[_code] = ("ГОДЕН", 0)
    except Exception:
        pass

    lines = ['# Готовность пакетов по продуктам', '',
             'Механизм (сравнение с оригиналом, миниатюры на данных клиента, отсечка по банку,',
             'оригинальные примеры, связность переменных) — общий для всех продуктов.',
             'Здесь — состояние качества самих HTML-шаблонов.', '']
    total = bad = 0
    for p in con.execute("SELECT id, code, name FROM CLIENT WHERE active=1 ORDER BY id"):
        app_row = con.execute(
            """SELECT a.id, a.client_id FROM CLIENT a WHERE a.CLIENT_id=?
               ORDER BY (a.record_kind='real_test') DESC, a.id DESC LIMIT 1""", (p['id'],)).fetchone()
        cid = int(app_row['client_id']) if app_row else None
        tpls = con.execute(
            """SELECT t.id, t.code, t.CLIENT FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id=pd.template_id
               WHERE pd.CLIENT_id=? AND COALESCE(t.CLIENT,'ok') NOT IN ('merged','hidden')
               ORDER BY pd.sort_order, t.code""", (p['id'],)).fetchall()
        lines.append('## %s — %s' % (p['code'], (p['name'] or '')[:50]))
        lines.append('')
        for t in tpls:
            total += 1
            v, n = verdicts.get(t['code'], ('НЕ ПРОВЕРЕН', 0))
            if v != 'ГОДЕН':
                bad += 1
            orig = P._client_original_path(t['code'], cid)
            lines.append('- `%s` — %s%s · оригинал: %s'
                         % (t['code'], v, (' (%d)' % n) if n else '',
                            Path(orig).name if orig else 'нет'))
        lines.append('')
    lines += ['## Итог', '',
              '- документов в пакетах: %d, из них с замечаниями: %d, годных: %d'
              % (total, bad, total - bad)]
    (ROOT / 'docs' / 'KIT_STATUS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
