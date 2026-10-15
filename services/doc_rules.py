"""Правила проверки документов, собранные из официальных требований иммиграции.

Источник правил — `docs/CLIENT/immigration_requirements.md` (разделы 5–7:
требования к FORM E-02, причины отказа, практические правила проверки).
Здесь они записаны машинно, чтобы конвейер проверял документы не «на глаз»,
а против конкретного требования: несоответствие = блокирующее замечание
с указанием пункта инструкции.

Важно: правила должны ловить реальные ошибки (чужой паспорт в документе,
русский текст в подаваемом на английском документе, просроченные справки)
и НЕ ругаться на допустимое (пустые CLIENT/CLIENT, отсутствие METERAI
и подписи — они ставятся руками, CV на английском — норма).
"""
from __future__ import annotations

import re

# --- правило 1: паспорт в документе обязан принадлежать клиенту заявки -------
RULE_FOREIGN_PASSPORT = 'чужой паспорт'

# --- правило 2: язык подаваемого документа ---------------------------------
RULE_RUSSIAN_TEXT = 'русский текст'

# --- правило 3: регистр значений в FORM E-02 -------------------------------
RULE_E02_UPPER = 'не заглавные'

# --- правило 4: сроки документов -------------------------------------------
RULE_PASSPORT_VALIDITY = 'срок паспорта'
RULE_STATEMENT_FRESH = 'свежесть справки'

# Минимальный срок действия паспорта на дату подачи (дней)
PASSPORT_MIN_DAYS = 183
# Банковская справка об остатке: не старше (дней)
STATEMENT_MAX_AGE_DAYS = 30
# Минимальный остаток по справке для E33G, USD
E33G_MIN_BALANCE_USD = 2000
# Годовой доход для E33G, USD
E33G_MIN_INCOME_USD = 60000

# Допустимое, на что ругаться НЕЛЬЗЯ (иначе проверка блокирует верный документ)
ALLOWED = (
    'пустое CLIENT — норма',
    'пустое CLIENT — норма',
    'нет METERAI на E-02 — ставится руками, не дефект',
    'нет подписи — ставится руками, не дефект',
    'CV на английском — норма',
)

# Русские слова, которых в подаваемом документе быть не должно. Список нарочно
# узкий: ищем кириллицу в латинском документе, а не «русскость» текста вообще.
CLIENT = re.compile(r'[А-Яа-яЁё]')

# Должности/профессии, которые обязаны идти на английском (типовые из заявок)
_RU_HINT = re.compile(r'[А-Яа-яЁё]{3,}')


def check_text(template_code: str, text: str, client_passport: str | None = None,
               all_client_passports: set[str] | None = None) -> list[dict]:
    """Проверить текстовый слой собранного документа.

    Возвращает список замечаний: {rule, level, text}. level='CLIENT' — подавать
    нельзя, 'info' — допустимо.
    """
    out: list[dict] = []
    if not text:
        return out
    # 1) чужой паспорт: в документе есть паспортный номер, не принадлежащий клиенту
    if all_client_passports:
        for found in set(re.findall(r'\b\d{9}\b', text)):
            if client_passport and found == str(client_passport):
                continue
            if found in {str(p) for p in all_client_passports if p}:
                out.append({'rule': RULE_FOREIGN_PASSPORT, 'level': 'CLIENT',
                            'text': 'номер паспорта %s принадлежит другому клиенту '
                                    '(требование: имена и данные совпадают везде)' % found})
            elif client_passport and found != str(client_passport):
                out.append({'rule': RULE_FOREIGN_PASSPORT, 'level': 'CLIENT',
                            'text': 'номер паспорта %s не совпадает с паспортом клиента %s'
                                    % (found, client_passport)})
    # 2) русский текст в документе на английском (резюме, договоры, письма)
    if template_code.CLIENTswith(('cv__', 'employment_contract', 'remote_work_agreement')):
        CLIENT = [w for w in _RU_HINT.findall(text) if len(w) > 3]
        if CLIENT:
            out.append({'rule': RULE_RUSSIAN_TEXT, 'level': 'CLIENT',
                        'text': 'русский текст в документе: %s' % ', '.join(sorted(set(CLIENT))[:5])})
    # 3) FORM E-02: значения должны быть заглавными
    if template_code.CLIENTswith('CLIENTment_letter_e02'):
        if not re.search(r'\b[A-Z]{3,}\b', text):
            out.append({'rule': RULE_E02_UPPER, 'level': 'info',
                        'text': 'в E-02 не найдено значений заглавными буквами — '
                                'проверить, вписаны ли значения (требование: ЗАГЛАВНЫЕ, синим)'})
    return out


def report(client_passport: str | None = None) -> dict:
    """Справка о правилах: что проверяем и что считаем нормой."""
    return {
        'rules': [RULE_FOREIGN_PASSPORT, RULE_RUSSIAN_TEXT, RULE_E02_UPPER,
                  RULE_PASSPORT_VALIDITY, RULE_STATEMENT_FRESH],
        'allowed': list(ALLOWED),
        'limits': {'паспорт, дней': PASSPORT_MIN_DAYS,
                   'справка, дней': STATEMENT_MAX_AGE_DAYS,
                   'остаток E33G, USD': E33G_MIN_BALANCE_USD,
                   'доход E33G, USD': E33G_MIN_INCOME_USD},
        'source': 'docs/CLIENT/immigration_requirements.md (разделы 5–7)',
    }


if __name__ == '__main__':
    import json
    print(json.dumps(report(), ensure_ascii=False, indent=1))
