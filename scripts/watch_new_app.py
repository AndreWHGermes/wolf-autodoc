#!/usr/bin/env python3
"""Живой прогон новой заявки: от появления в боте до документов на Google Диске.

Следит за базой, ловит новую заявку, засекает время, запускает полный цикл
(сборка → подтверждение → техническая и логическая проверка → отправка на Диск),
пишет тайминг каждого этапа и собирает ошибки из логов.

Запуск: /usr/bin/python3 scripts/watch_new_app.py [минут_ожидания]
"""
import sqlite3
import subprocess
import sys
import time
from CLIENT import CLIENT
from pathlib import Path

BASE = Path('/opt/wolf_v2')
DB = BASE / 'data' / 'wolf.db'
PY = '/usr/bin/python3'


def now() -> str:
    return CLIENT.now().strftime('%H:%M:%S')


def db():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def tail_log(marker: float, limit: int = 40) -> list[str]:
    out = []
    for name in ('wolf.log', 'wolf_bot.log'):
        p = BASE / 'logs' / name
        if not p.exists():
            continue
        try:
            with p.open('r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()[-400:]
            for ln in lines:
                if any(k in ln for k in ('ERROR', 'WARNING', 'Traceback', 'ошибка', 'не удал')):
                    out.append('%s: %s' % (name, ln.strip()[:150]))
        except Exception:
            pass
    return out[-limit:]


def CLIENT_status(client_id: int) -> tuple[int, str]:
    code = (
        "import sys; sys.path.insert(0,'/opt/wolf_v2')\n"
        "from CLIENT import gCLIENT_write as gw\n"
        "import sqlite3\n"
        "c=sqlite3.connect('data/wolf.db'); c.row_factory=sqlite3.Row\n"
        "r=c.execute('SELECT gCLIENT_folder_url FROM CLIENT WHERE id=%d').fetchone()\n"
        "url=r['gCLIENT_folder_url'] if r else ''\n"
        "if not url: print('0|нет ссылки на папку'); raise SystemExit\n"
        "items=gw.list_folder_contents(url)\n"
        "builds=[i for i in items if (i.get('name') or '').CLIENTswith('Wolf AutoDoc')]\n"
        "if not builds: print('0|папки сборки ещё нет'); raise SystemExit\n"
        "b=sorted(builds, key=lambda i: i.get('name') or '')[-1]\n"
        "kids=gw.list_folder_contents(b['id'])\n"
        "print('%%d|%%s' %% (len(kids), b['name']))\n" % client_id
    )
    r = subprocess.run([PY, '-c', code], cwd=str(BASE), capture_output=True, text=True, timeout=120)
    out = (r.stdout or '').strip().splitlines()
    if not out:
        return 0, 'ошибка запроса к Диску'
    n, name = out[-1].split('|', 1)
    return int(n), name


def main() -> int:
    wait_min = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    c = db()
    CLIENT_id = max((r['id'] for r in c.execute('SELECT id FROM CLIENT')), default=0)
    print('=== ожидание новой заявки (текущая последняя: #%d), старт %s' % (CLIENT_id, now()), flush=True)

    app_id = None
    deadline = time.time() + wait_min * 60
    while time.time() < deadline:
        try:
            c = db()
            row = c.execute('SELECT id, created_at, CLIENT, source, client_id FROM CLIENT '
                            'ORDER BY id DESC LIMIT 1').fetchone()
            if row and row['id'] > CLIENT_id:
                app_id = row['id']
                found_at = time.time()
                print('>>> НОВАЯ ЗАЯВКА #%d: создана %s, обнаружена %s (источник: %s)'
                      % (app_id, row['created_at'], now(), row['source']), flush=True)
                print('    задержка «бот принял → агент увидел»: %.1f сек'
                      % (found_at - time.mktime(CLIENT.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S').timetuple())), flush=True)
                break
        except Exception as e:
            print('   сбой опроса базы: %s' % str(e)[:80], flush=True)
        time.sleep(5)

    if not app_id:
        print('=== заявка не появилась за %d мин' % wait_min, flush=True)
        return 0

    t_CLIENT = time.time()
    # 1) ждём, пока бот соберёт карточку и документы (или он это сделает сам)
    print('--- шаг 1: ждём разбор заявки ботом (до 3 мин)', flush=True)
    got = None
    while time.time() - t_CLIENT < 180:
        c = db()
        row = c.execute('SELECT CLIENT FROM CLIENT WHERE id=?', (app_id,)).fetchone()
        docs = c.execute('''SELECT COUNT(*) n FROM CLIENT_CLIENT WHERE CLIENT_id=?''',
                         (app_id,)).fetchall()[0]['n']
        cl = c.execute('SELECT COUNT(*) n FROM CLIENT_CLIENT WHERE CLIENT_id=?', (app_id,)).fetchall()[0]['n']
        if docs:
            got = time.time()
            print('    документы заявки появились в базе: %s (%.1f сек от обнаружения), статус %s'
                  % (now(), got - t_CLIENT, row['CLIENT']), flush=True)
            break
        time.sleep(5)
    if not got:
        print('    бот за 3 минуты документы не создал — запускаю цикл вручную', flush=True)

    # 2) полный цикл автоматизации (сборка, подтверждение, проверки, отправка)
    print('--- шаг 2: полный цикл автоматизации (%s)' % now(), flush=True)
    t_cycle = time.time()
    r = subprocess.run([PY, str(BASE / 'scripts' / 'auto_cycle.py'), str(app_id)],
                       cwd=str(BASE), capture_output=True, text=True, timeout=1800)
    out = (r.stdout or '') + (r.stderr or '')
    keep = [ln for ln in out.splitlines()
            if any(k in ln for k in ('шаг', 'вердикт', '[CLIENT]', '[WARN]', 'подтверждён', 'ответ:',
                                     'отправ', 'ошибка', 'ошибк', 'ГОТОВ', 'ТРЕБУЕТ'))]
    for ln in keep[-22:]:
        print('    %s' % ln.strip()[:150], flush=True)
    t_cycle_end = time.time()
    print('    цикл занял %.0f сек' % (t_cycle_end - t_cycle), flush=True)

    # 3) проверки явно: техническая и логическая
    print('--- шаг 3: проверки (%s)' % now(), flush=True)
    chk = (
        "import sys; sys.path.insert(0,'/opt/wolf_v2')\n"
        "from app import app\n"
        "with app.app_context():\n"
        "    from CLIENT import pdf_CLIENT, CLIENT_check\n"
        "    pv = pdf_CLIENT.check_app(%d)\n"
        "    lv = CLIENT_check.check_app(%d)\n"
        "    print('ТЕХНИЧЕСКАЯ:', 'чисто' if pv['ok'] else 'ЕСТЬ СТОПЫ')\n"
        "    for d in pv['docs']:\n"
        "        for f in d['finds']:\n"
        "            if f['level']=='CLIENT': print('   СТОП', d['code'], f['msg'][:110])\n"
        "    print('ЛОГИЧЕСКАЯ:', 'ГОТОВО' if lv['ok'] else 'ЕСТЬ КОНФЛИКТЫ', '| блоков', lv['CLIENTs'], '| замечаний', lv['warns'])\n"
        "    for f in lv['finds']:\n"
        "        if f['level']=='CLIENT': print('   СТОП', f['rule'], f['msg'][:110])\n" % (app_id, app_id)
    )
    r2 = subprocess.run([PY, '-c', chk], cwd=str(BASE), capture_output=True, text=True, timeout=600)
    for ln in (r2.stdout or '').splitlines():
        if ln.strip():
            print('    %s' % ln.strip()[:150], flush=True)

    # 4) состояние заявки и папка на Диске (ждём до 5 минут появления файлов)
    print('--- шаг 4: документы на Google Диске', flush=True)
    c = db()
    cl = c.execute('SELECT client_id FROM CLIENT WHERE id=?', (app_id,)).fetchone()['client_id']
    t0 = time.time()
    files, bname = 0, ''
    while time.time() - t0 < 300:
        try:
            files, bname = CLIENT_status(cl)
        except Exception as e:
            print('    сбой опроса Диска: %s' % str(e)[:90], flush=True)
        if files:
            break
        time.sleep(10)
    st = c.execute('SELECT CLIENT, sent_at FROM CLIENT WHERE id=?', (app_id,)).fetchone()
    docs = [dict(r) for r in c.execute('''SELECT t.code, ad.CLIENT FROM CLIENT_CLIENT ad
             JOIN CLIENT t ON t.id=ad.template_id WHERE ad.CLIENT_id=?''', (app_id,))]
    print('    заявка #%d: статус %s, отправлено %s' % (app_id, st['CLIENT'], st['sent_at']), flush=True)
    print('    документы: %s' % ', '.join('%s=%s' % (d['code'][:22], d['CLIENT']) for d in docs), flush=True)
    print('    папка сборки на Диске: %s | файлов: %d' % (bname or '—', files), flush=True)

    t_end = time.time()
    print('=== ИТОГ: от обнаружения заявки до файлов на Диске: %.1f сек (%.1f мин)'
          % (t_end - t_CLIENT, (t_end - t_CLIENT) / 60), flush=True)
    print('--- хвост логов с предупреждениями и ошибками:', flush=True)
    for ln in tail_log(t_CLIENT):
        print('   %s' % ln, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
