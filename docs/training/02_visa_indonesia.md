# Визовые документы Индонезии: Bridging, Conversion, Form E-02

## 1. Логика процесса (зачем всё это)

Иностранец въезжает в Индонезию по одной визе (например, C1 / B211A), затем хочет остаться и работать удалённо.
Иммиграция не меняет статус напрямую — нужен **двухшаговый переход**:

1. **Bridging Visa 60 hari** (мостовая виза, 60 дней, не продлевается) — временное разрешение, чтобы легально дождаться конверсии. Подаётся, пока действует текущее разрешение (важно: минимум за 3 дня до его окончания).
2. **Konversi Bridging → KITAS E33G Remote Worker** — конверсия в рабочее разрешение удалённого работника (5 лет для KITAS, при условии, что клиент работает на иностранную компанию и доход ≥ US$60 000/год).

Подаёт **не клиент**, а индонезийский спонсор **PT Alpha Prime Bali** через своего представителя по доверенности.
Адресаты — два разных отделения иммиграции на Бали (см. п. 4).

## 2. Три документа внутри одного комплекта

Каждый «комплект» — это **один PDF из 3 страниц**:

| Страница | Документ | Смысл | Кто подписывает |
|---|---|---|---|
| 1 | **Permohonan** | Ходатайство: «просим выдать мостовую визу / провести конверсию» с данными клиента | Marcellena Nirmala Chrisna Moeri (penerima kuasa) |
| 2 | **Surat Permintaan dan Jaminan** / **Surat Pernyataan dan Jaminan** | Письмо-запрос + **гарантия**: спонсор поручается за клиента и обязуется отвечать за последствия | Marcellena (от спонсора) |
| 3 | **Surat Kuasa** | Доверенность: PT Alpha Prime Bali уполномочивает представителя подавать документы | Pihak I — Bartosz Pawel Nafalski (Ngurah Rai) / Arine Fadillah (Denpasar) |

Плюс отдельный документ **Form E-02 (Statement Letter)** — одностраничное заявление клиента, где он подтверждает данные и цель, с маркой METERAI 10.000.

## 3. Переменные (по группам)

**Данные клиента:** `client_name`, `client_gender` (Laki-laki / Perempuan), `place_date_of_birth` (формат `RUSSIA / 08-01-1999`), `client_nationality` (`RUSIA`), `passport_no`, `address_in_indonesia` (адрес на Бали).

**Данные документа:** `letter_no` (`NN/PTAPB-SP/ДД.ММ.ГГГГ`), `date` / `place_date` (`Badung, 16 September 2026`), `letter_subject` (формула перехода), `application_no` (номер текущего разрешения вида `B12E21E1063044-C`).

**Выбор варианта:** `addressee_line1..3` (адресат), `sponsor_name` (подписант), `guarantor`, `signatory_*` (реквизиты подписанта).

**Постоянное (заполнено значением по умолчанию):** `sponsor_company` = PT ALPHA PRIME BALI, `sponsor_address`, `sponsor_contact` (Telp +62 811 397 9669, ptalphaprimeconsulting@gmail.com), `attorney_*` (Marcellena: Swasta, Indonesia, NIK 5171015403930001, Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya).

**Form E-02 дополнительно:** `full_name`, `place_of_birth`, `birth_date`, `nationality`, `occupation`, `passport_number`, `date_of_issue`, `date_of_expiry`, `stay_permit_no`, `phone`, `email`, `existing_stay_permit`, `guarantor`, `purpose_of_application`, `stay_permit_to_be_applied_for` (**E33G**, не «Bridge»), `place`, `doc_date`.

## 4. Развилка исполнителей (критично!)

| | **Ngurah Rai** (аэропорт) | **Denpasar** |
|---|---|---|
| Подписант (Surat Kuasa) | Bartosz Pawel Nafalski, **Direktur** | Arine Fadillah, **Komisaris** |
| Гражданство | Polandia | WNI (NIK 1271114606750008) |
| Адресат | Bapak Kepala Kantor Imigrasi Kelas I **Khusus TPI Ngurah Rai**, Jalan Perumahan Taman Jimbaran No. 1 Mumbul, Kabupaten Badung, Bali | Bapak Kepala Kantor Imigrasi Kelas I TPI Denpasar, Jl. D.I. Panjaitan No.3, Sumerta Kelod, Kec. Denpasar Tim., Kota Denpasar, Bali |

