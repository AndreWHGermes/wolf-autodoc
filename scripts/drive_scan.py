#!/usr/bin/env python3
"""Автономный разбор документов клиента с Google Drive (запускается в фоне по кнопке).

Использование: /usr/bin/python3 /opt/wolf_v2/scripts/drive_scan.py <application_id>
"""
import sys, os, json, sqlite3, subprocess, time, re, datetime
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
sys.path.insert(0, '/opt/wolf_v2/bot')
sys.path.insert(0, '/opt/wolf_v2/blocks')

DB = '/opt/wolf_v2/data/wolf.db'
CACHE = Path('/opt/wolf_v2/data/gdrive_cache')


def conn():
    c = sqlite3.connect(DB, timeout=120)
    c.row_factory = sqlite3.Row
    # Сборка и разбор документов могут идти одновременно: без busy_timeout
    # разбор падал на «database is locked» и заявка оставалась без документов.
    c.execute('PRAGMA busy_timeout=120000')
    c.execute('PRAGMA journal_mode=WAL')
    return c


def fetch_docs(client_id: int, url: str):
    d = CACHE / f'client_{client_id}'
    files = [f for f in d.rglob('*') if f.is_file()] if d.is_dir() else []
    if not files and url and 'drive.google.com' in url:
        sys.path.insert(0, '/opt/wolf_v2')
        d.mkdir(parents=True, exist_ok=True)
        from services import gdrive_api as api
        if api.available():
            # авторизованный доступ от имени робота: лимиты высокие,
            # ограничитель и откаты не нужны
            got = api.sync_folder(url, d)
            files = [f for f in d.rglob('*') if f.is_file()]
            if not got and not files:
                raise RuntimeError('робот не видит файлов в папке клиента')
        else:
            # запасной путь: анонимно, только по разрешению ограничителя
            from services import drive_throttle as thr
            if not thr.acquire(wait=True, max_wait=600):
                raise RuntimeError('Google ограничил обращения к Диску — попробуем позже')
            subprocess.run(['/usr/bin/python3', '-m', 'gdown', '--folder', url, '-O', str(d), '--quiet'],
                           timeout=600, check=False)
            files = [f for f in d.rglob('*') if f.is_file()]
            if files:
                thr.report_ok()
            else:
                thr.report_fail('Google не отдал файлы папки')
    # берём ВСЕ файлы клиента: попадаются файлы без расширения и HEIC с телефона,
    # поэтому тип определяем по содержимому, а не по имени
    skip = ('.ds_store', 'thumbs.db', '.ini')
    return [f for f in files if f.name.lower() not in skip and not f.name.startswith('.')][:24]


# ---- тип документа определяем сами: по имени файла и по шапке текста ----

_DOC_KINDS = [
    # банковские документы и ВНЖ идут ПЕРВЫМИ: их признаки точнее, а слова
    # «российская федерация» и «passport» встречаются и в справках банка —
    # из-за этого справка раньше определялась как паспорт и давала выдуманные данные
    ("bank_balance", ("доступном остатке", "доступный остаток", "available balance", "balance",
                      "справка о доступном", "bankstatement", "bank_statement", "personalbank",
                      "personal bank", "остатке.pdf", "остаток")),
    ("bank_movement", ("движении средств", "движение средств", "statement of account",
                       "funds_movement", "funds movement", "выписка")),
    # свидетельство о рождении: в папке клиента это документ ребёнка, и его даты
    # нельзя путать с датами клиента — поэтому тип нужен отдельный
    ("birth_certificate", ("свидетельство о рождении", "о рождении", "birth certificate",
                           "акта о рождении", "act of birth")),
    # индонезийская eVisa: в её тексте есть и «stay permit», и «passport»,
    # поэтому проверять её надо раньше ВНЖ и паспорта, иначе поля теряются.
    # Из признаков убраны «bridging» и «e33g»: они есть в письмах и договорах,
    # и по ним письмо родителя опознавалось как виза
    ("visa", ("evisa", "visa no", "nomor visa", "limited stay visa", "kementerian imigrasi",
              "direktorat jenderal imigrasi", "виза")),
    ("itk", ("itk", "итк", "трудовая", "permit number", "stay permit")),
    ("passport", ("паспорт", "passport")),
    ("photo", ("foto", "photo", "фото")),
    ("contract", ("contract", "agreement", "договор")),
    ("resume", ("resume", "резюме", "cv")),
]

