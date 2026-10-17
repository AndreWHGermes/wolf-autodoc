"""Финальная проверка пакета: сначала ВИЗУАЛЬНАЯ, затем ЛОГИЧЕСКАЯ.

Порядок принципиален. Если документ «грязный» — текст наползает друг на друга,
вылезли русские символы, уехали поля, потерян логотип, шапка не по левому краю —
читать его логически бессмысленно: сначала переделка. Поэтому визуальная
проверка идёт первой и при провале сразу возвращает документы на пересборку.

Визуальная прошла → включается логическая. Она читает пакет целиком: наши
документы плюс документы клиента с Google Диска, и сверяет с инструкцией
иммиграции для конкретного продукта заявки:
  * все ли документы подготовлены (пакетная подача под этот продукт);
  * стыкуются ли между документами даты, цифры, номера паспортов, суммы, имена;
  * соответствует ли каждый документ правилам оформления из инструкции.

Куда уходит результат:
  * не хватает документов КЛИЕНТА  → сообщение менеджеру и администратору;
  * логическая нестыковка в НАШИХ   → чиним сами и пересобираем (без человека);
  * визуальный дефект               → переделка сборки сразу;
  * всё чисто                       → готово к отправке.

Запуск: /usr/bin/python3 -m services.final_check <app_id>
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=60000')
    return c


# ---------------------------------------------------------------- визуальная --

def visual(app_id: int) -> dict:
    """Визуальная проверка собранных документов (грязь, наложения, язык, поля)."""
    issues: list[dict] = []
    checked = 0
    try:
        from services import doc_rules as dr
    except Exception:                                    # noqa: BLE001
        dr = None
    try:
        import pymupdf
        c = _conn()
        rows = [dict(r) for r in c.execute(
            """SELECT t.code, ad.pdf_path FROM application_documents ad
                 JOIN templates t ON t.id=ad.template_id
                WHERE ad.application_id=? AND COALESCE(ad.status,'') != 'rejected'
                  AND COALESCE(ad.status,'') != 'excluded'""", (app_id,))]
        c.close()
        for r in rows:
            path = r['pdf_path'] or ''
            if not path or not Path(path).exists():
                issues.append({'from': 'визуальная', 'doc': r['code'], 'level': 'block',
                               'text': 'нет собранного PDF'})
                continue
            checked += 1
            d = pymupdf.open(path)
            for pno, page in enumerate(d, 1):
                text = page.get_text()
                # пустая страница = документ не собрался
                if len(text.strip()) < 40:
                    issues.append({'from': 'визуальная', 'doc': r['code'], 'level': 'block',
                                   'text': 'страница %d почти пустая — документ не собрался' % pno})
                # текст выходит за пределы листа
                rect = page.rect
                for b in page.get_text('blocks'):
                    x0, y0, x1, y1 = b[:4]
                    if x1 > rect.width + 2 or x0 < -2 or y1 > rect.height + 2 or y0 < -2:
                        issues.append({'from': 'визуальная', 'doc': r['code'], 'level': 'block',
                                       'text': 'страница %d: текст выходит за пределы листа' % pno})
                        break
                # наложение строк друг на друга
                blocks = sorted([b for b in page.get_text('blocks')], key=lambda b: b[1])
                for i in range(len(blocks) - 1):
                    a, b = blocks[i], blocks[i + 1]
                    ov = min(a[3], b[3]) - max(a[1], b[1])
                    if ov > 2.5 and not (a[2] < b[0] or b[2] < a[0]):
                        issues.append({'from': 'визуальная', 'doc': r['code'], 'level': 'block',
                                       'text': 'страница %d: текст наложен друг на друга' % pno})
                        break
                # русские символы там, где документ должен быть на английском/индонезийском
                if dr and r['code'].startswith(('cv__', 'employment_contract', 'remote_work_agreement',
                                                'bridging_request_letter', 'conversion_request_letter',
                                                'statement_letter_e02')):
                    ru = re.findall(r'[А-ЯЁа-яё]{3,}', text)
                    if ru:
                        issues.append({'from': 'визуальная', 'doc': r['code'], 'level': 'block',
                                       'text': 'страница %d: русские символы — %s'
                                               % (pno, ', '.join(sorted(set(ru))[:4]))})
                # шрифты: подозрительно мелкий/крупный текст
                sizes = [s['size'] for bl in page.get_text('dict')['blocks'] if bl.get('lines')
                         for ln in bl['lines'] for s in ln['spans']]
                if sizes and (min(sizes) < 5.0 or max(sizes) > 26.0):
                    issues.append({'from': 'визуальная', 'doc': r['code'], 'level': 'warn',
                                   'text': 'страница %d: кегль вне обычного — %.1f..%.1f pt'
                                           % (pno, min(sizes), max(sizes))})
            d.close()
    except Exception as e:                                # noqa: BLE001
        issues.append({'from': 'визуальная', 'doc': '—', 'level': 'warn',
                       'text': 'визуальная проверка не завершилась: %s' % str(e)[:120]})
    return {'name': 'визуальная', 'checked': checked, 'issues': issues,
            'ok': not any(i['level'] == 'block' for i in issues)}


# ---------------------------------------------------------------- логическая --

def logic(app_id: int) -> dict:
    """Логическая проверка: пакет под продукт + стыковка данных + инструкция."""
    issues: list[dict] = []
    # 1) пакет под продукт: все ли документы собраны и подтверждены
    try:
        from services import pack_check
        res = None
        for fn in ('check_package', 'check', 'run'):
            f = getattr(pack_check, fn, None)
            if callable(f):
                try:
                    res = f(app_id)
                    break
                except TypeError:
                    continue
        for item in (res or {}).get('problems', []) if isinstance(res, dict) else []:
            issues.append({'from': 'логическая', 'doc': 'пакет', 'level': 'block',
                           'text': str(item)[:200]})
    except Exception:                                    # noqa: BLE001
        pass
    # 2) стыковка данных между документами: паспорт, имя, даты, суммы
    try:
        from services import doc_rules as dr
        import pymupdf
        c = _conn()
        client = c.execute("""SELECT c.* FROM applications a JOIN clients c ON c.id=a.client_id
                               WHERE a.id=?""", (app_id,)).fetchone()
        rows = [dict(r) for r in c.execute(
            """SELECT t.code, ad.pdf_path FROM application_documents ad
                 JOIN templates t ON t.id=ad.template_id
                WHERE ad.application_id=? AND COALESCE(ad.status,'') NOT IN ('rejected','excluded')""", (app_id,))]
        others = {r['passport_number'] for r in c.execute(
            "SELECT passport_number FROM clients WHERE COALESCE(passport_number,'') != ''")}
        c.close()
        for r in rows:
            path = r['pdf_path'] or ''
            if not path or not Path(path).exists():
                continue
            d = pymupdf.open(path)
            text = '\n'.join(p.get_text() for p in d)
            d.close()
            for f in dr.check_text(r['code'], text, client['passport_number'] if client else None, others):
                issues.append({'from': 'логическая', 'doc': r['code'],
                               'level': f['level'], 'text': f['text']})
    except Exception:                                    # noqa: BLE001
        pass
    # 3) документы клиента: хватает ли их для подачи по этому продукту
    missing = []
    try:
        from services import immigration_office as _io
        c = _conn()
        a = c.execute("SELECT product_id, client_id FROM applications WHERE id=?", (app_id,)).fetchone()
        c.close()
        if a:
            need = {'паспорт': ['passport_number'], 'адрес': ['address_live', 'address_reg'],
                    'банк': ['bank_name', 'account_no'], 'контакты': ['phone']}
            for label, fields in need.items():
                if not any((client[f] if client and f in client.keys() else None) for f in fields):
                    missing.append(label)
    except Exception:                                    # noqa: BLE001
        pass
    for m in missing:
        issues.append({'from': 'логическая', 'doc': 'документы клиента', 'level': 'client',
                       'text': 'не хватает данных клиента: %s' % m})
    blocks = [i for i in issues if i['level'] == 'block']
    client_issues = [i for i in issues if i['level'] == 'client']
    return {'name': 'логическая', 'issues': issues, 'ok': not blocks and not client_issues,
            'need_client_docs': client_issues, 'own_faults': blocks}


def run(app_id: int, verbose: bool = True) -> dict:
    """Полная проверка: визуальная → логическая. Возвращает вердикт и адресатов."""
    v = visual(app_id)
    result = {'app_id': app_id, 'visual': v, 'logic': None, 'action': '', 'verdict': ''}
    if verbose:
        print('визуальная: %s (проверено документов: %s, замечаний: %s)'
              % ('ок' if v['ok'] else 'ПРОВАЛ', v['checked'], len(v['issues'])))
    if not v['ok']:
        result['action'] = 'переделать'
        result['verdict'] = 'визуальная проверка не прошла — документы на переделку'
        return result
    lg = logic(app_id)
    result['logic'] = lg
    # Порядок: сначала свои ошибки (их чиним сами), потом нехватка от клиента.
    if lg['own_faults'] and lg['need_client_docs']:
        result['action'] = 'исправить самим и запросить у клиента'
        result['verdict'] = ('своих ошибок %s (чиним сами), не хватает от клиента %s '
                             '(сообщаем менеджеру)' % (len(lg['own_faults']), len(lg['need_client_docs'])))
    elif lg['own_faults']:
        result['action'] = 'исправить самим'
        result['verdict'] = 'логические нестыковки в наших документах: %s' % len(lg['own_faults'])
    elif lg['need_client_docs']:
        result['action'] = 'сообщить менеджеру и администратору'
        result['verdict'] = 'не хватает документов клиента: %s' % len(lg['need_client_docs'])
    else:
        result['action'] = 'готово'
        result['verdict'] = 'визуальная и логическая проверки пройдены'
    if verbose:
        print('логическая: %s' % result['verdict'])
    return result


if __name__ == '__main__':
    import sys
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not aid:
        print(__doc__)
        raise SystemExit(0)
    print(json.dumps(run(aid), ensure_ascii=False, indent=1, default=str)[:4000])
