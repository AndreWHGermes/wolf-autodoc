"""Данные разрешения на пребывание (ИТК) из документа клиента.

В папке клиента на Google Drive лежит PDF разрешения (виден по строкам
`PERMIT NUMBER`, `STAY PERMIT EXPIRY`). Из него берём то, что иначе пришлось бы
вводить руками:

    PERMIT NUMBER: B12E21E1063044-C      → application_no / stay_permit_no
    STAY PERMIT EXPIRY: 14/07/2026       → existing_stay_permit
    Place / Date of Birth: USSR / 11-01-1989 → place_birth_inline
    Passport Number / Expiry             → passport_number / passport_expiry
    Nationality: RUSIA                   → nationality
    Gender: MALE                         → client_gender (Laki-laki / Perempuan)
    Address: JL. … BALI 80361, INDONESIA → address_in_indonesia
    Occupation: -                        → occupation

Результат кэшируется в data/itk_cache.json по id клиента: разбор PDF — дорогая операция,
а документ меняется редко.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DATA = Path('/opt/wolf_v2/data')
CACHE = DATA / 'itk_cache.json'

_MONTHS = {'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6, 'juli': 7,
           'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12,
           'january': 1, 'february': 2, 'march': 3, 'may': 5, 'june': 6, 'july': 7,
           'august': 8, 'october': 10, 'december': 12}


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    except Exception:
        pass


def _field(text: str, *labels: str) -> str:
    """Значение после метки.

    В документах ИТК метка и значение стоят на разных строках, часто в две строки
    (английская + индонезийская), а значение идёт после «:»:
        Passport Number
        Nomor Paspor
        : 772374384
    """
    low = text.lower()
    for lab in labels:
        i = low.find(lab.lower())
        if i < 0:
            continue
        tail = text[i + len(lab): i + len(lab) + 200]
        m = re.search(r':\s*\n?\s*([^\n]+)', tail)
        if not m:
            continue
        val = m.group(1).strip().strip(':').strip()
        if not val or val in ('-', '–', '—'):
            continue
        # пропускаем строки-метки (на случай, если двоеточие нашлось не там)
        if re.fullmatch(r'(nomor|tanggal|kebangsaan|jenis|alamat|jabatan|penjamin|address|occupation|'
                        r'nationality|gender|guarantor)[^\n]*', val, re.I):
            continue
        return val
    return ''


def parse_itk_text(text: str) -> dict:
    """Разбирает текст документа разрешения на пребывание."""
    flat = re.sub(r'[ \t]+', ' ', text)
    out = {}
    permit = _field(flat, 'PERMIT NUMBER')
    if permit:
        out['permit_no'] = permit
    exp = _field(flat, 'STAY PERMIT EXPIRY')
    if exp:
        m = re.search(r'\d{2}[/.\-]\d{2}[/.\-]\d{4}', exp)
        if m:
            out['permit_expiry'] = m.group(0).replace('.', '/').replace('-', '/')
    pob = _field(flat, 'Place / Date of Birth', 'Tempat / Tanggal Lahir')
    if pob:
        out['place_birth_inline'] = pob
    out['passport_number'] = _field(flat, 'Passport Number', 'Nomor Paspor')
    out['passport_expiry'] = (_field(flat, 'Passport Expiry', 'Tanggal Habis Berlaku Paspor') or '').strip()
    out['nationality'] = _field(flat, 'Nationality', 'Kebangsaan')
    g = (_field(flat, 'Gender', 'Jenis Kelamin') or '').strip().upper()
    if g.startswith('M') or 'LAKI' in g:
        out['client_gender'] = 'Laki-laki'
    elif g.startswith('F') or 'PEREMPUAN' in g:
        out['client_gender'] = 'Perempuan'
    addr = _field(flat, 'Address', 'Alamat')
    if addr:
        # значение адреса занимает две строки и заканчивается словом INDONESIA
        low = flat.lower()
        i = low.find('alamat')
        if i < 0:
            i = low.find('address')
        chunk = flat[i:i + 400] if i >= 0 else ''
        m2 = re.search(r':\s*(.+?INDONESIA)', chunk, re.S | re.I)
        out['address_in_indonesia'] = re.sub(r'\s+', ' ', m2.group(1)).strip() if m2 else addr
    occ = _field(flat, 'Occupation', 'Jabatan')
    out['occupation'] = occ
    return {k: v for k, v in out.items() if v}


def find_itk_pdf(folder: Path):
    """Ищет в папке клиента PDF разрешения на пребывание (по содержимому, затем по имени)."""
    try:
        import pymupdf
    except Exception:
        return None
    files = [f for f in folder.iterdir() if f.suffix.lower() == '.pdf' and f.is_file()]
    # сначала по имени
    named = [f for f in files if re.search(r'\b(itk|kitas|izin|stay|e33g)\b', f.name, re.I)]
    for f in named + [x for x in files if x not in named]:
        try:
            doc = pymupdf.open(f)
            t = doc[0].get_text() if doc.page_count else ''
            doc.close()
        except Exception:
            continue
        u = t.upper()
        if 'PERMIT NUMBER' in u or 'STAY PERMIT EXPIRY' in u:
            return f
    return None


def itk_data(client_id: int, folder=None) -> dict:
    """Данные разрешения на пребывание по id клиента (с кэшем)."""
    if not client_id:
        return {}
    cache = _load_cache()
    key = str(client_id)
    if key in cache:
        return cache[key]
    data = {}
    try:
        if folder is None:
            from services.values import _find_client_folder_by_id
            folder = _find_client_folder_by_id(client_id)
        if folder:
            pdf = find_itk_pdf(Path(folder))
            if pdf:
                import pymupdf
                doc = pymupdf.open(pdf)
                text = '\n'.join(p.get_text() for p in doc)
                doc.close()
                data = parse_itk_text(text)
                data['_file'] = pdf.name
    except Exception as exc:
        data = {'_error': '%s: %s' % (type(exc).__name__, exc)}
    # Пустой или неудачный разбор не кэшируем: иначе клиент навсегда остаётся
    # без срока действующего разрешения, даже когда документ появится в папке.
    if data and not data.get('_error'):
        cache[key] = data
        _save_cache(cache)
    return data
