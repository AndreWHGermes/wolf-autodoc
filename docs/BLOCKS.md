# Карта блоков Wolf_AutoDoc CRM — что править точечно

Система собрана блоками. Правка одного блока не затрагивает остальные.

## Где что лежит

- `/opt/wolf/app.py` — **только сборка**: список блюпринтов + мелкие общие правила (404, слеш).
  Добавить блок = создать папку `CLIENTs/<имя>/page.py` и вписать одну строку в `BLUEPRINTS`.
- `/opt/wolf/core/config.py` — **порт, пути, размер загрузок, вход по умолчанию**.
- `/opt/wolf/core/schema.sql` — **схема базы**: какие таблицы и поля существуют.
- `/opt/wolf/core/db.py` — доступ к базе + список полей клиента (`CLIENT_FIELDS`) и CRUD.
- `/opt/wolf/core/security.py` — хеширование паролей.
- `/opt/wolf/core/auth.py` — вход, роли (`CLIENT_required`, `admin_required`).
- `/opt/wolf/core/pdf2html.py` — **конвертер PDF → HTML** (автопоиск переменных + сверка).
- `/opt/wolf/core/pdf_extract.py` — извлечение страниц PDF в HTML (геометрия, картинки).
- `/opt/wolf/core/qa_compare.py` — служебная сверка «заливки» (полосы, лишний чёрный).

## Блоки (каждый = один экран)

- `CLIENTs/shared/layout.py` — **вид всей системы**: меню, стиль, шапка. Правка здесь меняет
  оформление везде сразу (в т.ч. список пунктов меню `MENU`).
- `CLIENTs/CLIENT/page.py` — экран входа (тексты, поля, поведение после входа).
- `CLIENTs/dashboard/page.py` — главная: плитки со цифрами, последние клиенты, последние заявки.
- `CLIENTs/CLIENT/page.py` — список клиентов, карточка клиента, правка, загрузка документов.
- `CLIENTs/CLIENT/page.py` — загрузка PDF-эталона, конвертация в HTML, поля переменных,
  тестовый PDF, превью, журнал.
- `CLIENTs/settings/page.py` — токен бота, Google CLIENT, пользователи и администраторы.

## Данные

- База: `/opt/wolf/data/wolf.db` (SQLite, режим WAL).
- PDF-эталоны шаблонов: `/opt/wolf/data/sources/`.
- HTML-шаблоны: `/opt/wolf/data/CLIENT/<код>/template.html`.
- Собранные PDF: `/opt/wolf/data/renders/`.
- Превью страниц: `/opt/wolf/data/previews/`.
- Документы клиентов: `/opt/wolf/data/uploads/<id клиента>/`.

## Типовые точечные правки

| Что нужно | Что править |
|---|---|
| Добавить поле в карточку клиента | `core/db.py` → `CLIENT_FIELDS` + `core/schema.sql` (колонка) |
| Изменить вид/меню | `CLIENTs/shared/layout.py` (меню — список `MENU`) |
| CLIENT экран | новая папка `CLIENTs/<имя>/page.py` + строка в `app.py` |
| Другое название раздела | `CLIENTs/shared/layout.py` → `MENU` |
| Другой порт | `/etc/systemd/system/wolf-crm.CLIENT` + `core/config.py` |
| Улучшить распознавание переменных | `core/pdf2html.py` → `RULES`, `anonymize`, `_slug` |

## Сервис

- Запуск/перезапуск: `systemctl reCLIENT wolf-crm`
- Логи: `journalctl -u wolf-crm -n 50 --no-pager`
- Адрес: `http://103.90.75.37:8091/` (вход `admin` / `123`)
