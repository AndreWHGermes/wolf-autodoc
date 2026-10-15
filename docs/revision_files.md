# Инвентаризация /opt/wolf_v2 — файлы и мусор

## 1. Все .py по директориям (294 файла)

### scripts/ (200 файлов)

| Файл | Назначение |
|---|---|
| auto_queue.py | Воркер очереди (cron: */2 * * * *) |
| auto_cycle.py | Цикл автогенерации документов |
| backup.py | Бэкап БД (cron: hourly) |
| build_cv_from_example.py | Сборка CV из примера |
| build_guide.py | Сборка гайда |
| build_html_doc.py | HTML-документ из шаблона |
| build_html_flow.py | HTML-поток документа |
| build_html_frame.py | HTML-фрейм |
| build_one_doc.py | Сборка одного документа |
| build_ru_templates.py | Сборка RU-шаблонов |
| addr_cols.py | Адресные колонки |
| addr_offsets.py | Смещения адресов |
| addr_overlap.py | Перекрытие адресов |
| addr_verify_all.py | Проверка адресов |
| adopt_html_template.py | Адаптация HTML-шаблона |
| analyze_cv_archive.py | Анализ CV-архива |
| app_autoprepare.py | Автоподготовка заявки |
| apply_columns.py | Применение колонок |
| apply_guide_to_db.py | Применение гайда в БД |
| apply_margins.py | Применение полей |
| app_prepare.py | Подготовка заявки |
| audit_examples.py | Аудит примеров |
| autobuild_check.py | Проверка автосборки |
| automap_pool.py | Автомаппул пула |
| automark_values.py | Автомаркировка значений |
| balance_rules.py | Балансировка правил |
| check_addr_box.py | Проверка адресного бокса |
| check_documents.py | Проверка документов |
| check_history_query.py | Проверка истории |
| check_templates_vs_originals.py | Сравнение шаблонов с оригиналами |
| clean_cache.py | Очистка кэша |
| client_docs_matrix.py | Матрица клиентских документов |
| collect_amounts.py | Сбор сумм |
| collect_translation_keys.py | Сбор translation-ключей |
| columns_inventory.py | Инвентаризация колонок |
| compact_photos.py | Сжатие фото |
| compact_rwa.py | Компактизация RWA |
| compare_html_pdf.py | Сравнение HTML/PDF |
| compare_html_vs_pdf.py | Сравнение HTML vs PDF |
| compare_structure.py | Сравнение структур |
| compare_templates.py | Сравнение шаблонов |
| compare_with_manager.py | Сравнение с менеджером |
| cv_drop_catalogue.py | Сброс каталога CV |
| cv_fix_three.py | Исправление CV-3 |
| cv_flow.py | CV-поток |
| cv_links_ru.py | CV-ссылки RU |
| cv_phrases_ru.py | CV-фразы RU |
| cv_scan.py | Сканирование CV |
| cv_scan2.py | Сканирование CV v2 |
| cv_scan3.py | Сканирование CV v3 |
| cv_stress.py | CV-стресс-тест |
| diag_doc1.py | Диагностика doc1 |
| diag_history.py | Диагностика истории |
| doc_layout_check.py | Проверка layout документа |
| doc_number_rules.py | Правила нумерации документов |
| docs_registry.py | Реестр документов |
| doc_stress.py | Стресс-тест документа |
| drive_classify.py | Классификация Drive |
| drive_pull_all.py | Pull всех файлов с Drive |
| drive_scan.py | Сканирование Drive |
| example_values_extract.py | Извлечение example-значений |
| fetch_missing.py | Загрузка пропущенных |
| fill_cache_parallel.py | Параллельная заливка кэша |
| fill_translation_cache.py | Заливка translation-кэша |
| final_audit.py | Финальный аудит |
| find_long_statements.py | Поиск длинных выписок |
| find_olga.py | Поиск по Ольге (person-specific) |
| find_olga2.py | Поиск по Ольге v2 |
| finish_translation.py | Завершение перевода |
| fix_3m_tbank_header.py | Исправление заголовка 3m-tbank |
| fix_agreement_examples.py | Исправление agreement-examples |
| fix_bank_examples.py | Исправление bank-examples |
| fix_block_widths.py | Исправление ширин блоков |
| fix_broken_words.py | Исправление сломанных слов |
| fix_char_spans.py | Исправление char-spans |
| fix_columns2.py | Исправление колонок v2 |
| fix_contract_services.py | Исправление contract-services |
| fix_d12_examples.py | Исправление D12-examples |
| fix_html_paths.py | Исправление HTML-путей |
| fix_letter_examples.py | Исправление letter-examples |
| fix_margin_block.py | Исправление margin-блока |
| fix_originals.py | Исправление originals |
| fix_overflow.py | Исправление overflow |
| fix_pack_integrity.py | Проверка целостности пакета |
| fix_text_color.py | Исправление цвета текста |
| fix_text_size.py | Исправление размера текста |
| fix_text_spacing.py | Исправление интервалов |
| fix_word_split.py | Исправление split-слов |
| frame_all.py | Фрейм всех |
| gate_report.py | Отчёт gate |
| gen_doc1.py | Генерация doc1 |
| harvest_orgs.py | Сбор организаций |
| install_frame_html.py | Установка frame HTML |
| inventory_real_examples.py | Инвентаризация реальных примеров |
| kit_consistency.py | Консистентность kit |
| kit_status.py | Статус kit |
| letters_by_office.py | Письма по офису |
| letters_conversion.py | Конвертация писем |
| letters_signer.py | Подписант писем |
| map_by_labels.py | Маппинг по меткам |
| map_cv_fields.py | Маппинг CV-полей |
| map_letter_fields.py | Маппинг letter-полей |
| mark_cv_examples.py | Маркировка CV-примеров |
| mark_cv_examples_full.py | Полная маркировка CV-примеров |
| mark_records.py | Маркировка записей |
| marks_map.py | Карта маркировок |
| mem_guard.py | Охрана памяти (debug) |
| merge_apply.py | Merge apply |
| merge_continuations.py | Слияние continuation |
| merge_e02.py | Слияние E02 |
| merge_letters.py | Слияние писем |
| migrate.py | Миграция |
| migrate_letter_docs.py | Миграция letter-docs |
| one_bank_statement.py | Один bank-statement |
| one_cv.py | Один CV |
| overlap_check.py | Проверка перекрытий |
| overlay_diff.py | Diff overlay |
| pack_gaps_report.py | Отчёт по gaps пакета |
| packs_by_product.py | Паки по продукту |
| pack_selftest.py | Самотест пакета |
| packs_guide.py | Гайд пакетов |
| paragraph_flow.py | Поток абзацев |
| pdf_fill.py | Заполнение PDF |
| pdf_map.py | Маппинг PDF |
| pdf_map2.py | Маппинг PDF v2 |
| pdf_map3.py | Маппинг PDF v3 |
| pdf_map4.py | Маппинг PDF v4 |
| pdf_map5.py | Маппинг PDF v5 |
| pdf_map_extra.py | Доп. маппинг PDF |
| pdf_overlay_demo.py | Демо overlay PDF |
| pdf_overlay_v2.py | Overlay PDF v2 |
| pdf_prepare.py | Подготовка PDF |
| pdf_to_template.py | PDF → шаблон |
| pdf_vs_html.py | PDF vs HTML |
| pick_examples.py | Выбор примеров |
| pick_originals.py | Выбор originals |
| polish_contract.py | Полировка contract |
| preview_check.py | Проверка preview |
| preview_highlight.py | Highlight preview |
| profile_page.py | Страница профиля |
| profile_queries.py | Запросы профиля |
| qa_html.py | QA HTML |
| real_kit_run.py | Запуск реального kit |
| rebuild_3m_tbank.py | Пересборка 3m-tbank |
| rebuild_bank_statement.py | Пересборка bank-statement |
| rebuild_contract.py | Пересборка contract |
| rebuild_e02_from_example.py | Пересборка E02 из примера |
| rebuild_example.py | Пересборка example |
| rebuild_from_example.py | Пересборка из примера |
| rebuild_letter.py | Пересборка letter |
| refresh_all.py | Обновление всего |
| relax_flow.py | Расслабление flow |
| relink_template.py | Перелинковка шаблона |
| render_all_png.py | Рендер всех PNG |
| render_doc.py | Рендер документа |
| render_pack.py | Рендер пакета |
| renumber_documents.py | Перенумерация документов |
| research_card_source.py | Источник card-research |
| restore_dotted_lines.py | Восстановление пунктирных линий |
| restore_signature_lines.py | Восстановление сигнатурных линий |
| right_edge_audit.py | Аудит правого края |
| ru_labels.py | RU-метки |
| scan_passports_fio.py | Сканирование паспортов FIO |
| scope_frame.py | Scope фрейм |
| selfcheck.py | Самопроверка |
| sess2.py | Сессия v2 (устаревшая) |
| sess3.py | Сессия v3 (устаревшая) |
| sess_cookie.py | Cookie сессии |
| shift_overlaps.py | Сдвиг перекрытий |
| side_by_side.py | Побочный сравнительный |
| snapshot_templates.py | Снапшот шаблонов |
| spravka_to_docx.py | Справка → DOCX |
| static_lines_report.py | Отчёт по static-lines |
| stress_test.py | Стресс-тест (one-off) |
| structure_rules.py | Правила структуры |
| sync_archive.py | Синхронизация архива |
| sync_archive_api.py | Sync archive API |
| sync_example_values.py | Синхронизация example-значений |
| templatize.py | Шаблонизация |
| test_addr_wrap.py | Тест addr-wrap |
| tpl_audit.py | Аудит шаблонов |
| variables_guide.py | Гайд переменных |
| variables_rules.py | Правила переменных |
| var_instructions.py | Инструкции переменных |
| var_order.py | Порядок переменных |
| verify_3m_tbank.py | Проверка 3m-tbank |
| verify_columns_all.py | Проверка всех колонок |
| viewer_shot.py | Скриншот viewer (one-off) |
| visual_check.py | Визуальная проверка |
| visual_compare.py | Визуальное сравнение |
| warm_cache.py | Разогрев кэша |
| watch_autorun.py | Авторан-монитор |
| watch_new_app.py | Монитор новых заявок |
| word_flow.py | Word-поток |
| word_from_html.py | Word из HTML |
| word_run.py | Запуск Word |
| word_template.py | Word-шаблон |
| word_test_fill.py | Test-fill Word |
| y_zone.py | Y-зона (debug) |
| zone_png.py | PNG-зона (debug) |
| client_data/*.py (11 файлов) | Клиентские данные: coverage, fill, fix, mark, sync |

### services/ (45 файлов)

| Файл | Назначение |
|---|---|
| auto_runner.py | Главный autorun-цикл |
| address_pool.py | Пул адресов |
| addr_order.py | Порядок адресов |
| app_steps.py | Шаги заявки |
| autofill.py | Автозаполнение |
| bank_choice.py | Выбор банка |
| brief_values.py | Краткие значения |
| cv_fill.py | Заполнение CV |
| cv_gen.py | Генерация CV |
| doc_check.py | Проверка документа |
| doc_overrides.py | Переопределения документа |
| doc_parse.py | Разбор документа |
| doc_read.py | Чтение документа |
| doc_rules.py | Правила документа |
| drive.py | Drive-интеграция |
| drive_throttle.py | Троттлинг Drive |
| employer_pool.py | Пул работодателей |
| final_check.py | Финальная проверка |
| gdrive_api.py | Google Drive API |
| gdrive_oauth.py | GDrive OAuth |
| gdrive_write.py | Запись в GDrive |
| html_frame.py | HTML-фрейм |
| immigration_office.py | Иммиграционное управление |
| intake_gate.py | Входные ворота |
| itk_doc.py | ITK-документ |
| llm.py | LLM-вызовы |
| logical_check.py | Логическая проверка |
| marks.py | Маркировки |
| org_pool.py | Пул организаций |
| pack_check.py | Проверка пакета |
| pdf_quality.py | Качество PDF |
| photo.py | Фото |
| postmortem.py | Постмортем |
| previews.py | Превью |
| provenance.py | Provenance |
| reader_agent.py | Агент-читалка |
| render.py | Рендер |
| requested_product.py | Запрошенный продукт |
| salary_pool.py | Пул зарплат |
| self_heal.py | Самовосстановление |
| translate.py | Перевод |
| value_cache.py | Кэш значений |
| values.py | Значения |
| var_methods.py | Методы переменных |
| __init__.py | Пакет |

### core/ (9 файлов)

| Файл | Назначение |
|---|---|
| auth.py | Авторизация |
| config.py | Конфигурация |
| db.py | БД |
| log.py | Логирование |
| pdf2html.py | PDF→HTML |
| pdf_extract.py | Извлечение PDF |
| qa_compare.py | QA-сравнение |
| ru_labels.py | RU-метки |
| security.py | Безопасность |

### bot/ (3 файла)

| Файл | Назначение |
|---|---|
| wolf_bot.py | Telegram-бот |
| notify.py | Уведомления |
| ai_parser.py | AI-парсер |

### blocks/ (15 файлов)

| Файл | Назначение |
|---|---|
| dashboard/events.py | События дашборда |
| dashboard/page.py | Страница дашборда |
| guide/__init__.py | Пакет гайда |
| guide/page.py | Страница гайда |
| history/page.py | Страница истории |
| login/page.py | Страница логина |
| review/__init__.py | Пакет review |
| review/page.py | Страница review |
| review/pool.py | Пул review |
| review/scripts.py | Скрипты review |
| review/styles.py | Стили review |
| settings/page.py | Страница настроек |
| shared/health.py | Health-check |
| shared/layout.py | Общий layout |
| templates/page.py | Шаблон страницы |

### Корень

| Файл | Назначение |
|---|---|
| app.py | Flask CRM v2 (systemd: wolf-crm-v2.service) |

## 2. Группировка

**Рабочие (запускаются из крона / systemd / бота):**
- scripts/auto_queue.py — cron `*/2 * * * *`
- scripts/auto_cycle.py — вызывается из auto_queue
- services/auto_runner.py — ядро цикла
- bot/wolf_bot.py — systemd `wolf-bot.service`
- app.py — systemd `wolf-crm-v2.service`
- scripts/backup.py — cron hourly
- services/self_heal.py, services/postmortem.py — фоновые
- core/db.py, core/log.py — инфраструктура

**Вспомогательные разовые (пересборка шаблонов, правки, анализ):**
- scripts/build_*.py, scripts/rebuild_*.py, scripts/fix_*.py
- scripts/audit_*.py, scripts/verify_*.py, scripts/check_*.py
- scripts/pack_gaps_report.py, scripts/pack_selftest.py
- scripts/visual_*.py, scripts/compare_*.py
- scripts/client_data/*.py (11 шт.)

**Явно устаревшие:**
- scripts/sess2.py, sess3.py, sess_cookie.py — старая сессия
- scripts/find_olga.py, find_olga2.py — person-specific
- scripts/cv_scan2.py, cv_scan3.py — superseded cv_scan.py
- scripts/pdf_map2.py–pdf_map5.py, pdf_map_extra.py — superseded pdf_map.py
- scripts/zone_png.py, y_zone.py — debug-артефакты
- scripts/mem_guard.py — debug
- scripts/stress_test.py, cv_stress.py — one-off стресс
- scripts/viewer_shot.py — one-off
- scripts/test_addr_wrap.py — тест

## 3. Мусор

### Топ-10 мусорных позиций

| # | Объект | Размер | Тип |
|---|---|---|---|
| 1 | backups/docs_2026100[3-7]_0300.tar.gz (5 файлов) | 519+524+372+376+376 = **2.17 GB** | Старые бэкапы docs |
| 2 | data/templates_bak_20261006_0925/ (1764 файла) | **51 MB** | Дубли шаблонов с bak |
| 3 | data/templates_bank_backup_20260929_0756/ | **15 MB** | Бэкап шаблонов bank |
| 4 | data/templates_fonts_backup/ | **15 MB** | Бэкап шаблонов fonts |
| 5 | data/templates_defects_backup_20260929_0825/ | **13 MB** | Бэкап дефектных шаблонов |
| 6 | data/templates_video_backup_20260929_081[78]/ (2 директории) | **26 MB** | Бэкап video-шаблонов |
| 7 | backups/templates_bak_20261001/ | **2.0 MB** | Старый бэкап шаблонов |
| 8 | data/templates_dup_archive_20260929_0813/ | **2.5 MB** | Дубликат шаблонов |
| 9 | data/backups/template_snapshots/ (2 снапшота) | **36 MB** | Дубликаты snapshots |
| 10 | data/backup/ (JSON-бэкапы) + data/renders_backup_test/ | **5.1 MB** | Тестовые/дублирующие бэкапы |

### Прочий мусор

- **974 файла .bak/.bak_*** по core/, bot/, blocks/, scripts/, data/templates/ — от правок, именованный бэкап (bak_kind_073225, bak_paths, bak_lbl_063949 и т.д.)
- **12 дублирующихся template.html** в templates_bak vs templates_bank_backup (md5 совпадают)
- **0-byte пустые файлы**: 10 файлов в docs/txt_cache/ + .hermes-tmp.86DgxY (0 байт)
- **docs/wolf.db.bak_1247, docs/wolf.db.bak2_1307** — по 2.1 MB каждый
- **data/wolf.db.backup_pre_gdrive** — 128 KB
- **reports/rules_backup_*.json** — 3 копии правил
- **data/templates/employment_contract__default.bak_before_relink2/**, **remote_work_agreement__default.bak_before_relink2/** — 126 файлов в каждом, бэкап перед relink

### Огромных логов (>50 MB) — нет
Логи logs/ максимум ~156 KB (wolf.log). Логи ротейтятся.

## 4. Cron и systemd

### Crontab
```
0 * * * * /usr/bin/python3 /opt/wolf_v2/scripts/backup.py >> /opt/wolf_v2/logs/backup.log 2>&1
*/2 * * * * flock -n /var/lock/wolf_auto.lock -c '/usr/bin/python3 /opt/wolf_v2/scripts/auto_queue.py worker' >> /opt/wolf_v2/logs/auto_runner.log 2>&1
```

### Systemd
```
wolf-bot.service        active/running  Telegram-бот
wolf-crm-v2.service     active/running  Flask CRM v2 :8094
```

### Проверка: что запускают vs что есть
- `auto_queue.py` — в кроне, файл **есть** ✓
- `auto_cycle.py` — вызывается из auto_queue, файл **есть** ✓
- `auto_runner.py` — вызывается из auto_cycle, файл **есть** ✓
- `backup.py` — в кроне hourly, файл **есть** ✓
- `wolf_bot.py` — systemd, файл **есть** ✓
- `app.py` — systemd, файл **есть** ✓
- Нет запуска scripts/backup.py из systemd — только cron ✓ (ожидаемо)
- Нет systemd-юнитов для scripts/auto_cycle.py напрямую — запуск через auto_queue ✓

## Итого

- 294 .py файла: 200 scripts + 45 services + 9 core + 3 bot + 15 blocks + 1 app.py
- ~2.2 GB мусора в backups/docs_*.tar.gz
- ~133 MB в template_bak/backup директориях
- 974 .bak-файла по всему проекту
- 10+1 пустых файлов
- Крон и systemd синхронизированы с существующими файлами — рассинхрона нет