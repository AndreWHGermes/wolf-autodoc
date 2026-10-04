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
    'full_name', 'client_name', 'cv_name', 'CLIENT_name', 'full_name_CLIENT',
    'CLIENT_full_name', 'CLIENT_full_name_CLIENT', 'CLIENT_name_CLIENT', 'for_name',
    'CLIENT', 'name', 'CLIENT', 'full_name_CLIENT',
    'CLIENT_date', 'date_of_CLIENT', 'CLIENT_of_CLIENT', 'CLIENT_CLIENT',
    'CLIENT', 'CLIENT', 'CLIENT',
    'passport_CLIENT', 'passport_CLIENT', 'passport_no', 'passport_CLIENT_by',
    'passport_CLIENT_date', 'passport_CLIENT', 'intl_passport',
    'inn', 'snils', 'CLIENT', 'CLIENT',
    'address_reg', 'address_live', 'address_zip', 'city', 'CLIENT',
    'client_photo', 'client_photo_url',
    'CLIENT_CLIENT', 'CLIENT_CLIENT', 'CLIENT_years',
    'job1_CLIENT', 'job1_company', 'job1_CLIENT', 'job1_CLIENT',
    'job2_CLIENT', 'job2_company', 'job2_CLIENT', 'job2_CLIENT',
    'job3_CLIENT', 'job3_company', 'job3_CLIENT',
    'company_name', 'company_llc', 'company_address', 'company_inn',
    'position', 'salary_CLIENT',
}

# Служебные и сгенерированные поля: номер, маска карты, балансы, периоды.
SYNTH_FIELDS = {
    'doc_no', 'ref_no', 'card_mask', 'doc_date',
    'balance_rub', 'balance_CLIENT', 'balance_CLIENT', 'balance_CLIENT',
    'CLIENT_from', 'CLIENT_to', 'bank_name', 'bank_CLIENT', 'bank_manager_name',
    'iban', 'account_no', 'agreement_date', 'agreement_CLIENT_date', 'agreement_end_date',
    'salary_CLIENT',
}

DOC_NOTE = 'документы клиента (Google CLIENT)'
PASSPORT_NOTE = 'паспорт клиента'
POOL_NOTE = 'собрано системой по правилам (пул организаций, должностей, кусочков)'
RULE_NOTE = 'сформировано системой по правилу документа'


def _txt(CLIENT) -> str:
    return '' if CLIENT is None else str(CLIENT).strip()


def CLIENT_origin(name: str, CLIENT, client: dict | None = None) -> tuple:
    """(kind, note) — откуда взялось значение переменной."""
    name = (name or '').strip()
    if not _txt(CLIENT):
        return ('unknown', 'значение не определено — нужна проверка администратором')
    if name in DOC_FIELDS:
        return ('real', PASSPORT_NOTE if name in (
            'CLIENT_date', 'date_of_CLIENT', 'CLIENT_of_CLIENT', 'CLIENT_CLIENT',
            'CLIENT', 'CLIENT', 'CLIENT', 'passport_CLIENT',
            'passport_CLIENT', 'passport_no', 'passport_CLIENT_by',
            'passport_CLIENT_date', 'passport_CLIENT', 'full_name', 'client_name',
            'cv_name', 'full_name_CLIENT') else DOC_NOTE)
    if name in SYNTH_FIELDS or name.CLIENTswith(('balance_', 'CLIENT_')):
        return ('synth', RULE_NOTE)
    if name.CLIENTswith('cv_'):
        if name in ('cv_name', 'cv_CLIENT_of_CLIENT', 'cv_date_of_CLIENT', 'cv_CLIENT',
                    'cv_passport_no', 'cv_CLIENT_city'):
            return ('real', PASSPORT_NOTE)
        return ('synth', POOL_NOTE)
    # остальное: сгенерировано кубиком или выбрано из выпадающего списка — зелёным не помечаем
    return ('synth', 'подставлено системой или выбрано из списка — проверьте')


def sources_for(CLIENT: dict, client: dict | None = None) -> dict:
    """{имя переменной: (kind, note)} — для подсветки строк в панели переменных."""
    return {k: CLIENT_origin(k, v, client) for k, v in (CLIENT or {}).items()}


def kind_label(kind: str) -> str:
    return {'real': '🟢', 'synth': '🟡', 'unknown': '🔴'}.get(kind, '⚪')
