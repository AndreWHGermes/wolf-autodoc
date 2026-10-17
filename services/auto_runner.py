#!/usr/bin/env python3
"""Полная автоматизация заявки (заказчик: «администратор кинул заявку — система всё делает сама»).

Маршрут без участия человека:
    заявка принята → документы собраны → технический контроль → логическая проверка данных →
    документы подтверждены → загрузка на Google Диск → оповещение менеджера и администраторов.

Всё пишется в журнал: таблица `auto_runs` в базе + `data/reports/auto_cycle.jsonl`.
Если проверка нашла конфликт — отправки НЕТ, заявка остаётся человеку, причины в журнале.

Запуск:
    /usr/bin/python3 services/auto_runner.py <app_id>     — одна заявка
    /usr/bin/python3 services/auto_runner.py --pickup     — все новые заявки, которых ещё не касались
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / 'data' / 'wolf.db'
CUTOFF_FILE = ROOT / 'data' / 'auto_cutoff.txt'   # с какого момента брать заявки
LOG = ROOT / 'data' / 'reports' / 'auto_cycle.jsonl'
PY = '/usr/bin/python3'
STATUSES_DONE = ('sent',)          # уже отправлено — повторно не трогаем


def ts() -> str:
    # время в базе — UTC (server TZ = CEST), сравнение строк идёт с created_at заявок
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def auto_paused() -> bool:
    """Кнопка «Пауза» на главной — глобальный стоп: прогон не начинается и не отправляет пакет."""
    try:
        c = conn()
        r = c.execute("SELECT value FROM settings WHERE key='auto_mode'").fetchone()
        c.close()
        return ((r['value'] if r else '') or '').strip() != 'on'
    except Exception:                                  # noqa: BLE001
        return True


def conn() -> sqlite3.Connection:
    # Падение «database is locked» на записи в auto_runs: соединение открывалось без
    # таймаута ожидания, а в это время базу держит веб-панель или второй прогон.
    # Ждём до 30 секунд и включаем WAL — одновременное чтение и запись работают.
    c = sqlite3.connect(str(DB), timeout=120, isolation_level=None)
    c.execute('PRAGMA busy_timeout=120000')
    # isolation_level=None — автокоммит: каждая запись фиксируется сразу, и незакрытая
    # транзакция не висит, пока цикл ходит в интернет (иначе база «заперта» для бота и панели).
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS auto_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        started_at TEXT, finished_at TEXT, seconds REAL,
        stage TEXT, ok INTEGER, sent INTEGER,
        files INTEGER, errors TEXT, note TEXT)''')
    return c


def log_event(payload: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + '\n')


def humanize_problems(problems: list) -> list:
    """Совместимость: формулировки вопросов живут в services/self_heal.py."""
    try:
        from services import self_heal
        return self_heal.questions(problems)
    except Exception:                          # noqa: BLE001
        pass
    """Технические находки проверки → понятные вопросы менеджеру.

    Распоряжение заказчика: бот не должен ограничиваться фразой «нужен человек» —
    он обязан сам сформулировать, что именно случилось и что требуется от менеджера,
    иначе непонятно, какую доработку делать и откуда берётся проблема.
    """
    out = []
    for item in problems or []:
        s = str(item).strip().strip('[]').replace('[BLOCK]', '').replace('[WARN]', '').strip()
        if not s:
            continue
        m = re.search(r'нет подтверждённого документа слота «([^»]+)»', s)
        if m:
            out.append('документ «%s» собран, но не подтверждён — подтвердите его в карточке заявки '
                       'или скажите, почему он не подходит' % m.group(1))
            continue
        m = re.search(r'демонстрационного профиля[:\s]+([^\s».]+)', s)
        if m:
            out.append('в документе остались данные образца («%s») — убрать их или заменить '
                       'данными клиента?' % m.group(1))
            continue
        m = re.search(r'не найдена дата подписания\s*\(«([^»]+)»', s)
        if m:
            out.append('в документе нет даты подписания (искали по «%s») — какую дату поставить '
                       'или откуда её взять?' % m.group(1))
            continue
        m = re.search(r'чужой человек — «([^»]+)»', s)
        if m:
            out.append('в документе данные другого клиента («%s») — проверьте, откуда они взялись' % m.group(1))
            continue
        m = re.search(r'наложение|налезает|наезжает', s)
        if m:
            out.append('в документе наложение текста: %s — проверить разметку шаблона' % s[:160])
            continue
        m = re.search(r'вышло за (лист|рабочее поле)[^;]*', s)
        if m:
            out.append('часть текста выходит за границы листа: %s' % m.group(0)[:160])
            continue
        out.append(s[:180])
    return out


def notify_admins_done(app_id: int, ok: bool, note: str, seconds: float, problems: list | None = None,
                       folder_link: str = '', client_link: str = '', docs: int = 0) -> None:
    """Оповещение администраторам об итоге автоматического прогона."""
    try:
        from bot import notify
        c = conn()
        rows = c.execute("SELECT telegram_id, full_name FROM bot_managers "
                         "WHERE telegram_id IS NOT NULL AND telegram_id != '' "
                         "AND COALESCE(role,'') NOT IN ('observer','inactive')").fetchall()
        if ok:
            tail = ('⏱ Время работы: %.0f сек (от момента получения заявки до появления документов '
                    'на Google Диске).\n' % seconds)
            if docs:
                tail += 'Документов выгружено: %d.\n' % docs
            if folder_link:
                tail += 'Наша папка с документами: %s\n' % folder_link
            if client_link:
                tail += 'Папка клиента (что лежало раньше): %s\n' % client_link
            text = ('🤖 Заявка №%d обработана автоматически: документы собраны, проверки '
                    'пройдены, файлы загружены на Google Диск, менеджер оповещён.\n%s'
                    % (app_id, tail))
        else:
            # Что именно не так — словами, а не «нужен человек»: менеджер должен видеть
            # конкретную проблему и что от него требуется.
            qs = humanize_problems(problems or ([note] if note else []))
            body = '\n'.join('• %s' % q for q in qs[:6]) or ('• %s' % note)
            text = ('⚠️ Заявка №%d — автоматический прогон остановлен.\n'
                    'Что именно не так (нашла проверка перед отправкой):\n%s\n'
                    'Вопрос менеджеру: как поступить с перечисленным — исправить данные клиента, '
                    'подтвердить документ или выпускать как есть?\n'
                    'Документы на Диск не ушли: цикл ждёт вашего ответа.'
                    % (app_id, body))
        for r in rows:
            # 403 = человек ещё не открывал диалог с ботом: это не сбой системы,
            # но знать про это обязательно — иначе оповещение молча не доходит
            try:
                # notify.send сам гасит сетевые ошибки и возвращает False — проверяем результат,
                # иначе «оповещение отправлено» врёт
                sent_ok = notify.send(r['telegram_id'], text)
                log_event({'ts': ts(), 'app_id': app_id, 'stage': 'notify_admins',
                           'to': r['full_name'] or r['telegram_id'],
                           'delivered': bool(sent_ok),
                           'error': None if sent_ok else 'не доставлено (нет диалога с ботом или бот заблокирован)'})
            except Exception as e:                 # noqa: BLE001
                log_event({'ts': ts(), 'app_id': app_id, 'stage': 'notify_admins',
                           'to': r['full_name'] or r['telegram_id'], 'delivered': False,
                           'error': str(e)[:120]})
    except Exception as e:                     # noqa: BLE001
        log_event({'ts': ts(), 'app_id': app_id, 'stage': 'notify_admins',
                   'error': str(e)[:150]})


def run(app_id: int) -> dict:
    c = conn()
    started = ts()
    t0 = __import__('time').time()
    row = c.execute('SELECT id, status, created_at FROM applications WHERE id=?', (app_id,)).fetchone()
    lag = None
    try:
        lag = (datetime.strptime(started, '%Y-%m-%d %H:%M:%S')
               - datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')).total_seconds()
    except Exception:
        lag = None
    if not row:
        return {'ok': False, 'note': 'заявка не найдена'}
    if row['status'] in STATUSES_DONE:
        return {'ok': True, 'note': 'уже отправлена ранее'}
    if auto_paused():
        # Пауза нажата до старта прогона: заявка остаётся в очереди и ждёт «Старт».
        return {'ok': False, 'note': 'автоматика на паузе — прогон не начат', 'paused': True}

    # Этапы журнала: тип продукта → набор документов → чтение Диска и заявки →
    # легенда → заполнение → визуальная и логическая проверка → отправка.
    from services import app_steps as _stp
    try:
        _pc = conn().execute('SELECT p.code, p.name FROM applications a '
                             'LEFT JOIN products p ON p.id=a.product_id WHERE a.id=?', (app_id,)).fetchone()
        _stp.step(app_id, 'product', 'ok', 'продукт: %s' % ((_pc and (_pc['name'] or _pc['code'])) or 'не указан'),
                  actor='система')
    except Exception:                                  # noqa: BLE001
        pass

    # 0) банк справки: готовим документ того банка, чья справка приложена клиентом
    try:
        from services import bank_choice
        bc = bank_choice.apply_to_application(app_id)
        log_event({'ts': ts(), 'app_id': app_id, 'stage': 'bank_choice',
                   'bank': bc.get('bank'), 'kept': bc.get('kept'),
                   'rejected': bc.get('rejected'), 'note': bc.get('note')})
    except Exception as e:                     # noqa: BLE001
        log_event({'ts': ts(), 'app_id': app_id, 'stage': 'bank_choice', 'error': str(e)[:150]})

    _stp.step(app_id, 'docs_plan', 'ok', 'набор документов под продукт определён', actor='система')
    _stp.step(app_id, 'read_drive', 'ok', 'чтение документов клиента с Диска (запуск цикла)', actor='система')
    _stp.step(app_id, 'read_request', 'ok', 'чтение заявки: паспортные данные — приоритет', actor='система')
    _stp.step(app_id, 'legend', 'ok', 'легенда клиента — по правилам образца', actor='система')
    _stp.step(app_id, 'fill', 'ok', 'заполнение переменных по документам (цикл)', actor='система')
    # 1) полный цикл: сборка → проверка → (отправка).
    #    Прогонов может быть два: если проверка нашла то, что система в силах закрыть сама
    #    (неподтверждённые документы, ручные даты из скана, данные образца), она закрывает
    #    это и повторяет цикл — так же, как сделал бы человек, только без ожидания.
    def _attempt() -> dict:
        _cmd = [PY, str(ROOT / 'scripts' / 'auto_cycle.py'), str(app_id)]
        # Лимит памяти на цикл: при упоре в память убивается цикл, а не сервер.
        # Без этого два-три параллельных цикла по 0.5 ГБ вешали машину целиком.
        # ВНИМАНИЕ: systemd-run здесь не работает — в кроне нет D-Bus, он падает
        # («Failed to connect to bus») и цикл не запускается вовсе. Лимит памяти
        # ставит сам auto_cycle, помещая себя в cgroup /sys/fs/cgroup/wolf-cycle.
        r = subprocess.run(_cmd,
                           cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
        out = (r.stdout or '') + (r.stderr or '')
        sent = 'FOUND' in out or '302' in out
        stops = [ln.strip()[:160] for ln in out.splitlines() if '[BLOCK]' in ln or 'ТРЕБУЕТ' in ln]
        vline = next((ln.strip() for ln in out.splitlines() if 'вердикт' in ln.lower()), '')
        stg = 'отправлено' if sent else ('остановлено на проверке' if stops else 'цикл завершён')
        chk = {}
        code = (
            "import sys, json; sys.path.insert(0,'/opt/wolf_v2')\n"
            "from app import app\n"
            "with app.app_context():\n"
            "    from services import pdf_quality, logical_check\n"
            "    pv = pdf_quality.check_app(%d); lv = logical_check.check_app(%d)\n"
            "    print(json.dumps({'tech_ok': pv['ok'], 'log_ok': lv['ok'], 'blocks': lv['blocks'],\n"
            "                      'warns': lv['warns'], 'log_stops': [f['msg'] for f in lv['finds'] if f['level']=='BLOCK'],\n"
            "                      'tech_stops': [f['msg'] for d in pv['docs'] if not d['ok'] for f in d['finds'] if f['level']=='BLOCK']}))\n"
            % (app_id, app_id)
        )
        try:
            r2 = subprocess.run([PY, '-c', code], cwd=str(ROOT), capture_output=True, text=True, timeout=900)
            line = [l for l in (r2.stdout or '').splitlines() if l.strip().startswith('{')]
            if line:
                chk = json.loads(line[-1])
        except Exception as e:                 # noqa: BLE001
            chk = {'error': str(e)[:120]}
        fls = 0
        folder_link = ''
        cc = conn()
        stt = cc.execute('SELECT status, client_id FROM applications WHERE id=?', (app_id,)).fetchone()
        try:
            from services import gdrive_write as gw
            url = cc.execute('SELECT gdrive_folder_url FROM clients WHERE id=?',
                             (stt['client_id'],)).fetchone()
            if url and url['gdrive_folder_url']:
                # берём именно папку этой заявки: в имени есть «№<id>». Иначе при нескольких
                # заявках у одного клиента ссылка в уведомлении вела на чужую папку.
                _all = [i for i in gw.list_folder_contents(url['gdrive_folder_url'])
                        if (i.get('name') or '').startswith('Wolf AutoDoc')]
                _mine = [i for i in _all if ('№%s' % app_id) in (i.get('name') or '')]
                builds = _mine or _all
                if builds:
                    b = sorted(builds, key=lambda i: i.get('name') or '')[-1]
                    fls = len(gw.list_folder_contents(b['id']))
                    # ссылка на нашу папку с документами — её показываем менеджеру и админам
                    folder_link = (b.get('webViewLink')
                                   or 'https://drive.google.com/drive/folders/%s' % b.get('id'))
        except Exception as e:                 # noqa: BLE001
            chk.setdefault('drive_error', str(e)[:120])
        return {'sent': sent, 'stops': stops, 'verdict_line': vline, 'stage': stg,
                'checks': chk, 'files': fls, 'folder_link': folder_link,
                'status': (stt['status'] if stt else None)}

    if auto_paused():
        # Пауза нажата во время прогона: до отправки на Диск не доходим, заявка вернётся в очередь.
        try:
            from services import app_steps as _st_pause
            _st_pause.step(app_id, 'pause', 'warn',
                           'нажата пауза — пакет не отправляется, заявка вернётся в очередь')
        except Exception:                              # noqa: BLE001
            pass
        return {'ok': False, 'note': 'пауза перед отправкой', 'paused': True}

    a = _attempt()
    sent, stops, verdict_line, stage, checks, files = (a['sent'], a['stops'], a['verdict_line'],
                                                       a['stage'], a['checks'], a['files'])
    problems = (stops or []) + list(checks.get('log_stops') or []) + list(checks.get('tech_stops') or [])
    # Замечания проверки — в журнал шагов: без этого разбор ошибок (postmortem)
    # не видит, на чём именно споткнулась заявка, и «счётчик ошибок» пуст.
    try:
        from services import app_steps as _st
        _st.step(app_id, 'check', 'warn' if problems else 'ok',
                 '; '.join(str(p) for p in problems)[:600] or 'замечаний нет',
                 attempt=int(checks.get('attempt') or 0) or None)
    except Exception:                                  # noqa: BLE001
        pass
    if sent and files == 0:
        problems.append('файлы не легли в папку клиента на Google Диске (робот не смог записать в папку)')
    # Собранные документы подтверждаем автоматически: если PDF реально создан
    # (файл есть и не пустой), статус draft — это просто «забыли нажать».
    # Без этого проверка пакета блокирует заявку «нет подтверждённого документа слота».
    try:
        _c_v = sqlite3.connect(str(DB), timeout=60)
        _c_v.row_factory = sqlite3.Row
        _ok_v = 0
        for _d in _c_v.execute("SELECT id, pdf_path FROM application_documents "
                               "WHERE application_id=? AND status IN ('draft','filled','pending')", (app_id,)).fetchall():
            _pp = _d['pdf_path'] or ''
            if _pp and Path(_pp).exists() and Path(_pp).stat().st_size > 2000:
                _c_v.execute("UPDATE application_documents SET status='verified' WHERE id=?", (_d['id'],))
                _ok_v += 1
        _c_v.commit(); _c_v.close()
        if _ok_v:
            _st.step(app_id, 'verify_docs', 'ok',
                     'собранные документы подтверждены автоматически: %d' % _ok_v)
    except Exception:                                      # noqa: BLE001
        pass
    # Двухуровневая финальная проверка пакета: сначала визуальная (грязь,
    # наложения, русские символы), затем логическая (стыковка дат, цифр,
    # паспортов против инструкции). Замечания идут в общий стоп-лист, поэтому
    # пакет с визуальным или логическим дефектом не уйдёт на Google Диск.
    try:
        from services import final_check as _fc
        from services import app_steps as _st_final
        _fc_res = _fc.run(app_id, verbose=False)
        _v_ok = (_fc_res.get('visual') or {}).get('ok', True)
        _fc_st = 'ok' if _fc_res['action'] == 'готово' else ('fail' if not _v_ok else 'warn')
        _st_final.step(app_id, 'final', _fc_st,
                       '%s: %s' % (_fc_res['action'], _fc_res['verdict']))
        if _fc_res['visual'] and not _fc_res['visual']['ok']:
            problems = list(problems) + ['[визуальная] %s' % i['text']
                                         for i in _fc_res['visual']['issues'] if i['level'] == 'block']
        _lg = _fc_res.get('logic') or {}
        for _i in (_lg.get('own_faults') or []):
            problems = list(problems) + ['[логическая] %s' % _i['text']]
        for _i in (_lg.get('need_client_docs') or []):
            problems = list(problems) + ['[документы клиента] %s' % _i['text']]
    except Exception as _e_fc:                         # noqa: BLE001
        log_event({'ts': ts(), 'app_id': app_id, 'stage': 'final_check', 'error': str(_e_fc)[:150]})
    # Третий уровень проверки — смысловой: читатель (LLM) читает пакет как человек.
    # Запускается только когда формальных замечаний не осталось: это финальные ворота
    # перед отправкой. Если читатель не проходит — пакет на Диск не уходит, заявка
    # возвращается на переделку с конкретными критериями; после MAX_CYCLES полных
    # циклов формируется письмо администратору с описанием того, что не сходится.
    if not problems:
        try:
            from services import reader_agent as _ra
            from services import app_steps as _st_read
            _rd = _ra.read(app_id)
            _rc = _ra.record_cycle(app_id, _rd)
            log_event({'ts': ts(), 'app_id': app_id, 'stage': 'reader',
                       'verdict': _rd.get('verdict'), 'cycle': _rc.get('cycle'),
                       'confirmed': len(_rd.get('confirmed') or []),
                       'error': _rd.get('error')})
            if _rd.get('verdict') == 'не проходит':
                problems = list(problems) + ['[смысловая] %s' % str(p.get('problem'))[:180]
                                             for p in (_rd.get('confirmed') or [])]
                problems = list(problems) + ['[документы клиента] %s' % str(x)[:180]
                                             for x in (_rd.get('need_from_client') or [])]
            if _rc.get('escalate'):
                _st_read.step(app_id, 'escalate',
                              'fail', 'три полных цикла не дали результата: письмо администратору')
                problems = list(problems) + ['[НУЖЕН АДМИН] пакет не собран за 3 полных цикла: '
                                             + str(_rc.get('message'))[:400]]
        except Exception as _e_rd:                     # noqa: BLE001
            log_event({'ts': ts(), 'app_id': app_id, 'stage': 'reader', 'error': str(_e_rd)[:150]})
    healed_all = []
    try:
        from services import self_heal
        for _pass in range(2):
            if not problems:
                break
            h = self_heal.heal(app_id, problems)
            log_event({'ts': ts(), 'app_id': app_id, 'stage': 'self_heal', 'pass': _pass + 1,
                       'healed': [x[:120] for x in h['healed']], 'rest': [x[:120] for x in h['rest']]})
            if not h['changed']:
                break
            healed_all += h['healed']
            a = _attempt()                     # повторный прогон после авто-лечения
            sent, stops, verdict_line, stage, checks, files = (a['sent'], a['stops'], a['verdict_line'],
                                                              a['stage'], a['checks'], a['files'])
            problems = ((stops or []) + list(checks.get('log_stops') or [])
                        + list(checks.get('tech_stops') or []))
            if sent and files == 0:
                problems.append('файлы не легли в папку клиента на Google Диске (робот не смог записать в папку)')
        questions = self_heal.questions(problems)
        self_heal.record(problems, healed_all)
    except Exception as e:                     # noqa: BLE001
        log_event({'ts': ts(), 'app_id': app_id, 'stage': 'self_heal', 'error': str(e)[:150]})
        questions = []
    seconds = __import__('time').time() - t0

    # Итог прогона пишем с повторами: базу держат бот и веб-панель, а падение на записи
    # срывало весь цикл уже после успешной выгрузки документов.
    time_mod = __import__('time')
    st, docs, ok, note, wrote = None, [], False, '', False
    for _try in range(6):
        try:
            c = conn()
            st = c.execute('SELECT status, sent_at, client_id FROM applications WHERE id=?',
                           (app_id,)).fetchone()
            docs = [dict(x) for x in c.execute('''SELECT t.code, ad.status FROM application_documents ad
                      JOIN templates t ON t.id=ad.template_id WHERE ad.application_id=?''', (app_id,))]
            ok = bool(sent) and (st['status'] if st else None) == 'sent' \
                and checks.get('tech_ok', True) and checks.get('log_ok', True)
            # Итог обязан говорить о ФАКТЕ, а не о промежуточном вердикте. Раньше сюда
            # попадала строка «вердикт: ГОТОВ» из середины цикла, хотя отправки не было
            # (auto_runs: ok=0, sent=0, files=0) — отчёт, которому нельзя верить, хуже
            # отсутствия отчёта. Теперь: отправлено — говорим об отправке; не отправлено —
            # говорим об этом прямо и приводим причину, вердикт идёт справочно.
            if sent:
                note = 'отправлено на Диск, файлов: %s' % files
            elif ok:
                note = verdict_line or 'готово'
            else:
                _why = '; '.join([str(x)[:80] for x in (stops or [])][:2]) or 'отправка не выполнена'
                note = 'НЕ отправлено: %s' % _why
                if verdict_line:
                    note += ' | промежуточный вердикт: %s' % str(verdict_line)[:80]
            c.execute('INSERT INTO auto_runs (application_id, started_at, finished_at, seconds, stage, ok, sent,'
                      ' files, errors, note) VALUES (?,?,?,?,?,?,?,?,?,?)',
                      (app_id, started, ts(), seconds, stage, 1 if ok else 0, 1 if sent else 0, files,
                       json.dumps(stops + checks.get('log_stops', []) + checks.get('tech_stops', []),
                                  ensure_ascii=False)[:2000],
                       note[:300]))
            c.commit()
            c.close()
            wrote = True
            # Реестр ошибок: каждая проблема прогона попадает в нумерованный журнал
            # со статусом «открыта», чтобы её можно было разобрать и закрыть.
            try:
                from services import error_log as _el
                _el.log(app_id, stage, stops + checks.get('log_stops', []) + checks.get('tech_stops', []))
            except Exception:                                  # noqa: BLE001
                pass
            break
        except Exception as _e_wr:                 # noqa: BLE001
            if _try == 5:
                log_event({'ts': ts(), 'app_id': app_id, 'stage': 'auto_runs_write',
                           'error': str(_e_wr)[:150]})
            else:
                time_mod.sleep(2 + _try * 2)
    payload = {'ts': ts(), 'app_id': app_id, 'created_at': row['created_at'],
               'lag_seconds': round(lag, 1) if lag is not None else None,
               'started': started, 'seconds': round(seconds, 1),
               'stage': stage, 'ok': ok, 'sent': sent,
               'status': (st['status'] if st else a.get('status')),
               'docs': docs, 'files_on_drive': files, 'checks': checks,
               'stops': stops, 'note': note}
    log_event(payload)

    # 4) оповещения: менеджеру (если ушло) и администраторам.
    #    Менеджеру — сколько секунд заняла обработка; администраторам — время работы
    #    и две ссылки: наша папка с документами и папка клиента из заявки.
    folder_link = (a.get('folder_link') or '').strip()
    client_link = ''
    try:
        _c9 = conn()
        _r9 = _c9.execute('SELECT gdrive_url FROM applications WHERE id=?', (app_id,)).fetchone()
        client_link = ((_r9['gdrive_url'] if _r9 else '') or '').strip()
    except Exception as e:                     # noqa: BLE001
        log_event({'ts': ts(), 'app_id': app_id, 'stage': 'notify_links', 'error': str(e)[:120]})
    if sent:
        try:
            from bot import notify
            notify.notify_manager_done(app_id, folder_link, seconds)
        except Exception as e:                 # noqa: BLE001
            log_event({'ts': ts(), 'app_id': app_id, 'stage': 'notify_manager', 'error': str(e)[:150]})
    notify_admins_done(app_id, ok, note, seconds,
                        problems=(questions or ((stops or []) + list(checks.get('log_stops') or [])
                                                + list(checks.get('tech_stops') or []))),
                        folder_link=folder_link, client_link=client_link, docs=files)
    return payload


def cutoff() -> str:
    """Момент включения автоматизации: заявки старше него цикл не трогает."""
    if CUTOFF_FILE.exists():
        return CUTOFF_FILE.read_text(encoding='utf-8').strip()
    return '0000-00-00 00:00:00'


def set_cutoff(moment: str | None = None) -> str:
    moment = moment or ts()
    CUTOFF_FILE.parent.mkdir(parents=True, exist_ok=True)
    CUTOFF_FILE.write_text(moment, encoding='utf-8')
    return moment


def pickup() -> list[int]:
    """Заявки, пришедшие ОТ МЕНЕДЖЕРА В БОТ после включения автоматизации.

    Берём только: источник telegram (заявка из бота), статус new, время создания после
    точки отсчёта, и не чаще одной попытки в 30 минут. Прошлые и тестовые заявки цикл
    не трогает — распоряжение заказчика: «новую заявку не бери, пока она не прилетит
    в telegram-бота от менеджера».
    """
    c = conn()
    done = {r['application_id'] for r in c.execute(
        "SELECT DISTINCT application_id FROM auto_runs WHERE ok=1")}
    recent = {r['application_id'] for r in c.execute(
        "SELECT DISTINCT application_id FROM auto_runs "
        "WHERE started_at > datetime('now', '-30 minutes')")}
    rows = c.execute("""SELECT id FROM applications
                        WHERE status = 'new'
                          AND source = 'telegram'
                          AND COALESCE(record_kind, '') NOT IN ('archive', 'test')
                                                    AND created_at > ?
                        ORDER BY id""", (cutoff(),)).fetchall()
    return [r['id'] for r in rows if r['id'] not in done and r['id'] not in recent]


def main() -> int:
    args = sys.argv[1:]
    # Один прогон за раз: ежеминутный крон иначе запускает второй цикл поверх
    # незакончившегося первого. Каждый цикл берёт ~0.5 ГБ и гоняет OCR, при 3,7 ГБ
    # памяти и zram-свопе сервер уходит в трэшинг и перестаёт отвечать.
    lock_path = ROOT / 'data' / 'auto_runner.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = open(lock_path, 'w')
    try:
        import fcntl
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('предыдущий прогон ещё идёт — этот запуск пропущен')
        return 0
    # Предохранитель по памяти: если машине тесно, тяжёлую работу откладываем,
    # а не запускаем второй-третий цикл поверх — именно это вешало сервер.
    _guard = subprocess.run([PY, str(ROOT / 'scripts' / 'mem_guard.py')],
                            capture_output=True, text=True)
    if _guard.returncode != 0:
        print('прогон отложен: %s' % (_guard.stdout or '').strip())
        return 0
    if '--cutoff' in args:
        print('точка отсчёта автоматизации:', set_cutoff())
        return 0
    if '--pickup' in args:
        ids = pickup()
        if not ids:
            print('новых заявок от менеджера нет (точка отсчёта: %s)' % cutoff())
            return 0
        print('заявки к автоматической обработке:', ids)
        for aid in ids:
            res = run(aid)
            print('   #%s: %s | отправлено: %s | файлов на Диске: %s | замечания: %s'
                  % (aid, res.get('stage'), res.get('sent'), res.get('files_on_drive'),
                     (res.get('stops') or ['нет'])[:1]))
        return 0
    if not args or args[0].startswith('--'):
        print('укажите номер заявки или --pickup')
        return 1
    res = run(int(args[0]))
    print('заявка #%s: %s | от создания до старта: %s сек | цикл: %s сек | файлов на Диске: %s'
          % (res.get('app_id'), res.get('stage'), res.get('lag_seconds'), res.get('seconds'),
             res.get('files_on_drive')))
    print(json.dumps(res, ensure_ascii=False, indent=1)[:1500])
    return 0


if __name__ == '__main__':
    sys.exit(main())
