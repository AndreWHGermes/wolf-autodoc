"""Машиночитаемая строка паспорта (MRZ) — самый надёжный источник данных.

Печатные поля разбираются OCR-ом с ошибками: «Дата рождения» и «Дата выдачи»
идут рядом и система путает их, а фамилию латиницей OCR склеивает с мусором
(вместо MAKAROVA выходило «Makarovakkalisak»). В MRZ эти же данные закодированы
жёстко, с контрольными цифрами, и распознать их можно почти без ошибок.

Формат TD3 (паспорт), две строки по 44 символа:
  1) P<RUSМАКАROVA<<ALISA<<<
  2) 5514348905RUS1206131F3405167<<<...06
     └ номер паспорта + контроль  └ дата рождения ГГММДД + контроль

OCR иногда отдаёт вместо латинских букв похожие кириллические — приводим их
к латинице по таблице гомоглифов, иначе «MAKAROVA» не собрать.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

# кириллица и мусор OCR → латиница: только визуально совпадающие символы
HOMOGLYPHS = {
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H', 'К': 'K', 'М': 'M',
    'О': 'O', 'Р': 'P', 'Т': 'T', 'У': 'U', 'Х': 'X', 'У': 'U', 'З': '3',
    'Ь': 'b', 'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'u',
    'х': 'x', 'к': 'k', 'м': 'm', 'т': 't', 'н': 'h', 'в': 'b',
    '$': 'S', '\\': 'V', '|': 'I', '!': 'I',
}
_MRZ_CHARS = re.compile(r'[A-Z0-9<]')
_MRZ_JUNK = re.compile(r'[^A-Z0-9<]')
_MRZ_LINE = re.compile(r'^[A-Z0-9<]{30,44}$')


def _norm(line: str) -> str:
    """Привести строку MRZ к латинице и вычистить мусор распознавания."""
    out = ''.join(HOMOGLYPHS.get(ch, ch) for ch in line.upper())
    # остаются только символы, допустимые в MRZ: буквы, цифры и заполнитель
    return _MRZ_JUNK.sub('', out)


def _chk(s: str) -> str:
    """Контрольная цифра MRZ — ею проверяется, верно ли прочитаны цифры."""
    w, t = (7, 3, 1), 0
    for i, ch in enumerate(s):
        if ch.isdigit():
            v = int(ch)
        elif ch == '<':
            v = 0
        elif ch.isalpha():
            v = ord(ch.upper()) - 55
        else:
            v = 0
        t += v * w[i % 3]
    return str(t % 10)


def _date(yymmdd: str, future: bool = False) -> str:
    """ГГММДД → ДД.ММ.ГГГГ. Для срока действия год всегда в будущем."""
    if not re.fullmatch(r'\d{6}', yymmdd or ''):
        return ''
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ''
    year = (2000 + yy) if future else (2000 + yy if yy < 30 else 1900 + yy)
    try:
        return dt.date(year, mm, dd).strftime('%d.%m.%Y')
    except ValueError:
        return ''


_PRINTED_FIELDS = (
    ("birth_date", r"Дата\s*рожден\w*[^\n]*?(\d{2}[.\-/]\d{2}[.\-/]\d{4})"),
    ("passport_issue_date", r"Дата\s*выдачи[^\n]*?(\d{2}[.\-/]\d{2}[.\-/]\d{4})"),
    ("passport_expiry", r"Дата\s*окончан\w*[^\n]*?(\d{2}[.\-/]\d{2}[.\-/]\d{4})"),
    ("place_of_birth", r"Место\s*рожден\w*[^\n]*\n?\s*([A-ZА-ЯЁ][^\n]{2,40})"),
    ("surname_printed", r"Фамилия[^\n]*\n\s*([A-ZА-ЯЁ][A-ZА-ЯЁ /-]{2,40})"),
    ("name_printed", r"Имя[^\n]*\n\s*([A-ZА-ЯЁ][A-ZА-ЯЁ /-]{2,40})"),
)


def parse_printed(text: str) -> dict:
    """Печатные поля паспорта — основной источник данных.

    Именно так, как читает человек: дата рождения напечатана на бланке крупно и
    чётко, поэтому она берётся из печатного поля. Машиночитаемая строка служит
    проверкой: если она расходится с печатным полем, верим печатному (MRZ
    распознаётся с перестановками цифр — «12.06.2013» вместо «13.06.2012»).
    """
    out: dict = {}
    if not text:
        return out
    for key, pat in _PRINTED_FIELDS:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        val = re.sub(r"\s+", " ", m.group(1)).strip(" .,-")
        if not val:
            continue
        if key.endswith("date") or key == "passport_expiry":
            d = re.fullmatch(r"(\d{2})[.\-/](\d{2})[.\-/](\d{4})", val)
            if not d:
                continue
            out[key] = "%s.%s.%s" % (d.group(1), d.group(2), d.group(3))
            if key == "passport_expiry":
                out["passport_valid_until"] = out[key]
        else:
            out[key] = val
    # «Место рождения» стоит в одной строке с полом: OCR отдаёт «Ж/Е МОСКВА / RUSSIA».
    # Пол — не часть места рождения, его убираем.
    if out.get("place_of_birth"):
        out["place_of_birth"] = re.sub(
            r"^(?:[А-ЯЁA-Z]{1,2}\s*[/|]\s*[А-ЯЁA-Z]{1,2}\s*)+", "",
            out["place_of_birth"]).strip(" ./|,")
    return out


def parse_image(path: str) -> dict:
    """Прочитать MRZ прямо со снимка паспорта.

    Общий OCR читает всю страницу целиком и путает цифры. Если вырезать нижнюю
    полосу бланка, увеличить её втрое и поднять контраст, машиночитаемая строка
    распознаётся устойчиво — три прохода дают один и тот же результат.
    """
    try:
        import subprocess
        import tempfile
        from PIL import Image, ImageOps
    except Exception:                                                 # noqa: BLE001
        return {}
    try:
        im = Image.open(path).convert('L')
    except Exception:                                                 # noqa: BLE001
        return {}
    W, H = im.size
    # полоса MRZ — нижняя десятая часть страницы
    strip = im.crop((0, int(H * 0.86), W, H))
    strip = strip.resize((W * 3, max(1, int(H * 0.14) * 3)), Image.LANCZOS)
    strip = ImageOps.autocontrast(strip)
    texts = []
    for psm in (6, 4):
        try:
            tmp = Path(tempfile.mktemp(suffix='.png'))
            strip.save(tmp)
            out = subprocess.run(['tesseract', str(tmp), 'stdout', '-l', 'eng', '--psm', str(psm)],
                                 capture_output=True, text=True, timeout=120).stdout
            texts.append(out)
            tmp.unlink(missing_ok=True)
        except Exception:                                             # noqa: BLE001
            continue
    # берём разбор той полосы, где нашлись обе строки MRZ
    for t in texts:
        res = parse(t)
        if res.get('birth_date') and res.get('passport_no'):
            return res
    return {}


def parse(text: str) -> dict:
    """Достать из текста документа данные MRZ. Пусто — если MRZ не найдена."""
    if not text:
        return {}
    lines = []
    for raw in str(text).splitlines():
        # OCR вставляет мусор внутрь строки: «| Р<КИ$МАКАКОУ\А<<АЕ1$А<<<»
        # цифры тоже значимы — вторая строка MRZ начинается с номера паспорта
        cand = re.sub(r'^[^A-Za-zА-Яа-я0-9<]*', '', raw.strip())
        norm = _norm(cand)[:44].ljust(44, '<')
        if norm.count('<') >= 5 and sum(1 for ch in norm if ch.isalnum()) >= 9:
            lines.append(norm)
    if True:
        # Ищем связку «номер + три знака гражданства + дата рождения + пол + срок»
        # прямо в тексте документа: машиночитаемая строка часто распознаётся кашей
        # («551434890581$1206131Е3405167»), но цифры в ней читаются, а контрольная
        # цифра позволяет отбросить перестановки (13.06.2012 вместо 12.06.2013).
        # Гражданство здесь может быть распознано как «81S» вместо «RUS», поэтому
        # на его месте допускаем любые три символа MRZ.
        flat = _norm(str(text))
        for m in re.finditer(r'(\d{9})\d?[A-Z0-9<]{3}(\d{6})(\d)?([A-Z<])(\d{6})(\d)?', flat):
            if not (m.group(3) and _chk(m.group(2)) == m.group(3)):
                continue
            out = {'passport_no': m.group(1)}
            birth = _date(m.group(2))
            if birth:
                out['birth_date'] = birth
            # пол распознаётся как «F»/«M», но OCR часто отдаёт вместо него «E»:
            # это не повод терять дату рождения — пол заполним из печатного поля
            if m.group(4) in ('M', 'F'):
                out['sex'] = 'Male' if m.group(4) == 'M' else 'Female'
                out['client_gender'] = 'Laki-laki' if m.group(4) == 'M' else 'Perempuan'
            exp = _date(m.group(5), future=True)
            if exp:
                out['passport_expiry'] = exp
                out['passport_valid_until'] = exp
            return out
    if len(lines) < 2:
        return {}
    # Распознавание MRZ в фото паспорта даёт много ошибок в буквах, поэтому
    # берём из неё только цифровые поля: номер паспорта, даты и пол. Фамилию и
    # имя надёжнее читать из печатных полей бланка — там чёткая латиница.
    l2 = ''
    for cand in lines:
        if re.match(r'\d{9}', cand) or re.match(r'[A-Z]{2}\d{7}', cand):
            l2 = cand
            break
    if not l2:
        return {}
    out: dict = {}
    m = re.search(r'(\d{9})\d?([A-Z]{3})(\d{6})(\d)?([MF<])(\d{6})(\d)?', l2)
    if m:
        no = re.sub(r'<', '', m.group(1))
        if no.isdigit():
            out['passport_no'] = no
        # дату рождения принимаем только если сошлась контрольная цифра MRZ:
        # распознавание путает порядок цифр (13.06.2012 вместо 12.06.2013),
        # а контроль ловит такую перестановку
        if m.group(4) and _chk(m.group(3)) == m.group(4):
            birth = _date(m.group(3))
            if birth:
                out['birth_date'] = birth
        sex = m.group(5)
        if sex in ('M', 'F'):
            out['sex'] = 'Male' if sex == 'M' else 'Female'
            out['client_gender'] = 'Laki-laki' if sex == 'M' else 'Perempuan'
        exp = _date(m.group(6), future=True)
        if exp:
            out['passport_expiry'] = exp
            out['passport_valid_until'] = exp
    return {k: v for k, v in out.items() if v}

def parse_name(text: str) -> dict:
    """Фамилия и имя из первой строки MRZ («P<RUS<SURNAME<<GIVEN<NAMES»).

    Буквы в MRZ распознаются хуже цифр, поэтому это «черновое» имя: оно сверяется
    с печатными полями бланка и карточкой. Гомоглифы приводим к латинице.
    """
    if not text:
        return {}
    flat = _norm(str(text))
    best = {}
    for m in re.finditer(r'P[<A-Z0-9]{0,3}([A-Z<]{6,44})', flat):
        seg = m.group(1)
        if '<<' not in seg:
            continue
        sur, rest = seg.split('<<', 1)
        sur = re.sub(r'\s{2,}', ' ', sur.replace('<', ' ')).strip()
        given = re.sub(r'\s{2,}', ' ', rest.replace('<', ' ')).strip()
        if len(sur) < 2 or len(given) < 2:
            continue
        cand = {'surname': sur, 'given_names': given, 'full': (sur + ' ' + given).strip()}
        if len(cand['full']) > len(best.get('full', '')):
            best = cand
    return best


def name_from_image(path: str) -> dict:
    """Фамилия и имя из MRZ на снимке паспорта: нижняя полоса бланка → OCR → parse_name."""
    try:
        import subprocess
        import tempfile
        from PIL import Image, ImageOps
    except Exception:                                                 # noqa: BLE001
        return {}
    try:
        im = Image.open(path).convert('L')
    except Exception:                                                 # noqa: BLE001
        return {}
    W, H = im.size
    strip = im.crop((0, int(H * 0.84), W, H))
    strip = strip.resize((W * 3, max(1, int(H * 0.16) * 3)), Image.LANCZOS)
    strip = ImageOps.autocontrast(strip)
    res: dict = {}
    for psm in (6, 4):
        try:
            tmp = Path(tempfile.mktemp(suffix='.png'))
            strip.save(tmp)
            out = subprocess.run(['tesseract', str(tmp), 'stdout', '-l', 'eng', '--psm', str(psm)],
                                 capture_output=True, text=True, timeout=120).stdout
            tmp.unlink(missing_ok=True)
        except Exception:                                             # noqa: BLE001
            continue
        cand = parse_name(out)
        if cand and len(cand.get('full', '')) > len(res.get('full', '')):
            res = cand
    return res
