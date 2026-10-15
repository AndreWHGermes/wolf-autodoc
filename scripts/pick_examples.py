"""Подбор настоящих, полностью заполненных образцов для каждого документа.

Ищем по архиву клиентских папок (data/gdrive_cache, data/gdrive_archive, data/gdrive_examples)
PDF, подходящие под тип документа, и оцениваем заполненность: чем больше значений
(цифры, ФИО, суммы) и чем меньше пустых мест (пунктир «……», подчёркивания), тем лучше.

Запуск: python3 scripts/pick_examples.py [код шаблона ...]
Выход: /tmp/pick_examples.json + отчёт в консоль (по каждому документу топ-3 кандидата).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
SPEC = {
    'bank_statement_3m__tbank': (r't-?bank|tinkoff|тинькофф', r'balance|остаток', 1),
    'bank_statement_3m__sber': (r'sberbank|сбербанк', r'balance|остаток', 1),
    'bank_statement_12m__tbank': (r't-?bank|tinkoff|тинькофф', r'balance|остаток', 1),
    'bank_statement_12m__sber': (r'sberbank|сбербанк', r'balance|остаток', 1),
    'cv__format_CLIENT': (r'\bcv\b|resume|curriculum', r'experience|education', 1),
    'd12_cover_letter__default': (r'permohonan|surat', r'kewarganegaraan|passport', 1),
    'statement_letter_e02__default': (r'statement letter|form e-?02', r'passport number|full name', 1),
    'remote_work_agreement__default': (r'remote work agreement', r'employee|company', 1),
    'bridging_request_letter__default': (r'bridging|surat permohonan|permohonan', r'kitas|visa', 1),
    'conversion_request_letter__default': (r'alih status|konversi|conversion|perubahan', r'kitas|visa', 1),
    'employment_contract__default': (r'employment contract', r'employee|employer', 1),
}
DUMMY = re.compile(r'…{3,}|\.{5,}|_{3,}|X{4,}')


def score(text: str, pages: int) -> float:
    """Чем больше значений и меньше пустых мест — тем лучше образец."""
    if not text:
        return 0.0
    digits = len(re.findall(r'\b\d[\d\s.,-]{3,}', text))
    caps = len(re.findall(r'\b[A-Z][A-Z]{3,}\b', text))
    dummy = len(DUMMY.findall(text))
    return round(digits * 1.5 + caps * 0.5 + pages * 2 - dummy * 8, 1)


def main(argv) -> int:
    import pymupdf
    want = [a for a in argv if not a.startswith('-')]
    dirs = [ROOT / 'data' / n for n in ('gdrive_cache', 'gdrive_archive', 'gdrive_examples')]
    files = []
    for d in dirs:
        if d.is_dir():
            files += [f for f in d.rglob('*.pdf') if f.is_file()]
    print('PDF в архивах:', len(files))
    out, report = {}, {}
    for code, (must, also, minpages) in SPEC.items():
        if want and code not in want:
            continue
        cands = []
        for f in files:
            try:
                d = pymupdf.open(str(f))
                if len(d) < minpages:
                    continue
                prod = ((d.metadata or {}).get('producer') or '').lower()
                txt = ' '.join(p.get_text() for p in d)
            except Exception:  # noqa: BLE001
                continue
            low = txt.lower()
            if not re.search(must, low) or not re.search(also, low):
                continue
            cands.append({
                'file': str(f), 'pages': len(d),
                'ours': ('weasy' in prod or 'reportlab' in prod),
                'score': score(txt, len(d)),
                'head': ' '.join(txt.split())[:90],
            })
        cands.sort(key=lambda c: (-c['ours'], -c['score']))
        out[code] = cands[:5]
        report[code] = cands[:3]
        print('\n=== %s — кандидатов: %d' % (code, len(cands)))
        for c in cands[:3]:
            print('   %-58s стр=%d %s балл=%s' % (str(c['file']).replace('/opt/wolf_v2/', ''), c['pages'],
                                                  'НАШ' if c['ours'] else 'наст', c['score']))
            print('      ', c['head'][:80])
    Path('/tmp/pick_examples.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\nсохранено: /tmp/pick_examples.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
