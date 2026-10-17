"""Приём заявки: проверка минимального набора и разбор свободного текста менеджера.

Задача (заказчик, 06.10.2026): менеджер присылает заявку в свободной форме — текстом и ссылкой
на Google Диск. Система должна:

  1. понять из текста, какой это тип продукта (мостовая виза, C1, D12, E36G новый/продление, конверсия);
  2. проверить, что на Диске лежит минимальный набор документов клиента для этого продукта
     (паспорт и фотография — всегда; справка банка — период по продукту; KITAS — для продления и конверсии);
  3. проверить, что известны ключевые значения, без которых пакет не собрать
     (для мостовой — чем занимается клиент; для нового E33G — организация-работодатель вне Индонезии);
  4. сказать прямо: чего не хватает (система стопорится и просит у менеджера) и что она
     сформирует сама (суммы, даты, номера, письма, справки, договор).

Документы клиента определяем ПО ЗНАЧЕНИЯМ, а не по имени файла: паспорт может выглядеть
по-разному. Признаки: распознанные значения (номер паспорта, дата рождения) или файл-скан
паспорта в папке клиента.
"""
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'

PRODUCT_HINTS = [
    ('BRIDGING', r'мостов|bridging|переходн|bridge'),
    ('CONV', r'конверс|alih\s*status|смен(а|ить)\s*(визы|разрешен)|conversion'),
    ('C1-EXT', r'(продл|extension|продление).{0,25}\bc1\b|\bc1\b.{0,25}(продл|extension)|c1-ext'),
    ('C1', r'\bc1\b|виза\s*c1|c1\s*виза|рабоч(ая|ую)\s*виз'),
    ('D12', r'\bd12\b|pra-?invest|д12|инвесторск'),
    ('E33G-EXT', r'(продл|extension|продление).{0,25}e33g|e33g.{0,25}(продл|extension)|e33g-ext'),
    ('E33G-NEW', r'e33g|remote\s*worker|удаленн|китас\s*(работника|remot)'),
]

# минимальный набор по продукту: ключ → как проверить
MIN_DOCS = {
    'passport': 'Загранпаспорт клиента (мин. набор — всегда)',
    'photo': 'Фотография клиента (мин. набор — всегда)',
}
BANK_PERIOD = {'E33G-NEW': '12 месяцев', 'C1': '3 месяца', 'C1-EXT': '3 месяца',
               'D12': '3 месяца', 'E33G-EXT': '3 месяца', 'BRIDGING': '3 месяца', 'CONV': '3 месяца'}


def _con():
    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    con.row_factory = sqlite3.Row
    return con


def product_from_text(text: str):
    """Определить тип продукта по свободному тексту менеджера."""
    t = (text or '').lower()
    for code, pat in PRODUCT_HINTS:
        if re.search(pat, t):
            return code
    return None


def _client_dir(client_id) -> Path | None:
    """Папка документов клиента: кэш → архив выгрузок → папка из photo_path.

    Раньше смотрели только кэш, и по клиентам, чьи папки скачаны в архив
    (data/gdrive_archive/<ФИО>), приёмка честно врала: «нет паспорта и фото»,
    хотя файлы лежат на диске. Проверка «есть ли минимум» должна видеть все
    известные места, где система уже держит документы клиента.
    """
    cands = [ROOT / 'data/gdrive_cache' / ('client_%s' % client_id)]
    try:
        con = _con()
        row = con.execute('SELECT full_name_latin, full_name_title, photo_path FROM clients WHERE id=?',
                          (client_id,)).fetchone()
    except Exception:                                              # noqa: BLE001
        row = None
    if row:
        for nm in (row['full_name_latin'], row['full_name_title']):
            if nm:
                cands.append(ROOT / 'data/gdrive_archive' / nm)
        if row['photo_path']:
            cands.append(Path(row['photo_path']).parent)
    for p in cands:
        if p.is_dir():
            return p
    return None


