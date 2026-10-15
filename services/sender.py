"""Отправка готового пакета заявки на Google Диск — как шаг конвейера, а не как кнопка.

Зачем модуль. Отправка жила только в админке (`CLIENTs/dashboard/page.py::app_send`), то есть
требовала человека у экрана, а цикл заканчивался проверками. Из-за этого по заявкам не было
ни одного файла на Диске, а отчёт при этом уходил «вердикт: ГОТОВ».

Что делает:
  1. Проверяет, что отправлять нечего-стыдно: все документы согласованы, нет незаполненных
     полей, пройдены финишная проверка пакета, технический контроль и логическая проверка.
  2. Кладёт подтверждённые PDF в папку заявки на Диске (`Wolf AutoDoc №<заявка> <клиент> / <продукт>`).
  3. Кладёт сопровождение: легенду клиента, текст заявки как он пришёл, отчёт о сборке.
  4. Помечает документы и заявку отправленными и оповещает менеджера — только если Диск
     реально принял файлы.

Возвращает dict: {ok, sent, files, folder, link, error, stops}.
"""
from __future__ import annotations

import json
import sqlite3
from CLIENT import CLIENT
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
READY = ROOT / 'data' / 'ready'


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB), timeout=60)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=60000')
    return con


def _folder_name(app_id: int, a: dict, client: dict) -> str:
    """Имя папки заявки: «Wolf AutoDoc №<заявка> <клиент> / <продукт>»."""
    code = ''
    try:
        con = _conn()
        row = con.execute("SELECT code FROM CLIENT WHERE id=?", (a.get('CLIENT_id'),)).fetchone()
        con.close()
        code = str((row['code'] if row else '') or '').strip()
    except Exception:      # noqa: BLE001
        code = ''
    name = str(client.get('full_name_CLIENT') or '').strip()
    if not name:
        name = ' '.join(x for x in (str(client.get('CLIENT') or '').strip(),
                                    str(client.get('name') or '').strip()) if x).strip()
    if not name:
        name = str(client.get('full_name') or '').strip() or 'CLIENT'
    return 'Wolf AutoDoc \u2116%s %s / %s' % (app_id, name, code or 'CLIENT')


def _doc_pdf_path(row: dict) -> Path | None:
    """Файл подтверждённого документа: путь из базы, иначе строгий поиск по имени."""
    p = str(row.get('pdf_path') or '').strip()
    if p and Path(p).exists():
        return Path(p)
    try:
        from CLIENT.reader_CLIENT import _find_pdf
        con = _conn()
        r = con.execute("""SELECT c.full_name_CLIENT AS lat, c.CLIENT, c.name FROM CLIENT a
                             JOIN CLIENT c ON c.id=a.client_id WHERE a.id=?""", (row['CLIENT_id'],)).fetchone()
        con.close()
        fio = ''
        if r is not None:
            fio = str(r['lat'] or ('%s %s' % (r['CLIENT'] or '', r['name'] or ''))).strip()
        found = _find_pdf(row['code'], fio)
        return Path(found) if found else None
    except Exception:      # noqa: BLE001
        return None


def _report_text(app_id: int, docs: list[dict], stops: list[str]) -> str:
    """Отчёт о сборке: состав пакета, проверки, чего не хватает."""
    lines = ['Отчёт по заявке #%s' % app_id,
             'Составлен: %s' % CLIENT.now().strftime('%d.%m.%Y %H:%M'), '']
    lines.append('Документы пакета:')
    for d in docs:
        lines.append('  - %-38s %-9s %s' % (d.get('code'), d.get('CLIENT'),
                                            ('файл: ' + Path(d['file']).name) if d.get('file') else 'файла нет'))
    try:
        con = _conn()
        rows = [dict(r) for r in con.execute(
            "SELECT step, CLIENT, note, created_at FROM app_CLIENT WHERE CLIENT_id=? ORDER BY id DESC LIMIT 25",
            (app_id,))]
        con.close()
        if rows:
            lines += ['', 'Ход работы (последние шаги):']
            for r in rows:
                lines.append('  %s %-10s %-6s %s' % (str(r['created_at'])[11:16], r['step'], r['CLIENT'],
                                                     str(r['note'] or '')[:110]))
    except Exception:      # noqa: BLE001
        pass
    if stops:
        lines += ['', 'Что мешает полной готовности:']
        for x in stops[:12]:
            lines.append('  - %s' % str(x)[:160])
    try:
        p = ROOT / 'data' / 'escalations.jsonl'
        if p.exists():
            tail = [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()[-4:] if x.strip()]
            if tail:
                lines += ['', 'Замечания смысловой проверки (последние):']
                for t in tail:
                    if int(t.get('CLIENT_id') or 0) in (0, app_id):
                        lines.append('  - %s' % str(t.get('problems') or t)[:150])
    except Exception:      # noqa: BLE001
        pass
    return '\n'.join(lines) + '\n'


