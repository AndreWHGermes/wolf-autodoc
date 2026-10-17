"""Единый рендер документа Wolf AutoDoc.

Правило проекта: документ собирается ОДНИМ кодом — конструктор, карточка заявки,
Telegram-бот и автоподготовка вызывают только этот модуль. Дублирование логики
подстановки приводило к расхождениям визоров и «поехавшим» значениям.

Пять сущностей документа: архив → размеченный образец → HTML-шаблон →
HTML с данными клиента → PDF.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

try:            # пути — из конфигурации приложения: у v1 и v2 свои базы и шаблоны
    from core.config import DB_PATH as _CFG_DB, HTML_DIR as _CFG_HTML, RENDER_DIR as _CFG_RENDER
    DB_PATH = str(_CFG_DB)
    TPL_DIR = Path(_CFG_HTML)
    RENDER_DIR = Path(_CFG_RENDER)
except Exception:
    DB_PATH = '/opt/wolf_v2/data/wolf.db'
    TPL_DIR = Path('/opt/wolf_v2/data/templates')
    RENDER_DIR = Path('/opt/wolf_v2/data/renders')
OPTIONAL_RE = re.compile(r'<!--optional-->(.*?)<!--/optional-->', re.S)
_VAR_IN = re.compile(r'\{\{\s*([a-zA-Z_]\w*)\s*\}\}')


def _drop_empty_optional(html: str, values: dict) -> str:
    """Необязательные строки (реквизиты и т. п.): если все их значения пустые — строку убираем.

    Так документ выглядит как реальный образец, когда данных нет,
    и содержит реквизиты, когда они есть.
    """
    def repl(m):
        body = m.group(1)
        names = _VAR_IN.findall(body)
        if names and all(not str(values.get(n) or '').strip() for n in names):
            return ''
        return body
    return OPTIONAL_RE.sub(repl, html)


_LONE_PUNCT = re.compile(r"(?:&nbsp;|&#160;|[ \t\u00a0\u2009\u202f])+([.,;:])")
# случай на границе тегов: «{{ var }}<b> ,</b>» — переменная пустая, от неё
# остаётся пробел перед запятой уже внутри разметки, до неё _LONE_PUNCT не достаёт
_PUNCT_AFTER_TAG = re.compile(r">[ \t\u00a0]+([.,;:])")
# знак препинания может оказаться и на новой строке: «…\n,» — из-за переноса
# в шаблоне после пустой переменной
_LONE_PUNCT_NL = re.compile(r"[ \t]*\n[ \t]*([.,;:])")


def _tidy_punct(html: str) -> str:
    """«SURKOV VITALII , 08.10.2026» → «SURKOV VITALII, 08.10.2026».

    Когда переменная в шаблоне пустая, от неё остаётся пробел перед знаком
    препинания: «{{ contract_place }},» превращается в « ,». В готовом
    документе такой мусор выглядит как брак вёрстки, поэтому убираем его,
    не трогая текст внутри тегов.
    """
    parts = re.split(r"(<[^>]*>)", html)
    for i, p in enumerate(parts):
        if p and not p.startswith("<"):
            p = _LONE_PUNCT_NL.sub(r"\1", p)
            parts[i] = _PUNCT_AFTER_TAG.sub(r">\1", _LONE_PUNCT.sub(r"\1", p))
    joined = "".join(parts)
    # Пустой span (значение не подставилось) оставляет после себя пробел перед
    # знаком препинания: «position of <span></span>, and». Убираем оболочку
    # целиком, иначе пробел и запятая оказываются по разные стороны от тегов
    # и покусочная чистка до них не добирается.
    joined = re.sub(r"<span\b[^>]*>(?:\s|&nbsp;)*</span>", "", joined, flags=re.I)
    # Последний проход по целому документу: пробел перед запятой возникает и на
    # стыке частей — «in the position of {{ post }}, and» при пустой переменной
    # даёт «of , and», до этого места покусочная чистка не достаёт.
    return _LONE_PUNCT.sub(r"\1", joined)


VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# какие поля карточки клиента подставляются в одноимённые переменные
CLIENT_MAP = {
    'client_name': 'full_name_latin',
    'full_name_latin': 'full_name_latin',
    'surname': None,  # вычисляется
    'address_live': 'address_live',
    'passport_no': 'passport_number',
    'passport_number': 'passport_number',
    'date_of_birth': 'date_of_birth',
    'nationality': 'nationality',
    'place_of_birth': 'place_of_birth',
    'email': 'email',
    'phone': 'phone',
    # банковские реквизиты — только из карточки клиента (номер карты маскируется при подстановке)
    'card_mask': 'card_mask',
    'ref_no': 'ref_no',
    'account_no': 'account_no',
    'contract_no': 'contract_no',
    'bank_name': 'bank_name',
}


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def load_template(template_id: int | None = None, code: str | None = None) -> dict:
    """Шаблон из БД + его HTML."""
    c = connect()
    try:
        if template_id:
            row = c.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        else:
            row = c.execute("SELECT * FROM templates WHERE code=?", (code,)).fetchone()
        if not row:
            raise LookupError(f'шаблон не найден: id={template_id} code={code}')
        tpl = dict(row)
    finally:
        c.close()
    path = Path(tpl['html_path']) if tpl.get('html_path') else TPL_DIR / tpl['code'] / 'template.html'
    if not path.exists():
        raise FileNotFoundError(f'HTML шаблона не найден: {path}')
    tpl['_html'] = path.read_text(encoding='utf-8')
    tpl['_dir'] = str(path.parent)
    return tpl


def stored_values(application_id: int, template_id: int) -> dict:
    """Значения, сохранённые в карточке заявки для этого документа."""
    c = connect()
    try:
        row = c.execute("""SELECT values_json FROM application_documents
                           WHERE application_id=? AND template_id=?""",
                        (application_id, template_id)).fetchone()
        return json.loads(row['values_json'] or '{}') if row else {}
    except Exception:
        return {}
    finally:
        c.close()


def client_values(application_id: int) -> dict:
    """Значения из карточки клиента (персональные данные НЕ берём из общей истории переменных)."""
    c = connect()
    try:
        app = c.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
        if not app:
            return {}
        cl = c.execute("SELECT * FROM clients WHERE id=?", (app['client_id'],)).fetchone()
        if not cl:
            return {}
        cl = dict(cl)
    finally:
        c.close()
    out = {}
    for var, col in CLIENT_MAP.items():
        if col and cl.get(col) not in (None, ''):
            out[var] = cl[col]
    full = cl.get('full_name_latin') or ''
    if full:
        out.setdefault('surname', full.split()[0] if full.split() else '')
    if cl.get('passport_issue_date'):
        out.setdefault('date_of_issue', cl['passport_issue_date'])
    app_email = None
    if app_email:
        out.setdefault('email', app_email)
    return out


def normalize(values: dict, template_code: str = '') -> dict:
    """Приведение значений к виду документа: транслит, суммы прописью, переносы строк."""
    out = {k: v for k, v in (values or {}).items() if v is not None}
    try:
        import sys
        if '/opt/wolf' not in sys.path:
            sys.path.insert(0, '/opt/wolf')
        from ai_parser import translit_ru  # type: ignore
        if 'bank_statement' in template_code:
            for k, v in list(out.items()):
                if isinstance(v, str) and any('а' <= ch.lower() <= 'я' for ch in v):
                    out[k] = translit_ru(v)
            # Сумма и пропись НЕ пересчитываются здесь: единственный источник формата —
            # services/values.py (parse_amount_any + _fmt_money + _balance_words_from),
            # иначе получаются два разных вида одной и той же строки.
    except Exception:
        pass
    # Документы пакета — англоязычные, а справочники заполнены по-русски.
    # Всё, где остались русские буквы, переводим в латинскую запись: организация —
    # «Media Service LLC», директор — «Mikhail Yu. Reshetnikov», адрес — «ul. ...».
    # Иначе в английском бланке появляется русский текст и проверка блокирует пакет.
    try:
        from services import latin as _lat
        _org_re = re.compile(r'\b(ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО|ФГУП|МУП)\b', re.IGNORECASE)
        _fio_re = re.compile(r'[А-ЯЁ][а-яё\-]+ [А-ЯЁ][а-яё\-]+(?: [А-ЯЁ][а-яё\-]+)?')
        for k, v in list(out.items()):
            if not isinstance(v, str) or not _lat.has_cyrillic(v):
                continue
            if _org_re.search(v):
                out[k] = _lat.org_name(v)
            elif 'address' in k.lower() or 'addr' in k.lower():
                out[k] = _lat.address(v)
            elif _fio_re.fullmatch(v.strip()):
                out[k] = _lat.person(v)
            else:
                out[k] = _lat.value(v)
    except Exception:
        pass
    for k, v in list(out.items()):
        if isinstance(v, str):
            # поля-пункты (…_bullets) печатаем списком: каждая строка — свой пункт
            # с отступом и маркером, как в оригинале документа
            if k.endswith('_bullets') and '\n' in v:
                out[k] = ''.join(
                    '<div class="it">%s</div>' % ln.strip()
                    for ln in v.replace('\r\n', '\n').split('\n') if ln.strip())
            else:
                out[k] = v.replace('\r\n', '\n').replace('\n', '<br>')
    return _normalize_doc_values(out)


def _normalize_doc_values(out: dict) -> dict:
    # ФИО в резюме — «Tovpeko Egor Artemovich»: первая заглавная, остальные
    # строчные. Транслитерация приводила всё к ВЕРХНЕМУ регистру (Андрей, 17.10.2026).
    try:
        _cn = str(out.get("cv_name") or "").strip()
        if _cn:
            out["cv_name"] = " ".join(w.capitalize() for w in _cn.split())
    except Exception:
        pass
    """Единая доводка значений перед подстановкой в шаблон.

    Здесь правятся две вещи, которые раньше доходили до документа как есть:
    оборот о законах страны («laws of Russia» → «laws of the Russian Federation»)
    и форма записи оклада из карточки («600000.00» → «600,000»).
    """
    import re as _re
    # Пропись суммы приходит из разных источников то со скобками, то без, а шаблон
    # ставит скобки сам («… rubles ({{ balance_words }})»). Внешние скобки снимаем,
    # иначе в документе выходит «((one million … kopeks))».
    for _kw, _vw in list(out.items()):
        if any(x in str(_kw).lower() for x in ("words", "spelled")) and isinstance(_vw, str):
            _sw = _vw.strip()
            if _sw.startswith("(") and _sw.endswith(")") and _sw.count("(") == 1:
                out[_kw] = _sw[1:-1].strip()
    # Составные числительные в подлинниках пишутся через дефис («twenty-one»), а в
    # значениях из примеров он иногда теряется — приводим к форме банковского образца.
    _tens_w = r"(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    _ones_w = r"(one|two|three|four|five|six|seven|eight|nine)"
    for _kw, _vw in list(out.items()):
        if any(x in str(_kw).lower() for x in ("words", "spelled")) and isinstance(_vw, str):
            out[_kw] = _re.sub(r"\b%s +%s\b" % (_tens_w, _ones_w), r"\1-\2", _vw)
    try:
        _cb = str(out.get("company_block") or "")
        if _cb:
            out["company_block"] = _re.sub(r"(?i)laws of russia\b(?!n)",
                                           "laws of the Russian Federation", _cb)
        # суммы печатаем как в подлинниках: «600,000» (без копеек). Значение может прийти
        # и как «600000.00», и как «600,000.00» — под любым именем с salary/amount/sum.
        for _k9 in list(out.keys()):
            _low9 = _k9.lower()
            if any(x in _low9 for x in ("salary", "amount", "sum")) is False:
                continue
            # Пропись (…_words, …_text) и пояснения — не числа: автоформат их ломает
            # («(one million … rubles 00 kopeks)» превращалось в «(0.00 rubles kopeks)»).
            if any(x in _low9 for x in ("words", "text", "in_words", "spelled")):
                continue
            _v9 = str(out.get(_k9) or "").strip()
            if not _v9 or _v9.lower().startswith(("the ", "ru")):
                # «RUB 600,000.00» тоже допустимо — отбрасываем буквенный префикс
                _v9 = _re.sub(r"(?i)^\s*(rub|usd|eur|idr|\$|₽|€)\s*", "", _v9)
            _c9 = _re.sub(r"[^\d.,]", "", _v9)
            if not _c9:
                continue
            if "," in _c9 and "." in _c9:
                _c9 = _c9.replace(",", "")
            elif "," in _c9:
                _c9 = _c9.replace(",", "") if len(_c9.split(",")[-1]) == 3 else _c9.replace(",", ".")
            try:
                out[_k9] = "{:,.0f}".format(float(_c9))
            except Exception:
                continue
        # Остаток по счёту печатается с копейками и в английском формате: русская
        # запись «640 426,42» в англоязычной справке читается как «640 426 42»
        # (пробел-разделитель тысяч, запятая-разделитель копеек). Приводим к
        # «640,426.42» — как в документах банков на английском.
        # Остаток по счёту уже приходит из values.py в формате подлинника
        # («1 730 400,00» — пробелы и запятая перед копейками, как в справках банков).
        # Автопересчёт в английский формат ломал и сумму, и пропись: ключ balance_words
        # попадал под то же правило и превращался в «(0.00 rubles kopeks)».
        for _kb in list(out.keys()):
            _low_kb = _kb.lower()
            if not any(x in _low_kb for x in ("balance", "deposit", "остаток", "balance_rub")):
                continue
            if any(x in _low_kb for x in ("words", "text", "spelled")):
                continue
            _vb = str(out.get(_kb) or "").strip()
            if not _vb:
                continue
            # Пересчитываем ТОЛЬКО «сырое» число без форматирования (1730400.00).
            # Готовая запись подлинника («1 770 308,45» — пробелы и запятая) не трогается.
            if " " in _vb or "," in _vb:
                continue
            _nb = _re.sub(r"[^\d,.\s]", "", _vb).replace(" ", "")
            if not _nb:
                continue
            if "," in _nb and "." in _nb:
                _nb = _nb.replace(",", "")
            elif "," in _nb:
                _nb = _nb.replace(",", ".")
            try:
                out[_kb] = "{:,.2f}".format(float(_nb))
            except Exception:
                continue
        _lw = str(out.get("governing_law") or "").strip()
        for _p in ("the laws of ", "laws of "):
            if _lw.lower().startswith(_p):
                _lw = _lw[len(_p):].strip()
        if _lw:
            if _lw.lower() in ("russia", "russian federation", "the russian federation"):
                out["governing_law"] = "the Russian Federation"
            else:
                out["governing_law"] = _lw
    except Exception:
        pass
    # Русских букв в документах быть не должно. Названия организаций приходят из пула
    # кириллицей («ООО «Росгосстрах»») и печатались в англоязычном договоре как есть.
    for _k10, _v10 in list(out.items()):
        if isinstance(_v10, str):
            out[_k10] = _ascii_only(_v10)
    return out


def render_html(template_id: int | None = None, code: str | None = None,
                values: dict | None = None, html: str | None = None,
                keep_unfilled: bool = False) -> str:
    """Подставить значения в HTML шаблона. keep_unfilled=True — оставить {{ var }} как есть."""
    if html is None:
        tpl = load_template(template_id, code)
        html = tpl['_html']
        code = tpl['code']
    vals = normalize(values or {}, code or '')
    # В формах иммиграции пустое значение раньше показывали прочерком; на бланке E-02
    # этот прочерк накладывался на текст самого бланка («-» поверх «Manager»), поэтому
    # пустые поля теперь просто не печатаются — по канону пустые Occupation/Guarantor норма.
    _dash = False

    def sub(m):
        v = vals.get(m.group(1))
        if v in (None, ''):
            if _dash:
                return '-'
            return m.group(0) if keep_unfilled else ''
        s = str(v)
        # Значения из карточек/примеров приходят с ЭКРАНИРОВАННЫМИ переводами строк
        # («\n» как два символа) — без этого пункты обязанностей слипаются в строку.
        s = s.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
        return s
    return _tidy_punct(fit_width(VAR_RE.sub(sub, _drop_empty_optional(html, vals))))




# Английские названия документов — так же называются готовые файлы в папках клиентов на Google Drive
DOC_TITLES_EN = {
    "bank_statement_3m__tbank": "Bank Statement 3 months (TBank)",
    "bank_statement_3m__sber": "Bank Statement 3 months (Sberbank)",
    "bank_statement_12m__tbank": "Bank Statement 12 months (TBank)",
    "bank_statement_12m__sber": "Bank Statement 12 months (Sberbank)",
    "cv__format_short": "CV (short)",
    "cv__format_detailed": "CV (detailed)",
    # «(Sivaev)» — это имя человека из образца; в имени файла клиента ему не место
    # (нашлось при проверке уже отправленной заявки 105).
    "cv__format_sivaev": "CV",
    "d12_cover_letter__default": "D12 Cover Letter",
    "d12_statement_letter__default": "D12 Statement Letter",
    "statement_letter_e02__bridging": "Statement Letter E-02 (Bridging)",
    "statement_letter_e02__default": "Statement Letter E-02",
    "statement_letter_e02__conversion": "Statement Letter E-02 (Conversion)",
    "remote_work_agreement__default": "Remote Work Agreement",
    "employment_contract__default": "Employment Contract",
    "bridging_request_letter__default": "Bridging Request Letter",
    "bridging_request_letter__ngurahrai": "Bridging Request Letter (Ngurah Rai)",
    "bridging_request_letter__tabanan": "Bridging Request Letter (Tabanan)",
    "conversion_request_letter__default": "Conversion Request Letter",
    "conversion_request_letter__denpasar": "Conversion Request Letter (Denpasar)",
}


def doc_title_en(code: str | None, fallback: str = "") -> str:
    """Английское название документа для имени файла (по коду шаблона)."""
    if code and code in DOC_TITLES_EN:
        return DOC_TITLES_EN[code]
    return fallback or (code or "")

def doc_filename(title: str, values: dict, ext: str = ".pdf", code: str | None = None) -> str:
    """Имя готового документа: «Тип документа ФИО клиента ДД.ММ.ГГГГ.pdf».

    Так же называются сформированные справки в папках клиентов на Google Drive.
    """
    import re as _re

    def _clean(x):
        x = _re.sub(r'[\\/:*?"<>|]+', " ", str(x or ""))
        return _re.sub(r"\s+", " ", x).strip()

    _vals = values or {}
    fio = ""
    # имя файла — только латиницей: сначала берём готовую латинскую версию ФИО,
    # иначе транслитерируем кириллицу
    for k in ("full_name_latin", "client_name_latin", "cv_name", "employee_full_name_latin"):
        if _vals.get(k):
            fio = str(_vals[k]); break
    if not fio:
        for k in ("client_name", "full_name", "employee_name", "employee_full_name", "cv_name"):
            if _vals.get(k):
                fio = str(_vals[k]); break
    if fio and any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in fio):
        try:
            from bot.ai_parser import translit_ru as _tr
            fio = _tr(fio)
        except Exception:
            pass
    date = str(_vals.get("doc_date") or "").strip() or datetime.now().strftime("%d.%m.%Y")
    name = doc_title_en(code, title) if code else title
    return " ".join([x for x in (_clean(name), _clean(fio), _clean(date)) if x]) + ext

def _text_width_est(text: str, size: float, bold: bool = False) -> float:
    """Оценка ширины строки в pt для Arial/Helvetica (без шрифтового движка)."""
    narrow = "iljftr.,:;'!|()[]/ "
    wide = "mwMW@%"
    caps_digits = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    k = 0.0
    for ch in text:
        if ch in narrow:
            k += 0.30
        elif ch in wide:
            k += 0.85
        elif ch in caps_digits:
            k += 0.62
        else:
            k += 0.52
    if bold:
        k *= 1.06
    return k * size


def autofit(html: str, min_size: float = 6.0) -> str:
    """Подгонка значений под ширину блока.

    Блоки в шаблонах абсолютные и с white-space:pre: длинное значение (адрес, ФИО,
    email) вылезает за поля листа. Здесь уменьшаем кегль ТОЛЬКО у тех блоков, где
    текст шире блока; короткие значения остаются ровно того размера, что в образце.
    """
    import re as _re

    def fit(m):
        style_div, style_span, text = m.group(1), m.group(2), m.group(3)
        plain = _re.sub(r'<[^>]+>', '', text)
        if not plain.strip() or 'white-space:normal' in style_div:
            return m.group(0)
        wm = _re.search(r'width:([\d.]+)pt', style_div)
        sm = _re.search(r'font-size:([\d.]+)pt', style_span)
        if not wm or not sm:
            return m.group(0)
        box_w, size = float(wm.group(1)), float(sm.group(1))
        est = _text_width_est(plain, size, bold='bold' in style_span)
        if est <= box_w - 1.0:
            return m.group(0)
        new_size = max(min_size, round((box_w - 1.0) / est * size * 2) / 2 - 0.5)
        if new_size >= size:
            return m.group(0)
        return m.group(0).replace('font-size:%.2fpt' % size, 'font-size:%.2fpt' % new_size)

    return _re.sub(r'<div class="txt" style="([^"]*)"><span style="([^"]*)">([^<]*)</span></div>',
                   fit, html)


def hide_empty_sections(html: str) -> str:
    """Убирает пустые блоки и заголовки разделов без содержимого.

    Нужно для резюме: если опыт и образование не заполнены, вместо пустых строк
    и «висящих» заголовков WORK EXPERIENCE / EDUCATION в документе не остаётся
    ничего. Пустое место в резюме заказчик читает как дефект вёрстки.
    """
    blocks = []
    for m in re.finditer(r'<div class="txt" style="([^"]*)">(.*?)</div>', html, re.S):
        style, inner = m.group(1), m.group(2)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', inner)).strip()
        mm = re.search(r'top:\s*([\d.]+)pt', style)
        blocks.append({'start': m.start(), 'end': m.end(), 'style': style,
                       'text': text, 'top': float(mm.group(1)) if mm else 0.0})
    if not blocks:
        return html
    # порядок чтения — сверху вниз: заголовок раздела и его содержимое связаны
    # вертикальным расположением, а не порядком тегов в файле
    blocks.sort(key=lambda b: b['top'])
    heads = [i for i, b in enumerate(blocks)
             if b['text'] and 3 <= len(b['text']) <= 40
             and b['text'] == b['text'].upper() and any(c.isalpha() for c in b['text'])]
    kill = set()
    for pos, i in enumerate(heads):
        nxt = heads[pos + 1] if pos + 1 < len(heads) else len(blocks)
        content = [b for b in blocks[i + 1:nxt] if b['text']]
        if not content:
            kill.add(i)
    for i, b in enumerate(blocks):
        if i in kill or not b['text']:
            kill.add(i)
    for i in sorted(kill, key=lambda x: blocks[x]['start'], reverse=True):
        html = html[:blocks[i]['start']] + html[blocks[i]['end']:]
    # Подтягивание блоков вверх (compact_cv_gaps) не применяется: без замера высот
    # браузером перенесённые строки наезжали на следующий блок (05.10.2026).
    # Разделы с данными стоят на своих местах листа, пустые — удалены.
    return html


def compact_cv_gaps(html: str, step: float = 26.0, gap: float = 16.0) -> str:
    """Подтягивает блоки резюме вверх: провалы после удалённых пустых разделов закрываются.

    Между блоками резюме остаётся шаг не больше step; всё, что выше, считается
    пустым местом от удалённого раздела и сжимается до gap.
    """
    items = []
    for m in re.finditer(r'<div class="txt" style="([^"]*)">', html):
        mm = re.search(r'top:\s*(-?[\d.]+)pt', m.group(1))
        if mm:
            items.append({'top': float(mm.group(1)), 'sstart': m.start(1),
                          'send': m.end(1), 'style': m.group(1)})
    items.sort(key=lambda x: x['top'])
    shift = 0.0
    prev = None
    edits = []
    for it in items:
        top = it['top'] - shift
        if prev is not None and top - prev > step:
            delta = (top - prev) - gap
            shift += delta
            top -= delta
        prev = top
        if abs(it['top'] - top) > 0.5:
            edits.append((it['sstart'], it['send'],
                          re.sub(r'top\s*:\s*-?[\d.]+pt', 'top:%.2fpt' % top,
                                 it['style'], count=1)))
    for sstart, send, style in sorted(edits, key=lambda e: -e[0]):
        html = html[:sstart] + style + html[send:]
    return html


def tidy_for_pdf(html: str, code: str = "") -> str:
    """Порядок в готовом документе: никаких имён переменных и никаких выходов за лист.

    1. Всё, что осталось в шаблоне как {{ имя }}, вырезается: если значения нет,
       в документе должно быть пустое место, а не имя переменной (правило заказчика
       распространяется на все документы и бланки).
    2. Блок текста, который шире доступной ширины, переносится на следующую строку
       (white-space:normal, width до правого поля, height:auto). Если под блоком нет
       свободного места под вторую строку — кегль уменьшается ровно настолько, чтобы
       значение влезло в одну строку.
    """
    if not html:
        return html
    # 1) имена переменных в документ не попадают никогда
    html = re.sub(r'\{\{[^{}]{0,80}\}\}', '', html)

    page_w = 595.28
    right_edge = page_w - 39.28
    blocks = []
    for m in re.finditer(r'<div class="txt" style="([^"]*)">(.*?)</div>', html, re.S):
        style, inner = m.group(1), m.group(2)
        def _num(key, default=0.0):
            mm = re.search(r'%s:([\d.]+)pt' % key, style)
            return float(mm.group(1)) if mm else default
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', inner)).strip()
        # Кегль берём ОТТУДА, ГДЕ ОН ЗАДАН. В шаблонах он стоит в span, а в самом
        # контейнере его часто нет — тогда прежний код брал значение по умолчанию 10pt
        # и «подгонял» текст по неверной базе: в справках адрес клиента уезжал
        # с 8pt на 9.65, то есть форма расходилась с образцом на ровном месте.
        size_m = re.search(r'font-size:([\d.]+)pt', inner) or re.search(r'font-size:([\d.]+)pt', style)
        blocks.append({'start': m.start(), 'end': m.end(), 'style': style, 'text': text,
                       'left': _num('left'), 'top': _num('top'),
                       'width': _num('width'), 'height': _num('height'),
                       'size': float(size_m.group(1)) if size_m else 10.0,
                       'bold': 'bold' in inner,
                       'normal': 'white-space:normal' in style or 'white-space:normal' in inner})
    for i, b in enumerate(blocks):
        if not b['text'] or b['normal']:
            continue
        avail = right_edge - b['left']
        if avail <= 5:
            continue
        est = _text_width_est(b['text'], b['size'], b['bold'])
        if est <= avail + 1.0:
            continue
        # свободное место под блоком (до следующего блока по вертикали)
        nxt = min((o['top'] for o in blocks if o is not b and o['top'] > b['top'] + 0.1),
                  default=None)
        gap = (nxt - (b['top'] + max(b['height'], b['size'] * 1.1))) if nxt else 999
        if gap >= b['size'] * 1.05:
            b['new'] = (b['style'].replace('white-space:pre', 'white-space:normal')
                        + (';' if not b['style'].rstrip().endswith(';') else '')
                        + 'width:%.2fpt;height:auto' % avail)
        else:
            new_size = max(6.0, min(b['size'], b['size'] * (avail / max(est, 1.0)) - 0.05))
            if new_size < b['size'] - 0.02:
                # кегль живёт в span'ах внутри блока — уменьшать надо там
                b['resize'] = new_size
    # сначала подгонка кегля (правки внутри блока), затем замена стиля контейнера
    for b in sorted([x for x in blocks if x.get('resize')], key=lambda x: x['start'], reverse=True):
        seg = html[b['start']:b['end']]
        html = html[:b['start']] + re.sub(r'font-size:[\d.]+pt', 'font-size:%.2fpt' % b['resize'], seg) + html[b['end']:]
    for b in sorted([x for x in blocks if x.get('new')], key=lambda x: x['start'], reverse=True):
        html = html[:b['start']] + '<div class="txt" style="%s">' % b['new'] + html[html.index('>', b['start']) + 1:]
    return html


RIGHT_EDGE_PT = 556.0          # 595.28pt (A4) минус поля печати
LEFT_EDGE_PT = 40.0


def fit_width(html: str, right_edge: float = RIGHT_EDGE_PT, left_edge: float = LEFT_EDGE_PT) -> str:
    """Жёсткое правило: текст документа не выходит за поля листа.

    Блоки в шаблонах абсолютные (left/width в pt). Если блок шире доступной ширины —
    сужаем его до правого поля; если значение не влезает — переносим строку
    (white-space:normal, height:auto), а когда места под блоком нет — уменьшаем кегль
    внутри блока. Применяется к любому HTML — и к исходному документу, и к переводу:
    правило одно на все шаблоны, вручную ничего править не нужно.
    """
    if not html:
        return html
    out = []
    last = 0
    for m in re.finditer(r'<div class="txt" style="([^"]*)"([^>]*)>(.*?)</div>', html, re.S):
        style, attrs, inner = m.group(1), m.group(2), m.group(3)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', inner)).strip()
        def _num(key, default=0.0):
            mm = re.search(r'%s:([\d.]+)pt' % key, style)
            return float(mm.group(1)) if mm else default
        left, width = _num('left'), _num('width')
        if not text or width <= 0:
            continue
        size = _num('font-size', 10.0)
        bold = 'bold' in inner
        avail = right_edge - left
        new_style = style
        changed = False
        if left < left_edge - 1:
            shift = left_edge - left
            new_style = re.sub(r'left:[\d.]+pt', 'left:%.2fpt' % left_edge, new_style) if left < left_edge - 1 else new_style
            left = left_edge
            avail = right_edge - left
            changed = True
        if avail <= 20:
            out.append(html[last:m.start()]); out.append(m.group(0)); last = m.end()
            continue
        if width > avail + 0.5:
            new_style = re.sub(r'width:[\d.]+pt', 'width:%.2fpt' % avail, new_style)
            width = avail
            changed = True
        normal = 'white-space:normal' in new_style
        est = _text_width_est(text, size, bold)
        if not normal and est > width + 1.0:
            new_style = (new_style.replace('white-space:pre', 'white-space:normal')
                         + ';width:%.2fpt;height:auto' % width)
            changed = True
        elif not normal and est <= width + 1.0:
            pass
        out.append(html[last:m.start()])
        if changed:
            attrs = re.sub(r'style="[^"]*"', '', attrs)
            out.append('<div class="txt" style="%s"%s>%s</div>' % (new_style, attrs, inner))
        else:
            out.append(m.group(0))
        last = m.end()
    out.append(html[last:])
    return ''.join(out)


def render_pdf(html: str, base_dir: str | None = None, out_path: str | Path | None = None) -> Path:
    """HTML → PDF (weasyprint). Собираем из строки — без временных HTML на диске."""
    import weasyprint
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        out_path = RENDER_DIR / f"doc_{datetime.now():%Y%m%d_%H%M%S_%f}.pdf"
    out_path = Path(out_path)
    # Порядок в документе: вырезаем оставшиеся имена переменных и разводим
    # текст, который не влезает в строку (перенос вниз либо подгонка кегля).
    html = tidy_for_pdf(html)
    # html = autofit(html)  # отключено: заказчик требует ОДИН размер шрифта у всех значений
    # картинки шаблонов лежат в статике (/static/tpl_assets/…) — weasyprint по таким адресам
    # не ходит, поэтому подставляем путь к файлам на диске
    assets = str(Path(__file__).resolve().parent.parent / 'blocks' / 'static' / 'tpl_assets') + '/'
    html = html.replace('/static/tpl_assets/', assets)
    base = str(base_dir or Path(__file__).resolve().parent.parent)
    if not base.startswith('file://'):
        base = 'file://' + str(Path(base).resolve()) + '/'
    weasyprint.HTML(string=html, base_url=base).write_pdf(str(out_path))
    return out_path


def warm_up() -> None:
    """Прогрев weasyprint при старте сервиса.

    Первый сбор PDF в свежем процессе стоит ~1.5 с: импорт weasyprint и первичный подбор
    шрифтов. При прогреве первый запрос пользователя идёт ~0.3 с.
    """
    try:
        import weasyprint
        RENDER_DIR.mkdir(parents=True, exist_ok=True)
        probe = RENDER_DIR / '_warmup.pdf'
        weasyprint.HTML(string='<html><body style="font-family:Arial">warmup</body></html>').write_pdf(str(probe))
        probe.unlink(missing_ok=True)
    except Exception:
        pass


def unfilled(html: str) -> list[str]:
    """Какие переменные остались незаполненными."""
    return sorted(set(VAR_RE.findall(html)))


def fill(html: str, values: dict | None = None, keep_unfilled: bool = False,
         template_code: str = '') -> str:
    """Единая подстановка значений в HTML. Заменяет ручные re.sub по коду проекта.

    keep_unfilled=True оставляет {{ var }} для незаполненных (режим шаблона),
    False — вычищает (режим документа с данными).
    """
    vals = normalize(values or {}, template_code)
    # В формах иммиграции (Statement Letter) пустое значение показываем прочерком:
    # имени переменной в окне просмотра заявки быть не должно.
    _dash = str(template_code or '').startswith('statement_letter')

    def sub(m):
        v = vals.get(m.group(1))
        if v in (None, ''):
            if _dash:
                return '-'
            return m.group(0) if keep_unfilled else ''
        s = str(v)
        # Значения из карточек и примеров приходят с ЭКРАНИРОВАННЫМИ переводами строк
        # («\n» как два символа) — без этого пункты обязанностей слипаются в одну строку.
        s = s.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
        return str(_ascii_only(s))
    return VAR_RE.sub(sub, _drop_empty_optional(html, vals))


def generate(application_id: int, template_id: int, out_path: str | Path | None = None) -> dict:
    """Полный цикл: значения (карточка клиента + заявка) → HTML → PDF."""
    tpl = load_template(template_id)
    # карточка клиента — целиком: из неё считаются дата, период, суммы прописью
    cl = {}
    c = connect()
    try:
        app = c.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
        if app:
            row = c.execute("SELECT * FROM clients WHERE id=?", (app['client_id'],)).fetchone()
            cl = dict(row) if row else {}
    finally:
        c.close()
    stored = {}
    for _k, _v in stored_values(application_id, template_id).items():
        if _v not in (None, ''):
            stored[_k] = _v
    # Сумма остатка, пропись и адрес считаются заново из карточки клиента и его
    # документов. Сохранённые в карточке документа значения этих полей внутрь
    # расчёта не отдаём: они перебивали свежие и печатались обрезанными —
    # «… thousand» без «rubles 00 kopeks» (Андрей, 17.10.2026).
    for _k in ("balance_rub", "balance_words", "balance_words_2", "balance_cents",
               "address_live", "address_live_2", "address_ru"):
        stored.pop(_k, None)
    try:
        from services.values import build_template_values
        vals = build_template_values(cl, tpl['code'],
                                     {**client_values(application_id), **stored},
                                     app_id=application_id)
    except Exception:
        vals = {}
        vals.update(client_values(application_id))
    # Документы клиента сильнее карточки (правило заказчика 06.10.2026): если паспорт,
    # KITAS или банковская справка дают другое значение — в документ идёт значение из документа.
    try:
        from services import doc_overrides as _docov
        vals, _overridden = _docov.apply(vals, application_id)
        if _overridden:
            vals['__doc_overrides__'] = ', '.join(sorted(_overridden))
    except Exception:  # noqa: BLE001
        pass
    # явные значения (карточка заявки и поля, введённые админом) — поверх автоматических.
    # Но поля, которые всегда вычисляются заново (стороны документа, перечень услуг по
    # профессии, суммы, право), сохранёнными значениями не перебиваем: иначе в документ
    # уходит старый текст от прежней профессии или прежней организации.
    _DERIVED_KEYS = {
        "services_list", "company_block", "contractor_block", "employee_block", "company_tail",
        "inn_kpp_ogrn", "inn_ogrn_line", "governing_law", "company_entity_no",
        "engagement_phrase", "position_title", "base_salary", "base_salary_annual",
        "annual_amount_numeric", "annual_amount_words",
        "monthly_amount_numeric", "monthly_amount_words",
        # Сумма остатка и её пропись, а также адрес клиента всегда считаются заново:
        # в карточке документа лежали обрезанные значения («… thousand» без
        # «rubles 00 kopeks») и адрес в обратном порядке (Андрей, 17.10.2026).
        "balance_rub", "balance_words", "balance_words_2", "balance_cents",
        "address_live", "address_live_2",
    }
    for _k, _v in stored.items():
        if _k in _DERIVED_KEYS and str(vals.get(_k) or "").strip():
            continue
        vals[_k] = _v
    # банковская справка: дата документа и конец периода — всегда дата формирования,
    # начало периода — 3 или 12 месяцев назад (эти поля админ не перебивает)
    if 'bank_statement' in tpl['code']:
        try:
            from datetime import datetime as _dt
            from services.values import _minus_months
            _today = _dt.now()
            vals['doc_date'] = vals['period_to'] = _today.strftime('%d.%m.%Y')
            vals['period_from'] = _minus_months(_today, 12 if '12m' in tpl['code'] else 3).strftime('%d.%m.%Y')
        except Exception:
            pass
    # номер карты в документ уходит только маской: 6 цифр + ****** + 4 цифры
    try:
        from services.values import mask_card
        vals['card_mask'] = mask_card(vals.get('card_mask'), tpl['code'], seed=application_id)
    except Exception:
        pass
    # Русский текст в документ не попадает: всё печатается только на английском.
    # Если значение пришло кириллицей (должность, услуги, адрес, ФИО) — переводим;
    # там, где перевод не дал результата (имена собственные), транслитерируем.
    try:
        import re as _re_cyr
        _cyr = _re_cyr.compile(r"[А-Яа-яЁё]")
        _name_keys = ("client_name", "full_name", "employee_name", "employee_full_name",
                      "cv_name", "signer_name", "surname", "name", "patronymic")
        _ru = [k for k, v in vals.items() if isinstance(v, str) and _cyr.search(v)]
        if _ru:
            _plain = [k for k in _ru if not any(n in k for n in _name_keys)]
            if _plain:
                try:
                    from services import translate as _tr8
                    _src = [str(vals[k]) for k in _plain]
                    # Русский → английский: у модуля перевода основное направление
                    # английский→русский (для панели), поэтому берём обратный перевод.
                    _trans = [str(x or "").strip() for x in (_tr8.translate_reverse(_src, target="en") or [])]
                    if not _trans or any(_cyr.search(x) for x in _trans) or len(_trans) < len(_src):
                        _alt = [str(x or "").strip() for x in (_tr8.translate_by_reserve(_src) or [])]
                        if _alt and len(_alt) >= len(_src) and all(_alt) and not any(_cyr.search(x) for x in _alt):
                            _trans = _alt
                    for _k, _v in zip(_plain, _trans):
                        if _v and not _cyr.search(_v):
                            vals[_k] = _v
                except Exception:  # noqa: BLE001
                    pass
            # остаток кириллицы (в том числе имена) — транслитерация
            try:
                from bot.ai_parser import translit_ru as _tr9
            except Exception:  # noqa: BLE001
                _tr9 = None
            for _k in [k for k, v in vals.items() if isinstance(v, str) and _cyr.search(v)]:
                if _tr9 is None:
                    break
                vals[_k] = _tr9(str(vals[_k]))
    except Exception:  # noqa: BLE001
        pass
    # Адрес клиента в справке: деление на две строки — в одном месте
    # (services/addresses.split_two_lines). Раньше здесь адрес делился вторым
    # проходом, и половинки разъезжались: первая строка бралась старая, вторая —
    # от нового порядка, на листе они ложились друг на друга.
    try:
        from services import addresses as _AD
        _al = re.sub(r"\s+([,;])", r"\1", str(vals.get("address_live") or "").strip())
        _al2 = re.sub(r"\s+([,;])", r"\1", str(vals.get("address_live_2") or "").strip())
        if _al:
            _full = (_al + ", " + _al2).strip(" ,;") if _al2 else _al
            _full = re.sub(r"[,;]?\s*(Russian Federation|Rossiyskaya Federatsiya|RUSSIA|Russia)\s*$",
                           "", _full, flags=re.I).strip(" ,;")
            _l1, _l2 = _AD.split_two_lines(_full)
            vals["address_live"] = _l1
            vals["address_live_2"] = _l2
    except Exception:  # noqa: BLE001
        pass

    html = render_html(html=tpl['_html'], values=vals, code=tpl['code'])
    if 'cv__' in (tpl.get('code') or ''):
        from services.render import hide_empty_sections
        html = hide_empty_sections(html)
    left = unfilled(html)
    if out_path is None:
        out_path = RENDER_DIR / doc_filename(tpl.get("title") or tpl["code"], vals, code=tpl.get("code"))
    pdf = render_pdf(html, base_dir=tpl['_dir'], out_path=out_path)
    return {'pdf_path': str(pdf), 'html': html, 'values': vals, 'unfilled': left,
            'template': tpl['code'], 'pages': None}

_CYR = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
_TRANSLIT = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
             'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
             'х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}


def _ascii_only(value):
    """Значения переменных могут быть введены по-русски — в документ они идут латиницей."""
    if not isinstance(value, str) or not any(ch.lower() in _CYR for ch in value):
        return value
    out = []
    for ch in value:
        low = ch.lower()
        tr = _TRANSLIT.get(low)
        if tr is None:
            out.append(ch)
        else:
            out.append(tr.upper() if ch.isupper() else tr)
    return ''.join(out)