def client_docs_status(app_id) -> dict:
    """Что из документов клиента реально есть (по значениям и по файлам-сканам)."""
    con = _con()
    app = con.execute("""SELECT a.id, a.client_id, a.brief, c.full_name_latin, c.passport_number,
                                c.birth_date, c.birth_place, c.citizenship, c.passport_expiry,
                                c.address_live, c.position
                         FROM applications a LEFT JOIN clients c ON c.id=a.client_id
                         WHERE a.id=?""", (app_id,)).fetchone()
    if not app:
        return {}
    cid = app['client_id']
    folder = _client_dir(cid) if cid else None
    names = []
    if folder:
        names = [f.name.lower() for f in folder.rglob('*') if f.is_file()
                 and 'wolf autodoc' not in f.name.lower()]
    try:
        from services import doc_overrides as do
        doc_vals = do.for_application(app_id)
    except Exception:  # noqa: BLE001
        doc_vals = {}
    con2 = _con()
    try:
        scans = [r['payload'] for r in con2.execute(
            "SELECT payload FROM drive_scans WHERE application_id=? AND status='ok'", (app_id,))]
    except Exception:  # noqa: BLE001
        scans = []
    scan_text = ' '.join(s or '' for s in scans).lower()

    has_passport = bool(app['passport_number'] or doc_vals.get('passport_number')
                        or app['birth_date'] or doc_vals.get('birth_date')
                        or any(re.search(r'passport|паспорт|paspor', n) for n in names)
                        or 'passport' in scan_text)
    has_photo = bool(any(re.search(r'photo|фото|personal|foto', n) for n in names)
                     or (doc_vals.get('client_photo') or ''))
    has_bank = bool(doc_vals.get('balance_rub') or doc_vals.get('account_no')
                    or any(re.search(r'bank|statement|выписка|справк.*банк|остатк', n) for n in names)
                    or 'balance' in scan_text)
    has_kitas = bool(doc_vals.get('itk_no') or app['passport_expiry'] and False
                     or any(re.search(r'kitas|itk|\bkit\b|permit', n) for n in names)
                     or re.search(r'stay permit|kitas|itk', scan_text))
    has_address = bool(app['address_live'] or doc_vals.get('address_live'))
    return {
        'client_id': cid, 'name': app['full_name_latin'], 'folder_files': len(names),
        'passport': has_passport, 'photo': has_photo, 'bank': has_bank,
        'kitas': has_kitas, 'address': has_address,
        'profession': bool(app['position'] or doc_vals.get('occupation')
                           or re.search(r'должност[ьи]\s*[:—-]\s*\S', (app['brief'] or ''), re.I)),
        'doc_values': sorted(doc_vals.keys())[:20],
    }


def gate(app_id) -> dict:
    """Вердикт: можно ли собрать пакет автоматически, и чего не хватает."""
    con = _con()
    app = con.execute("""SELECT a.id, a.product_id, p.code AS product_code, p.name AS product_name,
                                a.comment, a.brief, a.gdrive_url, a.status
                         FROM applications a LEFT JOIN products p ON p.id=a.product_id
                         WHERE a.id=?""", (app_id,)).fetchone()
    if not app:
        return {'ok': False, 'stops': ['заявка не найдена']}
    code = app['product_code']
    free_text = ' '.join(str(x) for x in (app['comment'], app['brief']) if x)
    product_from_notes = None
    if not code:
        product_from_notes = product_from_text(free_text)
        code = product_from_notes
    st = client_docs_status(app_id)
    stops, have, auto = [], [], []

    if not code:
        stops.append('тип продукта не определён — в заявке нет названия продукта, и из текста понять не удалось')
    else:
        if not st.get('passport'):
            stops.append('нет паспорта клиента (ни скана в папке, ни распознанных данных) — '
                         'из него берём ФИО, номер, даты, гражданство')
        if not st.get('photo'):
            stops.append('нет фотографии клиента — она идёт в документы пакета')
        if not st.get('bank'):
            stops.append('нет справки банка об остатке (для %s нужен период %s)'
                         % (code, BANK_PERIOD.get(code, '3 месяца')))
        if code in ('E33G-EXT', 'C1-EXT', 'CONV') and not st.get('kitas'):
            stops.append('нет действующего KITAS/ITK — без него не собрать %s' % code)
        if code in ('BRIDGING', 'C1', 'E33G-NEW') and not st.get('profession'):
            stops.append('не указано, чем занимается клиент (профессия/должность) — '
                         'для %s это обязательное поле' % code)
        if not st.get('address'):
            stops.append('нет адреса клиента (из карточки или документа)')
    for k, label in MIN_DOCS.items():
        if st.get(k):
            have.append(label)
    auto = ['суммы и суммы прописью', 'даты и сроки (от даты договора)', 'номера документов',
            'перечень услуг и формулировки', 'справки, письма иммиграции, договоры, резюме',
            'организация-работодатель вне Индонезии (из справочника)']
    return {
        'application': app_id, 'product': code, 'product_name': app['product_name'],
        'product_from_notes': product_from_notes, 'status': app['status'],
        'ok': not stops, 'stops': stops, 'have': have, 'auto': auto,
        'bank_period': BANK_PERIOD.get(code or '', '3 месяца'),
    }


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description='Проверка заявки перед автоматической сборкой')
    ap.add_argument('--app', type=int, help='номер заявки')
    ap.add_argument('--text', help='свободный текст заявки от менеджера (проверить разбор продукта)')
    ap.add_argument('--all', action='store_true', help='прогнать все заявки')
    a = ap.parse_args(argv)
    if a.text is not None:
        print('текст → продукт:', product_from_text(a.text) or 'не определён')
        return 0
    if a.all:
        con = _con()
        ids = [r['id'] for r in con.execute('SELECT id FROM applications ORDER BY id')]
        stop_total = 0
        for i in ids:
            g = gate(i)
            if not g['ok']:
                stop_total += 1
                print('№%-4s %-9s СТОП: %s' % (i, g['product'] or '—', '; '.join(g['stops'][:3])))
        print('всего заявок: %d, с блокировкой: %d' % (len(ids), stop_total))
        return 0
    if a.app:
        print(json.dumps(gate(a.app), ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
