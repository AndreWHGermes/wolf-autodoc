"""Генерация текстов резюме (CV) по справочнику должностей.

Задача: по должности клиента собрать описание опыта и профиль так, как это
делали в реальных резюме (см. docs/cv_pool.md). Три объёма:
    short  — короткое резюме (3-4 пункта)
    medium — формат Сиваева (профиль + 3-4 пункта)
    long   — расширенный (профиль + 4-6 пунктов + навыки)

Функции вызываются из services/values.py при сборке значений шаблонов 4/5/6.
"""
import json
import re
from pathlib import Path

DOMAIN_EN = {
    'admin_assistant': 'Business Administration',
    'sales_manager': 'Sales and Business Development',
    'marketing': 'Marketing and Advertising',
    'smm_producer': 'Media Production and Communications',
    'hr': 'Human Resource Management',
    'it_specialist': 'Information Technology',
    'designer': 'Design and Applied Arts',
    'accountant': 'Accounting and Finance',
    'driver': 'Transport and Logistics',
    'nanny': 'Early Childhood Education',
    'retail': 'Retail Management',
    'logistics': 'Logistics and Supply Chain Management',
    'teacher': 'Education and Pedagogy',
    'chef': 'Culinary Arts',
    'director': 'Business Management',
    'product_manager': 'Product and Project Management',
}

POSITIONS_FILE = Path('/opt/wolf_v2/data/cv_positions.json')
_CACHE = {}


def load_positions(remote_only: bool = True) -> list:
    """Справочник должностей (кэш в памяти процесса).

    remote_only=True — только профессии, допустимые для УДАЛЁННОЙ работы на компанию
    вне Индонезии (флаг remote в data/cv_positions.json). Физические и локальные
    процессы (повар, водитель, няня, продавец в магазине) в резюме не попадают:
    заявки идут на E33G Remote Worker, а не на работу внутри Индонезии.
    """
    if 'positions' not in _CACHE:
        try:
            data = json.loads(POSITIONS_FILE.read_text(encoding='utf-8'))
            _CACHE['positions'] = data.get('positions', [])
        except Exception:
            _CACHE['positions'] = []
    pos = _CACHE['positions']
    return [p for p in pos if p.get('remote', True)] if remote_only else pos


# Пункт про удалённый формат работы — обязателен в каждом описании резюме
# (требование заказчика 05.10.2026): в документе не должно быть физических
# рабочих процессов и локальных площадок.
REMOTE_DUTY = ('Work remotely with a distributed team, coordinating tasks through '
               'online tools (Slack, Jira, Google Workspace).')
REMOTE_TAIL = 'Works remotely with a company registered outside Indonesia.'


def position_by_code(code: str):
    for p in load_positions():
        if p['code'] == code:
            return p
    return None


def position_title(code: str, lang: str = 'en') -> str:
    p = position_by_code(code)
    if not p:
        return ''
    return p.get('en') if lang == 'en' else p.get('ru')


def detect_position(*texts) -> str:
    """Определяет код должности по текстам (карточка, документы, договор)."""
    blob = ' '.join(str(t) for t in texts if t).lower()
    if not blob.strip():
        return ''
    # Точность важнее первого совпадения: считаем число совпавших ключей и их длину.
    # Иначе на «Cinematographer, Film Editor» побеждал профиль IT Specialist — из-за
    # короткого ключа «editor» (разбор 05.10.2026).
    best, best_score = '', (0, 0, 0)
    for p in load_positions():
        keys = [k for k in p.get('keys', []) if k and k.lower() in blob]
        if not keys:
            continue
        score = (len(keys), sum(len(k) for k in keys), max(len(k) for k in keys))
        if score > best_score:
            best, best_score = p['code'], score
    # одно короткое слово (до 6 букв) профессию не определяет
    if best_score[0] == 1 and best_score[2] < 7:
        return ''
    return best


def split_bullets(text: str, limit: int = 0) -> list:
    """Разбивает абзац описания на пункты (по предложениям, с ведущим «•  »)."""
    if not text:
        return []
    parts = re.split(r'(?<=[.;])\s+', text.strip())
    parts = [p.strip() for p in parts if len(p.strip()) > 12]
    if limit:
        parts = parts[:limit]
    return ['•  ' + p for p in parts]


def job_block(code: str, level: str, limit: int = 0) -> str:
    """Пункты обязанностей для нужного объёма."""
    p = position_by_code(code)
    if not p:
        return ''
    level = level if level in ('short', 'medium', 'long') else 'medium'
    text = (p.get('blocks') or {}).get(level, '')
    bullet = split_bullets(text, limit)
    if bullet and bullet[0].strip() != REMOTE_DUTY:
        bullet = ['•  ' + REMOTE_DUTY] + bullet
    return '\n'.join(bullet)


def skills_for(code: str) -> str:
    p = position_by_code(code)
    return (p or {}).get('skills', '')


def summary_for(code: str, years: str = '') -> str:
    """Профиль по формуле из архива: «<профессия> with experience across <область>»."""
    p = position_by_code(code)
    if not p:
        return ''
    title = p.get('en', '')
    # область всегда по-английски — русское название в англоязычном резюме недопустимо
    if code.startswith('custom_'):
        domain = 'professional services'
    else:
        domain = DOMAIN_EN.get(code) or p.get('en', '') or p.get('ru', '')
    if domain and any('а' <= ch.lower() <= 'я' for ch in domain):
        domain = 'professional services'   # русское название в англоязычном профиле недопустимо
    skill = p.get('skills', '')
    years_part = f'over {years} years of experience' if years else 'extensive experience'
    base = f'{title} with {years_part} across {domain.lower()} environment.'
    base = f'{base} Skilled in {skill}.' if skill else base
    return f'{base} {REMOTE_TAIL}'


CV_TEMPLATES = {'cv__format_short': 'short', 'cv__format_sivaev': 'medium',
                'cv__format_detailed': 'long'}


def is_cv_template(tpl_code: str) -> bool:
    """Это шаблон резюме?"""
    return (tpl_code or '') in CV_TEMPLATES


def level_for_template(tpl_code: str) -> str:
    """Объём описания под формат резюме."""
    return CV_TEMPLATES.get(tpl_code or '', 'medium')


