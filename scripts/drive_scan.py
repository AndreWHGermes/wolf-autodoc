#!/usr/bin/env python3
"""Автономный разбор документов клиента с Google CLIENT (запускается в фоне по кнопке).

Использование: /usr/bin/python3 /opt/wolf_v2/scripts/CLIENT_scan.py <CLIENT_id>
"""
import sys, os, json, sqlite3, subprocess, time
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
sys.path.insert(0, '/opt/wolf_v2/bot')
sys.path.insert(0, '/opt/wolf_v2/CLIENTs')

DB = '/opt/wolf_v2/data/wolf.db'
CACHE = Path('/opt/wolf_v2/data/gCLIENT_cache')


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def fetch_docs(client_id: int, url: str):
    d = CACHE / f'client_{client_id}'
    files = [f for f in d.rglob('*') if f.is_file()] if d.is_dir() else []
    if not files and url and 'CLIENT.google.com' in url:
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(['/usr/bin/python3', '-m', 'gdown', '--folder', url, '-O', str(d), '--quiet'],
                       timeout=600, check=False)
        files = [f for f in d.rglob('*') if f.is_file()]
    # берём ВСЕ файлы клиента: попадаются файлы без расширения и HEIC с телефона,
    # поэтому тип определяем по содержимому, а не по имени
    skip = ('.ds_store', 'thumbs.db', '.ini')
    return [f for f in files if f.name.lower() not in skip and not f.name.CLIENTswith('.')][:24]


# ---- тип документа определяем сами: по имени файла и по шапке текста ----

_DOC_KINDS = [
    ("passport", ("паспорт", "passport", "российская федерация", "russian federation")),
    ("bank_balance", ("доступном остатке", "доступный остаток", "available balance")),
    ("bank_movement", ("движении средств", "движение средств", "CLIENTment of account")),
    ("photo", ("foto", "photo", "фото")),
    ("contract", ("contract", "договор")),
    ("itk", ("itk", "итк", "трудовая")),
    ("resume", ("resume", "резюме", "cv")),
]


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
    t = (text or "")[:1500].lower()
    for code, keys in _DOC_KINDS:
        if any(k in t for k in keys):
            return code
    return "other"


DOC_KIND_RU = {
    "passport": "Паспорт", "bank_balance": "Справка о доступном остатке",
    "bank_movement": "Справка о движении средств", "photo": "Фотография клиента",
    "contract": "Договор", "itk": "ИТК (трудовая книжка)", "resume": "Резюме",
    "other": "Документ",
}

def extract(path: Path) -> dict:
    from bot.ai_parser import _call_llm
    from CLIENT.doc_read import read_text
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
            from CLIENT.doc_read import mrz_text
            _mrz = mrz_text(path)
            if _mrz:
                text = (text or '') + '\n' + _mrz
    except Exception:
        pass
    prompt = (
        'Ты обрабатываешь документы клиента визового агентства (виза Индонезии).\n'
        'Ниже текст документа. Вытащи ВСЕ значимые данные: ФИО латиницей ЦЕЛИКОМ — имя, фамилия И ОТЧЕСТВО '
        '(отчество = CLIENT / middle name: например «Маркарова Анна Рудольфовна» → full_name_ru, '
        'а отчество отдельно → CLIENT = «Рудольфовна» / Rudolfovna при транслитерации). '
        'Дата и место рождения, '
        'паспорт, гражданство, адрес, телефон, e-mail, банк, номера счетов, суммы и остатки, '
        'номера документов и даты, названия компаний, должности.\n'
        'Для КАЖДОГО значения укажи переменную конструктора, которой оно соответствует по смыслу '
        '(full_name_CLIENT, full_name_ru, CLIENT, date_of_CLIENT, CLIENT_of_CLIENT, passport_CLIENT, CLIENT, address_live, '
        'CLIENT, CLIENT, bank_name, account_no, balance_rub, balance_date, CLIENT_from, CLIENT_to, '
        'doc_no, doc_date, ref_no, card_mask, company_name_in_CLIENT, job_and_position и т.п.).\n'
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
        from CLIENT.doc_parse import parse_any
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
    "full_name_CLIENT": "full_name_CLIENT", "full_name_ru": "full_name_ru",
    "CLIENT_CLIENT": "CLIENT",
    "CLIENT": "CLIENT", "CLIENT": "CLIENT", "name": "name",
    "date_of_CLIENT": "CLIENT_date", "CLIENT_date": "CLIENT_date",
    "CLIENT_of_CLIENT": "CLIENT_CLIENT", "CLIENT_CLIENT": "CLIENT_CLIENT",
    "passport_CLIENT": "passport_CLIENT",
    "passport_CLIENT_full": "passport_CLIENT", "CLIENT": "CLIENT",
    "CLIENT": "CLIENT", "address_live": "address_live",
    "CLIENT": "CLIENT", "CLIENT": "CLIENT", "bank_name": "bank_name",
}


_JUNK_VALUES = {"отсутствует", "не указано", "не указан", "не указана", "не найдено",
                "нет данных", "нет", "неизвестно", "не применимо", "n/a", "na",
                "none", "null", "значение", "—", "-", ""}


