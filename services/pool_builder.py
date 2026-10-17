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
    python3 -m services.pool_builder <client_id> [--app N] [--llm] [--force]
    python3 -m services.pool_builder --all [--llm]        — по всем клиентам
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
CACHE = Path('/opt/wolf_v2/data/gdrive_cache')
# Скачанные вручную/скриптами папки клиентов: тот же набор документов, но вне кэша.
# Без этого пул по старым папкам остаётся пустым, а бланки печатаются без данных.
ARCHIVE = Path('/opt/wolf_v2/data/gdrive_archive')

# Наши же документы, отправленные клиенту обратно на Диск: читать их как источник
# нельзя — значения из собственной справки/легенды зацикливают пул:
# «должность» и суммы начинают приходить из документа, который мы сами и собрали.
_GENERATED_MARKERS = ('wolf autodoc №', 'wolf autodoc ', 'wolf_autodoc',
                      'application text (for administrator)')

# типы переменных, которые нам вообще нужны (совпадает с отчётом по сканам)
WANTED = [
    'surname', 'name', 'patronymic', 'surname_latin', 'name_latin', 'patronymic_latin',
    'full_name_latin', 'birth_date', 'birth_place', 'place_birth_inline', 'place_of_birth',
    'citizenship', 'nationality', 'client_gender', 'passport_number', 'passport_no',
    'passport_series', 'passport_expiry', 'passport_issue_date', 'passport_issued_by',
    'passport_valid_until', 'itk_no', 'itk_expiry', 'stay_permit_no', 'stay_permit_expiry',
    'existing_stay_permit', 'visa_no', 'bridging_visa_no', 'visa_type', 'date_of_issue',
    'valid_until', 'reference_no', 'address_live', 'address_reg', 'address_in_indonesia',
    'bank_name', 'account_no', 'card_mask', 'balance_rub', 'balance_words', 'balance_date',
    'contract_no', 'contract_date', 'doc_no', 'ref_no', 'ref_date', 'period_from', 'period_to',
    'position', 'salary_amount', 'company_name',
]


