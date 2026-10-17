# Реестр шаблонов Wolf AutoDoc

Зафиксировано: 16.10.2026 08:03. Один документ = один шаблон = один движок.

Движок: `word` — поток текста (DOCX-шаблон), `html` — координатная сетка (без подложки).

| документ (код) | движок | переменных | продуктов | эталон | хэш шаблона |
|---|---|---|---|---|---|
| bank_statement_12m__sber | html | 13 | E33G-EXT, E33G-NEW | example_filled.pdf | `ca587dd3039b7823` |
| bank_statement_12m__tbank | html | 13 | E33G-EXT, E33G-NEW | example_filled.pdf | `2e087aa7936b47a3` |
| bank_statement_3m__sber | html | 13 | C1, C1-EXT, D12, E33G-EXT, E33G-NEW | example_filled.pdf | `ca2df896cdc6e297` |
| bank_statement_3m__tbank | html | 10 | BRIDGING, C1, C1-EXT, D12, E33G-EXT, E33G-NEW | example_filled.pdf | `767e56157b9660d9` |
| bridging_request_letter__default | word | 38 | BRIDGING | example_filled.pdf | `d5f77808eab79da5` |
| conversion_request_letter__default | word | 44 | CONV | example_filled.pdf | `9854695d7eeb3e22` |
| cv__format_sivaev | word | 22 | BRIDGING, CONV, D12, E33G-EXT, E33G-NEW | example_filled.pdf | `9a2abe731d6f4777` |
| d12_cover_letter__default | word | 33 | D12 | example_filled.pdf | `aa83ea9122ed02f1` |
| employment_contract__default | word | 26 | BRIDGING, C1-EXT, CONV, D12, E33G-EXT, E33G-NEW | example_filled.pdf | `f59dd73e7838f248` |
| remote_work_agreement__default | word | 34 | BRIDGING, C1-EXT, CONV, D12, E33G-EXT, E33G-NEW | example_filled.pdf | `9e2412b1f5c29fcc` |
| statement_letter_e02__default | word | 22 | BRIDGING, CONV | example_filled.pdf | `b02f7d80a517c9e1` |

## Что закрыто (не используется, файлы в /opt/wolf_backups/templates_removed_20261016)
- merged: bridging ngurahrai/tabanan, conversion denpasar, e02 conversion
- hidden: cv short/detailed
- мусор: _archive, test_sber, две папки .bak_before_relink2
- закрытые пути сборки: каркас с подложкой (bg), подстановка в PDF (pdf_fill / pdf_overlay / pdf_map*)

## Слепки (защита от пропажи)
- /opt/wolf_v2/data/backups/template_snapshots/ — манифест с хэшами по каждому шаблону
