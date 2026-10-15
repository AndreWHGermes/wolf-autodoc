# Технический аудит кода Wolf AutoDoc CRM

Дата: 29.09.2026. Аудит только чтением: код, сервисы и БД не изменялись.
Метод: карта архитектуры, `py_compile`, `PRAGMA table_info`, поиск паттернов риска.

## 1. Карта архитектуры

**Точка входа:** `app.py` (776 строк) → `create_app()` → `waitress.serve(:8091, threads=8)`, юнит `wolf-crm.service`.
**Загрузка блоков:** `app.py:23-42` — динамический `importlib` по списку `BLUEPRINTS` (login, dashboard, history, templates, settings).

| Файл | Строк | Маршрутов |
|---|---|---|
| `app.py` | 776 | 12 |
| `blocks/dashboard/page.py` | 2321 | 17 |
| `blocks/templates/page.py` | 1485 | 18 |
| `blocks/shared/layout.py` | 733 | 0 |
| `blocks/settings/page.py` | 212 | 1 |
| `blocks/history/page.py` | 187 | 1 |
| `blocks/login/page.py` | 119 | 2 |
| `core/db.py` | 347 | — |
| `core/pdf2html.py` | 594 | — |
| `core/pdf_extract.py` | 265 | — |
| `core/auth.py` | 157 | — |
| `core/qa_compare.py` | 127 | — |
| `core/security.py` | 24 | — |
| `core/config.py` | 29 | — |
| `bot/wolf_bot.py` | 1219 | — |
| `bot/ai_parser.py` | 569 | — |
| `bot/notify.py` | 108 | — |
| `scripts/drive_scan.py` | 161 | — |
| `scripts/app_autoprepare.py` | 141 | — |

Итого ≈ 9574 строк Python.

## 2. Блочность

**Частично.** Есть 5 blueprint'ов + `shared`, но:
- `app.py` — второй монолит: 12 маршрутов, 776 строк, включая полноценный экран карточки клиента (`_client_view`, ~420 строк HTML/JS). Должно быть блоком `blocks/clients/`.
- Монолиты внутри блоков: `dashboard/page.py` (2321), `templates/page.py` (1485). Отдельные view-функции гигантские: `app_view` ~720 строк, `card()` ~666 строк, `app_doc_edit` ~556 строк.
- Дублирование: lookup оригиналов Google Drive дословно продублирован — `app.py:640-723` ≈ `blocks/dashboard/page.py:26-115`. Плюс две независимые системы рендера документа: dashboard `/doc/<id>/html|edit|preview-pdf|ensure-pdf` + `build_template_values` ↔ templates `/templates/<id>/render|pdfview|pdfpages|pdfimg` + `blocks/editor.html`.

## 3. Дефекты по файлам

### (а) Расхождение кода и схемы БД
- `core/schema.sql` устарел относительно живой `data/wolf.db`: отсутствуют таблицы `drive_scans, invites, login_codes, translation_cache, variable_chat` и ~15 колонок (`clients.photo_path/account_no/...`, `applications.bot_manager_id`, `templates.reviewed/doc_index/example_path/...`, `template_variables.rule_note/approved/examples_json`, `bot_managers.source/invited_by/updated_at`, `users.telegram_id`). `init_db()` строит БД строго по схеме → на чистой машине приложение упадёт.
- `blocks/dashboard/page.py:573,574,1762,1881,1882,1910,1912`, `blocks/templates/page.py:704` — обращение к колонке `templates.default_values_json`, которой нет ни в схеме, ни в БД. Через `dict.get()` исключения нет → тихая потеря дефолтных значений.
- `applications.product_name` — не колонка, а алиас `p.name AS product_name`; читается в `history/page.py:39,52`, `dashboard/page.py:465,634`. Работает, но связка хрупкая.
- `application_documents.created_at` не существует (есть `rendered_at`, `sent_at`).

### (б) Склейка HTML/JS внутри Python-литералов
- `blocks/dashboard/page.py:832-959` — один литерал `body` с 14 подстановками `""" + expr + """`; внутри JS-блок. Именно этот паттерн дал сбой «Python-код в JS буквально» (29.09.2026, кнопки окна просмотра не работали).
- `py_compile` даёт `SyntaxWarning`: `templates/page.py:82` (`\{`), `templates/page.py:1172`, `shared/layout.py:298` (`\s`). На 3.12 — предупреждение, дальше станет ошибкой.

