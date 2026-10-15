# Переменные документов Wolf AutoDoc

Собрано автоматически из системы (/opt/wolf_v2/data/wolf.db): описание, источник, место расчёта в коде.


## bank_statement_12m__sber — Банковская справка 12 мес. (Сбер)

Продукты: E33G-NEW
Переменных: 13; в HTML шаблона: 10

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `doc_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | No ha39545436 |
| `card_mask` | Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реа | client | services/values.py:1127, services/autofill.py:81 | «SberBank», universal license of Bank of Russia No 9441, her |
| `ref_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | X49348049TLC 04.10.2026 |
| `address_live` | Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — | client | services/values.py:222, services/render.py:53 | Apartment 58, 24 Brateyevskaya Street, Moscow, |
| `balance_words` | Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берут | client | services/values.py:1688, services/autofill.py:68 | As from 04.10.2025 to 04.10.2026 the deposit balance is 6661 |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | CLIENT_059 |
| `period_from` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1137, services/render.py:549 | As from 04.10.2025 to 04.10.2026 the deposit balance is 6661 |
| `period_to` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1139, services/render.py:548 | X49348049TLC 04.10.2026 |
| `doc_date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:976, services/autofill.py:82 | X49348049TLC 04.10.2026 |
| `contract_date` | Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, су | client | services/values.py:1460 | 01.01.2020 |
| `contract_no` | Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, с | client | services/values.py:1124, services/autofill.py:81 | 1234567890 |
| `account_no` | Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:1123, services/autofill.py:81 | 40817810099910004312 |
| `balance_rub` | Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутс | client | services/values.py:442, services/autofill.py:56 | As from 04.10.2025 to 04.10.2026 the deposit balance is 6661 |

Пробелы: без описания/нет в HTML — 3 (contract_date, contract_no, account_no)
Есть в HTML, нет в БД: —

## bank_statement_12m__tbank — Банковская справка 12 мес. (Т-Банк)

Продукты: E33G-NEW
Переменных: 13; в HTML шаблона: 10

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `doc_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | No ae32271197 |
| `card_mask` | Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реа | client | services/values.py:1127, services/autofill.py:81 | «TBank», universal license of Bank of Russia No 9441, hereby |
| `ref_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | B19289961ADL 02.10.2026 |
| `address_live` | Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — | client | services/values.py:222, services/render.py:53 | г. Москва, ул. Тверская, д. 1, кв. 23 |
| `balance_words` | Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берут | client | services/values.py:1688, services/autofill.py:68 | As from 02.10.2025 to 02.10.2026 the deposit balance is 7 12 |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | POLYAKOV EVGENIY ANDREEVICH |
| `period_from` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1137, services/render.py:549 | As from 02.10.2025 to 02.10.2026 the deposit balance is 7 12 |
| `period_to` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1139, services/render.py:548 | B19289961ADL 02.10.2026 |
| `contract_no` | Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, с | client | services/values.py:1124, services/autofill.py:81 | 5357583565 |
| `account_no` | Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:1123, services/autofill.py:81 | 40817810300031938570 |
| `balance_rub` | Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутс | client | services/values.py:442, services/autofill.py:56 | As from 02.10.2025 to 02.10.2026 the deposit balance is 7 12 |
| `doc_date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:976, services/autofill.py:82 | B19289961ADL 02.10.2026 |
| `contract_date` | Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, су | client | services/values.py:1460 | 21.03.2021 |

Пробелы: без описания/нет в HTML — 3 (contract_no, account_no, contract_date)
Есть в HTML, нет в БД: —

## bank_statement_3m__sber — Банковская справка 3 мес. (Сбер)

