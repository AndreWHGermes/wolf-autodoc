# Аудит services/ перед рефакторингом

**Дата:** 2026-10-17
**Этап:** 0 (без правок кода)
**Точка отката:** тег `pre-refactor-2026-10-17`, бэкап `/opt/wolf_backups/pre-refactor-20261017_143239/`

## Сводка

- **Всего модулей:** 69 (без `.bak`, без `__init__.py`)
- **Строк кода:** ~23 715
- **Самый большой:** `values.py` — 4 443 строки (монстр, главная цель разбиения)
- **Топ-5 по размеру:**
  1. `values.py` (4 443) — оркестратор значений
  2. `cv_gen.py` (1 232) — генерация резюме
  3. `legend.py` (982) — построение «легенды» клиента
  4. `render.py` (914) — HTML → PDF
  5. `doc_check.py` (863) — проверки документа

## Граф зависимостей

**Ключевая находка:** импорты внутри `services/` почти односторонние.
Только `values.py` напрямую импортирует другие модули (`cv_gen`, и др.).
Остальные модули либо независимы, либо импортируют только `core/`.

Это значит:
- При миграции правил из `values.py` в `services/templates/` обратные ссылки ломаться не будут.
- Можно мигрировать по одному модулю за раз, остальная система продолжает работать.

## Таблица модулей

| #  | Файл                  | Строк | Зона ответственности | Куда переедет |
|----|-----------------------|-------|----------------------|---------------|
| 1  | addresses.py          | 176   | классификатор адресов (РФ vs Индонезия) | `services/values/addresses.py` |
| 2  | address_fit.py        | 146   | подгонка длины адресной строки | `services/values/addresses.py` |
| 3  | address_pool.py       | 344   | пул адресов РФ | `services/pools/addresses.py` |
| 4  | addr_order.py         | 100   | порядок слов в английском адресе | `services/values/addresses.py` |
| 5  | agent_bridge.py       | 167   | мост к агенту (вызовы кода из cron) | `services/transport/` или `services/agent/` |
| 6  | app_steps.py          | 187   | журнал этапов заявки | **остаётся** в `services/` |
| 7  | autofill.py           | 421   | оркестратор сборки документов | **остаётся** в `services/` (тонкий) |
| 8  | auto_runner.py        | 574   | цикл автопрогона заявки | **остаётся** в `services/` |
| 9  | bank_choice.py        | ~250  | выбор банка клиента (tbank/sber) | `services/templates/bank_statements/_common.py` |
| 10 | brief_values.py       | ~150  | извлечение значений из брифа | `services/values/orchestrator.py` (вспомогательная) |
| 11 | company_parse.py      | ~200  | парсинг названия организации | `services/values/organization.py` |
| 12 | cross_check.py        | ~250  | кросс-проверка документов в пакете | **остаётся** в `services/` |
| 13 | cv_content.py         | 268   | содержание CV по профессии | `services/templates/cv/sivaev.py` |
| 14 | cv_fill.py            | 335   | заполнение CV значениями | `services/templates/cv/sivaev.py` |
| 15 | cv_gen.py             | 1232  | генерация CV (Word + проверки) | `services/templates/cv/sivaev.py` (основной код) |
| 16 | cv_rules.py           | ~200  | правила текста CV | `services/templates/cv/sivaev.py` |
| 17 | derived_vars.py       | 389   | вычисляемые переменные (даты, номера) | `services/values/finance.py` + `addresses.py` |
| 18 | doc_blocks.py         | 305   | блоки документа (заголовок, тело, подвал) | **остаётся** в `services/` (рендер) |
| 19 | doc_branding.py       | ~180  | брендинг документа (логотип, цвета) | `services/templates/bank_statements/_common.py` или свой |
| 20 | doc_check.py          | 863   | проверки документа (5 слоёв) | `services/final_check.py` (расширить) |
| 21 | doc_engine.py         | 274   | движок документа (что рендерить) | **остаётся** в `services/` |
| 22 | doc_overrides.py      | ~150  | ручные override значений | `services/values/cache.py` |
| 23 | doc_parse.py          | 612   | парсинг текста клиентского документа | **остаётся** в `services/` (чтение Диска) |
| 24 | doc_read.py           | 330   | чтение текста PDF/DOCX с Диска | **остаётся** в `services/` |
| 25 | doc_rules.py          | ~250  | правила заполнения документа | `services/templates/<type>/<code>.py` |
| 26 | drive.py              | ~200  | обёртка над GDrive (старая) | `services/transport/drive.py` (заменить на gdrive_read/write) |
| 27 | drive_throttle.py     | ~100  | троттлинг запросов к GDrive | `services/transport/throttle.py` |
| 28 | employer_pool.py      | ~200  | пул работодателей | `services/pools/employers.py` |
| 29 | error_log.py          | ~150  | журнал ошибок | **остаётся** в `services/` |
| 30 | final_check.py        | ~250  | финальная проверка пакета | **остаётся** в `services/` |
| 31 | gdrive_api.py         | ~300  | GDrive API (чтение) | `services/transport/gdrive_read.py` |
| 32 | gdrive_oauth.py       | ~200  | OAuth-токен владельца | `services/transport/gdrive_oauth.py` |
| 33 | gdrive_write.py       | 368   | GDrive API (запись) | `services/transport/gdrive_write.py` |
| 34 | html_frame.py         | ~250  | HTML-каркас документа | `services/templates/bank_statements/_common.py` |
| 35 | immigration_office.py | 264   | адреса офисов иммиграции (Нгурах-Рай и др.) | `services/templates/letters/_common.py` |
| 36 | intake_gate.py        | ~200  | шлюз приёма заявок | **остаётся** в `services/` |
| 37 | itk_doc.py            | ~250  | работа с ITK (разрешение на пребывание) | **остаётся** в `services/` (специфика Индонезии) |
| 38 | kit.py                | ~200  | утилиты работы с БД | **остаётся** в `services/` |
| 39 | latin.py              | ~150  | транслитерация кириллица↔латиница | `services/values/personal.py` |
| 40 | legend.py             | 982   | построение «легенды» клиента | **остаётся** в `services/` |
| 41 | llm_extract.py        | ~350  | LLM-извлечение значений из текста | **остаётся** в `services/` |
| 42 | llm.py                | ~200  | обёртка LLM | **остаётся** в `services/` |
| 43 | logical_check.py      | 399   | логические проверки (согласованность) | **остаётся** в `services/` |
| 44 | marks.py              | ~150  | метки/марки документов | `services/values/cache.py` |
| 45 | movement_parse.py     | ~200  | парсинг банковских выписок | **остаётся** в `services/` (специфика) |
| 46 | mrz.py                | 285   | парсинг MRZ (машиночитаемая зона паспорта) | **остаётся** в `services/` (специфика) |
| 47 | org_pool.py           | 381   | пул организаций (работодатели клиентов) | `services/pools/organizations.py` |
| 48 | package.py            | 297   | сборка пакета документов | **остаётся** в `services/` |
| 49 | pack_check.py         | ~250  | проверка полноты пакета | **остаётся** в `services/` |
| 50 | pdf_quality.py        | 386   | проверка качества PDF | **остаётся** в `services/` |
| 51 | photo.py              | ~150  | работа с фотографией клиента | **остаётся** в `services/` |
| 52 | pipeline.py           | ~300  | конвейер этапов заявки | **остаётся** в `services/` |
| 53 | pool_assign.py        | 436   | выбор пула по клиенту | `services/pools/selector.py` |
| 54 | pool_builder.py       | 476   | построение пулов | `services/pools/builder.py` |
| 55 | pool_uni.py           | ~250  | пул вузов | `services/pools/universities.py` |
| 56 | postmortem.py         | ~200  | разбор ошибок после прогона | **остаётся** в `services/` |
| 57 | previews.py           | 522   | превью PDF/HTML | **остаётся** в `services/` |
| 58 | provenance.py         | ~200  | откуда значение (источник) | `services/values/registry.py` |
| 59 | reader_agent.py       | 551   | LLM-агент чтения документов клиента | **остаётся** в `services/` |
| 60 | render.py             | 914   | рендер HTML → PDF, fit_width | **остаётся** в `services/` |
| 61 | requested_product.py  | ~150  | определение продукта по заявке | **остаётся** в `services/` |
| 62 | requirements.py       | ~150  | требования к пакету | **остаётся** в `services/` |
| 63 | salary_pool.py        | ~200  | пул окладов | `services/pools/salaries.py` |
| 64 | self_heal.py          | 297   | самолечение (исправление типовых ошибок) | **остаётся** в `services/` |
| 65 | sender.py             | 297   | отправка пакета на GDrive | `services/transport/` или `services/sender.py` |
| 66 | translate.py          | 347   | перевод значений RU↔EN | `services/values/personal.py` |
| 67 | value_cache.py        | ~200  | кэш значений документа | `services/values/cache.py` |
| 68 | values.py             | 4443  | **МОНСТР** — оркестратор всех значений | `services/values/orchestrator.py` (тонкая обёртка) |
| 69 | var_methods.py        | ~200  | методы работы с переменными | `services/values/registry.py` |

