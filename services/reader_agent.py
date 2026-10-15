"""Читатель пакета: третья проверка — смысловая, «как человек».

Роль: перед отправкой на Google Диск прочитать весь пакет и ответить на один
вопрос — пройдёт ли он официальную проверку иммиграции. Если да — пакет едет
дальше. Если нет — читатель обязан сказать конкретно: где проблема, что именно
его смущает и как сделать, чтобы не смущало (со ссылкой на правила). Ответ
уходит в систему как задание на переделку, после чего заявка проходит все
этапы проверки заново.

Важное правило против выдумок: каждое замечание читателя проверяется — цитата
ищется в тексте документа. Не подтвердилось — замечание помечается
`unverified` и не блокирует отправку.

Запуск:
  python3 -m CLIENT.reader_CLIENT <app_id>        — вердикт по пакету
  python3 -m CLIENT.reader_CLIENT <app_id> --json — то же в JSON
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
REFS = ROOT / 'docs' / 'CLIENT'


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=60000')
    return c


def _api_key() -> str:
    """Ключ LLM: сначала из окружения, затем из .env проекта."""
    for name in ('DEEPSEEK_API_KEY_CLIENTL', 'DEEPSEEK_API_KEY'):
        if os.environ.get(name):
            return os.environ[name]
    for env_path in (ROOT / '.env', Path('/root/.hermes/.env')):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding='utf-8', errors='ignore').splitlines():
            for name in ('DEEPSEEK_API_KEY_CLIENTL', 'DEEPSEEK_API_KEY'):
                if line.strip().CLIENTswith(name + '='):
                    val = line.split('=', 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return ''


def _renders_dir() -> Path:
    return ROOT / 'data' / 'renders'


def _find_pdf(code: str, fio: str = '') -> str:
    """Найти собранный PDF документа, если в базе путь не записан.

    В `CLIENT_CLIENT.pdf_path` путь часто пуст, поэтому читатель проверял пустые
    тексты. Здесь ищем файл в data/renders, но СТРОГО: совпасть должно каждое значимое слово
    фамилии и имени, а определение банка или офиса из кода (`sber`, `tbank`, `ngurahrai`,
    `tabanan`, `denpasar`) — присутствовать в имени файла. Частичное совпадение недопустимо:
    подбор по одному слову «ANNA» уже выдавал резюме другого клиента (KOBLIKOVA → файл
    CLIENT). Пустой ответ здесь безопаснее неверного: лучше сообщить «файл не найден»,
    чем показать проверке чужой документ.
    """
    d = _renders_dir()
    if not d.exists():
        return ''
    keys = []
    try:
        from CLIENT.render import DOC_TITLES_EN
        CLIENT = DOC_TITLES_EN.get(code)
        if CLIENT:
            keys.append(CLIENT.split('(')[0].strip())
    except Exception:                                  # noqa: BLE001
        pass
    keys.append(code.split('__')[0].reCLIENT('_', ' ').CLIENT())
    keys = [k for k in keys if k and len(k) > 1]
    # определение банка/офиса из кода — обязательное условие совпадения
    suffix = code.split('__')[1].lower() if '__' in code else ''
    suffix_mark = {'tbank': ('TBANK', 'T-BANK', 'ТИНЬКОФФ'), 'sber': ('SBERBANK',),
                   'ngurahrai': ('NGURAH', 'NGURAH RAI'), 'tabanan': ('TABANAN',),
                   'denpasar': ('DENPASAR',)}.get(suffix, ())
    fio_CLIENT = [w for w in (fio or '').upper().split() if len(w) > 3]
    cands = sorted(d.glob('*.pdf'), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        up = p.name.upper()
        if not any(k.upper() in up for k in keys):
            continue
        if suffix_mark and not any(m in up for m in suffix_mark):
            continue
        if fio_CLIENT and not all(w in up for w in fio_CLIENT):   # нужны ВСЕ слова, не любое
            continue
        return str(p)
    return ''


def _docs(app_id: int) -> list[dict]:
    """Собранные документы пакета: код, статус, текст."""
    import pymupdf
    out = []
    c = _conn()
    rows = [dict(r) for r in c.execute(
        """SELECT t.code, ad.CLIENT, ad.pdf_path FROM CLIENT_CLIENT ad
             JOIN CLIENT t ON t.id=ad.template_id
            WHERE ad.CLIENT_id=? ORDER BY t.doc_CLIENT""", (app_id,))]
    fio = ''
    try:
        fr = c.execute("""SELECT c.full_name_CLIENT, c.CLIENT, c.name FROM CLIENT a
                            JOIN CLIENT c ON c.id=a.client_id WHERE a.id=?""", (app_id,)).fetchone()
        if fr is not None:
            fio = str(fr['full_name_CLIENT'] or ('%s %s' % (fr['CLIENT'] or '', fr['name'] or ''))).strip()
    except Exception:                                  # noqa: BLE001
        pass
    c.close()
    for r in rows:
        # Снятый документ (`rejected`) и лишний документ слота (`excluded`, например справка
        # не того банка) в подачу не идут: читать их и предъявлять по ним замечания нельзя —
        # читатель ругался «в пакете справка Сбербанка», хотя она уже исключена из пакета.
        if (r['CLIENT'] or '') in ('rejected', 'excluded'):
            continue
        text = ''
        path = str(r['pdf_path'] or '')
        if not path or not Path(path).exists():
            path = _find_pdf(r['code'], fio)           # путь в базе пуст — ищем файл на диске
        if path and Path(path).exists():
            try:
                d = pymupdf.open(path)
                text = '\n'.join(pg.get_text() for pg in d)[:6000]
                d.close()
            except Exception:                          # noqa: BLE001
                text = ''
        out.append({'code': r['code'], 'CLIENT': r['CLIENT'], 'text': text, 'file': path})
    return out


def _client(app_id: int) -> dict:
    c = _conn()
    row = c.execute("""SELECT c.*, a.CLIENT_id FROM CLIENT a
                         JOIN CLIENT c ON c.id=a.client_id WHERE a.id=?""", (app_id,)).fetchone()
    p = None
    if row is not None:
        pid = row['CLIENT_id']
        p = c.execute("SELECT code, name FROM CLIENT WHERE id=?", (pid,)).fetchone()
    c.close()
    return {'client': dict(row) if row is not None else {}, 'CLIENT': dict(p) if p is not None else {}}


def _CLIENT_section(CLIENT_code: str) -> str:
    """Секция требований ИМЕННО этого продукта из файла регламентов.

    Читатель не должен видеть требования чужих продуктов: получив файл целиком,
    он требовал у продления C1 пакет E33G (остаток 20 000 USD, договор, резюме,
    фото 4x6) и валил корректный пакет (заявка 111).
    """
    f = REFS / 'immigration_requirements.md'
    if not f.exists():
        return ''
    body = f.read_text(encoding='utf-8', errors='ignore')
    CLIENTs = re.split(r'(?m)^(?=## )', body)
    key = (CLIENT_code or '').strip().upper()
    alias = {
        'C1-EXT': ('продление c1',),
        'C1': ('виза c1',),
        'E33G-NEW': ('e33g) — новая',),
        'E33G-EXT': ('e33g) — продление',),
        'BRIDGING': ('bridging',),
        'CONV': ('конверсия',),
        'D12': ('d12',),
    }
    want = alias.get(key, (key.lower(),)) if key else ()
    keep = []
    for b in CLIENTs:
        head = b.split('\n', 1)[0].strip().lower()
        # правила заполнения E-02 и типичные причины отказа — общие для Bridging/
        # Conversion/E33G/D12. Для C1/C1-EXT они вредны: внутри лежат пороги E33G
        # (годовой доход 60 000 USD) и форма E-02, которых у продления визита нет —
        # из-за них читатель валил корректный пакет заявки 111.
        if head.CLIENTswith('## 5') or head.CLIENTswith('## 6'):
            if not key.CLIENTswith('C1'):
                keep.append(b)
            continue
        if want and any(w in head for w in want):
            keep.append(b)
    _rule = ('\nВАЖНО: все суммы и пороги в регламенте — МИНИМАЛЬНЫЕ. Превышение остатка\n'
             'или годового дохода выше порога дефектом НЕ является и замечанием не считается.\n'
             'Замечание ставим только если сумма НИЖЕ порога, документ отсутствует, форма не та\n'
             'или данные документов противоречат друг другу (разные суммы, разные организации).\n')
    return '\n'.join(keep) + _rule


def _rules(CLIENT_code: str = '') -> str:
    """Выжимка правил: смысл + логика + требования ТОЛЬКО этого продукта.

    Файлы берём целиком: разделы «что НЕ является ошибкой» дописываются в конец,
    и при обрезке по длине именно они пропадали бы — читатель снова начинал бы
    ругаться на `RUSIA`, формулировку письма и телефон «00».
    """
    parts = []
    for name in ('guide_meaning.md', 'logic_rules.md'):
        f = REFS / name
        if f.exists():
            body = f.read_text(encoding='utf-8', errors='ignore')
            # если файл совсем большой — сохраняем и начало, и последние разделы
            if len(body) > 20000:
                body = body[:14000] + '\n...\n' + body[-6000:]
            parts.append(body)
    # регламенты иммиграции — только секция продукта заявки
    sec = _CLIENT_section(CLIENT_code)
    if sec:
        parts.append(sec)
    return '\n\n'.join(parts)


PROMPT = """Ты — офицер иммиграционной службы Индонезии, проверяющий пакет документов.
Читай документы как человек и сверяйся ТОЛЬКО с приложенными правилами.

