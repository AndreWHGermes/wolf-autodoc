# Wolf AutoDoc — полный перечень этапов заявки

> **Куда смотреть в БД:** `app_steps` (шаги цикла), `events` (события действий), `auto_runs` (попытки прогона), `drive_scans` (разбор Google Drive), `application_documents` (слоты документов).
>
> **Где видно админу:** на странице заявки — «Журнал этапов» (таблица внизу страницы).
>
> **Обновлено:** 2026-10-17 (Андрей, топик #11 Bi Group).

---

## Фаза A. Приём заявки (от Telegram-бота до постановки в очередь)

| # | Этап | Что делает системa | Где в коде | Шаг в `app_steps` | Стоп? |
|---|------|---------------------|-----------|-------------------|-------|
| A.1 | Сообщение в боте | Андрей шлёт `@Wolf_AutoDoc_bot` сообщение со ссылкой на Google Drive папку клиента | `bot/wolf_bot.py` | — | нет |
| A.2 | Создание клиента | Поиск клиента в БД по `full_name_latin`; если нет — создание нового | `bot/wolf_bot.py:create_or_get_client` | — | да, если имя пустое |
| A.3 | Создание заявки | `applications: insert` со статусом `new`, привязка `client_id`, `gdrive_folder_url`, `product_code` | `bot/wolf_bot.py:create_app` | `received` | да, если заявка с тем же ID уже есть |
| A.4 | Определение продукта | По тексту сообщения и состоянию клиента — какой продукт (E33G-NEW, D12, BRIDGING, …) | `bot/wolf_bot.py:detect_product` | `product` | нет, берётся дефолт |
| A.5 | Снимок в `auto_queue` | Постановка в очередь на автоцикл (`status='queued'`) | `services/auto_queue.py:enqueue` | — | да, если цикл выключен (`paused`) |
| A.6 | Входящие на сайте | Заявка появляется в `/inbox` главной админки | `blocks/dashboard/page.py:page` | — | нет |

## Фаза B. Старт автоцикла (от «взята в работу» до «легенда построена»)

| # | Этап | Что делает система | Где в коде | Шаг в `app_steps` | Стоп? |
|---|------|---------------------|-----------|-------------------|-------|
| B.1 | Взята в работу | Цикл вытащил заявку из очереди, `auto_queue.status='running'`, `auto_runs` вставлен | `services/auto_runner.py:claim_one` | `taken` | да, если заявка в `archive` |
| B.2 | **Этап -1: Разбор Google Drive** | `services.drive.start_scan()` — запуск `scripts/drive_scan.py` в фоне с пониженным приоритетом; `drive_scans` пишется со статусом `running` | `services/drive.py:start_scan` → `scripts/drive_scan.py:main` | `read_drive` | да, если Google Drive вернул ошибку |
| B.2.1 | Скачивание файлов | `gdrive_api.list_files()` → 6 элементов из папки клиента (PASSPORT, ITK, INN, фото, ITK_старая, Документ.pdf, Виза) | `services/gdrive_api.py:list_files` | — | да, если 0 файлов |
| B.2.2 | Чтение PDF/OCR | Для каждого файла `services.doc_read.read_text()` — извлечение текстового слоя или OCR через Tesseract | `services/doc_read.py` | — | да, если OCR упал |
| B.2.3 | Классификация документов | `scripts.drive_scan.doc_kind_name()` — по имени файла и тексту определяет тип: `passport` / `itk` / `bank_balance` / `bank_movement` / `photo` / `other` | `scripts/drive_scan.py:91-110` | — | нет |
| B.2.4 | **Отбор самой свежей ИТК** | Если `doc_type='itk'` встретилось несколько раз, сортируем по дате (выпуска/срока) и оставляем **самую свежую**. Остальные ИТК помечаются `_skipped` и не идут в карточку | `scripts/drive_scan.py:apply_values` (этап 23) | — | нет |
| B.2.5 | Извлечение переменных по правилам | Для каждого документа — `services.doc_parse.parse_any()` — регулярные вытаски `passport_number`, `inn`, `balance_rub`, `card_mask`, `account_no`, `date_of_birth`, `stay_permit_no`, `expiry_date` и т.д. | `services/doc_parse.py:parse_any` | — | да, если критичные поля пустые |
| B.2.6 | Извлечение через LLM (если правила не вывезли) | Если текст есть, а правила ничего не нашли — `_call_llm()` через `services/llm.py`. **Бесплатные модели в приоритете** (`nararouter` → `nemotron-3.5-lightning-free`), платные (`deepseek-andreyl` → `minimax`) только если бесплатные вернули ошибку | `services/llm.py:call_llm` | — | нет, fallback на правила |
| B.2.7 | Запись в карточку клиента | Пустые колонки `clients` заполняются найденными значениями (`passport_number`, `birth_date`, `address_live`, `phone`, `email` и т.д.) | `scripts/drive_scan.py:apply_values:262-279` | — | нет |
| B.2.8 | Запись в `data/doc_values/client_<id>.json` | Снимок всех значений с указанием источника (имя файла) и времени. `chosen: True` блокирует перезапись (ручной выбор админа) | `scripts/drive_scan.py:282-321` | — | нет |
| B.2.9 | Снимок для конструктора | `application_documents.values_json` для самого свежего слота заявки пополняется новыми значениями; старый `pdf_path` сбрасывается в `NULL`, статус → `draft` | `scripts/drive_scan.py:323-336` | — | нет |
| B.2.10 | Итог разбора | `drive_scans.status='ok'`, `note` содержит «в наличии N документ(ов): Паспорт ×1, ИТК ×2, … Прочитано 5, в карточку перенесено 12 значений. Старые ИТК не участвуют в сборке: ITK_old.pdf.» | `scripts/drive_scan.py:417-426` | — | да, если 0 значений перенесено |
| B.3 | **Этап 0: Легенда клиента** | `services.legend.build()` — собирает ФИО латиницей, ФИО кириллицей, отчество, дата рождения, место рождения, гражданство, адреса, банк, ИНН — из `clients` + `doc_values` | `services/legend.py:build` | `legend` | да, если нет ФИО или даты рождения |
| B.3.1 | Сбор ФИО | `surname`, `name`, `patronymic` + `full_name_latin` (Title Case для банковских справок, First Letter Capital для ФИО по отдельности) | `services/values.py:_smart_title`, `_fio_full_latin` (этап 18) | — | нет |
| B.3.2 | Адреса | `address_in_indonesia` (для индонезийских писем), `address_reg` / `address_live` (для справок, РФ) | `services/legend.py:build_addresses` | — | нет, берётся дефолт из `address_pool.py` |
| B.3.3 | Банк | `bank_name` — TBank / Sber / нет (берётся из `doc_values` или из существующих полей клиента) | `services/legend.py:build_bank` | — | нет |
| B.3.4 | ИНН, СНИЛС, паспорт | Прямое копирование из `clients` (только если непустое) | `services/legend.py:build_personal` | — | да, если пустое |
| B.3.5 | Сохранение легенды | `services.legend.save()` → `data/legends/client_<id>.json` | `services/legend.py:669` | — | нет |
| B.4 | Запись в `app_steps` | `legend: ok` — легенда построена и сохранена | `scripts/auto_cycle.py:159-192` | `legend` | — |

## Фаза C. Подготовка переменных (от легенды до готовности к подстановке)

| # | Этап | Что делает система | Где в коде | Шаг в `app_steps` | Стоп? |
|---|------|---------------------|-----------|-------------------|-------|
| C.1 | **Этап 0.5: Выбор банка** | `services.bank_choice.run()` — определяет какой банк подставлять в справки: TBank или Sber (правило: если у клиента Sber → берём Сбер; если TBank → Тинькофф; если ничего → дефолт TBank) | `services/bank_choice.py:run` | `bank_choice` | нет |
| C.1.1 | Анализ документов клиента | Сканирует `data/gdrive_cache/client_<id>/*` — ищет справки Сбера или Тинькофф | `services/bank_choice.py:detect_from_drive` | — | нет |
| C.1.2 | Принятие решения | Если в папке есть Sber → помечаем TBank-шаблоны как `rejected`; если TBank → помечаем Sber-шаблоны как `rejected`; если обе → берём ту, у которой свежее дата | `services/bank_choice.py:apply_to_slots` | — | нет |
| C.2 | **Этап 0.7: Назначение организации** | `services.org_pool.assign()` — если в `application_documents.values_json` нет `company_name` / `company_inn` / `company_address` / `salary_amount`, выбираем одну организацию из пула (`data/organizations.json` + `salary_pool.json`) и заполняем | `services/org_pool.py:assign` | `org_assigned` | нет |
| C.2.1 | Проверка | Если в `values_json` уже есть `company_name` — пропускаем (админ задал вручную) | `services/org_pool.py:should_assign` | — | нет |
| C.2.2 | Выбор из пула | Round-robin или по приоритету — компания, у которой меньше использований за последние 30 дней | `services/org_pool.py:pick_one` | — | нет |
| C.2.3 | Зарплата | Подбирается из `salary_pool.json` по диапазону, валюте и продукту (E33G-NEW: 2500-4500 USD; D12: 3000-5000 USD) | `services/org_pool.py:assign_salary` | — | нет |
| C.2.4 | Запись в слоты | `values_json` для **всех** документов заявки получает `company_name`, `company_inn`, `company_address`, `salary_amount`, `salary_currency`, `position` | `services/org_pool.py:write_to_slots` | — | нет |
| C.3 | **Этап 0.8: Назначение адреса в РФ** | `services.address_pool.assign()` — для справок Сбера/Тинькофф нужен `address_reg` / `address_live` в РФ; если нет — берём из пула | `services/address_pool.py:assign` | `address_assigned` | нет |
| C.4 | **Этап 0.9: Назначение университета** (только D12-студент) | `services.pool_uni.assign()` — подбираем ВУЗ из `data/universities.json` | `services/pool_uni.py:assign` | `uni_assigned` | нет |
| C.5 | **Этап 0.95: Нормализация значений** | `services.values.normalize()` — приведение к нужному регистру/формату: ФИО — Title Case, даты — DD.MM.YYYY, числа без пробелов, деньги с разделителями | `services/values.py:normalize_all` | `normalize` | нет |
| C.6 | **Этап 0.97: Вычисление зависимых переменных** | `services.values.derive()` — расчёт `period_from` / `period_to` (по `balance_date`), `contract_date` (по `received_at` + 14 дней), `card_mask` (по `account_no`), `full_address` (по `zip + city + street`) | `services/values.py:derive_all` | `derive` | нет |
| C.7 | Запись в `app_steps` | `prepare_vars: ok` — все пулы назначены, значения нормализованы | `scripts/auto_cycle.py:200-230` | `prepare_vars` | — |

## Фаза D. Сборка пакета (от шаблонов до готовых PDF)

| # | Этап | Что делает система | Где в коде | Шаг в `app_steps` | Стоп? |
|---|------|---------------------|-----------|-------------------|-------|
| D.1 | **Шаг 1: Подготовка слотов пакета** | По `product_documents` для `product_code` находим все шаблоны (CV, договор, справка 3м, справка 12м, письмо 1, письмо 2, письмо 3). Для каждого — `application_documents` (если нет — создаём `draft`) | `services/autofill.py:ensure_slots` | `ensure_slots` | да, если для продукта нет ни одного шаблона |
| D.2 | **Шаг 1.1: Фильтр банков** | `services.bank_choice.apply_to_slots()` — шаблоны отклонённого банка получают `status='rejected'` и не участвуют в сборке | `services/bank_choice.py:apply_to_slots` | — | нет |
| D.3 | **Шаг 2: Подстановка переменных в шаблоны** | `services.autofill.fill_one(slot_id)` для каждого слота. Идёт **в цикле, пока есть незаполненные метки `{{ }}`** | `services/autofill.py:fill_one` | `fill` | да, если 3 попытки подряд не уменьшили число меток |
| D.3.1 | Рендер HTML | `services.autofill.render_html()` — Jinja2-шаблон получает `values_json`; получается HTML с подставленными `{{ variable }}` → реальные значения | `services/autofill.py:render_html` | — | нет |
| D.3.2 | Генерация PDF | WeasyPrint / ReportLab — HTML → PDF; путь: `data/renders/<app_id>/<template_code>.pdf` | `services/autofill.py:html_to_pdf` | — | да, если WeasyPrint упал |
| D.3.3 | Защита от `{{ }}` | После каждой подстановки `services.autofill.check_unfilled()` сканирует PDF на наличие `{{` / `}}`. Если найдено — слот помечается `_unfilled=True` | `services/autofill.py:check_unfilled` | — | да, если >5 меток осталось |
| D.3.4 | Защита от малого набора | Если заполнено **менее 5 переменных** — слот принудительно `_incomplete=True`, в архив не идёт | `services/autofill.py:check_minimum` | — | да |
| D.3.5 | Персональные переменные | `services.values._PERSONAL_VARS` (ФИО, паспорт, дата рождения) — берутся только из `clients` или `legend`, **не** из `variable_value_history` (защита от утечки между клиентами) | `services/values.py:_PERSONAL_VARS` | — | нет |
| D.3.6 | Дефолты **не подставляются** | Поля с `default_value` (например «Москва») в собранный документ **не идут** — если переменная пуста, остаётся пустой | `services/autofill.py:skip_defaults` | — | нет |
| D.4 | **Шаг 3: Проверка минимального набора** | `services.autofill.check_min_values()` — для каждого слота считает, сколько значений подставлено; если <5 — слот откладывается | `services/autofill.py:check_min_values` | `check_min` | да, если хотя бы один слот <5 значений |
| D.5 | **Шаг 4: Логическая проверка пакета** | `services.checks.logical.run()` — все документы пакета сверяются между собой: ФИО везде одинаковое, дата рождения одна, паспорт один, адрес сходится | `services/checks/logical.py:run` | `check` | да, если есть расхождения |
| D.5.1 | Сверка ФИО | `legal_name_latin` из всех документов должен совпадать с `legend.full_name_latin` | `services/checks/logical.py:check_fio` | — | нет, только WARN |
| D.5.2 | Сверка даты рождения | `date_of_birth` из всех документов должен совпадать с `legend.date_of_birth` | `services/checks/logical.py:check_dob` | — | нет |
| D.5.3 | Сверка паспорта | `passport_number` одинаковый во всех справках | `services/checks/logical.py:check_passport` | — | да, если в одном документе другой |
| D.5.4 | Сверка адреса | `address_reg` в справках банка = `address_live` или = адрес регистрации | `services/checks/logical.py:check_address` | — | нет |
| D.5.5 | Сверка банка | `bank_name` во всех справках один | `services/checks/logical.py:check_bank` | — | да |
| D.5.6 | Сверка ITK | `stay_permit_no` присутствует в легенде, `expiry_date` > сегодня | `services/checks/logical.py:check_itk` | — | нет |
| D.5.7 | Сверка компании | `company_name`, `company_inn` одинаковы во всех документах (договор, справка) | `services/checks/logical.py:check_company` | — | нет |
| D.6 | **Шаг 5: Визуальная проверка** | `services.pdf_quality.scan()` — каждый PDF сканируется на: «лишний текст» (фрагменты шаблона, которые не должны быть видны), `{{ }}` в видимом тексте, размытые участки, обрезанный текст, цвет | `services/pdf_quality.py:scan` | `visual` | да, если найдено >2 проблем |
| D.6.1 | Поиск меток `{{ }}` | `pypdf` извлекает текст, ищет `{{` или `}}` | `services/pdf_quality.py:check_unfilled` | — | да |
| D.6.2 | Поиск фрагментов HTML | Если в PDF есть «`<` `>` `&nbsp;` — это значит рендер не сработал | `services/pdf_quality.py:check_html` | — | да |
| D.6.3 | Поиск пустых блоков | Если в визуально видимой области есть пустые прямоугольники >5% страницы | `services/pdf_quality.py:check_blanks` | — | нет, только WARN |
| D.6.4 | Поиск мусора | «Lorem ipsum», «TODO», «FIXME» | `services/pdf_quality.py:check_garbage` | — | да |
| D.7 | **Шаг 6: Согласованность пакета** | `services.checks.pack.run()` — все ли обязательные документы пода есть (по `product_documents.required=True`) | `services/checks/pack.py:run` | `pack` | да, если нет хотя бы одного обязательного |
| D.7.1 | Список обязательных | Для каждого продукта в `data/products.json` указано: какие шаблоны `required` | `data/products.json` | — | — |
| D.7.2 | Список бонусных | Шаблоны `required=False` (например, второе письмо) — идут если есть, не идут если нет | `data/products.json` | — | нет |
| D.7.3 | Список отклонённых | Шаблоны `status='rejected'` (например, отклонённый банк) — не идут и в финальном списке не показываются | `application_documents` | — | нет |
| D.8 | Запись в `app_steps` | `fill: ok` — все слоты собраны, проверки пройдены | `scripts/auto_cycle.py:273` | `fill` | — |

## Фаза E. Подтверждение и отправка (от «галочки ставит система» до «уведомление отправлено»)

| # | Этап | Что делает система | Где в коде | Шаг в `app_steps` | Стоп? |
|---|------|---------------------|-----------|-------------------|-------|
| E.1 | **Шаг 7: Авто-пометка verified** | `services.checks.verify.run()` — все слоты пакета, прошедшие проверки, получают `status='verified'` (галочка) автоматически | `services/checks/verify.py:run` | `verify_docs` | нет, частичная пометка |
| E.2 | **Шаг 8: Финальная проверка** | `services.checks.final.run()` — повторная сверка всего пакета перед отправкой (защита от гонок: между E.1 и E.4 что-то могло измениться) | `services/checks/final.py:run` | `final` | да, если что-то сломалось |
| E.3 | **Шаг 9: Маршрутизация замечаний (если есть)** | `services.checks.route.run()` — замечания делятся на: `auto` (система сама исправит в следующей попытке), `template` (правка шаблона), `client` (правка данных клиента) | `services/checks/route.py:run` | `route` | нет |
| E.4 | **Шаг 10: Сборка комплекта в `data/out/<app_id>/`** | `services.transport.drive.collect_pack()` — все verified-PDF собираются в одну папку; проверяется, что все обязательные шаблоны там | `services/transport/drive.py:collect_pack` | `collect` | да, если не все шаблоны |
| E.5 | **Шаг 11: Отправка на Google Drive** | `services.transport.drive.upload()` — для каждого PDF вызывается `gdrive_write.upload_to_folder(folder_id, file_name, bytes)`; папка — `gdrive_folder_url` клиента | `services/transport/drive.py:upload` | `upload` | да, если upload упал |
| E.5.1 | Throttle | `services.drive_throttle.can_call()` — не больше 60 заходов в минуту | `services/drive_throttle.py:can_call` | — | да, если превышен лимит |
| E.5.2 | OAuth / Service Account | Загрузка идёт через **OAuth-токен владельца** (`services/gdrive_write.py`, scope `drive.file`) — иначе SA не имеет квоты | `services/gdrive_write.py:upload_to_folder` | — | да, если токен истёк |
| E.5.3 | Прогресс | `auto_runs.files` обновляется по мере загрузки; `events` пишет `uploaded <file>` | `services/transport/drive.py:upload` | — | нет |
| E.5.4 | Verify | После загрузки `gdrive_api.list_files(folder_url)` — проверить, что все файлы видны | `services/gdrive_api.py:list_files` | — | да, если расхождение |
| E.6 | **Шаг 12: Уведомления** | `services.notifier.facade.notify_all()` — отправка в Telegram (админу, владельцу заявки, агенту-монитору) + запись в `events` | `services/notifier/facade.py:notify_all` | `notify` | нет, уведомления идут в фоне |
| E.6.1 | Админу | «Заявка #N отправлена на Google Drive, 7 файлов» | `services/notifier/telegram.py:notify_admin` | — | нет |
| E.6.2 | Владельцу заявки | «Ваши документы готовы и загружены» (если у клиента есть `telegram_id`) | `services/notifier/telegram.py:notify_client` | — | нет |
| E.6.3 | Агенту-монитору | «Цикл #N завершён за X секунд, ok=1, sent=1, files=7» | `services/notifier/agent.py:notify_agent` | — | нет |
| E.7 | **Шаг 13: Перевод в архив** | `applications.status='closed'`, `record_kind='archive'`, `closed_at=now()` | `services/auto_runner.py:archive` | `archive` | нет |
| E.8 | **Шаг 14: Очистка `auto_queue`** | `auto_queue.status='done'`, `finished_at=now()` | `services/auto_runner.py:finish` | — | нет |
| E.9 | Запись в `app_steps` | `done: ok` — заявка закрыта, в архиве | `scripts/auto_cycle.py:430-440` | `done` | — |

## Фаза F. Визуализация на сайте (что админ видит на странице заявки)

| # | Блок на странице | Что отображает | Обновляется |
|---|------------------|----------------|-------------|
| F.1 | Шапка заявки | ID, клиент, продукт, статус (`new` / `processing` / `closed`), таймер «от приёма», спиннер | каждые 2 сек (live JS) |
| F.2 | Прогресс документов | «📄 рендер документов: 5/11 · осталось 6» — `docs_state()` | каждые 2 сек |
| F.3 | Список документов | Карточки по каждому слоту: `name`, `status` (draft/filled/verified/rejected/sent), кнопки «Открыть», «Пометить Ок» | при изменениях |
| F.4 | Превью PDF | Кнопка «Открыть PDF» → `data/renders/<id>/<code>.pdf` (или `out/<id>/<code>.pdf` если отправлен) | при изменениях |
| F.5 | Журнал этапов | Таблица `app_steps`: время, этап, статус, длительность, примечание | при изменениях |
| F.6 | События | Таблица `events`: время, действие, актор, payload | при изменениях |
| F.7 | Разбор Drive | Ссылка на `drive_scans.report_html` — что было в папке клиента, что распознано | при изменениях |
| F.8 | Кнопки управления | «🚀 Запустить обработку», «⏸ Пауза», «❌ Отклонить документ», «📤 Отправить вручную» (только при `paused`) | всегда |

## Как читать журнал этапов

| `step` в `app_steps` | Что значит | Когда появился |
|----------------------|------------|---------------|
| `received` | Заявка пришла из бота | Этап A.3 |
| `product` | Продукт определён | Этап A.4 |
| `taken` | Цикл начал работу | Этап B.1 |
| `read_drive` | Разбор Google Drive запущен | Этап B.2 |
| `read_request` | Чтение заявки (приоритет паспорта) | Этап B.3 (старая логика) |
| `legend` | Легенда клиента построена | Этап B.3.5 |
| `bank_choice` | Банк выбран | Этап C.1 (новое) |
| `org_assigned` | Организация назначена | Этап C.2 (новое) |
| `address_assigned` | Адрес в РФ назначен | Этап C.3 (новое) |
| `uni_assigned` | ВУЗ назначен (D12) | Этап C.4 (новое) |
| `normalize` | Значения нормализованы | Этап C.5 (новое) |
| `derive` | Зависимые переменные вычислены | Этап C.6 (новое) |
| `prepare_vars` | Подготовка переменных завершена | Этап C.7 (новое) |
| `ensure_slots` | Слоты пакета созданы | Этап D.1 (новое) |
| `fill` | Подстановка переменных в шаблоны | Этап D.3 |
| `check` | Логическая проверка | Этап D.5 |
| `visual` | Визуальная проверка | Этап D.6 (новое) |
| `pack` | Согласованность пакета | Этап D.7 (новое) |
| `verify_docs` | Документы подтверждены | Этап E.1 |
| `final` | Финальная проверка | Этап E.2 |
| `route` | Маршрутизация замечаний | Этап E.3 (новое) |
| `collect` | Сборка комплекта | Этап E.4 (новое) |
| `upload` | Отправка на Google Drive | Этап E.5 |
| `notify` | Уведомления | Этап E.6 |
| `archive` | Заявка в архиве | Этап E.7 (новое) |
| `done` | Цикл завершён успешно | Этап E.9 |
| `final: fail` | Цикл завершён с ошибкой | любой этап |
| `done: warn` | Цикл завершён с предупреждениями | любой этап |

## Что есть сейчас vs что планируется

| Этап | Сейчас | Планируется |
|------|--------|-------------|
| A.1-A.6 | ✅ Работает | — |
| B.1 | ✅ Работает | — |
| B.2 (Drive) | ✅ Работает (этап 22) | Детальные подэтапы в журнал |
| B.3 (легенда) | ✅ Работает | Расширить подэтапы |
| C.1 (банк) | ✅ Работает | Помечать в `app_steps` явно |
| C.2 (организация) | ✅ Работает | Помечать в `app_steps` явно |
| C.3 (адрес) | ⚠️ Частично | Доделать |
| C.4-C.6 | ⚠️ Частично | Доделать |
| C.7 | ❌ Нет записи | Добавить `_db_log('prepare_vars', 'ok', ...)` |
| D.1 (слоты) | ✅ Работает | Записывать в `app_steps` |
| D.2 (фильтр банков) | ✅ Работает | — |
| D.3 (подстановка) | ✅ Работает (этап 18) | Детальный пошаговый лог в `events` |
| D.5-D.7 (проверки) | ✅ Работают | Помечать каждую проверку отдельной строкой |
| E.1 (verified) | ✅ Работает | — |
| E.5 (upload) | ✅ Работает | — |
| E.6 (notify) | ✅ Работает | — |
| E.7 (архив) | ✅ Работает (этап 20) | — |
| F.1-F.8 (визуализация) | ⚠️ Частично | Добавить таймеры длительности, прогресс-бар |

## План доделки

1. **Этап 24**: добавить в `app_steps` записи для C.7, D.1, D.7, E.4, E.7 — чтобы каждый шаг был виден в журнале
2. **Этап 25**: добавить в `events` подробный лог подстановки переменных (какой шаблон, какая переменная, откуда взято)
3. **Этап 26**: на странице заявки показывать прогресс-бар по этапам A→E с подсветкой текущего
4. **Этап 27**: добавить кнопку «Принудительно повторить этап N» — для отладки
