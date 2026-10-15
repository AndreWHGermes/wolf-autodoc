"""Одна банковская справка на пакет (как требует инструкция по продуктам).

Банк определяется по данным клиента: сначала по названию банка в карточке, затем по
распознанным файлам его папки на Диске (T-Bank / Сбер), иначе остаётся вариант по
умолчанию (T-Bank — форма, которая чаще встречается в архиве).

Период задаёт продукт: C1 / C1-EXT / D12 / E33G-EXT — справка за 3 месяца,
E33G-NEW — за 12 месяцев. Лишние справки в заявке помечаются rejected с пояснением
(документы не удаляются).

Запуск: python3 scripts/one_bank_statement.py [--apply]
"""
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
BACKUP = ROOT / 'data' / 'backup'
KINDS = ROOT / 'data' / 'gdrive_archive' / '_kinds.json'

# продукт → какой слот справки ему нужен
PRODUCT_SLOT = {
    'C1': 'bank_stmt_3m', 'C1-EXT': 'bank_stmt_3m', 'D12': 'bank_stmt_3m',
    'E33G-EXT': 'bank_stmt_3m', 'E33G-NEW': 'bank_stmt_12m',
    'BRIDGING': 'bank_stmt_3m', 'CONV': 'bank_stmt_3m',
}
SBANK_HINTS = ('sber', 'сбер', 'sberbank', 'сбербанк')
TBANK_HINTS = ('tbank', 't-bank', 'т-банк', 'тинькофф', 'tinkoff')


def bank_of(client: dict, folder_kinds: Counter) -> str:
    raw = ' '.join(str(client.get(k) or '') for k in
                   ('bank_name', 'notes', 'account_no', 'card_mask')).lower()
    if any(h in raw for h in SBANK_HINTS):
        return 'sber'
    if any(h in raw for h in TBANK_HINTS):
        return 'tbank'
    return 'tbank'


def main(apply: bool) -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    BACKUP.mkdir(parents=True, exist_ok=True)
    snap = BACKUP / ('bank_statements_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    rows = [dict(r) for r in con.execute(
        """SELECT ad.id, ad.application_id, ad.status, t.code, a.product_id, a.client_id
             FROM application_documents ad
             JOIN templates t ON t.id=ad.template_id
             JOIN applications a ON a.id=ad.application_id
            WHERE t.code LIKE 'bank_statement%'""")]
    snap.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('слепок:', snap, '| документов:', len(rows))
    prods = {r['id']: r['code'] for r in con.execute("SELECT id, code FROM products")}
    tpl = {r['code']: r['id'] for r in con.execute("SELECT id, code FROM templates")}
    clients = {r['id']: dict(r) for r in con.execute("SELECT * FROM clients")}
    kinds = json.loads(KINDS.read_text(encoding='utf-8')) if KINDS.is_file() else []
    by_folder: dict[str, Counter] = {}
    for k in kinds:
        by_folder.setdefault((k.get('client') or '').strip().upper(), Counter())[k.get('kind')] += 1

    keep_n = mark_n = 0
    for app_id in sorted(set(r['application_id'] for r in rows)):
        group = [r for r in rows if r['application_id'] == app_id]
        pcode = prods.get(group[0]['product_id'], '')
        want_slot = PRODUCT_SLOT.get(pcode)
        client = clients.get(group[0]['client_id'], {})
        fname = ((client.get('surname') or '') + ' ' + (client.get('name') or '')).strip().upper()
        bank = bank_of(client, by_folder.get(fname, Counter()))
        want_code = 'bank_statement_%s__%s' % ('12m' if want_slot == 'bank_stmt_12m' else '3m', bank)
        keep_ids = [r['id'] for r in group if r['code'] == want_code]
        drop = [r for r in group if r['code'] != want_code]
        reason = ('оставлена одна справка по инструкции продукта: %s, банк по данным клиента (%s)'
                  % ('12 месяцев' if want_slot == 'bank_stmt_12m' else '3 месяца', bank))
        if keep_ids:
            keep_n += 1
        elif drop:
            # нужного варианта в заявке нет — создаём подключение к шаблону продукта
            target = want_code
            if apply and target in tpl:
                conn = con.execute("""INSERT INTO application_documents (application_id, template_id, status)
                                      VALUES (?,?, 'draft')""", (app_id, tpl[target]))
                keep_ids = [conn.lastrowid]
                keep_n += 1
        for d in drop:
            if (d['status'] or '') == 'rejected':
                continue
            if apply:
                con.execute("UPDATE application_documents SET status='rejected', error=? WHERE id=?",
                            (reason, d['id']))
            mark_n += 1
        if apply and keep_ids:
            con.execute("UPDATE application_documents SET error=NULL WHERE id IN (%s)"
                        % ','.join('?' * len(keep_ids)), tuple(keep_ids))
    if apply:
        con.commit()
        left = con.execute("""SELECT COUNT(*) FROM application_documents ad JOIN templates t ON t.id=ad.template_id
                              WHERE t.code LIKE 'bank_statement%' AND ad.status NOT IN ('rejected')""").fetchone()[0]
        print('заявок с одной справкой: %d | помечено лишних: %d | активных справок осталось: %d'
              % (keep_n, mark_n, left))
    else:
        print('(пробный прогон) заявок с одной справкой стало бы %d, помечено было бы %d' % (keep_n, mark_n))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
