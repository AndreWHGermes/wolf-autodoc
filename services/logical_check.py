#!/usr/bin/env python3
"""Логическая проверка данных пакета документов заявки.

Работает перед отправкой на Google Диск вместе с технической проверкой (services/pdf_quality):
техническая смотрит, КАК напечатано (наложения, фон, обрезка), а эта — ЧТО напечатано:
совпадают ли ФИО, даты, номера, суммы в разных документах и с карточкой клиента.

Правила (BLOCK — не отправлять, WARN — отправить можно, но есть вопрос к администратору):
  R1  чужой человек: в документах заявки нет фамилий других клиентов;
  R2  дата рождения: совпадает с карточкой, возраст 18-70, формат даты верный;
  R3  паспорт: номер и срок действия совпадают с карточкой, срок в будущем,
      выдача раньше срока действия, срок позже даты договора;
  R4  даты документов: не в будущем, дата договора не раньше выдачи паспорта,
      даты писем не раньше даты договора, срок договора не меньше года;
  R5  деньги: оклад в границах агентства, месяц = год / 12, цифры и пропись согласованы;
  R6  организация: одна и та же во всех документах и вне Индонезии;
  R7  сквозные поля (гражданство, место рождения, номер и срок ITK) одинаковы везде;
  R8  форматы: паспорт — цифры, ITK — буквы/цифры/дефис, суммы с валютой;
  R9  офис иммиграции соответствует адресу клиента;
  R10 должность не выдумана (есть в пуле должностей или в карточке клиента).

Журнал: data/reports/logical_checks.jsonl

Запуск: /usr/bin/python3 services/logical_check.py <app_id> [--no-save]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'wolf.db'
LOG = ROOT / 'data' / 'reports' / 'logical_checks.jsonl'
READY = ROOT / 'data' / 'ready'

# границы агентства по окладу (рубли)
SALARY_YEAR_MIN, SALARY_YEAR_MAX = 4_980_000, 7_680_000
SALARY_MONTH_MIN, SALARY_MONTH_MAX = 415_000, 640_000
TODAY = date.today()

DATE_RX = re.compile(r'\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b')
MONEY_RX = re.compile(r'(\d[\d\s,.]{5,})\s*(?:RUB|IDR|₽|руб)', re.IGNORECASE)
PASSPORT_RX = re.compile(r'\b(\d{6,9})\b')
ITK_RX = re.compile(r'\b([A-Z0-9]{6,}[-\s]?[A-Z0-9]{0,6})\b')
INDONESIA_MARKS = ('INDONESIA', 'JAKARTA', 'BALI', 'DENPASAR', 'KABUPATEN', 'KECAMATAN',
                   'NPWP', 'PT PMA', 'NIB', 'TANGERANG', 'SURABAYA')


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def parse_date(s: str) -> date | None:
    m = DATE_RX.search(s or '')
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def norm_num(s: str) -> int | None:
    digits = re.sub(r'\D', '', s or '')
    return int(digits) if digits else None


class Checker:
    def __init__(self, app_id: int):
        self.app_id = app_id
        self.finds: list[dict] = []
        self.docs: list[dict] = []

    def add(self, level: str, rule: str, doc: str, msg: str, fix: str = '') -> None:
        self.finds.append({'level': level, 'rule': rule, 'doc': doc, 'msg': msg, 'fix': fix})

    # ---------- сбор данных ----------
    def load(self) -> bool:
        c = _conn()
        app = c.execute('SELECT * FROM applications WHERE id=?', (self.app_id,)).fetchone()
        if not app:
            return False
        self.app = dict(app)
        cl = c.execute('SELECT * FROM clients WHERE id=?', (self.app['client_id'],)).fetchone()
        self.client = dict(cl) if cl else {}
        rows = c.execute('''SELECT t.code, t.title, ad.template_id FROM application_documents ad
                            JOIN templates t ON t.id = ad.template_id
                            WHERE ad.application_id=? ORDER BY t.code''', (self.app_id,)).fetchall()
        self.templates = [dict(r) for r in rows]
        # тексты готовых документов заявки: имена файлов берём у сборки, а не по догадке
        surname = (self.client.get('surname') or '').strip().upper()
        code_words = {r['code']: [w for w in r['code'].split('__')[0].split('_') if len(w) > 3] for r in rows}
        texts = {}
        for r in rows:
            code = r['code']
            path = None
            # документы заявки опознаются по фамилии клиента в имени файла:
            # в папке готовых лежат и старые файлы-заглушки вида <code>.pdf
            for p in sorted(READY.glob('*.pdf'), key=lambda q: -q.stat().st_mtime):
                nm = p.name.upper()
                if surname and surname in nm:
                    if any(w.upper() in nm for w in code_words.get(code, [])) or code.split('__')[0][:6].upper() in nm:
                        path = p
                        break
            if not path:
                continue
            try:
                import pymupdf
                doc = pymupdf.open(str(path))
                texts[code] = '\n'.join(pg.get_text() for pg in doc)
            except Exception:
                continue
        self.texts = texts
        return True

    def all_text(self) -> str:
        return '\n'.join(self.texts.values())

    # ---------- правила ----------
    def r1_foreign_names(self) -> None:
        c = _conn()
        mine = (self.client.get('surname') or '').upper()
        # Своё имя/отчество — не «чужое»: в базе встречаются карточки, где имя клиента
        # попало в поле «фамилия» другого человека, и проверка ловила клиента на себе же.
        mine_parts = {(self.client.get(k) or '').upper().strip()
                      for k in ('surname', 'name', 'patronymic', 'full_name_latin')}
        mine_parts = {p for p in mine_parts if len(p) > 2}
        known = set()
        for r in c.execute('SELECT surname FROM clients WHERE surname IS NOT NULL AND surname != ""'):
            s = (r['surname'] or '').upper().strip()
            if s and s != mine and len(s) > 2 and s not in mine_parts:
                known.add(s)
        text = self.all_text().upper()
        for name in sorted(known):
            if name in mine_parts:
                continue
            if re.search(r'\b%s\b' % re.escape(name), text):
                self.add('BLOCK', 'R1', '-', 'в документах встречается чужое имя: %s' % name,
                         'убрать значение из шаблона или из карточки клиента')

    def r2_birth(self) -> None:
        bd = parse_date(self.client.get('birth_date') or '')
        if not bd:
            self.add('WARN', 'R2', '-', 'в карточке клиента нет даты рождения — сверить не с чем')
            return
        age = (TODAY - bd).days // 365
        if not 18 <= age <= 70:
            self.add('BLOCK', 'R2', '-', 'возраст по дате рождения: %d лет (вне 18-70)' % age)
        for code, t in self.texts.items():
            for m in DATE_RX.finditer(t):
                d = parse_date(m.group(0))
                if d and d == bd:
                    break
            else:
                self.add('WARN', 'R2', code, 'дата рождения клиента (%s) в документе не найдена'
                         % self.client.get('birth_date'))

    def r3_passport(self) -> None:
        num = norm_num(self.client.get('passport_number') or '')
        exp = parse_date(self.client.get('passport_expiry') or '')
        iss = parse_date(self.client.get('passport_issue_date') or '')
        if exp and exp <= TODAY:
            self.add('BLOCK', 'R3', '-', 'срок действия паспорта (%s) уже истёк' % exp.strftime('%d.%m.%Y'))
        if iss and exp and iss >= exp:
            self.add('BLOCK', 'R3', '-', 'паспорт выдан позже срока действия (%s -> %s)'
                     % (iss.strftime('%d.%m.%Y'), exp.strftime('%d.%m.%Y')))
        if iss and exp:
            years = (exp - iss).days / 365
            if years > 10.5:
                self.add('WARN', 'R3', '-', 'срок действия паспорта %.1f лет — больше обычных 10' % years)
        if num:
            found = False
            for code, t in self.texts.items():
                if str(num) in re.sub(r'\D', '', t) or str(num) in t:
                    found = True
            if not found:
                self.add('WARN', 'R3', '-', 'номер паспорта %s не найден ни в одном документе' % num)
        # ловушка перепутанных дат: дата рождения на месте срока действия и наоборот
        bd = parse_date(self.client.get('birth_date') or '')
        if bd and exp:
            t = self.all_text()
            wrong = 0
            for m in DATE_RX.finditer(t):
                d = parse_date(m.group(0))
                if not d:
                    continue
                ctx = t[max(0, m.start() - 160):m.start()].lower()
                if ('masa berlaku paspor' in ctx or 'passport expiry' in ctx
                        or 'passport valid' in ctx or 'срок действия паспорта' in ctx):
                    if d == bd:
                        wrong += 1
                    elif d != exp:
                        self.add('WARN', 'R3', '-', 'в поле срока паспорта стоит %s, в карточке %s'
                                 % (d.strftime('%d.%m.%Y'), exp.strftime('%d.%m.%Y')))
            if wrong:
                self.add('BLOCK', 'R3', '-', 'в поле «срок действия паспорта» стоит дата рождения (%s)'
                         % bd.strftime('%d.%m.%Y'), 'исправить подстановку поля')
        if exp and not re.search(r'(?i)(masa berlaku paspor|passport expiry|passport valid|'
                                 r'срок действия паспорта|дата окончания паспорта)', self.all_text()):
            self.add('WARN', 'R3', '-', 'срок действия паспорта (%s) ни в одном документе не напечатан'
                     % exp.strftime('%d.%m.%Y'), 'проверить, требуется ли срок в этом пакете')

    def r4_dates(self) -> None:
        t = self.all_text()
        contract_date = parse_date(self.client.get('contract_date') or '') or \
            parse_date(self.app.get('created_at') or '')
        for m in DATE_RX.finditer(t):
            d = parse_date(m.group(0))
            if d and d > TODAY:
                ctx = t[max(0, m.start() - 70):m.start() + 30].replace('\n', ' ')
                if 'date:' in ctx.lower() or 'дата' in ctx.lower() or 'sign' in ctx.lower():
                    self.add('WARN', 'R4', '-', 'дата документа в будущем: %s (…%s…)'
                             % (d.strftime('%d.%m.%Y'), ctx.strip()[-52:]))
        iss = parse_date(self.client.get('passport_issue_date') or '')
        if contract_date and iss and contract_date < iss:
            self.add('WARN', 'R4', '-', 'дата договора (%s) раньше выдачи паспорта (%s)'
                     % (contract_date.strftime('%d.%m.%Y'), iss.strftime('%d.%m.%Y')))
        years = re.findall(r'(\d{1,2})\s*(?:year|years|лет|года)', t, re.IGNORECASE)
        if years and max(int(y) for y in years) < 1:
            self.add('WARN', 'R4', '-', 'срок договора меньше года')

    def r5_money(self) -> None:
        t = self.all_text()
        year_sums, month_sums = [], []
        for m in MONEY_RX.finditer(t):
            val = norm_num(m.group(1))
            if not val:
                continue
            if 4_000_000 <= val <= 9_000_000:
                year_sums.append(val)
            elif 300_000 <= val <= 800_000:
                month_sums.append(val)
        for v in set(year_sums):
            if not SALARY_YEAR_MIN <= v <= SALARY_YEAR_MAX:
                self.add('BLOCK', 'R5', '-', 'годовой оклад %s ₽ вне границ %s-%s'
                         % (f'{v:,}'.replace(',', ' '), f'{SALARY_YEAR_MIN:,}'.replace(',', ' '),
                            f'{SALARY_YEAR_MAX:,}'.replace(',', ' ')))
        for v in set(month_sums):
            if not SALARY_MONTH_MIN <= v <= SALARY_MONTH_MAX:
                self.add('BLOCK', 'R5', '-', 'месячный оклад %s ₽ вне границ %s-%s'
                         % (f'{v:,}'.replace(',', ' '), f'{SALARY_MONTH_MIN:,}'.replace(',', ' '),
                            f'{SALARY_MONTH_MAX:,}'.replace(',', ' ')))
        for y in set(year_sums):
            expected = round(y / 12)
            if not any(abs(expected - m) <= 5000 for m in month_sums):
                self.add('WARN', 'R5', '-', 'месячная сумма не согласована с годовой: %s / 12 = %s'
                         % (f'{y:,}'.replace(',', ' '), f'{expected:,}'.replace(',', ' ')))
        if year_sums and not re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,}', t):
            self.add('WARN', 'R5', '-', 'сумма напечатана только цифрами — прописью не найдена')

    def r6_company(self) -> None:
        # Проверяем только те документы, где работодателя подставляем МЫ (договор): там он обязан
        # быть вне Индонезии. В письмах и справках индонезийская компания — это спонсор клиента
        # (например, Alih Sponsor по D12), и стоп по нему останавливал цикл на ровном месте.
        OWN_DOCS = ('employment_contract', 'remote_work_agreement')
        own_text = '\n'.join(t for code, t in self.texts.items()
                             if any(h in str(code) for h in OWN_DOCS))
        names = set()
        for m in re.finditer(r'(?:LLC|LTD|OOO|ООО|ИП|PT)\s+[«"\']?([A-ZА-Я0-9][\w\s«»"\'\-]{2,40})', own_text, re.IGNORECASE):
            raw = re.sub(r'[^A-ZА-Я0-9\s]', ' ', m.group(1).upper())
            words = [w for w in raw.split() if len(w) > 2][:3]
            if words:
                names.add(' '.join(words))
        if len(names) > 1:
            self.add('WARN', 'R6', '-', 'в документах упоминаются разные организации: %s'
                     % '; '.join(sorted(names)[:4]))
        for name in names:
            for mark in INDONESIA_MARKS:
                if mark in name:
                    self.add('BLOCK', 'R6', '-', 'организация работодателя внутри Индонезии: %s' % name,
                             'работодатель должен быть вне Индонезии')
                    break

    def r7_cross(self) -> None:
        exp = parse_date(self.client.get('passport_expiry') or '')
        if not exp:
            return
        seen = set()
        for code, t in self.texts.items():
            for m in DATE_RX.finditer(t):
                d = parse_date(m.group(0))
                if d and d.year >= 2026 and d != exp:
                    ctx = t[max(0, m.start() - 80):m.start()].lower()
                    if 'masa berlaku paspor' in ctx or 'passport expiry' in ctx:
                        seen.add(d.strftime('%d.%m.%Y'))
        if seen:
            self.add('BLOCK', 'R7', '-', 'срок паспорта расходится по документам: %s'
                     % ', '.join(sorted(seen)), 'во всех документах срок должен совпадать')

    def r8_formats(self) -> None:
        t = self.all_text()
        nums = [norm_num(self.client.get('passport_number') or '')]
        for m in PASSPORT_RX.finditer(t):
            v = m.group(1)
            if len(v) in (7, 8) and not re.match(r'^(19|20)\d\d$', v):
                nums.append(int(v))
        itk = re.findall(r'\b([A-Z]\d[A-Z0-9]{6,}[-\s]?[A-Z0-9]{0,4})\b', t)
        if not itk:
            self.add('WARN', 'R8', '-', 'номер ITK в документах не найден')

    def r9_office(self) -> None:
        t = self.all_text().upper()
        addr = (self.client.get('address_live') or '').upper()
        if not addr:
            return
        denpasar_area = any(k in addr for k in ('GIANYAR', 'UBUD', 'DENPASAR', 'KLUNGKUNG',
                                                'BANGLI', 'KARANGASEM'))
        if denpasar_area and 'NGURAH RAI' in t and 'DENPASAR' not in t:
            self.add('WARN', 'R9', '-', 'адрес клиента (%s) — зона офиса Denpasar, а документ оформлен на Ngurah Rai'
                     % self.client.get('address_live')[:40])
        if not denpasar_area and 'DENPASAR' in t and 'NGURAH RAI' not in t:
            self.add('WARN', 'R9', '-', 'адрес клиента — зона Ngurah Rai, а документ оформлен на Denpasar')

    def r10_position(self) -> None:
        pos = (self.client.get('position') or '').strip()
        if not pos:
            self.add('WARN', 'R10', '-', 'в карточке клиента не указана должность')
            return
        pool_file = ROOT / 'data' / 'organizations.json'
        pool_ok = False
        if pool_file.exists():
            try:
                data = json.loads(pool_file.read_text(encoding='utf-8'))
                raw = json.dumps(data, ensure_ascii=False).upper()
                pool_ok = any(w.upper() in raw for w in re.split(r'[\s/]+', pos) if len(w) > 3)
            except Exception:
                pool_ok = False
        if not pool_ok:
            self.add('WARN', 'R10', '-', 'должность «%s» не найдена в пуле организаций' % pos)

    # ---------- запуск ----------
    def run(self) -> dict:
        if not self.load():
            return {'ok': False, 'app_id': self.app_id, 'finds': [
                {'level': 'BLOCK', 'rule': '-', 'doc': '-', 'msg': 'заявка не найдена', 'fix': ''}]}
        for step in (self.r1_foreign_names, self.r2_birth, self.r3_passport, self.r4_dates,
                     self.r5_money, self.r6_company, self.r7_cross, self.r8_formats,
                     self.r9_office, self.r10_position):
            try:
                step()
            except Exception as e:  # правило не должно ронять весь прогон
                self.add('WARN', step.__name__, '-', 'правило не отработало: %s' % str(e)[:80])
        blocks = [f for f in self.finds if f['level'] == 'BLOCK']
        warns = [f for f in self.finds if f['level'] == 'WARN']
        return {'ok': not blocks, 'app_id': self.app_id, 'blocks': len(blocks), 'warns': len(warns),
                'docs': sorted(self.texts), 'finds': self.finds,
                'checked_at': datetime.now().isoformat(timespec='seconds')}

    def save(self, verdict: dict) -> None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(verdict, ensure_ascii=False) + '\n')


def check_app(app_id: int, save: bool = True) -> dict:
    v = Checker(app_id).run()
    c = _conn()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS logical_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER, checked_at TEXT,
            ok INTEGER, blocks INTEGER, warns INTEGER, report TEXT)''')
        c.execute('INSERT INTO logical_checks (application_id, checked_at, ok, blocks, warns, report)'
                  ' VALUES (?,?,?,?,?,?)',
                  (app_id, v['checked_at'], 1 if v['ok'] else 0, v.get('blocks', 0),
                   v.get('warns', 0), json.dumps(v['finds'], ensure_ascii=False)))
        c.commit()
    except Exception:
        pass
    if save:
        Checker(app_id).save(v)
    return v


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print('укажите номер заявки')
        return 1
    v = check_app(int(args[0]), save='--no-save' not in sys.argv)
    print('ЛОГИЧЕСКАЯ ПРОВЕРКА заявки %s: %s' % (v['app_id'], 'ГОТОВО' if v['ok'] else 'ЕСТЬ КОНФЛИКТЫ'))
    print('   документов проверено:', len(v.get('docs', [])), '| блоков:', v.get('blocks'), '| замечаний:', v.get('warns'))
    for f in v['finds']:
        if f['level'] == 'BLOCK':
            print('   [СТОП] %s %s: %s' % (f['rule'], f['doc'], f['msg']))
    for f in v['finds'][:6]:
        if f['level'] == 'WARN':
            print('   [внимание] %s %s: %s' % (f['rule'], f['doc'], f['msg']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