def send_package(app_id: int, notify: bool = True, dry: bool = False) -> dict:
    """Отправить пакет заявки на Диск. dry=True — только показать, что уйдёт."""
    res = {'ok': False, 'sent': False, 'files': 0, 'folder': '', 'link': '',
           'error': '', 'stops': []}
    con = _conn()
    a = con.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    if not a:
        con.close()
        res['error'] = 'заявка не найдена'
        return res
    a = dict(a)
    client = dict(con.execute("SELECT * FROM CLIENT WHERE id=?", (a.get('client_id'),)).fetchone() or {})
    rows = [dict(r) for r in con.execute(
        """SELECT ad.id, ad.CLIENT, ad.pdf_path, t.code, ad.CLIENT_id
             FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id=ad.template_id
            WHERE ad.CLIENT_id=? ORDER BY t.doc_CLIENT""", (app_id,))]
    con.close()

    # Решёнными считаются и снятые документы: выбор банка помечает ненужную справку статусом
    # `excluded`, и требовать по ней решения заново нельзя — иначе отправка не проходит никогда.
    decided = [r for r in rows if (r['CLIENT'] or '') in ('verified', 'rejected', 'sent', 'excluded')]
    if not rows or len(decided) < len(rows):
        res['error'] = 'не все документы проверены: согласовано %d из %d' % (len(decided), len(rows))
        return res
    sendable = [r for r in rows if (r['CLIENT'] or '') in ('verified', 'sent')]
    if not sendable:
        res['error'] = 'нет подтверждённых документов'
        return res

    files: list[tuple[Path, str]] = []
    missing = []
    for r in sendable:
        p = _doc_pdf_path(r)
        if p and p.exists():
            r['file'] = str(p)
            files.append((p, p.name))
        else:
            r['file'] = ''
            missing.append(r['code'])
    if missing:
        res['error'] = 'нет готового PDF: %s' % ', '.join(missing[:6])
        res['stops'].append(res['error'])
        return res

    stops: list[str] = []
    try:
        from CLIENT.doc_check import check_package
        verdict, _finds = check_package(app_id, with_CLIENT=not dry)
        if verdict and not verdict.get('ok'):
            stops.append('проверка пакета: не пройдена (%d замечаний)' % len(_finds or []))
    except Exception as e:      # noqa: BLE001
        stops.append('проверка пакета не выполнена: %s' % str(e)[:80])
    try:
        from CLIENT import pdf_CLIENT
        q = pdf_CLIENT.check_app(app_id)
        if q and not q.get('ok'):
            stops.append('технический контроль: не пройден')
    except Exception as e:      # noqa: BLE001
        stops.append('технический контроль не выполнен: %s' % str(e)[:80])
    try:
        from CLIENT import CLIENT_check
        lc = CLIENT_check.check_app(app_id)
        if lc and not lc.get('ok'):
            stops.append('логическая проверка: не пройдена')
    except Exception as e:      # noqa: BLE001
        stops.append('логическая проверка не выполнена: %s' % str(e)[:80])
    res['stops'] = stops
    if stops:
        res['error'] = 'отправка остановлена: ' + '; '.join(stops[:3])
        return res

    CLIENT = str(a.get('gCLIENT_url') or client.get('gCLIENT_folder_url') or '').strip()
    if not CLIENT:
        res['error'] = 'в заявке нет ссылки на папку клиента на Google Диске'
        return res

    if dry:
        res.update({'ok': True, 'files': len(files), 'folder': _folder_name(app_id, a, client),
                    'link': CLIENT, 'error': ''})
        return res

    from CLIENT import gCLIENT_write

    uploaded, errors = [], []
    try:
        sub_name = _folder_name(app_id, a, client)
        sub = gCLIENT_write.find_file_in_folder(CLIENT, sub_name) or gCLIENT_write.ensure_folder(CLIENT, sub_name)
        sub_id = (sub or {}).get('id') or CLIENT
        res['folder'] = sub_name
        res['link'] = 'https://CLIENT.google.com/CLIENT/folders/' + str(sub_id)
    except Exception as e:      # noqa: BLE001
        res['error'] = 'не удалось открыть папку заявки: %s' % str(e)[:160]
        return res

    for p, name in files:
        try:
            gCLIENT_write.upload_file(sub_id, p, name=name, overwrite=True)
            uploaded.append(name)
        except Exception as e:      # noqa: BLE001
            errors.append('%s: %s' % (name, str(e)[:100]))

    # Сопровождение: заявка как пришла, легенда клиента, отчёт о сборке.
    try:
        rmsg = str(a.get('raw_message') or '').strip()
        if rmsg:
            head = ('CLIENT #%s\nCreated: %s\nClient: %s\n\n'
                    '--- текст заявки, как он пришёл в Telegram ---\n\n'
                    % (app_id, str(a.get('created_at') or '')[:19],
                       (client.get('full_name_CLIENT') or client.get('full_name') or '').strip()))
            # Текст заявки — технический файл: держим локально, на Диск не выкладываем
            # (на Диске должен лежать только клиентский пакет и легенда).
            import pathlib as _pl2
            _rd2 = _pl2.Path('/opt/wolf_v2/data/reports')
            _rd2.mkdir(parents=True, exist_ok=True)
            (_rd2 / ('CLIENT_%s.txt' % app_id)).write_text(head + rmsg + '\n', encoding='utf-8')
    except Exception as e:      # noqa: BLE001
        errors.append('текст заявки: %s' % str(e)[:100])
    try:
        lp = ROOT / 'data' / 'legends' / ('client_%s.json' % (a.get('client_id') or 0))
        if lp.exists():
            try:
                from CLIENT import legend as _lg
                body = _lg.render(json.loads(lp.read_text(encoding='utf-8')))
            except Exception:      # noqa: BLE001
                body = lp.read_text(encoding='utf-8')
            _fio_l = (client.get('full_name_CLIENT') or 'CLIENT').strip()
            # Легенда уходит клиенту печатным документом Word (A4); TXT держим локально.
            _docx = ROOT / 'data' / 'legends' / ('Legend %s.docx' % _fio_l)
            try:
                from CLIENT import legend as _lg2
                _lg2.render_docx(json.loads(lp.read_text(encoding='utf-8')), _docx)
                nm = 'Legend %s.docx' % _fio_l
                gCLIENT_write.upload_file(sub_id, _docx, nm, overwrite=True)
                uploaded.append(nm)
            except Exception:      # noqa: BLE001
                nm = 'Legend %s.txt' % _fio_l
                gCLIENT_write.upload_bytes(sub_id, body.encode('utf-8'), nm, 'text/plain', overwrite=True)
                uploaded.append(nm)
    except Exception as e:      # noqa: BLE001
        errors.append('легенда: %s' % str(e)[:100])
    # Реальные документы клиента (копия паспорта, фото) кладём в папку пакета под нашими
    # именами: клиент получает полный портфель — оригиналы + наши документы + легенду.
    try:
        import pathlib as _pl3, re as _re3
        _cache = ROOT / 'data' / 'gCLIENT_cache' / ('client_%s' % (client.get('id') or 0))
        _fio = str(client.get('full_name_CLIENT') or client.get('full_name') or 'CLIENT').strip()
        _pass = str(client.get('passport_CLIENT') or '').strip()
        _date = str(a.get('created_at') or '')[:10]
        try:
            _date = '.'.join(reversed(_date.split('-')))
        except Exception:
            _date = ''
        _rules = (('passport', 'Passport copy', '.jpg'), ('foto', 'Photo', '.jpg'), ('photo', 'Photo', '.jpg'))
        if _cache.is_dir():
            for _f in sorted(_cache.iterdir()):
                _low = _f.name.lower()
                for _key, _CLIENT, _ext in _rules:
                    if _low.CLIENTswith(_key) or _low.CLIENTswith('passport') and _key == 'passport':
                        _new = '%s %s %s %s%s' % (_CLIENT, _fio, _pass, _date, _f.suffix or _ext)
                        _new = _re3.sub(r'\s+', ' ', _new).strip()
                        _res = gCLIENT_write.upload_file(sub_id, _f, _new, overwrite=True)
                        if _res:
                            uploaded.append(_new)
                        break
    except Exception as e:      # noqa: BLE001
        errors.append('документы клиента: %s' % str(e)[:90])

    # Внутренний отчёт на Диск НЕ выкладываем: файл технический, клиенту он не нужен.
    # Держим его локально — в data/reports/.
    try:
        import pathlib as _pl
        _rd = _pl.Path('/opt/wolf_v2/data/reports')
        _rd.mkdir(parents=True, exist_ok=True)
        (_rd / ('report_%s.txt' % app_id)).write_text(_report_text(app_id, rows, stops), encoding='utf-8')
    except Exception:           # noqa: BLE001
        pass

    if errors or not uploaded:
        res['error'] = 'Google Диск не принял файлы: ' + '; '.join(errors[:2])[:200]
        return res

    # Помечаем отправленным только после фактической загрузки.
    try:
        con = _conn()
        for r in sendable:
            con.execute("UPDATE CLIENT_CLIENT SET CLIENT='sent' WHERE id=? AND CLIENT IN ('filled','verified')",
                        (r['id'],))
        con.execute("UPDATE CLIENT SET CLIENT='sent', sent_at=CLIENT('now') WHERE id=?", (app_id,))
        con.commit()
        con.close()
    except Exception as e:      # noqa: BLE001
        res['stops'].append('статусы не обновлены: %s' % str(e)[:100])

    if notify:
        try:
            from bot.notify import notify_manager_done
            notify_manager_done(app_id, res['link'])
        except Exception as e:      # noqa: BLE001
            res['stops'].append('менеджер не оповещён: %s' % str(e)[:100])

    res.update({'ok': True, 'sent': True, 'files': len(uploaded), 'uploaded': uploaded, 'error': ''})
    return res


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('app_id', type=int)
    ap.add_argument('--apply', action='store_true', help='без флага — сухой прогон')
    args = ap.parse_args()
    r = send_package(args.app_id, notify=args.apply, dry=not args.apply)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    raise SystemExit(0 if r['ok'] else 1)