Продукты: C1, C1-EXT, D12, E33G-EXT, E33G-NEW
Переменных: 13; в HTML шаблона: 10

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `doc_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | 5569979o 22.08.2026 |
| `card_mask` | Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реа | client | services/values.py:1127, services/autofill.py:81 | «SberBank», universal license of Bank of Russia No 9441, her |
| `ref_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | 5569979o 22.08.2026 |
| `address_live` | Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — | client | services/values.py:222, services/render.py:53 | 185039, Respublika Kareliya, G Petrozavodsk, Ul Gogolya , D. |
| `balance_words` | Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берут | client | services/values.py:1688, services/autofill.py:68 |  |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | ZHIDKO CLIENT |
| `period_from` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1137, services/render.py:549 | As from 26.08.2025 to 26.08.2026 the deposit balance is 2 75 |
| `period_to` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1139, services/render.py:548 | 5569979o 22.08.2026 |
| `doc_date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:976, services/autofill.py:82 | 5569979o 22.08.2026 |
| `balance_rub` | Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутс | client | services/values.py:442, services/autofill.py:56 | As from 26.08.2025 to 26.08.2026 the deposit balance is 2 75 |
| `account_no` | Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:1123, services/autofill.py:81 | 40817810099910004312 |
| `contract_date` | Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, су | client | services/values.py:1460 | 01.01.2020 |
| `contract_no` | Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, с | client | services/values.py:1124, services/autofill.py:81 | 1234567890 |

Пробелы: без описания/нет в HTML — 3 (account_no, contract_date, contract_no)
Есть в HTML, нет в БД: —

## bank_statement_3m__tbank — Банковская справка 3 мес. (Т-Банк)

Продукты: C1, C1-EXT, D12, E33G-EXT, E33G-NEW
Переменных: 10; в HTML шаблона: 10

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `doc_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | No ae32271197 |
| `card_mask` | Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реа | client | services/values.py:1127, services/autofill.py:81 | «TBank», universal license of Bank of Russia No 9441, hereby |
| `ref_no` | Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок,  | client | services/values.py:529, services/autofill.py:81 | B19289961ADL 26.08.2026 |
| `address_live` | Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — | client | services/values.py:222, services/render.py:53 | 115191, Moscow, Ul Bol'shaya Tul'skaya, D. 2, Kv. 846 |
| `balance_words` | Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берут | client | services/values.py:1688, services/autofill.py:68 | As from 26.05.2026 to 26.08.2026 the deposit balance is 672  |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | CLIENT ANNA SERGEEVNA |
| `period_from` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1137, services/render.py:549 | As from 26.05.2026 to 26.08.2026 the deposit balance is 672  |
| `period_to` | Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1139, services/render.py:548 | B19289961ADL 26.08.2026 |
| `balance_rub` | Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутс | client | services/values.py:442, services/autofill.py:56 | As from 26.05.2026 to 26.08.2026 the deposit balance is 672  |
| `doc_date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:976, services/autofill.py:82 | B19289961ADL 26.08.2026 |

Пробелы: без описания/нет в HTML — 0 (—)
Есть в HTML, нет в БД: —

## bridging_request_letter__denpasar — Bridging: комплект документов (Denpasar, Арине)

Продукты: BRIDGING
Переменных: 38; в HTML шаблона: 21

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `addressee_office` | — нет описания — | client | services/values.py:944 |  |
| `attorney_address` | — нет описания — | client | services/values.py:738 |  |
| `attorney_name` | — нет описания — | client | services/values.py:219 |  |
| `attorney_nik` | — нет описания — | client | services/values.py:939 |  |
| `body_request_line` | — нет описания — | client |  |  |
| `client_address` | — нет описания — | client | services/values.py:223 |  |
| `client_dob` | — нет описания — | client | services/values.py:1917 |  |
| `date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client |  | 24 Agustus 2026 |
| `itk_expiry` | — нет описания — | client | services/values.py:1349 |  |
| `itk_no` | — нет описания — | client | services/values.py:1349 |  |
| `letter_place_date` | — нет описания — | client |  |  |
| `passport_expiry` | — нет описания — | client | services/values.py:1102 |  |
| `signatory_address` | — нет описания — | client | services/values.py:737 |  |
| `signatory_name` | — нет описания — | client | services/values.py:2083 |  |
| `sponsor_person_name` | — нет описания — | client | services/values.py:940 |  |
| `surname` | — нет описания — | client | services/values.py:68, services/render.py:52 |  |
| `date_iso` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1955 | 2026-08-24 |
| `date_iso_2` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1956 | 21-12-2032 |
| `date_iso_3` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1957 | 12-10-2026 |
| `letter_no` | Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата | — | services/values.py:966 | 64/PTAPB-SP/03.10.2026 |
| `letter_subject` | Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбира | — | services/values.py:945 | Permohonan Bridging Visa 60 Hari |
| `addressee_line1` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Jl. D.I. Panjaitan No.3, Sumerta Kelod, Kec. Denpasar Tim., |
| `addressee_line2` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Kota Denpasar, Bali |
| `addressee_line3` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:739 | Kota Denpasar, Bali |
| `client_gender` | Что это: Пол клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | — | services/values.py:1887 | LAKI-LAKI |
| `client_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1889 | RUSIA |
| `address_in_indonesia` | — нет описания — | client | services/values.py:737 | JL. DESA CEPAKA, CEPAKA, KEC. KEDIRI, KABUPATEN TABANAN 8035 |
| `place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:219, services/render.py:58 | BELARUS |
| `address_live` | Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — | client | services/values.py:222, services/render.py:53 | 8611, Kareliya, Petrozavodsk, Botanicheskaya |
| `application_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:975 | 2A222E21EG005288-C |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | IVAN SMIRNOV |
| `passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1099, services/render.py:54 | 769773904 |
| `place_date` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:976 | Badung, 3 Oktober 2026 |
| `sponsor_name` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:218 | PT ALPHA PRIME BALI |
| `place_birth_inline` | Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента | client | services/values.py:1980 | RUSSIA / 30-09-1995 |
| `signatory_position` | Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, ко | sponsor | services/values.py:942 |  |
| `signatory_citizenship` | Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса,  | sponsor | services/values.py:942 |  |
| `signatory_nik_or_dash` | Что это: NIK подписанта (или прочерк) Тип: logic — логика оформления — люди, компании и ад | sponsor | services/values.py:943 |  |

Пробелы: без описания/нет в HTML — 28 (addressee_office, attorney_address, attorney_name, attorney_nik, body_request_line, client_address, client_dob, date, itk_expiry, itk_no, letter_place_date, passport_expiry)
Есть в HTML, нет в БД: —

## bridging_request_letter__ngurahrai — Bridging: комплект документов (Ngurah Rai, Бартош)