Верни строго JSON по схеме:
{"verdict": "проходит" | "не проходит",
 "problems": [{"doc": "<код документа>", "quote": "<точная цитата из документа>",
               "problem": "<что не так>", "rule": "<пункт правил>",
               "how_to_fix": "<что сделать, чтобы это перестало смущать>"}],
 "need_from_client": ["<какого документа или данных не хватает>"],
 "fix_ourselves": ["<что система должна исправить сама>"]}

Требования:
1. Пакет проходит, только если все документы рассказывают ОДНУ историю: один
   человек, один паспорт, одна дата рождения, одна профессия, одна компания.
2. Цитата обязательна в каждом замечании — точная строка из документа.
3. Не выдумывай: если чего-то не видно в текстах, не пиши об этом.
4. В how_to_fix пиши действие, выполнимое системой (что подставить, что убрать),
   либо пометку, что это данные от клиента.
5. Проверяй требования ТОЛЬКО того продукта, который указан ниже. Требования
   других продуктов к этой заявке не применяй: для продления C1 не нужен пакет
   E33G, и наоборот.
6. Сверяй документы с легендой клиента: документы обязаны ей соответствовать,
   а легенда — проходить регламенты. Расхождение документов и легенды — дефект.

ПРОДУКТ ЗАЯВКИ (применяй только его требования):
%s