def _hash(text: str) -> str:
    return hashlib.sha1((text or '').encode('utf-8', 'ignore')).hexdigest()[:20]


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), timeout=60, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def read_one(path: Path, use_llm: bool) -> dict:
    """Прочитать один документ: текст, тип, блоки, значения (правила + модель + сверка)."""
    from services.doc_read import read_text
    from scripts.drive_scan import doc_kind_name
    from services.doc_blocks import segment, assign
    from services.cross_check import compare, _key

    text = ''
    try:
        text = read_text(path) or ''
    except Exception as e:                                    # noqa: BLE001
        return {'state': 'error', 'note': '%s: %s' % (type(e).__name__, str(e)[:120]),
                'text': '', 'kind': 'other', 'values': {}, 'blocks': []}

    kind = doc_kind_name(path, text)
    # паспорт: подмешиваем машиночитаемую зону, прочитанную отдельным проходом —
    # из общей страницы она почти не распознаётся, а номер и дату рождения даёт надёжно
    if kind in ('passport', 'other') and len(text.strip()) < 3000:
        try:
            from services.doc_read import mrz_text
            mrz = mrz_text(path) or ''
            if mrz.strip():
                text = (text + '\n' + mrz).strip()
        except Exception:                                     # noqa: BLE001
            pass
    if not text.strip():
        # фото без текстового слоя и подобное: отмечаем, чтобы не читать повторно
        return {'state': 'empty', 'note': 'текста нет', 'text': '', 'kind': kind,
                'values': {}, 'blocks': []}

    from services.doc_parse import parse_any
    rules = parse_any(text, kind) or {}
    llm, rejected = {}, []
    if use_llm:
        from services.llm_extract import extract_missing, MISSING_BY_KIND
        need = [v for v in MISSING_BY_KIND.get(kind, []) if v not in rules]
        if need:
            try:
                got = extract_missing(text, kind, need) or {}
                rejected = got.pop('_rejected', [])
                got.pop('_error', None)
                llm = {k: v for k, v in got.items() if not k.startswith('_')}
            except Exception:                                 # noqa: BLE001
                llm = {}

    report = compare(rules, llm)
    # каждое значение — с блоком документа: видно, из какого куска текста оно взято
    marked = assign(report['final'], text, kind)
    blocks = [{'code': b.spec.code, 'title': b.spec.title, 'found': b.found}
              for b in segment(text, kind)]

    values = {}
    for var, val in report['final'].items():
        if var not in WANTED or not val:
            continue
        info = marked.get(var, {})
        method = 'rule' if var in report['rule_only'] or var in report['agree'] else 'llm'
        if var in report['llm_only']:
            method = 'llm'
        if var in report['agree'] and llm.get(var):
            method = 'rule+llm'
        values[var] = {
            'value': str(val).strip(),
            'block': info.get('block') or '',
            'block_title': info.get('block_title') or '',
            'method': method,
            'confidence': 'check' if var in report['needs_human'] else
                          ('high' if method.startswith('rule') else 'medium'),
            'quote': '',
        }
    # MRZ паспорта: цифровые поля (номер, даты рождения/окончания, пол) читаются
    # жёстко и перекрывают ошибки распознавания печатных полей, где «Дата
    # рождения» и «Дата выдачи» стоят рядом и путаются между собой
    try:
        from services import mrz as _mrz
        # Печатные поля — основной источник: дата рождения напечатана на бланке
        # крупно и чётко, её и берём. Машиночитаемая строка — проверка и добор
        # (номер паспорта, гражданство, пол): она снимает перестановки цифр.
        printed = _mrz.parse_printed(text) or {}
        got = _mrz.parse(text) or {}
        if not (got.get('birth_date') and got.get('passport_no')) and \
                str(path).lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
            # общий OCR путает цифры в машиночитаемой строке — читаем полосу
            # бланка отдельно, с увеличением
            got = _mrz.parse_image(str(path)) or got
        got.update({k: v for k, v in printed.items() if v})
        for k, v in got.items():
            values[k] = {'value': str(v).strip(), 'block': 'person',
                         'block_title': 'Паспорт (MRZ)', 'method': 'rule',
                         'confidence': 'high', 'quote': 'MRZ'}
    except Exception:                                                 # noqa: BLE001
        pass

    # Фамилия и имя латиницей: OCR склеивает их с мусором («Makarovakkalisak»),
    # поэтому берём печатные поля бланка и переводим в латиницу сами
    try:
        from bot.ai_parser import translit_ru
        for src, dst in (('surname', 'surname_latin'), ('name', 'name_latin')):
            val = str((values.get(src) or {}).get('value') or '').strip()
            if not val:
                continue
            lat = val if re.fullmatch(r'[A-Za-z\'\- ]{2,40}', val) else translit_ru(val)
            bad = str((values.get(dst) or {}).get('value') or '')
            if lat and (not bad or not re.search(r'[^A-Za-z\'\- ]', bad) is False
                        or len(bad) > len(lat) + 4):
                values[dst] = {'value': lat.strip().title(), 'block': 'person',
                               'block_title': 'Личные данные', 'method': 'rule',
                               'confidence': 'high', 'quote': val[:40]}
    except Exception:                                                 # noqa: BLE001
        pass

    # реквизиты организации из документов клиента: у него почти всегда есть
    # договор или справка с ИНН, КПП, ОГРН и адресом работодателя
    try:
        from services.company_parse import looks_like_company_doc, parse_company
        if looks_like_company_doc(text):
            comp = parse_company(text)
            # Реквизиты берём только когда есть настоящие номера (ИНН/ОГРН):
            # слово «Limited» встречается и в бланках («Signature», «Suite C»),
            # а без реквизитов проверить название нечем — организация тогда
            # приходит из карточки заявки, и подменять её нельзя
            if comp.get('company_inn') or comp.get('company_ogrn'):
                for k, v in comp.items():
                    if v and k not in values:
                        values[k] = {'value': str(v).strip(), 'block': 'company',
                                     'block_title': 'Реквизиты организации', 'method': 'rule',
                                     'confidence': 'high', 'quote': ''}
    except Exception:                                             # noqa: BLE001
        pass

    for var, val in (report['needs_human'] or {}).items():
        values['_check:' + var] = {'value': str(val).strip(), 'block': '', 'block_title': '',
                                   'method': 'llm', 'confidence': 'check', 'quote': ''}
    if rejected:
        values['_rejected:' + kind] = {'value': ', '.join(rejected), 'block': '', 'block_title': '',
                                       'method': 'llm', 'confidence': 'check', 'quote': ''}

    return {'state': 'parsed', 'note': '', 'text': text, 'kind': kind,
            'values': values, 'blocks': blocks,
            'method': 'rule+llm' if llm else 'rule'}