Выбор варианта в системе: селект у документа `bridging_letter` / `conversion_letter` в карточке заявки (или в конструкторе — подгруппы «Bridging / Conversion — Ngurah Rai (Бартош)» и «— Denpasar (Арине)»).

## 5. Формула перехода (`letter_subject`)

- Мостовая: `Permohonan Bridging Visa 60 Hari`
- Конверсия в E33G: `Konversi Bridging Visa menjadi KITAS E33G Remote Worker`
- Переход на D12: `Konversi Bridging Visa menjadi Visa D12`
- D12: `Permohonan Visa D12`
- C1: `Permohonan Visa C1`

Первая строка письма меняется вместе с парой «с какой визы на какую» — при смене типа визы менять и тему, и первую строку.

## 6. Закономерности и подводные камни

1. **Номер письма:** `NN/PTAPB-SP/ДД.ММ.ГГГГ`, где NN — сквозной исходящий номер (ставит исполнитель), а дата в номере = дата письма. В архиве: bridging 45/…/16.09.2026, 34/…/24.08.2026; конверсия 39/…/24.08.2026, 37/… .
2. **Дата подписания:** `Badung, <день> <месяц по-индонезийски> <год>` — Agustus, September, Oktober…
3. **METERAI 10.000** — марка на Form E-02, постоянный элемент.
4. **Только английский / Bahasa Indonesia** — русского текста в документах быть не может.
5. **Данные клиента подставляются на 2-й лист** (в D12 и части визовых) — проверять оба листа.
6. **Текущий ITK (`application_no`)** — вида `B12E21E1063044-C`, берётся строго из документа иммиграции клиента, не придумывается.
7. **Для конверсии нужен запас ≥31 дня** по действующему разрешению (иначе подача невозможна) — см. `product_documents_audit.md`.

## 7. Где используется

- **BRIDGING**: комплект (Ngurah Rai или Denpasar) + CV + Form E-02 (bridging) + Work Agreement
- **CONV**: комплект (Ngurah Rai или Denpasar) + CV + Form E-02 (conversion) + Work Agreement

(Состав проверен по БД `product_documents`: слоты `bridging_letter` / `conversion_letter`, `cv`, `statement_e02_*`, `work_agreement`.)

## 8. Разобранные примеры из архива

1. **IVAN CLIENT** — bridging, Ngurah Rai, №45/PTAPB-SP/16.09.2026, место/дата рождения `RUSSIA / 08-01-1999`, паспорт 770139869, конверсия в KITAS E33G Remote Worker.
2. **HANNA SUSHKO** (Беларусь) — bridging, Denpasar, №34/PTAPB-SP/24.08.2026.
3. **ARTUR BALABAEV** — конверсия, Ngurah Rai, №39/PTAPB-SP/24.08.2026; **ELDAR SATTAROV** — конверсия, Denpasar, №37/PTAPB-SP/24.08.2026 (ITK `B12B17EB077957-C`, срок до 30-10-2026).

## 9. Открытые вопросы

1. **Адрес офиса Denpasar:** в инструкции заказчика — `Jl. Raya Puputan No. 1, Renon, Denpasar Sel.`, во всех архивах и в шаблонах — `Jl. D.I. Panjaitan No.3, Sumerta Kelod, Kec. Denpasar Tim.`. В систему поставлен архивный вариант — ждём подтверждения заказчика.
2. Кто подписывает Permohonan/Jaminan: фактически **Marcellena** (представитель), а не Bartosz/Arine — уточнить, всегда ли так.
3. В архиве есть расхождения в написании клиентского адреса на Бали (два разных адреса в разных документах одного клиента) — уточнить, какой брать.