def position_phrases_pairs(code: str, variable: str = '') -> list:
    """Фразы для «кусочков» с русской подписью: [{'en': ..., 'ru': ...}].

    Администратор читает и отмечает русский вариант, а в документ подставляется
    английский — так требует заказчик (документ на английском, интерфейс на русском).
    """
    ph = position_phrases(code, variable)
    ru_map = {}
    extra = []
    try:
        data = (load_phrases_ru() or {}).get(code) or {}
        for en, ru in zip(data.get('phrases') or [], data.get('phrases_ru') or []):
            if en and ru:
                ru_map[en] = ru
            # всё, что администратор вводил руками или генерировал моделью,
            # тоже должно быть в списке «кусочков» — оно уже переведено и в памяти
            if en and en not in ph:
                extra.append(en)
    except Exception:
        ru_map = {}
    if extra:
        ph = ph + extra
    return [{'en': x, 'ru': ru_map.get(x, '') or x} for x in ph]


_RU_PHRASES = None


def load_phrases_ru() -> dict:
    """Русские переводы пула фраз (файл, считается один раз скриптом)."""
    global _RU_PHRASES
    if _RU_PHRASES is None:
        try:
            with open('/opt/wolf_v2/data/cv_phrases_ru.json', encoding='utf-8') as f:
                _RU_PHRASES = json.load(f)
        except Exception:
            _RU_PHRASES = {}
    return _RU_PHRASES


def value_of(app_id: int, key: str) -> str:
    """Текущее значение переменной в документах заявки (последнее непустое).

    Нужно, чтобы при подтверждении описания понять, какая профессия выбрана.
    """
    try:
        from services import db as _db
        rows = _db.q("SELECT values_json FROM application_documents "
                     "WHERE application_id=? ORDER BY id DESC", (app_id,)) or []
        for r in rows:
            try:
                vals = json.loads(r.get("values_json") or "{}")
            except Exception:
                continue
            v = (vals.get(key) or "").strip()
            if v:
                return v
    except Exception:
        pass
    return ""


def code_by_title(title: str) -> str:
    """Код профессии по её названию (английскому или русскому).

    Нужен, когда администратор выбрал профессию текстом в поле — чтобы новые
    формулировки запомнились именно под этой профессией.
    """
    t = (title or '').strip().lower()
    if not t:
        return ''
    for p in load_positions():
        for key in ('en', 'ru', 'code'):
            v = (p.get(key) or '').strip().lower()
            if v and (v == t or v in t or t in v):
                return p.get('code') or ''
    return ''


def remember_phrase(code: str, en: str, ru: str) -> bool:
    """Запомнить пару «фраза EN / фраза RU» на сервере.

    Нужна для того, что администратор вводит руками, для сгенерированных
    уникальных описаний и для новых профессий: дальше такая пара берётся из
    памяти, без обращения к модели.
    """
    en = (en or '').strip()
    ru = (ru or '').strip()
    if not en:
        return False
    path = '/opt/wolf_v2/data/cv_phrases_ru.json'
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    d = data.setdefault(code or '_common', {'ru': '', 'en': '', 'phrases': [], 'phrases_ru': []})
    ph = d.setdefault('phrases', [])
    ph_ru = d.setdefault('phrases_ru', [])
    if en in ph:
        i = ph.index(en)
        if ru:
            ph_ru[i] = ru
    else:
        ph.append(en)
        ph_ru.append(ru)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        return False
    global _RU_PHRASES
    _RU_PHRASES = data
    if ru:
        try:
            from services import db as _db
            for tid in (4, 5, 6):
                _db.exec_sql('INSERT OR REPLACE INTO translation_line(template_id, src, ru) '
                             'VALUES(?,?,?)', (tid, en, ru))
        except Exception:
            pass
    return True


def generate_unique_summary(code: str, n: int = 3) -> dict:
    """Сгенерировать уникальное описание профессии — единственный случай, когда
    нужна модель.

    Возвращает пару: английский текст для документа и русский для памяти.
    Оба варианта сразу запоминаются, чтобы больше модель не дёргать.
    """
    prof = position_by_code(code) or {}
    title_en = prof.get('en') or code
    title_ru = prof.get('ru') or ''
    prompt = (
        'Составь описание профессионального профиля для резюме на английском языке. '
        'Должность: %s. Ровно %d предложения, деловой стиль, без первого лица, '
        'без выдуманных компаний и цифр. Верни только текст.' % (title_en, n))
    text_en = ''
    try:
        from services.llm import call_llm
        text_en = (call_llm([{'role': 'user', 'content': prompt}], timeout=90,
                            json_mode=False) or '').strip()
    except Exception:
        text_en = ''
    if not text_en:
        return {'ok': False, 'error': 'модель недоступна'}
    text_en = ' '.join(text_en.split())
    text_ru = ''
    try:
        from services import translate as _T
        got = _T.translate_by_reserve([text_en])
        text_ru = (got[0] if got else '') or ''
    except Exception:
        text_ru = ''
    remember_phrase(code, text_en, text_ru)
    return {'ok': True, 'en': text_en, 'ru': text_ru}


def translate_ru_to_en(text: str) -> str:
    """Русский ручной текст → английский (для документа)."""
    try:
        from services import translate as _T
        got = _T.translate_reverse([text])
        return (got[0] if got else '') or ''
    except Exception:
        return ''


def translate_en_to_ru(text: str) -> str:
    """Английский текст → русский (для памяти и интерфейса)."""
    try:
        from services import translate as _T
        got = _T.translate_by_reserve([text])
        return (got[0] if got else '') or ''
    except Exception:
        return ''