def _person_of(title: str, values: dict, main_name: str) -> tuple:
    """Кто из людей в папке «владеет» этим документом.

    В одной папке клиента лежат документы нескольких человек (заявитель, супруг,
    ребёнок) — например, три паспорта в деле Карповых. Если это не размечать,
    номер паспорта ребёнка может попасть в документы заявителя.
    Признаки: префикс имени файла («ANZHELIKA__…») и ФИО внутри документа.
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-zа-яё]", "", str(s or '').lower())

    def latin(s: str) -> str:
        # кириллица и латиница об одном человеке: «СУРКОВ» и «SURKOV» —
        # сравниваем ещё и транслитерацией, иначе паспорт считается «чужим»
        try:
            from bot.ai_parser import translit_ru
            return re.sub(r"[^a-z]", "", translit_ru(str(s or '')).lower())
        except Exception:                                     # noqa: BLE001
            return ''

    def garbage(s: str) -> bool:
        try:
            from services.pool_assign import _looks_like_garbage as g
            return g(s)
        except Exception:                                     # noqa: BLE001
            return False

    # «Passport Number Nomor Paspor», «Bank Statement» — это не имя человека,
    # а служебные слова, вытащенные из бланка: по ним нельзя решить, что документ
    # чужой, иначе данные заявителя теряются
    _NOT_NAME = ('passport', 'number', 'nomor', 'bank', 'statement', 'agreement',
                 'guarantee', 'work', 'visa', 'itk', 'company', 'letter', 'contract',
                 'invoice', 'period', 'balance', 'account', 'recipient', 'sender')

    def looks_like_person(s: str) -> bool:
        words = re.findall(r'[A-Za-zА-Яа-яЁё]{3,}', str(s or ''))
        if not words or len(words) > 3:
            return False
        return not any(w.lower().startswith(_NOT_NAME) for w in words)

    def val(name: str) -> str:
        # значения в пуле лежат как {'value':…, 'block':…}, а не строкой
        item = values.get(name)
        if isinstance(item, dict):
            return str(item.get('value') or '')
        return str(item or '')

    doc_name = val('full_name_latin') or val('surname') or ''
    doc_norm, main_norm = norm(doc_name), norm(main_name)
    doc_lat, main_lat = latin(doc_name), latin(main_name)

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
    if not doc_norm or not looks_like_person(doc_name):
        # имени в документе нет (или это служебные слова бланка) — пробуем
        # понять из имени файла («ANZHELIKA__…»)
        person = 'main'
        m = re.match(r'^([A-Z][A-Za-z]{2,})[ _-]+[A-Z]?', str(title))
        if m and looks_like_person(m.group(1)):
            doc_name = m.group(1)
            cand = latin(doc_name)
            person = 'main' if (main_bad or (cand and cand in main_lat)) else 'other'
    else:
        person = 'main' if (same or main_bad) else 'other'
    return person, doc_name[:60]


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
                    if not name or name.startswith('.'):
                        continue
                    out_dir.mkdir(parents=True, exist_ok=True)
                    target = out_dir / name
                    if not target.exists():
                        with zf.open(info) as src, open(target, 'wb') as dst:
                            dst.write(src.read())
                    known = conn.execute(
                        'SELECT 1 FROM client_documents WHERE client_id=? AND path=?',
                        (client_id, str(target))).fetchone()
                    if not known:
                        conn.execute(
                            'INSERT INTO client_documents (client_id, kind, title, path, uploaded_at) '
                            "VALUES (?,?,?,?,datetime('now'))",
                            (client_id, 'other', ('%s / %s' % (z.name, name))[:180], str(target)))
                        added += 1
        except Exception as e:                                 # noqa: BLE001
            print('   архив %s не распакован: %s' % (z.name[:40], str(e)[:80]))
    if added:
        print('   из архивов добавлено файлов: %d' % added)
    return added


def build_for_client(client_id: int, application_id: int | None = None,
                     use_llm: bool = False, force: bool = False, verbose: bool = True) -> dict:
    """Собрать пул значений по клиенту. Возвращает статистику."""
    conn = _db()
    # ФИО заявителя: по нему размечаем, чьи значения в пуле
    row = conn.execute('SELECT surname, name, full_name_latin, full_name_title FROM clients WHERE id=?',
                       (client_id,)).fetchone()
    main_name = ''
    if row:
        main_name = (row['full_name_latin'] or row['full_name_title']
                     or ' '.join(x for x in (row['surname'], row['name']) if x) or '')
    # архивы раскрываем до чтения: внутри них те же документы клиента
    expand_archives(client_id, conn)
    if force:
        # полная пересборка: прежние значения убираем, иначе в пуле остаются
        # записи от старых правил разбора (например мусорные названия компании)
        conn.execute('DELETE FROM client_values_pool WHERE client_id=?', (client_id,))
        conn.commit()
    docs = list(conn.execute(
        'SELECT * FROM client_documents WHERE client_id=? ORDER BY title', (client_id,)))
    if not docs:
        # Документы могли быть скачаны с Диска, но как источники не заведены:
        # разбор заявки кладёт файлы в кэш клиента, а пул читает client_documents.
        # Без этой связки пул остаётся пустым и бланки печатаются без данных.
        # Папка клиента может лежать не только в кэше, но и в архиве выгрузок
        # (скачана скриптом/вручную) — берём первую найденную.
        folders = [CACHE / ('client_%d' % client_id)]
        for _nm in {main_name, (row['full_name_title'] if row else '')}:
            if _nm:
                folders.append(ARCHIVE / _nm)
        folders += [p.parent for p in (Path(r['photo_path']).parent for r in conn.execute(
            'SELECT photo_path FROM clients WHERE id=? AND photo_path IS NOT NULL', (client_id,))
            if r['photo_path'])]
        folder = next((p for p in folders if p.is_dir()), None)
        if folder is not None:
            kinds = {'.pdf': 'other', '.png': 'photo', '.jpg': 'photo', '.jpeg': 'photo',
                     '.heic': 'photo', '.doc': 'other', '.docx': 'other'}
            # Фотография клиента определяется по имени файла, а не по расширению:
            # в папке лежат и фото, и снимки паспорта/ITK — все в PNG. Читать и
            # распознавать содержимое не нужно, достаточно знать, что файл есть:
            # имя с «foto/photo/фото/портрет» — это и есть фотография для пакета.
            _photo_words = ('foto', 'photo', 'фото', 'портрет', 'portrait', 'selfie', 'snapshot')
            for f in sorted(folder.rglob('*')):
                if not f.is_file() or f.suffix.lower() not in kinds:
                    continue
                if any(m in str(f).lower() for m in _GENERATED_MARKERS):
                    continue        # наш собственный документ, не источник данных
                _stem = f.stem.lower()
                _kind = 'photo' if any(w in _stem for w in _photo_words) else 'other'
                conn.execute(
                    'INSERT INTO client_documents (client_id, kind, title, path, uploaded_at) '
                    "VALUES (?,?,?,?,datetime('now'))",
                    (client_id, _kind, f.name[:180], str(f)))
            conn.commit()
            docs = list(conn.execute(
                'SELECT * FROM client_documents WHERE client_id=? ORDER BY title', (client_id,)))
    stat = {'client_id': client_id, 'docs': len(docs), 'new': 0, 'skipped': 0,
            'empty': 0, 'errors': 0, 'values': 0, 'changed': 0}

    for d in docs:
        path = Path(d['path'])
        if not path.exists():
            continue
        state = d['state'] or 'new'
        # уже прочитан и файл не менялся — не перечитываем
        if not force and state in ('parsed', 'empty', 'error'):
            stat['skipped'] += 1
            continue

        res = read_one(path, use_llm)
        stat[res['state'] if res['state'] in ('empty', 'error') else 'new'] = \
            stat.get(res['state'] if res['state'] in ('empty', 'error') else 'new', 0) + 1

        payload = json.dumps(res.get('blocks', []), ensure_ascii=False)[:4000]
        conn.execute(
            "UPDATE client_documents SET doc_kind=?, blocks_json=?, text_hash=?, text_len=?, "
            "read_at=datetime('now'), state=?, method=?, note=? WHERE id=?",
            (res['kind'], payload, _hash(res['text']), len(res['text']),
             res['state'], res.get('method', ''), res['note'][:200], d['id']))

        for var, info in (res['values'] or {}).items():
            if var.startswith('_'):
                continue
            person, person_name = _person_of(d['title'], res['values'], main_name)
            conn.execute(
                "INSERT INTO client_values_pool (client_id, application_id, variable_name, value, "
                "doc_kind, source_file, source_block, quote, person, person_name, method, confidence) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(client_id, variable_name, source_file) DO UPDATE SET "
                "value=excluded.value, source_block=excluded.source_block, quote=excluded.quote, "
                "person=excluded.person, person_name=excluded.person_name, "
                "method=excluded.method, confidence=excluded.confidence, updated_at=datetime('now')",
                (client_id, application_id, var, info['value'], res['kind'],
                 d['title'], info.get('block') or '', info.get('quote') or '',
                 person, person_name, info.get('method') or '', info.get('confidence') or 'medium'))
            stat['values'] += 1

        if verbose:
            print('   [%-7s] %-44s %s' % (res['state'], d['title'][:44],
                                          'значений: %d' % len([v for v in res['values'] if not v.startswith('_')])))

    total_pool = conn.execute('SELECT COUNT(*) FROM client_values_pool WHERE client_id=?',
                              (client_id,)).fetchone()[0]
    stat['pool_total'] = total_pool
    return stat


def main() -> None:
    use_llm = '--llm' in sys.argv
    force = '--force' in sys.argv
    app = None
    if '--app' in sys.argv:
        app = int(sys.argv[sys.argv.index('--app') + 1])
    t0 = time.time()

    conn = _db()
    if '--all' in sys.argv:
        ids = [r[0] for r in conn.execute(
            'SELECT DISTINCT client_id FROM client_documents ORDER BY client_id')]
        print('клиентов: %d, модель: %s' % (len(ids), 'да' if use_llm else 'нет'))
        total = 0
        for cid in ids:
            st = build_for_client(cid, app, use_llm, force, verbose=False)
            total += st['values']
            print('   client_%-3d документов %-3d новых %-3d пропущено %-3d значений %-4d '
                  'в пуле %d' % (cid, st['docs'], st['new'], st['skipped'], st['values'],
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
    for r in conn.execute('SELECT variable_name, value, source_block, source_file, method '
                          'FROM client_values_pool WHERE client_id=? ORDER BY source_file, id',
                          (cid,)):
        print('   %-20s %-30s блок=%-10s %s [%s]' % (
            r['variable_name'], str(r['value'])[:30], r['source_block'] or '-',
            r['source_file'][:34], r['method']))


if __name__ == '__main__':
    main()
