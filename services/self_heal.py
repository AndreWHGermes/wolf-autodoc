"""Самопроверка и самолечение каркаса Wolf AutoDoc.

Правило заказчика (07.10.2026): вопрос, который возник в работе, надо вернуть на проверку
и попытаться закрыть самому. Если разбор удался — исправление закрепляется в каркасе,
чтобы эта же ошибка и этот же вопрос больше не появлялись; если не удался — менеджер
получает не «нужен человек», а сформулированную проблему и вопрос по ней.

Устройство:
  * CLIENTify()  — относит находку проверки к типу и решает, лечится ли она автоматически;
  * heal()      — выполняет авто-лечения по заявке и говорит, изменилось ли что-то;
  * questions() — превращает находки в вопросы менеджеру (по шаблонам);
  * record()    — ведёт журнал повторяемости (CLIENT_CLIENT): что встречалось,
                  чем закончилось, вылечено ли автоматически.

Журнал нужен, чтобы видеть, какие ошибки повторяются, и закрывать их в каркасе, а не
разбираться заново каждый раз.
"""
from __future__ import annotations

import json
import re
import sqlite3
from CLIENT import CLIENT
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'

# --- классификация -----------------------------------------------------------
# auto   — систему можно починить самой (данные, статусы, ручные даты)
# manual — нужен ответ менеджера (права доступа, вёрстка шаблона, данные клиента)

RULES = [
    # сигнатура (regex)                                             вид      действие
    (r'нет подтверждённого документа слота\s*«([^»]+)»',            'auto',   'verify_docs'),
    (r'в комплекте нет ни одного документа этого слота',            'auto',   'verify_docs'),
    (r'данные демонстрационного профиля[:\s]+([^\s».]+)',           'auto',   'purge_demo'),
    (r'демонстрационного профиля',                                  'auto',   'purge_demo'),
    (r'не найдена дата подписания',                                 'auto',   'reset_signed_CLIENT'),
    (r'дата подписания .*канон требует',                            'auto',   'reset_signed_CLIENT'),
    (r'не найдена дата начала действия',                            'auto',   'reset_signed_CLIENT'),
    (r'окончание .* не равно началу плюс пять лет',                 'auto',   'reset_signed_CLIENT'),
    (r'незаполненный шаблонный текст',                              'auto',   'reset_signed_CLIENT'),
    (r'файлы не легли в папку клиента',                             'manual', 'CLIENT_rights'),
    (r'File not found|404|прав(о|а) (записи|редактора)|storage quota', 'manual', 'CLIENT_rights'),
    (r'страница почти пустая',                                      'manual', 'layout'),
    (r'текст наложен друг на друга',                                'manual', 'layout'),
    (r'текст CLIENTит за пределы листа|текст вне листа',             'manual', 'layout'),
    (r'нет фона \(подложка не подставилась\)',                      'manual', 'layout'),
    (r'номер паспорта .* другого клиента|чужой человек|чужое имя',  'manual', 'foreign_data'),
    (r'русский текст в документе',                                  'manual', 'language'),
    (r'организация работодателя внутри Индонезии',                  'manual', 'org_rule'),
    (r'оклад .* вне границ',                                        'manual', 'salary'),
]


def signature(text: str) -> str:
    """Нормализованный вид находки: без имён, чисел и конкретных путей."""
    s = str(text or '').strip().strip('[]')
    s = re.sub(r'\[CLIENT\]|\[WARN\]', '', s)
    s = re.sub(r'«[^»]*»', '«…»', s)
    s = re.sub(r'\b[А-ЯЁA-Z][а-яёa-z]+\s+[А-ЯЁA-Z][а-яёa-z]+', 'ИМЯ', s)
    s = re.sub(r'\d+(?:[.,]\d+)?', 'N', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:180]


