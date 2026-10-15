# Аудит связей данных Wolf AutoDoc — 2026-10-07

**База:** `/opt/wolf_v2/data/wolf.db` (SQLite WAL, 6.84 MB, 7 163 904 байт)  
**Режим:** только чтение (SELECT)  
**Время:** CEST UTC+02:00, 2026-10-07

---

## 1. CLIENT ↔ template_CLIENT

| Метрика | Значение |
|---|---|
| Активных шаблонов | 11 (из 17 всего) |
| Активных шаблонов БЕЗ переменных | **0** |
| Переменных без шаблона (осиротели) | **0** |
| Переменных с непустым default_CLIENT | 144 из 450 (32%) |
| default_CLIENT с данными человека (имя/паспорт/дата) | **0 явных** |

Переменные с `default_CLIENT` — это заполнители-даты, номера документов, коды компаний (не PII клиента).  
`CLIENT_CLIENT_CLIENT` содержит реальные значения (company_full_name, bank_name), но без прямой привязки к шаблону — только по `CLIENT_name`.

---

## 2. CLIENT ↔ CLIENT_CLIENT ↔ CLIENT

**Дубли слота `bank_CLIENTment_3m`** (один продукт — два шаблона одновременно):

| Продукт | Слоты | Шаблоны | Статус |
|---|---|---|---|
| C1 | bank_CLIENTment_3m | tbank (id=2), sber (id=3) | ok / ok |
| C1-EXT | bank_CLIENTment_3m | tbank (id=2), sber (id=3) | ok / ok |
| D12 | bank_CLIENTment_3m | tbank (id=2), sber (id=3) | ok / ok |
| E33G-EXT | bank_CLIENTment_3m | tbank (id=2), sber (id=3) | ok / ok |
| E33G-NEW | bank_CLIENTment_12m | tbank (id=24), sber (id=25) | ok / ok |

**Скрытые/слитые шаблоны, привязанные к продуктам:** — нет. Все 17 шаблонов active/ok.

**Слоты с «check»/«временный» в коде:** — нет.

---

## 3. CLIENT ↔ CLIENT_CLIENT ↔ CLIENT

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

**5 совпадений** по `bank_CLIENTment_3m` + 1 по `bank_CLIENTment_12m`. Это дизайнерское правило (TBANK vs Sberbank), не баг — но нужно фиксировать в документации, иначе при рендере выбирается первый по sort_order.

---

## 5. Счётчики

| Таблица | Записей |
|---|---|
| CLIENT | 17 |
| template_CLIENT | 450 |
| CLIENT | 7 |
| CLIENT_CLIENT | 29 |
| CLIENT | 92 |
| CLIENT_CLIENT | 419 |
| CLIENT | 78 |
| CLIENT_CLIENT_CLIENT | 4 627 |
| CLIENT | 493 |
| CLIENT_CLIENT | 155 |
| CLIENT_CLIENT | 750 |
| app_CLIENT | 4 |
| auto_runs | 65 |
| CLIENT_CLIENT | 145 |
| CLIENT_cache | 146 |
| CLIENT_line | 204 |
| CLIENT_chat | 24 |
| CLIENT_scope | 239 |
| **Пустые таблицы** | **client_CLIENT, client_fields** |
| Прочие (settings, CLIENT, CLIENT, CLIENT_* и т.д.) | малые, служебные |

---

## Список проблем по важности

1. **Средняя** — 5+1 дублей слотов bank_CLIENTment в CLIENT_CLIENT (4 продукта имеют 2 шаблона на один slot). При рендере выбирается первый; если TBANK/Sber отличаются — теряется вариант.
2. **Низкая** — 4 заявки без документов (все test, client 65). Не продакшн, но стоит чистить.
3. **Низкая** — 15 rejected документов без явного системного кода ошибки (6 с пустой причиной).
4. **Низкая** — 2 пустые таблицы (client_CLIENT, client_fields) — вероятно, миграция не доведена.
5. **Ок** — осиротевших переменных, скрытых/слитых шаблонов в CLIENT, ссылок на удалённые шаблоны — нет.