Продукты: BRIDGING
Переменных: 36; в HTML шаблона: 21

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `attorney_address` | — нет описания — | client | services/values.py:738 |  |
| `attorney_nik` | — нет описания — | client | services/values.py:939 |  |
| `body_request_line` | — нет описания — | client |  |  |
| `client_address` | — нет описания — | client | services/values.py:223 |  |
| `client_dob` | — нет описания — | client | services/values.py:1917 |  |
| `date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client |  | 16 September 2026 |
| `itk_expiry` | — нет описания — | client | services/values.py:1349 |  |
| `itk_no` | — нет описания — | client | services/values.py:1349 |  |
| `letter_place_date` | — нет описания — | client |  |  |
| `passport_expiry` | — нет описания — | client | services/values.py:1102 |  |
| `signatory_name` | — нет описания — | client | services/values.py:2083 |  |
| `date_iso` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1955 | 2026-09-16 |
| `date_iso_2` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1956 | 2026-09-16 |
| `date_iso_3` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1957 | 2026-09-16 |
| `letter_no` | Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата | — | services/values.py:966 | 45/PTAPB-SP/16.09.2026 |
| `letter_subject` | Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбира | — | services/values.py:945 | Permohonan Bridging Visa 60 Hari |
| `addressee_line1` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Bapak Kepala Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai |
| `addressee_line2` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Jalan Perumahan Taman Jimbaran No. 1 Mumbul |
| `addressee_line3` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:739 | Kabupaten Badung, Bali |
| `attorney_name` | Что это: Доверенное лицо (имя) Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:219 | Marcellena Nirmala Chrisna Moeri |
| `client_gender` | Что это: Пол клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | — | services/values.py:1887 | Laki-laki |
| `client_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1889 | RUSIA |
| `addressee_office` | — нет описания — | client | services/values.py:944 |  |
| `place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:219, services/render.py:58 | RUSSIA |
| `passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1099, services/render.py:54 | 770139869 |
| `signatory_address` | Что это: Адрес подписанта Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:737 | Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya |
| `signatory_citizenship` | Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса,  | client | services/values.py:942 | Indonesia |
| `sponsor_person_name` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:940 | Marcellena Nirmala Chrisna Moeri |
| `application_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:975 | B12E21E1093972-C |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | Perempuan |
| `place_date` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:976 | Badung, 16 September 2026 |
| `sponsor_name` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:218 | PT ALPHA PRIME BALI |
| `surname` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:68, services/render.py:52 | Perempuan |
| `place_birth_inline` | Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента | client | services/values.py:1980 |  |
| `signatory_position` | Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, ко | sponsor | services/values.py:942 |  |
| `signatory_nik_or_dash` | Что это: NIK подписанта (или прочерк) Тип: logic — логика оформления — люди, компании и ад | sponsor | services/values.py:943 |  |

Пробелы: без описания/нет в HTML — 25 (attorney_address, attorney_nik, body_request_line, client_address, client_dob, date, itk_expiry, itk_no, letter_place_date, passport_expiry, signatory_name, date_iso)
Есть в HTML, нет в БД: —

## bridging_request_letter__tabanan — Bridging: комплект документов (Tabanan)

Продукты: BRIDGING
Переменных: 36; в HTML шаблона: 21

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `application_no` | — нет описания — | client | services/values.py:975 |  |
| `attorney_address` | — нет описания — | client | services/values.py:738 |  |
| `attorney_name` | — нет описания — | client | services/values.py:219 |  |
| `attorney_nik` | — нет описания — | client | services/values.py:939 |  |
| `body_request_line` | — нет описания — | client |  |  |
| `client_address` | — нет описания — | client | services/values.py:223 |  |
| `client_dob` | — нет описания — | client | services/values.py:1917 |  |
| `client_gender` | — нет описания — | client | services/values.py:1887 |  |
| `client_name` | — нет описания — | client | services/values.py:217, services/render.py:50 |  |
| `client_nationality` | — нет описания — | client | services/values.py:1889 |  |
| `date` | — нет описания — | client |  |  |
| `date_iso` | — нет описания — | client | services/values.py:1955 |  |
| `date_iso_2` | — нет описания — | client | services/values.py:1956 |  |
| `date_iso_3` | — нет описания — | client | services/values.py:1957 |  |
| `itk_expiry` | — нет описания — | client | services/values.py:1349 |  |
| `itk_no` | — нет описания — | client | services/values.py:1349 |  |
| `letter_no` | — нет описания — | client | services/values.py:966 |  |
| `letter_place_date` | — нет описания — | client |  |  |
| `letter_subject` | — нет описания — | client | services/values.py:945 |  |
| `passport_expiry` | — нет описания — | client | services/values.py:1102 |  |
| `passport_no` | — нет описания — | client | services/values.py:1099, services/render.py:54 |  |
| `place_birth_inline` | — нет описания — | client | services/values.py:1980 |  |
| `place_date` | — нет описания — | client | services/values.py:976 |  |
| `place_of_birth` | — нет описания — | client | services/values.py:219, services/render.py:58 |  |
| `signatory_address` | — нет описания — | client | services/values.py:737 |  |
| `signatory_citizenship` | — нет описания — | client | services/values.py:942 |  |
| `signatory_name` | — нет описания — | client | services/values.py:2083 |  |
| `signatory_nik_or_dash` | — нет описания — | client | services/values.py:943 |  |
| `signatory_position` | — нет описания — | client | services/values.py:942 |  |
| `sponsor_name` | — нет описания — | client | services/values.py:218 |  |
| `sponsor_person_name` | — нет описания — | client | services/values.py:940 |  |
| `surname` | — нет описания — | client | services/values.py:68, services/render.py:52 |  |
| `addressee_line1` | — нет описания — | client | services/values.py:738 |  |
| `addressee_line2` | — нет описания — | client | services/values.py:738 |  |
| `addressee_line3` | — нет описания — | client | services/values.py:739 |  |
| `addressee_office` | — нет описания — | client | services/values.py:944 |  |

Пробелы: без описания/нет в HTML — 36 (application_no, attorney_address, attorney_name, attorney_nik, body_request_line, client_address, client_dob, client_gender, client_name, client_nationality, date, date_iso)
Есть в HTML, нет в БД: —

## conversion_request_letter__denpasar — Conversion: комплект документов (Denpasar, Арине)

Продукты: CONV
Переменных: 41; в HTML шаблона: 21

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `addressee_office` | — нет описания — | client | services/values.py:944 |  |
| `body_request_line` | — нет описания — | client |  |  |
| `client_address` | — нет описания — | client | services/values.py:223 |  |
| `client_dob` | — нет описания — | client | services/values.py:1917 |  |
| `date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client |  | 24 Agustus 2026 |
| `itk_expiry` | — нет описания — | client | services/values.py:1349 |  |
| `itk_no` | — нет описания — | client | services/values.py:1349 |  |
| `letter_place_date` | — нет описания — | client |  |  |
| `passport_expiry` | — нет описания — | client | services/values.py:1102 |  |
| `place_of_birth` | — нет описания — | client | services/values.py:219, services/render.py:58 |  |
| `signatory_address` | — нет описания — | client | services/values.py:737 |  |
| `signatory_name` | — нет описания — | client | services/values.py:2083 |  |
| `sponsor_person_name` | — нет описания — | client | services/values.py:940 |  |
| `surname` | — нет описания — | client | services/values.py:68, services/render.py:52 |  |
| `date_iso` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1955 | 2026-08-24 |
| `date_iso_2` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1956 | 2026-08-24 |
| `date_iso_3` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1957 | 2026-08-24 |
| `letter_no` | Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата | — | services/values.py:966 | Lampiran: satu berkas |
| `letter_subject` | Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбира | — | services/values.py:945 | Konversi Bridging Visa menjadi KITAS E33G Remote Worker |
| `addressee_line1` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Jl. D.I. Panjaitan No.3, Sumerta Kelod, Kec. Denpasar Tim., |
| `addressee_line2` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Kota Denpasar, Bali |
| `addressee_line3` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:739 | Kota Denpasar, Bali |
| `sponsor_address` | Что это: Адрес спонсора Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:737 | Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten G |
| `sponsor_contact` | Что это: Контакты спонсора Тип: logic — логика оформления — люди, компании и адреса, котор | — | services/values.py:940 | Telp: +62 811 397 9669, Email: ptalphaprimeconsulting@gmail. |
| `attorney_occupation` | Что это: Занятие доверенного лица Тип: logic — логика оформления — люди, компании и адреса | — | services/values.py:939 | Indonesia |
| `attorney_citizenship` | Что это: Гражданство доверенного лица Тип: logic — логика оформления — люди, компании и ад | — | services/values.py:939 | 5171015403930001 |
| `attorney_nik` | Что это: NIK доверенного лица Тип: logic — логика оформления — люди, компании и адреса, ко | — | services/values.py:939 | Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya |
| `attorney_address` | Что это: Адрес доверенного лица Тип: logic — логика оформления — люди, компании и адреса,  | — | services/values.py:738 | Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya |
| `client_gender` | Что это: Пол клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | — | services/values.py:1887 | Laki-laki |
| `client_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1889 | RUSIA |
| `passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1099, services/render.py:54 | 769762908 |
| `application_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:975 | B12B17EB077957-C |
| `attorney_name` | Что это: Доверенное лицо (имя) Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:219 | Komisaris PT Alpha Prime Bali |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | ELDAR SATTAROV |
| `place_date` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:976 | Badung, 24 Agustus 2026 |
| `sponsor_company` | Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:940 | PT ALPHA PRIME BALI |
| `sponsor_name` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:218 | PT ALPHA PRIME BALI |
| `place_birth_inline` | Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента | client | services/values.py:1980 |  |
| `signatory_position` | Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, ко | sponsor | services/values.py:942 |  |
| `signatory_citizenship` | Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса,  | sponsor | services/values.py:942 |  |
| `signatory_nik_or_dash` | Что это: NIK подписанта (или прочерк) Тип: logic — логика оформления — люди, компании и ад | sponsor | services/values.py:943 |  |

Пробелы: без описания/нет в HTML — 29 (addressee_office, body_request_line, client_address, client_dob, date, itk_expiry, itk_no, letter_place_date, passport_expiry, place_of_birth, signatory_address, signatory_name)
Есть в HTML, нет в БД: —

## conversion_request_letter__ngurahrai — Conversion: комплект документов (Ngurah Rai, Бартош)

Продукты: CONV
Переменных: 44; в HTML шаблона: 21

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `addressee_office` | — нет описания — | client | services/values.py:944 |  |
| `body_request_line` | — нет описания — | client |  |  |
| `client_address` | — нет описания — | client | services/values.py:223 |  |
| `client_dob` | — нет описания — | client | services/values.py:1917 |  |
| `date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client |  | Badung, 3 Oktober 2026 |
| `itk_expiry` | — нет описания — | client | services/values.py:1349 |  |
| `itk_no` | — нет описания — | client | services/values.py:1349 |  |
| `letter_place_date` | — нет описания — | client |  |  |
| `passport_expiry` | — нет описания — | client | services/values.py:1102 |  |
| `place_of_birth` | — нет описания — | client | services/values.py:219, services/render.py:58 |  |
| `signatory_address` | — нет описания — | client | services/values.py:737 |  |
| `signatory_name` | — нет описания — | client | services/values.py:2083 |  |
| `sponsor_person_name` | — нет описания — | client | services/values.py:940 |  |
| `surname` | — нет описания — | client | services/values.py:68, services/render.py:52 |  |
| `letter_no` | Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата | — | services/values.py:966 | Nomor: 21/PTAPB-SP/03.10.2026 |
| `letter_subject` | Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбира | — | services/values.py:945 | Hal: Konversi Bridging Visa menjadi KITAS E33G Remote Worker |
| `addressee_line1` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Bapak Kepala Kantor Imigrasi Kelas I Khusus TPI |
| `addressee_line2` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:738 | Jalan Perumahan Taman Jimbaran |
| `addressee_line3` | Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:739 | Mumbul, Kabupaten Badung, |
| `sponsor_address` | Что это: Адрес спонсора Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:737 | Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten G |
| `sponsor_contact` | Что это: Контакты спонсора Тип: logic — логика оформления — люди, компании и адреса, котор | — | services/values.py:940 | Telp: +62 811 397 9669, Email: ptalphaprimeconsulting@gmail. |
| `attorney_name` | Что это: Доверенное лицо (имя) Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:219 | Bartosz Pawel Nafalski |
| `attorney_occupation` | Что это: Занятие доверенного лица Тип: logic — логика оформления — люди, компании и адреса | — | services/values.py:939 | Swasta |
| `bridging_visa_no` | Что это: Номер мостовой визы Тип: client_fact — фактические данные клиента — берутся из ре | client |  | 2A222B17E1093925-C |
| `attorney_citizenship` | Что это: Гражданство доверенного лица Тип: logic — логика оформления — люди, компании и ад | — | services/values.py:939 | Indonesia |
| `attorney_nik` | Что это: NIK доверенного лица Тип: logic — логика оформления — люди, компании и адреса, ко | — | services/values.py:939 | 5171015403930001 |
| `attorney_address` | Что это: Адрес доверенного лица Тип: logic — логика оформления — люди, компании и адреса,  | — | services/values.py:738 | Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya |
| `client_gender` | Что это: Пол клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | — | services/values.py:1887 | Laki-laki |
| `client_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1889 | RUSIA |
| `passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1099, services/render.py:54 | 000000000 |
| `place_date_of_birth` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:2035 | RUSSIA , 29-07-2002 |
| `sponsor_company_details` | Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:941 |  |
| `application_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:975 | 2A222B17E1093925-C |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | POLINA MIKHEEVA |
| `date_iso` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1955 | 2026-08-24 |
| `date_iso_2` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1956 | 2026-08-24 |
| `date_iso_3` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:1957 | 2026-08-24 |
| `place_date` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:976 | Badung, 3 Oktober 2026 |
| `sponsor_company` | Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:940 | PT ALPHA PRIME BALI |
| `sponsor_name` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:218 | PT ALPHA PRIME BALI |
| `place_birth_inline` | Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента | client | services/values.py:1980 |  |
| `signatory_position` | Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, ко | sponsor | services/values.py:942 |  |
| `signatory_citizenship` | Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса,  | sponsor | services/values.py:942 |  |
| `signatory_nik_or_dash` | Что это: NIK подписанта (или прочерк) Тип: logic — логика оформления — люди, компании и ад | sponsor | services/values.py:943 |  |

Пробелы: без описания/нет в HTML — 32 (addressee_office, body_request_line, client_address, client_dob, date, itk_expiry, itk_no, letter_place_date, passport_expiry, place_of_birth, signatory_address, signatory_name)
Есть в HTML, нет в БД: —

## cv__format_detailed — Резюме (CV) — расширенный формат

Продукты: —
Переменных: 26; в HTML шаблона: 25

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `cv_profession` | Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который сист | заявка / вручную | services/values.py:979, services/cv_gen.py:869 |  |
| `full_name_latin` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:66, services/cv_gen.py:808 | Name: Viktoriia Korchagina |
| `cv_date_of_birth` | Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1538 | Date of Birth: November 3, 1990 |
| `cv_place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1540 | Place of Birth: Yakutsk, Yakutskaya ASSR, USSR |
| `cv_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1530 | Russian Federation |
| `cv_passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1535 | 77 9937194 |
| `cv_passport_issue` | Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1542 | August 14, 2026 |
| `cv_passport_expiry` | Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1544 | August 14, 2036 |
| `cv_summary` | Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который сист | llm | services/values.py:979, services/cv_gen.py:729 |  |
| `cv_job1_title` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job1_period` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 | March 2018 – Present |
| `cv_job1_company` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job1_bullets` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job2_title` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_job2_period` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 | June 2013 – February 2018 |
| `cv_job2_company` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_job2_bullets` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_education_degree` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:1370, services/cv_gen.py:903 |  |
| `cv_education_school` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:1369, services/cv_gen.py:872 |  |
| `cv_education_years` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:1370, services/cv_gen.py:875 |  |
| `cv_education_note` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:1370, services/cv_gen.py:904 |  |
| `cv_skills_hard` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | llm | services/values.py:980, services/cv_gen.py:867 |  |
| `cv_skills_soft` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | llm | services/values.py:980, services/cv_gen.py:960 |  |
| `cv_skills_tools` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | llm | services/values.py:1371, services/cv_gen.py:961 |  |
| `cv_languages` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | llm | services/values.py:1371, services/cv_gen.py:959 |  |
| `client_photo_url` | Что это: Фото клиента Тип: client_fact — фактические данные клиента — берутся из реальных  | client | services/values.py:1093 |  |