# строка машиночитаемой зоны паспорта: заглавные латиница/цифры и «<»
_MRZ_LINE = __import__('re').compile(r'^[A-Z0-9<]{25,}$', __import__('re').M)


def doc_kind_name(path, text: str = "") -> str:
    """Что это за документ.

    Порядок: имя файла (самый надёжный признак) → текст внутри.
    Важно: имя файла проверяем ДО текста — у паспорта-фотографии текста
    может не быть вовсе, а имя «PASSPORT - …» всё равно говорит, что это паспорт.
    """
    name = Path(path).name.lower()
    for code, keys in _DOC_KINDS:
        if any(k in name for k in keys):
            return code
    t = (text or "")[:1500]
    low = t.lower()
    for code, keys in _DOC_KINDS:
        if any(k in low for k in keys):
            return code
    # свободный «passport» в тексте — признак слабый: надёжно только по полосе MRZ
    if any(_MRZ_LINE.match(ln.strip()) for ln in (text or "").splitlines()):
        return "passport"
    return "other"


DOC_KIND_RU = {
    "passport": "Паспорт", "bank_balance": "Справка о доступном остатке",
    "bank_movement": "Справка о движении средств", "photo": "Фотография клиента",
    "contract": "Договор", "itk": "ИТК (разрешение на пребывание в Индонезии)",
    "resume": "Резюме", "birth_certificate": "Свидетельство о рождении",
    "visa": "Виза", "other": "Документ",
}

def extract(path: Path) -> dict:
    from bot.ai_parser import _call_llm
    from services.doc_read import read_text
    # PDF с текстовым слоем читаем напрямую, сканы и фото (PNG/JPG/HEIC) — через OCR
    try:
        text = read_text(path) or ''
    except Exception as e:  # noqa: BLE001
        text = f'(ошибка чтения: {e})'
    if not text.strip():
        text = '(текст из документа извлечь не удалось)'
    # Паспорт: подмешиваем машиночитаемую зону, прочитанную отдельным проходом.
    # Общее распознавание страницы эту полосу часто портит (мелкий шрифт, голограмма),
    # а в ней самое надёжное имя и фамилия латиницей.
    try:
        _low = (path.name + ' ' + (text or '')[:400]).lower()
        if 'passport' in _low or 'паспорт' in _low:
            from services.doc_read import mrz_text
            _mrz = mrz_text(path)
            if _mrz:
                text = (text or '') + '\n' + _mrz
    except Exception:
        pass
    prompt = (
        'Ты обрабатываешь документы клиента визового агентства (виза Индонезии).\n'
        'Ниже текст документа. Вытащи ВСЕ значимые данные: ФИО латиницей ЦЕЛИКОМ — имя, фамилия И ОТЧЕСТВО '
        '(отчество = patronymic / middle name: например «Маркарова Анна Рудольфовна» → full_name_ru, '
        'а отчество отдельно → patronymic = «Рудольфовна» / Rudolfovna при транслитерации). '
        'Дата и место рождения, '
        'паспорт, гражданство, адрес, телефон, e-mail, банк, номера счетов, суммы и остатки, '
        'номера документов и даты, названия компаний, должности.\n'
        'Для КАЖДОГО значения укажи переменную конструктора, которой оно соответствует по смыслу '
        '(full_name_latin, full_name_ru, patronymic, date_of_birth, place_of_birth, passport_number, nationality, address_live, '
        'phone, email, bank_name, account_no, balance_rub, balance_date, period_from, period_to, '
        'doc_no, doc_date, ref_no, card_mask, company_name_in_quotes, job_and_position и т.п.).\n'
        'Формат ответа — строго строки вида: `значение | переменная | пояснение`. Без вступлений.\n\n'
        'ДОКУМЕНТ: ' + path.name + '\n' + text[:6000]
    )
    # Фотография клиента определяется по имени файла — до любого распознавания:
    # текста в ней нет и не должно быть, модель тут не нужна.
    _kind0 = doc_kind_name(path, '')
    if _kind0 in ('photo', 'foto', 'image'):
        return {'file': path.name, 'kind': path.suffix.lstrip('.').upper() or 'БЕЗ РАСШИРЕНИЯ',
                'doc_type': _kind0, 'text_len': 0, 'by': 'rules',
                'found': ('Фотография клиента. Файл «' + path.name + '» определён как фото клиента '
                          '(текста в нём нет и не должно быть).\n'
                          'Используется как переменная client_photo — на тех формах, где нужна '
                          'фотография клиента, она подставляется в документ.')}

    # СНАЧАЛА правила — они не требуют модели и не тратят ключи.
    try:
        from services.doc_parse import parse_any
        _rule_vals = parse_any(text, doc_kind_name(path, text))
    except Exception:
        _rule_vals = {}
    if _rule_vals:
        _found = "\n".join(f"{v} | {k} | из документа по правилам" for k, v in _rule_vals.items())
        return {'file': path.name, 'kind': path.suffix.lstrip('.'),
                'doc_type': doc_kind_name(path, text), 'text_len': len(text),
                'found': _found, 'by': 'rules'}

    # фотография без текста — модель не нужна, это фото клиента
    if len(text.strip()) < 20:
        _kind = doc_kind_name(path, '')
        if _kind in ('photo', 'foto', 'image'):
            return {'file': path.name, 'kind': path.suffix.lstrip('.').upper() or 'БЕЗ РАСШИРЕНИЯ',
                    'doc_type': _kind, 'text_len': 0, 'by': 'rules',
                    'found': ('Фотография клиента. Файл «' + path.name + '» определён как фото клиента '
                              '(текста в нём нет и не должно быть).\n'
                              'Используется как переменная client_photo — на тех формах, где нужна '
                              'фотография клиента, она подставляется в документ.')}
        return {'file': path.name, 'kind': path.suffix.lstrip('.').upper() or 'БЕЗ РАСШИРЕНИЯ',
                'doc_type': _kind, 'text_len': len(text), 'by': 'rules',
                'found': ('Текст в файле не распознан (тип документа: '
                          + _kind + '). Нужна ручная проверка.')}
    try:
        out = _call_llm([{'role': 'user', 'content': prompt}], timeout=180, json_mode=False) or ''
    except Exception as e:  # noqa: BLE001
        return {'file': path.name, 'kind': path.suffix.lstrip('.'),
                'doc_type': doc_kind_name(path, text), 'text_len': len(text),
                'note': f'модель недоступна: {str(e)[:120]}'}
    return {'file': path.name, 'kind': path.suffix.lstrip('.'),
            'doc_type': doc_kind_name(path, text), 'text_len': len(text),
            'found': out.strip()}



