"""Смысловые блоки документа: что за кусок текста прочитан и что в нём лежит.

Задача, которую решает модуль: между «мы прочитали текст» и «мы поставили
значение в переменную» должен быть ещё один слой — понимание, из какого
информационного блока взято значение.

Пример для банковской справки: это не «просто текст», а блок «банк»
(название, лицензия), блок «клиент» (ФИО, адрес), блок «карта» (маска),
блок «сумма» (остаток цифрами и прописью, валюта, дата остатка),
блок «период», блок «подписи и исполнитель», блок «исходящие» (ref, номер).

Каждый блок описывает СВОИ переменные. Значение, найденное в тексте,
сначала приписывается блоку, и только потом — нашей переменной. Тогда
в карточке видно не «номер 220050…1293», а «маска карты ← блок «карта
клиента» ← файл BankStatement.pdf».

Запуск для проверки:  python3 -m services.doc_blocks <файл> [тип]
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')


@dataclass
class BlockSpec:
    """Описание смыслового блока: как его найти и что в нём искать."""
    code: str
    title: str                       # человеческое название для карточки
    purpose: str                     # зачем этот блок в нашей работе
    markers: tuple = ()              # подстроки, по которым блок начинается
    vars: tuple = ()                 # наши переменные, которые живут в блоке


@dataclass
class Block:
    """Найденный в документе блок: границы, текст, источник."""
    spec: BlockSpec
    start: int
    end: int
    text: str
    found: bool = True
    source: str = "rule"             # rule | llm | none

    @property
    def name(self) -> str:
        return self.spec.code


# ---------------------------------------------------------------- паспорт РФ
PASSPORT = [
    BlockSpec("person", "Личные данные", "ФИО, дата и место рождения, гражданство, пол",
              ("фамилия", "surname", "имя / given", "given names"), ("surname", "name",
               "patronymic", "surname_latin", "name_latin", "full_name_latin",
               "birth_date", "birth_place", "citizenship", "client_gender")),
    BlockSpec("document", "Данные документа", "серия, номер, дата выдачи, кем выдан, срок",
              ("паспорт / passport", "номер паспорта", "passport no", "выдан", "issued by"),
              ("passport_series", "passport_number", "passport_no", "passport_issue_date",
               "passport_issued_by", "passport_expiry")),
    BlockSpec("mrz", "Машиночитаемая зона", "самый надёжный источник номера и даты рождения",
              ("p<rus", "p<"),
              ("passport_number", "birth_date", "passport_series")),
    BlockSpec("registration", "Регистрация", "адрес по месту жительства",
              ("зарегистрирован", "место жительства", "registration"),
              ("address_reg", "address_live")),
]

# ----------------------------------------------------- карточка ВНЖ (ITK/КИТАС)
ITK = [
    BlockSpec("permit", "Разрешение на пребывание", "номер и срок действия ВНЖ",
              ("permit number", "stay permit expiry", "stay permit index"),
              ("itk_no", "stay_permit_no", "itk_expiry", "stay_permit_expiry",
               "existing_stay_permit")),
    BlockSpec("person", "Личные данные", "ФИО, дата и место рождения, гражданство, пол",
              ("name", "place / date of birth", "nationality", "gender"),
              ("surname", "name", "full_name_latin", "birth_date", "birth_place",
               "place_birth_inline", "citizenship", "nationality", "client_gender")),
    BlockSpec("passport", "Паспорт иностранца", "номер и срок паспорта, страна",
              ("passport number", "passport expiry", "nomor paspor"),
              ("passport_number", "passport_no", "passport_expiry")),
    BlockSpec("address", "Адрес в Индонезии", "место фактического пребывания",
              ("address", "alamat"),
              ("address_in_indonesia",)),
    BlockSpec("sponsor", "Спонсор и гарант", "кто отвечает за пребывание",
              ("sponsor", "guarantor", "penjamin"),
              ("sponsor_name", "sponsor_address")),
]

# ------------------------------------------------------ справка банка об остатке
BANK_BALANCE = [
    BlockSpec("bank", "Банк", "банк, с которым работает клиент, его реквизиты и лицензия",
              ("tbank", "сбербанк", "sberbank", "universal license", "bank of russia"),
              ("bank_name", "bank_license", "bank_address")),
    BlockSpec("client", "Клиент", "ФИО и адрес владельца счёта",
              ("hereby informs", "has been issued for", "клиент", "home address",
               "registration address"),
              ("full_name_latin", "full_name_ru", "address_live", "address_reg")),
    BlockSpec("card", "Карта и счёт", "номер счёта и маска карты",
              ("card no", "account", "счет", "счёт", "iban"),
              ("card_mask", "account_no")),
    BlockSpec("amount", "Сумма и остаток", "остаток цифрами и прописью, валюта, дата остатка",
              ("available balance", "остаток", "balance", "amount of available"),
              ("balance_rub", "balance_words", "balance_date", "currency")),
    BlockSpec("dogovor", "Договор с банком", "когда заключён и под каким номером",
              ("date of conclusion of the contract", "contract number", "договор"),
              ("contract_no", "contract_date")),
    BlockSpec("period", "Период", "за какой срок показаны данные",
              ("as from", "movement of funds", "период", "period"),
              ("period_from", "period_to")),
    BlockSpec("operations", "Операции по счёту", "таблица движения: даты, суммы, назначения",
              ("date and time of the transaction", "date of the transaction", "операция"),
              ("movement_count", "moves", "credits_total", "debits_total")),
    BlockSpec("outgoing", "Исходящие реквизиты", "номер и дата письма банка, ссылка",
              ("ref.", "№", "no ", "date"),
              ("ref_no", "ref_date", "doc_no", "statement_date")),
    BlockSpec("signature", "Подпись и исполнитель", "кто подписал справку и печать банка",
              ("signature", "подпись", "исполнитель", "authorized"),
              ("signed_by", "signature_position")),
]

# ------------------------------------------------------------- выписка о движении
BANK_MOVEMENT = [
    BlockSpec("account", "Счёт", "по какому счёту выписка",
              ("contract", "счёт", "account"),
              ("account_no",)),
    BlockSpec("period", "Период выписки", "с какой по какую дату операции",
              ("period", "за период", "from", "to"),
              ("period_from", "period_to")),
    BlockSpec("operations", "Операции", "даты, суммы, назначения платежей",
              ("date", "operation", "дата", "сумма"),
              ("movement_count", "moves", "biggest_credits")),
    BlockSpec("totals", "Итоги", "обороты за период: поступления и списания",
              ("total", "итого", "оборот"),
              ("credits_total", "debits_total", "credits_count", "debits_count")),
]

# ------------------------------------------------------ договор клиента / офер
CONTRACT = [
    BlockSpec("parties", "Стороны", "кто работодатель, кто работник, реквизиты",
              ("parties", "between", "company", "стороны", "employee"),
              ("company_name", "company_tax_id", "employee_name")),
    BlockSpec("subject", "Предмет и должность", "что за работа и на какой должности",
              ("position", "должность", "subject", "duties", "обязанности"),
              ("position", "duties", "employment_type")),
    BlockSpec("payment", "Оплата", "сумма, валюта, порядок выплат",
              ("salary", "оклад", "payment", "remuneration", "зарплата"),
              ("salary_amount", "salary_currency", "payment_terms")),
    BlockSpec("term", "Срок и подписи", "дата заключения, срок, подписанты",
              ("term", "срок", "date of", "signature", "подпис"),
              ("contract_no", "contract_date", "contract_term", "signed_by")),
]

# ------------------------------------------------------------ виза (eVisа Индонезии)
VISA = [
    BlockSpec("visa", "Виза", "номер визы, тип, срок действия, кем выдана",
              ("visa no", "nomor visa", "visa type", "evisa", "limited stay visa"),
              ("visa_no", "bridging_visa_no", "visa_type", "date_of_issue",
               "valid_until", "reference_no")),
    BlockSpec("person", "Личные данные", "ФИО, дата и место рождения, гражданство, пол",
              ("name", "date of birth", "place of birth", "nationality", "sex"),
              ("surname", "name", "full_name_latin", "birth_date", "place_of_birth",
               "citizenship", "nationality", "client_gender")),
    BlockSpec("issuer", "Кто выдал", "иммиграционная служба и её подразделение",
              ("kementerian imigrasi", "direktorat jenderal imigrasi", "issued by"),
              ("issued_by", "issuing_office")),
]


BLOCKS_BY_KIND = {
    "passport": PASSPORT,
    "itk": ITK,
    "visa": VISA,
    "bank_balance": BANK_BALANCE,
    "bank_movement": BANK_MOVEMENT,
    "contract": CONTRACT,
    "resume": CONTRACT,
    "other": BANK_BALANCE + PASSPORT,
}


def _marker_pos(low: str, marker: str) -> int:
    """Где начинается маркер блока.

    Ищем по словам, а не цельной строкой: в распознанном тексте фраза почти
    всегда разорвана переносом строки («Date and time of the\n transaction»),
    и поиск подстроки такой маркер не находит вовсе.
    """
    words = [re.escape(w) for w in str(marker).lower().split()]
    if not words:
        return -1
    m = re.search(r"\s+".join(words), low)
    return m.start() if m else -1


def segment(text: str, kind: str) -> list[Block]:
    """Нарезать документ на смысловые блоки по маркерам начала.

    Блок тянется от своего маркера до маркера следующего блока. Если маркер
    не найден — блок помечается найденным=false: это значит, что в документе
    такого раздела нет (или распознавание его не прочитало) и переменные
    этого блока брать неоткуда.
    """
    specs = BLOCKS_BY_KIND.get(kind) or BLOCKS_BY_KIND["other"]
    t = text or ""
    low = t.lower()

    starts = []
    for spec in specs:
        pos = None
        for m in spec.markers:
            p = _marker_pos(low, m)
            if p >= 0 and (pos is None or p < pos):
                pos = p
        starts.append((pos if pos is not None else len(low) + 1, spec))

    order = sorted(range(len(starts)), key=lambda i: starts[i][0])
    blocks: list[Block] = []
    for n, idx in enumerate(order):
        pos, spec = starts[idx]
        if pos > len(low):
            blocks.append(Block(spec, -1, -1, "", found=False, source="none"))
            continue
        nxt = len(low)
        for j in order[n + 1:]:
            if starts[j][0] <= len(low):
                nxt = min(nxt, starts[j][0])
                break
        blocks.append(Block(spec, pos, nxt, t[pos:nxt].strip()))
    return blocks


def describe(text: str, kind: str) -> list[dict]:
    """Человеческое описание разбора: что за блоки есть и что в них искать."""
    out = []
    for b in segment(text, kind):
        out.append({
            "code": b.spec.code,
            "title": b.spec.title,
            "purpose": b.spec.purpose,
            "vars": list(b.spec.vars),
            "found": b.found,
            "chars": len(b.text),
            "excerpt": re.sub(r"\s+", " ", b.text)[:160],
        })
    return out


def assign(values: dict, text: str, kind: str) -> dict:
    """Приписать каждое найденное значение к блоку, в тексте которого оно стоит.

    Это и есть ответ на вопрос «из какого информационного блока мы это взяли».
    Значение без блока не теряется: оно помечается как «блок не определён» —
    такие случаи нужно видеть, потому что это признак ошибки разбора.
    """
    blocks = [b for b in segment(text, kind) if b.found]
    result = {}
    for var, val in (values or {}).items():
        if var.startswith("_") or not val:
            continue
        needle = re.sub(r"\s+", "", str(val)).lower()
        hit = None
        if len(needle) >= 3:
            for b in blocks:
                if needle in re.sub(r"\s+", "", b.text).lower():
                    hit = b
                    break
        # если значение есть в тексте, но не в блоке — блок считаем по переменной
        if hit is None:
            for b in blocks:
                if var in b.spec.vars:
                    hit = b
                    break
        result[var] = {
            "value": val,
            "block": hit.spec.code if hit else None,
            "block_title": hit.spec.title if hit else "блок не определён",
            "file": "",
        }
    return result


def main() -> None:
    from services.doc_read import read_text
    from scripts.drive_scan import doc_kind_name

    path = Path(sys.argv[1])
    text = read_text(path) or ''
    kind = sys.argv[2] if len(sys.argv) > 2 else doc_kind_name(path, text)
    print('файл:', path.name[:56], '| тип:', kind, '| символов:', len(text))
    print('\n=== смысловые блоки документа ===')
    for d in describe(text, kind):
        state = 'найден' if d['found'] else 'НЕ НАЙДЕН'
        print('\n[%s] %s — %s' % (d['code'], d['title'], state))
        print('   зачем: %s' % d['purpose'])
        print('   переменные: %s' % ', '.join(d['vars']))
        if d['found']:
            print('   текст (%d симв.): %s' % (d['chars'], d['excerpt']))


if __name__ == '__main__':
    main()