## Куда сколько модулей уезжает

| Целевой каталог | Модулей | Ключевые |
|-----------------|---------|----------|
| `services/templates/` | ~15 | cv (3 файла), bank_statements (3), letters, contracts, e02 |
| `services/values/`   | ~12 | personal, addresses, organization, finance, orchestrator, cache, registry |
| `services/pools/`    | ~7  | organizations, salaries, addresses, employers, universities, selector, builder |
| `services/transport/` | ~6  | gdrive_read, gdrive_write, gdrive_oauth, throttle, drive |
| **Остаётся** в `services/` | ~29 | autofill, render, pipeline, auto_runner, final_check, app_steps, error_log, doc_engine, doc_blocks, doc_parse, doc_read, legend, llm*, reader_agent, kit, sender, ... |

## Циклы импортов

**Не обнаружены.** Граф импортов внутри `services/` практически односторонний:
`values.py` → всё остальное. Остальные модули не импортируют друг друга напрямую
(за единичными исключениями через `services.cv_gen`).

Это упрощает миграцию: можно переносить правила по одному, ломая только `values.py`.

## Что НЕ нужно трогать

- `core/` — ядро, стабильное.
- `repositories/` — SQL-обёртки, уже изолированы.
- `blocks/`, `bot/` — внешние слои, в этом этапе не трогаем.

## Этапы рефакторинга (по согласованию с заказчиком)

См. `/opt/wolf_v2/docs/REFACTOR_PLAN.md` (план, согласован 17.10.2026).

**Этап 0 — Аудит** ← мы здесь, файл создан.

**Этап 1 — Вынос правил банковских справок.**
- Файлы: `services/templates/bank_statements/{_common,tbank,sber}.py` — уже созданы как каркас.
- Подключение: `services/values.py` импортирует правила из нового модуля,
  если для `tpl_code` есть правила в реестре. Иначе — fallback на старую логику.
- Тест: `build_all(122)` → PDF идентичен слепку.

**Этап 2 — Разбиение `values.py`.** Перенос функций по доменам в `services/values/`.

**Этап 3 — Пулы** в `services/pools/`.

**Этап 4 — Транспорт** в `services/transport/`.

**Этап 5 — Разбиение `blocks/dashboard/page.py` (4502 строк).**

**Этап 6 — Документация + паспорта переменных.**