#!/usr/bin/env python3
"""Происхождение значений переменных.

Заказчик (правило для ВСЕХ документов и переменных):
  real    — значение взято из реальных документов клиента → подсветка зелёным,
            в панели пишем, где именно оно найдено;
  synth   — значение собрано системой по правилам (пулы организаций, должностей,
            кусочков) или сформировано по шаблону → подсветка жёлтым,
            такие переменные требует проверить администратор;
  unknown — систему не смогла определить значение → подсветка красным.

Пустых переменных быть не должно: если данных нет, значение собирается по цепочке
город рождения (из паспорта) → учебное заведение → должность → организация из пула →
описание профессии. Такое значение помечается как synth.
"""

# Фактические данные: их можно взять только из документов/карточки — они не выдумываются.
DOC_FIELDS = {
    'full_name', 'client_name', 'cv_name', 'employee_name', 'full_name_latin',
    'employee_full_name', 'employee_full_name_latin', 'employee_name_latin', 'for_name',
    'surname', 'name', 'patronymic', 'full_name_title',
    'birth_date', 'date_of_birth', 'place_of_birth', 'birth_place',
    'nationality', 'citizenship', 'gender',
    'passport_series', 'passport_number', 'passport_no', 'passport_issued_by',
    'passport_issue_date', 'passport_expiry', 'intl_passport',
    'inn', 'snils', 'phone', 'email',
    'address_reg', 'address_live', 'address_zip', 'city', 'country',
    'client_photo', 'client_photo_url',
    'education_school', 'education_degree', 'education_years',
    'job1_title', 'job1_company', 'job1_period', 'job1_bullets',
    'job2_title', 'job2_company', 'job2_period', 'job2_bullets',
    'job3_title', 'job3_company', 'job3_period',
    'company_name', 'company_llc', 'company_address', 'company_inn',
    'position', 'salary_amount',
}

# Служебные и сгенерированные поля: номер, маска карты, балансы, периоды.
SYNTH_FIELDS = {
    'doc_no', 'ref_no', 'card_mask', 'doc_date',
    'balance_rub', 'balance_value', 'balance_words', 'balance_cents',
    'period_from', 'period_to', 'bank_name', 'bank_phone', 'bank_manager_name',
    'iban', 'account_no', 'agreement_date', 'agreement_start_date', 'agreement_end_date',
    'salary_currency',
}

DOC_NOTE = 'документы клиента (Google Drive)'
PASSPORT_NOTE = 'паспорт клиента'
POOL_NOTE = 'собрано системой по правилам (пул организаций, должностей, кусочков)'
RULE_NOTE = 'сформировано системой по правилу документа'


def _txt(value) -> str:
    return '' if value is None else str(value).strip()


def value_origin(name: str, value, client: dict | None = None) -> tuple:
    """(kind, note) — откуда взялось значение переменной."""
    name = (name or '').strip()
    if not _txt(value):
        return ('unknown', 'значение не определено — нужна проверка администратором')
    if name in DOC_FIELDS:
        return ('real', PASSPORT_NOTE if name in (
            'birth_date', 'date_of_birth', 'place_of_birth', 'birth_place',
            'nationality', 'citizenship', 'gender', 'passport_series',
            'passport_number', 'passport_no', 'passport_issued_by',
            'passport_issue_date', 'passport_expiry', 'full_name', 'client_name',
            'cv_name', 'full_name_latin') else DOC_NOTE)
    if name in SYNTH_FIELDS or name.startswith(('balance_', 'period_')):
        return ('synth', RULE_NOTE)
    if name.startswith('cv_'):
        if name in ('cv_name', 'cv_place_of_birth', 'cv_date_of_birth', 'cv_nationality',
                    'cv_passport_no', 'cv_education_city'):
            return ('real', PASSPORT_NOTE)
        return ('synth', POOL_NOTE)
    # остальное: сгенерировано кубиком или выбрано из выпадающего списка — зелёным не помечаем
    return ('synth', 'подставлено системой или выбрано из списка — проверьте')


def sources_for(values: dict, client: dict | None = None) -> dict:
    """{имя переменной: (kind, note)} — для подсветки строк в панели переменных."""
    return {k: value_origin(k, v, client) for k, v in (values or {}).items()}


def kind_label(kind: str) -> str:
    return {'real': '🟢', 'synth': '🟡', 'unknown': '🔴'}.get(kind, '⚪')
