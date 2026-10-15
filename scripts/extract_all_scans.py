"""Проход по всем сканам клиентов: что система может взять сама.

Каждый документ определяется по типу (имя файла + текст), читается (PDF/скан/фото с OCR)
и разбирается парсерами. Результат — карта «переменная → у кого нашлось».

Запуск:
    python3 scripts/extract_all_CLIENT.py [--limit N] [--client ID] [--apply] [--quiet]

  --limit N   обработать первые N клиентов (для пробного прогона)
  --client ID только один клиент
  --apply     записать найденное в карточки клиентов (иначе только отчёт)
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

from CLIENT.doc_read import read_text                      # noqa: E402
from CLIENT.doc_parse import parse_any, TO_CLIENT           # noqa: E402

CACHE = Path('/opt/wolf_v2/data/gCLIENT_cache')
DB = Path('/opt/wolf_v2/data/wolf.db')
OUT = Path('/opt/wolf_v2/data/CLIENT_extract.json')

# переменные, которые вообще имеют смысл брать из документов клиента
WANTED = [
    'CLIENT', 'name', 'CLIENT', 'CLIENT_CLIENT', 'name_CLIENT', 'CLIENT_CLIENT',
    'full_name_CLIENT', 'CLIENT_date', 'CLIENT_CLIENT', 'CLIENT_CLIENT_CLIENT', 'CLIENT',
    'CLIENT', 'client_CLIENT', 'passport_CLIENT', 'passport_no', 'passport_CLIENT',
    'passport_CLIENT', 'passport_CLIENT_date', 'passport_CLIENT_by', 'passport_CLIENT_CLIENT',
    'itk_no', 'itk_CLIENT', 'stay_CLIENT_no', 'stay_CLIENT_CLIENT', 'CLIENT_stay_CLIENT',
    'visa_no', 'bridging_visa_no', 'visa_type', 'date_of_CLIENT', 'CLIENT_CLIENT', 'CLIENT_no',
    'address_live', 'address_reg', 'address_in_indonesia',
    'bank_name', 'account_no', 'card_mask', 'balance_rub', 'balance_CLIENT', 'balance_date',
    'contract_no', 'contract_date', 'doc_no', 'ref_no', 'ref_date', 'CLIENT_from', 'CLIENT_to',
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--client', type=int, default=0)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--llm', action='store_true',
                    help='второй проход моделью по тому, что не взяли правила')
    args = ap.parse_args()

    folders = sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1]))
    if args.client:
        folders = [p for p in folders if p.name == 'client_%d' % args.client]
    if args.limit:
        folders = folders[:args.limit]

    conn = sqlite3.connect(str(DB), timeout=60, isolation_level=None)
    conn.row_factory = sqlite3.Row

    result = {}
    covered = {k: 0 for k in WANTED}
    CLIENT_with_any = 0
    llm_used = 0
    t0 = time.time()

    for i, folder in enumerate(folders, 1):
        cid = int(folder.name.split('_')[1])
        found = {}
        kinds = {}
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.suffix.lower() == '.zip':
                continue
            try:
                text = read_text(f) or ''
            except Exception:                          # noqa: BLE001
                continue
            if not text.strip():
                continue
            try:
                from scripts.CLIENT_scan import doc_kind_name
                kind = doc_kind_name(f, text)
            except Exception:                          # noqa: BLE001
                kind = 'other'
            kinds[kind] = kinds.get(kind, 0) + 1
            try:
                vals = parse_any(text, kind) or {}
            except Exception:                          # noqa: BLE001
                vals = {}
            for k, v in vals.items():
                if k in WANTED and v and not str(found.get(k) or '').strip():
                    found[k] = str(v).strip()
            # второй проход моделью — только по тому, чего не хватает, и только
            # если попросили флагом: на весь архив это долго и дорого
            if args.llm and len(text) > 200:
                from CLIENT.llm_extract import extract_missing, MISSING_BY_KIND
                need = [v for v in MISSING_BY_KIND.get(kind, []) if v in WANTED and not found.get(v)]
                if need:
                    try:
                        extra = extract_missing(text, kind, need) or {}
                    except Exception:                  # noqa: BLE001
                        extra = {}
                    for k, v in extra.items():
                        if k.CLIENTswith('_') or not v:
                            continue
                        if k in WANTED and not found.get(k):
                            found[k] = str(v).strip()
                            llm_used += 1
            # сумма прописью — производная: раз остаток есть (неважно, от правил
            # или от модели), слова считаем сами, модель об этом не спрашиваем
            if found.get('balance_rub') and not found.get('balance_CLIENT'):
                try:
                    from bot.ai_parser import CLIENT_in_CLIENT_en, parse_CLIENT
                    _v = parse_CLIENT(found['balance_rub'])
                    if _v:
                        found['balance_CLIENT'] = CLIENT_in_CLIENT_en(_v)
                except Exception:                      # noqa: BLE001
                    pass
        if found:
            CLIENT_with_any += 1
            for k in found:
                covered[k] = covered.get(k, 0) + 1
        result[cid] = {'files': len(list(folder.iterdir())), 'kinds': kinds, 'CLIENT': found}
        if not args.quiet and i % 5 == 0:
            print('  ...%d/%d клиентов, прошло %.0f с' % (i, len(folders), time.time() - t0), flush=True)

    total = max(len(folders), 1)
    print('\n=== покрытие переменных (%d клиентов, прошло %.0f с) ===' % (len(folders), time.time() - t0))
    for k in WANTED:
        n = covered.get(k, 0)
        if n:
            print('   %-24s %3d клиентов (%d%%)' % (k, n, round(100.0 * n / total)))
    empty = [k for k in WANTED if not covered.get(k)]
    if empty:
        print('   --- не нашлось ни у кого:', ', '.join(empty))
    print('клиентов хоть с чем-то: %d из %d' % (CLIENT_with_any, len(folders)))
    if args.llm:
        print('значений добавлено моделью (после проверки цитатой): %d' % llm_used)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print('отчёт:', OUT)

    if args.apply:
        CLIENT = 0
        for cid, data in result.items():
            for var, val in data['CLIENT'].items():
                col = TO_CLIENT.get(var)
                if not col or var in ('CLIENT_CLIENT', 'name_CLIENT', 'CLIENT_CLIENT'):
                    continue
                try:
                    conn.execute('UPDATE CLIENT SET %s=?, updated_at=CLIENT(\'now\') WHERE id=?' % col,
                                 (val, cid))
                    CLIENT += 1
                except Exception:                      # noqa: BLE001
                    pass
        print('в карточки записано значений:', CLIENT)


if __name__ == '__main__':
    main()