def add_profession(name_ru: str) -> dict:
    """Завести новую профессию: сгенерировать описание и сразу перевести.

    Это второй (и последний) случай, когда нужна модель. Название администратор
    пишет по-русски, в документ уходит английское; все фразы и переводы
    запоминаются, дальше профессия работает из памяти наравне с предзаписанными.
    """
    import re as _re
    name_ru = (name_ru or '').strip()
    if not name_ru:
        return {'ok': False, 'error': 'не указано название профессии'}
    title_en = name_ru
    if _re.search(r'[А-Яа-яЁё]', name_ru):
        try:
            from services import translate as _T
            got = _T.translate_reverse([name_ru])
            title_en = (got[0] if got else '') or ''
        except Exception:
            title_en = ''
    if not title_en:
        return {'ok': False, 'error': 'не удалось перевести название профессии'}
    code = _re.sub(r'[^a-z0-9]+', '_', title_en.lower()).strip('_')[:48] or 'custom'

    prompt = (
        'Составь для резюме список обязанностей и достижений на английском языке. '
        'Должность: %s. Ровно 8 строк, каждая — одно предложение делового стиля, '
        'без первого лица, без выдуманных компаний, городов и цифр. '
        'Верни только строки, без нумерации.' % title_en)
    lines = []
    try:
        from services.llm import call_llm
        raw = (call_llm([{'role': 'user', 'content': prompt}], timeout=120, json_mode=False) or '')
        lines = [l.strip(' -•\t') for l in raw.splitlines() if l.strip()]
    except Exception:
        lines = []
    if not lines:
        return {'ok': False, 'error': 'модель недоступна — попробуйте позже'}
    lines = lines[:8]

    ru_lines = []
    try:
        from services import translate as _T
        ru_lines = _T.translate_by_reserve(lines)
    except Exception:
        ru_lines = []

    prof_en = '%s with extensive experience across the relevant business environment.' % title_en
    prof_ru = ''
    try:
        from services import translate as _T
        got = _T.translate_by_reserve([prof_en])
        prof_ru = (got[0] if got else '') or ''
    except Exception:
        prof_ru = ''

    for en, ru in zip(lines, ru_lines):
        remember_phrase(code, ('•  ' + en), ('•  ' + (ru or '')))
    remember_phrase(code, prof_en, prof_ru)

    bullets_en = ['•  ' + x for x in lines]
    bullets_ru = ['•  ' + (x or '') for x in ru_lines]
    blocks = {
        'short': '|'.join(bullets_en[:2]),
        'medium': '|'.join(bullets_en[:4]),
        'long': '|'.join(bullets_en[:6]),
    }
    try:
        data = json.loads(POSITIONS_FILE.read_text(encoding='utf-8'))
    except Exception:
        data = {'positions': []}
    positions = data.setdefault('positions', [])
    if not any((p.get('code') or '') == code for p in positions):
        positions.append({'code': code, 'en': title_en, 'ru': name_ru,
                          'skills': '', 'blocks': blocks})
        try:
            POSITIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                      encoding='utf-8')
        except Exception:
            return {'ok': False, 'error': 'не удалось сохранить профессию'}
    _CACHE.pop('positions', None)
    _RU_PHRASES_PAIRS_RELOAD()
    return {'ok': True, 'code': code, 'en': title_en, 'ru': name_ru,
            'pairs': [{'en': prof_en, 'ru': prof_ru}]
                      + [{'en': e, 'ru': r} for e, r in zip(bullets_en, bullets_ru)]}



# Выбор из пула закрепляем за клиентом: одинаковые компании/должности/вузы
# во всех трёх резюме (random давал разные места в каждом документе).
_SALT = {'k': '0'}


def _pick(lst, tag: str = ''):
    if not lst:
        return None
    import hashlib
    h = hashlib.md5(('%s|%s' % (_SALT.get('k'), tag)).encode()).hexdigest()
    return lst[int(h[:8], 16) % len(lst)]

def _RU_PHRASES_PAIRS_RELOAD():
    """Сбросить кэш русских переводов, чтобы новые фразы сразу подхватились."""
    global _RU_PHRASES
    _RU_PHRASES = None


_LINKS = None
_LINKS_RU = None
_UNIS = None


def _load_universities() -> dict:
    """Пул учебных заведений по городам (место рождения → вуз)."""
    global _UNIS
    if _UNIS is None:
        try:
            with open('/opt/wolf_v2/data/cv_universities.json', encoding='utf-8') as f:
                _UNIS = json.load(f)
        except Exception:
            _UNIS = {}
    return _UNIS


def city_key(city: str) -> str:
    """Ключ города по значению места рождения (латиница, кириллица, варианты)."""
    c = ' '.join((city or '').strip().lower().replace('.', ' ').replace(',', ' ').split())
    if not c:
        return ''
    for key, info in (_load_universities().get('cities') or {}).items():
        for alias in (info.get('aliases') or []):
            a = (alias or '').strip().lower()
            if a and (a in c or c in a):
                return key
    return ''


def city_label(city: str) -> str:
    """Название города для интерфейса (русское), как в карточке."""
    data = _load_universities()
    info = (data.get('cities') or {}).get(city_key(city)) or {}
    return info.get('ru') or info.get('en') or (city or '').strip()


def city_label_en(city: str) -> str:
    """Название города для ДОКУМЕНТА — латиницей.

    В резюме уезжало «Е ГЧЕЛЯБИНСК» из карточки клиента: место рождения приходит
    в русском написании, а документ английский. Берём город из справочника (там есть
    латинское имя) и только если его нет — аккуратно переносим русское в латиницу.
    """
    data = _load_universities()
    info = (data.get('cities') or {}).get(city_key(city)) or {}
    name = (info.get('en') or '').strip()
    if name:
        return name
    raw = (city or '').strip()
    if not raw:
        return ''
    try:
        table = _load_universities().get('translit') or {}
        low = raw.lower()
        for ru, en in table.items():
            if ru.lower() in low:
                return en
    except Exception:
        pass
    return TRANSLIT(raw) if 'TRANSLIT' in globals() else raw


def universities_for_city(city: str) -> list:
    """Учебные заведения города места рождения; город неизвестен — общий список."""
    data = _load_universities()
    info = (data.get('cities') or {}).get(city_key(city)) or {}
    return list(info.get('universities') or data.get('default') or [])


def degree_options() -> list:
    """Пул формулировок образования для выпадающего списка."""
    return list(_load_universities().get('degrees') or [])


def university_for_city(city: str, sector: str = '') -> str:
    """Случайный вуз из пула города (город — из места рождения клиента)."""
    import random
    lst = universities_for_city(city)
    _r = _pick(lst, 'uni'); return _r if _r else ''


