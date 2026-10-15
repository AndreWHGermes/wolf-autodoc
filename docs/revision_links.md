# Аудит связей данных Wolf AutoDoc — 2026-10-07

**База:** `/opt/wolf_v2/data/wolf.db` (SQLite WAL, 6.84 MB, 7 163 904 байт)  
**Режим:** только чтение (SELECT)  
**Время:** CEST UTC+02:00, 2026-10-07

---

## 1. templates ↔ template_variables

| Метрика | Значение |
|---|---|
| Активных шаблонов | 11 (из 17 всего) |
| Активных шаблонов БЕЗ переменных | **0** |
| Переменных без шаблона (осиротели) | **0** |
| Переменных с непустым default_value | 144 из 450 (32%) |
| default_value с данными человека (имя/паспорт/дата) | **0 явных** |

Переменные с `default_value` — это заполнители-даты, номера документов, коды компаний (не PII клиента).  
`variable_value_history` содержит реальные значения (company_full_name, bank_name), но без прямой привязки к шаблону — только по `variable_name`.

---

## 2. products ↔ product_documents ↔ templates

**Дубли слота `bank_statement_3m`** (один продукт — два шаблона одновременно):

| Продукт | Слоты | Шаблоны | Статус |
|---|---|---|---|
| C1 | bank_statement_3m | tbank (id=2), sber (id=3) | ok / ok |
| C1-EXT | bank_statement_3m | tbank (id=2), sber (id=3) | ok / ok |
| D12 | bank_statement_3m | tbank (id=2), sber (id=3) | ok / ok |
| E33G-EXT | bank_statement_3m | tbank (id=2), sber (id=3) | ok / ok |
| E33G-NEW | bank_statement_12m | tbank (id=24), sber (id=25) | ok / ok |

**Скрытые/слитые шаблоны, привязанные к продуктам:** — нет. Все 17 шаблонов active/ok.

**Слоты с «check»/«временный» в коде:** — нет.

---

## 3. applications ↔ application_documents ↔ templates

| Метрика | Значение |
|---|---|
| Заявки без документов | **4** (все test, client_id=65) |
| Документы со статусом rejected | **15** |
| Документы со статусом pending | 1 |
| Ссылки на удалённые (удалённые) шаблоны | **0** |

Причины rejected (топ):
- «оставлена одна справка по инструкции продукта, 3 месяца, банк по данным клиента» — 6
- пустая причина — 6
- «подтверждён 07.10.2026 system» — 3

---

## 4. Дубли: два активных шаблона на один slot_code одного продукта

**5 совпадений** по `bank_statement_3m` + 1 по `bank_statement_12m`. Это дизайнерское правило (TBANK vs Sberbank), не баг — но нужно фиксировать в документации, иначе при рендере выбирается первый по sort_order.

---

## 5. Счётчики

| Таблица | Записей |
|---|---|
| templates | 17 |
| template_variables | 450 |
| products | 7 |
| product_documents | 29 |
| applications | 92 |
| application_documents | 419 |
| clients | 78 |
| variable_value_history | 4 627 |
| events | 493 |
| logical_checks | 155 |
| quality_checks | 750 |
| app_steps | 4 |
| auto_runs | 65 |
| drive_scans | 145 |
| translation_cache | 146 |
| translation_line | 204 |
| variable_chat | 24 |
| variable_scope | 239 |
| **Пустые таблицы** | **client_documents, client_fields** |
| Прочие (settings, invites, users, login_* и т.д.) | малые, служебные |

---

## Список проблем по важности

1. **Средняя** — 5+1 дублей слотов bank_statement в product_documents (4 продукта имеют 2 шаблона на один slot). При рендере выбирается первый; если TBANK/Sber отличаются — теряется вариант.
2. **Низкая** — 4 заявки без документов (все test, client 65). Не продакшн, но стоит чистить.
3. **Низкая** — 15 rejected документов без явного системного кода ошибки (6 с пустой причиной).
4. **Низкая** — 2 пустые таблицы (client_documents, client_fields) — вероятно, миграция не доведена.
5. **Ок** — осиротевших переменных, скрытых/слитых шаблонов в products, ссылок на удалённые шаблоны — нет.
