# Движки документов: HTML и Word (зафиксировано 16.10.2026)

## Решение (Андрей, 16.10.2026)
Один документ = один шаблон = один движок. Движок хранится в `templates.engine`.

- `html` — координатная сетка без подложки. **4 банковские справки** (3m/12m × Т-Банк/Сбер).
- `word` — DOCX-шаблон, текст течёт сам, ничего не налезает. **7 документов**: письма bridging/conversion,
  Statement Letter E-02, D12, резюме (cv__format_sivaev), оба договора (employment, remote work).

Закрыто и убрано (файлы: /opt/wolf_backups/templates_removed_20261016):
каркас с подложкой `bg` (скан предыдущего клиента), подстановка в PDF (pdf_fill / pdf_overlay / pdf_map*),
merged-шаблоны (ngurahrai, tabanan, denpasar, e02 conversion), hidden-резюме (short, detailed), мусор (_archive, test_sber, *.bak*).

## Единый движок
`services/doc_engine.py` — один вход для всех:

    build_document(code, values, out_dir, engine=None, name=None)

- `engine='word'` → `build_word()`: docxtpl + LibreOffice → PDF (+ список пустых переменных).
- `engine='html'` → `build_html()`: services/render (weasyprint).
- `placeholders_left()` — проверка: остались ли `{{...}}` в готовом PDF (такой документ выпускать нельзя).

Используется: конструктор (`/templates/<id>/preview_pdf`) и выпуск заявок.

## Конструктор
- Подпись вкладки = движок: **HTML** или **Word** (было всегда «HTML»).
- Кнопка «Оригинал» — настоящий заполненный документ (`example_filled.pdf`).
- Кнопка «Сравнение» — два листа рядом: оригинал и наша сборка (`/templates/compare/<id>`).
- «Просмотр PDF» — сборка тем же движком, что и выпуск.

## Требуется в Word-шаблонах (открыто)
- `scripts/word_from_html.py` переносит только блоки `<span class="v">` (значения) — теряются статические
  подписи полей («Nama», «Pekerjaan», «No. Paspor»). Нужно переносить ВСЕ блоки, сохраняя координаты.
- В старых Word-шаблонах (от 06–07.10) параметризация кривая: E-02 — 263 метки на 17 уникальных,
  справка 3m ТБанк — `ref_no` размножен на 13 строк. Пересобирать из HTML.
- Проверено хорошо: `employment_contract__default`, `remote_work_agreement__default`
  (тест коротких/средних/длинных значений: текст в границах, за краем нет).

## Проверка перед выпуском
1. `doc_engine.placeholders_left(pdf)` — пусто.
2. Список пустых переменных (`missing`) — либо заполнить, либо подтвердить, что поле в документе пустое (как ITK у новой заявки).
3. Сверка с эталоном: `/templates/compare/<id>` (оригинал | наша сборка).

## Word-окружение
- Сайт (`wolf-crm-v2.service`) работает на `/usr/bin/python3`; `docxtpl 0.20.2` установлен и туда
  (pip --break-system-packages), и в `.venv_docs`.
- Конвертация DOCX → PDF: `/usr/bin/soffice --headless --convert-to pdf`.
