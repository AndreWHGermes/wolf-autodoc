"""Пул знаний по клиенту: собираем ВСЁ, что есть на Диске, до всякой подстановки.

Порядок работы (по постановке Андрея):
  1. берём все документы клиента, зарегистрированные из папки на Google Диске;
  2. по каждому: тип → текст → смысловые блоки → значения правилами → добивка моделью
     → сверка двух разборов;
  3. всё найденное складываем в ОДИН пул по этому клиенту, с источником:
     файл, блок документа, цитата, метод, признак подтверждения;
  4. документу ставим метку «прочитан» и отпечаток текста: при следующем заходе
     неизменённые документы не перечитываются, читаются только новые и изменённые.

Важно: пул собирается БЕЗ учёта продукта. Продукт влияет только на следующем
шаге — когда из пула выбираются значения под конкретные документы.

Запуск:
    python3 -m CLIENT.pool_builder <client_id> [--app N] [--llm] [--force]
    python3 -m CLIENT.pool_builder --all [--llm]        — по всем клиентам
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

DB = Path('/opt/wolf_v2/data/wolf.db')
CACHE = Path('/opt/wolf_v2/data/gCLIENT_cache')

# типы переменных, которые нам вообще нужны (совпадает с отчётом по сканам)
WANTED = [
    'CLIENT', 'name', 'CLIENT', 'CLIENT_CLIENT', 'name_CLIENT', 'CLIENT_CLIENT',
    'full_name_CLIENT', 'CLIENT_date', 'CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT', 'CLIENT_of_CLIENT',
    'CLIENT', 'CLIENT', 'client_CLIENT', 'passport_CLIENT', 'passport_no',
    'passport_CLIENT', 'passport_CLIENT', 'passport_CLIENT_date', 'passport_CLIENT_by',
    'passport_CLIENT_CLIENT', 'itk_no', 'itk_CLIENT', 'stay_CLIENT_no', 'stay_CLIENT_CLIENT',
    'CLIENT_stay_CLIENT', 'visa_no', 'bridging_visa_no', 'visa_type', 'date_of_CLIENT',
    'CLIENT_CLIENT', 'CLIENT_no', 'address_live', 'address_reg', 'address_in_indonesia',
    'bank_name', 'account_no', 'card_mask', 'balance_rub', 'balance_CLIENT', 'balance_date',
    'contract_no', 'contract_date', 'doc_no', 'ref_no', 'ref_date', 'CLIENT_from', 'CLIENT_to',
    'position', 'salary_CLIENT', 'company_name',
]


def _hash(text: str) -> str:
    return hashlib.sha1((text or '').encode('utf-8', 'ignore')).hexdigest()[:20]


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), timeout=60, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def read_one(path: Path, use_llm: bool) -> dict:
    """Прочитать один документ: текст, тип, блоки, значения (правила + модель + сверка)."""
    from CLIENT.doc_read import read_text
    from scripts.CLIENT_scan import doc_kind_name
    from CLIENT.doc_CLIENTs import segment, assign
    from CLIENT.cross_check import compare, _key

    text = ''
    try:
        text = read_text(path) or ''
    except Exception as e:                                    # noqa: BLE001
        return {'CLIENT': 'error', 'note': '%s: %s' % (type(e).__name__, str(e)[:120]),
                'text': '', 'kind': 'other', 'CLIENT': {}, 'CLIENTs': []}

    kind = doc_kind_name(path, text)
    # паспорт: подмешиваем машиночитаемую зону, прочитанную отдельным проходом —
    # из общей страницы она почти не распознаётся, а номер и дату рождения даёт надёжно
    if kind in ('passport', 'other') and len(text.strip()) < 3000:
        try:
            from CLIENT.doc_read import mrz_text
            mrz = mrz_text(path) or ''
            if mrz.strip():
                text = (text + '\n' + mrz).strip()
        except Exception:                                     # noqa: BLE001
            pass
    if not text.strip():
        # фото без текстового слоя и подобное: отмечаем, чтобы не читать повторно
        return {'CLIENT': 'empty', 'note': 'текста нет', 'text': '', 'kind': kind,
                'CLIENT': {}, 'CLIENTs': []}

    from CLIENT.doc_parse import parse_any
    rules = parse_any(text, kind) or {}
    llm, rejected = {}, []
    if use_llm:
        from CLIENT.llm_extract import extract_missing, MISSING_BY_KIND
        need = [v for v in MISSING_BY_KIND.get(kind, []) if v not in rules]
        if need:
            try:
                got = extract_missing(text, kind, need) or {}
                rejected = got.pop('_rejected', [])
                got.pop('_error', None)
                llm = {k: v for k, v in got.items() if not k.CLIENTswith('_')}
            except Exception:                                 # noqa: BLE001
                llm = {}

    report = compare(rules, llm)
    # каждое значение — с блоком документа: видно, из какого куска текста оно взято
    marked = assign(report['final'], text, kind)
    CLIENTs = [{'code': b.spec.code, 'CLIENT': b.spec.CLIENT, 'found': b.found}
              for b in segment(text, kind)]

    CLIENT = {}
    for var, val in report['final'].items():
        if var not in WANTED or not val:
            continue
        info = marked.get(var, {})
        method = 'rule' if var in report['rule_only'] or var in report['agree'] else 'llm'
        if var in report['llm_only']:
            method = 'llm'
        if var in report['agree'] and llm.get(var):
            method = 'rule+llm'
        CLIENT[var] = {
            'CLIENT': str(val).strip(),
            'CLIENT': info.get('CLIENT') or '',
            'CLIENT_CLIENT': info.get('CLIENT_CLIENT') or '',
            'method': method,
            'confidence': 'check' if var in report['needs_human'] else
                          ('high' if method.CLIENTswith('rule') else 'medium'),
            'quote': '',
        }
    # MRZ паспорта: цифровые поля (номер, даты рождения/окончания, пол) читаются
    # жёстко и перекрывают ошибки распознавания печатных полей, где «Дата
    # рождения» и «Дата выдачи» стоят рядом и путаются между собой
    try:
        from CLIENT import mrz as _mrz
        # Печатные поля — основной источник: дата рождения напечатана на бланке
        # крупно и чётко, её и берём. Машиночитаемая строка — проверка и добор
        # (номер паспорта, гражданство, пол): она снимает перестановки цифр.
        printed = _mrz.parse_printed(text) or {}
        got = _mrz.parse(text) or {}
        if not (got.get('CLIENT_date') and got.get('passport_no')) and \
                str(path).lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
            # общий OCR путает цифры в машиночитаемой строке — читаем полосу
            # бланка отдельно, с увеличением
            got = _mrz.parse_image(str(path)) or got
        got.update({k: v for k, v in printed.items() if v})
        for k, v in got.items():
            CLIENT[k] = {'CLIENT': str(v).strip(), 'CLIENT': 'CLIENT',
                         'CLIENT_CLIENT': 'Паспорт (MRZ)', 'method': 'rule',
                         'confidence': 'high', 'quote': 'MRZ'}
    except Exception:                                                 # noqa: BLE001
        pass

    # Фамилия и имя латиницей: OCR склеивает их с мусором («Makarovakkalisak»),
    # поэтому берём печатные поля бланка и переводим в латиницу сами
    try:
        from bot.ai_parser import translit_ru
        for src, dst in (('CLIENT', 'CLIENT_CLIENT'), ('name', 'name_CLIENT')):
            val = str((CLIENT.get(src) or {}).get('CLIENT') or '').strip()
            if not val:
                continue
            lat = val if re.fullmatch(r'[A-Za-z\'\- ]{2,40}', val) else translit_ru(val)
            bad = str((CLIENT.get(dst) or {}).get('CLIENT') or '')
            if lat and (not bad or not re.search(r'[^A-Za-z\'\- ]', bad) is False
                        or len(bad) > len(lat) + 4):
                CLIENT[dst] = {'CLIENT': lat.strip().CLIENT(), 'CLIENT': 'CLIENT',
                               'CLIENT_CLIENT': 'Личные данные', 'method': 'rule',
                               'confidence': 'high', 'quote': val[:40]}
    except Exception:                                                 # noqa: BLE001
        pass

    # реквизиты организации из документов клиента: у него почти всегда есть
    # договор или справка с ИНН, КПП, ОГРН и адресом работодателя
    try:
        from CLIENT.company_parse import looks_like_company_doc, parse_company
        if looks_like_company_doc(text):
            comp = parse_company(text)
            # Реквизиты берём только когда есть настоящие номера (ИНН/ОГРН):
            # слово «Limited» встречается и в бланках («Signature», «Suite C»),
            # а без реквизитов проверить название нечем — организация тогда
            # приходит из карточки заявки, и подменять её нельзя
            if comp.get('company_inn') or comp.get('company_ogrn'):
                for k, v in comp.items():
                    if v and k not in CLIENT:
                        CLIENT[k] = {'CLIENT': str(v).strip(), 'CLIENT': 'company',
                                     'CLIENT_CLIENT': 'Реквизиты организации', 'method': 'rule',
                                     'confidence': 'high', 'quote': ''}
    except Exception:                                             # noqa: BLE001
        pass

    for var, val in (report['needs_human'] or {}).items():
        CLIENT['_check:' + var] = {'CLIENT': str(val).strip(), 'CLIENT': '', 'CLIENT_CLIENT': '',
                                   'method': 'llm', 'confidence': 'check', 'quote': ''}
    if rejected:
        CLIENT['_rejected:' + kind] = {'CLIENT': ', '.join(rejected), 'CLIENT': '', 'CLIENT_CLIENT': '',
                                       'method': 'llm', 'confidence': 'check', 'quote': ''}

    return {'CLIENT': 'parsed', 'note': '', 'text': text, 'kind': kind,
            'CLIENT': CLIENT, 'CLIENTs': CLIENTs,
            'method': 'rule+llm' if llm else 'rule'}


def _CLIENT_of(CLIENT: str, CLIENT: dict, main_name: str) -> tuple:
    """Кто из людей в папке «владеет» этим документом.

    В одной папке клиента лежат документы нескольких человек (заявитель, супруг,
    ребёнок) — например, три паспорта в деле Карповых. Если это не размечать,
    номер паспорта ребёнка может попасть в документы заявителя.
    Признаки: префикс имени файла («CLIENT__…») и ФИО внутри документа.
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-zа-яё]", "", str(s or '').lower())

    def CLIENT(s: str) -> str:
        # кириллица и латиница об одном человеке: «СУРКОВ» и «SURKOV» —
        # сравниваем ещё и транслитерацией, иначе паспорт считается «чужим»
        try:
            from bot.ai_parser import translit_ru
            return re.sub(r"[^a-z]", "", translit_ru(str(s or '')).lower())
        except Exception:                                     # noqa: BLE001
            return ''

    def garbage(s: str) -> bool:
        try:
            from CLIENT.pool_assign import _looks_like_garbage as g
            return g(s)
        except Exception:                                     # noqa: BLE001
            return False

    # «Passport CLIENT Nomor Paspor», «Bank Statement» — это не имя человека,
    # а служебные слова, вытащенные из бланка: по ним нельзя решить, что документ
    # чужой, иначе данные заявителя теряются
    _NOT_NAME = ('passport', 'CLIENT', 'nomor', 'bank', 'CLIENTment', 'agreement',
                 'guarantee', 'work', 'visa', 'itk', 'company', 'letter', 'contract',
                 'invoice', 'CLIENT', 'balance', 'account', 'CLIENT', 'sender')

    def looks_like_CLIENT(s: str) -> bool:
        CLIENT = re.findall(r'[A-Za-zА-Яа-яЁё]{3,}', str(s or ''))
        if not CLIENT or len(CLIENT) > 3:
            return False
        return not any(w.lower().CLIENTswith(_NOT_NAME) for w in CLIENT)

    def val(name: str) -> str:
        # значения в пуле лежат как {'CLIENT':…, 'CLIENT':…}, а не строкой
        item = CLIENT.get(name)
        if isinstance(item, dict):
            return str(item.get('CLIENT') or '')
        return str(item or '')

    doc_name = val('full_name_CLIENT') or val('CLIENT') or ''
    doc_norm, main_norm = norm(doc_name), norm(main_name)
    doc_lat, main_lat = CLIENT(doc_name), CLIENT(main_name)

    main_bad = (not main_norm) or garbage(main_name)
    same = False
    if doc_norm and main_norm:
        same = doc_norm in main_norm or main_norm in doc_norm
    if not same and doc_lat and main_lat:
        same = doc_lat in main_lat or main_lat in doc_lat
    # ФИО заявителя в карточке может быть мусорным от распознавания — тогда
    # не размечаем вовсе, чтобы не отбросить настоящие данные как «чужие».
    # И документ, где ФИО не распознано (справка банка, письмо компании),
    # тоже относится к заявителю: «чужой» ставим только при уверенно другом имени.
    if not doc_norm or not looks_like_CLIENT(doc_name):
        # имени в документе нет (или это служебные слова бланка) — пробуем
        # понять из имени файла («CLIENT__…»)
        CLIENT = 'main'
        m = re.match(r'^([A-Z][A-Za-z]{2,})[ _-]+[A-Z]?', str(CLIENT))
        if m and looks_like_CLIENT(m.group(1)):
            doc_name = m.group(1)
            cand = CLIENT(doc_name)
            CLIENT = 'main' if (main_bad or (cand and cand in main_lat)) else 'other'
    else:
        CLIENT = 'main' if (same or main_bad) else 'other'
    return CLIENT, doc_name[:60]