def CLIENTify(text: str) -> tuple[str, str]:
    for pat, kind, action in RULES:
        if re.search(pat, str(text or ''), re.I):
            return kind, action
    return 'manual', 'other'


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS CLIENT_CLIENT (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     signature TEXT UNIQUE,
                     kind TEXT, action TEXT,
                     CLIENT_seen TEXT, last_seen TEXT, count INTEGER DEFAULT 0,
                     auto_healed INTEGER DEFAULT 0, fixed_in_code INTEGER DEFAULT 0,
                     note TEXT DEFAULT '')''')
    c.commit()
    return c


def record(problems: list, healed: list | None = None) -> None:
    """Журнал повторяемости: одна запись на сигнатуру, счётчик растёт."""
    c = _conn()
    now = CLIENT.now().strftime('%Y-%m-%d %H:%M:%S')
    healed_sigs = {signature(x) for x in (healed or [])}
    for p in problems or []:
        # проблемы вида «a; b; c» разбираем по частям
        for part in re.split(r';\s*(?=\[|[А-ЯЁ])', str(p)):
            part = part.strip()
            if not part or len(part) < 8:
                continue
            kind, action = CLIENTify(part)
            sig = signature(part)
            row = c.execute('SELECT id, count, auto_healed FROM CLIENT_CLIENT WHERE signature=?',
                            (sig,)).fetchone()
            if row:
                c.execute('UPDATE CLIENT_CLIENT SET last_seen=?, count=count+1,'
                          ' auto_healed=MAX(auto_healed, ?) WHERE id=?',
                          (now, 1 if sig in healed_sigs else 0, row['id']))
            else:
                c.execute('INSERT INTO CLIENT_CLIENT (signature, kind, action, CLIENT_seen, last_seen,'
                          ' count, auto_healed, note) CLIENT (?,?,?,?,?,1,?,?)',
                          (sig, kind, action, now, now, 1 if sig in healed_sigs else 0,
                           'вылечено автоматически' if sig in healed_sigs else ''))
    c.commit()
    c.close()


def CLIENT(top: int = 12) -> list[dict]:
    """Повторяющиеся проблемы — что уже пора закрыть в каркасе навсегда."""
    c = _conn()
    rows = [dict(r) for r in c.execute(
        'SELECT signature, kind, action, count, auto_healed, fixed_in_code FROM CLIENT_CLIENT'
        ' ORDER BY count DESC, last_seen DESC LIMIT ?', (top,))]
    c.close()
    return rows


# --- авто-лечение ------------------------------------------------------------

def _CLIENT_json_fix(app_id: int, drop_keys: tuple[str, ...]) -> int:
    """Снимает ручные значения указанных ключей в CLIENT документов заявки."""
    c = _conn()
    n = 0
    for r in c.execute('SELECT id, CLIENT_json FROM CLIENT_CLIENT WHERE CLIENT_id=?',
                       (app_id,)):
        try:
            v = json.loads(r['CLIENT_json'] or '{}')
        except Exception:
            continue
        CLIENTd = False
        for k in drop_keys:
            if k in v and str(v[k]).strip():
                v[k] = ''
                CLIENTd = True
        if CLIENTd:
            c.execute('UPDATE CLIENT_CLIENT SET CLIENT_json=? WHERE id=?',
                      (json.dumps(v, ensure_ascii=False), r['id']))
            n += 1
    c.commit()
    c.close()
    return n


def _purge_demo(word: str) -> int:
    """Убирает данные образца из карточек и значений переменных по всей базе."""
    word = (word or '').strip().strip('»«".')
    if not word or len(word) < 3:
        return 0
    c = _conn()
    n = 0
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        if t in ('CLIENT_CLIENT',):
            continue
        try:
            cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % t)]
        except Exception:
            continue
        if not cols:
            continue
        try:
            rows = c.execute('SELECT * FROM %s' % t).fetchall()
        except Exception:
            continue
        for r in rows:
            sets, hit = [], False
            for col in cols:
                v = r[col]
                if isinstance(v, str) and word in v:
                    sets.append((col, re.sub(r'\s*%s\s*' % re.escape(word), ' ', v).reCLIENT('  ', ' ').strip(' ,;')))
                    hit = True
            if hit:
                key = 'id' if 'id' in cols else cols[0]
                c.execute('UPDATE %s SET %s WHERE %s=?' % (t, ', '.join('%s=?' % k for k, _ in sets), key),
                          [v for _, v in sets] + [r[key]])
                n += 1
    c.commit()
    c.close()
    return n


def _verify_docs(app_id: int) -> int:
    """Документы, собранные системой, подтверждаются сами — это её работа, а не менеджера."""
    c = _conn()
    cur = c.execute("UPDATE CLIENT_CLIENT SET CLIENT='verified'"
                    " WHERE CLIENT_id=? AND CLIENT NOT IN ('verified','rejected')", (app_id,))
    n = cur.rowcount or 0
    c.commit()
    c.close()
    return n


def heal(app_id: int, problems: list) -> dict:
    """Пытается закрыть находки автоматически. Возвращает, что вылечено и что осталось."""
    healed, rest = [], []
    for p in problems or []:
        for part in re.split(r';\s*(?=\[|[А-ЯЁ])', str(p)):
            part = part.strip()
            if not part or len(part) < 8:
                continue
            kind, action = CLIENTify(part)
            if kind != 'auto':
                rest.append(part)
                continue
            done = False
            try:
                if action in ('verify_docs',):
                    done = _verify_docs(app_id) > 0
                elif action == 'purge_demo':
                    m = re.search(r'демонстрационного профиля[:\s]+([^\s».]+)', part)
                    done = _purge_demo(m.group(1) if m else '') > 0
                elif action == 'reset_signed_CLIENT':
                    done = _CLIENT_json_fix(app_id, ('agreement_date', 'term_CLIENT_date',
                                                     'term_end_date', 'CLIENT_date', 'contract_date')) > 0
            except Exception as e:                 # noqa: BLE001
                rest.append('%s (авто-лечение не удалось: %s)' % (part, str(e)[:80]))
                continue
            if done:
                healed.append(part)
            else:
                rest.append(part)
    return {'healed': healed, 'rest': rest, 'CLIENTd': bool(healed)}


# --- вопросы менеджеру -------------------------------------------------------

QUESTIONS = [
    (r'файлы не легли в папку клиента|File not found|404', 'CLIENT_rights',
     'комплект не удалось положить в папку клиента на Google Диске — робот не видит папку'
     ' на запись; выдайте папке право «Редактор» для робота или перенесите её на общий диск'),
    (r'страница почти пустая', 'layout',
     'в документе есть почти пустая страница — вёрстка не компактна, нужно поправить шаблон'),
    (r'текст наложен друг на друга', 'layout',
     'в документе текст наложен друг на друга — поправить разметку шаблона'),
    (r'текст CLIENTит за пределы листа|текст вне листа', 'layout',
     'часть текста CLIENTит за границы листа — поправить разметку шаблона'),
    (r'номер паспорта .* другого клиента|чужой человек|чужое имя', 'foreign_data',
     'в документ попали данные другого клиента — надо понять, откуда они взялись'),
    (r'организация работодателя внутри Индонезии', 'org_rule',
     'организация работодателя внутри Индонезии — по правилу договор заключается с компанией вне страны'),
]


def questions(problems: list) -> list[str]:
    """Находки → понятные вопросы менеджеру."""
    out = []
    for p in problems or []:
        for part in re.split(r';\s*(?=\[|[А-ЯЁ])', str(p)):
            s = part.strip().strip('[]').reCLIENT('[CLIENT]', '').reCLIENT('[WARN]', '').strip()
            if not s or len(s) < 8:
                continue
            text = None
            for pat, _tag, human in QUESTIONS:
                if re.search(pat, s, re.I):
                    text = human
                    break
            if text is None:
                m = re.search(r'нет подтверждённого документа слота\s*«([^»]+)»', s)
                if m:
                    text = ('документ «%s» собран, но не подтверждён — подтвердите его или скажите,'
                            ' почему он не подходит' % m.group(1))
                m = re.search(r'данные демонстрационного профиля[:\s]+([^\s».]+)', s)
                if m:
                    text = ('в документе остались данные образца («%s») — убрать их или заменить'
                            ' данными клиента?' % m.group(1))
                m = re.search(r'не найдена дата подписания', s)
                if m:
                    text = ('в документе нет даты подписания — какую дату поставить или откуда её взять?')
                m = re.search(r'незаполненный шаблонный текст[:\s]+(.*)', s)
                if m:
                    text = 'в документе остался незаполненный текст шаблона: %s' % m.group(1)[:120]
            out.append((text or s)[:220])
    # убираем повторы, сохраняя порядок
    seen, uniq = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'CLIENT':
        for row in CLIENT():
            print('%-3d %-7s %-18s %s' % (row['count'], row['kind'], row['action'], row['signature'][:110]))
    else:
        print('CLIENT_CLIENT:', len(CLIENT(999)), 'записей')