### (в) Возвраты tuple
- `app.py:61-63` — `return render(...), 404` (валидно, но хрупко).
- `blocks/shared/layout.py:653-667` `docs_state()` возвращает tuple.
- `blocks/shared/layout.py:661` — `summary.get("error", 0) > 0`, где `error` — строка → потенциальный `TypeError`.

### (г) Дублирование
- `app.py:640-723` ↔ `blocks/dashboard/page.py:26-115` (оригиналы Drive).
- `app.py:65-487` (`_client_view`) ↔ `blocks/dashboard/page.py:440-2321` — два места правят один домен.
- Два движка рендера документа (см. п.2).

### (д) Необработанные исключения
- `blocks/dashboard/page.py:575,587,1883` — голый `except: pass` (глотает всё).
- **118** вхождений `except Exception` без логирования.

### (е) SQL
- f-string в SQL: `app.py:528`, `core/db.py:140,144,165`, `bot/wolf_bot.py:413,500`, `scripts/drive_scan.py:104`. Значения параметризованы, имена колонок — из белых списков; прямой инъекции нет, но паттерн хрупкий.

### (ж) Заглушки, секреты, мусор
- `core/config.py:29` — `DEFAULT_ADMIN_PASSWORD = "123"`; `core/db.py:48` заводит `admin/123`.
- `core/config.py:23` — предсказуемый `WEB_SECRET` по умолчанию → подделка сессии.
- `app.py:549-550` — мёртвый код `url_for(...) if False`.
- `app.py:388-399` — битая подстановка `'&dollar;'` в JS.
- `app.py:775` — отладочный `print()` в проде.
- Нет CSRF, не заданы `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE`, нет CSP/X-Frame-Options; нет rate-limit на логине (`login/page.py:104-113`).
- 52 хардкод-пути `/opt/wolf`; дубль `import re` в `dashboard/page.py:8,12`.
- Мусорные копии, мешающие анализу: `blocks/dashboard/page.py.bak`, `*.lock_20260928`, `core/db.py.bak`, `core/db.py.bak2`.

## 4. Топ-10 приоритетных фиксов

1. `app.py:156` — `int(time.time())` без `import time` → `NameError`. Добавить импорт.
2. `core/config.py:29` — дефолтный пароль `123` → брать из окружения/генерировать.
3. `core/config.py:23` — предсказуемый `WEB_SECRET` → фейлить старт без явного секрета.
4. `dashboard/page.py:573` (+1762,1881) — колонки `default_values_json` нет → заменить на существующую или добавить в схему.
5. `core/schema.sql` — синхронизировать со `PRAGMA table_info(wolf.db)`.
6. `app.py:549` — убрать мёртвую ветку.
7. `dashboard/page.py:575,587,1883` — `except: pass` → логирование.
8. `shared/layout.py:298`, `templates/page.py:82,1172` — raw-строки для JS-литералов.
9. `app.py:640-723` ↔ `dashboard/page.py:26-115` — вынести lookup в `blocks/shared/originals.py`.
10. `app.py:490+` — CSRF + secure-cookie + заголовки безопасности.

## 5. Вердикт

| Критерий | Оценка | Обоснование |
|---|---|---|
| Модульность | 5/10 | 5 блоков + shared, но `app.py` — второй монолит, 2 блока по 1485/2321 строк, дублирование |
| Читаемость | 5/10 | view-функции 600-720 строк, 14 подстановок в одном литерале, мусорные копии |
| Безопасность | 3/10 | `admin/123`, предсказуемый секрет, нет CSRF/secure-cookie/заголовков/rate-limit |
| Устойчивость | 4/10 | `NameError` в app.py:156, рассинхрон схемы, 118×`except Exception`, мёртвый код |

**Итого ≈ 4.3/10** — рабочий продукт с опасным техдолгом во входной точке и в безопасности.

## 6. Что из этого уже исправлено (29.09.2026)
- Сломанный JS в карточке заявки (`const APP_ID`) — причина была именно в паттерне (б) — **исправлено**, готча записана в скилл.
- Окно просмотра заявки переведено на общий HTML-лист — устранена часть дублирования рендера — **сделано**.