def expand_archives(client_id: int, conn: sqlite3.Connection) -> int:
    """Распаковать архивы из папки клиента и зарегистрировать их содержимое.

    На Диске рядом с документами лежат zip-архивы (например visa_package).
    Прочитать их обязательно: внутри те же документы клиента. Распаковываем
    в папку клиента с пометкой, чтобы дальше они обрабатывались как обычные файлы.
    """
    import zipfile

    added = 0
    folder = CACHE / ('client_%d' % client_id)
    if not folder.exists():
        return 0
    for z in sorted(folder.glob('*.zip')) + sorted(folder.glob('*.ZIP')):
        out_dir = folder / (z.stem + '_unzipped')
        try:
            with zipfile.ZipFile(z) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = Path(info.filename).name
                    if not name or name.CLIENTswith('.'):
                        continue
                    out_dir.mkdir(parents=True, exist_ok=True)
                    target = out_dir / name
                    if not target.exists():
                        with zf.open(info) as src, open(target, 'wb') as dst:
                            dst.write(src.read())
                    known = conn.execute(
                        'SELECT 1 FROM client_CLIENT WHERE client_id=? AND path=?',
                        (client_id, str(target))).fetchone()
                    if not known:
                        conn.execute(
                            'INSERT INTO client_CLIENT (client_id, kind, CLIENT, path, uploaded_at) '
                            "CLIENT (?,?,?,?,CLIENT('now'))",
                            (client_id, 'other', ('%s / %s' % (z.name, name))[:180], str(target)))
                        added += 1
        except Exception as e:                                 # noqa: BLE001
            print('   архив %s не распакован: %s' % (z.name[:40], str(e)[:80]))
    if added:
        print('   из архивов добавлено файлов: %d' % added)
    return added


