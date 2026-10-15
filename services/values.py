"""Данные → переменные документа.

Порядок сбора значений для шаблона:
  1) документы клиента (выгрузка Google Drive) и его карточка;
  2) значения, сохранённые в самой заявке;
  3) пул из архива — только для типовых переменных (сроки, суммы, банк, компания).
     Данные конкретного человека (паспорт, ФИО, счёт, баланс) из пула не берутся.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from core import db
from core.config import DATA_DIR

GDRIVE_ROOT = Path(DATA_DIR) / "gdrive_examples"

ORIGINAL_PATTERNS = {
    "bank": ["bankstatement", "bank_statement", "bank statement", "funds_movement",
             "funds movement", "account_activity", "account activity",
             "справка", "движение средств"],
    "work": ["workagreement", "work_agreement", "work agreement", "трудовой",
             "трудовой дог", "employment agreement", "employment_agreement",
             "договор"],
    "cv": ["resume", "cv", "itk"],
    "personal": ["personal"],
}

def _original_patterns_for(template_code: str) -> list:
    code = (template_code or "").lower()
    if code.startswith("bank_statement") or "bank" in code:
        return ORIGINAL_PATTERNS["bank"]
    if "remote_work" in code or "agreement" in code:
        return ORIGINAL_PATTERNS["work"]
    if code.startswith("cv"):
        return ORIGINAL_PATTERNS["cv"]
    if "personal" in code:
        return ORIGINAL_PATTERNS["personal"]
    return []


def _find_client_folder_by_id(client_id: int):
    cl = db.q1("SELECT full_name_latin, surname, name, full_name_title FROM clients WHERE id=?",
               (client_id,))
    if not cl or not GDRIVE_ROOT.exists():
        return None
    # Скачанные с Диска папки лежат под техническими именами (client_83, CLIENT_66):
    # если папка клиента есть там, берём её — в ней лежат ITK, паспорт, фото.
    for _cand in (GDRIVE_ROOT / ("client_%s" % client_id),
                  GDRIVE_ROOT / ("client%s" % client_id),
                  GDRIVE_ROOT.parent / "gdrive_cache" / ("client_%s" % client_id)):
        if _cand.exists() and _cand.is_dir():
            return _cand

    def norm(s: str) -> str:
        return " ".join("".join(ch for ch in (s or "").lower()
                                if ch.isalnum() or ch.isspace()).split())

    def tokens(s: str) -> set:
        return set(norm(s).split())

    # Главный кандидат — полное ФИО латиницей
    full = norm(cl.get("full_name_latin"))
    full_tokens = tokens(cl.get("full_name_latin"))
    sur = norm(cl.get("surname"))
    nm = norm(cl.get("name"))

    folders = [d for d in GDRIVE_ROOT.iterdir() if d.is_dir()]

    # 1) Точное совпадение полного ФИО
    for d in folders:
        if norm(d.name) == full:
            return d

    if not full_tokens:
        return None

    # 2) Все токены ФИО клиента присутствуют в имени папки (или наоборот)
    best = None
    for d in folders:
        dt = tokens(d.name)
        if not dt:
            continue
        inter = full_tokens & dt
        # требуем чтобы ВСЕ токены клиента были в папке, либо все токены папки в клиенте
        if full_tokens <= dt or dt <= full_tokens:
            if len(inter) >= 2 or (sur and nm and sur in dt and nm in dt):
                return d
        # 3) fallback: фамилия + имя оба совпали (>=2 токена)
        if sur and nm and sur in dt and nm in dt:
            best = best or d
    return best


def _find_original_file(client_id: int, template_code: str):
    """Возвращает Path оригинального PDF клиента или None."""
    if not client_id:
        return None
    folder = _find_client_folder_by_id(client_id)
    if not folder:
        return None
    patterns = _original_patterns_for(template_code)
    if not patterns:
        return None
    pdfs = [f for f in folder.iterdir() if f.suffix.lower() == ".pdf" and f.is_file()]
    for pat in patterns:
        for f in pdfs:
            if pat in f.name.lower():
                return f
    return None


def _minus_months(d, months: int):
    """Уменьшает дату на N месяцев (день подрезается по длине месяца)."""
    import calendar
    m = d.month - months
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)


def _num2words_en(n: int) -> str:
    """Число прописью на английском (без внешних зависимостей)."""
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
            "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
            "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    if n == 0:
        return "zero"
    if n < 0:
        return "minus " + _num2words_en(-n)
    out = []
    if n >= 1_000_000_000:
        out.append(_num2words_en(n // 1_000_000_000) + " billion"); n %= 1_000_000_000
    if n >= 1_000_000:
        out.append(_num2words_en(n // 1_000_000) + " million"); n %= 1_000_000
    if n >= 1000:
        out.append(_num2words_en(n // 1000) + " thousand"); n %= 1000
    if n >= 100:
        out.append(ones[n // 100] + " hundred"); n %= 100
    if n >= 20:
        w = tens[n // 10]
        if n % 10:
            w += "-" + ones[n % 10]
        out.append(w)
    elif n > 0:
        out.append(ones[n])
    return " ".join(out)


def _date_id(datestr: str) -> str:
    """Дата в индонезийском формате: 24 Agustus 2026."""
    import datetime as _dt
    _M = ["Januari","Februari","Maret","April","Mei","Juni","Juli",
          "Agustus","September","Oktober","November","Desember"]
    d = None
    s0 = (datestr or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = _dt.datetime.strptime(s0, fmt).date(); break
        except Exception:
            continue
    if d is None:
        d = _dt.date.today()
    return f"{d.day} {_M[d.month-1]} {d.year}"


def _fio_latin(client: dict) -> str:
    """Собрать ФИО латиницей: приоритет full_name_latin (если уже 3 слова — есть отчество),
    иначе собрать из surname/name/patronymic, кириллицу транслитерируем."""
    full = (client.get("full_name_latin") or "").strip()
    parts = [client.get("surname") or "", client.get("name") or "",
             client.get("patronymic") or ""]
    # Разобраны все три части ФИО — собираем из них, в порядке «фамилия имя отчество».
    # Поле full_name_latin часто приходит из ИМЕНИ ФАЙЛА фото («CLIENT AKHMADEEV»),
    # где нет отчества и порядок обратный — доверять ему в этом случае нельзя.
    if all(p.strip() for p in parts):
        return _translit(" ".join(p.strip() for p in parts)).upper()
    if full:
        return full
    fio = " ".join(p for p in parts if p).strip()
    if not fio:
        return ""
    # транслитерация локальная: раньше тут был импорт несуществующего модуля,
    # из-за чего ФИО уходило в документ кириллицей
    return _translit(fio).upper()


# --- Автоперевод русских значений: документы всегда формируются на английском ---
_TRANSLIT_MAP = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}
_ADDR_WORDS = {
    'край': 'Krai', 'область': 'Oblast', 'обл': 'Oblast', 'район': 'Dist',
    'город': '', 'г': '', 'ул': 'ul.', 'улица': 'ul.', 'проспект': 'Ave.', 'пр': 'Ave.',
    'переулок': 'Lane', 'пер': 'Lane', 'дом': 'd.', 'д': 'd.', 'корпус': 'bldg.', 'корп': 'bldg.',
    'кв': 'apt.', 'квартира': 'apt.', 'строение': 'bldg.', 'стр': 'bldg.', 'шоссе': 'Hwy',
    'бульвар': 'Blvd', 'набережная': 'Emb.', 'проезд': 'Pass', 'этаж': 'fl.', 'офис': 'off.',
}
# города — как их пишут в англоязычных документах
_CITY_EN = {
    'москва': 'Moscow', 'санкт-петербург': 'Saint Petersburg', 'казань': 'Kazan',
    'краснодар': 'Krasnodar', 'новосибирск': 'Novosibirsk', 'екатеринбург': 'Yekaterinburg',
    'уфа': 'Ufa', 'самара': 'Samara', 'омск': 'Omsk', 'ростов-на-дону': 'Rostov-on-Don',
    'сочи': 'Sochi', 'тюмень': 'Tyumen', 'челябинск': 'Chelyabinsk', 'пермь': 'Perm',
    'волгоград': 'Volgograd', 'красноярск': 'Krasnoyarsk', 'воронеж': 'Voronezh',
    'саратов': 'Saratov', 'тольятти': 'Tolyatti', 'ижевск': 'Izhevsk', 'барнаул': 'Barnaul',
    'иркутск': 'Irkutsk', 'хабаровск': 'Khabarovsk', 'владивосток': 'Vladivostok',
}
_PERSONAL_VARS = {
    'name','surname','patronymic','full_name','client_name','full_name_latin','for_name',
    'employee_name','employer_name','contractor_full_name','company_director','sponsor_name',
    'attorney_name','passport_issued_by','id_number','place_of_birth','birth_place',
    # Персональные данные резюме и документов: НИКОГДА не берутся из общего пула
    # значений. Иначе в резюме нового клиента попадают паспорт, имя и дата рождения
    # предыдущего — именно так в резюме заявки 107 оказался паспорт клиента LEVIN.
    # Эти значения набираются только из карточки клиента этой заявки.
    'cv_name','cv_passport_no','passport_number','passport_no','cv_date_of_birth',
    'cv_place_of_birth','cv_nationality','birth_date','date_of_birth','nationality',
    # Дополнено 07.10.2026 после разбора заявки 107: под этими именами в пуле лежали
    # данные ЧУЖИХ людей — гарант Bartosz Nafalski, CLIENT_048, её email и имя файла.
    # Пул хранит значения без привязки к клиенту, поэтому любое имя человека в пуле —
    # это чужие данные для следующей заявки.
    'email','phone','phone_number','mobile','contact_phone','contact_email',
    'guarantor','guarantor_name','sponsor_person_name','sponsor_name','signatory_name',
    'name_on_visa','visa_name','last_name_ru','last_name_latin','full_name_ru',
    'employee_full_name','employee_full_name_latin','source_file_name','holder_name',
    'account_holder','passport_issued','passport_issue_date','passport_expiry',
    'passport_place','passport_date','date_iso','place_date_of_birth','address_live',
    # Номера разрешений на пребывание — у каждого клиента свои. В шаблонах лежал номер
    # образца B12E21E1087150-C и подставлялся в шесть писем любому клиенту (разбор 107).
    'itk_no','stay_permit_no','permit_no','visa_no','kitab_no','kitas_no',
    # Сроки паспорта и разрешения, место рождения и номер письма — тоже персональные.
    # В четырёх шаблонах лежали сроки паспорта и ИТК клиентки Маркаровой (23-11-2030,
    # 15-09-2026) и подставлялись в письма другим людям; номер письма у каждого свой
    # и должен вычисляться для заявки, а не браться из образца (разбор по архиву Диска).
    'passport_expiry','itk_expiry','permit_expiry','visa_expiry','letter_no',
    # Даты конкретной заявки: дата письма, сроки в письмах, периоды справок, дата договора.
    # В шаблонах стояли даты прошлых заявок (дата письма 24 Agustus 2026, срок паспорта
    # 24-01-2033) и подставлялись новым клиентам вместо их собственных (разбор 07.10.2026).
    'date','date_iso_2','date_iso_3','date_of_issue','doc_date','letter_place_date',
    'period_from','period_to','contract_date','agreement_date','term_start_date','term_end_date',
}

# Корни имён переменных, которые ВСЕГДА означают личные данные: если имя переменной
# содержит такой корень, значение из пула не берётся ни при каких условиях.
# Исключения — реквизиты, которые к человеку не относятся (компания, банк, файл).
_PERSONAL_ROOTS = ('fio', 'full_name', 'last_name', 'surname', 'passport', 'birth',
                   'guarantor', 'signatory', 'sponsor_person', 'sponsor_name', 'visa_name',
                   'name_on_visa', 'employee_', 'account_holder', 'holder_name',
                   'date_of_birth', 'place_date_of_birth', 'customer_name', 'client_full_name')
_NOT_PERSONAL = ('company_', 'bank_', 'file_name', 'product_name', 'template_name',
                 'office_name', 'org_name', 'vendor_name', 'employer_', 'signatory_position',
                 'job', 'profession', 'position', 'industry', 'purpose', 'date_iso')


def _is_personal(var_name: str) -> bool:
    """Личная ли переменная: её значение нельзя брать из общего пула.

    Пул значений не привязан к клиенту, поэтому имя, паспорт, дата рождения,
    гарант или email из пула — это данные другого человека.
    """
    n = (var_name or '').strip().lower()
    if not n:
        return False
    if n in _NOT_PERSONAL or any(n.startswith(p) for p in _NOT_PERSONAL):
        return False
    if n in _PERSONAL_VARS:
        return True
    return any(root in n for root in _PERSONAL_ROOTS)
_ADDRESS_VARS = {
    'address_live','address_reg','address_registration','employee_address','home_address',
    'registration_address','company_address','company_registered_address','client_address',
}


def _has_cyr(text) -> bool:
    return any('а' <= ch.lower() <= 'я' or ch.lower() == 'ё' for ch in str(text or ''))


def _translit(text: str, addr: bool = False) -> str:
    out = []
    for word in str(text).split():
        low = word.strip('.,').lower()
        if addr and low in _CITY_EN:
            out.append(_CITY_EN[low] + (',' if word.endswith(',') else ''))
            continue
        if addr and low in _ADDR_WORDS:
            rep = _ADDR_WORDS[low]
            if rep:
                out.append(rep + (',' if word.endswith(',') else ''))
            continue
        buf = []
        for ch in word:
            lo = ch.lower()
            if lo in _TRANSLIT_MAP:
                t = _TRANSLIT_MAP[lo]
                buf.append(t.upper() if ch.isupper() and len(t) == 1 else t)
            else:
                buf.append(ch)
        out.append(''.join(buf))
    return ' '.join(out)


def _ru_to_en(var_name: str, value):
    """Значение переменной к виду документа: транслит ФИО/адресов, перевод остального."""
    s = str(value or '')
    if not _has_cyr(s):
        return value
    if _is_personal(var_name):
        # ФИО в документах — всегда латиницей и заглавными: в паспорте это фамилия,
        # имя и отчество (иногда два или четыре слова при двойном имени) — и в
        # документе они должны выглядеть так же, как в паспорте.
        _upper = {'surname', 'name', 'patronymic', 'surname_latin', 'name_latin',
                  'patronymic_latin', 'client_name', 'full_name', 'full_name_latin',
                  'employee_name', 'employee_full_name', 'employee_full_name_latin',
                  'contractor_full_name', 'cv_name', 'for_name'}
        return _translit(s).upper() if var_name in _upper else _translit(s)
    if var_name in _ADDRESS_VARS:
        return _translit(s, addr=True)
    # прочий текст — перевод (с кэшем)
    try:
        import hashlib
        from core import db as _db
        h = hashlib.sha1(s.encode('utf-8')).hexdigest()
        row = _db.q1("SELECT ru_json FROM translation_cache WHERE template_id=? AND src_hash=?",
                     (-1, h))
        if row and row.get('ru_json'):
            try:
                import json as _json
                return _json.loads(row['ru_json'])[0]
            except Exception:
                pass
        from bot.ai_parser import _call_llm
        ru = _call_llm([{"role": "user", "content":
                         "Переведи на английский язык (деловой/визовый документ). "
                         "Верни ТОЛЬКО перевод одной строкой, без пояснений:\n" + s}],
                       timeout=45, json_mode=False) or s
        ru = ru.strip().splitlines()[0] if ru.strip() else s
        import json as _json
        _db.exec_sql("INSERT OR REPLACE INTO translation_cache(template_id,src_hash,ru_json) VALUES(?,?,?)",
                     (-1, h, _json.dumps([ru], ensure_ascii=False)))
        return ru
    except Exception:
        return s


# БИН (первые 6 цифр) зависят от банка: начало номера говорит, чья это карта.
# Сверено со справочниками BIN (bintable, binlist, fin-bin) и с реальными справками архива:
# Т-Банк (Тинькофф): Мир 220070, Mastercard 553691/521324/528041/548387/551960/518901/553420/538994,
#   Visa 437773/437783/437772.
# Сбербанк: Мир 220220, Visa 427638/427660/427602/427616/427683/427901, Mastercard 546918, Maestro 676280, 639002.
# ВНИМАНИЕ: 220050 — это Home Credit, к Т-Банку не относится.
BANK_BINS = {
    'tbank': ['220070', '553691', '521324', '528041', '548387',
              '551960', '518901', '437773', '437783', '437772'],
    'sber': ['220220', '427638', '427660', '427602', '427616',
             '427683', '427901', '546918', '676280', '639002'],
}


def bank_bins(tpl_code: str) -> list:
    """Допустимые БИН для банка этого документа — рандомизация только внутри своего банка."""
    return BANK_BINS['sber'] if 'sber' in (tpl_code or '').lower() else BANK_BINS['tbank']


CARD_BIN = {k: v[0] for k, v in BANK_BINS.items()}      # БИН по умолчанию, для совместимости

# Диапазоны остатка для банковских справок (решение Андрея):
#   3 месяца — от 190 000 ₽ (≈2 000 $) до 800 000 ₽
#   12 месяцев — от 5 200 000 ₽ (≈60 000 $) до 8 000 000 ₽
BALANCE_RANGE = {'3m': (190_000, 800_000), '12m': (5_200_000, 8_000_000)}


def balance_bounds(tpl_code: str) -> tuple:
    """Границы остатка для типа справки."""
    return BALANCE_RANGE['12m'] if '12m' in (tpl_code or '').lower() else BALANCE_RANGE['3m']


def gen_balance(tpl_code: str, seed=None):
    """Остаток, когда реальной суммы взять негде: генерируем в диапазоне типа справки.
    Сумма идёт с копейками и не округляется до круглых тысяч (требование Андрея)."""
    import random as _random
    lo, hi = balance_bounds(tpl_code)
    rnd = _random.Random(f'bal-{seed}-{tpl_code}') if seed is not None else _random.Random()
    value = rnd.randrange(lo, hi + 1)
    cents = rnd.randrange(0, 100)
    # в справках Сбера разряды пишутся без пробелов (в подлиннике 17621.29)
    _c = (tpl_code or '').lower()
    if 'sber' in _c:
        return f'{value}.{cents:02d}' if '3m' in _c else f'{value},{cents:02d}'
    return f'{value:,}'.replace(',', ' ') + f',{cents:02d}'




def _day_ordinal(day: int) -> str:
    """Число с порядковым суффиксом: 1st, 2nd, 3rd, 4th, 11th, 21st."""
    if 10 <= day % 100 <= 20:
        return "%dth" % day
    return "%d%s" % (day, {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th"))


def _fmt_date_uk(value) -> str:
    """Дата договора: «5th October 2025» — с порядковым числительным.

    Требование заказчика (05.10.2026): в договоре день идёт с суффиксом (5th, 10th),
    как уже напечатано в разделе TERM («10th August 2025»).
    """
    import datetime as _dt
    s = str(value or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%B %d, %Y"):
        try:
            d = _dt.datetime.strptime(s, fmt).date()
            return f"{_day_ordinal(d.day)} {d.strftime('%B')} {d.year}"
        except Exception:
            continue
    return s


EMAIL_DOMAIN = "alpha-prime.group"


def _client_email(client) -> str:
    """Почта клиента по правилу заказчика: фамилия + «+@alpha-prime.group».

    Требование (05.10.2026): «у всех почта — фамилия+@alpha-prime.group».
    Фамилия — латиницей, строчными; кириллица транслитерируется.
    """
    client = client or {}
    sur = str(client.get("surname") or client.get("surname_latin") or "").strip()
    if not sur:
        full = str(client.get("full_name_latin") or client.get("full_name") or "").strip()
        sur = full.split()[0] if full else ""
    if not sur:
        return ""
    sur = sur.lower()
    if any("\u0400" <= ch <= "\u04ff" for ch in sur):
        try:
            from bot.ai_parser import translit_ru
            sur = translit_ru(sur)
        except Exception:
            pass
    sur = "".join(ch for ch in sur.lower() if ch.isalnum())
    # Правило заказчика (05.10.2026): фамилия@alpha-prime.group — плюса быть не должно.
    return (sur + "@" + EMAIL_DOMAIN) if sur else ""


def _fmt_date_en(value) -> str:
    """Дата для резюме в формате «April 3, 1989» — правило шаблонов резюме."""
    s = str(value or '').strip()
    if not s:
        return ''
    from datetime import datetime as _dt
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            d = _dt.strptime(s[:10], fmt)
            return '%s %d, %d' % (d.strftime('%B'), d.day, d.year)
        except Exception:
            continue
    return s


def _fmt_money(value, template_code: str = '') -> str:
    """Сумма в стиле банковской справки: пробелы между разрядами, запятая перед копейками.
    Оригиналы различаются по форме: справка TBANK 3м — «1 770 300,00» (без пробела после
    запятой), остальные справки (TBANK 12м, Sberbank 3м/12м) — «1 235 508, 00» (с пробелом)."""
    num = parse_amount_any(value)
    if num is None:
        return str(value or '')
    s = '{:,.2f}'.format(num).replace(',', ' ').replace('.', ',')
    if 'bank_statement_3m__tbank' not in (template_code or ''):
        s = s.replace(',', ', ', 1) if ',' in s else s
    return s


def parse_amount_any(value) -> float | None:
    """Сумма из любого вида записи: «250,000.00», «250 000,00», «1 770 300,00»,
    «7 121 309, 98», «7,121,309.98», «652105.99».

    Правило: убираем пробелы (в т. ч. неразрывные). Если есть и «,» и «.», то десятичный
    разделитель — последний из них, остальные считаются разделителями разрядов.
    Если только «,» и после неё ровно две цифры — это десятичная запятая.
    """
    if value is None:
        return None
    s = str(value).strip().replace(' ', '').replace('\xa0', '').replace('₽', '').replace('RUB', '')
    if not s:
        return None
    has_dot, has_comma = '.' in s, ',' in s
    if has_dot and has_comma:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif has_comma:
        tail = s.split(',')[-1]
        s = s.replace(',', '.') if len(tail) == 2 else s.replace(',', '')
    try:
        return float(s)
    except Exception:
        return None


def _balance_words_from(num: float) -> str:
    """Пропись суммы как в настоящей справке: «(seven million … rubles ninety-eight kopeks)».
    Для целых копеек — «rubles 00 kopeks»."""
    rub, kop = int(num), int(round((num - int(num)) * 100))
    cents = _num2words_en(kop) if kop else '00'
    return "(%s rubles %s kopeks)" % (_num2words_en(rub), cents)


def read_client_bank_statement(client_id: int) -> dict:
    """Разбор настоящей банковской справки клиента: банк, счёт, остаток, период.

    Универсально: Т-Банк («Amount of available balance as 17.09.2026: 2 757 201.00 ₽»)
    и Сбер («deposit balance is ... rubles»). Всё, что прочитано, дальше идёт
    в готовую справку: банк определяет шаблон, сумма и период — содержимое.
    """
    if not client_id:
        return {}
    try:
        path = _find_original_file(client_id, 'bank_statement')
        if not path:
            return {}
        from services.doc_read import read_text
        from services.doc_parse import parse_bank_statement
        text = read_text(str(path)) or ''
        out = parse_bank_statement(text) or {}
        if not out.get('balance_rub'):
            # запасной путь: прежний формат Сбербанка
            import pymupdf
            import re as _re
            d = pymupdf.open(path)
            t2 = ' '.join(' '.join(pg.get_text() for pg in d).split())
            d.close()
            m = _re.search(r'deposit balance is ([\d\s.,]+?)\s*rubles', t2)
            if m:
                out['balance_rub'] = _re.sub(r'\s+', ' ', m.group(1)).strip().rstrip(',')
        return out
    except Exception:
        return {}


def read_client_bank_amount(client_id: int):
    """Сумма остатка из настоящей банковской справки клиента в Google Drive (или None)."""
    info = read_client_bank_statement(client_id)
    amt = info.get('balance_rub')
    return str(amt) if amt else None


def bank_amount_for(client_id, tpl_code: str):
    """Сумма остатка для банковской справки — с подгонкой под регламент.

    Решение заказчика: справку иммиграции подаём не «какая есть», а какую нужно.
    Банковскую справку система собирает сама, поэтому:

      1. если реальная справка клиента проходит по порогу продукта — берём её
         сумму (документ не выдумываем без нужды);
      2. если реальная справка НЕ проходит (или её нет) — ставим сумму, которая
         проходит регламент (порог продукта + запас), потому что пакет обязан
         пройти проверку иммиграции.

    Порог берётся из services.requirements (C1/C1-EXT — 2 000 USD), не из
    случайного числа: иначе читатель снова начнёт браковать корректный пакет.
    """
    from services import requirements as _req

    real = read_client_bank_amount(client_id)
    product = _product_of_statement(tpl_code)
    need = _req.min_balance_rub(product)
    real_num = _to_float(real)

    if need <= 0:
        return real
    # Планка «солидности»: справка на 12 месяцев несёт крупный остаток, как в настоящих
    # справках клиентов (образец TBank — 7 121 309,98). Маленькая сумма в годовой справке
    # выглядит неправдоподобно и не проходит проверку, поэтому её не печатаем.
    _solid = 7121309.98 if "12m" in str(tpl_code) else 0.0

    if real_num >= max(need, _solid):
        return real                      # реальная справка солидная — не трогаем
    if _solid:
        return "%.2f" % _solid
    # иначе ставим проходную сумму с запасом
    target = need * 1.25                 # запас, чтобы не «ровно по порогу»
    return "%s" % _round_thousand(target)


def _round_thousand(value: float) -> int:
    """Округлить вверх до тысяч — правдоподобная сумма остатка."""
    try:
        v = int(value)
    except Exception:
        return 0
    return ((v + 999) // 1000) * 1000


def _to_float(value) -> float:
    """'449 157,88' -> 449157.88 (для сравнения с порогом)."""
    if value is None:
        return 0.0
    s = str(value).replace("\xa0", " ").replace(" ", "").replace(",", ".")
    s = "".join(ch for ch in s if ch.isdigit() or ch == ".")
    try:
        return float(s or 0)
    except Exception:
        return 0.0


def _product_of_statement(tpl_code: str) -> str:
    """Продукт, ради которого собирается справка.

    По коду шаблона продукт не определить — берём продукт последней заявки
    клиента, для которого этот шаблон входит в набор.
    """
    try:
        import sqlite3

        conn = sqlite3.connect("/opt/wolf_v2/data/wolf.db", timeout=20)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT p.code FROM product_documents pd "
            "JOIN products p ON p.id = pd.product_id "
            "JOIN templates t ON t.id = pd.template_id "
            "WHERE t.code = ? ORDER BY p.id DESC LIMIT 1", (tpl_code,)).fetchone()
        conn.close()
        if row:
            return row["code"]
    except Exception:
        pass
    return ""


def read_client_card_mask(client_id):
    """Маска карты из настоящей справки клиента: БИН (6 цифр) + последние 4 цифры.

    Банк в справке раскрывает только эти части номера — полного номера в документах нет.
    """
    if not client_id:
        return None
    try:
        path = _find_original_file(client_id, 'bank_statement')
        if not path:
            return None
        import pymupdf
        import re as _re
        d = pymupdf.open(path)
        text = ' '.join(' '.join(p.get_text() for p in d).split())
        d.close()
        m = _re.search(r'card\s*No\.?\s*(\d{6})[\s*•x\-]{2,12}(\d{4})', text, _re.I)
        if m:
            return m.group(1) + '*' * 6 + m.group(2)
        return None
    except Exception:
        return None


def card_from_client_docs(client_id, tpl_code: str):
    """Маска карты из документов клиента — но только если банк совпадает с банком документа."""
    mask = read_client_card_mask(client_id)
    if mask and mask[:6] in bank_bins(tpl_code):
        return mask
    return None


def _gen_by_pattern(seed, pattern: str) -> str:
    """Строка по шаблону: l — строчная буква, U — заглавная, d — цифра."""
    import hashlib
    raw = hashlib.sha256(str(seed).encode('utf-8')).digest() * 4
    out = []
    for i, ch in enumerate(pattern):
        b = raw[i]
        if ch == 'l':
            out.append(chr(ord('a') + b % 26))
        elif ch == 'U':
            out.append(chr(ord('A') + b % 26))
        else:
            out.append(str(b % 10))
    return ''.join(out)


# правила номеров, если в документе они отличаются от общих
# d — цифра, l — строчная латинская, U — заглавная латинская
NUMBER_RULES = {
    # Сбербанк, 3 месяца: и номер справки, и исходящий номер — семь цифр + строчная буква (9922732e)
    'bank_statement_3m__sber': {'doc_no': 'd' * 7 + 'l', 'ref_no': 'd' * 7 + 'l'},
    'bank_statement_12m__sber': {'doc_no': 'd' * 7 + 'l', 'ref_no': 'd' * 7 + 'l'},
    # Т-Банк: номер справки — две строчные латинские + восемь цифр (ae32271197),
    # исходящий — буква + восемь цифр + три буквы (B19289961ADL)
    'bank_statement_3m__tbank': {'doc_no': 'l' * 2 + 'd' * 8, 'ref_no': 'U' + 'd' * 8 + 'U' * 3},
    'bank_statement_12m__tbank': {'doc_no': 'l' * 2 + 'd' * 8, 'ref_no': 'U' + 'd' * 8 + 'U' * 3},
}


def num_ok(value, *patterns) -> str | None:
    """Пропускаем номер только если он совпадает с форматом документа.

    Иначе в справку уходил чужой формат (например «9922732e» вместо «ae32271197»):
    значение из чужого документа или из другого банка отбрасывается и номер генерируется заново.
    """
    if not value:
        return None
    v = str(value).strip()
    for p in patterns:
        if not p:
            continue
        rx = p.replace('d', '[0-9]').replace('l', '[a-z]').replace('U', '[A-Z]')
        if re.fullmatch(rx, v):
            return v
    return None


def number_pattern(code: str, name: str) -> str | None:
    """Правило номера для конкретного документа (None — общее правило)."""
    return (NUMBER_RULES.get(code or '') or {}).get(name)


def gen_doc_no(client_name, doc_date, salt: str = '', pattern: str | None = None) -> str:
    """№1: две строчные латинские буквы + восемь цифр (в реальных справках — ae32271197)."""
    return _gen_by_pattern(f'doc|{client_name}|{doc_date}|{salt}', pattern or ('ll' + 'd' * 8))


def gen_ref_no(client_name, doc_date, salt: str = '', pattern: str | None = None) -> str:
    """№2: одна заглавная буква + восемь цифр + три заглавные (в реальных — B19289961ADL)."""
    return _gen_by_pattern(f'ref|{client_name}|{doc_date}|{salt}', pattern or ('U' + 'd' * 8 + 'UUU'))


def read_client_doc_numbers(client_id):
    """Значения Ref. и No из настоящей банковской справки клиента (или None)."""
    if not client_id:
        return None, None
    try:
        path = _find_original_file(client_id, 'bank_statement')
        if not path:
            return None, None
        import pymupdf
        import re as _re
        d = pymupdf.open(path)
        text = ' '.join(' '.join(p.get_text() for p in d).split())
        d.close()
        ref = _re.search(r'Ref\.\s*([A-Za-z0-9]{6,})', text)
        no = _re.search(r'\bNo\.?\s*([A-Za-z0-9]{8,})', text)
        ref = ref.group(1) if ref and _re.search(r'[A-Za-z]', ref.group(1)) and _re.search(r'\d', ref.group(1)) else None
        no = no.group(1) if no and _re.search(r'[A-Za-z]', no.group(1)) and _re.search(r'\d', no.group(1)) else None
        return ref, no
    except Exception:
        return None, None


CARD_MASK_RE = None


def mask_card(value, tpl_code: str = '', seed=None):
    """Номер карты в документ уходит ТОЛЬКО маской: 6 цифр + ****** + 4 цифры (16 знаков).

    - есть 16 (или больше 10) цифр → маскируем по формуле;
    - введено уже со звёздочками (админ написал как надо) → оставляем как есть;
    - значения нет вовсе → генерируем правдоподобный (тот же для этой заявки, чтобы
      при повторной сборке документа номер не «прыгал»).
    """
    import re as _re
    import random as _random
    v = str(value or '').strip()
    if v:
        if '*' in v:
            return _re.sub(r'[\s\-]', '', v)              # админ задал маску вручную
        d = _re.sub(r'\D', '', v)
        if len(d) >= 10:
            return f'{d[:6]}******{d[-4:]}'
        return v
    bins = bank_bins(tpl_code)
    rnd = _random.Random(str(seed) + str(tpl_code)) if seed is not None else _random.Random()
    bin_ = bins[rnd.randrange(len(bins))]
    card = bin_ + ''.join(str(rnd.randint(0, 9)) for _ in range(10))
    return f'{card[:6]}******{card[-4:]}'


_FIO_PAT = re.compile(r"(?i)(ovich|evich|ich|ovna|evna|ichna|inichna|kyzy|uly|oglu|ович|евич|ична|инична|овна|евна|кызы|улы|оглы)$")
# фамильные окончания — помогают понять, где в сплошной строке фамилия
_SUR_PAT = re.compile(r"(?i)(ova|eva|ina|aya|skaya|skiy|ov|ev|iy|ko|uk|yan|idze|shvili|ova|hina|nko)$")


def _fio_from_application(client_id) -> str:
    """Строка «ФИО: ...» из заявки клиента (там пишут «Имя Фамилия [Отчество]»)."""
    if not client_id:
        return ""
    try:
        import core.db as _db
        for row in _db.q("SELECT raw_payload FROM applications WHERE client_id=? ORDER BY id DESC LIMIT 3", (client_id,)):
            for line in (row["raw_payload"] or "").splitlines():
                m = re.match(r"\s*(?:ФИО|FIO)\s*[:\-]\s*(.+)$", line.strip(), re.I)
                if m and m.group(1).strip():
                    return m.group(1).strip()
    except Exception:
        pass
    return ""


def _fio_from_passport(client_id) -> tuple:
    """ФИО из скана паспорта клиента (Google Drive): машиночитаемая строка MRZ.

    MRZ загранпаспорта: P<RUSCLIENT<<ANNA<VLADIMIROVNA<<<<<<<<<
    Отдаёт (фамилия, имя, отчество) — пустые строки, если паспорта в кэше нет.
    """
    if not client_id:
        return ("", "", "")
    import glob as _glob
    import os as _os
    texts = []
    try:
        import core.db as _db
        for r in _db.q("SELECT text_dump FROM client_documents WHERE client_id=? AND COALESCE(text_dump,'')<>''", (client_id,)):
            texts.append(r["text_dump"])
    except Exception:
        pass
    base = _os.path.join(str(DATA_DIR), "gdrive_cache")
    taken = 0
    for folder in (_os.path.join(base, "client_%s" % client_id), _os.path.join(base, "%s" % client_id)):
        if not _os.path.isdir(folder):
            continue
        for f in _glob.glob(_os.path.join(folder, "**", "*"), recursive=True):
            # читаем только сканы паспорта — остальные файлы клиента не трогаем (это заметно ускоряет работу)
            if not f.lower().endswith(".pdf") or not re.search(r"(?i)пасп|passport|загран|pass", _os.path.basename(f)):
                continue
            if taken >= 5:
                break
            taken += 1
            try:
                import pymupdf
                doc = pymupdf.open(f)
                texts.append(" ".join(" ".join(pg.get_text() for pg in doc).split()))
                doc.close()
            except Exception:
                continue
    for t in texts:
        m = re.search(r"P[<A-Z]{0,3}([A-Z]{3})([A-Z<]{5,44})", t)
        if not m:
            continue
        body = m.group(2)
        if "<<" not in body:
            continue
        sur, rest = body.split("<<", 1)
        sur = sur.replace("<", " ").strip()
        name = rest.replace("<<<", "|").replace("<", " ").strip(" |")
        parts = [x for x in name.split("|") if x.strip()]
        if not parts:
            continue
        name = parts[0].strip()
        patronymic = parts[1].strip() if len(parts) > 1 else ""
        if sur or name:
            return (sur, name, patronymic)
    return ("", "", "")
def _split_fio_text(text: str):
    """Разбирает «Имя Фамилия [Отчество]» или «Фамилия Имя Отчество» на части.

    Отчество узнаём по окончанию (-ович/-овна/…). Если частей две — считаем, что первым
    идёт имя, вторым фамилия (так пишут в заявках).
    """
    parts = [x for x in re.split(r"\s+", (text or "").strip()) if x]
    patronymic = ""
    if len(parts) >= 3 and _FIO_PAT.search(parts[-1].replace(" ", "")):
        patronymic, parts = parts[-1], parts[:-1]
    if len(parts) >= 3:
        # «Фамилия Имя(а)» или «Имя(а) Фамилия» — фамилию ищем по окончанию
        idx = next((i for i, x in enumerate(parts) if _SUR_PAT.search(x)), None)
        if idx is None:
            surname, name = parts[0], " ".join(parts[1:])
        else:
            surname = parts[idx]
            name = " ".join(x for i, x in enumerate(parts) if i != idx)
    elif len(parts) == 2:
        # «Имя Фамилия» (как в заявках) или «Фамилия Имя» (как в паспорте) — решаем по окончанию
        if _SUR_PAT.search(parts[0]) and not _SUR_PAT.search(parts[1]):
            surname, name = parts[0], parts[1]
        else:
            name, surname = parts[0], parts[1]
    elif len(parts) == 1:
        surname, name = parts[0], ""
    else:
        surname = name = ""
    return surname, name, patronymic


def _fio_full_latin(client: dict) -> str:
    """ФИО для документов банка: ФАМИЛИЯ ИМЯ ОТЧЕСТВО (латиница, верхний регистр).

    Порядок источников: карточка клиента → заявка клиента → ФИО латиницей из карточки.
    Если отчества нет нигде — в документ идут две части; если имя или отчество двойные —
    вставляем все части, как в паспорте.
    """
    client = client or {}
    surname = (client.get("surname") or "").strip()
    name = (client.get("name") or "").strip()
    patronymic = (client.get("patronymic") or "").strip()
    if not (surname and name):
        s2, n2, p2 = _split_fio_text(_fio_from_application(client.get("id") or client.get("client_id"))
                                     or client.get("full_name_latin") or "")
        surname, name = surname or s2, name or n2
        patronymic = patronymic or p2
    if surname and not patronymic:
        # отчества нет в карточке и заявке — пробуем скан паспорта клиента
        p_sur, p_name, p_pat = _fio_from_passport(client.get("id") or client.get("client_id"))
        surname = surname or p_sur
        name = name or p_name
        patronymic = p_pat
    # в карточке поля иногда заполнены наоборот (фамилия в поле «имя» и наоборот) —
    # разбираем по фамильному окончанию, чтобы в справке всегда было «ФАМИЛИЯ ИМЯ»
    if surname and name and _SUR_PAT.search(name) and not _SUR_PAT.search(surname):
        surname, name = name, surname
    parts = [x for x in (surname, name, patronymic) if x]
    if not parts:
        return ""
    return _translit(" ".join(parts)).upper()
# Документы, где адрес по смыслу ИНДОНЕЗИЙСКИЙ: письма в иммиграцию, заявления,
# спонсорские и адвокатские адреса. Здесь генерация запрещена — только реальный
# адрес из заявки/документов, иначе поле остаётся пустым для ручного выбора.
INDONESIA_ADDRESS_VARS = ("address_in_indonesia", "signatory_address", "sponsor_address",
                          "attorney_address", "addressee_line1", "addressee_line2",
                          "addressee_line3", "company_registered_address")


def is_indonesia_document(tpl_code: str) -> bool:
    """Нужен ли этому документу индонезийский адрес (по смыслу документа)."""
    code = (tpl_code or "").lower()
    return any(w in code for w in ("bridging", "conversion", "d12_", "statement_letter",
                                   "sponsor", "immigration", "kitas", "e33g", "b211",
                                   "denpasar", "ngurahrai"))


# Кэш: client_id -> (подпись файлов папки, найденный адрес). Разбор документов
# клиента занимает секунды, а адрес запрашивается многократно при сборке.
_ADDR_DOC_CACHE = {}


def _address_from_client_docs(client_id) -> str:
    """Адрес в стране клиента из его документов: строка «Home address:».

    В прошлой банковской справке и анкете лежит адрес клиента у себя в стране —
    он и нужен банковскому документу. Индонезийские адреса отбрасываем.
    """
    try:
        import pathlib as _pl
        import re as _re
        from services.doc_read import read_text
        from services.doc_parse import is_indonesia_address
        _root = _pl.Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % client_id)
        if not _root.exists():
            return ""
        # Кэш: разбор документов клиента занимает ~12 секунд, а вызывается
        # для каждой переменной адреса. Подпись — набор (имя, размер, mtime)
        # файлов папки: изменились файлы — пересчитываем.
        try:
            sig = sorted([f.name, f.stat().st_size, int(f.stat().st_mtime)]
                         for f in _root.iterdir() if f.is_file())
        except Exception:
            sig = None
        hit = _ADDR_DOC_CACHE.get(str(client_id))
        if sig is not None and hit and hit[0] == sig:
            return hit[1]
        # Дисковый кэш: переживает перезапуск сервиса и общий для процессов.
        try:
            from services.value_cache import get as _vc_get
            _disk = _vc_get("addr_docs", client_id, sig)
        except Exception:
            _disk = ""
        if _disk:
            _ADDR_DOC_CACHE[str(client_id)] = (sig, _disk)
            return _disk
        result = ""
        for f in sorted(_root.iterdir()):
            if not f.is_file():
                continue
            try:
                t = read_text(str(f)) or ""
            except Exception:
                continue
            m = _re.search(r"Home address[:\s]*([^\n]{5,120})", t, _re.I)
            if m:
                cand = m.group(1).strip(" .;")
                if not is_indonesia_address(cand):
                    result = cand
                    break
        if sig is not None:
            _ADDR_DOC_CACHE[str(client_id)] = (sig, result)
            try:
                from services.value_cache import put as _vc_put
                _vc_put("addr_docs", client_id, sig, result)
            except Exception:
                pass
        return result
    except Exception:
        pass
    return ""


def _client_photo_path(client_id) -> str:
    """Путь к файлу-фотографии клиента в локальной копии папки Google Drive.

    Фотография — тоже значение переменной: на формах, где требуется фото клиента,
    она подставляется в документ.
    """
    try:
        import pathlib as _pl
        _root = _pl.Path("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % client_id)
        if not _root.exists():
            return ""
        from scripts.drive_scan import doc_kind_name
        for f in sorted(_root.iterdir()):
            if f.is_file() and doc_kind_name(str(f), "") in ("photo", "foto", "image"):
                if f.suffix.lower() in (".heic", ".heif"):
                    # браузер и печать HEIC не понимают — держим рядом PNG-копию
                    png = f.with_suffix(".photo.png")
                    if not png.exists():
                        try:
                            from services.doc_read import _heic_to_png  # noqa
                            _heic_to_png(str(f), str(png))
                        except Exception:
                            try:
                                import pillow_heif  # noqa
                                from PIL import Image
                                pillow_heif.register_heif_opener()
                                Image.open(str(f)).convert("RGB").save(str(png))
                            except Exception:
                                return str(f)
                    # Копия из HEIC выходит тяжёлой (снимок с телефона 5 МБ):
                    # сразу облегчаем её — в документ идёт небольшое фото.
                    try:
                        from services import previews as _pv
                        _done = _pv.compact_image(png, long_side=_pv.COMPACT_PHOTO_LONG)
                        if _done:
                            png = _done[0]
                        _pv.ensure_image(png, _pv.THUMB_W)
                        _pv.ensure_image(png, _pv.FULL_SCALE)
                    except Exception:
                        pass
                    return str(png)
                # Фото приводим к пропорции слота в документе (5:7) и облегчаем:
                # снимок с телефона слишком высокий, лицо в слоте «поехало» бы.
                try:
                    from services import photo as _ph
                    _ready = _ph.prepare_photo(str(f), client_id=client_id)
                    if _ready:
                        return str(_ready)
                except Exception:
                    pass
                return str(f)
    except Exception:
        pass
    return ""


def read_client_company_requisites(client_id) -> dict:
    """Реквизиты компании-работодателя из документов клиента (договор, выписка ЕГРЮЛ).

    Приоритет как у банковских справок: реальный документ клиента сильнее карточки.
    Если в документах реквизитов нет — берём из карточки, а если и там пусто, поле
    остаётся пустым: выдумывать ИНН/ОГРН нельзя.
    """
    out = {}
    if not client_id:
        return out
    try:
        from pathlib import Path as _P
        folder = _P('/opt/wolf_v2/data/gdrive_cache') / ('client_%s' % client_id)
        if not folder.is_dir():
            return out
        rx_inn = re.compile(r'(?:ИНН|INN)\D{0,8}(\d{10})')
        rx_kpp = re.compile(r'(?:КПП|KPP)\D{0,8}(\d{9})')
        rx_ogrn = re.compile(r'(?:ОГРН|OGRN)\D{0,8}(\d{13})')
        rx_addr = re.compile(r'(?:Юридический адрес|Registered address|Address)[:\s]{1,4}([^\n]{15,120})',
                             flags=re.IGNORECASE)
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.suffix.lower() not in ('.pdf', '.doc', '.docx', '.txt'):
                continue
            name = f.name.lower()
            if not any(k in name for k in ('agreement', 'contract', 'egrn', 'выписк', 'договор',
                                           'requisit', 'company', 'inn')):
                continue
            try:
                from services.doc_read import read_text
                text = read_text(str(f)) or ''
            except Exception:
                continue
            if len(text) < 100:
                continue
            if 'inn' not in out:
                m = rx_inn.search(text)
                if m:
                    out['inn'] = m.group(1)
                    out['file'] = f.name
            if 'kpp' not in out:
                m = rx_kpp.search(text)
                if m:
                    out['kpp'] = m.group(1)
            if 'ogrn' not in out:
                m = rx_ogrn.search(text)
                if m:
                    out['ogrn'] = m.group(1)
            if 'address' not in out:
                m = rx_addr.search(text)
                if m:
                    out['address'] = ' '.join(m.group(1).split())
            if len(out) >= 4:
                break
    except Exception:
        return out
    return out


def is_contract_template(tpl_code: str) -> bool:
    """Документ — договор/соглашение о работе или услугах?"""
    c = (tpl_code or "").lower()
    return ("remote_work_agreement" in c) or ("agreement" in c) or ("contract" in c)


# Переменные, значения которых — постоянные данные агентства/офиса подачи, а не данные клиента.
# Их можно брать из карты переменных (таблица template_variables), даже если тип источника «client».
_TV_CONST_VARS = {
    'attorney_name', 'attorney_citizenship', 'attorney_occupation', 'attorney_nik', 'attorney_address',
    'sponsor_company', 'sponsor_name', 'sponsor_contact', 'sponsor_address', 'sponsor_person_name',
    'sponsor_position', 'sponsor_nationality', 'sponsor_birth_place_date', 'sponsor_company_details',
    'signatory_position', 'signatory_citizenship', 'signatory_address',
    'signatory_nik_or_dash', 'sponsor_name', 'sponsor_person_name', 'sponsor_address',
    'addressee_line1', 'addressee_line2', 'addressee_line3', 'addressee_office',
    'letter_subject',
    'addressee_line1', 'addressee_line2', 'addressee_line3', 'addressee_office',
    'letter_subject', 'purpose_of_application', 'stay_permit_to_be_applied_for', 'guarantor',
    'the_company_confirms_that', 'place', 'doc_place',
}

# Поля 1,2,3 и 9..13 списка переменных офисного письма: постоянные данные агентства и
# доверенного лица (компания-спонсор и её контакты + ФИО/должность/гражданство/NIK/адрес
# получателя доверенности). Их значения берутся из карты переменных шаблона с приоритетом —
# решение заказчика 05.10.2026: подставлять из списка переменных, а не из настроек.
_MAP_WINS = {
    'sponsor_company', 'sponsor_address', 'sponsor_contact',
    'attorney_name', 'attorney_occupation', 'attorney_citizenship',
    'attorney_nik', 'attorney_address',
}

# Вместе с адресатом эти поля — постоянные реквизиты офиса и агентства: их значения
# берутся ТОЛЬКО из карты переменных шаблона. Из истории значений их не подставляем,
# иначе в письмо одного офиса уезжает адрес другого (был случай: в письмо Denpasar
# попадал адрес Ngurah Rai «Taman Jimbaran»).
OFFICE_FIXED = _MAP_WINS | {'addressee_line1', 'addressee_line2', 'addressee_line3',
                            'addressee_office', 'letter_no'}

# Переменные, которые система ВЫЧИСЛЯЕТ при сборке документа: назначение обращения — из типа
# продукта заявки, срок разрешения — из документа ITK клиента, реквизиты письма — из офиса
# заявки. Их НЕЛЬЗЯ перекрывать ни пулом истории значений, ни «одобренными» значениями:
# иначе в документ уезжает чужая запись (было: purpose из карты шаблона, а срок разрешения
# печатался голой датой «11/10/2026» вместо «VISIT STAY PERMIT (ITK), VALID UNTIL 11-10-2026»).
CALC_VARS = {
    'letter_no', 'letter_subject', 'purpose_of_application', 'existing_stay_permit',
    'stay_permit_to_be_applied_for', 'address_in_indonesia', 'application_no',
    'stay_permit_no', 'place', 'doc_date', 'place_date', 'doc_place',
    # резюме собирается системой (cv_gen): профессия, профиль и обязанности считаются
    # по заявке и документам клиента, «одобренные» значения из памяти их не перекрывают
    'cv_profession', 'cv_position_ru', 'cv_profession_note', 'cv_summary',
    'cv_skills_hard', 'cv_skills_soft',
    'cv_job1_title', 'cv_job1_company', 'cv_job1_period', 'cv_job1_bullets',
    'cv_job2_title', 'cv_job2_company', 'cv_job2_period', 'cv_job2_bullets',
    'cv_job3_title', 'cv_job3_company', 'cv_job3_period', 'cv_job3_bullets',
}

# Тема письма = название продукта заявки (решение заказчика 05.10.2026).
# В письме — индонезийская формулировка, привязанная к коду продукта; если кода нет
# в таблице, тема собирается как «Permohonan <название продукта из заявки>».
PRODUCT_SUBJECTS = {
    'BRIDGING':  'Permohonan Bridging Visa 60 Hari',
    'CONV':      'Permohonan Konversi (Alih Status) menjadi KITAS',
    'E33G-NEW':  'Permohonan KITAS E33G (Remote Worker)',
    'E33G-EXT':  'Permohonan Perpanjangan KITAS E33G',
    'D12':       'Permohonan Visa D12 (Pra-Investasi)',
    'C1':        'Permohonan Visa C1 (B211A)',
    'C1-EXT':    'Permohonan Perpanjangan Visa C1',
}

# Назначение обращения (Purpose of Application, №14 в форме E-02) — по ТИПУ ПРОДУКТА заявки.
# Правило заказчика 05.10.2026: значение берётся из продукта заявки, а не из карты переменных.
PRODUCT_PURPOSES = {
    'BRIDGING':  'VISA BRIDGING TO E33G',
    'CONV':      'VISA CONVERSION (ALIH STATUS) TO KITAS E33G',
    'E33G-NEW':  'VISA E33G (REMOTE WORKER)',
    'E33G-EXT':  'EXTENSION OF STAY PERMIT E33G',
    'D12':       'VISA D12 (PRE-INVESTMENT)',
    'C1':        'VISA C1 (B211A)',
    'C1-EXT':    'EXTENSION OF VISIT STAY PERMIT C1',
}
_TV_CACHE = {}


def template_variable_map(tpl_code: str) -> dict:
    """Карта переменных шаблона из базы: тип источника, значение по умолчанию, примеры.

    Единый источник истины по переменным — таблица template_variables (правило, значение,
    примеры из подлинников). Раньше генератор её не читал, из-за чего поля, для которых
    всё уже описано, оставались пустыми.
    """
    if tpl_code in _TV_CACHE:
        return _TV_CACHE[tpl_code]
    out = {}
    try:
        rows = db.q("""SELECT tv.name, tv.source_kind, tv.default_value, tv.examples_json
                       FROM template_variables tv JOIN templates t ON t.id=tv.template_id
                       WHERE t.code=?""", (tpl_code,))
        for r in rows:
            out[r['name']] = {'kind': (r['source_kind'] or '').strip(),
                              'default': (r['default_value'] or '').strip()}
    except Exception:
        out = {}
    _TV_CACHE[tpl_code] = out
    return out


def _services_items_html(pos: str, limit: int = 5) -> str:
    """Перечень услуг/обязанностей договора по должности — пунктами, как в образцах.

    Профиль должности (data/cv_positions.json) отдаёт код через cv_gen, а сам текст
    обязанностей лежит в записи профиля — cv_gen.position_by_code(code)['blocks'].
    Раньше код запрашивали у cv_gen.resolve_profession, а блоки брали ИЗ ЕГО ОТВЕТА,
    где ключа 'blocks' нет вовсе: перечень оставался пустым, и контроль качества
    блокировал отправку договоров (задачи #12, #13, 14.10.2026 — заявки 107-109).
    """
    text = re.sub(r"\s+", " ", str(pos or "")).strip()
    if not text or len(text) > 90 or text.lower() in ("none", "null", "-"):
        return ""
    try:
        from html import escape as _esc
        from services import cv_gen as _cvg
        code = ((_cvg.resolve_profession({"position": text, "profession": text}) or {}).get("code")
                or _cvg.detect_position(text) or "")
        rec = _cvg.position_by_code(code) if code else None
        blocks = (rec or {}).get("blocks") or {}
        items = []
        for lvl in ("short", "medium", "long"):
            raw = str(blocks.get(lvl) or "").strip()
            if raw:
                for x in _cvg.split_bullets(raw):
                    x = str(x).strip().lstrip("\u2022\u25cf\u25aa\u25e6 ").strip()
                    if len(x) > 12 and x not in items:
                        items.append(x)
        if items:
            return "<br>".join("\u25cf %s" % _esc(i) for i in items[:limit])
    except Exception:                                                 # noqa: BLE001
        pass
    return ""


# Типовой перечень услуг/обязанностей договора. Нужен как последний рубеж: если ни
# должность, ни отрасль компании не дали пунктов, договор печатал «services:» без
# единого пункта — контроль качества блокировал отправку (задачи #12, #13).
# Формулировки нейтральные, персональных данных не содержат.
_SERVICES_DEFAULT = (
    "Providing professional services for the Company's ongoing projects;",
    "Planning and organising the Contractor's own working process;",
    "Reporting to the Company on the results of the services provided.",
)


def services_list_for(client: dict, tpl_code: str, position: str = "") -> str:
    """Перечень услуг договора: сохранённая правка админа → генерация по должности → типовые пункты.

    Раньше этот блок формировался только в боте, поэтому при генерации договора
    из админки поле оставалось пустым. Результат кэшируется: генерация — вызов модели.

    `position` — должность, уже подобранная для документа (карточка → заявка →
    документы клиента → пул должностей, см. _client_position). Передавать её надо
    обязательно: без неё перечень собирался только по client['position'], а у клиента
    это поле пустое — в договоре оставалась метка «services:» без пунктов (заявки 108, 109).
    """
    if not is_contract_template(tpl_code):
        return ""
    pos = str(position or (client or {}).get("position") or "").strip()
    pos = re.sub(r'\s+', ' ', pos)
    company = str((client or {}).get("company_name") or "")
    if len(pos) > 90 or pos.lower() in ("none", "null", "-"):
        pos = ""          # мусор в поле «должность» — перечень по нему не собираем
    if pos:
        sig = re.sub(r'\W+', '', pos.lower())[:40] + "|" + company[:30]
        try:
            from services.value_cache import get as _vc_get, put as _vc_put
            cached = _vc_get("services_list", (client or {}).get("id"), sig)
            if cached:
                return cached
            from bot.ai_parser import generate_duties, duties_to_html
            duties = generate_duties(pos, company)
            html = duties_to_html(duties) if duties else ""
            if html:
                _vc_put("services_list", (client or {}).get("id"), sig, html)
                return html
        except Exception:                                             # noqa: BLE001
            pass
        # Модель недоступна или отдала пусто: берём готовые обязанности из профиля
        # должности (data/cv_positions.json) — тот же источник, что у резюме.
        html = _services_items_html(pos)
        if html:
            return html
    # Должности нет вовсе: типовые услуги по отрасли компании, затем нейтральный перечень.
    try:
        from services import derived_vars as _dv
        html = _dv._services_by_sector(str((client or {}).get("sector") or ""))
        if html:
            return html
    except Exception:                                                 # noqa: BLE001
        pass
    return "<br>".join("\u25cf %s" % t for t in _SERVICES_DEFAULT)



def _build_template_values_impl(client: dict, tpl_code: str, doc_values: dict = None,
                          app_id=None) -> dict:
    """Собирает значения переменных: клиент → история значений → ранее введённое."""
    client = client or {}
    vals = {}
    # Даты договора считаем один раз на сборку: разделы 2 TERM и 7 COMPANY DECLARATION
    # обязаны печатать одну и ту же дату начала, иначе в документе расхождение.
    _CONTRACT_DATES = _contract_dates(doc_values, client)
    # реальные Ref./No из банковской справки клиента на Google Drive (если она есть)
    _real_ref, _real_no = read_client_doc_numbers(client.get("id"))
    # основа генерации №1 и №2: дата формирования документа + имя и фамилия клиента
    from datetime import datetime as _dt
    _doc_key = _dt.now().strftime("%d.%m.%Y")
    _salt_key = tpl_code or ""       # разные документы одного клиента — разные номера
    simple = {
        "full_name": _fio_full_latin(client),
        "surname": client.get("surname"), "name": client.get("name"),
        "patronymic": client.get("patronymic"),
        "full_name_latin": _fio_full_latin(client),
        "full_name_title": client.get("full_name_title"),
        "client_name": _fio_full_latin(client),
        "cv_name": _fio_full_latin(client),
        "employee_name": _fio_full_latin(client),
        "for_name": _fio_latin(client),
        "birth_date": client.get("birth_date"),
        "date_of_birth": client.get("birth_date"),
        "place_of_birth": client.get("birth_place"),
        # фотография клиента с Google Drive — подставляется на формах, где нужна фотография
        "client_photo": _client_photo_path(client.get("id")),
        "client_photo_url": _client_photo_path(client.get("id")),
        "birth_place": client.get("birth_place"),
        "gender": client.get("gender"), "citizenship": client.get("citizenship"),
        "nationality": client.get("nationality") or client.get("citizenship"),
        "passport_series": client.get("passport_series"),
        "passport_number": client.get("passport_number"),
        "passport_no": client.get("passport_number"),
        "passport_issued_by": client.get("passport_issued_by"),
        "passport_issue_date": client.get("passport_issue_date"),
        "passport_expiry": client.get("passport_expiry"),
        "inn": client.get("inn"), "snils": client.get("snils"),
        "intl_passport": client.get("intl_passport"),
        # Телефон в формах (E-02) по стандарту — «00» (правило заказчика 06.10.2026).
        # Настоящий телефон клиента не подставляется сам: его выбирают в панели переменных.
        "phone": "00", "email": _client_email(client),
        "address_reg": client.get("address_reg"), "address_live": client.get("address_live"),
        "address_zip": client.get("address_zip"), "city": client.get("city"),
        "country": client.get("country"), "position": client.get("position"),
        "profession": client.get("position"),
        "salary_amount": client.get("salary_amount"), "salary": client.get("salary_amount"),
        "salary_amount_raw": client.get("salary_amount"),
        "company_name": client.get("company_name"), "company_llc": client.get("company_llc"),
        "company_name_in_quotes": client.get("company_name"),
        "company_full_name": client.get("company_name"),
        "company_address": client.get("company_address"),
        "company_inn": client.get("company_inn"), "company_kpp": client.get("company_kpp"),
        "company_ogrn": client.get("company_ogrn"),
        "company_director": client.get("company_director"),
        "bank_name": client.get("bank_name"),
        # --- банковские реквизиты (только из карточки клиента, никогда из общей истории) ---
        "account_no": client.get("account_no"),
        "contract_no": client.get("contract_no"),
        # номер карты в документ идёт только маской: 6 цифр + ****** + 4 цифры
        # номер карты: из карточки → из документов клиента (если банк тот же) → генерация по банку
        "card_mask": mask_card(client.get("card_mask") or card_from_client_docs(client.get("id"), tpl_code)
                               or (doc_values or {}).get("card_mask"), tpl_code,
                               seed=client.get("id") or client.get("client_id")),
        # остаток: из карточки → из реальной справки клиента в Google Drive → генерируем в диапазоне
        # Остаток: приоритет — реальная сумма из справки клиента (Google Drive),
        # потому что она настоящая; карточка и генерация — только если справки нет.
        "balance_rub": _fmt_money(bank_amount_for(client.get("id"), tpl_code)
                                  or client.get("balance_rub")
                                  or gen_balance(tpl_code, seed=client.get("id"))),
        # период справки: если у клиента есть его настоящая справка — берём её период
        "period_from": (read_client_bank_statement(client.get("id")).get("period_from")
                        or client.get("period_from")),
        "period_to": (read_client_bank_statement(client.get("id")).get("period_to")
                      or client.get("period_to")),
        "balance_date": (read_client_bank_statement(client.get("id")).get("balance_date")
                         or client.get("balance_date")),
        # №1 и №2: из данных клиента → из его реальной справки на Google Drive → генерация
        # по правилу (дата формирования + имя и фамилия), чтобы значения были уникальны
        # Порядок: данные клиента → реальный номер из его документов → номер,
        # уже сохранённый в этом документе → генерация (один раз, затем фиксируется).
        "ref_no": (num_ok(client.get("ref_no")) or num_ok(_real_ref, number_pattern(tpl_code, "ref_no"), 'U' + 'd' * 8 + 'U' * 3)
                   or num_ok((doc_values or {}).get("ref_no"), number_pattern(tpl_code, "ref_no"), 'U' + 'd' * 8 + 'U' * 3)
                   or gen_ref_no(_fio_latin(client), _doc_key, _salt_key, pattern=number_pattern(tpl_code, "ref_no"))),
        "doc_no": (num_ok(client.get("doc_no")) or num_ok(_real_no, number_pattern(tpl_code, "doc_no"), 'l' * 2 + 'd' * 8)
                   or num_ok((doc_values or {}).get("doc_no"), number_pattern(tpl_code, "doc_no"), 'l' * 2 + 'd' * 8)
                   or gen_doc_no(_fio_latin(client), _doc_key, _salt_key, pattern=number_pattern(tpl_code, "doc_no"))),
        "stay_permit_no": client.get("stay_permit_no"),
        "place": client.get("place"),
        "employer_name": client.get("company_director") or "",
        "employee_name": _fio_full_latin(client),
        "employee_full_name": _fio_full_latin(client),
        "employee_full_name_latin": _fio_full_latin(client),
        "employee_address": (_translit(client.get("address_live") or client.get("address_reg") or "", addr=True)
                             if (client.get("address_live") or client.get("address_reg")) else ""),
        "employee_birth_date": client.get("birth_date") or "",
        "employee_birth_place": client.get("birth_place") or "",
        "employee_passport": client.get("passport_number") or "",
    }
    for k, v in simple.items():
        if v:
            vals[k] = str(v)

    # --- Организация для договора (Remote Work Agreement, док. №11) ---
    # Реквизиты работодателя берём из пула архивных организаций, а не из общей
    # истории значений: чужие реквизиты в документе недопустимы. Название в шапке
    # и адрес/ИНН/КПП/ОГРН в подвале — ОДНА и та же запись пула, поэтому верх и низ
    # документа всегда логически связаны. Заявка закрепляет организацию за собой:
    # выбор детерминирован, при повторной сборке она не меняется.
    # Организация заявки: если документ уже хранит выбранную организацию из пула,
    # она закреплена — реквизиты берём только из её записи (см. ниже).
    try:
        from services import employer_pool as _emp_pin
        _pinned = bool(_emp_pin.by_title(str((doc_values or {}).get("company_name_in_quotes") or "").strip()))
    except Exception:
        _pinned = False
    if is_contract_template(tpl_code):
        try:
            from services import employer_pool as _emp
            # Если организация уже выбрана для этой заявки (сохранённые значения
            # документа), автовыбор по городу не применяем: иначе он подставит
            # реквизиты другой компании — чужие ИНН/КПП/ОГРН в договоре.
            _dv_title = str((doc_values or {}).get("company_name_in_quotes") or "").strip()
            if not _pinned and not (client.get("company_name") or client.get("company_inn")):
                # Город клиента задаёт приоритет выбора: клиент из Москвы — и
                # организация московская. Адрес проживания в Индонезии (Бали,
                # Джакарта) ориентиром быть не может — там нет организаций для
                # договора, поэтому он пропускается, и берётся следующий источник
                # (регистрация, место рождения). Совпадений нет — любая из списка.
                _cands = [client.get("city"), client.get("address_reg"),
                          client.get("address_live"), client.get("birth_place")]
                for _k, _v in (_emp.values_for(app_id=app_id, client_id=client.get("id"),
                                               cities=[c for c in _cands if c]) or {}).items():
                    if _v:
                        vals.setdefault(_k, _v)
        except Exception:
            pass

    # --- Свободный комментарий заявки: должность и сфера деятельности ---------
    # Менеджер вписывает в карточку заявки «Должность: артист-продюсер». Это значение
    # главнее автоподбора: должность идёт и в резюме, и в договор, а по сфере
    # подбирается организация (кинопродакшн вместо компании из общего списка).
    try:
        from services import brief_values as _bv
        _brief = str((doc_values or {}).get("brief") or "").strip() or _bv.read_brief(app_id)
        if _brief:
            _pos_ru, _pos_en = _bv.parse_position(_brief)
            _pos = _pos_en or _pos_ru
            if _pos:
                for _k in ("position_title", "position", "cv_position", "profession"):
                    vals[_k] = _pos
                # Перечень услуг в договоре — по той же профессии, что и должность:
                # раньше он оставался от старой (административной) профессии и
                # расходился с резюме.
                try:
                    _sl_html = _services_items_html(_pos)
                    if _sl_html:
                        vals["services_list"] = _sl_html
                except Exception:
                    pass
            if is_contract_template(tpl_code):
                # Комментарий заявки главнее: менеджер прямо указал сферу, по ней и
                # подбираем организацию, даже если в документе осела другая компания.
                _rec = _bv.pick_employer_by_sphere(_brief)
                for _k, _v in (_bv.employer_variables(_rec) or {}).items():
                    if _v:
                        vals[_k] = _v
    except Exception:
        pass

    # --- Период для банковских справок: period_to = balance_date, period_from = -N мес ---
    # ВАЖНО: считается ПОСЛЕ загрузки истории ниже.

    # --- Договор (Work Agreement): суммы, срок, реквизиты компании, должность ---
    # Сумма в карточке встречается в свободной записи («545000 RUB/мес», «5 100 000»,
    # «5100000.00») — вытаскиваем число и приводим к формату договора: «RUB 6,540,000».
    try:
        amt_raw = str(vals.get("salary_amount_raw") or vals.get("salary_amount") or "").strip()
        per_month = bool(re.search(r"мес|month|/m\b", amt_raw, flags=re.IGNORECASE))
        n = None
        if amt_raw:
            digits = re.sub(r"[^0-9.,]", "", amt_raw.replace(" ", "").replace("\xa0", ""))
            if digits:
                digits = digits.replace(",", ".")
                try:
                    n = int(round(float(digits)))
                except Exception:
                    n = None
        if n and per_month:
            n, n2 = n * 12, n          # в карточке была сумма за месяц
        elif n:
            n2 = int(round(n / 12))
        if n:
            words = _num2words_en(n)
            # в тексте договора слово RUB уже стоит перед числом — значение только цифрами;
            # прописью — с заглавных букв, как в поданных договорах (цифры и слова из одного числа)
            fmt = lambda x: f"{x:,}"
            vals.setdefault("amount_in_words", words)
            vals.setdefault("amount_per_year", fmt(n))
            vals.setdefault("amount_per_month", fmt(n2))
            vals.setdefault("amount_per_month_in_words", _num2words_en(n2).title())
            vals.setdefault("annual_amount_numeric", fmt(n))
            vals.setdefault("annual_amount_words", words.title())
            vals.setdefault("monthly_amount_numeric", fmt(n2))
            vals.setdefault("monthly_amount_words", _num2words_en(n2).title())
    except Exception:
        pass

    # Сумма договора: границы как в архивных договорах (ниже/выше архива не бывает),
    # округление до 1 000 ₽ (копейки не пишем), месяц всегда = год / 12. Если сумма не
    # задана или выпадает из этих правил — берём сумму из пула/генерируем в границах.
    # Прописью всегда пересчитывается из тех же цифр, поэтому разойтись не могут.
    if is_contract_template(tpl_code):
        try:
            from services import salary_pool as _sal
            def _digits(_v):
                _s = re.sub(r"[^\d]", "", str(_v or ""))
                return int(_s) if _s else None
            _an = _digits(vals.get("annual_amount_numeric"))
            _mn = _digits(vals.get("monthly_amount_numeric"))
            _good = bool(_an and _sal.in_range(_an) and _an % 1000 == 0
                         and (_mn is None or _mn * 12 == _an))
            if not _good:
                _new = _sal.values_for(app_id=app_id, client_id=client.get("id")) or {}
                for _k, _v in _new.items():
                    if _v:
                        vals[_k] = _v
                _an = _digits(_new.get("annual_amount_numeric"))
                _mn = _digits(_new.get("monthly_amount_numeric"))
            if _an:
                vals["annual_amount_numeric"] = f"{_an:,}"
                vals["amount_per_year"] = f"{_an:,}"
                vals["annual_amount_words"] = _sal.words_en(_an)
            if _mn:
                vals["monthly_amount_numeric"] = f"{_mn:,}"
                vals["amount_per_month"] = f"{_mn:,}"
                vals["monthly_amount_words"] = _sal.words_en(_mn)
        except Exception:
            pass
    try:
        inn, kpp, ogrn = vals.get("company_inn"), vals.get("company_kpp"), vals.get("company_ogrn")
        parts = [p for p in (f"INN: {inn}" if inn else "",
                             f"KPP: {kpp}" if kpp else "",
                             f"OGRN: {ogrn}" if ogrn else "") if p]
        if parts:
            vals.setdefault("inn_kpp_ogrn", ", ".join(parts))
        for src, dst in (("company_address", "company_registered_address"),
                         (("company_name", "employer_name")[0], "employer_name"),
                         ("position", "position_title"),
                         ("profession", "position_title")):
            if vals.get(src):
                vals.setdefault(dst, vals[src])
        if vals.get("full_name_latin") or vals.get("client_name"):
            vals.setdefault("contractor_full_name", vals.get("full_name_latin") or vals.get("client_name"))
    except Exception:
        pass
    # Номер договора: в карточке его часто нет — тогда номер создаётся один раз и
    # фиксируется в документе (как номер банковской справки), чтобы не менялся.
    try:
        if is_contract_template(tpl_code) and not vals.get("contract_no"):
            import random as _rnd
            vals["contract_no"] = str(_rnd.randint(5010000000, 5999999999))
    except Exception:
        pass
    # Баланс прописью считается в конце функции: здесь сумма ещё не окончательная
    # (карточка клиента и сохранённые значения документа переопределяют её ниже).

    # значения из истории (наиболее частые)
    # ВАЖНО: персональные данные (номера счетов, балансы, паспорта) НЕЛЬЗЯ брать из общей
    # истории — там значения ДРУГИХ клиентов. Такие поля берутся только из карточки
    # клиента или вводятся админом вручную.
    # Какие переменные — «данные этого клиента» (из общего пула их брать нельзя),
    # а какие типовые (сроки, суммы, банк, компания — можно взять из пула и поправить).
    # Разделение хранится в таблице variable_scope, наполняется скриптом классификации.
    # Поля договора — тоже персональные: реквизиты компании, номер и сроки договора
    # у каждого клиента свои. Из общего пула истории они не берутся, иначе данные
    # одного клиента перетекают в документы другого.
    PERSONAL_VARS = {
        "balance_value", "balance_rub", "account_no", "contract_no", "card_mask",
        "doc_no", "stay_permit_no", "passport_number", "passport_no", "passport_series",
        "inn", "snils", "phone", "email", "ref_no", "itk_no", "itk_expiry",
        "company_inn", "company_kpp", "company_ogrn", "company_registered_address",
        "employer_name", "company_name_in_quotes", "agreement_date", "term_start_date",
        "term_end_date", "monthly_amount_numeric", "monthly_amount_words",
        "annual_amount_numeric", "annual_amount_words", "passport_issued_by",
        "passport_issue_date", "passport_expiry", "employee_address", "place_of_birth",
        "date_of_birth", "the_company_confirms_that", "services_list", "position_title",
    }
    # Переменные организации для договора: название в шапке и в тексте, название и
    # ИНН/КПП/ОГРН в подвале. Источник — пул организаций (или выбор/ввод админа),
    # но НЕ история значений и не обрывки из ранее сохранённых значений.
    ORG_VARS = {
        "company_name_in_quotes", "employer_name", "company_registered_address",
        "company_inn", "company_kpp", "company_ogrn",
    }
    # Резюме: опыт, образование, навыки и краткое описание берутся только из данных
    # этого клиента или из значений, введённых по конкретному документу, а НЕ из общей
    # истории значений: иначе в резюме попадали чужие данные из образца (05.10.2026).
    CV_NARRATIVE_VARS = {
        "cv_summary", "cv_job1_company", "cv_job1_title", "cv_job1_bullets",
        "cv_job2_company", "cv_job2_title", "cv_job2_bullets", "cv_education_school",
        "cv_education_degree", "cv_education_years", "cv_education_note", "cv_skills_hard",
        "cv_skills_soft", "cv_skills_tools", "cv_languages",
    }
    try:
        for r in db.q("SELECT name FROM variable_scope WHERE scope='individual'"):
            PERSONAL_VARS.add(r["name"])
    except Exception:
        pass
    try:
        # Берём по одному самому частому значению на КАЖДУЮ переменную — так пул
        # из архива реальных документов используется целиком, а не только его «топ».
        # (MAX без коррелированного подзапроса: со старым вариантом страница собиралась ~2.2 сек)
        # Переменные организации (название, адрес, ИНН, КПП, ОГРН) приходят из пула
        # организаций, а не из истории значений: в истории встречались обрывки
        # («LLC », ««ТБАНК»»), из-за которых в шапке и подвале стоял мусор.
        for r in db.q("""SELECT variable_name, value, MAX(used_count) AS used_count
                         FROM variable_value_history GROUP BY variable_name"""):
            name = r["variable_name"]
            v = r["value"] or ""
            if name in CV_NARRATIVE_VARS:
                continue
            if name in PERSONAL_VARS or name in OFFICE_FIXED or name in CALC_VARS or name in ORG_VARS:
                continue
            # отсеиваем мусор из парсинга PDF: многострочные и слишком длинные значения
            if not v or "\n" in v or len(v) > 120:
                continue
            vals.setdefault(name, v)
    except Exception:
        pass
    if doc_values:
        # Вычисляемые заново значения (сторона документа, перечень услуг по профессии,
        # суммы, право) не принимаем из карточки: иначе в документ попадает старый текст
        # от прежней профессии или прежней организации.
        _DERIVED8 = {"services_list", "company_block", "contractor_block", "employee_block",
                     "position_title", "engagement_phrase", "governing_law", "company_tail",
                     "base_salary", "annual_amount_numeric", "annual_amount_words",
                     "monthly_amount_numeric", "monthly_amount_words"}
        vals.update({k: v for k, v in doc_values.items() if v and k not in _DERIVED8})

    # Организация договора — всегда из пула, если админ не выбрал её сам:
    # 1) в сохранённых значениях стоит реальная организация пула → берём весь её
    #    набор реквизитов (название в шапке, название в тексте, название + ИНН/КПП/
    #    ОГРН в подвале — всё из одной записи);
    # 2) значения нет или это обрывок парсинга («LLC », ««ТБАНК»» ) → подставляем
    #    организацию автоматически (город клиента, иначе любая из списка);
    # 3) админ написал своё название руками → оставляем как есть.
    if is_contract_template(tpl_code):
        try:
            from services import employer_pool as _emp
            _title = str((doc_values or {}).get("company_name_in_quotes")
                         or vals.get("company_name_in_quotes") or "").strip()
            _rec = _emp.by_title(_title) if _title else {}
            if _rec:
                # Организация найдена в пуле — берём её реквизиты целиком, включая
                # пустые: если у организации нет КПП или ОГРН, в документе должно быть
                # пустое место (история и прежние значения не подставляются).
                vals.update(_emp.values_of(_rec))
            elif _pinned:
                # организация закреплена за заявкой — автовыбор не применяем
                pass
            elif not _title or len(_title) < 6:
                _cands = [client.get("city"), client.get("address_reg"),
                          client.get("address_live"), client.get("birth_place")]
                vals.update({k: v for k, v in (_emp.values_for(
                    app_id=app_id, client_id=client.get("id"),
                    cities=[c for c in _cands if c]) or {}).items() if v})
        except Exception:
            pass
    # Строки реквизитов для абзаца и подвала собираются ЗДЕСЬ — после того как
    # определена организация заявки. Печатаем только имеющиеся реквизиты: если у
    # компании нет КПП или ОГРН, надпись с ним в документ не попадает (пустота).
    try:
        _i, _k, _o = (str(vals.get(x) or "").strip() for x in ("company_inn", "company_kpp", "company_ogrn"))
        _pairs = [f"INN: {_i}" if _i else "", f"KPP: {_k}" if _k else "", f"OGRN: {_o}" if _o else ""]
        vals["inn_kpp_ogrn"] = ", ".join([x for x in _pairs if x])
        vals["inn_ogrn_line"] = " | ".join([x for x in (f"INN: {_i}" if _i else "",
                                                       f"OGRN: {_o}" if _o else "") if x])
    except Exception:
        pass
    # Фраза о компании в преамбуле и строка о найме собираются здесь: так пустая
    # величина не оставляет в документе лишних слов («as  since») и страну компании
    # не подменяет гражданство клиента (было «laws of the RUSIA»).
    try:
        _cname = str(vals.get("employer_name") or vals.get("company_name_in_quotes") or "").strip()
        _addr = str(vals.get("company_registered_address") or "")
        _country = "Republic of Indonesia" if "indonesia" in _addr.lower() else "Russian Federation"
        vals["company_country"] = _country
        vals["company_incorporated_phrase"] = (
            "(%s), a software development company incorporated under the laws of the %s,"
            % (_cname, _country) if _cname else
            "A software development company incorporated under the laws of the %s," % _country)
        _who = str(vals.get("employee_name") or vals.get("full_name_latin")
                   or vals.get("contractor_full_name") or "").strip()
        _pos = _client_position(client, vals)
        # Дата начала — та же, что в разделе 2 TERM: одно значение на документ.
        _since = (_CONTRACT_DATES.get("term_start_date")
                  or str(vals.get("contract_start_date") or vals.get("start_date")
                         or vals.get("contract_date") or "").strip())
        if _who:
            vals["engagement_line"] = ("— %s is engaged by the Company%s since %s."
                                       % (_who, (" as " + _with_article(_pos)) if _pos else "", _since))
        else:
            vals["engagement_line"] = ""
    except Exception:
        pass
    # Фотография: в сохранённых значениях путь мог остаться от прежнего файла
    # (после облегчения снимка имя меняется) — берём только существующий файл.
    _fresh_photo = _client_photo_path(client.get("id"))
    if _fresh_photo:
        vals["client_photo"] = _fresh_photo
        vals["client_photo_url"] = _fresh_photo

    # Адрес — данные клиента, а не «что-то, что когда-то записалось в документ».
    # В архивных values_json встречались адреса ДРУГИХ клиентов, поэтому здесь
    # адрес клиента всегда побеждает значение из документа.
    try:
        from services.doc_parse import is_russian_address, is_indonesia_address
        _bank = any(w in (tpl_code or "") for w in ("bank_statement", "balance", "movement", "bank"))
        _cli_addr = str((client or {}).get("address_live") or "")
        _cli_reg = str((client or {}).get("address_reg") or "")
        if _bank:
            _ru = next((c for c in (_cli_reg, _cli_addr, _address_from_client_docs((client or {}).get("id")))
                        if c and is_russian_address(c)), "")
            if _ru:
                from services.addr_order import en_order
                _ru = en_order(_ru, _translit)
                vals["address_live"] = _ru
                vals["client_address"] = _ru
            elif is_indonesia_address(vals.get("address_live")):
                vals["address_indonesia"] = vals.get("address_live")
                vals["address_live"] = ""
                vals["client_address"] = ""
        else:
            if _cli_addr and not is_russian_address(vals.get("address_live")):
                vals["address_live"] = _cli_addr
                vals["client_address"] = _cli_addr
    except Exception:
        pass

    # --- Резюме (CV): описание по должности клиента из справочника -----------------
    # Если админ ещё не задал описание — собираем его по паттернам архива
    # (см. docs/cv_pool.md): профиль + обязанности нужного объёма.
    try:
        from services import cv_gen
        if cv_gen.is_cv_template(tpl_code):
            # профессия: сначала из настоящего резюме клиента (Google Drive),
            # затем из карточки — тот же приоритет, что у банковских справок
            # профессия: карточка заявки (с очисткой) → документы клиента с Диска
            # профессия: карточка заявки (с очисткой) → документы клиента с Диска.
            # Должность из комментария заявки главнее: менеджер пишет её прямо в заявке.
            _cl = dict(client or {})
            try:
                from services import brief_values as _bvc
                _bc = str((doc_values or {}).get("brief") or "").strip() or _bvc.read_brief(app_id)
                _rc, _ec = _bvc.parse_position(_bc)
                _pc = _ec or _rc
                if _pc:
                    _cl["position"] = _cl["profession"] = _cl["job_title"] = _pc
            except Exception:
                pass
            _res = cv_gen.resolve_profession(_cl)
            _code = _res.get("code") or ""
            _cv = cv_gen.build_full(
                code=_code, level=cv_gen.level_for_template(tpl_code), client=_cl,
                company=_cl.get("company_name") or _cl.get("company_llc") or "")
            for _k, _v in _cv.items():
                if _v and not vals.get(_k):
                    vals[_k] = _v
            # гражданство и паспорт — из карточки или документов клиента
            if not vals.get("cv_nationality"):
                _nat = (client.get("nationality") or client.get("citizenship") or "").strip()
                if not _nat or _nat.upper() in ("РФ", "РОССИЯ", "RUS", "RU"):
                    _nat = "Russian Federation"
                vals["cv_nationality"] = _nat
            if not vals.get("cv_passport_no"):
                vals["cv_passport_no"] = (client.get("passport_number")
                                          or (doc_values or {}).get("passport_no") or "")
            if not vals.get("cv_date_of_birth"):
                vals["cv_date_of_birth"] = _fmt_date_en(client.get("birth_date"))
            if not vals.get("cv_place_of_birth"):
                vals["cv_place_of_birth"] = client.get("birth_place") or ""
            if not vals.get("cv_passport_issue"):
                vals["cv_passport_issue"] = _fmt_date_en(client.get("passport_issue_date"))
            if not vals.get("cv_passport_expiry"):
                vals["cv_passport_expiry"] = _fmt_date_en(client.get("passport_expiry"))
            # период работы: из настоящего резюме клиента, иначе — от года договора
            if not vals.get("cv_job1_period"):
                _per = ""
                try:
                    _own = cv_gen.read_client_cv(client.get("id")) or {}
                    _per = (_own.get("period") or "").strip()
                except Exception:
                    _per = ""
                if not _per:
                    # Год начала работы берём из договора; если его нет — период не выдумываем
                    # (в подлинниках он всегда настоящий), поле остаётся пустым для администратора.
                    _cd = str(client.get("contract_date") or "")[:4]
                    _per = f"{_cd} — Present" if _cd.isdigit() else ""
                vals["cv_job1_period"] = _per
    except Exception:
        pass

    # --- Дефолты из template_variables (низший приоритет, но выше мусора из истории) ---
    try:
        t = db.q1("SELECT id FROM templates WHERE code=?", (tpl_code,))
        if t:
            for r in db.q("SELECT name, default_value FROM template_variables WHERE template_id=?",
                          (t["id"],)):
                # Значение по умолчанию применяем только к типовым полям:
                # в полях клиента дефолт из реестра означал бы чужие данные.
                # Резюме (cv_*) — исключение: его нарратив (профиль, навыки, опыт,
                # образование) лежит в шаблоне как текст заполненного образца, и дефолт
                # печатал клиенту чужую профессию (05.10.2026). Пустое поле резюме
                # убирается сборщиком, а чужая профессия клиенту недопустима.
                if (r["default_value"] and not vals.get(r["name"])
                        and not _is_personal(r["name"])
                        and not str(r["name"]).startswith("cv_")):
                    vals[r["name"]] = r["default_value"]
            # Поля 1,2,3 и 9..13 списка переменных + адресат — постоянные реквизиты
            # офиса и агентства: карта переменных шаблона перекрывает историю и настройки.
            for r in db.q("SELECT name, default_value FROM template_variables WHERE template_id=?",
                          (t["id"],)):
                if r["name"] in OFFICE_FIXED and (r["default_value"] or "").strip():
                    vals[r["name"]] = r["default_value"].strip()
    except Exception:
        pass

    # --- Алиасы имён переменных (история ↔ шаблон) ---
    _aliases = {
        "balance_value": ["balance_rub"],
        "period_dates": ["balance_date"],
        "client_name": ["full_name_latin", "for_name", "employee_name", "employee_full_name"],
        "passport": ["passport_number", "passport_no", "employee_passport"],
    }
    for src, dsts in _aliases.items():
        if vals.get(src):
            for dt in dsts:
                if not vals.get(dt):
                    vals[dt] = vals[src]

    # --- Банковская справка: дата документа = дата формирования (сегодня),
    #     период: от неё же назад 3 или 12 месяцев — в зависимости от типа справки ---
    if "bank_statement" in tpl_code:
        try:
            from datetime import datetime as _dt
            _real = read_client_bank_statement(client.get("id"))
            if _real.get("balance_rub"):
                # Из настоящей справки клиента берём ДАТУ ОСТАТКА, а длину периода задаёт
                # требование документа: у клиента справка может быть за год, тогда как для
                # продукта нужна выписка за 3 месяца (C1-EXT: min_statement_months=3).
                # Раньше период копировался из справки клиента целиком, и в 3-месячный бланк
                # попадал год — проверка справедливо не пропускала такой пакет.
                _bal = str(_real.get("balance_date") or _real.get("statement_date")
                           or vals.get("balance_date") or "").strip()
                vals["balance_date"] = vals["doc_date"] = _bal
                _months = 12 if "12m" in tpl_code else 3
                try:
                    from services import requirements as _rq
                    _pc = ""
                    if app_id:
                        _rowp = db.q1("""SELECT p.code FROM applications a
                                           JOIN products p ON p.id = a.product_id
                                          WHERE a.id = ?""", (app_id,))
                        _pc = str((_rowp or {}).get("code") or "").upper()
                    _m = (_rq.PRODUCTS.get(_pc) or {}).get("min_statement_months")
                    if _m:
                        _months = int(_m)
                except Exception:      # noqa: BLE001
                    pass
                try:
                    from datetime import datetime as _dt2
                    _d = _dt2.strptime(_bal, "%d.%m.%Y")
                    vals["period_to"] = _d.strftime("%d.%m.%Y")
                    vals["period_from"] = _minus_months(_d, _months).strftime("%d.%m.%Y")
                except Exception:      # noqa: BLE001
                    if _real.get("period_from"):
                        vals["period_from"] = _real["period_from"]
                    if _real.get("period_to"):
                        vals["period_to"] = _real["period_to"]
            else:
                today = _dt.now()
                vals["balance_date"] = vals["doc_date"] = today.strftime("%d.%m.%Y")
                vals["period_to"] = today.strftime("%d.%m.%Y")
                vals["period_from"] = _minus_months(
                    today, 12 if "12m" in tpl_code else 3).strftime("%d.%m.%Y")
        except Exception:
            pass
    elif not vals.get("doc_date") and vals.get("balance_date"):
        vals["doc_date"] = vals["balance_date"]

    # --- Период банковской справки (после всех источников) ---
    bd = (vals.get("balance_date") or "").strip()
    if bd and "bank_statement" not in tpl_code:
        months = 12 if "12m" in tpl_code else 3
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(bd, "%d.%m.%Y")
            vals["period_to"] = d.strftime("%d.%m.%Y")
            vals["period_from"] = _minus_months(d, months).strftime("%d.%m.%Y")
        except Exception:
            pass
    # --- реквизиты компании-спонсора и место подписания (из settings) ---
    try:
        _st = {r["key"]: r["value"] for r in db.q("SELECT key, value FROM settings")}
    except Exception:
        _st = {}
    vals["sponsor_name"]    = _st.get("sponsor_name", "")
    vals["sponsor_company"] = _st.get("sponsor_company", "")
    # attorney_name — постоянное доверенное лицо: приоритет у карты переменных,
    # настройка используется только как запасной вариант.
    if not str(vals.get("attorney_name") or "").strip():
        vals["attorney_name"] = _st.get("attorney_name", "")
    vals["doc_place"]       = _st.get("doc_place", "Badung")
    _place = (vals.get("doc_place") or "Badung").strip()
    _d = vals.get("doc_date") or vals.get("balance_date") or ""
    vals["place_date"] = f"{_place}, {_date_id(_d)}"
    vals["client_address"] = vals.get("address_live") or client.get("address_live") or ""

    # В банковских документах адрес — это адрес в СТРАНЕ КЛИЕНТА (откуда он едет),
    # а не место пребывания в Индонезии. Если в карточке оказался индонезийский
    # адрес (отель, вилла, пермит), банковский документ его не получает: берём
    # адрес из документов клиента (прошлая справка/анкета) либо оставляем пусто.
    try:
        from services.doc_parse import is_indonesia_address
        _bank_doc = any(w in (tpl_code or "") for w in ("bank_statement", "balance", "movement", "bank"))
        from services.doc_parse import is_russian_address
        _addr_now = str(vals.get("address_live") or "")
        if _bank_doc:
            # банковские справки Сбера и Т-Банка формируются по адресу в РОССИИ:
            # приоритет — адрес регистрации, затем адрес из документов клиента
            _cand = [vals.get("address_reg"), _address_from_client_docs(client.get("id")),
                     _addr_now]
            _ru = next((str(c) for c in _cand if c and is_russian_address(str(c))), "")
            if is_indonesia_address(_addr_now):
                vals["address_indonesia"] = _addr_now
            if _ru:
                # единый порядок адреса в англоязычном документе: дом, корпус, квартира,
                # улица, город, регион, индекс, страна (правило Андрея)
                from services.addr_order import en_order
                _ru = en_order(_ru, _translit)
                # Длинный адрес делим на две строки шаблона: одной строкой он не
                # влезает по ширине, и рендер сжимает кегль до нечитаемых 8pt,
                # хотя заказчик требует единый размер шрифта (жалоба по заявке 111).
                _l1, _l2 = _ru, ""
                if len(_ru) > 52:
                    _cs = [m.start() for m in re.finditer(r"[,;]", _ru)]
                    if _cs:
                        _c = min(_cs, key=lambda c: abs(c - len(_ru) // 2))
                        if _c > 15:
                            _l1 = _ru[:_c].rstrip(" ,;")
                            _l2 = _ru[_c:].lstrip(" ,;")
                vals["address_live"] = _l1
                vals["client_address"] = _ru
                vals["address_live_2"] = _l2
            elif is_indonesia_address(_addr_now):
                # российского адреса нет — лучше пусто, чем Бали
                vals["address_live"] = ""
                vals["client_address"] = ""
    except Exception:
        pass

    # Единый порядок адреса в англоязычном бланке — в том числе когда значение пришло из
    # сохранённых значений заявки и переопределение выше его не тронуло (правило Андрея:
    # дом → корпус → квартира → улица → город → регион → индекс → страна).
    try:
        if any(w in (tpl_code or "") for w in ("bank_statement", "balance", "movement", "bank")):
            from services.addr_order import en_order
            _a = str(vals.get("address_live") or "").strip()
            _b = str(vals.get("address_live_2") or "").strip()   # дом/корпус/квартира может лежать отдельной строкой
            if _b and _b not in _a:
                _a = (_a + ", " + _b).strip(", ")
            if _a:
                _a = en_order(_a, _translit)
                _l1, _l2 = _a, ""
                if len(_a) > 52:
                    _cs = [m.start() for m in re.finditer(r"[,;]", _a)]
                    if _cs:
                        _c = min(_cs, key=lambda c: abs(c - len(_a) // 2))
                        if _c > 15:
                            _l1 = _a[:_c].rstrip(" ,;")
                            _l2 = _a[_c:].lstrip(" ,;")
                vals["address_live"] = _l1
                vals["client_address"] = _a
                vals["address_live_2"] = _l2
    except Exception:
        pass

    # автоперевод: если админ ввёл значение по-русски — в документ уходит английский вариант.
    # НО адреса, номера документов, маски карт, суммы и даты — это данные, а не текст:
    # их переводить нельзя, иначе в документ попадает чужой/испорченный адрес.
    _NO_TRANSLATE = ("address_live", "address_reg", "address_registration", "home_address",
                     "registration_address", "client_address", "employee_address",
                     "card_mask", "balance_rub", "balance_value", "balance_words",
                     "period_from", "period_to", "doc_date", "doc_no", "ref_no",
                     "passport_number", "passport_no", "account_no", "contract_no",
                     "birth_date", "date_of_birth", "phone", "email")
    for _k in list(vals.keys()):
        if _k in _NO_TRANSLATE:
            continue
        if isinstance(vals[_k], str) and vals[_k]:
            vals[_k] = _ru_to_en(_k, vals[_k])
    # Баланс прописью и копейки — В САМОМ КОНЦЕ: только здесь balance_rub окончательный.
    # Иначе слова считаются от раннего значения-заглушки, а в документе стоит уже другая сумма
    # (симптом: «672 502, 00» в цифрах и «seventeen thousand…» прописью).
    try:
        _bal_src = vals.get("balance_rub") or vals.get("balance_value") or ""
        _bal_num = parse_amount_any(_bal_src)
        if _bal_num is not None and _bal_num > 0:
            # Цифры — как в настоящей справке («1 770 300,00»), пропись — со скобками.
            vals["balance_rub"] = _fmt_money(_bal_num, tpl_code)
            vals["balance_words"] = _balance_words_from(_bal_num)
            vals["balance_words_2"] = ""      # вторая строка прописи не нужна: всё в одну строку
            vals["balance_cents"] = "%02d" % int(round((_bal_num - int(_bal_num)) * 100))
    except Exception:
        pass

    # Адрес — в самом конце, чтобы никакое переопределение (перевод, значения
    # документа) не подменило его чужим или индонезийским адресом.
    try:
        from services.doc_parse import is_russian_address as _is_ru, is_indonesia_address as _is_id
        _bank_doc = any(w in (tpl_code or "") for w in ("bank_statement", "balance", "movement", "bank"))
        _cli = client or {}
        _cur = str(vals.get("address_live") or "")
        if _bank_doc:
            _ru2 = next((str(c) for c in (_cli.get("address_reg"), _cli.get("address_live"),
                                          _address_from_client_docs(_cli.get("id")))
                         if c and _is_ru(str(c))), "")
            if _is_id(_cur):
                vals["address_indonesia"] = _cur
            if _ru2:
                # реальный российский адрес — используем как есть
                vals["address_live"] = _ru2
                vals["client_address"] = _ru2
            else:
                # адреса нет нигде: город берём из данных клиента (место рождения,
                # кем выдан паспорт, текст документов), иначе — из пула городов;
                # улица, дом и квартира подбираются детерминированно по клиенту
                from services.address_pool import resolve_address
                _hint = " ".join(str(_cli.get(x) or "") for x in
                                 ("birth_place", "address_reg", "address_live", "citizenship"))
                try:
                    _hint += " " + (_address_from_client_docs(_cli.get("id")) or "")
                except Exception:
                    pass
                _gen = resolve_address("client-%s" % _cli.get("id"), "", _hint)
                if _gen.get("address"):
                    vals["address_live"] = _gen["address"]
                    vals["client_address"] = _gen["address"]
                    vals["address_city"] = _gen.get("city") or ""
                    vals["address_generated"] = "1"
        elif is_indonesia_document(tpl_code):
            # Документ по смыслу требует ИНДОНЕЗИЙСКИЙ адрес (письма в иммиграцию,
            # заявления, адреса спонсора/адвоката). Рандомизатор здесь запрещён:
            # берём только реальный адрес из заявки или документов клиента,
            # иначе поле остаётся пустым — администратор выберет значение из списка.
            _real_id = next((str(c) for c in (_cli.get("address_live"), _cli.get("address_reg"),
                                              _address_from_client_docs(_cli.get("id")), _cur)
                             if c and _is_id(str(c))), "")
            if _real_id:
                vals["address_live"] = _real_id
                vals["client_address"] = _real_id
            else:
                vals["address_live"] = ""
                vals["client_address"] = ""
            # отдельные поля писем не должны получить российский адрес клиента
            for _v in INDONESIA_ADDRESS_VARS:
                if _v in vals and _is_ru(vals.get(_v)):
                    vals[_v] = ""
        else:
            if _cli.get("address_live") and not _is_ru(_cur):
                vals["address_live"] = _cli["address_live"]
                vals["client_address"] = _cli["address_live"]
    except Exception:
        pass
    # --- Адрес: единый арбитр ------------------------------------------------
    # Выше адрес собирают несколько исторических блоков и перебивают друг друга.
    # Здесь ставим точку: тип адреса определяется СМЫСЛОМ документа (банковские и
    # рабочие — адрес в России, письма и формы — адрес в Индонезии), оба адреса
    # лежат в своих переменных, деление на две строки делается один раз.
    try:
        from services import addresses as _AD
        from services.addr_order import en_order as _en
        _pair = _AD.client_addresses(client, client.get("id"))
        _ru, _id_a = _pair["ru"], _pair["id"]
        vals["address_ru"] = _ru
        vals["address_in_indonesia"] = _id_a or vals.get("address_in_indonesia") or ""
        vals["address_indonesia"] = _id_a or vals.get("address_indonesia") or ""
        if _AD.is_indonesia_document(tpl_code):
            vals["address_live"] = _id_a
            vals["address_live_2"] = ""
            vals["client_address"] = _id_a
            # российский адрес в индонезийские поля не пускаем ни при каких условиях
            for _v in _AD.INDONESIA_ADDRESS_VARS:
                if _v in vals and _AD._looks_russian(vals.get(_v)):
                    vals[_v] = _id_a
        elif _AD.is_domestic_document(tpl_code):
            if _ru:
                _o = _en(_ru, _translit)
                _l1, _l2 = _AD.split_two_lines(_o)
                vals["address_live"] = _l1
                vals["address_live_2"] = _l2
                vals["client_address"] = _o
            else:
                # российского адреса нет — пусто, но никогда не Бали
                vals["address_live"] = ""
                vals["address_live_2"] = ""
                vals["client_address"] = ""
    except Exception:
        pass
    # --- Договор: срок действия и номер ---
    # Считаем в самом конце: дата договора к этому моменту уже определена всеми
    # источниками (карточка, документы, история). Срок — пять лет, как в архиве.
    try:
        if is_contract_template(tpl_code):
            # даты шапки договора — в формате архивных: «5 March 2025» вместо 2025-03-05
            for _k, _raw in (("passport_issue_date", client.get("passport_issue_date")),
                             ("passport_expiry", client.get("passport_expiry")),
                             ("date_of_birth", client.get("birth_date"))):
                _cur = str(vals.get(_k) or "").strip()
                if not _cur or re.match(r"^\d{4}-\d{2}-\d{2}$", _cur):
                    _f = _fmt_date_uk(_raw)
                    if _f:
                        vals[_k] = _f
            if not vals.get("passport_issued_by"):
                vals["passport_issued_by"] = client.get("passport_issued_by") or ""
            # реквизиты компании: сначала реальные документы клиента, потом карточка
            try:
                _req = read_client_company_requisites(client.get("id")) or {}
            except Exception:
                _req = {}
            for _key, _cl, _short in (("company_inn", "company_inn", "inn"),
                                      ("company_kpp", "company_kpp", "kpp"),
                                      ("company_ogrn", "company_ogrn", "ogrn"),
                                      ("company_registered_address", "company_address", "address")):
                # В договоре организация приходит из пула: если у неё нет КПП или ОГРН,
                # в документе остаётся пустое место. Добирать реквизиты из карточки
                # клиента нельзя — так в договор попадали чужие ИНН/КПП/ОГРН.
                if not is_contract_template(tpl_code) and not vals.get(_key):
                    vals[_key] = str(client.get(_cl) or "") or str(_req.get(_short) or "")
            # название компании в тексте: «<название>, a software development company…»,
            # а если названия нет — без висящей запятой
            _cname = str(vals.get("company_name_in_quotes") or "").strip()
            vals["company_intro_phrase"] = ((_cname + ", a software development company incorporated")
                                            if _cname else "A software development company incorporated")
            # кем выдан и срок действия паспорта — одной фразой, если данные есть
            _by = str(vals.get("passport_issued_by") or "").strip()
            _on = str(vals.get("passport_issue_date") or "").strip()
            _vl = str(vals.get("passport_expiry") or "").strip()
            _iss = ""
            if _by:
                _iss += f", issued by {_by}"
            if _on:
                _iss += f" on {_on}"
            if _vl:
                _iss += f", valid until {_vl}"
            vals["passport_issued_block"] = _iss
            # место рождения: строка «Place of Birth: …, » либо пусто
            _pob = str(vals.get("place_of_birth") or "").strip()
            vals["place_of_birth_block"] = (f"Place of Birth: {_pob}, " if _pob else "")
            # должность: « as <должность>» либо ничего
            # Должность: панель → карточка → профессия из резюме. Одна на весь комплект,
            # поэтому сохраняем её в значениях — остальные блоки берут готовую.
            _pos = _client_position(client, vals)
            if _pos and not str(vals.get("position_title") or "").strip():
                vals["position_title"] = _pos
            # договор берёт должность из {{ position }} — держим оба имени в согласии
            if _pos:
                vals["position"] = _pos
                vals.setdefault("job_title", _pos)
            vals["position_block"] = (" as " + _pos) if _pos else ""
            vals["position_as"] = " as " if _pos else " "
            # адрес в тексте договора: «, with registered address at …,» или пусто
            _addr = str(vals.get("company_registered_address") or "").strip()
            vals["company_address_phrase"] = (f", with registered address at {_addr}," if _addr else "")
            _parts = [p for p in (f"INN: {vals.get('company_inn')}" if vals.get("company_inn") else "",
                                  f"KPP: {vals.get('company_kpp')}" if vals.get("company_kpp") else "",
                                  f"OGRN: {vals.get('company_ogrn')}" if vals.get("company_ogrn") else "") if p]
            if _parts and not vals.get("inn_kpp_ogrn"):
                vals["inn_kpp_ogrn"] = ", ".join(_parts)
            # реквизиты в тексте договора: «INN: …, KPP: …, OGRN: …, » либо пусто —
            # чтобы при отсутствии реквизитов не оставалась висящая запятая
            _req_txt = ", ".join(_parts)
            vals["company_requisites_phrase"] = (f"{_req_txt}, " if _req_txt else "")
            if not vals.get("place_of_birth"):
                vals["place_of_birth"] = client.get("birth_place") or ""
            import datetime as _dt
            _start = None
            # Только данные этого клиента: карточка → ранее сохранённое в документе.
            # Общий пул значений не используем — иначе дата договора одного клиента
            # попадает в документы другого.
            # Приоритет — только ручное значение из панели переменных документа.
            # Дата из карточки клиента не используется: договор составляется «некоторое
            # время назад», дата каждый раз случайная (правило заказчика 05.10.2026).
            _cands = [(doc_values or {}).get("agreement_date"),
                      (doc_values or {}).get("contract_date")]
            for _raw in _cands:
                _s = str(_raw).strip() if _raw else ""
                if not _s:
                    continue
                for _fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%d %B %Y", "%d %B %Y"):
                    try:
                        _start = _dt.datetime.strptime(_s, _fmt).date()
                        break
                    except Exception:
                        continue
                if _start:
                    break
            # Даты договора — скользящая рандомизация (правило заказчика 05.10.2026):
            # документ должен выглядеть составленным некоторое время назад. Шапка и подписи —
            # 5–7 дней назад от сегодня, сам договор — год или два назад, срок 5 лет.
            # Если дата задана вручную (панель переменных/карточка) — она не меняется.
            _dates = _CONTRACT_DATES
            vals["agreement_date"] = _dates["agreement_date"]
            vals["term_start_date"] = _dates["term_start_date"]
            vals["term_end_date"] = _dates["term_end_date"]
            # Должность уже посчитана выше; пусто — фраза собирается без роли.
            _role = str(vals.get("position_title") or "").strip()
            vals["engagement_phrase"] = ("as " + _with_article(_role)) if _role else ""
            if not vals.get("contract_no"):
                import random as _rnd
                vals["contract_no"] = str(_rnd.randint(5010000000, 5999999999))
    except Exception:
        pass

    # --- Индонезийские письма (D12, bridging, conversion, e02): общие форматы ---
    # Пол и гражданство клиента, место рождения: в письмах пишут латиницей
    # и в индонезийской записи (Laki-laki/Perempuan, RUSIA), иначе поля остаются пустыми.
    try:
        if _is_indonesia_letter(tpl_code):
            _g = str(client.get("gender") or "").strip().upper()
            if _g:
                vals["client_gender"] = ("PEREMPUAN" if _g.startswith(("F", "Ж", "W", "P")) and not _g.startswith("PR")
                                         else "LAKI-LAKI")
            if not str(vals.get("client_nationality") or "").strip():
                vals["client_nationality"] = _country_id(client.get("citizenship")
                                                         or client.get("nationality"))
            if not str(vals.get("place_of_birth") or "").strip():
                vals["place_of_birth"] = str(client.get("birth_place") or "").strip()
            # Номер ходатайства и фактические данные клиента ставим БЕЗУСЛОВНО, поверх
            # истории значений: в ней лежит «самое частое» по всем клиентам, из-за этого
            # в письмо попадал чужой номер (64/PTAPB-SP/…) и чужая дата рождения, а к
            # номеру приклеивался префикс, который уже печатает сам шаблон.
            _lno = _d12_letter_no(app_id, client.get("id"))
            if _lno:
                vals["letter_no"] = _lno
            vals["letter_no"] = re.sub(r"^Nomor:\s*", "", str(vals.get("letter_no") or ""))
            _pb2 = str(client.get("birth_place") or "").strip()
            if _pb2:
                vals["place_of_birth"] = _pb2
            _bd2 = str(client.get("birth_date") or "").strip()
            if _bd2:
                try:
                    import datetime as _dt2
                    for _f in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"):
                        try:
                            _bd2 = _dt2.datetime.strptime(_bd2[:10], _f).strftime("%d-%m-%Y")
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
                vals["client_dob"] = _bd2
            _gn2 = str(client.get("gender") or "").strip().upper()
            if _gn2:
                vals["client_gender"] = ("PEREMPUAN"
                                         if _gn2.startswith(("F", "Ж", "W")) and not _gn2.startswith("PR")
                                         else "LAKI-LAKI")
            if not str(vals.get("letter_no") or "").strip():
                vals["letter_no"] = _d12_letter_no(app_id, client.get("id"))
            # адрес клиента в Индонезии — из заявки (карточка клиента), в документах заглавными
            _al = str(client.get("address_live") or client.get("address_reg") or "").strip()
            if _al:
                vals["address_in_indonesia"] = _al.upper()
            # адресат письма — от адреса заявки: офис иммиграции выбирается по адресу клиента
            try:
                from services import immigration_office as _io
                _of = _io.resolve_text(client.get("address_live"), client.get("address_reg"),
                                       client.get("address_zip"), client.get("city"))
                _ad = _io.addressee_for(_of.get("office"))
                if _ad:
                    vals["addressee_line1"] = _ad["line1"]
                    vals["addressee_line2"] = _ad["line2"]
                    vals["addressee_line3"] = _ad["line3"]
                    vals["addressee_office"] = _ad["office"]
            except Exception:
                pass
            # тема письма — название продукта заявки (индонезийская формулировка по коду)
            try:
                if app_id:
                    _pr = db.q1("""SELECT p.code, p.name FROM applications a
                                     LEFT JOIN products p ON p.id = a.product_id
                                    WHERE a.id = ?""", (app_id,))
                    if _pr:
                        _subj = PRODUCT_SUBJECTS.get((_pr["code"] or "").upper())
                        vals["letter_subject"] = _subj or ("Permohonan %s" % (_pr["name"] or "")).strip()
            except Exception:
                pass
            # даты письма — ТОЛЬКО из данных клиента (в истории лежат чужие даты):
            # дата рождения, срок паспорта, срок ITK. Нет данных — поле остаётся пустым.
            _iso = {"date_iso": client.get("birth_date"),
                    "date_iso_2": client.get("passport_expiry"),
                    "date_iso_3": (doc_values or {}).get("stay_permit_expiry") or client.get("stay_permit_expiry")}
            for _k, _raw in _iso.items():
                _d = _parse_any_date(_raw)
                vals[_k] = _d.strftime("%d-%m-%Y") if _d else ""
            # дата документа — всегда текущая на момент сборки (правило реестра),
            # если администратор не задал своё значение
            _dd_admin = str((doc_values or {}).get("doc_date") or "").strip()
            import datetime as _dt_id
            # Дата выписки — день подачи заявки, а не сегодняшний: справка не может быть
            # выписана позже подачи (для прошедших заявок отсчёт от текущего дня ломается).
            vals["doc_date"] = _dd_admin or _app_base_date({"_app_id": app_id}).strftime("%d.%m.%Y")
            # паспортные даты — только из карточки клиента (в истории чужие значения)
            for _k, _raw in (("date_of_issue", client.get("passport_issue_date")),
                             ("date_of_expiry", client.get("passport_expiry"))):
                _d = _parse_any_date(_raw)
                if _d:
                    vals[_k] = _d.strftime("%d.%m.%Y")
                elif _parse_any_date(vals.get(_k)):
                    vals[_k] = _parse_any_date(vals.get(_k)).strftime("%d.%m.%Y")
                else:
                    vals[_k] = ""
            # место и дата рождения одной строкой: «RUSIA / 03-04-1989»
            # (без висящего слэша, если места рождения нет в карточке)
            _place_id = _country_id(str(vals.get("place_of_birth") or "").strip()
                                    or client.get("birth_place") or client.get("citizenship"))
            vals["place_birth_inline"] = " / ".join(
                x for x in (_place_id, str(vals.get("date_iso") or "").strip()) if x)
            # адрес: обрезаем мусорный хвост, попавший из карточки клиента
            for _ak in ("address_in_indonesia", "address_live"):
                _av = str(vals.get(_ak) or "").strip()
                _au = _av.upper()
                if "INDONESIA" in _au and len(_au) > _au.find("INDONESIA") + len("INDONESIA") + 4:
                    vals[_ak] = _av[: _au.find("INDONESIA") + len("INDONESIA")]
            # место и дата подписания: текущая дата составления (правку админа уважаем)
            _pd_admin = str((doc_values or {}).get("place_date") or "").strip()
            # концовка E-02: «{{place}}, {{doc_date}}» — место подписи без «—»
            vals["place"] = "Badung"
            # Договор: рядом с номером паспорта печатается срок его действия
            # (требование 05.10.2026 — иначе в строке стояла дата рождения).
            try:
                _pe = str((client or {}).get("passport_expiry") or "").strip()
                if _pe:
                    import datetime as _dt
                    for _f in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"):
                        try:
                            vals["passport_valid_until"] = _dt.datetime.strptime(_pe, _f).strftime("%d.%m.%Y")
                            break
                        except ValueError:
                            continue
                    else:
                        vals["passport_valid_until"] = _pe
            except Exception:
                pass
            vals["place_date"] = _pd_admin or _fmt_date_id(str(vals.get("doc_place") or "Badung"), app_id=app_id)
            # запасное значение для срока пребывания по ITK
            _permit = str(client.get("stay_permit_no") or "").strip()
            if not str(vals.get("stay_permit_no") or "").strip():
                vals["stay_permit_no"] = _permit
            # номер разрешения на пребывание (ITK) в письмах — только из карточки клиента
            if _permit and not str(vals.get("application_no") or "").strip():
                vals["application_no"] = _permit
    except Exception:
        pass

    # --- Ходатайства D12 (Permohonan Visa / Surat Pernyataan Penjamin) ---
    # Реальные письма спонсора (образец: Bridging_Visa_CLIENT) заполняются иначе,
    # чем российские документы: даты ДД-ММ-ГГГГ, гражданство в индонезийской записи,
    # номер письма вида NN/PTAPB-SP/ДД.ММ.ГГГГ, подписант — директор спонсора.
    try:
        if _is_d12(tpl_code):
            # срок паспорта и дата рождения — ДД-ММ-ГГГГ
            for _k, _raw in (("passport_expiry", client.get("passport_expiry")),
                             ("date_of_birth", client.get("birth_date"))):
                _d = _parse_any_date(_raw) or _parse_any_date(vals.get(_k))
                if _d:
                    vals[_k] = _d.strftime("%d-%m-%Y")
            # место и дата рождения клиента: «RUSSIA / 03-04-1989»
            _pb = _country_id(vals.get("place_of_birth") or client.get("birth_place")
                              or client.get("citizenship"))
            _bd = str(vals.get("date_of_birth") or "").strip()
            vals["place_date_of_birth"] = " / ".join(x for x in (_pb, _bd) if x)
            # гражданство клиента индонезийской записью: RUSIA, UKRAINE…
            vals["client_citizenship"] = (_country_id(vals.get("client_nationality")
                                                      or client.get("citizenship")
                                                      or client.get("nationality"))
                                          or str(vals.get("client_citizenship") or ""))
            # ITK (izin tinggal kunjungan): номер и срок — заполняет админ при необходимости
            if not str(vals.get("itk_no") or "").strip():
                vals["itk_no"] = str(client.get("stay_permit_no") or "").strip()
            _itk_exp = _parse_any_date((doc_values or {}).get("itk_expiry")) or _parse_any_date(vals.get("itk_expiry"))
            if _itk_exp:
                vals["itk_expiry"] = _itk_exp.strftime("%d-%m-%Y")
            # номер письма: NN/PTAPB-SP/ДД.ММ.ГГГГ (постоянный для клиента)
            if not str(vals.get("letter_no") or "").strip():
                vals["letter_no"] = _d12_letter_no(app_id, client.get("id"))
            # адрес клиента в Индонезии — из заявки (карточка клиента), в документах заглавными
            _al = str(client.get("address_live") or client.get("address_reg") or "").strip()
            if _al:
                vals["address_in_indonesia"] = _al.upper()
            # адресат письма — от адреса заявки: офис иммиграции выбирается по адресу клиента
            try:
                from services import immigration_office as _io
                _of = _io.resolve_text(client.get("address_live"), client.get("address_reg"),
                                       client.get("address_zip"), client.get("city"))
                _ad = _io.addressee_for(_of.get("office"))
                if _ad:
                    vals["addressee_line1"] = _ad["line1"]
                    vals["addressee_line2"] = _ad["line2"]
                    vals["addressee_line3"] = _ad["line3"]
                    vals["addressee_office"] = _ad["office"]
            except Exception:
                pass
            # тема письма — название продукта заявки (индонезийская формулировка по коду)
            try:
                if app_id:
                    _pr = db.q1("""SELECT p.code, p.name FROM applications a
                                     LEFT JOIN products p ON p.id = a.product_id
                                    WHERE a.id = ?""", (app_id,))
                    if _pr:
                        _subj = PRODUCT_SUBJECTS.get((_pr["code"] or "").upper())
                        vals["letter_subject"] = _subj or ("Permohonan %s" % (_pr["name"] or "")).strip()
            except Exception:
                pass
            # место и дата подписания: «Badung, 2 Oktober 2026»
            vals["place_date"] = _fmt_date_id(app_id=app_id)
            # подписант — директор спонсора, как в архивных письмах
            _dir = str(vals.get("sponsor_person_name") or "").strip()
            if _dir:
                vals["signatory_name"] = _dir
            # «Pekerjaan dan jabatan» — без заглушки «-»
            if str(vals.get("job_and_position") or "").strip() in ("-", "—"):
                vals["job_and_position"] = ""
            # адрес в Индонезии: обрезаем хвост, попавший из карточки
            _addr = str(vals.get("address_in_indonesia") or "").strip()
            _up = _addr.upper()
            if "INDONESIA" in _up and len(_up) > _up.find("INDONESIA") + len("INDONESIA") + 4:
                vals["address_in_indonesia"] = _addr[: _up.find("INDONESIA") + len("INDONESIA")]
    except Exception:
        pass

    # --- Индонезийские письма: добивка значений (выполняется всегда, вне «глушилки») ---
    try:
        if _is_indonesia_letter(tpl_code):
            # гражданство в индонезийских документах — коротко, латиницей: RUSIA
            _nat = str(vals.get("nationality") or "").strip()
            if not _nat or _nat.lower() in ("russian federation", "россия", "российская федерация", "рф", "russia"):
                vals["nationality"] = (_country_id(vals.get("client_nationality")
                                                  or vals.get("client_citizenship")
                                                  or client.get("citizenship") or "")
                                       or "RUSIA")
            # паспортные даты — в формате индонезийских документов ДД-ММ-ГГГГ
            for _k, _src in (("date_of_issue", "passport_issue_date"), ("date_of_expiry", "passport_expiry")):
                _raw = str(vals.get(_k) or client.get(_src) or "").strip()
                _m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", _raw)
                if _m:
                    vals[_k] = "%s-%s-%s" % (_m.group(3), _m.group(2), _m.group(1))
                elif re.match(r"^(\d{2})[/.](\d{2})[/.](\d{4})$", _raw):
                    vals[_k] = "%s-%s-%s" % (_raw[0:2], _raw[3:5], _raw[6:10])
            # Гарант (penjamin). Раньше здесь жёстко подставлялось имя «Bartosz Pawel Nafalski»
            # всем клиентам — это оказалось человеком из образца, и он уезжал в E-02 любому
            # заявителю (разбор 07.10.2026). По реальным поданным комплектам пустой Guarantor —
            # норма: значение берём только из карточки клиента, иначе оставляем прочерк.
            if str(vals.get("guarantor") or "").strip() in ("", "-", "–", "—"):
                vals["guarantor"] = "-"
            # место и дата рождения одной строкой: «RUSIA / 03-04-1989» (без висящего слэша)
            _place_id = _country_id(str(vals.get("place_of_birth") or "").strip()
                                    or client.get("birth_place") or client.get("citizenship"))
            _bdate = str(vals.get("date_iso") or vals.get("date_of_birth") or "").strip()
            if not re.match(r"^\d{2}-\d{2}-\d{4}$", _bdate):
                _bd = _parse_any_date(client.get("birth_date"))
                _bdate = _bd.strftime("%d-%m-%Y") if _bd else _bdate
            vals["place_birth_inline"] = " / ".join(x for x in (_place_id, _bdate) if x)
            # подписант доверенности (лист «Surat Kuasa») зависит от отделения подачи:
            # Ngurah Rai — директор Bartosz Pawel Nafalski, Denpasar — комиссар Arine Fadillah
            _denpasar = "denpasar" in (tpl_code or "").lower()
            vals["signatory_position"] = ("Komisaris PT ALPHA PRIME BALI" if _denpasar
                                          else "Direktur PT ALPHA PRIME BALI")
            vals["signatory_citizenship"] = "WNI" if _denpasar else "Polandia"
            vals["signatory_nik_or_dash"] = "1271114606750008" if _denpasar else "-"
            # ФИО подписанта тоже строго по отделению подачи (раньше могло подтянуться
            # чужое значение из карточки переменных): Ngurah Rai — директор, Denpasar — комиссар
            vals["signatory_name"] = "Arine Fadillah" if _denpasar else "Bartosz Pawel Nafalski"
            # В письмах подписант печатается полем sponsor_name: держим его тоже строго
            # по отделению, иначе туда попадает получатель доверенности (Marcellena).
            # Верхний блок письма и получатель доверенности — постоянный представитель
            # Марцеллена; подписант внизу — директор (Ngurah Rai) или комиссар (Denpasar).
            vals["sponsor_person_name"] = "MARCELLENA NIRMALA CHRISNA MOERI"
            vals["sponsor_name"] = "Marcellena Nirmala Chrisna Moeri"
            vals["attorney_person_name"] = "MARCELLENA NIRMALA CHRISNA MOERI"
            vals["attorney_name"] = "Marcellena Nirmala Chrisna Moeri"
            vals["attorney_position"] = "Swasta"
            vals["attorney_citizenship"] = "Indonesia"
            vals["attorney_nik"] = "5171015403930001"
            vals["attorney_address"] = "Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya"
            vals["signatory_person_name"] = ("ARINE FADILLAH" if _denpasar
                                             else "BARTOSZ PAWEL NAFALSKI")
            vals["signatory_line"] = ("Arine Fadillah, Komisaris PT Alpha Prime Bali" if _denpasar
                                      else "Bartosz Pawel Nafalski, Direktur PT Alpha Prime Bali")
            # получатель доверенности — постоянный представитель (Marcellena), её KTP;
            # чужой NIK (комиссара) в это поле не попадает
            if str(vals.get("attorney_nik") or "").strip() in ("", "1271114606750008"):
                vals["attorney_nik"] = "5171015403930001"
            if str(vals.get("attorney_name") or "").strip() in ("",):
                vals["attorney_name"] = "Marcellena Nirmala Chrisna Moeri"
            # место и дата подписания — текущая дата сборки
            if not str((doc_values or {}).get("place_date") or "").strip():
                vals["place_date"] = _fmt_date_id(str(vals.get("doc_place") or "Badung"), app_id=app_id)
    except Exception as _e:
        vals["_id_letter_error"] = "%s: %s" % (type(_e).__name__, _e)

    # --- данные разрешения на пребывание (ИТК) из документа клиента -------------
    # Номер и срок разрешения, адрес в Индонезии, пол — берём из PDF клиента,
    # если он есть в его папке; иначе поле остаётся пустым и его проставит администратор.
    try:
        if (_is_indonesia_letter(tpl_code) or (tpl_code or "").lower().startswith("cv")
                or "statement_letter" in str(tpl_code or "")):
            from services.itk_doc import itk_data
            _itk = itk_data(client.get("id"))
            _map_itk = {"permit_no": ("application_no", "stay_permit_no"),
                        "permit_expiry": (),
                        "client_gender": ("client_gender",),
                        "address_in_indonesia": ("address_in_indonesia",),
                        "occupation": ("occupation",),
                        "place_birth_inline": ("place_birth_inline",),
                        "passport_expiry": ("passport_expiry",),
                        "nationality": ("nationality", "client_nationality")}
            for _src, _targets in _map_itk.items():
                _tv = str(_itk.get(_src) or "").strip()
                if not _tv:
                    continue
                for _t in _targets:
                    if vals.get(_t) in (None, ""):
                        vals[_t] = _tv
            # «Existing Stay Permit» в форме E-02 пишется текстом с датой окончания
            # разрешения: VISIT STAY PERMIT (ITK), VALID UNTIL 11-10-2026
            # (дата — из документа ITK клиента, поле STAY PERMIT EXPIRY).
            _exp = str(_itk.get("permit_expiry") or "").strip()
            if _exp:
                vals["itk_expiry"] = re.sub(r"[./]", "-", _exp)
                # Форма E-02: «Date of expiry» — это дата, до которой действует
                # разрешение на пребывание (ИТК). Берём её из документа клиента
                # (STAY PERMIT EXPIRY), а не из срока паспорта.
                if "statement_letter" in str(tpl_code or ""):
                    vals["date_of_expiry"] = re.sub(r"[./]", "-", _exp)
                # Слот «Masa Berlaku ITK» письма — это date_iso_3, но в других шаблонах
                # эта же переменная означает другую дату: подставляем только в письма.
                if "bridging_request_letter" in str(tpl_code or ""):
                    vals["date_iso_3"] = vals["itk_expiry"]
            # Occupation в форме E-02 — должность клиента (та же, что в договоре и резюме:
            # «Manager» приходил из документа ITK и расходился с остальным комплектом).
            if "statement_letter" in str(tpl_code or ""):
                _pt = str(vals.get("position_title") or "").strip()
                if _pt:
                    vals["occupation"] = _pt
            if _exp and not str(vals.get("existing_stay_permit") or "").strip():
                _exp_txt = re.sub(r"[./]", "-", _exp)
                vals["existing_stay_permit"] = ("VISIT STAY PERMIT (ITK), VALID UNTIL %s"
                                                % _exp_txt)
    except Exception:
        pass

    # --- значения из карты переменных (таблица template_variables) --------------
    # Поля, для которых правило и значение уже описаны в базе (доверенное лицо, спонсор,
    # подписант, адресат иммиграционного офиса, тема письма, цель обращения, гарант),
    # добираем отсюда — раньше генератор эту карту не читал и поля оставались пустыми.
    # Данные конкретного клиента (тип «client» и не в белом списке _TV_CONST_VARS)
    # НЕ подставляем: в документ не должны попасть чужие ФИО, суммы и номера.
    try:
        for _name, _info in template_variable_map(tpl_code).items():
            if vals.get(_name) not in (None, ""):
                continue
            _val = _info.get("default") or ""
            if not _val:
                continue
            _kind = _info.get("kind") or ""
            if _kind == "manual":
                continue            # заполняет администратор — не выдумываем
            if _kind == "client" and _name not in _TV_CONST_VARS:
                continue            # это данные клиента, а не константа агентства
            vals[_name] = _val
    except Exception:
        pass

    # --- назначение обращения (Purpose of Application, №14 в форме E-02) --------
    # Правило заказчика 05.10.2026: формируется из ТИПА ПРОДУКТА заявки, а не из карты
    # переменных шаблона — иначе в заявку другого продукта уезжает чужой текст.
    try:
        if (tpl_code or "").lower().startswith("statement_letter"):
            _pid = 0
            if app_id:
                _arow = db.q1("SELECT product_id FROM applications WHERE id=?", (app_id,)) or {}
                _arow = dict(_arow) if not isinstance(_arow, dict) else _arow
                _pid = int(_arow.get("product_id") or 0)
            if not _pid:
                _pid = int((client or {}).get("product_id") or 0)
            if _pid:
                _pr = db.q1("SELECT code, name FROM products WHERE id=?", (_pid,)) or {}
                _pr = dict(_pr) if not isinstance(_pr, dict) else _pr
                _pc = str(_pr.get("code") or "").upper()
                if _pc in PRODUCT_PURPOSES:
                    vals["purpose_of_application"] = PRODUCT_PURPOSES[_pc]
                    if vals.get("stay_permit_to_be_applied_for") not in (None, ""):
                        pass
                elif str(_pr.get("name") or "").strip():
                    vals["purpose_of_application"] = str(_pr["name"]).strip().upper()
    except Exception:
        pass

    # --- резюме: места работы и образование из карточки -------------------------
    # Шаблон резюме содержит cv_job1_*/cv_job2_*/cv_education_*. Раньше второе место
    # работы и образование не заполнялись вовсе. Берём из карточки, ничего не выдумываем:
    # чего нет — остаётся пустым и попадает в список для администратора.
    try:
        import services.cv_gen as _cv
        _cl = client or {}
        _pos = _cv.clean_position(_cl.get("position") or "") if hasattr(_cv, "clean_position") else (_cl.get("position") or "")
        # Должность в резюме печатается по-английски: если профессия указана в заявке
        # (свободный комментарий или поле должности), берём её английское название,
        # а не русскую строку из карточки клиента.
        try:
            from services import brief_values as _bv3
            _r3, _e3 = _bv3.parse_position(_bv3.read_brief(app_id))
            if _e3:
                _pos = _e3
        except Exception:
            pass
        _pairs = {
            "cv_job1_title": _pos,
            "cv_job1_company": str(_cl.get("company_name") or "").strip(),
            "cv_job1_period": str(_cl.get("job1_period") or "").strip(),
            "cv_job2_title": str(_cl.get("job2_title") or "").strip(),
            "cv_job2_company": str(_cl.get("job2_company") or "").strip(),
            "cv_job2_period": str(_cl.get("job2_period") or "").strip(),
            "cv_job2_bullets": str(_cl.get("job2_bullets") or "").strip(),
            "cv_education_school": str(_cl.get("education_school") or "").strip(),
            "cv_education_degree": str(_cl.get("education_degree") or "").strip(),
            "cv_education_years": str(_cl.get("education_years") or "").strip(),
        }
        for _k, _v in _pairs.items():
            if _v and vals.get(_k) in (None, ""):
                vals[_k] = _v
        # обязанности первого места — по профессии, если их не задал администратор
        if vals.get("cv_job1_bullets") in (None, "") and _pos:
            try:
                _code = _cv.detect_position(_pos)
                _bl = _cv.job_block(_code, _cv.level_for_template(tpl_code), limit=5) if _code else ""
                if _bl:
                    vals["cv_job1_bullets"] = _bl
            except Exception:
                pass
    except Exception:
        pass

    # --- обучение: подтверждённые администратором значения -----------------------
    # То, что администратор поставил или выбрал руками при изготовлении документа,
    # считается верным и перекрывает автогенерацию. Данные конкретного клиента
    # (паспорт, счёт, суммы) не трогаем: обобщённая привычка подставила бы чужое.
    try:
        _appr = db.approved_values()
        for _k, _v in (_appr or {}).items():
            if _k in PERSONAL_VARS or _k in CALC_VARS or not _v:
                continue
            _sv = str(_v)
            if len(_sv) > 600:
                continue
            if vals.get(_k) != _sv:
                vals[_k] = _sv
    except Exception:
        pass

    # --- перечень услуг договора (по должности клиента) ------------------------
    # Сохранённая правка админа (doc_values) уже лежит в vals — её не трогаем.
    try:
        _force_sl = False
        try:
            from services import brief_values as _bv3
            _b3 = str((doc_values or {}).get("brief") or "").strip() or _bv3.read_brief(app_id)
            _force_sl = bool(_b3 and _bv3.parse_position(_b3)[1])
        except Exception:
            pass
        if vals.get("services_list") in (None, "") or _force_sl:
            # Должность уже подобрана для документа (карточка → заявка → документы →
            # пул должностей) — перечень услуг обязан совпадать с ней. Иначе при
            # пустом client['position'] договор печатал «services:» без пунктов.
            _sl = services_list_for(client, tpl_code,
                                    position=str(vals.get("position_title")
                                                 or vals.get("position") or ""))
            # Комментарий заявки задаёт должность — услуги в договоре берём из той же
            # профессии, иначе перечень расходится с должностью и с резюме.
            try:
                from services import brief_values as _bv2, cv_gen as _cvg2
                _b2 = str((doc_values or {}).get("brief") or "").strip() or _bv2.read_brief(app_id)
                _r2, _e2 = _bv2.parse_position(_b2)
                _p2 = _e2 or _r2
                if _p2:
                    _prof2 = _cvg2.resolve_profession({"position": _p2, "profession": _p2}) or {}
                    _blk2 = _prof2.get("blocks") or {}
                    _list2 = [str(_blk2.get(k) or "").strip() for k in ("short", "medium", "long")
                              if str(_blk2.get(k) or "").strip()]
                    if _list2:
                        _sl = "".join('<div class="svc-item">\u25cf %s</div>' % t for t in _list2)
            except Exception:
                pass
            if _sl:
                vals["services_list"] = _sl
    except Exception:
        pass

    # Почта клиента — по правилу заказчика (05.10.2026): фамилия+@alpha-prime.group.
    # Ставим в самом конце сборки, чтобы правило действовало для всех документов
    # и не перебивалось значением из карточки.
    # Почта-формула «фамилия+@alpha-prime.group» убрана по указанию заказчика
    # (05.10.2026): в документы она не подставляется.
    vals["email"] = ""

    # Название города — без «г.»/«G.» в начале и без кириллицы в документе.
    for _k in ("place_birth_inline", "place_of_birth", "cv_place_of_birth", "birth_place",
               "birth_place_ru", "place_of_birth_date"):
        if vals.get(_k):
            vals[_k] = _clean_place(str(vals[_k]))


    # ── Эхо образца: значение, совпавшее с примером шаблона, в пакет не идёт ────
    # В примерах подлинников лежат данные другого клиента (ФИО, стаж, ИТ-навыки).
    # Если в значениях оказалось ровно то, что стоит в примере, поле считается
    # незаполненным — иначе чужой человек попадает в резюме реального клиента.
    try:
        _tc = (args[1] if len(args) > 1 else kwargs.get("tpl_code")) or ""
        if _tc:
            _rows = db.q("""SELECT tv.name, tv.examples_json FROM template_variables tv
                              JOIN templates t ON t.id=tv.template_id WHERE t.code=?""", (_tc,)) or []
            for _r in _rows:
                _ex = str(_r.get("examples_json") or "")
                _val = str(vals.get(_r["name"]) or "").strip()
                if _val and len(_val) > 3 and _val[:40] in _ex:
                    vals[_r["name"]] = ""
    except Exception:
        pass

    return vals


# --- Ходатайства D12: индонезийские форматы ---
_ID_MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni",
              "Juli", "Agustus", "September", "Oktober", "November", "Desember")
_COUNTRY_ID = {"RUSSIA": "RUSIA", "RUSSIAN FEDERATION": "RUSIA", "РОССИЯ": "RUSIA",
               "РОССИЙСКАЯ ФЕДЕРАЦИЯ": "RUSIA", "РФ": "RUSIA", "RUS": "RUSIA", "UKRAINE": "UKRAINA", "УКРАИНА": "UKRAINA",
               "BELARUS": "BELARUSIA", "KAZAKHSTAN": "KAZAKHSTAN", "POLAND": "POLANDIA",
               "ПОЛЬША": "POLANDIA", "INDONESIA": "INDONESIA", "ИНДОНЕЗИЯ": "INDONESIA",
               "UZBEKISTAN": "UZBEKISTAN", "KYRGYZSTAN": "KIRGIZSTAN", "ARMENIA": "ARMENIA",
               "GEORGIA": "GEORGIA", "MOLDOVA": "MOLDOVA", "AZERBAIJAN": "AZERBAIJAN"}


def _is_indonesia_letter(tpl_code: str) -> bool:
    """Письма в иммиграцию: D12, bridging, conversion, statement letter e02."""
    code = (tpl_code or "").lower()
    return any(w in code for w in ("d12", "bridging", "conversion", "statement_letter"))


def _is_d12(tpl_code: str) -> bool:
    """Ходатайства в иммиграцию: d12_cover_letter / d12_statement_letter."""
    return "d12" in (tpl_code or "").lower()


def _parse_any_date(value):
    """Разбирает дату в любом из встречающихся форматов, возвращает date или None."""
    import datetime as _dt
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d.%m.%y", "%d %B %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return _dt.datetime.strptime(text[:19] if "%H" in fmt else text, fmt).date()
        except Exception:
            continue
    return None


def _country_id(value: str) -> str:
    """Страна в индонезийской записи: Россия → RUSIA."""
    text = str(value or "").strip()
    if not text:
        return ""
    key = text.upper().strip()
    if key in _COUNTRY_ID:
        return _COUNTRY_ID[key]
    for ru, ident in _COUNTRY_ID.items():
        if ru and (ru in key or key in ru):
            return ident
    return key


def _fmt_date_id(place: str = "Badung", app_id=None) -> str:
    """Дата подписания индонезийского письма: «Badung, 2 Oktober 2026».

    Отсчёт — от даты подачи заявки: письмо не может быть датировано позже подачи.
    """
    import datetime as _dt
    today = _app_base_date({"_app_id": app_id}) if app_id else _dt.date.today()
    return "%s, %d %s %d" % (place, today.day, _ID_MONTHS[today.month - 1], today.year)


def _d12_letter_no(app_id=None, client_id=None) -> str:
    """Номер ходатайства: <номер заявки>/PTAPB-SP/<дата оформления>.

    Формат задан заказчиком 05.10.2026: первая часть — номер заявки в системе,
    последняя — текущая дата оформления (ДД.ММ.ГГГГ). Если заявка не передана —
    берём последнюю заявку клиента; если и её нет, номер остаётся пустым
    (данные не выдумываем).
    """
    import datetime as _dt
    num = app_id
    if not num and client_id:
        try:
            row = db.q1("""SELECT id FROM applications WHERE client_id=?
                            ORDER BY id DESC LIMIT 1""", (client_id,))
            num = row["id"] if row else None
        except Exception:
            num = None
    if not num:
        return ""
    # Дата оформления — день подачи заявки, а не сегодняшний: иначе у прошедшей заявки
    # номер письма содержит дату из будущего относительно самой подачи.
    _base = _app_base_date({"_app_id": num})
    return "%s/PTAPB-SP/%s" % (num, _base.strftime("%d.%m.%Y"))


def fio_full_for_display(text: str) -> str:
    """Полное ФИО (с отчеством) для ФИО из оригинального примера.

    В примерах отчества нет, а в наших документах оно должно быть: ищем клиента в базе
    и берём его ФИО целиком. Если клиента не нашли — отдаём ФИО как есть.
    """
    text = (text or "").strip()
    if not text:
        return ""
    sur, nm, pat = _split_fio_text(text)
    if pat or not sur:
        return text
    try:
        rows = db.q("""SELECT * FROM clients
                       WHERE UPPER(COALESCE(surname,''))=?
                          OR UPPER(COALESCE(name,''))=?
                          OR UPPER(COALESCE(full_name_latin,'')) LIKE ?
                       LIMIT 5""",
                    (sur.upper(), sur.upper(), "%" + sur.upper() + "%"))
    except Exception:
        rows = []
    for r in rows:
        full = _fio_full_latin(dict(r))
        if full and sur.upper() in full.upper():
            return full
    return _translit(text).upper()


_NAT_EN = {"RUSSIAN FEDERATION": "Russian Federation", "RUSSIA": "Russian Federation",
           "РОССИЙСКАЯ ФЕДЕРАЦИЯ": "Russian Federation", "РОССИЯ": "Russian Federation",
           "РФ": "Russian Federation", "RUSIA": "Russian Federation", "RUSSIA": "Russian Federation",
           "INDONESIA": "Indonesia", "ИНДОНЕЗИЯ": "Indonesia"}


def _nat_english(value) -> str:
    """Гражданство по-английски: «РОССИЙСКАЯ ФЕДЕРАЦИЯ» → «Russian Federation»."""
    s = re.sub(r"\s+", " ", str(value or "")).strip()
    if not s:
        return ""
    up = s.upper()
    if up in _NAT_EN:
        return _NAT_EN[up]
    # Уже транслитерированная форма («Rossiyskaya federatsiya», «ROSSIYSKAya FEDERATsIya»):
    # распознаём по корню и отдаём каноничное написание, иначе в документ уходила
    # смесь регистров из транслита.
    _lat = re.sub(r"[^A-Z]", "", up)
    if _lat.startswith("ROSSIYSK") or _lat.startswith("ROSSIJSK") or _lat in (
            "RUSSIA", "RUSIA", "RUSSIANFEDERATION", "RUSSIANFED", "RF"):
        return "Russian Federation"
    if re.search(r"[\u0400-\u04ff]", s):
        try:
            from bot.ai_parser import translit_ru
            s = translit_ru(s)
        except Exception:
            pass
    return s.upper() if len(s) == 3 else s[:1].upper() + s[1:].lower()


_PLACE_PREFIX = re.compile(r"^\s*(?:г\.\s*|гор\.\s*|город\s+|г\s+|g\.\s*|city\s+of\s+)", re.I)


def _clean_place(value: str) -> str:
    """Название города пишем сразу, без буквы «г.»/«G.» в начале (правило заказчика 05.10.2026).

    «Г. МОСКВА» → «MOSKVA»; кириллица транслитерируется, чтобы в документе не было
    русского текста.
    """
    s = _PLACE_PREFIX.sub("", str(value or "").strip())
    if re.search(r"[\u0400-\u04ff]", s):
        try:
            from bot.ai_parser import translit_ru
            s = " / ".join(translit_ru(p.strip()) for p in s.split("/"))
        except Exception:
            pass
    return re.sub(r"\s+", " ", s).strip()


def build_template_values(*args, **kwargs):
    """Общая точка входа: значения документа.

    Почта-формула «фамилия+@alpha-prime.group» убрана по указанию заказчика
    (05.10.2026): в документы она не подставляется ни в одном шаблоне.
    """
    vals = _build_template_values_impl(*args, **kwargs) or {}
    try:
        client = (args[0] if args else kwargs.get("client")) or {}
        mail = _client_email(client)
        if mail:
            vals["email"] = mail
    except Exception:
        pass

    # Данные клиента сильнее значений примера шаблона и старых сохранённых значений:
    # иначе в резюме уходили ФИО, даты и стаж клиента из образца (требование 05.10.2026).
    _cl = {}
    try:
        _cl = (args[0] if args else kwargs.get("client")) or {}
    except Exception:
        _cl = {}
    if isinstance(_cl, dict) and _cl:
        _pos = re.sub(r"\s*\([^)]*\)\s*", " ", str(_cl.get("position") or "")).strip()
        # Гражданство в документе — по-английски.
        _nat_en = _nat_english(_cl.get("citizenship") or _cl.get("nationality"))

        # Имя в шапке резюме — без отчества, как в настоящих образцах («CLIENT_048»).
        # Полное ФИО с отчеством не влезает в отведённую ширину и накладывается на
        # строку с датой рождения ниже.
        _cv_name_short = " ".join(
            x for x in (str(_cl.get("surname") or "").strip(),
                        str(_cl.get("name") or "").strip()) if x)
        if _cv_name_short and re.search(r"[\u0400-\u04ff]", _cv_name_short):
            _cv_name_short = _fio_full_latin(_cl)
        for _k, _v in (("cv_name", _cv_name_short or _fio_full_latin(_cl)),
                       ("full_name_latin", _fio_full_latin(_cl)),
                       ("cv_date_of_birth", _fmt_date_en(_cl.get("birth_date"))),
                       ("cv_place_of_birth", _clean_place(_cl.get("birth_place"))),
                       ("cv_nationality", _nat_en or ""),
                       ("cv_passport_no", str(_cl.get("passport_number") or "").strip()),
                       ("cv_passport_issue", _fmt_date_en(_cl.get("passport_issue_date"))),
                       ("cv_passport_expiry", _fmt_date_en(_cl.get("passport_expiry"))),
                       ("cv_profession", _pos),
                   ("passport_valid_until", _fmt_dotted(_cl.get("passport_expiry"))),
                   ("cv_job1_company", str(_cl.get("company_name") or "").strip()),
                   ("cv_job1_period", str(_cl.get("job1_period") or "").strip()),
                   ("cv_job2_company", str(_cl.get("job2_company") or "").strip()),
                   ("cv_job2_title", str(_cl.get("job2_title") or "").strip()),
                   ("cv_job2_period", str(_cl.get("job2_period") or "").strip()),
                   ("cv_job2_bullets", str(_cl.get("job2_bullets") or "").strip()),
                   ("cv_education_school", str(_cl.get("education_school") or "").strip()),
                   ("cv_education_degree", str(_cl.get("education_degree") or "").strip()),
                   ("cv_education_years", str(_cl.get("education_years") or "").strip()),
                   ("cv_job3_company", str(_cl.get("job3_company") or "").strip()),
                   ("cv_job3_title", str(_cl.get("job3_title") or "").strip()),
                       ("cv_job1_title", _pos),
                       ("cv_job1_company", str(_cl.get("company_name") or "").strip())):
            if _v:
                vals[_k] = _v

    # Должность в резюме — по-английски, из профессии заявки. В карточке клиента
    # должность хранится по-русски («артист продюсер»), и именно она уходила в шапку
    # резюме; берём английское название профессии, указанной в заявке.
    try:
        from services import brief_values as _bv4
        _az4 = kwargs.get("app_id")
        if _az4 is None and len(args) > 3:
            _az4 = args[3]
        _r4, _e4 = _bv4.parse_position(_bv4.read_brief(_az4))
        if _e4:
            vals["cv_job1_title"] = _e4
            vals["cv_profession"] = _e4
            if not str(vals.get("cv_position") or "").strip():
                vals["cv_position"] = _e4
    except Exception:
        pass

    # Резюме: образование и места работы. Если в карточке клиента их нет, собираем
    # по образцу из пулов системы (вуз по городу, компания по сфере профессии).
    try:
        from services import cv_fill as _cf, cv_gen as _cg5
        _tc5 = args[1] if len(args) > 1 else kwargs.get("tpl_code")
        if _tc5 and _cg5.is_cv_template(str(_tc5)):
            _cl5 = dict((args[0] if args else kwargs.get("client")) or {})
            _az5 = kwargs.get("app_id")
            if _az5 is None and len(args) > 3:
                _az5 = args[3]
            _title5 = str(vals.get("cv_position") or vals.get("position_title")
                          or _cl5.get("position") or "").strip()
            _code5 = (_cg5.resolve_profession({"position": _title5, "profession": _title5}) or {}).get("code") or ""
            _cmp5 = str(vals.get("employer_name") or vals.get("company_name")
                        or _cl5.get("company_name") or _cl5.get("company_llc") or "").strip()
            # Организация в резюме — только латиницей (документ на английском).
            try:
                from services import latin as _lat5
                if _lat5.has_cyrillic(_cmp5):
                    _cmp5 = _lat5.org_name(_cmp5)
            except Exception:
                pass
            # Организация в резюме должна совпадать с договором (документ 11):
            # договор уже хранит подставленную организацию в своих значениях —
            # берём её оттуда, иначе в резюме оказывается другое место работы.
            try:
                _row5 = db.q1("""SELECT ad.values_json FROM application_documents ad
                                   JOIN templates t ON t.id = ad.template_id
                                  WHERE ad.application_id=? AND t.doc_index=11
                                  ORDER BY ad.id DESC LIMIT 1""", (int(_az5 or 0),))
                _dv5 = json.loads((_row5 or {}).get("values_json") or "{}")
                _from_contract = str(_dv5.get("company_name_in_quotes") or _dv5.get("company_name") or "").strip()
                if _from_contract:
                    _cmp5 = _from_contract
                    try:
                        from services import latin as _lat5b
                        if _lat5b.has_cyrillic(_cmp5):
                            _cmp5 = _lat5b.org_name(_cmp5)
                    except Exception:
                        pass
            except Exception:
                pass
            # «NKO», «SOTKA», «Chillgaming» и подобный мусор из распознавания заявки
            # работодателем не считается: название должно выглядеть как организация.
            if _cmp5 and len(_cmp5) < 6 and not any(w in _cmp5.upper() for w in ("LLC", "LTD", "ООО")):
                _cmp5 = ""
            if not _cmp5:
                # Работодателя берём из того же пула, что и договор: в резюме должно
                # стоять ровно то название, которое напечатано в контракте.
                try:
                    from services import employer_pool as _emp5
                    _cmp5 = str((_emp5.pick(app_id=int(_az5 or 0), client_id=_cl5.get("id")) or {})
                                .get("company") or "").strip()
                except Exception:
                    _cmp5 = ""
            _fill5 = _cf.fill_for(app_id=int(_az5 or 0), client=_cl5, code=_code5, company=_cmp5)
            for _k5, _v5 in (_fill5 or {}).items():
                if _v5 and not str(vals.get(_k5) or "").strip():
                    vals[_k5] = _v5
            # Профиль и текущее место работы — по формуле резюме: у описания профессии
            # не должно быть машинной фразы «extensive experience across … environment».
            if _fill5.get("cv_summary"):
                vals["cv_summary"] = _fill5["cv_summary"]
            # Текущее место работы в резюме — всегда организация из договора,
            # даже если в карточке клиента уже стояла другая: приоритет у договора.
            if _fill5.get("cv_job1_company"):
                vals["cv_job1_company"] = _fill5["cv_job1_company"]
    except Exception:
        pass

    # Резюме на английском: место работы пишется латиницей в том же виде, что и
    # в договоре («Media Daydzhest LLC»), а из карточки приходит «ООО «Медиа Дайджест»».
    # Брать название из org_pool нельзя: он выбирает организацию по своему seed
    # и в резюме попадала ДРУГАЯ фирма, чем в договоре.
    try:
        _jc9 = str(vals.get("cv_job1_company") or "")
        if re.search(r"[\u0400-\u04ff]", _jc9):
            from bot.ai_parser import translit_ru as _tr9
            _lat9 = _tr9(_jc9)
            _lat9 = re.sub(r"^\s*(OOO|OAO|ZAO|IP)\s*", "", _lat9).strip().strip('"\u00ab\u00bb')
            _lat9 = re.sub(r"\s+", " ", _lat9).strip()
            if _lat9:
                vals["cv_job1_company"] = _lat9 + (" LLC" if not _lat9.endswith("LLC") else "")
    except Exception:
        pass

    # --- Договор работы с организацией (Employment Contract) --------------------
    # Документ внедрён 06.10.2026 по реальному образцу из комплекта клиента:
    # стороны, номер, дата, реквизиты организации и данные работника — из системы.
    try:
        _tz7 = args[1] if len(args) > 1 else kwargs.get("tpl_code")
        # Договор работы с организацией (Employment Contract) и Remote Work Agreement
        # используют один и тот же набор сторон и реквизитов: организация заявки,
        # её адрес, ИНН/КПП/ОГРН, подписант — поэтому блок общий.
        if "employment_contract" in str(_tz7 or "") or "remote_work_agreement" in str(_tz7 or ""):
            _az7 = kwargs.get("app_id")
            if _az7 is None and len(args) > 3:
                _az7 = args[3]
            _cl7 = client or {}
            # Организация — единый источник: значения договора заявки (документ №11).
            _company7 = ""
            try:
                _row7 = db.q1("""SELECT ad.values_json FROM application_documents ad
                                   JOIN templates t ON t.id = ad.template_id
                                  WHERE ad.application_id=? AND t.doc_index=11
                                  ORDER BY ad.id DESC LIMIT 1""", (int(_az7 or 0),))
                _dv7 = json.loads((_row7 or {}).get("values_json") or "{}")
                _company7 = str(_dv7.get("company_name_in_quotes") or _dv7.get("company_name") or "").strip()
            except Exception:
                _company7 = ""
            if not _company7:
                _company7 = str(vals.get("company_name_in_quotes") or vals.get("employer_name") or "").strip()
            # мусор из распознавания заявки («NKO», «"SOTKA», «Chillgaming») организацией не считается:
            # у настоящего названия есть организационная форма или это минимум два слова
            _up7 = _company7.upper()
            if _company7 and not any(w in _up7 for w in ("LLC", "LTD", "ООО", "LLP", "INC", "CORP")) and len(_company7.split()) < 2:
                _company7 = ""
            if _company7:
                vals["company_full_name"] = _company7
            # Организация — одна на всю заявку (правило заказчика 07.10.2026):
            # организация из заявки имеет приоритет; если её нет — подбор по виду
            # деятельности должности из пула Москвы и Санкт-Петербурга. Тот же выбор
            # используется в резюме и контракте, поэтому организация не «плавает».
            try:
                _org7x = _org_for_application(_cl7 or {}, _az7, vals)
                if _org7x:
                    _company7 = str(_org7x).strip()
                    vals["company_full_name"] = _company7
            except Exception:
                pass
            _rec7 = {}
            try:
                # Реквизиты — из единого пула организаций: он собран из наших документов
                # и истории заявок, поэтому в договоре и контракте они совпадают.
                from services import org_pool as _op7
                _orgs7 = _op7.organizations()
                _kk7 = _op7._key(vals.get("company_full_name") or "")
                _rec7 = next((o for o in _orgs7 if _op7._key(o.get("name")) == _kk7), {}) or {}
                if not _rec7:
                    _rec7 = _op7.pick_for(profession=str(vals.get("position_title") or _cl7.get("position") or ""),
                                          city=str(_cl7.get("city") or ""), app_id=_az7) or {}
            except Exception:
                _rec7 = {}
            if not _rec7:
                try:
                    from services import employer_pool as _emp7
                    _rec7 = _emp7.pick(app_id=int(_az7 or 0), client_id=_cl7.get("id")) or {}
                except Exception:
                    _rec7 = {}
            _addr7 = str(_rec7.get("address") or "").strip()
            # Реквизиты работодателя — строго из ОДНОЙ записи пула.
            # Раньше имя, адрес и ИНН/КПП/ОГРН приходили из разных источников, и в
            # одном договоре оказывались данные трёх разных организаций (имя — одной,
            # адрес — другой, реквизиты — третьей, а иногда и банк клиента). Такой
            # документ подавать нельзя: ИНН не сходится с названием.
            try:
                if _rec7:
                    _orgn7 = str(_rec7.get("name_lat") or _rec7.get("legal_name_lat")
                                 or _rec7.get("name") or "").strip().strip('"')
                    if _orgn7:
                        vals["employer_name"] = _orgn7
                        vals["company_name"] = _orgn7
                        vals["company_name_in_quotes"] = _orgn7
                        vals["company_full_name"] = _orgn7
                    _oa7 = str(_rec7.get("address_lat") or _rec7.get("address") or "").strip()
                    if _oa7:
                        vals["company_registered_address"] = _oa7
                    for _k7, _s7 in (("company_inn", "inn"), ("company_kpp", "kpp"),
                                     ("company_ogrn", "ogrn")):
                        _v7 = str(_rec7.get(_s7) or "").strip()
                        if _v7:
                            vals[_k7] = _v7
                    _dir7 = str(_rec7.get("director_lat") or _rec7.get("director") or "").strip()
                    if _dir7:
                        vals["signer_name"] = _dir7
                    _ct7 = str(_rec7.get("city_lat") or _rec7.get("city") or "").strip()
                    if _ct7:
                        vals["company_city"] = _ct7
            except Exception:
                pass
            if _addr7:
                _parts7 = [_p.strip() for _p in _addr7.split(",")]
                vals["company_address_1"] = ", ".join(_parts7[:2])
                vals["company_address_2"] = ", ".join(_parts7[2:])
            else:
                # нет адреса из пула — не оставляем в документе чужие реквизиты образца
                vals["company_address_1"] = ""
                vals["company_address_2"] = ""
            vals["company_type"] = "Limited Liability Company"
            # город/регион регистрации организации берём из её адреса, а не из карточки клиента
            _city7 = ""
            if _addr7:
                # город — первая часть адреса без цифр (индекс и «intra-city…» не берём)
                for _p7 in [x.strip() for x in _addr7.split(",")]:
                    if _p7 and not re.search(r"\d", _p7):
                        _city7 = _p7
                        break
            vals["company_state"] = _city7 or "Moscow"
            # Место подписания в шапке договора — город организации (в образце «Moscow»).
            if not str(vals.get("agreement_place") or "").strip():
                vals["agreement_place"] = _city7 or "Moscow"
            vals["company_country"] = "Russia"
            # п.7 (Governing Law) — переменная по смыслу: это право страны организации,
            # а не всегда «the State of …, USA» из образца американской компании.
            _c7 = str(_rec7.get("country") or vals.get("company_country") or "Russia").strip()
            _cu7 = _c7.lower()
            if any(x in _cu7 for x in ("russ", "росси", "рф")):
                _law7 = "the Russian Federation"
            elif any(x in _cu7 for x in ("usa", "united states", "u.s.")):
                _law7 = "the State of %s, USA" % (str(_rec7.get("state") or "California").strip() or "California")
            else:
                _law7 = "the laws of %s" % _c7
            vals["governing_law"] = _law7
            vals["company_entity_no"] = str(_rec7.get("ogrn") or _rec7.get("inn") or "").strip()
            # номер договора: инициалы названия (без организационной формы) + номер заявки
            _name7 = re.sub(r"\b(LLC|LTD|LLP|INC|CORP|ООО|Limited|Liability|Company)\b", "",
                            str(vals.get("company_full_name") or ""), flags=re.I).strip(' ".,')
            _words7 = [w for w in re.findall(r"[A-Za-zА-Яа-я]{2,}", _name7)]
            _init7 = "".join(w[0] for w in _words7[:2]).upper() if _words7 else ""
            if not _init7.isalpha() or not _init7:
                _init7 = "EC"
            vals["contract_no"] = "%s-%s" % (_init7, _az7 or "")
            vals["contract_place"] = str(_cl7.get("city") or "Moscow").strip() or "Moscow"
            # Фраза о работодателе — одной переменной, чтобы в документе не склеивались
            # обрывки блоков: как в подлиннике («Linguamarina, Inc., a General Corporation
            # incorporated under the laws of the State of California, USA, Entity Number:
            # 4272843, with registered and mailing address at …»).
            _addr_line7 = ", ".join([x for x in (vals.get("company_address_1"), vals.get("company_address_2")) if str(x or "").strip() and str(x).strip() != str(vals.get("company_state") or "").strip()])
            # в пуле адрес организации хранится городом: дополняем страной, как в подлинных договорах
            if _addr_line7 and "russia" not in _addr_line7.lower() and "russian" not in _addr_line7.lower() and "india" not in _addr_line7.lower():
                _addr_line7 = "%s, %s" % (_addr_line7, vals.get("company_country") or "Russia")
            if not _addr_line7:
                # в подлинниках у организации указан и город, и страна
                _addr_line7 = "%s, %s" % (str(vals.get("company_state") or "Moscow").strip() or "Moscow",
                                          vals.get("company_country") or "Russia")
            # страна в законах договора печатается полным названием: в подлинниках
            # «incorporated under the laws of the Russian Federation», а не «of Russia»
            _ctry7 = str(vals.get("company_country") or "Russia").strip()
            _laws_phr7 = "the Russian Federation" if _ctry7.lower().startswith("rus") else _ctry7
            vals["company_block"] = ("%s, a %s incorporated under the laws of %s, Entity Number: %s, "
                                     "with registered and mailing address at %s, (hereinafter referred to as the \"Company\")") % (
                str(vals.get("company_full_name") or "").strip() or 'the Company',
                vals.get("company_type") or "Limited Liability Company",
                _laws_phr7,
                str(vals.get("company_entity_no") or "").strip() or "—",
                _addr_line7 or (vals.get("company_state") or "").strip() or "Russia")
            _cb7 = str(vals.get("company_block") or "")
            _nm7 = str(vals.get("company_full_name") or "").strip()
            vals["company_tail"] = _cb7[len(_nm7):] if (_nm7 and _cb7.startswith(_nm7)) else _cb7
            vals["contract_date"] = str(vals.get("term_start_date") or vals.get("agreement_date") or "").strip()
            # подпись работника: «BUDKO O.», подписант организации печатается по данным пула либо пустым
            _fio7 = str(vals.get("employee_full_name") or "").strip()
            _w7 = _fio7.split()
            vals["employee_short"] = ("%s %s." % (_w7[0], _w7[1][0]) if len(_w7) > 1 else _fio7).strip()
            vals["signer_name"] = str(_rec7.get("director_lat") or _rec7.get("director")
                                     or _rec7.get("signer_name") or "").strip()
            # национальность в карточке встречается сокращённо («RUSIA») — печатаем как в подлинных договорах
            _nat7 = str(vals.get("nationality") or "").strip().upper()
            if _nat7.startswith("RUSIA"):
                # в подлинных договорах и бланках гражданство пишут именно так
                vals["nationality"] = "RUSIA"
            vals["signer_title"] = "GENERAL DIRECTOR"
            # Национальность и место рождения из карточки приходят по-русски или
            # сокращённо («РОССИЙСКАЯ ФЕДЕРАЦИЯ», «Е ГОР БЕЛГОРОД») и после транслита
            # давали в договор «ROSSIYSKAya FEDERATsIya» и «E GOR BELGOROD».
            try:
                _n7 = _nat_english(vals.get("nationality") or _cl.get("citizenship")
                                   or _cl.get("nationality"))
                if _n7:
                    vals["nationality"] = _n7
                    vals["client_nationality"] = _n7
                _pb7 = re.sub(r"^\s*(?:Е|E|Г|G)\s*(?:ГОР|GOR)\.?\s*", "",
                              str(vals.get("place_of_birth") or _cl.get("birth_place") or "").strip(),
                              flags=re.I)
                if re.search(r"[\u0400-\u04ff]", _pb7):
                    try:
                        from bot.ai_parser import translit_ru as _tr7
                        _pb7 = _tr7(_pb7)
                    except Exception:
                        pass
                _pb7 = re.sub(r"\s+", " ", _pb7).strip().title() if _pb7 else ""
                if _pb7:
                    vals["place_of_birth"] = _pb7
                    vals["client_birth_place"] = _pb7
            except Exception:
                pass
            # Номер договора — случайный по правилу, но всегда есть: без него в шапке
            # печаталось «EMPLOYMENT CONTRACT No. R-» с пустым номером.
            try:
                # Номер договора фиксируется при первой сборке и дальше берётся как есть,
                # поэтому в документ попадал обрезок «R-» без цифр: такой номер негоден.
                _cn7 = str(vals.get("contract_no") or "").strip()
                if not re.search(r"\d", _cn7):
                    import random as _r7
                    vals["contract_no"] = "R-%d" % _r7.randint(5010000, 5999999)
            except Exception:
                pass
            # Блоки сторон печатаются целыми абзацами: в Remote Work Agreement стороны
            # идут отдельными абзацами, и обрывки («Federation, Place of Birth: …» без
            # имени и паспорта) в документ попадать не должны.
            try:
                _empl7b = str(vals.get("employee_full_name") or vals.get("employee_name")
                              or vals.get("full_name") or vals.get("client_name") or "").strip()
                _pp7b = str(vals.get("passport_number") or "").strip()
                _dob7b = str(vals.get("date_of_birth") or "").strip()
                _nat7b = str(vals.get("nationality") or "").strip()
                _pob7b = str(vals.get("place_of_birth") or "").strip()
                _contr7b = [x for x in (
                    _empl7b,
                    ("Passport No: %s" % _pp7b) if _pp7b else "",
                    ("Date of Birth: %s" % _dob7b) if _dob7b else "",
                    ("Nationality: %s" % _nat7b) if _nat7b else "",
                    ("Place of Birth: %s" % _pob7b) if _pob7b else "",
                ) if x]
                vals["contractor_block"] = (", ".join(_contr7b) + ', (hereinafter referred to as the "Contractor")') \
                    if _contr7b else ""
                # в трудовом договоре тот же блок сторон, но с именем «Employee»
                vals["employee_block"] = (", ".join(_contr7b) + ', (hereinafter referred to as the "Employee")') \
                    if _contr7b else ""
                _company7b = str(vals.get("company_full_name") or "").strip()
                _inc7b = str(vals.get("company_incorporated") or "").strip()
                if not _inc7b:
                    # тип организации выводим из названия или пула: «LLC "PICKUP FILM", a limited
                    # liability company incorporated under the laws of …» — как в подлинных договорах
                    _ct7b = str(vals.get("company_type") or "").strip()
                    if not _ct7b:
                        _nm7c = _company7b.upper()
                        if "PJSC" in _nm7c or "PUBLIC JOINT" in _nm7c:
                            _ct7b = "public joint-stock company"
                        elif "JSC" in _nm7c or "JOINT-STOCK" in _nm7c or "AO " in _nm7c:
                            _ct7b = "joint-stock company"
                        elif "INC" in _nm7c or "CORP" in _nm7c:
                            _ct7b = "corporation"
                        else:
                            _ct7b = "limited liability company"
                    _inc7b = "a %s" % _ct7b if not _ct7b.lower().startswith("a ") else _ct7b
                _laws7b = str(vals.get("company_laws") or "").strip() or "the Russian Federation"
                # страна в адресе не должна задваиваться («Moscow, Russia, Russia»)
                # Адрес в английском договоре — латиницей: русский адрес пула
                # («г. Москва, вн.тер. г. …») в документе на английском недопустим.
                _lat8 = str(vals.get("company_registered_address") or "").strip()
                if _lat8 and not re.search(r"[\u0400-\u04ff]", _lat8):
                    _addr7b = _lat8
                    if not any(x.lower() in _addr7b.lower() for x in ("russia", "russian")):
                        _addr7b = "%s, %s" % (_addr7b, vals.get("company_country") or "Russia")
                    _addr_parts8 = []
                    _skip_addr8 = True
                else:
                    _skip_addr8 = False
                _addr_parts8 = []
                for _p8 in (vals.get("company_address_1"), vals.get("company_address_2")):
                    _s8 = str(_p8 or "").strip()
                    if not _s8:
                        continue
                    if _addr_parts8 and _s8.lower() == _addr_parts8[-1].lower():
                        continue
                    if any(_s8.lower() in (x.lower(), x.lower() + " ") or x.lower() in _s8.lower()
                           for x in ("Russia", "Russian Federation")):
                        _country_in_addr8 = True
                    _addr_parts8.append(_s8)
                if not _skip_addr8:
                    _addr7b = ", ".join(_addr_parts8)
                    if _addr7b and not any(x.lower() in _addr7b.lower() for x in ("russia", "russian")):
                        _addr7b = "%s, %s" % (_addr7b, vals.get("company_country") or "Russia")
                _req7b = [x for x in (
                    ("INN: %s" % (str(_rec7.get("inn") or "").strip())) if str(_rec7.get("inn") or "").strip() else "",
                    ("KPP: %s" % (str(_rec7.get("kpp") or "").strip())) if str(_rec7.get("kpp") or "").strip() else "",
                    ("OGRN: %s" % (str(_rec7.get("ogrn") or "").strip())) if str(_rec7.get("ogrn") or "").strip() else "",
                ) if x]
                if _req7b:
                    vals["inn_kpp_ogrn"] = ", ".join(_req7b)
                    vals["inn_ogrn_line"] = " | ".join(_req7b)
                _comp7b = [x for x in (
                    _company7b,
                    _inc7b or "a company",
                    ("incorporated under the laws of %s" % _laws7b),
                    ("with registered address at %s" % _addr7b) if _addr7b else "",
                ) if x]
                vals["company_block"] = (", ".join(_comp7b) + ', (hereinafter referred to as the "Company")') \
                    if _comp7b else ""
                if not str(vals.get("company_registered_address") or "").strip() and _addr7b:
                    vals["company_registered_address"] = _addr7b
            except Exception:
                pass
            # оклад работника по контракту — ТА ЖЕ сумма, что в договоре: берём из пула окладов,
            # карточка/ручные значения используются только если пула нет.
            try:
                from services import salary_pool as _salp3
                _row3 = _salp3.pick(app_id=_az7, client_id=_cl7.get("id")) or {}
                _m3 = int(_row3.get("monthly") or 0)
            except Exception:
                _m3 = 0
            vals["base_salary"] = ("{:,.0f}".format(_m3) if _m3 else
                                   str(vals.get("salary") or vals.get("salary_amount")
                                       or vals.get("contract_salary") or "").strip())
            # сумма из карточки приходит как «600000.00» — печатаем как в подлинниках:
            # «600,000» (без копеек, с разделителем тысяч)
            try:
                _bs9 = vals["base_salary"].replace(" ", "").replace("\u00a0", "")
                if re.fullmatch(r"\d+(?:[.,]\d+)?", _bs9):
                    vals["base_salary"] = "{:,.0f}".format(float(_bs9.replace(",", ".")))
            except Exception:
                pass
            # Нет суммы в заявке — берём правдоподобную из истории договоров (архив окладов),
            # чтобы документ проходил проверку и сходился с датами и должностью.
            try:
                if not vals["base_salary"]:
                    from services import org_pool as _op8
                    _sal8 = _op8.salary_for(profession=str(vals.get("position_title") or _cl7.get("position") or ""),
                                            app_id=_az7) or {}
                    if _sal8.get("monthly"):
                        vals["base_salary"] = "{:,.0f}".format(float(_sal8["monthly"]))
                        vals["base_salary_annual"] = "{:,.0f}".format(float(_sal8["annual"] or _sal8["monthly"] * 12))
            except Exception:
                pass
            # Сроки договора: он уже действует сегодня и заключён на пять лет.
            try:
                if not str(vals.get("term_start_date") or "").strip() or not str(vals.get("term_end_date") or "").strip():
                    from services import org_pool as _op9
                    _tm9 = _op9.term_dates(app_id=_az7, start=str(vals.get("contract_date") or ""))
                    vals.setdefault("term_start_date", _tm9["start"])
                    vals.setdefault("term_end_date", _tm9["end"])
                    if not str(vals.get("contract_date") or "").strip():
                        vals["contract_date"] = _tm9["start"]
            except Exception:
                pass
    except Exception:
        pass

    # Законы страны печатаем полным названием, как в подлинных договорах: «incorporated
    # under the laws of the Russian Federation», а не «of Russia»; и в п. «Governing Law»
    # храним только название страны, чтобы шаблон сам ставил оборот «the laws of …».
    try:
        _cb9 = str(vals.get("company_block") or "")
        if _cb9:
            vals["company_block"] = re.sub(r"the laws of Russia\b(?!n)",
                                           "the laws of the Russian Federation", _cb9)
        _lw9 = str(vals.get("governing_law") or "").strip()
        for _pref9 in ("the laws of ", "laws of "):
            if _lw9.lower().startswith(_pref9):
                _lw9 = _lw9[len(_pref9):].strip()
        if not _lw9 or _lw9.lower() in ("russia", "russian federation", "the russian federation"):
            _lw9 = "the Russian Federation"
        vals["governing_law"] = _lw9
    except Exception:
        pass

    # Одна организация на всю заявку: если клиент работает в организации «по текущий
    # момент», она должна совпадать в резюме, в договоре (№11) и в контракте (№18).
    try:
        _az8 = kwargs.get("app_id")
        if _az8 is None and len(args) > 3:
            _az8 = args[3]
        _org8 = _org_for_application(client or {}, _az8, vals)
        if _org8:
            # Документы комплекта — на английском. Русское название организации
            # («ООО «Медиа Дайджест»») приводим к латинице в том же виде, что и в
            # договоре: «Media Daydzhest LLC». Иначе резюме и договор называют
            # работодателя по-разному, и проверка считает это расхождением.
            if re.search(r"[\u0400-\u04ff]", str(_org8)):
                try:
                    from bot.ai_parser import translit_ru as _tr8
                    _lat8 = re.sub(r"^\s*(OOO|OAO|ZAO|IP)\s*", "",
                                   _tr8(str(_org8))).strip().strip('"\u00ab\u00bb')
                    _lat8 = re.sub(r"\s+", " ", _lat8).strip()
                    if _lat8:
                        _org8 = _lat8 if _lat8.endswith("LLC") else _lat8 + " LLC"
                except Exception:
                    pass
            vals["cv_job1_company"] = _org8
            _sum8 = str(vals.get("cv_summary") or "")
            if _sum8:
                vals["cv_summary"] = _sum8.replace("for a Russian company", "for %s" % _org8)
    except Exception:
        pass

    # Последнее слово — за комментарием заявки: перечень услуг договора берём из той
    # профессии, что указана в заявке. Иначе в шаблон уходит описание прежней профессии
    # (оно теперь переменная {{services_list}}), и оно расходится с должностью в шапке.
    try:
        import os as _os2
        from services import brief_values as _bvz
        try:
            _tz = args[1] if len(args) > 1 else kwargs.get("tpl_code")
        except Exception:
            _tz = kwargs.get("tpl_code")
        _az = kwargs.get("app_id")
        if _az is None and len(args) > 3:
            _az = args[3]
        _bz = str((args[2] if len(args) > 2 and isinstance(args[2], dict) else kwargs.get("doc_values")
                   or {}).get("brief") or "").strip() or _bvz.read_brief(_az)
        _rz, _ez = _bvz.parse_position(_bz)
        _codez = (_bvz.profession_code(_rz, _ez) if hasattr(_bvz, "profession_code") else "") or ""
        if not _codez and (_rz or _ez):
            from services import cv_gen as _cvz2
            _codez = (_cvz2.resolve_profession({"position": _ez or _rz,
                                                "profession": _ez or _rz}) or {}).get("code") or ""
        if _codez and _tz and is_contract_template(_tz):
            _pz = _os2.path.join(_os2.path.dirname(_os2.path.dirname(_os2.path.abspath(__file__))),
                                 "data", "cv_positions.json")
            _recs = json.loads(open(_pz, encoding="utf-8").read())
            if isinstance(_recs, dict):
                _recs = _recs.get("positions") or _recs.get("items") or \
                    [v for v in _recs.values() if isinstance(v, dict)]
            _rec = next((r for r in _recs if isinstance(r, dict) and r.get("code") == _codez), None) or {}
            _bkz = (_rec.get("blocks") or {})
            _lz = [str(_bkz.get(k) or "").strip() for k in ("short", "medium")
                   if str(_bkz.get(k) or "").strip()]
            if _lz:
                vals["services_list"] = "".join('<div class="svc-item">\u25cf %s</div>' % t
                                                for t in _lz)
    except Exception:
        pass

    # --- Форма E-02: доводим поля до состояния настоящего бланка ---
    try:
        _cli = (locals().get("_cl") or locals().get("client") or {})
        _tc = ""
        try:
            _tc = str(args[1] if len(args) > 1 else (kwargs.get("tpl_code") or kwargs.get("code") or ""))
        except Exception:
            _tc = ""
        # форма E-02 узнаётся по своим полям-подписям (purpose/guarantor есть только в ней)
        if "e02" in _tc or "statement_letter" in _tc or "purpose_of_application" in vals:
            # Формат настоящего бланка: «USSR, 15-04-1973» — страна и дата через дефис.
            _pl = str(vals.get("place_of_birth") or "").strip()
            _bd = str(vals.get("birth_date") or "").strip()
            _country = "USSR" if "USSR" in _pl.upper() else ("RUSSIA" if _pl else "")
            _bd_dash = _bd.replace(".", "-")
            if _country or _bd_dash:
                vals["place_date_of_birth"] = ", ".join(x for x in (_country, _bd_dash) if x)
            # в бланке стоит адрес пребывания В ИНДОНЕЗИИ, а не российский
            _ind = str((_cli or {}).get("address_in_indonesia") or "").strip()
            if _ind:
                # в бланке строка одна — печатаем адрес компактно
                # в бланке одна строка: убираем служебные части адреса, чтобы влезал целиком
                _short = (_ind.replace("Kec. ", "").replace("Kabupaten ", "")
                              .replace("Kab. ", "").replace("Kecamatan ", "")
                              .replace("Kuta Utara, ", "").replace("Kuta Utara ", ""))
                _short = _short.replace(", ,", ",").replace(" ,", ",")
                import re as _re5
                _short = _re5.sub(r"\s{2,}", " ", _short).strip(" ,").upper()
                if not _short.startswith("JL"):
                    _short = "JL. " + _short.lstrip(". ")
                vals["address_in_indonesia"] = _short
            # в подписанных бланках гражданство печатают как «RUSIA»
            vals["nationality"] = "RUSIA"
            # гарант по E-02 — принимающая сторона (как в настоящем бланке)
            # пустые строки в бланке помечают дефисом, как в подписанных образцах
            for _k in ("guarantor", "occupation"):
                vals[_k] = str(vals.get(_k) or "").strip() or "-"
            # почта в бланке — логин капсом
            if vals.get("email"):
                vals["email"] = str(vals["email"]).upper()
            # назначение обращения — по продукту заявки
            _purpose = str(vals.get("purpose_of_application") or "").upper()
            if "E33G" in _purpose or not _purpose:
                vals["purpose_of_application"] = "VISA BRIDGING TO E33G"
                vals["stay_permit_to_be_applied_for"] = "BRIDGE"
            # Обе строки берутся из документа ITK клиента (services/itk_doc.py):
            # PERMIT NUMBER → Stay Permit Number, STAY PERMIT EXPIRY → срок в Existing Stay Permit.
            try:
                from services.itk_doc import itk_data as _itkf
                _itk = _itkf(client_id) or {}
            except Exception:
                _itk = {}
            _permit_no = str(_itk.get("permit_no") or vals.get("stay_permit_no") or "").strip()
            vals["stay_permit_no"] = _permit_no or "-"
            _permit_exp = str(_itk.get("permit_expiry") or "").strip()
            if _permit_exp:
                vals["existing_stay_permit"] = ("VISIT STAY PERMIT (ITK), VALID UNTIL %s"
                                                % _permit_exp.replace("/", "-"))
            else:
                vals["existing_stay_permit"] = str(
                    vals.get("existing_stay_permit") or "").strip() or "-"
    except Exception:
        pass

    # ЕДИНЫЙ ДОХОД: в договоре, трудовом контракте и легенде — одна и та же сумма.
    # Правило заказчика: отталкиваемся от договора, порог берём с запасом (курс каждый раз
    # не считаем), округляем вверх — неровные значения допустимы.
    try:
        from services import requirements as _rq
        _need_usd = 0
        _cl_pid = (_cl or {}).get("product_id")
        if _cl_pid:
            for _code, _spec in (_rq.PRODUCTS or {}).items():
                if int(_spec.get("product_id") or 0) == int(_cl_pid):
                    _need_usd = int(_spec.get("min_annual_usd") or 0)
                    break
        if not _need_usd and _cl_pid:
            _spec = _rq.for_product(_rq.code_of(int(_cl_pid))) if hasattr(_rq, "code_of") else None
            _need_usd = int((_spec or {}).get("min_annual_usd") or 0)
        # Порог годового дохода для рабочего KITAS/E33G — 60 000 USD. Если продукт заявки
        # не определился, но документ содержит сумму дохода, всё равно поднимаем её с запасом
        # (иначе сумма стоит впритык к порогу и не проходит проверку).
        if not _need_usd and (_digits(vals.get("annual_amount_numeric")) or _digits(vals.get("monthly_amount_numeric"))):
            _need_usd = 60000
        if _need_usd:
            _year = float(_need_usd) * 100.0 * 1.30
            _year = float(int(_year / 50000 + 1) * 50000)
            _month = float(int(_year / 12 / 1000 + 1) * 1000)
            vals["annual_amount_numeric"] = "{:,.0f}".format(_year)
            vals["monthly_amount_numeric"] = "{:,.0f}".format(_month)
            vals["base_salary"] = "{:,.0f}".format(_month)
            vals["salary"] = "{:,.0f}".format(_month)
            vals["annual_amount_words"] = _num2words_en(int(_year)).title()
            vals["monthly_amount_words"] = _num2words_en(int(_month)).title()
    except Exception:
        pass
    # ЕДИНАЯ СУММА НА ВЕСЬ ПАКЕТ: источник — пул окладов (data/salary_pool.json),
    # ту же пару цифр показывает договор (pick — та же функция, что в договоре).
    try:
        from services import salary_pool as _salp2
        _row2 = _salp2.pick(app_id=app_id, client_id=client_id) or {}
        _a2, _m2 = int(_row2.get("annual") or 0), int(_row2.get("monthly") or 0)
        if _a2 and _m2:
            vals["annual_amount_numeric"] = "{:,.0f}".format(_a2)
            vals["monthly_amount_numeric"] = "{:,.0f}".format(_m2)
            vals["annual_amount_words"] = _salp2.words_en(_a2)
            vals["monthly_amount_words"] = _salp2.words_en(_m2)
            vals["amount_per_year"] = vals["annual_amount_numeric"]
            vals["amount_per_month"] = vals["monthly_amount_numeric"]
            vals["base_salary"] = vals["monthly_amount_numeric"]
            vals["salary"] = vals["monthly_amount_numeric"]
            vals["salary_year"] = vals["annual_amount_numeric"]
            vals["salary_month"] = vals["monthly_amount_numeric"]
    except Exception:
        pass
    return vals


# ─── Правила дат и должности (согласовано с менеджером 05.10.2026) ───────────────────

def _with_article(name: str) -> str:
    """Артикль по первой букве: «an IT Specialist», «an Administrative Assistant», «a Sales Manager»."""
    value = str(name or "").strip()
    if not value:
        return ""
    return ("an " if value[:1].lower() in "aeiou" else "a ") + value


def _add_months_back(day, months: int):
    """Сдвиг даты назад на months месяцев с сохранением числа, насколько это возможно."""
    import calendar as _cal
    y, m = day.year, day.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return day.replace(year=y, month=m, day=min(day.day, _cal.monthrange(y, m)[1]))


def _client_position(client, vals=None) -> str:
    """Профессия/должность клиента: панель → карточка → документы клиента → пул профессий.

    Одна и та же на весь комплект документов: в договоре должна совпадать с резюме.
    """
    vals = vals or {}
    for raw in (vals.get("position_title"), vals.get("position"),
                (client or {}).get("position"), (client or {}).get("job_title")):
        text = str(raw or "").strip()
        if text and text.lower() not in ("none", "null", "-"):
            return text
    # Пул должностей: если ни заявка, ни карточка, ни документы должность не дали —
    # берём подходящую из пула (распоряжение заказчика), а не оставляем пусто.
    try:
        import json as _json2
        from pathlib import Path as _P2
        _pool_path = _P2("/opt/wolf_v2/data/positions_pool.json")
        if _pool_path.exists():
            _items = (_json2.loads(_pool_path.read_text(encoding="utf-8")) or {}).get("roles") or []
            _bad = ("of fashion", "performs", "spare part")
            _clean = [i.get("title", "").strip() for i in _items
                      if i.get("title") and not any(b in i.get("title", "").lower() for b in _bad)]
            _prefer = ("manager", "designer", "specialist", "producer", "consultant", "creator")
            for _t in sorted(_clean, key=lambda x: (not any(k in x.lower() for k in _prefer), -len(x))):
                if 2 < len(_t) < 40:
                    return _t
    except Exception:
        pass
    try:
        from services import cv_gen
        prof = cv_gen.resolve_profession(client or {}) or {}
        title = str(prof.get("title") or "").strip()
        if title:
            return title
        code = str(prof.get("code") or "").strip() or "admin_assistant"
        import json as _json
        from pathlib import Path as _P
        pool = _json.loads(_P("/opt/wolf_v2/data/cv_positions.json").read_text(encoding="utf-8"))
        items = pool if isinstance(pool, list) else (pool.get("positions") or [])
        for item in items:
            if isinstance(item, dict) and item.get("code") == code:
                return str(item.get("en") or item.get("ru") or "").strip()
    except Exception:
        pass
    return ""


def _manual_contract_date(doc_values) -> "object":
    """Дата договора, введённая вручную в панели переменных (если есть)."""
    import datetime as _dt
    for raw in ((doc_values or {}).get("agreement_date"), (doc_values or {}).get("contract_date")):
        text = str(raw).strip() if raw else ""
        if not text:
            continue
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%d %B %Y", "%d %B %Y"):
            try:
                return _dt.datetime.strptime(text, fmt).date()
            except Exception:
                continue
    return None


def _app_base_date(doc_values=None, client=None):
    """Дата, от которой считаются все документные даты.

    Правило заказчика («подписание 5–7 дней назад») считается от даты ПОДАЧИ заявки, а не
    от текущего дня. Для заявки, поданной в прошлом, отсчёт от сегодня даёт дату, которой в
    момент подачи не существовало: письмо в иммиграцию и договор получали даты из будущего
    относительно подачи. Если заявка неизвестна (ручная сборка) — берём сегодня.
    """
    import datetime as _dt
    import sqlite3
    app_id = 0
    try:
        app_id = int((doc_values or {}).get("_app_id") or 0)
    except Exception:      # noqa: BLE001
        app_id = 0
    if app_id:
        try:
            con = sqlite3.connect("/opt/wolf_v2/data/wolf.db", timeout=20)
            row = con.execute("SELECT created_at FROM applications WHERE id=?", (app_id,)).fetchone()
            con.close()
            if row and row[0]:
                base = _dt.datetime.fromisoformat(str(row[0])[:19]).date()
                if base <= _dt.date.today():
                    return base
        except Exception:      # noqa: BLE001
            pass
    return _dt.date.today()


def _contract_dates(doc_values=None, client=None, manual=None) -> dict:
    """Даты договора по правилу заказчика.

    Подписание — 5–7 дней назад от сегодня, месяц и год текущие (документ уже подписан);
    начало срока — год или два назад (случайно), месяц сдвинут на 1–3 месяца назад;
    окончание — всегда ровно начало + 5 лет, поэтому пара сходится при любом годе начала.
    Значение из панели переменных отменяет расчёт целиком.
    """
    import datetime as _dt
    import random as _rnd
    manual = manual or _manual_contract_date(doc_values)
    # Отсчёт — от даты подачи заявки, а не от сегодняшнего дня: прошедшая заявка не должна
    # получать договор, подписанный уже после подачи.
    today = _app_base_date(doc_values, client)
    # Даты, уже рассчитанные при первой сборке, переиспользуем: иначе каждое
    # обновление страницы или пересборка сдвигали подписание и начало срока —
    # документ «переписывался» сам по себе.
    _kept = {k: str((doc_values or {}).get(k) or "").strip()
             for k in ("agreement_date", "term_start_date", "term_end_date")}
    if all(_kept.values()) and not manual:
        return _kept
    # Смещения считаем детерминированно — от клиента/заявки, а не от случайного числа:
    # иначе при каждой пересборке договор получал новые даты подписания и начала срока.
    _seed = 0
    try:
        _seed = int((client or {}).get("id") or 0) * 1000 + int((doc_values or {}).get("_app_id")
                                                               or (client or {}).get("application_id") or 0)
    except Exception:
        _seed = 0
    _rnd = _rnd.Random(_seed or 7)
    if manual:
        signed = start = manual
    else:
        # Подписание — не сегодняшнее число: 5–7 дней назад, месяц и год текущие.
        signed = today - _dt.timedelta(days=_rnd.randint(5, 7))
        # Начало срока — год или два назад (случайно), месяц сдвинут на 1–3 месяца назад.
        start = _add_months_back(today.replace(year=today.year - _rnd.randint(1, 2)), _rnd.randint(1, 3))
    return {"agreement_date": _fmt_date_uk(str(signed)),
            "term_start_date": _fmt_date_uk(str(start)),
            "term_end_date": _fmt_date_uk(str(start.replace(year=start.year + 5)))}


def _fmt_dotted(value):
    """Дата в формате ДД.ММ.ГГГГ — так срок действия паспорта печатается в договоре."""
    import datetime as _dt
    s = str(value or "").strip()
    if not s:
        return ""
    for f in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(s, f).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return s

_ORG_FOR_APP_CACHE = {}


def _org_for_application(client: dict, app_id, vals: dict) -> str:
    """Организация заявки — один источник для всех документов.

    Порядок (правило заказчика 07.10.2026):
      1) организация из заявки — комментарий/бриф заявки, карточка клиента, данные договора;
      2) организации в заявке нет — подбор по виду деятельности должности из пула
         (Москва и Санкт-Петербург, независимо от города проживания клиента);
      3) вида деятельности нет — вид выбирается из пула, затем организация.
    Выбор запоминается по заявке: во всех документах комплекта — одна организация.
    """
    import json as _json8

    if app_id and str(app_id) in _ORG_FOR_APP_CACHE:
        return _ORG_FOR_APP_CACHE[str(app_id)]

    def _clean8(s8: str) -> str:
        # кавычки в названии организации значимы: «LLC "PICKUP FILM"» печатается как есть
        s8 = str(s8 or "").strip()
        if not s8:
            return ""
        up = s8.upper()
        if not any(w in up for w in ("LLC", "LTD", "LLP", "INC", "CORP", "ООО", "ОАО", "ЗАО")):
            if len(s8.split()) < 2:
                return ""
        return s8

    def _remember(app, value):
        """Одна организация на всю заявку: запоминаем выбор и переиспользуем."""
        if app:
            _ORG_FOR_APP_CACHE[str(app)] = value
        return value

    # 1) Организация из самой заявки: комментарий/бриф заявки — что клиент написал.
    try:
        from services import brief_values as _bv8b
        _brief8b = _bv8b.read_brief(app_id) if app_id else ""
        if _brief8b:
            rec8b = _bv8b.pick_employer_by_sphere(_brief8b) or {}
            c = _clean8(rec8b.get("name") or rec8b.get("legal_name") or "")
            if c:
                return _remember(app_id, c)
    except Exception:
        pass
    # 2) Организация из карточки клиента (админ заполнил) или из данных заявки.
    cand = [_clean8(client.get("company_name")), _clean8(client.get("company_llc")),
            _clean8(client.get("employer_name"))]
    for c in cand:
        if c:
            return _remember(app_id, c)
    # 3) Организация, уже проставленная в договоре этой заявки (документ №11).
    try:
        if app_id:
            row = db.q1("""SELECT ad.values_json FROM application_documents ad
                             JOIN templates t ON t.id = ad.template_id
                            WHERE ad.application_id=? AND t.doc_index=11
                            ORDER BY ad.id DESC LIMIT 1""", (int(app_id),))
            dv = _json8.loads((row or {}).get("values_json") or "{}")
            c = _clean8(dv.get("company_name_in_quotes") or dv.get("company_name") or "")
            if c:
                return _remember(app_id, c)
    except Exception:
        pass
    try:
        # Подбор «по смыслу»: по должности клиента — организация из нужной сферы
        # с правдоподобными реквизитами (единый пул организаций).
        from services import org_pool as _op8
        rec8 = _op8.pick_for(profession=str(client.get("position") or client.get("profession") or ""),
                             city=str(client.get("city") or ""), app_id=app_id) or {}
        c = _clean8(rec8.get("name") or rec8.get("legal_name") or "")
        if c:
            return _remember(app_id, c)
    except Exception:
        pass
    try:
        from services import employer_pool as _emp8
        rec = _emp8.pick(app_id=int(app_id or 0), client_id=client.get("id")) or {}
        c = _clean8(rec.get("name") or rec.get("legal_name") or "")
        if c:
            return _remember(app_id, c)
    except Exception:
        pass
    return _remember(app_id, _clean8(vals.get("company_name_in_quotes")))