UNI_PROFILES = (
    ('medical', ('medical', 'medic', 'sechenov', 'pavlov', 'pharmac')),
    ('technical', ('technical', 'polytechnic', 'technological', 'engineering', 'aviation',
                   'bauman', 'itmo', 'radioelectronic', 'mining', 'petroleum', 'aerospace',
                   'automobile', 'transport', 'industrial', 'oil')),
    ('economics', ('economic', 'finance', 'financial', 'management', 'trade', 'business',
                   'agrarian', 'agricultural', 'law', 'customs')),
    ('humanities', ('pedagogical', 'linguistic', 'humanities', 'culture', 'social', 'art',
                    'international', 'olympic', 'journalism')),
)


def university_profile(name: str) -> str:
    """Профиль учебного заведения по его названию (для подбора специальностей)."""
    n = (name or '').lower()
    for prof, keys in UNI_PROFILES:
        if any(k in n for k in keys):
            return prof
    return 'general'


def majors_for(university: str) -> list:
    """Специальности по профилю выбранного вуза."""
    m = (_load_universities().get('majors') or {})
    return list(m.get(university_profile(university)) or m.get('general') or [])


def education_options(university: str = '') -> list:
    """Варианты для поля «образование»: степень + специальность выбранного вуза."""
    data = _load_universities()
    majors = majors_for(university)
    degs = [d for d in (data.get('degrees') or [])
            if d and 'MBA' not in d and 'PhD' not in d][:3] or ["Bachelor's Degree"]
    out = []
    for d in degs:
        for m in majors[:4]:
            out.append('%s in %s' % (d, m))
    return out


def load_links() -> dict:
    """Связи «профессия → сферы → должности → обязанности»."""
    global _LINKS
    if _LINKS is None:
        try:
            with open('/opt/wolf_v2/data/cv_links.json', encoding='utf-8') as f:
                _LINKS = json.load(f)
        except Exception:
            _LINKS = {}
    return _LINKS


def load_links_ru() -> dict:
    """Русские подписи связей (для интерфейса администратора)."""
    global _LINKS_RU
    if _LINKS_RU is None:
        try:
            with open('/opt/wolf_v2/data/cv_links_ru.json', encoding='utf-8') as f:
                _LINKS_RU = json.load(f)
        except Exception:
            _LINKS_RU = {}
    return _LINKS_RU


def load_companies() -> list:
    """Пул компаний (реальные из архива + нейтральные по сферам)."""
    try:
        with open('/opt/wolf_v2/data/cv_companies.json', encoding='utf-8') as f:
            return (json.load(f) or {}).get('companies') or []
    except Exception:
        return []


def sectors_for(code: str) -> list:
    return (load_links().get('profession_sectors') or {}).get(code) or []


def companies_for(code: str) -> list:
    """Компании, логически подходящие профессии (по сферам)."""
    secs = sectors_for(code)
    out = [c for c in load_companies() if c.get('sector') in secs]
    return out or load_companies()


def titles_for(code: str) -> list:
    """Должности профессии: английский для документа, русский для интерфейса."""
    lst = (load_links().get('profession_titles') or {}).get(code) or []
    ru = (load_links_ru().get('titles') or {})
    if not lst:
        p = position_by_code(code) or {}
        lst = [p.get('en') or code]
    return [{'en': t, 'ru': ru.get(t) or t} for t in lst]