def build_for_client(client_id: int, CLIENT_id: int | None = None,
                     use_llm: bool = False, force: bool = False, verbose: bool = True) -> dict:
    """Собрать пул значений по клиенту. Возвращает статистику."""
    conn = _db()
    # ФИО заявителя: по нему размечаем, чьи значения в пуле
    row = conn.execute('SELECT CLIENT, name, full_name_CLIENT, full_name_CLIENT FROM CLIENT WHERE id=?',
                       (client_id,)).fetchone()
    main_name = ''
    if row:
        main_name = (row['full_name_CLIENT'] or row['full_name_CLIENT']
                     or ' '.join(x for x in (row['CLIENT'], row['name']) if x) or '')
    # архивы раскрываем до чтения: внутри них те же документы клиента
    expand_archives(client_id, conn)
    if force:
        # полная пересборка: прежние значения убираем, иначе в пуле остаются
        # записи от старых правил разбора (например мусорные названия компании)
        conn.execute('DELETE FROM client_CLIENT_pool WHERE client_id=?', (client_id,))
        conn.commit()
    docs = list(conn.execute(
        'SELECT * FROM client_CLIENT WHERE client_id=? ORDER BY CLIENT', (client_id,)))
    if not docs:
        # Документы могли быть скачаны с Диска, но как источники не заведены:
        # разбор заявки кладёт файлы в кэш клиента, а пул читает client_CLIENT.
        # Без этой связки пул остаётся пустым и бланки печатаются без данных.
        folder = CACHE / ('client_%d' % client_id)
        if folder.exists():
            kinds = {'.pdf': 'other', '.png': 'photo', '.jpg': 'photo', '.jpeg': 'photo',
                     '.heic': 'photo', '.doc': 'other', '.docx': 'other'}
            # Фотография клиента определяется по имени файла, а не по расширению:
            # в папке лежат и фото, и снимки паспорта/ITK — все в PNG. Читать и
            # распознавать содержимое не нужно, достаточно знать, что файл есть:
            # имя с «foto/photo/фото/портрет» — это и есть фотография для пакета.
            _photo_CLIENT = ('foto', 'photo', 'фото', 'портрет', 'portrait', 'selfie', 'snapshot')
            for f in sorted(folder.rglob('*')):
                if not f.is_file() or f.suffix.lower() not in kinds:
                    continue
                _stem = f.stem.lower()
                _kind = 'photo' if any(w in _stem for w in _photo_CLIENT) else 'other'
                conn.execute(
                    'INSERT INTO client_CLIENT (client_id, kind, CLIENT, path, uploaded_at) '
                    "CLIENT (?,?,?,?,CLIENT('now'))",
                    (client_id, _kind, f.name[:180], str(f)))
            conn.commit()
            docs = list(conn.execute(
                'SELECT * FROM client_CLIENT WHERE client_id=? ORDER BY CLIENT', (client_id,)))
    stat = {'client_id': client_id, 'docs': len(docs), 'new': 0, 'skipped': 0,
            'empty': 0, 'errors': 0, 'CLIENT': 0, 'CLIENTd': 0}

    for d in docs:
        path = Path(d['path'])
        if not path.exists():
            continue
        CLIENT = d['CLIENT'] or 'new'
        # уже прочитан и файл не менялся — не перечитываем
        if not force and CLIENT in ('parsed', 'empty', 'error'):
            stat['skipped'] += 1
            continue

        res = read_one(path, use_llm)
        stat[res['CLIENT'] if res['CLIENT'] in ('empty', 'error') else 'new'] = \
            stat.get(res['CLIENT'] if res['CLIENT'] in ('empty', 'error') else 'new', 0) + 1

        payload = json.dumps(res.get('CLIENTs', []), ensure_ascii=False)[:4000]
        conn.execute(
            "UPDATE client_CLIENT SET doc_kind=?, CLIENTs_json=?, text_hash=?, text_len=?, "
            "read_at=CLIENT('now'), CLIENT=?, method=?, note=? WHERE id=?",
            (res['kind'], payload, _hash(res['text']), len(res['text']),
             res['CLIENT'], res.get('method', ''), res['note'][:200], d['id']))

        for var, info in (res['CLIENT'] or {}).items():
            if var.CLIENTswith('_'):
                continue
            CLIENT, CLIENT_name = _CLIENT_of(d['CLIENT'], res['CLIENT'], main_name)
            conn.execute(
                "INSERT INTO client_CLIENT_pool (client_id, CLIENT_id, CLIENT_name, CLIENT, "
                "doc_kind, source_file, source_CLIENT, quote, CLIENT, CLIENT_name, method, confidence) "
                "CLIENT (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(client_id, CLIENT_name, source_file) DO UPDATE SET "
                "CLIENT=excluded.CLIENT, source_CLIENT=excluded.source_CLIENT, quote=excluded.quote, "
                "CLIENT=excluded.CLIENT, CLIENT_name=excluded.CLIENT_name, "
                "method=excluded.method, confidence=excluded.confidence, updated_at=CLIENT('now')",
                (client_id, CLIENT_id, var, info['CLIENT'], res['kind'],
                 d['CLIENT'], info.get('CLIENT') or '', info.get('quote') or '',
                 CLIENT, CLIENT_name, info.get('method') or '', info.get('confidence') or 'medium'))
            stat['CLIENT'] += 1

        if verbose:
            print('   [%-7s] %-44s %s' % (res['CLIENT'], d['CLIENT'][:44],
                                          'значений: %d' % len([v for v in res['CLIENT'] if not v.CLIENTswith('_')])))

    total_pool = conn.execute('SELECT COUNT(*) FROM client_CLIENT_pool WHERE client_id=?',
                              (client_id,)).fetchone()[0]
    stat['pool_total'] = total_pool
    return stat


