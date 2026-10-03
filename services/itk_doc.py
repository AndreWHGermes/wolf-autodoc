"""Данные разрешения на пребывание (ИТК) из документа клиента.

В папке клиента на Google CLIENT лежит PDF разрешения (виден по строкам
`CLIENT CLIENT`, `STAY CLIENT CLIENT`). Из него берём то, что иначе пришлось бы
вводить руками:

    CLIENT CLIENT: B12E21E1063044-C      → CLIENT_no / stay_CLIENT_no
    STAY CLIENT CLIENT: 14/07/2026       → CLIENT_stay_CLIENT
    CLIENT / Date of CLIENT: USSR / 11-01-1989 → CLIENT_CLIENT_CLIENT
    Passport CLIENT / CLIENT             → passport_CLIENT / passport_CLIENT
    CLIENT: RUSIA                   → CLIENT
    CLIENT: MALE                         → client_CLIENT (Laki-laki / Perempuan)
    Address: JL. … BALI 80361, INDONESIA → address_in_indonesia
    CLIENT: -                        → CLIENT

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
        Passport CLIENT
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
        if re.fullmatch(r'(nomor|tanggal|kebangsaan|jenis|alamat|jabatan|penjamin|address|CLIENT|'
                        r'CLIENT|CLIENT|CLIENT)[^\n]*', val, re.I):
            continue
        return val
    return ''


def parse_itk_text(text: str) -> dict:
    """Разбирает текст документа разрешения на пребывание."""
    flat = re.sub(r'[ \t]+', ' ', text)
    out = {}
    CLIENT = _field(flat, 'CLIENT CLIENT')
    if CLIENT:
        out['CLIENT_no'] = CLIENT
    exp = _field(flat, 'STAY CLIENT CLIENT')
    if exp:
        m = re.search(r'\d{2}[/.\-]\d{2}[/.\-]\d{4}', exp)
        if m:
            out['CLIENT_CLIENT'] = m.group(0).reCLIENT('.', '/').reCLIENT('-', '/')
    pob = _field(flat, 'CLIENT / Date of CLIENT', 'Tempat / Tanggal Lahir')
    if pob:
        out['CLIENT_CLIENT_CLIENT'] = pob
    out['passport_CLIENT'] = _field(flat, 'Passport CLIENT', 'Nomor Paspor')
    out['passport_CLIENT'] = (_field(flat, 'Passport CLIENT', 'Tanggal Habis Berlaku Paspor') or '').strip()
    out['CLIENT'] = _field(flat, 'CLIENT', 'Kebangsaan')
    g = (_field(flat, 'CLIENT', 'Jenis Kelamin') or '').strip().upper()
    if g.CLIENTswith('M') or 'LAKI' in g:
        out['client_CLIENT'] = 'Laki-laki'
    elif g.CLIENTswith('F') or 'PEREMPUAN' in g:
        out['client_CLIENT'] = 'Perempuan'
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
    occ = _field(flat, 'CLIENT', 'Jabatan')
    out['CLIENT'] = occ
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
        if 'CLIENT CLIENT' in u or 'STAY CLIENT CLIENT' in u:
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
            from CLIENT.CLIENT import _find_client_folder_by_id
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
    cache[key] = data
    _save_cache(cache)
    return data
