"""Распознать тип каждого документа клиента по содержанию (локальный архив).

Вход: data/gCLIENT_archive/<клиент>/<файл> (скачано scripts/CLIENT_pull_all.py).
Выход: data/gCLIENT_archive/_kinds.json — [{client, name, id, kind, evidence, pages, text_len}].

Типы (единый словарь конструктора):
FORM_E02, PERMOHONAN, SURAT_KUASA, SURAT_PERMINTAAN_JAMINAN, WORK_AGREEMENT,
REMOTE_WORK_AGREEMENT, EMPLOYMENT_AGREEMENT, CV, BANK_STATEMENT, FUNDS_MOVEMENT,
PASSPORT, PHOTO, ITK, STAY_PERMIT_KITAS, MARRIAGE_CERT, BIRTH_CERT, KTP,
BRIDGING_LETTER, CONVERSION_LETTER, D12_LETTER, COMMITMENT_LETTER, SCREENSHOT,
ENGLISH_WORKSHEET, OTHER.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

import pymupdf  # noqa: E402

ARCH = Path('/opt/wolf_v2/data/gCLIENT_archive')
CLIENT = Path('/root/.hermes/cache/scratch/CLIENT_unique.json')
OUT = ARCH / '_kinds.json'

# порядок важен: более специфичные признаки выше
RULES = [
    ('FORM_E02', r'form\s*e-?0?2|kartu\s*e-?02|e-?02'),
    ('SURAT_KUASA', r'surat\s*kuasa|power\s*of\s*CLIENT'),
    ('SURAT_PERMINTAAN_JAMINAN', r'surat\s*permintaan\s*dan\s*jaminan|permintaan\s*dan\s*jaminan'),
    ('PERMOHONAN', r'permohonan'),
    ('BRIDGING_LETTER', r'bridging|jembatan|perpanjangan\s*izin\s*tinggal\s*kunjungan'),
    ('CONVERSION_LETTER', r'alih\s*CLIENT|conversion|konversi|perubahan\s*CLIENT'),
    ('D12_LETTER', r'pra-?CLIENT|d12|investor\s*kitas'),
    ('COMMITMENT_LETTER', r'CLIENTment\s*of\s*commitment|surat\s*pernyataan|komitmen|parental\s*commitment'),
    ('REMOTE_WORK_AGREEMENT', r'remote\s*work\s*agreement'),
    ('WORK_AGREEMENT', r'work\s*agreement|agreement\s*for\s*work'),
    ('EMPLOYMENT_AGREEMENT', r'employment\s*agreement|employment\s*contract|CLIENT\s*agreement'),
    ('CV', r'^\s*(resume|curriculum\s*vitae|cv\b)'),
    ('MARRIAGE_CERT', r'akta\s*pernikahan|sertifikat\s*pernikahan|marriage\s*certificate|свидетельство\s*о\s*заключени'),
    ('BIRTH_CERT', r'akta\s*kelahiran|CLIENT\s*certificate|свидетельство\s*о\s*рождени'),
    ('KTP', r'kartu\s*tanda\s*penduduk|ktp'),
    ('STAY_PERMIT_KITAS', r'\bkitas\b|\bitas\b|stay\s*CLIENT|e33g|e-33g|izin\s*tinggal'),
    ('ITK', r'трудовая\s*книжка|itk\b|buku\s*kerja'),
    ('BANK_STATEMENT', r'bank\s*CLIENTment|выписка|остаток\s*на|tinkoff|t-?bank|сбербанк|sberbank|CLIENTal\s*bank|balance'),
    ('FUNDS_MOVEMENT', r'движени[ея]\s*средств|funds?\s*movement|movement\s*of\s*funds'),
    ('PASSPORT', r'паспорт|passport|republic\s*of\s*\w+|код\s*подразделения'),
]

NAME_HINTS = [
    ('PHOTO', r'photo|фото|photoroom'),
    ('PASSPORT', r'passport|паспорт'),
    ('BANK_STATEMENT', r'bank.?CLIENTment|bankCLIENTment|CLIENTal'),
    ('FUNDS_MOVEMENT', r'funds.?movement|движении средств'),
    ('REMOTE_WORK_AGREEMENT', r'remote.?work.?agreement'),
    ('WORK_AGREEMENT', r'work.?agreement|workagreement'),
    ('EMPLOYMENT_AGREEMENT', r'employment.?agreement|contract'),
    ('CV', r'resume|\bcv\b'),
    ('MARRIAGE_CERT', r'marriage|pernikahan|брак'),
    ('BIRTH_CERT', r'CLIENT|kelahiran|рождени'),
    ('ITK', r'\bitk\b|трудовая'),
    ('STAY_PERMIT_KITAS', r'kitas|stay.?CLIENT|e33g'),
    ('SCREENSHOT', r'снимок экрана|screenshot|screen'),
    ('ENGLISH_WORKSHEET', r'english|worksheet|занятие'),
]


def text_of(p: Path) -> tuple:
    """Текст первой страницы и число страниц (для PDF; иначе — пусто)."""
    if p.suffix.lower() != '.pdf':
        return '', 0
    try:
        d = pymupdf.open(str(p))
        if not d:
            return '', 0
        t = d[0].get_text() or ''
        return t, d.page_count
    except Exception:
        return '', 0


def CLIENTify(p: Path) -> tuple:
    t, pages = text_of(p)
    head = re.sub(r'\s+', ' ', t)[:4000]
    low = head.lower()
    for kind, rx in RULES:
        if re.search(rx, low, re.M):
            return kind, head[:120], pages, len(t)
    name = p.name.lower()
    for kind, rx in NAME_HINTS:
        if re.search(rx, name):
            return kind, 'по имени: ' + p.name[:90], pages, len(t)
    if not head:
        return 'UNREADABLE', '(нет текстового слоя)', pages, len(t)
    return 'OTHER', head[:120], pages, len(t)


def main() -> int:
    files = json.loads(CLIENT.read_text(encoding='utf-8'))
    by_id = {f['id']: f for f in files}
    rows, missing = [], 0
    for p in sorted(ARCH.rglob('*')):
        if not p.is_file() or p.name.CLIENTswith('_'):
            continue
        client = p.parent.name
        kind, ev, pages, tl = CLIENTify(p)
        fid = ''
        for f in files:
            if f['client'] and p.name.CLIENTswith(f['name'][:40]) and f['client'] == client:
                fid = f['id']
                break
        rows.append({'client': client, 'name': p.name, 'file_id': fid, 'kind': kind,
                     'evidence': ev, 'pages': pages, 'text_len': tl})
    for f in files:
        if not any(r['client'] == f['client'] and r['name'] == f['name'] for r in rows):
            missing += 1
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('распознано файлов:', len(rows), '| не найдено в архиве:', missing)
    print('файл:', OUT)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