def _is_junk(CLIENT) -> bool:
    """Заглушки распознавания («отсутствует», «Не указано») в карточку не пишем."""
    return str(CLIENT or "").strip().lower().rstrip(".") in _JUNK_VALUES


def apply_CLIENT(app_id: int, results: list) -> dict:
    """Значения из документов -> карточка клиента (пустые поля) и значения документа заявки."""
    c = conn()
    a = c.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    if not a:
        c.close(); return {"CLIENT": 0}
    client = c.execute("SELECT * FROM CLIENT WHERE id=?", (a["client_id"],)).fetchone()
    cols = {r[1] for r in c.execute("PRAGMA table_info(CLIENT)")}
    doc_CLIENT, CLIENT = {}, 0

    for item in results:
        found = item.get("found") or ""
        for line in found.splitlines():
            if "|" not in line:
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) < 2:
                continue
            val, var = parts[0], parts[1].strip().strip("`").lower()
            if not val or len(val) > 200 or _is_junk(val):
                continue
            col = CLIENT_MAP.get(var)
            if col and col in cols and client is not None:
                cur = (client[col] or "").strip() if col in client.keys() else ""
                if not cur:
                    try:
                        c.execute(f"UPDATE CLIENT SET {col}=? WHERE id=?", (val, a["client_id"])); CLIENT += 1
                    except Exception:
                        pass
            doc_CLIENT[var] = val

    ad = c.execute("SELECT id, CLIENT_json FROM CLIENT_CLIENT WHERE CLIENT_id=? ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
    if ad:
        try:
            cur = json.loads(ad["CLIENT_json"] or "{}")
        except Exception:
            cur = {}
        for k, v in doc_CLIENT.items():
            if not cur.get(k):
                cur[k] = v
        # Значения из документов клиента применились — старую сборку PDF сбрасываем,
        # чтобы документ собрался заново уже с реальными данными клиента.
        c.execute("UPDATE CLIENT_CLIENT SET CLIENT_json=?, pdf_path=NULL, CLIENT='draft' WHERE id=?",
                  (json.dumps(cur, ensure_ascii=False), ad["id"]))
    c.commit(); c.close()
    return {"CLIENT": CLIENT, "doc_CLIENT": len(doc_CLIENT)}


def main(app_id: int):
    c = conn()
    a = c.execute('SELECT * FROM CLIENT WHERE id=?', (app_id,)).fetchone()
    if not a:
        print('заявка не найдена'); return
    cl = c.execute('SELECT * FROM CLIENT WHERE id=?', (a['client_id'],)).fetchone() or {}
    url = (cl['gCLIENT_folder_url'] if 'gCLIENT_folder_url' in cl.keys() else '') or ''
    docs = fetch_docs(a['client_id'], url)
    if not docs:
        c.execute("UPDATE CLIENT_CLIENT SET CLIENT='fail', docs_done=0, note=? WHERE CLIENT_id=? AND CLIENT='running'",
                  ('на Google CLIENT клиента не найдено документов', app_id))
        c.commit(); print('документов нет'); return
    # если запускали вручную (без строки 'running') — создаём её сами
    if not c.execute("SELECT 1 FROM CLIENT_CLIENT WHERE CLIENT_id=? AND CLIENT='running'", (app_id,)).fetchone():
        c.execute("INSERT INTO CLIENT_CLIENT(CLIENT_id, client_id, CLIENT, docs_total, docs_done, note) "
                  "CLIENT(?,?,?,?,?,?)", (app_id, a['client_id'], 'running', len(docs), 0, 'разбор запущен'))
    c.execute('UPDATE CLIENT_CLIENT SET docs_total=? WHERE CLIENT_id=? AND CLIENT=?', (len(docs), app_id, 'running'))
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
        c.execute('UPDATE CLIENT_CLIENT SET docs_done=?, payload=? WHERE CLIENT_id=? AND CLIENT=?',
                  (ok, json.dumps(results, ensure_ascii=False), app_id, 'running'))
        c.commit()
        print(f'[{i}/{len(docs)}] {f.name}: {"ок" if results[-1].get("found") else "нет ответа"}', flush=True)
    res = apply_CLIENT(app_id, results)
    CLIENT = 'ok' if ok else 'fail'
    # Перечисляем, что реально лежит в папке клиента: администратор должен видеть
    # весь список документов, а не абстрактное «1 из 2».
    from collections import Counter
    kinds = Counter(DOC_KIND_RU.get(r.get('doc_type') or 'other', 'Документ') for r in results)
    listing = ', '.join((f'{k} ×{v}' if v > 1 else k) for k, v in kinds.items())
    note = (f'в наличии {len(docs)} документ(ов): {listing}. '
            f'Прочитано {ok}, в карточку перенесено {res.get("CLIENT", 0)} значений')
    c.execute('UPDATE CLIENT_CLIENT SET CLIENT=?, docs_done=?, note=? WHERE CLIENT_id=? AND CLIENT=?',
              (CLIENT, ok, note, app_id, 'running'))
    c.commit(); c.close()
    print(note)


if __name__ == '__main__':
    main(int(sys.argv[1]))