Пробелы: без описания/нет в HTML — 1 (cv_profession)
Есть в HTML, нет в БД: —

## cv__format_short — Резюме (CV) — короткий формат

Продукты: —
Переменных: 21; в HTML шаблона: 19

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `cv_profession` | Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который сист | заявка / вручную | services/values.py:979, services/cv_gen.py:869 | Personal Assistant |
| `cv_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:267, services/render.py:246 | Artur Balabaev |
| `cv_date_of_birth` | Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1538 | 29 July 2002 |
| `cv_place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1540 | Khabarovsk Krai, Russia |
| `cv_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1530 | Russian Federation |
| `cv_passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1535 | 77 2829709 |
| `cv_passport_issue` | Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1542 | 15 March 2024 |
| `cv_passport_expiry` | Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1544 | 15 March 2034 |
| `cv_summary` | Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который сист | llm | services/values.py:979, services/cv_gen.py:729 |  |
| `cv_job1_title` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job1_period` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 | Jun 2025 – Present |
| `cv_job1_company` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job1_bullets` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_education_degree` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | документы клиента | services/values.py:1370, services/cv_gen.py:903 |  |
| `cv_education_school` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | документы клиента | services/values.py:1369, services/cv_gen.py:872 |  |
| `cv_languages` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | документы клиента | services/values.py:1371, services/cv_gen.py:959 |  |
| `full_name_latin` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:66, services/cv_gen.py:808 | Artur Balabaev |
| `cv_job2_title` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_job2_period` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:982, services/cv_gen.py:895 | Sep 2023 – Aug 2025 |
| `cv_job2_company` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_job2_bullets` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:982, services/cv_gen.py:895 |  |

Пробелы: без описания/нет в HTML — 2 (cv_summary, full_name_latin)
Есть в HTML, нет в БД: —

## cv__format_CLIENT — Резюме (CV) — формат Сиваева

Продукты: BRIDGING, CONV, D12, E33G-EXT, E33G-NEW
Переменных: 20; в HTML шаблона: 20

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `cv_profession` | Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который сист | заявка / вручную | services/values.py:979, services/cv_gen.py:869 | Executive Director |
| `cv_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:267, services/render.py:246 | IVAN CLIENT |
| `cv_date_of_birth` | Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1538 | Date of Birth: 08.01.1999 | Nationality: Russian Federation  |
| `cv_place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1540 | Moscow, Russia |
| `cv_nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1530 | Date of Birth: 08.01.1999 | Nationality: Russian Federation  |
| `cv_passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1535 | Date of Birth: 08.01.1999 | Nationality: Russian Federation  |
| `cv_summary` | Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который сист | llm | services/values.py:979, services/cv_gen.py:729 |  |
| `cv_job1_title` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job1_period` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 | September 2025 – Present |
| `cv_job1_company` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job1_bullets` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:981, services/cv_gen.py:894 |  |
| `cv_job2_period` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_job2_company` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_job2_bullets` | Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из ре | llm | services/values.py:982, services/cv_gen.py:895 |  |
| `cv_languages` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | документы клиента | services/values.py:1371, services/cv_gen.py:959 |  |
| `full_name_latin` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:66, services/cv_gen.py:808 | IVAN CLIENT |
| `cv_skills_hard` | Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подб | client | services/values.py:980, services/cv_gen.py:867 |  |
| `cv_education_degree` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1370, services/cv_gen.py:903 |  |
| `cv_education_school` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1369, services/cv_gen.py:872 |  |
| `cv_education_years` | Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1370, services/cv_gen.py:875 |  |

Пробелы: без описания/нет в HTML — 2 (cv_profession, full_name_latin)
Есть в HTML, нет в БД: cv_job2_title, cv_skills_soft

## d12_cover_letter__default — D12: Permohonan Visa (ходатайство)

Продукты: D12
Переменных: 32; в HTML шаблона: 24

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `letter_no` | Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата | — | services/values.py:966 | 38/PTAPB-SP/24.08.2026 |
| `letter_subject` | Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбира | — | services/values.py:945 | Permohonan Bridging Visa 60 Hari |
| `signatory_position` | Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, ко | sponsor | services/values.py:942 | Direktur ALPHA PRIME BALI |
| `signatory_citizenship` | Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса,  | client | services/values.py:942 | Indonesia |
| `signatory_address` | Что это: Адрес подписанта Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:737 | Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten G |
| `sponsor_address` | Что это: Адрес спонсора Тип: logic — логика оформления — люди, компании и адреса, которые  | — | services/values.py:737 | Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten G |
| `sponsor_contact` | Что это: Контакты спонсора Тип: logic — логика оформления — люди, компании и адреса, котор | — | services/values.py:940 | Telp: +62 811 397 9669, Email: ptalphaprimeconsulting@gmail. |
| `sponsor_person_name` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:940 | Marcellena Nirmala Chrisna Moeri |
| `sponsor_birth_place_date` | Что это: Место и дата рождения руководителя спонсора Тип: logic — логика оформления — люди | — | services/values.py:941 | Poland, 20-03-1973 |
| `sponsor_nationality` | Что это: Гражданство спонсора Тип: logic — логика оформления — люди, компании и адреса, ко | — | services/values.py:941 | Poland |
| `sponsor_position` | Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, к | client | services/values.py:941 | Direktur |
| `passport_no` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1099, services/render.py:54 | 763655709 |
| `place_date_of_birth` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:2035 |  |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 | CLIENT_048 |
| `place_date` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:976 | Badung, 24 Agustus 2026 |
| `sponsor_company` | Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:940 | PT ALPHA PRIME BALI |
| `job_and_position` | Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — бер | client | services/values.py:2085 | Direktur |
| `signatory_name` | Что это: Имя подписанта от агентства Тип: logic — логика оформления — люди, компании и адр | client | services/values.py:2083 | Marcellena Nirmala Chrisna Moeri |
| `signatory_name_2` | Что это: Имя подписанта от агентства Тип: logic — логика оформления — люди, компании и адр | client |  | Marcellena Nirmala Chrisna Moeri |
| `client_citizenship` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:2037 | RUSIA |
| `passport_expiry` | Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1102 | 23-11-2030 |
| `address_in_indonesia` | Что это: Адрес клиента в Индонезии Тип: client_fact — фактические данные клиента — берутся | client | services/values.py:737 | Jl. Sempol, Pererenan, Kec. Mengwi, Kabupaten Badung, Bali 8 |
| `itk_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | manual | services/values.py:1349 | B12E21E1087150-C |
| `itk_expiry` | Что это: Срок разрешения на пребывание Тип: client_fact — фактические данные клиента — бер | manual | services/values.py:1349 | 15-09-2026 |
| `addressee_line1` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:738 | Bapak Kepala Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai |
| `addressee_line2` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:738 | Direktur Lalu Lintas Keimigrasian |
| `addressee_line3` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:739 | Kabupaten Badung, Bali |
| `attorney_occupation` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:939 | Swasta |
| `attorney_nik` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:939 | 5171015403930001 |
| `attorney_address` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:738 | Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya |
| `client_gender` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:1887 | 000000000 |
| `place_birth_inline` | Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подста | logic | services/values.py:1980 | RUSSIA / 01-02-1995 |