# ---- применение извлечённых значений ----
CLIENT_MAP = {
    "full_name_latin": "full_name_latin", "full_name_ru": "full_name_ru",
    "patronymic_latin": "patronymic",
    "patronymic": "patronymic", "surname": "surname", "name": "name",
    "date_of_birth": "birth_date", "birth_date": "birth_date",
    "place_of_birth": "birth_place", "birth_place": "birth_place",
    "passport_number": "passport_number",
    "passport_number_full": "passport_number", "nationality": "citizenship",
    "citizenship": "citizenship", "address_live": "address_live",
    "phone": "phone", "email": "email", "bank_name": "bank_name",
}


_JUNK_VALUES = {"отсутствует", "не указано", "не указан", "не указана", "не найдено",
                "нет данных", "нет", "неизвестно", "не применимо", "n/a", "na",
                "none", "null", "значение", "—", "-", ""}


def _is_junk(value) -> bool:
    """Заглушки распознавания («отсутствует», «Не указано») в карточку не пишем."""
    return str(value or "").strip().lower().rstrip(".") in _JUNK_VALUES


_DATE_RE = re.compile(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})')


def _bad_date(value) -> bool:
    """Невозможная дата — признак сбоя распознавания. Такое значение нельзя
    ставить ни в карточку, ни в документы (паспорт клиента читался как «42.01.2001»)."""
    s = str(value or '').strip()
    m = _DATE_RE.fullmatch(s)
    if not m:
        return False
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= d <= 31 and 1 <= mo <= 12) or not (1900 <= y <= 2100):
        return True
    try:
        datetime.date(y, mo, d)
    except ValueError:
        return True
    return False


