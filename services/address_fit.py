"""Адрес в документе — одна строка, не длиннее эталона.

Правило заказчика (16.10.2026): эталон длины — значение, которое стоит в переменной
address_in_indonesia в панели конструктора (для E-02: 'JL. DESA CEPAKA, CEPAKA, KEDIRI,
TABANAN, BALI 80351' = 274.7 pt при 9.5 pt). Всё, что длиннее, СОКРАЩАЕТСЯ (сокращения
названий + отбрасывание второстепенных частей), а не переносится на вторую строку.
Кегль остаётся 9.5 pt — как в оригинале формы.
"""
from __future__ import annotations

import re

VALUE_X0 = 240.1
FIELD_RIGHT = 538.28
SHEET_RIGHT = 600.0
FALLBACK_MAX_W = 274.7      # ширина эталонного значения E-02 при 9.5 pt
BASE_SIZE = 9.5

ABBR = (('JALAN', 'JL.'), ('KECAMATAN', 'KEC.'), ('KABUPATEN', 'KAB.'), ('KELURAHAN', 'KEL.'),
        ('PROVINSI', 'PROV.'), ('PROVINCE', 'PROV.'), ('GANG', 'GG.'),
        ('NOMOR', 'NO.'), ('STREET', 'ST.'), ('BANJAR', 'BJR.'))
DROP_WORDS = ('INDONESIA', 'NEGARA')
DROP_PARTS = ('PROV.', 'PROV', 'INDONESIA', 'NEGARA', 'REPUBLIK INDONESIA')
UNIT = re.compile(r'^(BLOCK|BLK|APARTMENT|APT|UNIT|FL|FLOOR|ROOM|VILLA|GUEST HOUSE|HOTEL|RESORT|'
                  r'HOMESTAY|STAY|HOUSE|HOSTEL|BUNGALOW|NO\.?L?-?\d+)')
CITY_HINT = re.compile(r'\b(BALI|DENPASAR|UBUD|CANGGU|SEMINYAK|KUTA|GIANYAR|BADUNG|TABANAN|'
                       r'MENGWI|KEDIRI|BENOA|SANUR|JIMBARAN|KEROBOKAN)\b')

_max_w_cache: list[float] = []


def _text_w(text: str, size: float) -> float:
    from services.doc_engine import _text_width
    return _text_width(text, size, bold=True)


def _max_w() -> float:
    """Предел ширины: ширина значения-эталона из панели (template_variables)."""
    if _max_w_cache:
        return _max_w_cache[0]
    w = FALLBACK_MAX_W
    try:
        import sqlite3
        c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
        row = c.execute("""SELECT tv.default_value FROM template_variables tv
                           JOIN templates t ON t.id = tv.template_id
                           WHERE tv.name='address_in_indonesia'
                             AND t.code LIKE 'statement_letter_e02__%'
                             AND tv.default_value IS NOT NULL AND tv.default_value <> ''
                           ORDER BY CASE WHEN t.code='statement_letter_e02__default' THEN 0 ELSE 1 END
                           LIMIT 1""").fetchone()
        if row and row[0]:
            w = round(_text_w(re.sub(r'\s+', ' ', row[0]).strip().upper(), BASE_SIZE), 1)
    except Exception:
        pass
    _max_w_cache.append(w)
    return w


def _norm(text: str) -> str:
    t = re.sub(r'\s+', ' ', str(text or '')).strip().upper()
    for a, b in ABBR:
        t = re.sub(r'\b%s\b' % re.escape(a), b, t)
    t = re.sub(r'\bJL\b', 'JL.', t)
    for w in DROP_WORDS:
        t = re.sub(r'\b%s\b' % w, '', t)
    t = re.sub(r'\([^)]*$', '', t)
    t = re.sub(r'\b(\w+)( \1\b)+', r'\1', t)
    t = re.sub(r'\.\.+', '.', t)
    t = re.sub(r'\s*[,;]\s*', ', ', t)
    return re.sub(r'\s+', ' ', t).strip(' ,;.')


def _prio(part: str, idx: int, early: bool = False) -> int:
    """Чем меньше — тем раньше часть отбрасывается при сокращении."""
    p = part.strip()
    if early:
        return 1                      # вторичная улица (до основной) — уходит рано
    if UNIT.match(p):
        return 0                       # объект/юнит (Villa, Block 79…)
    if re.match(r'^(KEL\.|DS\.|BJR\.)', p):
        return 2
    if re.match(r'^PROV', p):
        return 3
    if re.match(r'^KEC\.', p):
        return 4
    if re.match(r'^KAB\.', p):
        return 5
    if idx == 0 and not re.search(r'(JL\.|GG\.|\d)', p):
        return 1                       # название комплекса перед улицей
    if re.search(r'(JL\.|GG\.|JG\.)', p):
        return 10                      # улица — держим крепче всего
    if re.search(r'\d{5}', p):
        return 9                       # почтовый индекс
    if CITY_HINT.search(p):
        return 8                       # город/район
    return 6


def fit_address(text: str, size: float = BASE_SIZE, min_size: float = 7.0) -> tuple[str, float, bool]:
    """(текст одной строкой, кегль, признак сокращения)."""
    t = _norm(text)
    orig = re.sub(r'\s+', ' ', str(text or '')).strip().upper()
    if not t:
        return '', size, False
    lim = _max_w()
    shortened = t != orig

    parts = [p.strip(' ,;.') for p in t.split(',') if p.strip(' ,;.')]
    parts = [p for p in parts if p not in DROP_PARTS]
    # часть с двумя улицами («JL. A JL. B») режем: первая улица уходит раньше последней
    expanded: list[tuple[str, bool]] = []
    for p_ in parts:
        pos = [m.start() for m in re.finditer(r'\b(?:JL\.|GG\.|JG\.)', p_)]
        if len(pos) > 1:
            frags = [(p_[a:b].strip(' ,;.'), False) for a, b in zip(pos, pos[1:] + [len(p_)])]
            frags = [f for f in frags if f[0]]
            for i, f in enumerate(frags):
                expanded.append((f[0], i < len(frags) - 1))    # все, кроме последней, вторичны
        else:
            expanded.append((p_, False))
    parts = [t_ for t_, _ in expanded]
    early = [e for _, e in expanded]
    join = lambda ps: ', '.join(ps)

    while len(parts) > 2 and _text_w(join(parts), size) > lim:
        prios = [_prio(parts[i], i, early[i]) for i in range(len(parts))]
        best = min(range(len(parts)), key=lambda i: (prios[i], -i))
        parts.pop(best)
        early.pop(best)
        shortened = True
    t = join(parts)

    # если даже улица одна не влезает — обрезка по словам, индекс сохраняем
    if _text_w(t, size) > lim:
        m = re.search(r'\b\d{5}\b', t)
        zip_txt = (' ' + m.group(0)) if m else ''
        words = (t[:m.start()] if m else t).rstrip(' ,').split()
        while words and _text_w(' '.join(words) + zip_txt, size) > lim:
            words.pop()
        t = (' '.join(words) + zip_txt).strip(' ,')
        shortened = True
    sz = size
    while sz > min_size and _text_w(t, sz) > lim:   # крайний случай: одно длинное слово
        sz = round(sz - 0.5, 1)
    return t, sz, shortened