Пробелы: без описания/нет в HTML — 9 (signatory_position, signatory_address, sponsor_person_name, sponsor_birth_place_date, sponsor_nationality, sponsor_position, place_date_of_birth, job_and_position, signatory_name_2)
Есть в HTML, нет в БД: signatory_person_name

## remote_work_agreement__default — Remote Work Agreement (контракт)

Продукты: BRIDGING, CONV, E33G-EXT, E33G-NEW
Переменных: 29; в HTML шаблона: 22

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `passport_expiry` | Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1102 |  |
| `passport_issue_date` | Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1101, services/render.py:131 |  |
| `passport_issued_by` | Что это: Кем выдан паспорт Тип: client_fact — фактические данные клиента — берутся из реал | client | services/values.py:219 |  |
| `the_company_confirms_that` | Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, которы | client | services/values.py:948 | and shall not be considered an employee of any Indonesian en |
| `services_list` | Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, которы | client | services/values.py:1051 | ● Strategic evolution of user experience, interface design,  |
| `agreement_date` | Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, су | client | services/values.py:1351 | 10 August 2026 |
| `company_name_in_quotes` | Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1115, services/employer_pool.py:196 | L-TECH |
| `date_of_birth` | Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1089, services/cv_gen.py:778 | 11.01.1989 |
| `full_name_latin` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:66, services/cv_gen.py:808 | CLIENT CLIENT |
| `inn_kpp_ogrn` | Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — | client | services/values.py:1314 | INN: 000000000, KPP: 501801001, OGRN: 1185029007140 |
| `nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1096, services/render.py:57 | Russian Federation |
| `passport_number` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1098, services/render.py:54 | 77 2374384 |
| `place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:219, services/render.py:58 | USSR |
| `employee_address` | Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — | client | services/values.py:222 |  |
| `contract_no` | Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, с | client | services/values.py:1124, services/autofill.py:81 | 5618252091 |
| `employer_name` | Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:218, services/employer_pool.py:195 | L-TECH LLC |
| `employee_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:218, services/render.py:250 | VASILEV CLIENT |
| `company_registered_address` | Что это: Адрес компании Тип: client_fact — фактические данные клиента — берутся из реальны | client | services/values.py:223, services/employer_pool.py:197 | 141073, Moscow Oblast, Korolev, ul. Leninskaya (Yubileyny mk |
| `company_inn` | Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — | client | services/values.py:1118, services/employer_pool.py:198 | 000000000 |
| `company_kpp` | Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — | client | services/values.py:1118, services/employer_pool.py:199 | 501801001 |
| `company_ogrn` | Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — | client | services/values.py:1119, services/employer_pool.py:200 | 1185029007140 |
| `position_title` | Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — бер | client | services/values.py:1213 | Product Designer |
| `term_start_date` | Что это: Начало срока (договор) Тип: doc_service — служебное поле документа — номер, дата, | client | services/values.py:1351 | 10 August 2025 |
| `term_end_date` | Что это: Окончание срока (договор) Тип: doc_service — служебное поле документа — номер, да | client | services/values.py:1352 | 10 August 2030 |
| `annual_amount_numeric` | Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, да | client | services/values.py:1270, services/salary_pool.py:101 | 5,100,000 |
| `annual_amount_words` | Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, да | client | services/values.py:1271, services/salary_pool.py:103 | Five Million One Hundred Thousand Russian Rubles |
| `monthly_amount_numeric` | Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, д | client | services/values.py:1272, services/salary_pool.py:102 | 425,000 |
| `monthly_amount_words` | Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, д | client | services/values.py:1273, services/salary_pool.py:104 | Four Hundred Twenty-Five Thousand Russian Rubles |
| `contractor_full_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:218 | VASILEV CLIENT |