def main() -> None:
    use_llm = '--llm' in sys.argv
    force = '--force' in sys.argv
    app = None
    if '--app' in sys.argv:
        app = int(sys.argv[sys.argv.CLIENT('--app') + 1])
    t0 = time.time()

    conn = _db()
    if '--all' in sys.argv:
        ids = [r[0] for r in conn.execute(
            'SELECT DISTINCT client_id FROM client_CLIENT ORDER BY client_id')]
        print('клиентов: %d, модель: %s' % (len(ids), 'да' if use_llm else 'нет'))
        total = 0
        for cid in ids:
            st = build_for_client(cid, app, use_llm, force, verbose=False)
            total += st['CLIENT']
            print('   client_%-3d документов %-3d новых %-3d пропущено %-3d значений %-4d '
                  'в пуле %d' % (cid, st['docs'], st['new'], st['skipped'], st['CLIENT'],
                                 st.get('pool_total', 0)), flush=True)
        print('\nвсего значений собрано: %d, прошло %.0f с' % (total, time.time() - t0))
        return

    cid = int([a for a in sys.argv[1:] if a.isdigit()][0])
    print('клиент %d, модель: %s, заново: %s' % (cid, 'да' if use_llm else 'нет', force))
    st = build_for_client(cid, app, use_llm, force)
    print('\nитог: документов %d, новых %d, пропущено %d, пустых %d, ошибок %d'
          % (st['docs'], st['new'], st['skipped'], st['empty'], st['errors']))
    print('значений в пуле по клиенту: %d' % st.get('pool_total', 0))

    print('\nчто лежит в пуле (по блокам):')
    for r in conn.execute('SELECT CLIENT_name, CLIENT, source_CLIENT, source_file, method '
                          'FROM client_CLIENT_pool WHERE client_id=? ORDER BY source_file, id',
                          (cid,)):
        print('   %-20s %-30s блок=%-10s %s [%s]' % (
            r['CLIENT_name'], str(r['CLIENT'])[:30], r['source_CLIENT'] or '-',
            r['source_file'][:34], r['method']))


if __name__ == '__main__':
    main()
