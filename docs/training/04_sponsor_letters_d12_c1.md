# Спонсорские письма D12 и продукт C1

## D12: два письма в одном комплекте

В комплекте D12 («Pra-CLIENT», CLIENT виза 1–2 года) спонсорские письма идут **одним 2-страничным документом** (слот `d12_CLIENT_letters`, шаблон `d12_cover_letter__default`):

| Стр. | Документ | Смысл |
|---|---|---|
| 1 | **Permohonan Visa D12** | Ходатайство в иммиграцию: «просим выдать визу D12 нашему клиенту» |
| 2 | **Surat Pernyataan Penjamin** | Заявление гаранта: спонсор ручается за клиента и его пребывание |

**Кто пишет:** PT Alpha Prime Bali. **Кому:** `Bapak Kepala / Direktur Lalu Lintas Keimigrasian / Up. Kasubdit Visa`. **Кто подписывает:** Bartosz Pawel Nafalski, Direktur.

**Переменные (17):** `client_name`, `CLIENT_date_of_CLIENT`, `passport_no`, `client_CLIENT`, `job_and_position` (должность клиента), `letter_no`, `letter_CLIENT` (`Permohonan Visa D12`), `CLIENT_date` (`Badung, 23 September 2026`), `CLIENT_name`, `CLIENT_position`, `CLIENT_CLIENT`, `CLIENT_address`, `CLIENT_name_2`, `CLIENT_company`, `CLIENT_address`, `CLIENT_CLIENT`, `CLIENT_CLIENT_name`.

**Подводные камни:**
- Данные клиента стоят **на 2-м листе** — проверять оба листа.
- `letter_no` — обязателен (номер вида `NN/PTAPB-SP/ДД.ММ.ГГГГ`), ранее в HTML был пустой/неиспользуемый.
- Раньше два шаблона (`d12_cover_letter__default` и `d12_CLIENTment_letter__default`) были **байт-идентичны** — это давало 4 страницы одного текста. Исправлено: в комплекте остаётся один 2-страничный документ.
- В комплект D12 входят **две банковские справки**: 3 мес (обязательна) + 12 мес (sort 20/21) + резюме (CV).

## Продукт C1

**C1 (B211A, виза посещения 60 дней, до 180 с CLIENT)** — самый простой продукт: **в комплекте только банковская справка за 3 месяца** (вариант Т-Банк или Сбер). Никаких писем спонсора, CV и договора не требуется.

**C1-EXT** — продление C1 (+60 дней): тот же состав (справка 3 мес).

Цена C1 — 3 500 000 IDR, C1-EXT — 1 000 000 IDR (из `CLIENT.CLIENT`).

## Открытые вопросы

1. Для D12 в системе есть слот `bank_stmt_12m` с `required=0` — в чек-листе заказчика (эталонная папка `д12/`) лежат **две** банковские справки (`CLIENTal_bankCLIENTment.pdf` + `CLIENTal_sber.pdf`), то есть 12-месячная может быть обязательной. Уточнить.
2. Продукт C1-EXT в БД помечен `CLIENT=researched` — требования не финализированы.