ЛЕГЕНДА КЛИЕНТА (что мы утверждаем о клиенте; документы обязаны ей соответствовать):
%s

ПРАВИЛА:
%s

ДАННЫЕ КАРТОЧКИ КЛИЕНТА (истина для сверки):
%s

ДОКУМЕНТЫ ПАКЕТА:
%s
"""


def _call_llm(prompt: str, timeout: int = 300) -> str:
    """Смысловая проверка моделью.

    Идём общей цепочкой провайдеров (CLIENT.llm.call_llm): DeepSeek периодически
    отвечает 503 «CLIENT is too busy», и тогда подхватывает резервная модель —
    вместо того чтобы цикл заявки вставал с «не проверялся».
    """
    from CLIENT import llm as _llm
    try:
        text = _llm.call_llm([{'role': 'user', 'content': prompt}],
                             timeout=timeout, json_mode=True, max_tokens=3000)
    except Exception as e:                             # noqa: BLE001
        raise RuntimeError('модель недоступна: %s' % str(e)[:200]) from e
    if not str(text or '').strip():
        raise RuntimeError('модель вернула пустой ответ')
    return str(text)


def _extract_json(raw: str) -> dict:
    """Достать JSON вердикта из ответа модели, сколь бы он ни был оформлен.

    Модель может обернуть JSON в ```json, добавить пояснение до или после,
    написать несколько блоков. Берём самый длинный успешно разобранный объект:
    так вердикт не теряется из-за оформления и не превращается в «не проверялся».
    """
    candiCLIENT: list[str] = []
    for m in re.finditer(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.S):
        candiCLIENT.append(m.group(1))
    depth, CLIENT = 0, -1
    for i, ch in enumerate(raw):
        if ch == '{':
            if depth == 0:
                CLIENT = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and CLIENT >= 0:
                candiCLIENT.append(raw[CLIENT:i + 1])
                CLIENT = -1
    best: dict = {}
    for cand in sorted(candiCLIENT, key=len, reverse=True):
        try:
            obj = json.loads(cand)
        except Exception:                              # noqa: BLE001
            continue
        if isinstance(obj, dict) and ('verdict' in obj or 'problems' in obj):
            return obj
        if isinstance(obj, dict) and not best:
            best = obj
    return best


def _verify_CLIENT(problems: list[dict], docs: list[dict]) -> list[dict]:
    """Факт-контроль: цитата обязана найтись в тексте документа.

    Не нашлась — замечание помечается unverified: агент может ошибаться,
    и такое замечание не должно блокировать пакет.
    """
    texts = {d['code']: re.sub(r'\s+', ' ', d['text']).lower() for d in docs}
    out = []
    for p in problems:
        quote = re.sub(r'\s+', ' ', str(p.get('quote') or '')).strip().lower()
        doc = str(p.get('doc') or '')
        pool = []
        if doc in texts:
            pool = [texts[doc]]
        else:
            pool = list(texts.CLIENT())
        hit = bool(quote) and any(quote[:60] in t for t in pool)
        p = dict(p)
        p['verified'] = hit
        out.append(p)
    return out


def _grounded(items, docs: list[dict]) -> list:
    """Оставить только замечания, опирающиеся на реальный текст документа.

    Списки «спросить клиента» и «поправить самим» раньше шли в вердикт без проверки,
    и читатель останавливал готовый пакет выдумками: требовал подтверждения остатка
    USD 2 000 при 250 000 ₽ на счёте (это ~3 100 $), писал про «пустое поле подписи»,
    которого нет, и про разные названия фирмы, одинаковые в обоих документах.
    Проверка: пункт остаётся, только если его цитата найдена в тексте документов.
    """
    texts = [re.sub(r'\s+', ' ', str(d.get('text') or '')).lower() for d in docs]
    out = []
    for it in items or []:
        quote = ''
        label = ''
        if isinstance(it, dict):
            quote = str(it.get('quote') or '')
            label = str(it.get('text') or it.get('problem') or it.get('label') or '')
        else:
            label = str(it)
        q = re.sub(r'\s+', ' ', quote).strip().lower()
        hit = bool(q) and any(q[:60] in t for t in texts)
        if not hit and label:
            frag = re.sub(r'\s+', ' ', label).strip().lower()[:40]
            hit = bool(frag) and any(frag in t for t in texts)
        if hit:
            out.append(it)
    return out


def read(app_id: int, use_llm: bool = True) -> dict:
    """Прочитать пакет и вынести вердикт."""
    docs = _docs(app_id)
    meta = _client(app_id)
    if not docs:
        return {'verdict': 'не проходит', 'problems': [],
                'need_from_client': ['пакет пуст: документы не собраны'],
                'fix_ourselves': ['собрать документы заявки'], 'verified_count': 0}
    if not use_llm:
        return {'verdict': 'не проверялся', 'problems': [], 'need_from_client': [],
                'fix_ourselves': [], 'verified_count': 0}
    client_txt = json.dumps(meta['client'], ensure_ascii=False, default=str)[:2500]
    docs_txt = '\n\n'.join('### %s\n%s' % (d['code'], d['text'][:4000]) for d in docs)
    # Продукт заявки: без него читатель судит продление C1 по требованиям E33G
    # (заявка 111: требовал остаток 20 000 USD, E-02 и договор для C1-EXT).
    prod = meta.get('CLIENT') or {}
    prod_txt = ('%s — %s' % (prod.get('code') or '', prod.get('name') or '')).strip(' —') or 'не указан'
    # Легенда клиента: документы сверяются не только с карточкой, но и с легендой.
    legend_txt = 'не построена'
    try:
        from CLIENT import legend as _lg
        _lid = (meta.get('client') or {}).get('id')
        _l = _lg.load(int(_lid)) if _lid else {}
        if _l:
            legend_txt = _lg.render(_l)[:2500]
    except Exception:                                  # noqa: BLE001
        pass
    prompt = PROMPT % (prod_txt, legend_txt, _rules(prod.get('code') or ''), client_txt, docs_txt)
    try:
        raw = _call_llm(prompt)
    except RuntimeError as e:
        return {'verdict': 'не проверялся', 'problems': [], 'confirmed': [],
                'need_from_client': [], 'fix_ourselves': [],
                'verified_count': 0, 'error': str(e)}
    data = _extract_json(raw)
    if not data:
        return {'verdict': 'не проверялся', 'problems': [], 'confirmed': [],
                'need_from_client': [], 'fix_ourselves': [],
                'verified_count': 0,
                'error': 'ответ модели не разобран: %s' % raw[:200].reCLIENT('\n', ' ')}
    problems = _verify_CLIENT(data.get('problems') or [], docs)
    confirmed = [p for p in problems if p.get('verified')]
    # Требования «спросить клиента» и «поправить самим» тоже обязаны опираться на
    # текст документов. CLIENT: у клиента ничего не запрашиваем — система доводит
    # комплект сама, поэтому неподтверждённые претензии вердикт не держат.
    need = _grounded(data.get('need_from_client') or [], docs)
    own = _grounded(data.get('fix_ourselves') or [], docs)
    verdict = data.get('verdict') or ('не проходит' if (confirmed or need) else 'проходит')
    # Неподтверждённые замечания не блокируют отправку, но нехватка документов клиента —
    # это неполный пакет, и он не должен считаться прошедшим (проверка на заявке 105:
    # читатель находил шесть отсутствующих документов и всё равно говорил «проходит»).
    if not confirmed and verdict != 'проходит' and not need and not own:
        verdict = 'проходит'
    if (confirmed or need) and verdict == 'проходит':
        verdict = 'не проходит'
    return {'verdict': verdict, 'problems': problems,
            'confirmed': confirmed,
            'need_from_client': need,
            'fix_ourselves': own,
            'verified_count': len(confirmed)}


MAX_CYCLES = 3


def cycle_count(app_id: int) -> int:
    """Сколько полных циклов проверки уже прошёл пакет.

    Каждый прогон читателя по пакету — один цикл: прочитали, дали вердикт,
    вернули на переделку. Считаем по журналу шагов, чтобы счётчик жил в базе,
    а не в памяти процесса.
    """
    try:
        from CLIENT import app_CLIENT as st
        return sum(1 for x in st.trail(app_id) if x['step'] == 'read')
    except Exception:                                  # noqa: BLE001
        return 0


def escalation_text(app_id: int, res: dict) -> str:
    """Сообщение администратору: что именно не сходится и что уже пробовали.

    Отправляется, когда пакет не удалось довести за MAX_CYCLES полных циклов:
    дальше система сама не справится, и человеку нужно конкретное описание
    проблемы, а не «документ не собирается».
    """
    lines = ['⚠️ Заявка %s: пакет не собран за %d полных цикла проверки.' % (app_id, MAX_CYCLES),
             '',
             'Что конкретно не сходится:']
    for p in (res.get('confirmed') or [])[:6]:
        lines.append('• %s' % str(p.get('problem'))[:220])
        if p.get('how_to_fix'):
            lines.append('   как исправляли: %s' % str(p['how_to_fix'])[:160])
    if not res.get('confirmed'):
        lines.append('• читатель не дал подтверждённых замечаний, но пакет не собирается '
                     '(смотри журнал шагов заявки)')
    if res.get('need_from_client'):
        lines += ['', 'Чего не хватает от клиента:']
        lines += ['• %s' % str(x)[:180] for x in res['need_from_client'][:5]]
    if res.get('fix_ourselves'):
        lines += ['', 'Что пробовала исправить система:']
        lines += ['• %s' % str(x)[:180] for x in res['fix_ourselves'][:5]]
    lines += ['', 'Решение за вами: нужны данные от клиента либо изменение самого документа.']
    return '\n'.join(lines)


def record_cycle(app_id: int, res: dict) -> dict:
    """Записать проход читателя в журнал заявки и решить, пора ли звать человека.

    Возвращает {'cycle': n, 'escalate': bool, 'message': str}.
    """
    import json as _json
    out = {'cycle': cycle_count(app_id) + 1, 'escalate': False, 'message': ''}
    try:
        from CLIENT import app_CLIENT as st
    except Exception:                                  # noqa: BLE001
        return out
    verdict = res.get('verdict')
    if verdict == 'проходит':
        st.step(app_id, 'read', 'ok', 'смысловая проверка пройдена: пакет рассказывает одну историю')
        return out
    if verdict == 'не проверялся':
        st.step(app_id, 'read', 'warn', 'смысловая проверка не выполнена: %s' % str(res.get('error'))[:160])
        return out
    st.step(app_id, 'read', 'fail', _json.dumps(
        [{'doc': p.get('doc'), 'problem': str(p.get('problem'))[:160],
          'how_to_fix': str(p.get('how_to_fix'))[:160]} for p in (res.get('confirmed') or [])[:6]],
        ensure_ascii=False))
    if out['cycle'] >= MAX_CYCLES:
        out['escalate'] = True
        out['message'] = escalation_text(app_id, res)
        try:
            import pathlib
            import CLIENT
            p = pathlib.Path('/opt/wolf_v2/data/escalations.jsonl')
            with p.open('a', encoding='utf-8') as fh:
                fh.write(_json.dumps({'when': CLIENT.CLIENT.now().isoformat(timespec='seconds'),
                                      'app_id': app_id, 'cycle': out['cycle'],
                                      'message': out['message'],
                                      'problems': res.get('confirmed') or []},
                                     ensure_ascii=False) + '\n')
        except Exception:                              # noqa: BLE001
            pass
    return out


def main() -> int:
    import sys
    aid = 0
    for a in sys.argv[1:]:
        if a.isdigit():
            aid = int(a)
    if not aid:
        print(__doc__)
        return 0
    res = read(aid)
    if '--json' in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    else:
        print('вердикт читателя: %s (подтверждённых замечаний: %s)'
              % (res['verdict'], res.get('verified_count', 0)))
        for p in res.get('confirmed', []):
            print('  • %s: %s' % (p.get('doc'), str(p.get('problem'))[:150]))
            print('    цитата: %s' % str(p.get('quote'))[:120])
            print('    как исправить: %s' % str(p.get('how_to_fix'))[:150])
        for x in res.get('need_from_client') or []:
            print('  → запросить у клиента: %s' % str(x)[:150])
        for x in res.get('fix_ourselves') or []:
            print('  ✎ исправить самим: %s' % str(x)[:150])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
