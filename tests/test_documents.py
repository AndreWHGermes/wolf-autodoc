#!/usr/bin/env python3
"""Этап 8: тесты на то, где у нас рождались дефекты.

Запуск:  /usr/bin/python3 tests/run_tests.py
Тесты написаны в стиле pytest (функции test_*), поэтому позже можно запускать и через pytest.
Работают на КОПИИ базы: ни рабочие данные, ни версии не затрагиваются.
"""
from pathlib import Path

V2 = Path('/opt/wolf_v2')

# ── подготовка окружения до импорта модулей проекта ────────────────────────────
import os  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix='wolf_tests_'))
shutil.copy2(V2 / 'data/wolf.db', TMP / 'wolf.db')
for f in (V2 / 'data').glob('wolf.db-*'):
    shutil.copy2(f, TMP / f.name)
os.environ['WOLF_DB'] = str(TMP / 'wolf.db')
os.environ['WOLF_BASE'] = str(V2)
sys.path.insert(0, str(V2))

from core import db  # noqa: E402
from services import render as doc_render  # noqa: E402
from services import values as values_service  # noqa: E402

TEMPLATES = V2 / 'data' / 'templates'   # рабочая сборка v2 (v1 — только эталон)
CYR = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'


# ── данные клиента не берём из общего пула ─────────────────────────────────────
def test_personal_vars_never_from_pool():
    """Индивидуальные поля (паспорт, счёт, баланс) не заполняются чужими данными."""
    db.exec_sql("INSERT INTO clients(surname, name, created_at) VALUES('Проверка','Тест',datetime('now'))")
    row = db.q1("SELECT id FROM clients WHERE surname='Проверка' ORDER BY id DESC LIMIT 1")
    client = dict(db.q1("SELECT * FROM clients WHERE id=?", (row['id'],)) or {})
    vals = values_service.build_template_values(client, 'bank_statement_3m__tbank')
    # значения из архива чужих документов (пул) брать нельзя; сгенерированное по правилу — можно
    pool = {r['variable_name']: (r['value'] or '').strip()
            for r in db.q("SELECT variable_name, MAX(used_count), value FROM variable_value_history GROUP BY variable_name")}
    for field in ('passport_number', 'account_no', 'balance_rub', 'card_mask', 'contract_no'):
        got = (vals.get(field) or '').strip()
        assert got != pool.get(field), f'{field} взят из пула чужих значений: {got!r}'
    db.exec_sql("DELETE FROM clients WHERE id=?", (row['id'],))


def test_common_vars_may_come_from_pool():
    """Типовые поля (банк, компания, сроки) из пула брать можно."""
    client = dict(db.q1("SELECT * FROM clients ORDER BY id LIMIT 1") or {})
    vals = values_service.build_template_values(client, 'bank_statement_3m__tbank')
    filled = [k for k in ('bank_name', 'bank_inn', 'period_from', 'period_to') if (vals.get(k) or '').strip()]
    assert filled, 'типовые поля не заполнились даже из пула'


# ── расчёты ────────────────────────────────────────────────────────────────────
def test_amount_in_words():
    words = values_service._num2words_en(1946508)
    assert 'million' in words and 'five hundred' in words, words


def test_term_dates_plus_one_year():
    client = {'agreement_date': '18.09.2019'}
    vals = values_service.build_template_values(client, 'remote_work_agreement__default')
    if vals.get('term_end_date'):
        assert '2020' in vals['term_end_date'], vals['term_end_date']


def test_translit_and_latin_name():
    assert values_service._translit('Краснодарский край').upper().startswith('KRASNODAR')
    latin = values_service._fio_latin({'surname': 'Маркарова', 'name': 'Анна'})
    assert 'CLIENT' in latin.upper(), latin


# ── рендер документа ───────────────────────────────────────────────────────────
def test_render_fills_all_placeholders():
    html = '<p>{{ full_name_latin }} / {{ passport_number }}</p>'
    out = doc_render.fill(html, {'full_name_latin': 'CLIENT_048', 'passport_number': '0315 000000000'})
    assert '{{' not in out and 'CLIENT_048' in out and '0315 000000000' in out


def test_render_no_cyrillic_for_client_data():
    """Английский документ не должен получить русские данные клиента."""
    html = '<p>{{ full_name_latin }}</p>'
    out = doc_render.fill(html, {'full_name_latin': 'Маркарова Анна'})
    assert not any(ch.lower() in CYR for ch in out), f'кириллица в документе: {out}'


# ── сами шаблоны ───────────────────────────────────────────────────────────────
def test_templates_have_no_cyrillic():
    """Тот самый дефект: русский текст с комментариями, попавший в бланк."""
    bad = []
    for f in TEMPLATES.glob('*/template.html'):
        text = f.read_text(encoding='utf-8')
        body = ''.join(ch for ch in text if ch.lower() in CYR)
        if body:
            bad.append((f.parent.name, body[:40]))
    assert not bad, f'кириллица в шаблонах: {bad}'


def test_bank_statements_kopeks_are_variable():
    """Сумма и её пропись в справках — только переменные: жёсткого «00 kopeks/cents» быть не должно."""
    bad = []
    for f in TEMPLATES.glob('bank_statement_*/template.html'):
        text = f.read_text(encoding='utf-8')
        for hard in ('00 kopeks', '00 cents', '0 kopeks', '0 cents'):
            if hard in text:
                bad.append((f.parent.name, hard))
        if '{{ balance_rub }}' not in text and '{{balance_rub}}' not in text:
            bad.append((f.parent.name, 'нет {{ balance_rub }}'))
    assert not bad, f'жёсткая сумма в шаблонах: {bad}'


def test_conversion_letters_differ():
    """Письма Ngurah Rai и Denpasar — разные документы, а не копии."""
    a = (TEMPLATES / 'conversion_request_letter__ngurahrai/template.html').read_text(encoding='utf-8')
    b = (TEMPLATES / 'conversion_request_letter__denpasar/template.html').read_text(encoding='utf-8')
    assert a != b, 'письма снова стали одинаковыми'
    assert 'Ngurah Rai' in a and 'Denpasar' in b


# ── необязательные строки (реквизиты договора) ────────────────────────────────
def test_optional_lines_disappear_without_data():
    """Строка реквизитов исчезает, если данных нет, и остаётся, если есть — как в образцах."""
    tpl = '<p>a</p><!--optional--><div>Contract number: {{ contract_no }}</div><!--/optional--><p>z</p>'
    without = doc_render.fill(tpl, {'contract_no': ''})
    with_data = doc_render.fill(tpl, {'contract_no': 'ABC-1'})
    assert 'Contract' not in without, without
    assert 'ABC-1' in with_data, with_data


def test_bank_templates_have_optional_contract_lines():
    """Строки реквизитов (счёт/контракт) в справках, если есть, помечены как необязательные."""
    bad = []
    for f in TEMPLATES.glob('bank_statement_*/template.html'):
        text = f.read_text(encoding='utf-8')
        low = text.lower()
        for marker in ('date of conclusion', 'contract number', 'account number'):
            if marker in low and '<!--optional-->' not in text:
                bad.append((f.parent.name, marker))
    assert not bad, f'реквизиты без пометки необязательности: {bad}'
