"""Отправка готового пакета заявки на Google Диск — как шаг конвейера, а не как кнопка.

Зачем модуль. Отправка жила только в админке (`blocks/dashboard/page.py::app_send`), то есть
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
from datetime import datetime
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
        row = con.execute("SELECT code FROM products WHERE id=?", (a.get('product_id'),)).fetchone()
        con.close()
        code = str((row['code'] if row else '') or '').strip()
    except Exception:      # noqa: BLE001
        code = ''
    name = str(client.get('full_name_latin') or '').strip()
    if not name:
        name = ' '.join(x for x in (str(client.get('surname') or '').strip(),
                                    str(client.get('name') or '').strip()) if x).strip()
    if not name:
        name = str(client.get('full_name') or '').strip() or 'CLIENT'
    return 'Wolf AutoDoc \u2116%s %s / %s' % (app_id, name, code or 'PRODUCT')


def _doc_pdf_path(row: dict) -> Path | None:
    """Файл подтверждённого документа: путь из базы, иначе строгий поиск по имени."""
    p = str(row.get('pdf_path') or '').strip()
    if p and Path(p).exists():
        return Path(p)
    try:
        from services.reader_agent import _find_pdf
        con = _conn()
        r = con.execute("""SELECT c.full_name_latin AS lat, c.surname, c.name FROM applications a
                             JOIN clients c ON c.id=a.client_id WHERE a.id=?""", (row['application_id'],)).fetchone()
        con.close()
        fio = ''
        if r is not None:
            fio = str(r['lat'] or ('%s %s' % (r['surname'] or '', r['name'] or ''))).strip()
        found = _find_pdf(row['code'], fio)
        return Path(found) if found else None
    except Exception:      # noqa: BLE001
        return None


def _report_text(app_id: int, docs: list[dict], stops: list[str]) -> str:
    """Отчёт о сборке: состав пакета, проверки, чего не хватает."""
    lines = ['Отчёт по заявке #%s' % app_id,
             'Составлен: %s' % datetime.now().strftime('%d.%m.%Y %H:%M'), '']
    lines.append('Документы пакета:')
    for d in docs:
        lines.append('  - %-38s %-9s %s' % (d.get('code'), d.get('status'),
                                            ('файл: ' + Path(d['file']).name) if d.get('file') else 'файла нет'))
    try:
        con = _conn()
        rows = [dict(r) for r in con.execute(
            "SELECT step, status, note, created_at FROM app_steps WHERE application_id=? ORDER BY id DESC LIMIT 25",
            (app_id,))]
        con.close()
        if rows:
            lines += ['', 'Ход работы (последние шаги):']
            for r in rows:
                lines.append('  %s %-10s %-6s %s' % (str(r['created_at'])[11:16], r['step'], r['status'],
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
                    if int(t.get('application_id') or 0) in (0, app_id):
                        lines.append('  - %s' % str(t.get('problems') or t)[:150])
    except Exception:      # noqa: BLE001
        pass
    return '\n'.join(lines) + '\n'


def send_package(app_id: int, notify: bool = True, dry: bool = False) -> dict:
    """Отправить пакет заявки на Диск. dry=True — только показать, что уйдёт."""
    res = {'ok': False, 'sent': False, 'files': 0, 'folder': '', 'link': '',
           'error': '', 'stops': []}
    con = _conn()
    a = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not a:
        con.close()
        res['error'] = 'заявка не найдена'
        return res
    a = dict(a)
    client = dict(con.execute("SELECT * FROM clients WHERE id=?", (a.get('client_id'),)).fetchone() or {})
    rows = [dict(r) for r in con.execute(
        """SELECT ad.id, ad.status, ad.pdf_path, t.code, ad.application_id
             FROM application_documents ad JOIN templates t ON t.id=ad.template_id
            WHERE ad.application_id=? ORDER BY t.doc_index""", (app_id,))]
    con.close()

    # Решёнными считаются и снятые документы: выбор банка помечает ненужную справку статусом
    # `excluded`, и требовать по ней решения заново нельзя — иначе отправка не проходит никогда.
    decided = [r for r in rows if (r['status'] or '') in ('filled', 'verified', 'rejected', 'sent', 'excluded')]
    if not rows or len(decided) < len(rows):
        res['error'] = 'не все документы проверены: согласовано %d из %d' % (len(decided), len(rows))
        return res
    sendable = [r for r in rows if (r['status'] or '') in ('filled', 'verified', 'sent')]
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
        from services.doc_check import check_package
        verdict, _finds = check_package(app_id, with_drive=not dry)
        if verdict and not verdict.get('ok'):
            stops.append('проверка пакета: не пройдена (%d замечаний)' % len(_finds or []))
    except Exception as e:      # noqa: BLE001
        stops.append('проверка пакета не выполнена: %s' % str(e)[:80])
    try:
        from services import pdf_quality
        q = pdf_quality.check_app(app_id)
        if q and not q.get('ok'):
            stops.append('технический контроль: не пройден')
    except Exception as e:      # noqa: BLE001
        stops.append('технический контроль не выполнен: %s' % str(e)[:80])
    try:
        from services import logical_check
        lc = logical_check.check_app(app_id)
        if lc and not lc.get('ok'):
            stops.append('логическая проверка: не пройдена')
    except Exception as e:      # noqa: BLE001
        stops.append('логическая проверка не выполнена: %s' % str(e)[:80])
    res['stops'] = stops
    if stops:
        res['error'] = 'отправка остановлена: ' + '; '.join(stops[:3])
        return res

    drive = str(a.get('gdrive_url') or client.get('gdrive_folder_url') or '').strip()
    if not drive:
        res['error'] = 'в заявке нет ссылки на папку клиента на Google Диске'
        return res

    if dry:
        res.update({'ok': True, 'files': len(files), 'folder': _folder_name(app_id, a, client),
                    'link': drive, 'error': ''})
        return res

    from services import gdrive_write

    uploaded, errors = [], []
    try:
        sub_name = _folder_name(app_id, a, client)
        sub = gdrive_write.find_file_in_folder(drive, sub_name) or gdrive_write.ensure_folder(drive, sub_name)
        sub_id = (sub or {}).get('id') or drive
        res['folder'] = sub_name
        res['link'] = 'https://drive.google.com/drive/folders/' + str(sub_id)
    except Exception as e:      # noqa: BLE001
        res['error'] = 'не удалось открыть папку заявки: %s' % str(e)[:160]
        return res

    # Имя файла на Диске должно быть стабильным: убираем служебный хвост времени
    # («… 17.10.2026 113014.pdf»), иначе при повторном прогоне появляются дубли.
    import re as _re_names
    for p, name in files:
        try:
            name = _re_names.sub(r" (\d{6})(\.pdf)$", r"\2", str(name))
            gdrive_write.upload_file(sub_id, p, name=name, overwrite=True)
            uploaded.append(name)
        except Exception as e:      # noqa: BLE001
            errors.append('%s: %s' % (name, str(e)[:100]))

    # Сопровождение: заявка как пришла, легенда клиента, отчёт о сборке.
    try:
        rmsg = str(a.get('raw_message') or '').strip()
        if rmsg:
            head = ('Application #%s\nCreated: %s\nClient: %s\n\n'
                    '--- текст заявки, как он пришёл в Telegram ---\n\n'
                    % (app_id, str(a.get('created_at') or '')[:19],
                       (client.get('full_name_latin') or client.get('full_name') or '').strip()))
            # Текст заявки — технический файл: держим локально, на Диск не выкладываем
            # (на Диске должен лежать только клиентский пакет и легенда).
            import pathlib as _pl2
            _rd2 = _pl2.Path('/opt/wolf_v2/data/reports')
            _rd2.mkdir(parents=True, exist_ok=True)
            (_rd2 / ('application_%s.txt' % app_id)).write_text(head + rmsg + '\n', encoding='utf-8')
    except Exception as e:      # noqa: BLE001
        errors.append('текст заявки: %s' % str(e)[:100])
    try:
        lp = ROOT / 'data' / 'legends' / ('client_%s.json' % (a.get('client_id') or 0))
        if lp.exists():
            lg = json.loads(lp.read_text(encoding='utf-8'))
            if not str(lg.get('application_text') or '').strip():
                lg['application_text'] = str(a.get('raw_message') or '')
            try:
                from services import legend as _lg
                body = _lg.render(lg)
            except Exception:      # noqa: BLE001
                body = lp.read_text(encoding='utf-8')
            nm = 'Wolf AutoDoc \u2116%s.txt' % app_id
            gdrive_write.upload_bytes(sub_id, body.encode('utf-8'), nm, 'text/plain', overwrite=True)
            uploaded.append(nm)
    except Exception as e:      # noqa: BLE001
        errors.append('легенда: %s' % str(e)[:100])

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
            con.execute("UPDATE application_documents SET status='sent' WHERE id=? AND status IN ('filled','verified')",
                        (r['id'],))
        # Заявка → в архив (история) ТОЛЬКО при чистой отправке.
        # Правило 17.10.2026: в архив попадают только полностью прошедшие цикл
        # заявки без ошибок. Если документы отправлены с ошибкой или некорректно —
        # админ достаёт вручную через app_restart.
        con.execute("UPDATE applications SET status='sent', sent_at=datetime('now'), "
                    "record_kind='archive' WHERE id=?", (app_id,))
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