def apply_values(app_id: int, results: list) -> dict:
    """Значения из документов -> карточка клиента (пустые поля) и значения документа заявки.

    Перед сборкой значений — фильтруем ИТК: если в папке клиента два файла ITK,
    берём данные только из самого свежего (по дате из текста/имени). Остальные
    ИТК не участвуют ни в карточке, ни в doc_values — администратору они
    не нужны, а двойные записи портят сборку.
    """
    # 1. Из всех результатов выделяем именно ИТК
    itks = [(i, r) for i, r in enumerate(results) if (r.get('doc_type') or '') == 'itk']
    if len(itks) > 1:
        def _itk_sort_key(pair):
            _idx, r = pair
            txt = (r.get('found') or '').lower()
            from services.doc_read import read_text
            # Пытаемся достать дату выпуска/срока из найденных значений
            dates = []
            for line in (r.get('found') or '').splitlines():
                if '|' not in line:
                    continue
                parts = [x.strip() for x in line.split('|')]
                if len(parts) < 2:
                    continue
                val, var = parts[0], parts[1].strip().lower()
                if any(k in var for k in ('date', 'date_of', 'issued', 'expiry', 'expir', 'period')):
                    from datetime import datetime
                    for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                        try:
                            dates.append(datetime.strptime(val, fmt))
                            break
                        except (ValueError, TypeError):
                            pass
            return (max(dates) if dates else datetime.min,
                    (r.get('file') or ''))
        itks.sort(key=_itk_sort_key, reverse=True)
        # Оставляем первую (самую свежую), остальные помечаем как 'skipped_old_itk'
        for _idx, r in itks[1:]:
            r['_skipped'] = 'более старая ИТК (выбрана другая, более свежая)'
        # Убираем её значения из выборки ниже — проще всего сделать копию
        results = [r for r in results if not r.get('_skipped')]

    c = conn()
    a = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not a:
        c.close(); return {"applied": 0}
    client = c.execute("SELECT * FROM clients WHERE id=?", (a["client_id"],)).fetchone()
    cols = {r[1] for r in c.execute("PRAGMA table_info(clients)")}
    doc_values, applied = {}, 0

    for item in results:
        found = item.get("found") or ""
        for line in found.splitlines():
            if "|" not in line:
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) < 2:
                continue
            val, var = parts[0], parts[1].strip().strip("`").lower()
            if not val or len(val) > 200 or _is_junk(val) or _bad_date(val):
                if val and _bad_date(val):
                    print('   [!] невозможная дата «%s» (%s) — не беру, нужно перечитать документ' % (val, var))
                continue
            col = CLIENT_MAP.get(var)
            if col and col in cols and client is not None:
                cur = (client[col] or "").strip() if col in client.keys() else ""
                if not cur:
                    try:
                        c.execute(f"UPDATE clients SET {col}=? WHERE id=?", (val, a["client_id"])); applied += 1
                    except Exception:
                        pass
            doc_values[var] = val

    # Копия значений, вытащенных именно из документов клиента: по ней видно
    # расхождения с анкетой, и администратор выбирает нужное значение.
    try:
        dv_dir = Path('/opt/wolf_v2/data/doc_values')
        dv_dir.mkdir(parents=True, exist_ok=True)
        dv_file = dv_dir / ('client_%s.json' % a["client_id"])
        cur_dv = {}
        if dv_file.exists():
            try:
                cur_dv = json.loads(dv_file.read_text(encoding='utf-8')) or {}
            except Exception:
                cur_dv = {}
        for item in results:
            src_name = str(item.get('file') or '')
            for line in (item.get('found') or '').splitlines():
                if '|' not in line:
                    continue
                parts = [x.strip() for x in line.split('|')]
                if len(parts) < 2:
                    continue
                val, var = parts[0], parts[1].strip().strip('`').lower()
                if not val or len(val) > 200 or _is_junk(val):
                    continue
                cell = cur_dv.get(var) or {}
                if isinstance(cell, str):
                    cell = {'value': cell}
                if cell.get('chosen'):
                    continue          # администратор уже выбрал — не перебиваем
                cur_dv[var] = {'value': val, 'from': src_name, 'at': time.time()}
        if cur_dv:
            dv_file.write_text(json.dumps(cur_dv, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass

    ad = c.execute("SELECT id, values_json FROM application_documents WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
    if ad:
        try:
            cur = json.loads(ad["values_json"] or "{}")
        except Exception:
            cur = {}
        for k, v in doc_values.items():
            if not cur.get(k):
                cur[k] = v
        # Значения из документов клиента применились — старую сборку PDF сбрасываем,
        # чтобы документ собрался заново уже с реальными данными клиента.
        c.execute("UPDATE application_documents SET values_json=?, pdf_path=NULL, status='draft' WHERE id=?",
                  (json.dumps(cur, ensure_ascii=False), ad["id"]))
    c.commit(); c.close()
    return {"applied": applied, "doc_values": len(doc_values)}


def _run(c, app_id: int):
    a = c.execute('SELECT * FROM applications WHERE id=?', (app_id,)).fetchone()
    if not a:
        print('заявка не найдена'); return
    cl = c.execute('SELECT * FROM clients WHERE id=?', (a['client_id'],)).fetchone() or {}
    url = (cl['gdrive_folder_url'] if 'gdrive_folder_url' in cl.keys() else '') or ''
    docs = fetch_docs(a['client_id'], url)
    if not docs:
        c.execute("UPDATE drive_scans SET status='fail', docs_done=0, note=? WHERE application_id=? AND status='running'",
                  ('на Google Drive клиента не найдено документов', app_id))
        c.commit(); print('документов нет'); return
    # Строку разбора запоминаем по номеру. Пока разбор идёт, сторож может
    # пометить её прерванной — правки «по статусу running» тогда уйдут в пустоту
    # и разбор потеряет и итог, и payload. Поэтому дальше пишем строго по id.
    row = c.execute("SELECT id FROM drive_scans WHERE application_id=? AND status='running' "
                    "ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
    if row:
        scan_id = row['id']
    else:
        cur = c.execute("INSERT INTO drive_scans(application_id, client_id, status, docs_total, docs_done, note) "
                        "VALUES(?,?,?,?,?,?)", (app_id, a['client_id'], 'running', len(docs), 0, 'разбор запущен'))
        scan_id = cur.lastrowid
    c.execute("UPDATE drive_scans SET status='running', docs_total=? WHERE id=?", (len(docs), scan_id))
    c.commit()
    results, ok = [], 0
    for i, f in enumerate(docs, 1):
        try:
            r = extract(f)
            results.append(r)
            if r.get('found'):
                ok += 1
        except Exception as e:
            results.append({'file': f.name, 'error': str(e)[:200]})
        c.execute('UPDATE drive_scans SET docs_done=?, payload=? WHERE id=?',
                  (ok, json.dumps(results, ensure_ascii=False), scan_id))
        c.commit()
        print(f'[{i}/{len(docs)}] {f.name}: {"ок" if results[-1].get("found") else "нет ответа"}', flush=True)
    res = apply_values(app_id, results)
    status = 'ok' if ok else 'fail'
    # Перечисляем, что реально лежит в папке клиента: администратор должен видеть
    # весь список документов, а не абстрактное «1 из 2».
    from collections import Counter
    kinds = Counter(DOC_KIND_RU.get(r.get('doc_type') or 'other', 'Документ') for r in results)
    listing = ', '.join((f'{k} ×{v}' if v > 1 else k) for k, v in kinds.items())
    # Если были отброшены старые ИТК — сообщаем администратору, какие именно
    skipped = [r for r in results if r.get('_skipped')]
    skipped_note = ''
    if skipped:
        skipped_note = ' Старые ИТК не участвуют в сборке: ' + ', '.join(r.get('file', '?') for r in skipped) + '.'
    note = (f'в наличии {len(docs)} документ(ов): {listing}. '
            f'Прочитано {ok}, в карточку перенесено {res.get("applied", 0)} значений.' + skipped_note)
    c.execute('UPDATE drive_scans SET status=?, docs_done=?, note=? WHERE id=?',
              (status, ok, note, scan_id))
    c.commit()
    print(note)


def main(app_id: int):
    """Запуск разбора. Любая ошибка закрывает строку 'running' статусом 'fail'.

    Иначе брошенный разбор (перезапуск сайта, нехватка памяти, снятый процесс)
    остаётся 'running' навсегда, и сторож каждый обход ставит агенту одну и ту
    же задачу-призрак о паузе, которой уже нет.
    """
    c = conn()
    try:
        _run(c, app_id)
    except Exception as e:                                            # noqa: BLE001
        try:
            c.execute("UPDATE drive_scans SET status='fail', note=? "
                      "WHERE application_id=? AND status='running'",
                      ('прервано: %s' % str(e)[:150], app_id))
            c.commit()
        except Exception:                                             # noqa: BLE001
            pass
        print('разбор прерван ошибкой: %s' % str(e)[:200])
    finally:
        c.close()


if __name__ == '__main__':
    main(int(sys.argv[1]))
