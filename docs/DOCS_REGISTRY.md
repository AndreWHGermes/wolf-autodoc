# Реестр документов Wolf AutoDoc

Какие документы готовим мы, какие даёт клиент, где каждый документ используется.

## Документы, которые готовим мы

- **№1 `bank_statement_3m__tbank`** — Банковская справка 3 мес. (Т-Банк) (действующий)
  - используется в продуктах: C1, C1-EXT, D12, E33G-EXT
  - слоты: bank_stmt_3m | переменных: 10 | оригинальный пример: есть
- **№2 `bank_statement_3m__sber`** — Банковская справка 3 мес. (Сбер) (действующий)
  - используется в продуктах: C1, C1-EXT, D12, E33G-EXT
  - слоты: bank_stmt_3m | переменных: 13 | оригинальный пример: есть
- **№3 `bank_statement_12m__tbank`** — Банковская справка 12 мес. (Т-Банк) (действующий)
  - используется в продуктах: E33G-NEW
  - слоты: bank_stmt_12m | переменных: 13 | оригинальный пример: есть
- **№4 `bank_statement_12m__sber`** — Банковская справка 12 мес. (Сбер) (действующий)
  - используется в продуктах: E33G-NEW
  - слоты: bank_stmt_12m | переменных: 13 | оригинальный пример: есть
- **№5 `cv__format_short`** — Резюме (CV) — короткий формат (выключен из продуктов)
  - используется в продуктах: **нигде не используется**
  - слоты: — | переменных: 21 | оригинальный пример: есть
- **№6 `cv__format_detailed`** — Резюме (CV) — расширенный формат (выключен из продуктов)
  - используется в продуктах: **нигде не используется**
  - слоты: — | переменных: 26 | оригинальный пример: есть
- **№7 `cv__format_CLIENT`** — Резюме (CV) — формат Сиваева (действующий)
  - используется в продуктах: BRIDGING, CONV, D12, E33G-EXT, E33G-NEW
  - слоты: cv | переменных: 22 | оригинальный пример: есть
- **№8 `d12_cover_letter__default`** — D12: Permohonan Visa (ходатайство) (действующий)
  - используется в продуктах: D12
  - слоты: d12_sponsor_letters | переменных: 33 | оригинальный пример: есть
- **№9 `statement_letter_e02__default`** — Statement Letter (Form E-02) — Bridging (действующий)
  - используется в продуктах: BRIDGING, CONV
  - слоты: statement_e02_bridging, statement_e02_conversion | переменных: 22 | оригинальный пример: есть
- **№10 `statement_letter_e02__conversion`** — Statement Letter (Form E-02) — Conversion (объединён с другим документом)
  - используется в продуктах: **нигде не используется**
  - слоты: — | переменных: 22 | оригинальный пример: есть
- **№11 `remote_work_agreement__default`** — Remote Work Agreement (контракт) (действующий)
  - используется в продуктах: BRIDGING, CONV, E33G-EXT, E33G-NEW
  - слоты: work_agreement | переменных: 34 | оригинальный пример: есть
- **№12 `bridging_request_letter__ngurahrai`** — Bridging: комплект документов (Ngurah Rai, Бартош) (объединён с другим документом)
  - используется в продуктах: **нигде не используется**
  - слоты: — | переменных: 36 | оригинальный пример: есть
- **№13 `conversion_request_letter__default`** — Conversion: письмо в иммиграцию (офис по адресу клиента) (действующий)
  - используется в продуктах: CONV
  - слоты: conversion_letter | переменных: 44 | оригинальный пример: есть
- **№14 `bridging_request_letter__default`** — Bridging: письмо в иммиграцию (офис по адресу клиента) (действующий)
  - используется в продуктах: BRIDGING
  - слоты: bridging_letter | переменных: 38 | оригинальный пример: есть
- **№15 `conversion_request_letter__denpasar`** — Conversion: комплект документов (Denpasar, Арине) (объединён с другим документом)
  - используется в продуктах: **нигде не используется**
  - слоты: — | переменных: 41 | оригинальный пример: есть
- **№16 `bridging_request_letter__tabanan`** — Bridging: комплект документов (Tabanan) (объединён с другим документом)
  - используется в продуктах: **нигде не используется**
  - слоты: — | переменных: 36 | оригинальный пример: есть
- **№18 `employment_contract__default`** — Employment Contract (договор работы с организацией) (действующий)
  - используется в продуктах: BRIDGING, CONV, D12, E33G-EXT, E33G-NEW
  - слоты: employment_contract | переменных: 26 | оригинальный пример: есть

## Документы, которые даёт клиент

- **Загранпаспорт клиента** — паспорт: серия/номер, кем выдан, даты (обязательно)
- **Фотография клиента** — фото 3×4 / 4×6, цветное (обязательно)
- **Справка банка об остатке** — остаток, период, номер, банк (обязательно)
- **Адрес проживания и регистрации** — город, улица, дом, индекс (обязательно)
- **Действующий KITAS / ITK** — номер и срок разрешения (если продление или конверсия)
- **Свидетельство о браке** — для подачи с супругом(ой) (если семья)
- **Свидетельство о рождении** — для подачи с детьми (если семья)
- **Трудовая книжка (ИТК)** — встречается у ~7% клиентов (если есть)
- **Commitment / guarantee letter** — для зависимых членов семьи (если семья)

## Пакеты продуктов

- **BRIDGING** — наших документов: 5
  - №7 `cv__format_CLIENT` — cv
  - №9 `statement_letter_e02__default` — statement_e02_bridging
  - №11 `remote_work_agreement__default` — work_agreement
  - №14 `bridging_request_letter__default` — bridging_letter
  - №18 `employment_contract__default` — employment_contract
- **C1** — наших документов: 2
  - №1 `bank_statement_3m__tbank` — bank_stmt_3m
  - №2 `bank_statement_3m__sber` — bank_stmt_3m
- **C1-EXT** — наших документов: 2
  - №1 `bank_statement_3m__tbank` — bank_stmt_3m
  - №2 `bank_statement_3m__sber` — bank_stmt_3m
- **CONV** — наших документов: 5
  - №7 `cv__format_CLIENT` — cv
  - №9 `statement_letter_e02__default` — statement_e02_conversion
  - №11 `remote_work_agreement__default` — work_agreement
  - №13 `conversion_request_letter__default` — conversion_letter
  - №18 `employment_contract__default` — employment_contract
- **D12** — наших документов: 5
  - №1 `bank_statement_3m__tbank` — bank_stmt_3m
  - №2 `bank_statement_3m__sber` — bank_stmt_3m
  - №7 `cv__format_CLIENT` — cv
  - №8 `d12_cover_letter__default` — d12_sponsor_letters
  - №18 `employment_contract__default` — employment_contract
- **E33G-EXT** — наших документов: 5
  - №1 `bank_statement_3m__tbank` — bank_stmt_3m
  - №2 `bank_statement_3m__sber` — bank_stmt_3m
  - №7 `cv__format_CLIENT` — cv
  - №11 `remote_work_agreement__default` — work_agreement
  - №18 `employment_contract__default` — employment_contract
- **E33G-NEW** — наших документов: 5
  - №3 `bank_statement_12m__tbank` — bank_stmt_12m
  - №4 `bank_statement_12m__sber` — bank_stmt_12m
  - №7 `cv__format_CLIENT` — cv
  - №11 `remote_work_agreement__default` — work_agreement
  - №18 `employment_contract__default` — employment_contract