def period_chain(count: int = 3, ref=None) -> list:
    """Цепочка периодов работы назад от текущего месяца — без пересечений.

    По архиву: на одном месте держатся 4–6 лет, предыдущее место заканчивается
    месяцем начала следующего (Dec 2023 → Jan 2024). Текущее место — «Present»,
    его начало отсчитывается от текущего месяца.
    """
    import datetime
    import random
    ref = ref or datetime.date.today()
    out, cur_end = [], ref
    for i in range(max(1, count)):
        dur = _pick([36, 48, 60, 72], 'dur1_%d' % i) if i == 0 else _pick([36, 48, 60, 72, 84, 96], 'dur2_%d' % i)
        # конец места — месяц, предшествующий началу следующего (встык)
        m = cur_end.month - 1
        y = cur_end.year + (m // 12 if m <= 0 else 0)
        m = m if m > 0 else 12
        end_d = datetime.date(y, m, 1)
        start_d = datetime.date(end_d.year - (dur // 12), end_d.month, 1)
        out.append({'start': start_d.strftime('%b %Y'),
                    'end': 'Present' if i == 0 else end_d.strftime('%b %Y')})
        cur_end = start_d
    return out


def gen_experience(code: str, level: str = 'medium', count: int = 3) -> list:
    """Опыт работы: 2–3 места с согласованными должностью, компанией и обязанностями.

    Должности идут по нисходящей (текущая — выше, прошлые — ниже), компании —
    из сфер, разрешённых профессией, обязанности собираются под пару.
    """
    import random
    per = period_chain(count)
    tl = titles_for(code) or []
    comps = companies_for(code) or []
    # порядок компаний закрепляем за клиентом: во всех трёх резюме должны стоять
    # одни и те же места работы, а не случайные при каждой сборке (random.shuffle давал разные)
    import hashlib as _hl
    comps = sorted(comps, key=lambda c: _hl.md5(
        ('%s|%s' % (_SALT.get('k'), (c or {}).get('name', ''))).encode()).hexdigest())
    n_bul = {'short': 2, 'medium': 4, 'long': 4}.get(level, 4)
    out = []
    for i, p in enumerate(per):
        if tl:
            idx = max(0, len(tl) - 1 - i) if len(tl) > 1 else 0
            title = tl[idx]
        else:
            title = {'en': position_title(code, 'en'), 'ru': position_title(code, 'ru')}
        comp = comps[i] if i < len(comps) else (comps[0] if comps else {'name': '', 'sector': ''})
        sector = comp.get('sector') or ''
        duties = [x['en'] for x in duties_for(code, sector, level)][:n_bul]
        out.append({'title': title['en'], 'title_ru': title['ru'],
                    'company': comp.get('name_lat') or comp.get('name') or '', 'sector': sector,
                    'period': '%s \u2013 %s' % (p['start'], p['end']),
                    'duties': duties})
    return out


def _norm_words(text: str) -> set:
    """Слова фразы без маркеров — для отсева дублей по смыслу."""
    import re as _re
    t = _re.sub(r'^[•\-\s]+', '', (text or '')).lower()
    t = _re.sub(r'[^a-zа-яё0-9\s]', ' ', t)
    return {w for w in t.split() if len(w) > 3}


def duties_for(code: str, sector: str = '', level: str = 'medium') -> list:
    """Обязанности: базовые по профессии + фразы сферы компании.

    Берём блок одного уровня (иначе короткая и подробная формулировки дублируют
    друг друга) и отсекаем повторы по смыслу. Профессия задаёт суть работы,
    сфера компании — контекст, поэтому блоки не конфликтуют.
    """
    ru_map = {}
    d = (load_phrases_ru() or {}).get(code) or {}
    for en, r in zip(d.get('phrases') or [], d.get('phrases_ru') or []):
        ru_map[en] = r
    p = position_by_code(code) or {}
    blocks = p.get('blocks') or {}
    raw = blocks.get(level) or blocks.get('medium') or ''
    base = [x.strip() for x in (split_bullets(raw) or []) if x.strip()]
    if not base:
        base = [x for x in (position_phrases(code, 'cv_job') or []) if x.startswith('•')]

    picked, keys = [], []
    for x in base:
        w = _norm_words(x)
        if not w:
            continue
        if any(len(w & k) / float(max(1, len(w | k))) > 0.55 for k in keys):
            continue
        keys.append(w)
        picked.append(x if x.lstrip().startswith('•') else '•  ' + x.lstrip())

    sec_duties = ((load_links().get('sector_duties') or {}).get(sector) or [])[:2]
    sec_ru = (load_links_ru().get('duties') or {})
    items = [(x, ru_map.get(x) or ru_map.get('•  ' + x.lstrip('• '), '')) for x in picked]
    items += [(x, sec_ru.get(x, '')) for x in sec_duties]
    n = {'short': 2, 'medium': 4, 'long': 6}.get(level, 4)
    return [{'en': e, 'ru': r} for e, r in items[:n]]


def random_job(code: str, level: str = 'medium') -> dict:
    """Подобрать согласованную пару «должность + компания» и обязанности под них."""
    import random
    tl = titles_for(code)
    title = _pick(tl, 'title') if tl else {'en': '', 'ru': ''}
    comps = companies_for(code)
    comp = _pick(comps, 'comp') if comps else {'name': '', 'sector': ''}
    sector = comp.get('sector') or ''
    ctx_en = (load_links().get('sector_context') or {}).get(sector) or ''
    return {'ok': True, 'profession': code,
            'title': title['en'], 'title_ru': title['ru'],
            'company': comp.get('name_lat') or comp.get('name') or '', 'sector': sector,
            'context_en': ctx_en,
            'context_ru': (load_links_ru().get('context') or {}).get(ctx_en, ''),
            'duties': duties_for(code, sector, level)}


def summary_random(code: str, n: int = 3, avoid: set | None = None) -> str:
    """«Кубик рандома»: описание профессии из случайных предложений пула.

    Собирает связный абзац из нескольких предложений (как в архивных резюме):
    первое — с упоминанием профессии, остальные — из блоков описания и навыков.
    Уже использованные формулировки (avoid) берутся в последнюю очередь,
    чтобы описания у разных клиентов не повторялись дословно.
    """
    import random as _rnd
    p = position_by_code(code)
    if not p:
        return ''
    title = p.get('en', '') or ''
    sents = [s.lstrip('\u2022 ').strip() for s in position_phrases(code, 'cv_summary')]
    sents = [s for s in sents if len(s) > 25]
    if not sents:
        return ''
    avoid_set = {a.strip().lower() for a in (avoid or set()) if a and a.strip()}
    fresh = [s for s in sents if s.lower() not in avoid_set] or sents
    rnd = _rnd.SystemRandom()
    heads = [s for s in fresh if title and title.lower() in s.lower()] or fresh
    head = rnd.choice(heads)
    rest = [s for s in fresh if s != head]
    rnd.shuffle(rest)
    out = [head] + rest[:max(0, int(n) - 1)]
    text = ' '.join(out)
    return text if text.endswith('.') else text + '.'


def sector_by_company(name: str) -> str:
    """Сфера компании по названию (из карточки, документа клиента или пула)."""
    n = (name or '').strip().lower()
    if not n:
        return ''
    for c in load_companies():
        cn = (c.get('name') or '').lower()
        if cn and (cn == n or cn in n or n in cn):
            return c.get('sector') or ''
    return ''


def university_for(code: str, sector: str = '') -> str:
    """Вуз из пула — по сфере компании, иначе по первой сфере профессии."""
    import random
    uni = (load_links().get('universities') or {})
    lst = uni.get(sector) or uni.get((sectors_for(code) or [''])[0]) or []
    _r = _pick(lst, 'uni'); return _r if _r else ''


def job_pair(code: str, level: str = 'medium') -> dict:
    """Второе место работы: другая компания подходящей сферы, должность ниже уровнем."""
    import random
    tl = titles_for(code) or []
    title = tl[max(0, len(tl) - 2)]['en'] if len(tl) > 1 else (tl[0]['en'] if tl else '')
    comps = [c for c in companies_for(code) if c.get('name')]
    _c = _pick(comps, 'comp2'); comp = _c['name'] if _c else ''
    return {'title': title, 'company': comp}


def education_years_for(client: dict) -> str:
    """Годы обучения — производная от даты рождения (18–22 года), а не выдумка."""
    import re as _re
    bd = str((client or {}).get('birth_date') or (client or {}).get('date_of_birth') or '')
    m = _re.search(r'(19|20)\d{2}', bd)
    if not m:
        return ''
    y = int(m.group(0))
    return '%d \u2013 %d' % (y + 18, y + 22)


def build_for_application(level: str = 'short', code: str = '', client: dict | None = None,
                          company: str = '', period: str = 'Present') -> dict:
    """Готовый набор cv_* по единой логике — для всех трёх резюме.

    Приоритет источников: настоящее резюме клиента (Google Диск) → карточка
    заявки → пул (компании/должности/кусочки). Обязанности обзорные, без
    конкретики: так и написано в архивных документах.
    """
    client = client or {}
    _SALT['k'] = str(client.get('id') or '')
    # Выбор компании, вуза и периодов закрепляем за клиентом: во всех трёх резюме
    # должны стоять одни и те же места работы, а не случайные при каждой сборке.
    try:
        random.seed(20260000 + int(client.get('id') or 0))
    except Exception:
        pass
    doc = {}
    try:
        doc = read_client_cv(client.get('id'))
    except Exception:
        doc = {}
    eff = code or (doc.get('code') if doc else '') or detect_position(
        client.get('position', ''), client.get('job_title', ''), client.get('full_name_latin', ''))
    # профессии нет в справочнике: служебный код нужен внутренним вычислителям,
    # но профиль администратора в документ НЕ уходит — иначе кинооператору
    # печаталось резюме «Administrative Assistant» (разбор 05.10.2026).
    card_title = (client.get('position') or '').strip()
    auto_prof = False
    if not eff:
        eff = 'admin_assistant'
        auto_prof = True

    n_bul = {'short': 3, 'medium': 4, 'long': 5}.get(level, 4)

    raw_title = (client.get('position') or '').strip()
    if raw_title and (len(raw_title) > 60
                      or any(m in raw_title.lower() for m in _MESSY)):
        raw_title = ''
    comp1 = (company or client.get('company_name') or client.get('company_llc') or '').strip()
    if not comp1 and doc.get('companies'):
        comp1 = (doc.get('companies') or [''])[0]

    # опыт работы: 2–3 места, периоды идут назад от текущего месяца без пересечений
    exp = gen_experience(eff, level, count=2)
    if raw_title:
        exp[0]['title'] = raw_title
    if not comp1:
        comp1 = exp[0]['company']
    exp[0]['company'] = comp1
    exp[0]['sector'] = sector_by_company(comp1) or exp[0].get('sector') or ''
    p1 = (client.get('job1_period') or '').strip()
    if p1:
        exp[0]['period'] = p1
    if doc.get('bullets'):
        exp[0]['duties'] = list(doc.get('bullets'))[:n_bul]
    else:
        exp[0]['duties'] = [x['en'] for x in duties_for(eff, exp[0]['sector'], level)][:n_bul]

    if len(exp) > 1:
        t2 = (client.get('job2_title') or '').strip()
        c2 = (client.get('job2_company') or '').strip()
        if t2:
            exp[1]['title'] = t2
        if c2:
            exp[1]['company'] = c2
            exp[1]['sector'] = sector_by_company(c2) or ''
        if (client.get('job2_period') or '').strip():
            exp[1]['period'] = client['job2_period'].strip()
        b2 = (client.get('job2_bullets') or '').strip()
        if b2:
            exp[1]['duties'] = [x.strip() for x in b2.splitlines() if x.strip()][:n_bul]
        else:
            exp[1]['duties'] = [x['en'] for x in duties_for(eff, exp[1]['sector'], level)][:n_bul]

    out = {
        # при нераспознанной профессии — только название должности клиента и
        # удалённый характер работы; ни навыков, ни обязанностей, ни чужого профиля
        'cv_summary': (summary_for(eff) if not auto_prof else
                       (f'{card_title} with extensive experience across '
                        f'professional services environment. {REMOTE_TAIL}'
                        if card_title else '')),
        'cv_skills_hard': '' if auto_prof else skills_for(eff),
        'cv_position_ru': '' if auto_prof else position_title(eff, 'ru'),
        'cv_profession': card_title if auto_prof else position_title(eff, 'en'),
        'cv_profession_note': ('подобрана автоматически — проверьте' if auto_prof else ''),
        # учебное заведение: документы клиента → карточка → пул вузов его города
        'cv_education_school': ((client.get('education_school') or '').strip()
                                or ''),
        'cv_education_city': city_label_en(client.get('birth_place') or ''),
        'cv_education_years': ((client.get('education_years') or '').strip()
                               or ''),
    }
    for i, e in enumerate(exp, 1):
        duties = [str(x).strip() for x in e['duties'] if str(x).strip()]
        # удалённый формат работы указываем всегда: в резюме не должно быть
        # физических процессов и локальных площадок внутри Индонезии
        if not any('remot' in d.lower() for d in duties):
            duties = ['•  ' + REMOTE_DUTY] + duties
        out['cv_job%d_title' % i] = e['title']
        out['cv_job%d_company' % i] = e['company']
        out['cv_job%d_period' % i] = e['period']
        out['cv_job%d_bullets' % i] = '\n'.join(duties)
    # РЕАЛЬНЫЙ ДОКУМЕНТ: ничего не придумываем. Нет данных в карточке — поля пустые,
    # их заполняет администратор. Иначе в резюме реального клиента попадали работы,
    # вуз и периоды демонстрационного профиля (разбор 05.10.2026).
    _job_card = any(str((client or {}).get(k) or '').strip() for k in
                    ('job1_period', 'job2_company', 'job2_title', 'job2_period', 'company_name'))
    if not _job_card:
        for _k in ('cv_job1_company', 'cv_job1_title', 'cv_job1_period', 'cv_job1_bullets',
                   'cv_job2_company', 'cv_job2_title', 'cv_job2_period', 'cv_job2_bullets',
                   'cv_job3_company', 'cv_job3_title', 'cv_job3_period'):
            out[_k] = ''
    if auto_prof:
        # обязанности офисного профиля в документ тоже не идут
        for _k in ('cv_job1_bullets', 'cv_job2_bullets', 'cv_job3_bullets'):
            out[_k] = ''
    if not str((client or {}).get('education_school') or '').strip():
        for _k in ('cv_education_school', 'cv_education_degree', 'cv_education_years',
                   'cv_education_note'):
            out[_k] = ''

    return {k: v for k, v in out.items() if v}

# Область образования и типовые навыки по каждой профессии: нужны, чтобы резюме
# заполнялось целиком (образование, языки, личные качества, инструменты).
SOFT_SKILLS = ('attention to detail, time management, teamwork, '
               'clear communication, responsibility')
DEFAULT_LANGUAGES = 'Russian (Native), English (Upper-Intermediate)'


def degree_for(code: str, level: str = 'medium', university: str = '') -> str:
    """Строка образования: степень + специальность (по вузу) или область по профессии."""
    import random
    majors = majors_for(university) if university else []
    if majors:
        return 'Bachelor\u2019s Degree in %s' % _pick(majors, 'major')
    domain = DOMAIN_EN.get(code, '')
    if not domain:
        return ''
    return 'Bachelor\u2019s Degree in %s' % domain


def education_note_for(code: str) -> str:
    domain = DOMAIN_EN.get(code, '')
    return ('Focused on %s.' % domain) if domain else ''


def languages_for(code: str = '') -> str:
    return DEFAULT_LANGUAGES


def soft_for(code: str = '') -> str:
    return SOFT_SKILLS


def tools_for(code: str) -> str:
    """Инструменты — из навыков профессии (они перечислены через запятую)."""
    return skills_for(code)


def build_full(code: str = '', level: str = 'medium', company: str = '',
               period: str = '', client: dict | None = None) -> dict:
    """Полный набор переменных резюме по профессии (то, что подставляется в формы)."""
    out = build_for_application(level=level, code=code, client=client,
                                company=company, period=period)
    # если профессию передали не явно — берём ту, что определилась по карточке/резюме
    eff = code or detect_position((client or {}).get('position', ''),
                                  (client or {}).get('job_title', ''))
    out.update({
        # образование связано с вузом: специальность берётся по профилю заведения
        'cv_education_degree': ((str((client or {}).get('education_degree') or '').strip())
                                or ''),
        'cv_education_note': education_note_for(eff),
        'cv_languages': languages_for(eff),
        'cv_skills_soft': soft_for(eff),
        'cv_skills_tools': tools_for(eff),
    })
    return {k: v for k, v in out.items() if v}

def read_client_cv(client_id) -> dict:
    """Читает НАСТОЯЩЕЕ резюме клиента из его папки (Google Drive).

    Приоритет как у банковских справок: если у клиента есть своё резюме, профессия
    и обязанности берутся из него, а не подбираются системой.
    """
    if not client_id:
        return {}
    try:
        from pathlib import Path as _P
        # Папка клиента: сначала рабочий кэш Drive, затем выгрузка папок клиентов.
        # Раньше проверялся только gdrive_cache, из-за чего настоящие резюме не находились.
        folders = [_P('/opt/wolf_v2/data/gdrive_cache') / ('client_%s' % client_id)]
        try:
            from services.values import _find_client_folder_by_id
            extra = _find_client_folder_by_id(client_id)
            if extra:
                folders.append(_P(str(extra)))
        except Exception:
            pass
        cands = []
        for folder in folders:
            if folder and folder.is_dir():
                cands += [f for f in folder.iterdir() if f.is_file() and any(
                    k in f.name.lower() for k in ('resume', 'cv', 'резюме'))]
        if not cands:
            return {}
        from services.doc_read import read_text
        text = read_text(str(cands[0])) or ''
        if len(text.strip()) < 150:
            return {}
        bullets = [re.sub(r'^[•\-\*\s]+', '', l).strip()
                   for l in text.splitlines() if l.strip().startswith(('•', '-', '*'))]
        bullets = [b for b in bullets if len(b) > 25][:8]
        periods = re.findall(r'((?:[A-Z][a-z]+ )?\d{4}\s*[–—-]\s*(?:Present|(?:[A-Z][a-z]+ )?\d{4}))', text)
        companies = re.findall(r'^([A-Z][A-Za-z0-9&.,\'-]{2,40}(?: (?:LLC|Inc|Ltd|Agency|Group|Company))?)\s*[—|·]',
                               text, re.M)
        return {'file': cands[0].name, 'text': text,
                'code': detect_position(text),
                'bullets': bullets, 'periods': periods[:4],
                'companies': [c.strip() for c in companies[:4]]}
    except Exception:
        return {}

# ── Определение профессии ───────────────────────────────────────────────────
# Профессия нужна, чтобы собрать описание. Берём её в трёх местах по порядку:
# карточка заявки → документы клиента с Google Диска → выбор администратора.
_MESSY = ('employer', 'employee', 'hereby', 'performs', 'hired as', 'исполнител',
          'договор', 'contract', 'limited liability', 'the company')


def _cut_tail(text: str) -> str:
    """Обрезает служебный «хвост» договорной фразы: «Fashion Designer and performs» → «Fashion Designer»."""
    t = (text or '').strip(' -—:,')
    t = re.split(r'\s+(?:and\s+performs|and\s+carries|on\s+a\s+full|on\s+full|performs|for\s+the|to\s+perform|duties|position\b)', t)[0]
    t = re.split(r'\s+', t)
    # не более четырёх слов в названии профессии
    return ' '.join(t[:4]).strip(' -—:,')


def clean_position(text: str) -> str:
    """Вытаскивает профессию из поля карточки, куда попал кусок текста договора.

    В карточке встречаются значения вида «The Employer hereby employs the Employee
    as a Product Manager» или «of Fashion Designer and performs» — нужна сама
    профессия, без служебных фраз.
    """
    t = (text or '').strip()
    if not t:
        return ''
    if len(t) <= 48 and not any(m in t.lower() for m in _MESSY):
        return t
    low = t.lower()
    # 1) «employs the Employee as <профессия>» / «hired as <профессия>» / «как <профессия>»
    for m in re.finditer(r'(?:as|как)\s+(?:a|an|the|в|на)?\s*([A-ZА-Я][^.,;\n]{2,45})', t):
        cand = _cut_tail(m.group(1))
        cl = cand.lower()
        if not any(x in cl for x in _MESSY) and len(cand) > 2:
            return cand
    # 2) строка начинается с «of <профессия>» — убираем «of»
    m = re.match(r'^(?:of|в|на)\s+(.+)$', t, flags=re.IGNORECASE)
    if m:
        cand = _cut_tail(m.group(1))
        if len(cand) > 2:
            return cand
    # ничего разумного — отдаём как есть, но без переводов строк
    return ' '.join(t.split())[:60]


def resolve_profession(client: dict) -> dict:
    """Профессия клиента: карточка → документы Диска. Возвращает код, название и источник."""
    c = client or {}
    raw = (c.get('position') or c.get('job_title') or '').strip()
    title = clean_position(raw)
    code = detect_position(title, raw) if (title or raw) else ''
    if code:
        return {'code': code, 'title': title, 'source': 'карточка заявки'}
    # документы клиента (резюме/договор на Google Диске)
    own = {}
    # Резюме клиента с Диска источником профессии не служит: в папке лежали наши же
    # сборки с демо-профилем, из-за чего реальному клиенту доставалось чужое резюме.
    own = {}
    if own.get('code'):
        return {'code': own['code'], 'title': own.get('title') or '',
                'source': 'документы клиента'}
    return {'code': '', 'title': title, 'source': 'не найдена'}


def position_phrases(code: str, variable: str = '') -> list:
    """Готовые фразы («кусочки») по профессии: профиль, обязанности, навыки.

    Администратор отмечает нужные — из них собирается текст резюме.
    """
    p = position_by_code(code)
    if not p:
        return []
    out = []
    dom = DOMAIN_EN.get(code) or p.get('ru') or ''
    title = p.get('en') or ''
    if title and dom:
        out.append(f'{title} with extensive experience across {dom.lower()} environment.')
    blocks = p.get('blocks') or {}
    for level in ('short', 'medium', 'long'):
        for sent in split_bullets(blocks.get(level, '')):
            out.append(sent)
    sk = p.get('skills') or ''
    if sk:
        out.append(f'Skilled in {sk}.')
        out.append(f'Strong command of {sk}.')
    # убираем дубли, сохраняя порядок
    seen, uniq = set(), []
    for x in out:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append(x.strip())
    return uniq

RU_EN_WORDS = {
    'менеджер': 'Manager', 'продаж': 'Sales', 'продажам': 'Sales', 'продажи': 'Sales',
    'няня': 'Nanny', 'водитель': 'Driver', 'повар': 'Chef', 'официант': 'Waiter',
    'уборщик': 'Cleaner', 'уборщица': 'Cleaner', 'строитель': 'Construction Worker',
    'сиделка': 'Caregiver', 'администратор': 'Administrator', 'офис': 'Office',
    'бухгалтер': 'Accountant', 'дизайнер': 'Designer', 'парикмахер': 'Hairdresser',
    'массажист': 'Masseur', 'репетитор': 'Tutor', 'охранник': 'Security Guard',
    'промоутер': 'Promoter', 'курьер': 'Courier', 'бариста': 'Barista',
    'консультант': 'Consultant', 'мастер': 'Master', 'специалист': 'Specialist',
    'менеджер по продажам': 'Sales Manager', 'торговый представитель': 'Sales Representative',
    'специалист по уходу за детьми': 'Childcare Specialist', 'уход за пожилыми': 'Elderly Care',
    'клининг': 'Cleaning', 'рабочий': 'Worker', 'грузчик': 'Loader', 'кассир': 'Cashier',
    'швея': 'Seamstress', 'электрик': 'Electrician', 'сварщик': 'Welder', 'слесарь': 'Mechanic',
    'по': 'of', 'и': 'and', 'в': 'in', 'на': 'at', 'для': 'for',
}


def translate_title(title: str) -> str:
    """Английское название профессии для резюме: переводим известные слова."""
    full = (title or '').strip().lower()
    if full in RU_EN_WORDS:
        return RU_EN_WORDS[full]
    words = re.split(r'[\s\-]+', (title or '').strip())
    out = []
    for w in words:
        key = w.lower().strip('.,')
        out.append(RU_EN_WORDS.get(key, w))
    res = ' '.join(x for x in out if x)
    # если хотя бы одно слово переведено — считаем перевод удачным
    return res if any(w.lower().strip('.,') in RU_EN_WORDS for w in words) else title


def add_custom_position(title: str) -> dict:
    """Заводит профессию, которой нет в справочнике: генератор сразу умеет по ней писать.

    Администратор вписал профессию руками — система делает по ней заготовку описания
    (по той же формуле, что и для архивных профессий) и сохраняет в пул, чтобы
    профессия появилась в списке и переиспользовалась на других заявках.
    """
    import json
    import unicodedata
    t = (title or '').strip()
    if not t:
        raise ValueError('пустое название профессии')
    slug = re.sub(r'[^a-z0-9]+', '_', t.lower()).strip('_')
    if not slug:
        # кириллица — код собираем транслитом
        tr = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'zh', 'з': 'z',
              'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p',
              'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch',
              'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'}
        slug = ''.join(tr.get(ch, ch if ch.isalnum() else '_')
                       for ch in unicodedata.normalize('NFKC', t.lower()))
        slug = re.sub(r'_+', '_', slug).strip('_') or 'custom'
    code = 'custom_' + slug[:40]

    try:
        raw = json.loads(POSITIONS_FILE.read_text(encoding='utf-8'))
    except Exception:
        raw = []
    items = raw if isinstance(raw, list) else (raw.get('positions') or [])
    for it in items:
        if (it.get('code') or '') == code:
            # профессия уже есть — обновляем название и заготовку описания
            it['ru'] = t
            it['en'] = translate_title(t)
            it['keys'] = [t.lower(), slug.replace('_', ' ')]
            _blocks_for(it, t)
            _save(items, raw)
            _CACHE.pop('positions', None)
            return {'code': code, 'existed': True}
    entry = {'code': code, 'ru': t, 'en': translate_title(t),
             'keys': [t.lower(), slug.replace('_', ' ')], 'skills': '', 'custom': True}
    _blocks_for(entry, t)
    items.append(entry)
    _save(items, raw)
    _CACHE.pop('positions', None)   # сбрасываем кэш справочника
    return {'code': code, 'existed': False}


def _blocks_for(entry: dict, title: str) -> None:
    """Заготовка обязанностей по профессии (объёмы: короткий, средний, развёрнутый)."""
    en = entry.get('en') or title
    entry['blocks'] = {
        'short': f'Perform the core duties of a {en} in line with company standards '
                 f'and safety requirements.',
        'medium': f'Perform the core duties of a {en} in line with company standards and '
                  f'safety requirements. Maintain daily records, plan the working day and '
                  f'report to the supervisor.',
        'long': f'Perform the core duties of a {en} in line with company standards and safety '
                f'requirements. Maintain daily records, plan the working day and report to the '
                f'supervisor. Cooperate with colleagues and suppliers to keep the workflow '
                f'smooth. Train and support new staff when required.',
    }


def _save(items: list, raw) -> None:
    """Сохраняет справочник в файл, сохраняя его структуру."""
    import json as _json
    if isinstance(raw, list):
        POSITIONS_FILE.write_text(_json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    else:
        raw['positions'] = items
        POSITIONS_FILE.write_text(_json.dumps(raw, ensure_ascii=False, indent=1), encoding='utf-8')
