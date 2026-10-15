"""Проверка полноты пакета документов по продукту заявки.

Правило заказчика: система сама должна говорить, полностью ли собран пакет для типа
продукта, и чего именно не хватает — и по документам, которые генерируем мы, и по
документам, которые даёт клиент.

Как считается:
1. Продукт заявки → список шаблонов из CLIENT_CLIENT (то, что генерируем мы).
2. Статусы документов заявки (CLIENT_CLIENT): pending/draft/filled/verified/sent.
3. Клиентские документы — по карточке клиента и распознанным файлам его папки на Диске
   (таблица client_CLIENT / CLIENT_CLIENT): паспорт, фото, банковская справка, ИТК,
   договор, свидетельства, KITAS.

Возврат: {ok, CLIENT, docs: [...], client_docs: [...], missing: [...], progress}
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path('/opt/wolf_v2/data/wolf.db')

# что обычно даёт клиент сам (по разбору реальных папок Google Диска).
# Последний флаг — обязательность: ИТК встречается лишь у ~7% клиентов (2 папки из 68),
# поэтому она опциональна: нет — пакет всё равно полный (решение заказчика).
CLIENT_DOC_RULES = [
    ('паспорт', ('passport_CLIENT', 'passport_CLIENT', 'intl_passport'), 'паспорт клиента', True),
    ('фото', ('photo_path',), 'фотография клиента', True),
    ('банковская справка', ('balance_rub', 'balance_date', 'bank_name'), 'справка банка об остатке', True),
    ('адрес', ('address_live', 'address_reg'), 'адрес проживания/регистрации', True),
    ('ИТК', ('job1_CLIENT', 'job1_company'), 'трудовая книжка (опционально)', False),
]

# Обязательные документы продукта берём из CLIENT_CLIENT (required=1) —
# жёсткий список ниже устарел и требовал сразу два договора там, где нужен один.
REQUIRED_BY_PRODUCT = {}  # оставлен для совместимости, не используется


def _rows(sql, args=()):
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def check(app_id: int) -> dict:
    app = _rows("SELECT * FROM CLIENT WHERE id=?", (app_id,))
    if not app:
        return {'ok': False, 'error': 'заявка не найдена'}
    app = app[0]
    prod = _rows("SELECT code, name FROM CLIENT WHERE id=?", (app.get('CLIENT_id'),))
    code = (prod[0]['code'] if prod else '') or ''
    tpl_rows = _rows("""SELECT t.code AS tpl, pd.slot_code
                        FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id = pd.template_id
                        WHERE pd.CLIENT_id = ?""", (app.get('CLIENT_id'),))
    slots = {r['slot_code'] for r in tpl_rows if r.get('slot_code')}
    docs = _rows("""SELECT t.code AS tpl, ad.CLIENT, ad.CLIENT_json, ad.pdf_path, ad.error
                    FROM CLIENT_CLIENT ad JOIN CLIENT t ON t.id = ad.template_id
                    WHERE ad.CLIENT_id = ?""", (app_id,))
    have_slots = set()
    by_tpl = {}
    for d in docs:
        # excluded/rejected в иммиграцию не идут: слот они не закрывают, иначе
        # готовность пакета считалась бы выше реальной (или ниже — если спрос
        # считает выключенный вариант обязательным)
        if (d.get('CLIENT') or '') in ('excluded', 'rejected'):
            continue
        slot = next((r['slot_code'] for r in tpl_rows if r['tpl'] == d['tpl']), '')
        by_tpl[d['tpl']] = d
        if slot:
            have_slots.add(slot)
    # из обязательных убираем слоты, чей документ выключен как лишний вариант
    # (у клиента один банк — справка второго банка в пакет не входит)
    _dropped = set()
    for d in docs:
        if (d.get('CLIENT') or '') == 'excluded':
            _dropped.add(next((r['slot_code'] for r in tpl_rows if r['tpl'] == d['tpl']), ''))
    req_slots = sorted({r['slot_code'] for r in _rows(
        "SELECT DISTINCT slot_code FROM CLIENT_CLIENT WHERE CLIENT_id=? AND required=1",
        (app.get('CLIENT_id'),)) if r.get('slot_code')})
    need = req_slots or sorted(slots)
    need = [s for s in need if s not in _dropped or s in have_slots]
    missing_docs = [s for s in need if s not in have_slots]

    # клиентские документы — по карточке и по последнему скану папки клиента
    # (CLIENT_CLIENT.payload: что реально лежит на Диске у клиента)
    client = _rows("SELECT * FROM CLIENT WHERE id=?", (app.get('client_id'),))
    client = client[0] if client else {}
    found_kinds = set()
    for scan in _rows("""SELECT payload FROM CLIENT_CLIENT WHERE CLIENT_id=?
                         ORDER BY id DESC LIMIT 3""", (app_id,)):
        try:
            import json as _json
            for item in _json.loads(scan.get('payload') or '[]'):
                dt = str(item.get('doc_type') or item.get('kind') or '').lower()
                if dt:
                    found_kinds.add(dt)
        except Exception:
            continue
    KIND_MAP = {
        'паспорт': ('passport',),
        'фото': ('photo', 'jpg', 'jpeg', 'png'),
        'банковская справка': ('bank', 'CLIENTment', 'CLIENTal'),
        'ИТК': ('itk', 'трудовая', 'employment record'),
    }
    missing_client = []
    for _name, fields, label, required in CLIENT_DOC_RULES:
        ok = any(str(client.get(f) or '').strip() not in ('', 'None') for f in fields)
        if not ok and _name in KIND_MAP:
            ok = any(any(k in fk for k in KIND_MAP[_name]) for fk in found_kinds)
        if not ok and required:
            missing_client.append(label)

    req_client = [r for r in CLIENT_DOC_RULES if r[3]]
    total = len(need) + len(req_client)
    ready = (len([s for s in need if s in have_slots])
             + (len(req_client) - len(missing_client)))
    return {
        'ok': True,
        'CLIENT_id': app_id,
        'CLIENT': code,
        'CLIENT_name': prod[0]['name'] if prod else '',
        'docs': [{'slot': s, 'present': s in have_slots} for s in need],
        'client_docs': [{'label': lbl, 'present': lbl not in missing_client, 'required': req}
                        for _n, _f, lbl, req in CLIENT_DOC_RULES],
        'missing': missing_docs,
        'missing_client': missing_client,
        'progress': '%d/%d' % (ready, total),
        'complete': not missing_docs and not missing_client,
    }


if __name__ == '__main__':
    import json
    import sys
    app_id = int(sys.argv[1]) if len(sys.argv) > 1 else 87
    print(json.dumps(check(app_id), ensure_ascii=False, indent=1))