Пробелы: без описания/нет в HTML — 12 (passport_expiry, passport_issue_date, passport_issued_by, the_company_confirms_that, full_name_latin, employee_address, contract_no, company_inn, company_kpp, company_ogrn, position_title, contractor_full_name)
Есть в HTML, нет в БД: company_incorporated_phrase, engagement_line, engagement_phrase, inn_ogrn_line, passport_valid_until

## statement_letter_e02__conversion — Statement Letter (Form E-02) — Conversion

Продукты: —
Переменных: 22; в HTML шаблона: 18

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `full_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:250 |  |
| `place_date_of_birth` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:2035 |  |
| `date_of_issue` | Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1967, services/render.py:132 | 12.05.2021 |
| `birth_date` | Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1088, services/cv_gen.py:778 |  |
| `existing_stay_permit` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:974 |  |
| `purpose_of_application` | Что это: Цель обращения Тип: descriptive — обзорное описание — текст, который система подб | client | services/values.py:947 |  |
| `stay_permit_to_be_applied_for` | Что это: Что запрашиваем по заявке Тип: logic — логика оформления — люди, компании и адрес | client | services/values.py:947 | Conversion of Bridging Visa to KITAS E33G |
| `address_in_indonesia` | Что это: Адрес клиента в Индонезии Тип: client_fact — фактические данные клиента — берутся | client | services/values.py:737 |  |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 |  |
| `date_of_expiry` | Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1968 |  |
| `doc_date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:976, services/autofill.py:82 |  |
| `nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1096, services/render.py:57 |  |
| `occupation` | Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — бер | client | services/values.py:2174 |  |
| `phone` | Что это: Телефон клиента в форме E-02. Правило (заказчик, 06.10.2026): по стандарту всегда | client | services/values.py:1107, services/render.py:60 | 00 |
| `place` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:948 |  |
| `place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:219, services/render.py:58 |  |
| `guarantor` | Что это: Гарант (поручитель) письма Тип: logic — логика оформления — люди, компании и адре | sponsor | services/values.py:947 | Bartosz Pawel Nafalski |
| `sponsor_company` | Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:940 |  |
| `stay_permit_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:976 |  |
| `email` | Что это: Контакты клиента — адрес электронной почты. Формула для ВСЕХ клиентов одна: фамил | client | services/values.py:1107, services/render.py:59 | BUDKO@ALPHA-PRIME.GROUP |
| `passport_number` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1098, services/render.py:54 |  |
| `place_birth_inline` | Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента | client | services/values.py:1980 |  |

Пробелы: без описания/нет в HTML — 4 (place_date_of_birth, birth_date, place_of_birth, sponsor_company)
Есть в HTML, нет в БД: —

## statement_letter_e02__default — Statement Letter (Form E-02) — Bridging

Продукты: BRIDGING, CONV
Переменных: 21; в HTML шаблона: 18

| переменная | описание | источник | где считается | пример |
|---|---|---|---|---|
| `full_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:250 |  |
| `place_date_of_birth` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:2035 |  |
| `date_of_issue` | Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из р | client | services/values.py:1967, services/render.py:132 | 23-11-2020 |
| `date_of_expiry` | Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1968 | 23-11-2030 |
| `birth_date` | Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из  | client | services/values.py:1088, services/cv_gen.py:778 |  |
| `existing_stay_permit` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:974 |  |
| `purpose_of_application` | Что это: Цель обращения Тип: descriptive — обзорное описание — текст, который система подб | client | services/values.py:947 |  |
| `stay_permit_to_be_applied_for` | Что это: Что запрашиваем по заявке Тип: logic — логика оформления — люди, компании и адрес | client | services/values.py:947 | Visa Bridging to E33G |
| `address_in_indonesia` | Что это: Адрес клиента в Индонезии Тип: client_fact — фактические данные клиента — берутся | client | services/values.py:737 |  |
| `client_name` | Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных д | client | services/values.py:217, services/render.py:50 |  |
| `doc_date` | Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер,  | client | services/values.py:976, services/autofill.py:82 |  |
| `email` | Что это: Контакты клиента — адрес электронной почты. Формула для ВСЕХ клиентов одна: фамил | client | services/values.py:1107, services/render.py:59 | BUDKO@ALPHA-PRIME.GROUP |
| `nationality` | Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из ре | client | services/values.py:1096, services/render.py:57 |  |
| `passport_number` | Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:1098, services/render.py:54 | 763655709 |
| `phone` | Что это: Телефон клиента в форме E-02. Правило (заказчик, 06.10.2026): по стандарту всегда | client | services/values.py:1107, services/render.py:60 | 00 |
| `place` | Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — | client | services/values.py:948 | Badung |
| `guarantor` | Что это: Гарант (поручитель) письма Тип: logic — логика оформления — люди, компании и адре | sponsor | services/values.py:947 | PT Alpha Prime Bali |
| `place_of_birth` | Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из | client | services/values.py:219, services/render.py:58 |  |
| `sponsor_company` | Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которы | client | services/values.py:940 |  |
| `stay_permit_no` | Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиент | client | services/values.py:976 | B12E21E1087150-C |
| `place_birth_inline` | Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента | client | services/values.py:1980 |  |

Пробелы: без описания/нет в HTML — 4 (place_date_of_birth, birth_date, place_of_birth, sponsor_company)
Есть в HTML, нет в БД: occupation
