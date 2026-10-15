# Пакеты документов по продуктам

Собрано из системы (продукты → документы → переменные) и из разбора реальных папок клиентов на Google Диске. Внутри продукта документы связаны: значения берутся из одной карточки клиента и подставляются в несколько документов.


## BRIDGING — Мостовая виза (60 дней на переход)

### Шаг 1. Состав пакета

**Готовим мы (5 документа):**
- `bridging_request_letter__default` — Bridging: письмо в иммиграцию (офис по адресу клиента) (bridging_letter)
- `cv__format_CLIENT` — Резюме (CV) — формат Сиваева (cv)
- `employment_contract__default` — Employment Contract (договор работы с организацией) (employment_contract)
- `remote_work_agreement__default` — Remote Work Agreement (контракт) (work_agreement)
- `statement_letter_e02__default` — Statement Letter (Form E-02) — Bridging (statement_e02_bridging)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`bridging_request_letter__default`** — 38 переменных: `addressee_office`, `attorney_address`, `attorney_name`, `attorney_nik`, `body_request_line`, `client_address`, `client_dob`, `date`, `itk_expiry`, `itk_no`, `letter_place_date`, `passport_expiry`, `signatory_address`, `signatory_name`, `sponsor_person_name`, `surname`, `date_iso`, `date_iso_2`, `date_iso_3`, `letter_no`, `letter_subject`, `addressee_line1`, `addressee_line2`, `addressee_line3`, `client_gender`, `client_nationality`, `address_in_indonesia`, `place_of_birth`, `address_live`, `application_no`, `client_name`, `passport_no`, `place_date`, `sponsor_name`, `place_birth_inline`, `signatory_position`, `signatory_citizenship`, `signatory_nik_or_dash`

**`cv__format_CLIENT`** — 20 переменных: `cv_profession`, `cv_name`, `cv_date_of_birth`, `cv_place_of_birth`, `cv_nationality`, `cv_passport_no`, `cv_summary`, `cv_job1_title`, `cv_job1_period`, `cv_job1_company`, `cv_job1_bullets`, `cv_job2_period`, `cv_job2_company`, `cv_job2_bullets`, `cv_languages`, `full_name_latin`, `cv_skills_hard`, `cv_education_degree`, `cv_education_school`, `cv_education_years`

**`employment_contract__default`** — 25 переменных: `company_full_name`, `company_type`, `company_country`, `company_entity_no`, `company_address_1`, `company_address_2`, `company_block`, `company_link`, `contract_no`, `contract_date`, `contract_place`, `employee_full_name`, `employee_short`, `passport_number`, `date_of_birth`, `nationality`, `place_of_birth`, `position_title`, `services_list`, `base_salary`, `term_start_date`, `term_end_date`, `signer_title`, `signer_name`, `governing_law`

**`remote_work_agreement__default`** — 29 переменных: `passport_expiry`, `passport_issue_date`, `passport_issued_by`, `the_company_confirms_that`, `services_list`, `agreement_date`, `company_name_in_quotes`, `date_of_birth`, `full_name_latin`, `inn_kpp_ogrn`, `nationality`, `passport_number`, `place_of_birth`, `employee_address`, `contract_no`, `employer_name`, `employee_name`, `company_registered_address`, `company_inn`, `company_kpp`, `company_ogrn`, `position_title`, `term_start_date`, `term_end_date`, `annual_amount_numeric`, `annual_amount_words`, `monthly_amount_numeric`, `monthly_amount_words`, `contractor_full_name`

**`statement_letter_e02__default`** — 21 переменных: `full_name`, `place_date_of_birth`, `date_of_issue`, `date_of_expiry`, `birth_date`, `existing_stay_permit`, `purpose_of_application`, `stay_permit_to_be_applied_for`, `address_in_indonesia`, `client_name`, `doc_date`, `email`, `nationality`, `passport_number`, `phone`, `place`, `guarantor`, `place_of_birth`, `sponsor_company`, `stay_permit_no`, `place_birth_inline`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `place_of_birth` — в 4 документах: `bridging_request_letter__default`, `employment_contract__default`, `remote_work_agreement__default`, `statement_letter_e02__default`
- `nationality` — в 3 документах: `employment_contract__default`, `remote_work_agreement__default`, `statement_letter_e02__default`
- `passport_number` — в 3 документах: `employment_contract__default`, `remote_work_agreement__default`, `statement_letter_e02__default`
- `address_in_indonesia` — в 2 документах: `bridging_request_letter__default`, `statement_letter_e02__default`
- `client_name` — в 2 документах: `bridging_request_letter__default`, `statement_letter_e02__default`
- `contract_no` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `date_of_birth` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `full_name_latin` — в 2 документах: `cv__format_CLIENT`, `remote_work_agreement__default`
- `passport_expiry` — в 2 документах: `bridging_request_letter__default`, `remote_work_agreement__default`
- `place_birth_inline` — в 2 документах: `bridging_request_letter__default`, `statement_letter_e02__default`
- `position_title` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `services_list` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_end_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_start_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`

**Источник каждой переменной:**

`bridging_request_letter__default`:
  - `addressee_office` ← карточка клиента. — нет описания —
  - `attorney_address` ← карточка клиента. — нет описания —
  - `attorney_name` ← карточка клиента. — нет описания —
  - `attorney_nik` ← карточка клиента. — нет описания —
  - `body_request_line` ← карточка клиента. — нет описания —
  - `client_address` ← карточка клиента. — нет описания —
  - `client_dob` ← карточка клиента. — нет описания —
  - `date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `itk_expiry` ← карточка клиента. — нет описания —
  - `itk_no` ← карточка клиента. — нет описания —
  - `letter_place_date` ← карточка клиента. — нет описания —
  - `passport_expiry` ← карточка клиента. — нет описания —
  - `signatory_address` ← карточка клиента. — нет описания —
  - `signatory_name` ← карточка клиента. — нет описания —
  - `sponsor_person_name` ← карточка клиента. — нет описания —
  - `surname` ← карточка клиента. — нет описания —
  - `date_iso` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `date_iso_2` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `date_iso_3` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `letter_no` ← —. Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: форми
  - `letter_subject` ← —. Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбирает по данным клиента
  - `addressee_line1` ← —. Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `addressee_line2` ← —. Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `addressee_line3` ← —. Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `client_gender` ← —. Что это: Пол клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил
  - `client_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл
  - `address_in_indonesia` ← карточка клиента. — нет описания —
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных
  - `application_no` ← карточка клиента. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил
  - `passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов
  - `place_date` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок, 
  - `sponsor_name` ← карточка клиента. Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в о
  - `place_birth_inline` ← карточка клиента. Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента — берутся из реальн
  - `signatory_position` ← sponsor. Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оф
  - `signatory_citizenship` ← sponsor. Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в 
  - `signatory_nik_or_dash` ← sponsor. Что это: NIK подписанта (или прочерк) Тип: logic — логика оформления — люди, компании и адреса, которые участв

`cv__format_CLIENT`:
  - `cv_profession` ← заявка / вручную. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:869
  - `cv_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:267, services/render.py:246
  - `cv_date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1538
  - `cv_place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1540
  - `cv_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1530
  - `cv_passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1535
  - `cv_summary` ← llm. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:729
  - `cv_job1_title` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job2_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_languages` ← документы клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:1371, services/cv_gen.py:959
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `cv_skills_hard` ← карточка клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:980, services/cv_gen.py:867
  - `cv_education_degree` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:903
  - `cv_education_school` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1369, services/cv_gen.py:872
  - `cv_education_years` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:875

`employment_contract__default`:
  - `company_full_name` ← документы клиента. Организация, в которой работает клиент — из заявки (или из пула организаций). Американские организации подстав
  - `company_type` ← logic. Организационно-правовая форма: Limited Liability Company для российских организаций, General Corporation для о
  - `company_country` ← logic. Страна регистрации организации: Russia, India — по записи организации.
  - `company_entity_no` ← logic. Номер регистрации организации: ОГРН, при отсутствии — ИНН (из пула организаций).
  - `company_address_1` ← logic. Адрес организации из пула. Если в пуле только город — дополняется страной (Moscow, Russia), как в подлинных до
  - `company_address_2` ← logic. Продолжение адреса организации, если есть. Пустое значение не печатается.
  - `company_block` ← logic. Фраза о работодателе целиком: «Название, a Limited Liability Company incorporated under the laws of …, Entity 
  - `company_link` ← logic. Краткое описание деятельности организации — фраза «a company engaged in …» из подлинников. В подлинниках: «a c
  - `contract_no` ← logic. Номер договора как в подлинниках: «номер/год» или короткий номер из учёта организации — 14/25, 03/25, 1248. В 
  - `contract_date` ← заявка / вручную. Дата договора — дата начала договора из заявки.
  - `contract_place` ← заявка / вручную. Город заключения договора — город клиента, по умолчанию Moscow.
  - `employee_full_name` ← документы клиента. ФИО работника латиницей, как в паспорте (BUDKO OLEG).
  - `employee_short` ← logic. Подпись работника: фамилия и инициал (BUDKO O.).
  - `passport_number` ← документы клиента. Номер паспорта клиента.
  - `date_of_birth` ← документы клиента. Дата рождения клиента.
  - `nationality` ← документы клиента. Национальность. Сокращение из карточки («RUSIA») печатается как RUSSIAN FEDERATION, как в подлинниках.
  - `place_of_birth` ← документы клиента. Место рождения в формате подлинников: «город, страна» (Petrozavodsk, Russia / Uzbekistan, USSR / Moscow Region
  - `position_title` ← заявка / вручную. Должность клиента в организации — из комментария (brief) заявки. Подставляется и в шапку раздела, и в перечень
  - `services_list` ← llm. Перечень обязанностей: пункты по профессии из справочника (короткий и средний варианты), переносимый список.
  - `base_salary` ← заявка / вручную. Оклад в формате подлинников: «600,000.00» без слова «руб.» — валюта по договору организации.
  - `term_start_date` ← заявка / вручную. Дата начала работы — дата договора заявки.
  - `term_end_date` ← logic. Дата окончания: начало + 5 лет.
  - `signer_title` ← logic. Должность подписанта организации: GENERAL DIRECTOR.
  - `signer_name` ← logic. Полное ФИО подписанта организации (General Director — Кузнецов Олег Юрьевич и т. п.). Если в карточке организа
  - `governing_law` ← derived. — нет описания —

`remote_work_agreement__default`:
  - `passport_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1102
  - `passport_issue_date` ← карточка клиента. Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1101, services/render.py:131
  - `passport_issued_by` ← карточка клиента. Что это: Кем выдан паспорт Тип: client_fact — фактические данные клиента — берутся из реальных документов клие | код: services/values.py:219
  - `the_company_confirms_that` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:948
  - `services_list` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:1051
  - `agreement_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1351
  - `company_name_in_quotes` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1115, services/employer_pool.py:196
  - `date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1089, services/cv_gen.py:778
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `inn_kpp_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1314
  - `nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1096, services/render.py:57
  - `passport_number` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1098, services/render.py:54
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:219, services/render.py:58
  - `employee_address` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81
  - `employer_name` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:218, services/employer_pool.py:195
  - `employee_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218, services/render.py:250
  - `company_registered_address` ← карточка клиента. Что это: Адрес компании Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента | код: services/values.py:223, services/employer_pool.py:197
  - `company_inn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:198
  - `company_kpp` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:199
  - `company_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1119, services/employer_pool.py:200
  - `position_title` ← карточка клиента. Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — берутся из реальных док | код: services/values.py:1213
  - `term_start_date` ← карточка клиента. Что это: Начало срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формир | код: services/values.py:1351
  - `term_end_date` ← карточка клиента. Что это: Окончание срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1352
  - `annual_amount_numeric` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1270, services/salary_pool.py:101
  - `annual_amount_words` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1271, services/salary_pool.py:103
  - `monthly_amount_numeric` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1272, services/salary_pool.py:102
  - `monthly_amount_words` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1273, services/salary_pool.py:104
  - `contractor_full_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218

`statement_letter_e02__default`:
  - `full_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:250
  - `place_date_of_birth` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок,  | код: services/values.py:2035
  - `date_of_issue` ← карточка клиента. Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1967, services/render.py:132
  - `date_of_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1968
  - `birth_date` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1088, services/cv_gen.py:778
  - `existing_stay_permit` ← карточка клиента. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль | код: services/values.py:974
  - `purpose_of_application` ← карточка клиента. Что это: Цель обращения Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:947
  - `stay_permit_to_be_applied_for` ← карточка клиента. Что это: Что запрашиваем по заявке Тип: logic — логика оформления — люди, компании и адреса, которые участвуют | код: services/values.py:947
  - `address_in_indonesia` ← карточка клиента. Что это: Адрес клиента в Индонезии Тип: client_fact — фактические данные клиента — берутся из реальных докумен | код: services/values.py:737
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `email` ← карточка клиента. Что это: Контакты клиента — адрес электронной почты. Формула для ВСЕХ клиентов одна: фамилия клиента латиницей | код: services/values.py:1107, services/render.py:59
  - `nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1096, services/render.py:57
  - `passport_number` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1098, services/render.py:54
  - `phone` ← карточка клиента. Что это: Телефон клиента в форме E-02. Правило (заказчик, 06.10.2026): по стандарту всегда пишется 00 — это зн | код: services/values.py:1107, services/render.py:60
  - `place` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок,  | код: services/values.py:948
  - `guarantor` ← sponsor. Что это: Гарант (поручитель) письма Тип: logic — логика оформления — люди, компании и адреса, которые участвую | код: services/values.py:947
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:219, services/render.py:58
  - `sponsor_company` ← карточка клиента. Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформл | код: services/values.py:940
  - `stay_permit_no` ← карточка клиента. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль | код: services/values.py:976
  - `place_birth_inline` ← карточка клиента. Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента — берутся из реальн | код: services/values.py:1980


## C1 — Виза C1 (B211A — кунджунган, 60 дней, до 180 с продлением)

### Шаг 1. Состав пакета

**Готовим мы (2 документа):**
- `bank_statement_3m__sber` — Банковская справка 3 мес. (Сбер) (bank_stmt_3m)
- `bank_statement_3m__tbank` — Банковская справка 3 мес. (Т-Банк) (bank_stmt_3m)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`bank_statement_3m__sber`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `doc_date`, `balance_rub`, `account_no`, `contract_date`, `contract_no`

**`bank_statement_3m__tbank`** — 10 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `balance_rub`, `doc_date`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `address_live` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_rub` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_words` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `card_mask` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `client_name` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_date` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_from` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_to` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `ref_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`

**Источник каждой переменной:**

`bank_statement_3m__sber`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81

`bank_statement_3m__tbank`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82


## C1-EXT — Продление C1 (+60 дней, до 180)

### Шаг 1. Состав пакета

**Готовим мы (2 документа):**
- `bank_statement_3m__sber` — Банковская справка 3 мес. (Сбер) (bank_stmt_3m)
- `bank_statement_3m__tbank` — Банковская справка 3 мес. (Т-Банк) (bank_stmt_3m)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`bank_statement_3m__sber`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `doc_date`, `balance_rub`, `account_no`, `contract_date`, `contract_no`

**`bank_statement_3m__tbank`** — 10 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `balance_rub`, `doc_date`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `address_live` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_rub` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_words` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `card_mask` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `client_name` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_date` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_from` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_to` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `ref_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`

**Источник каждой переменной:**

`bank_statement_3m__sber`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81

`bank_statement_3m__tbank`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82


## CONV — Конверсия (Alih Status) — выход в KITAS

### Шаг 1. Состав пакета

**Готовим мы (5 документа):**
- `conversion_request_letter__default` — Conversion: письмо в иммиграцию (офис по адресу клиента) (conversion_letter)
- `cv__format_CLIENT` — Резюме (CV) — формат Сиваева (cv)
- `employment_contract__default` — Employment Contract (договор работы с организацией) (employment_contract)
- `remote_work_agreement__default` — Remote Work Agreement (контракт) (work_agreement)
- `statement_letter_e02__default` — Statement Letter (Form E-02) — Bridging (statement_e02_conversion)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`conversion_request_letter__default`** — 44 переменных: `addressee_office`, `body_request_line`, `client_address`, `client_dob`, `date`, `itk_expiry`, `itk_no`, `letter_place_date`, `passport_expiry`, `place_of_birth`, `signatory_address`, `signatory_name`, `sponsor_person_name`, `surname`, `letter_no`, `letter_subject`, `addressee_line1`, `addressee_line2`, `addressee_line3`, `sponsor_address`, `sponsor_contact`, `attorney_name`, `attorney_occupation`, `bridging_visa_no`, `attorney_citizenship`, `attorney_nik`, `attorney_address`, `client_gender`, `client_nationality`, `passport_no`, `place_date_of_birth`, `sponsor_company_details`, `application_no`, `client_name`, `date_iso`, `date_iso_2`, `date_iso_3`, `place_date`, `sponsor_company`, `sponsor_name`, `place_birth_inline`, `signatory_position`, `signatory_citizenship`, `signatory_nik_or_dash`

**`cv__format_CLIENT`** — 20 переменных: `cv_profession`, `cv_name`, `cv_date_of_birth`, `cv_place_of_birth`, `cv_nationality`, `cv_passport_no`, `cv_summary`, `cv_job1_title`, `cv_job1_period`, `cv_job1_company`, `cv_job1_bullets`, `cv_job2_period`, `cv_job2_company`, `cv_job2_bullets`, `cv_languages`, `full_name_latin`, `cv_skills_hard`, `cv_education_degree`, `cv_education_school`, `cv_education_years`

**`employment_contract__default`** — 25 переменных: `company_full_name`, `company_type`, `company_country`, `company_entity_no`, `company_address_1`, `company_address_2`, `company_block`, `company_link`, `contract_no`, `contract_date`, `contract_place`, `employee_full_name`, `employee_short`, `passport_number`, `date_of_birth`, `nationality`, `place_of_birth`, `position_title`, `services_list`, `base_salary`, `term_start_date`, `term_end_date`, `signer_title`, `signer_name`, `governing_law`

**`remote_work_agreement__default`** — 29 переменных: `passport_expiry`, `passport_issue_date`, `passport_issued_by`, `the_company_confirms_that`, `services_list`, `agreement_date`, `company_name_in_quotes`, `date_of_birth`, `full_name_latin`, `inn_kpp_ogrn`, `nationality`, `passport_number`, `place_of_birth`, `employee_address`, `contract_no`, `employer_name`, `employee_name`, `company_registered_address`, `company_inn`, `company_kpp`, `company_ogrn`, `position_title`, `term_start_date`, `term_end_date`, `annual_amount_numeric`, `annual_amount_words`, `monthly_amount_numeric`, `monthly_amount_words`, `contractor_full_name`

**`statement_letter_e02__default`** — 21 переменных: `full_name`, `place_date_of_birth`, `date_of_issue`, `date_of_expiry`, `birth_date`, `existing_stay_permit`, `purpose_of_application`, `stay_permit_to_be_applied_for`, `address_in_indonesia`, `client_name`, `doc_date`, `email`, `nationality`, `passport_number`, `phone`, `place`, `guarantor`, `place_of_birth`, `sponsor_company`, `stay_permit_no`, `place_birth_inline`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `place_of_birth` — в 4 документах: `conversion_request_letter__default`, `employment_contract__default`, `remote_work_agreement__default`, `statement_letter_e02__default`
- `nationality` — в 3 документах: `employment_contract__default`, `remote_work_agreement__default`, `statement_letter_e02__default`
- `passport_number` — в 3 документах: `employment_contract__default`, `remote_work_agreement__default`, `statement_letter_e02__default`
- `client_name` — в 2 документах: `conversion_request_letter__default`, `statement_letter_e02__default`
- `contract_no` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `date_of_birth` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `full_name_latin` — в 2 документах: `cv__format_CLIENT`, `remote_work_agreement__default`
- `passport_expiry` — в 2 документах: `conversion_request_letter__default`, `remote_work_agreement__default`
- `place_birth_inline` — в 2 документах: `conversion_request_letter__default`, `statement_letter_e02__default`
- `place_date_of_birth` — в 2 документах: `conversion_request_letter__default`, `statement_letter_e02__default`
- `position_title` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `services_list` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `sponsor_company` — в 2 документах: `conversion_request_letter__default`, `statement_letter_e02__default`
- `term_end_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_start_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`

**Источник каждой переменной:**

`conversion_request_letter__default`:
  - `addressee_office` ← карточка клиента. — нет описания —
  - `body_request_line` ← карточка клиента. — нет описания —
  - `client_address` ← карточка клиента. — нет описания —
  - `client_dob` ← карточка клиента. — нет описания —
  - `date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `itk_expiry` ← карточка клиента. — нет описания —
  - `itk_no` ← карточка клиента. — нет описания —
  - `letter_place_date` ← карточка клиента. — нет описания —
  - `passport_expiry` ← карточка клиента. — нет описания —
  - `place_of_birth` ← карточка клиента. — нет описания —
  - `signatory_address` ← карточка клиента. — нет описания —
  - `signatory_name` ← карточка клиента. — нет описания —
  - `sponsor_person_name` ← карточка клиента. — нет описания —
  - `surname` ← карточка клиента. — нет описания —
  - `letter_no` ← —. Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: форми
  - `letter_subject` ← —. Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбирает по данным клиента
  - `addressee_line1` ← —. Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `addressee_line2` ← —. Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `addressee_line3` ← —. Что это: Адресат письма Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `sponsor_address` ← —. Что это: Адрес спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен
  - `sponsor_contact` ← —. Что это: Контакты спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформ
  - `attorney_name` ← карточка клиента. Что это: Доверенное лицо (имя) Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в о
  - `attorney_occupation` ← —. Что это: Занятие доверенного лица Тип: logic — логика оформления — люди, компании и адреса, которые участвуют 
  - `bridging_visa_no` ← карточка клиента. Что это: Номер мостовой визы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл
  - `attorney_citizenship` ← —. Что это: Гражданство доверенного лица Тип: logic — логика оформления — люди, компании и адреса, которые участв
  - `attorney_nik` ← —. Что это: NIK доверенного лица Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оф
  - `attorney_address` ← —. Что это: Адрес доверенного лица Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в 
  - `client_gender` ← —. Что это: Пол клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил
  - `client_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл
  - `passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов
  - `place_date_of_birth` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок, 
  - `sponsor_company_details` ← карточка клиента. Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформл
  - `application_no` ← карточка клиента. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил
  - `date_iso` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `date_iso_2` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `date_iso_3` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф
  - `place_date` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок, 
  - `sponsor_company` ← карточка клиента. Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформл
  - `sponsor_name` ← карточка клиента. Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в о
  - `place_birth_inline` ← карточка клиента. Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента — берутся из реальн
  - `signatory_position` ← sponsor. Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оф
  - `signatory_citizenship` ← sponsor. Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в 
  - `signatory_nik_or_dash` ← sponsor. Что это: NIK подписанта (или прочерк) Тип: logic — логика оформления — люди, компании и адреса, которые участв

`cv__format_CLIENT`:
  - `cv_profession` ← заявка / вручную. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:869
  - `cv_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:267, services/render.py:246
  - `cv_date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1538
  - `cv_place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1540
  - `cv_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1530
  - `cv_passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1535
  - `cv_summary` ← llm. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:729
  - `cv_job1_title` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job2_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_languages` ← документы клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:1371, services/cv_gen.py:959
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `cv_skills_hard` ← карточка клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:980, services/cv_gen.py:867
  - `cv_education_degree` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:903
  - `cv_education_school` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1369, services/cv_gen.py:872
  - `cv_education_years` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:875

`employment_contract__default`:
  - `company_full_name` ← документы клиента. Организация, в которой работает клиент — из заявки (или из пула организаций). Американские организации подстав
  - `company_type` ← logic. Организационно-правовая форма: Limited Liability Company для российских организаций, General Corporation для о
  - `company_country` ← logic. Страна регистрации организации: Russia, India — по записи организации.
  - `company_entity_no` ← logic. Номер регистрации организации: ОГРН, при отсутствии — ИНН (из пула организаций).
  - `company_address_1` ← logic. Адрес организации из пула. Если в пуле только город — дополняется страной (Moscow, Russia), как в подлинных до
  - `company_address_2` ← logic. Продолжение адреса организации, если есть. Пустое значение не печатается.
  - `company_block` ← logic. Фраза о работодателе целиком: «Название, a Limited Liability Company incorporated under the laws of …, Entity 
  - `company_link` ← logic. Краткое описание деятельности организации — фраза «a company engaged in …» из подлинников. В подлинниках: «a c
  - `contract_no` ← logic. Номер договора как в подлинниках: «номер/год» или короткий номер из учёта организации — 14/25, 03/25, 1248. В 
  - `contract_date` ← заявка / вручную. Дата договора — дата начала договора из заявки.
  - `contract_place` ← заявка / вручную. Город заключения договора — город клиента, по умолчанию Moscow.
  - `employee_full_name` ← документы клиента. ФИО работника латиницей, как в паспорте (BUDKO OLEG).
  - `employee_short` ← logic. Подпись работника: фамилия и инициал (BUDKO O.).
  - `passport_number` ← документы клиента. Номер паспорта клиента.
  - `date_of_birth` ← документы клиента. Дата рождения клиента.
  - `nationality` ← документы клиента. Национальность. Сокращение из карточки («RUSIA») печатается как RUSSIAN FEDERATION, как в подлинниках.
  - `place_of_birth` ← документы клиента. Место рождения в формате подлинников: «город, страна» (Petrozavodsk, Russia / Uzbekistan, USSR / Moscow Region
  - `position_title` ← заявка / вручную. Должность клиента в организации — из комментария (brief) заявки. Подставляется и в шапку раздела, и в перечень
  - `services_list` ← llm. Перечень обязанностей: пункты по профессии из справочника (короткий и средний варианты), переносимый список.
  - `base_salary` ← заявка / вручную. Оклад в формате подлинников: «600,000.00» без слова «руб.» — валюта по договору организации.
  - `term_start_date` ← заявка / вручную. Дата начала работы — дата договора заявки.
  - `term_end_date` ← logic. Дата окончания: начало + 5 лет.
  - `signer_title` ← logic. Должность подписанта организации: GENERAL DIRECTOR.
  - `signer_name` ← logic. Полное ФИО подписанта организации (General Director — Кузнецов Олег Юрьевич и т. п.). Если в карточке организа
  - `governing_law` ← derived. — нет описания —

`remote_work_agreement__default`:
  - `passport_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1102
  - `passport_issue_date` ← карточка клиента. Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1101, services/render.py:131
  - `passport_issued_by` ← карточка клиента. Что это: Кем выдан паспорт Тип: client_fact — фактические данные клиента — берутся из реальных документов клие | код: services/values.py:219
  - `the_company_confirms_that` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:948
  - `services_list` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:1051
  - `agreement_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1351
  - `company_name_in_quotes` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1115, services/employer_pool.py:196
  - `date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1089, services/cv_gen.py:778
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `inn_kpp_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1314
  - `nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1096, services/render.py:57
  - `passport_number` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1098, services/render.py:54
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:219, services/render.py:58
  - `employee_address` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81
  - `employer_name` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:218, services/employer_pool.py:195
  - `employee_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218, services/render.py:250
  - `company_registered_address` ← карточка клиента. Что это: Адрес компании Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента | код: services/values.py:223, services/employer_pool.py:197
  - `company_inn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:198
  - `company_kpp` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:199
  - `company_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1119, services/employer_pool.py:200
  - `position_title` ← карточка клиента. Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — берутся из реальных док | код: services/values.py:1213
  - `term_start_date` ← карточка клиента. Что это: Начало срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формир | код: services/values.py:1351
  - `term_end_date` ← карточка клиента. Что это: Окончание срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1352
  - `annual_amount_numeric` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1270, services/salary_pool.py:101
  - `annual_amount_words` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1271, services/salary_pool.py:103
  - `monthly_amount_numeric` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1272, services/salary_pool.py:102
  - `monthly_amount_words` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1273, services/salary_pool.py:104
  - `contractor_full_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218

`statement_letter_e02__default`:
  - `full_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:250
  - `place_date_of_birth` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок,  | код: services/values.py:2035
  - `date_of_issue` ← карточка клиента. Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1967, services/render.py:132
  - `date_of_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1968
  - `birth_date` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1088, services/cv_gen.py:778
  - `existing_stay_permit` ← карточка клиента. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль | код: services/values.py:974
  - `purpose_of_application` ← карточка клиента. Что это: Цель обращения Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:947
  - `stay_permit_to_be_applied_for` ← карточка клиента. Что это: Что запрашиваем по заявке Тип: logic — логика оформления — люди, компании и адреса, которые участвуют | код: services/values.py:947
  - `address_in_indonesia` ← карточка клиента. Что это: Адрес клиента в Индонезии Тип: client_fact — фактические данные клиента — берутся из реальных докумен | код: services/values.py:737
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `email` ← карточка клиента. Что это: Контакты клиента — адрес электронной почты. Формула для ВСЕХ клиентов одна: фамилия клиента латиницей | код: services/values.py:1107, services/render.py:59
  - `nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1096, services/render.py:57
  - `passport_number` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1098, services/render.py:54
  - `phone` ← карточка клиента. Что это: Телефон клиента в форме E-02. Правило (заказчик, 06.10.2026): по стандарту всегда пишется 00 — это зн | код: services/values.py:1107, services/render.py:60
  - `place` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок,  | код: services/values.py:948
  - `guarantor` ← sponsor. Что это: Гарант (поручитель) письма Тип: logic — логика оформления — люди, компании и адреса, которые участвую | код: services/values.py:947
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:219, services/render.py:58
  - `sponsor_company` ← карточка клиента. Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформл | код: services/values.py:940
  - `stay_permit_no` ← карточка клиента. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль | код: services/values.py:976
  - `place_birth_inline` ← карточка клиента. Что это: Место и дата рождения одной строкой Тип: client_fact — фактические данные клиента — берутся из реальн | код: services/values.py:1980


## D12 — Виза D12 — Pra-Investasi (многократная 1–2 года)

### Шаг 1. Состав пакета

**Готовим мы (5 документа):**
- `bank_statement_3m__sber` — Банковская справка 3 мес. (Сбер) (bank_stmt_3m)
- `bank_statement_3m__tbank` — Банковская справка 3 мес. (Т-Банк) (bank_stmt_3m)
- `cv__format_CLIENT` — Резюме (CV) — формат Сиваева (cv)
- `d12_cover_letter__default` — D12: Permohonan Visa (ходатайство) (d12_sponsor_letters)
- `employment_contract__default` — Employment Contract (договор работы с организацией) (employment_contract)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`bank_statement_3m__sber`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `doc_date`, `balance_rub`, `account_no`, `contract_date`, `contract_no`

**`bank_statement_3m__tbank`** — 10 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `balance_rub`, `doc_date`

**`cv__format_CLIENT`** — 20 переменных: `cv_profession`, `cv_name`, `cv_date_of_birth`, `cv_place_of_birth`, `cv_nationality`, `cv_passport_no`, `cv_summary`, `cv_job1_title`, `cv_job1_period`, `cv_job1_company`, `cv_job1_bullets`, `cv_job2_period`, `cv_job2_company`, `cv_job2_bullets`, `cv_languages`, `full_name_latin`, `cv_skills_hard`, `cv_education_degree`, `cv_education_school`, `cv_education_years`

**`d12_cover_letter__default`** — 32 переменных: `letter_no`, `letter_subject`, `signatory_position`, `signatory_citizenship`, `signatory_address`, `sponsor_address`, `sponsor_contact`, `sponsor_person_name`, `sponsor_birth_place_date`, `sponsor_nationality`, `sponsor_position`, `passport_no`, `place_date_of_birth`, `client_name`, `place_date`, `sponsor_company`, `job_and_position`, `signatory_name`, `signatory_name_2`, `client_citizenship`, `passport_expiry`, `address_in_indonesia`, `itk_no`, `itk_expiry`, `addressee_line1`, `addressee_line2`, `addressee_line3`, `attorney_occupation`, `attorney_nik`, `attorney_address`, `client_gender`, `place_birth_inline`

**`employment_contract__default`** — 25 переменных: `company_full_name`, `company_type`, `company_country`, `company_entity_no`, `company_address_1`, `company_address_2`, `company_block`, `company_link`, `contract_no`, `contract_date`, `contract_place`, `employee_full_name`, `employee_short`, `passport_number`, `date_of_birth`, `nationality`, `place_of_birth`, `position_title`, `services_list`, `base_salary`, `term_start_date`, `term_end_date`, `signer_title`, `signer_name`, `governing_law`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `client_name` — в 3 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`, `d12_cover_letter__default`
- `address_live` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_rub` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_words` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `card_mask` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `contract_date` — в 2 документах: `bank_statement_3m__sber`, `employment_contract__default`
- `contract_no` — в 2 документах: `bank_statement_3m__sber`, `employment_contract__default`
- `doc_date` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_from` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_to` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `ref_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`

**Источник каждой переменной:**

`bank_statement_3m__sber`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81

`bank_statement_3m__tbank`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82

`cv__format_CLIENT`:
  - `cv_profession` ← заявка / вручную. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:869
  - `cv_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:267, services/render.py:246
  - `cv_date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1538
  - `cv_place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1540
  - `cv_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1530
  - `cv_passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1535
  - `cv_summary` ← llm. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:729
  - `cv_job1_title` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job2_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_languages` ← документы клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:1371, services/cv_gen.py:959
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `cv_skills_hard` ← карточка клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:980, services/cv_gen.py:867
  - `cv_education_degree` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:903
  - `cv_education_school` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1369, services/cv_gen.py:872
  - `cv_education_years` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:875

`d12_cover_letter__default`:
  - `letter_no` ← —. Что это: Номер исходящего письма Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: форми | код: services/values.py:966
  - `letter_subject` ← —. Что это: Тема письма Тип: descriptive — обзорное описание — текст, который система подбирает по данным клиента | код: services/values.py:945
  - `signatory_position` ← sponsor. Что это: Должность подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оф | код: services/values.py:942
  - `signatory_citizenship` ← карточка клиента. Что это: Гражданство подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в  | код: services/values.py:942
  - `signatory_address` ← карточка клиента. Что это: Адрес подписанта Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформл | код: services/values.py:737
  - `sponsor_address` ← —. Что это: Адрес спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформлен | код: services/values.py:737
  - `sponsor_contact` ← —. Что это: Контакты спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформ | код: services/values.py:940
  - `sponsor_person_name` ← карточка клиента. Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в о | код: services/values.py:940
  - `sponsor_birth_place_date` ← —. Что это: Место и дата рождения руководителя спонсора Тип: logic — логика оформления — люди, компании и адреса, | код: services/values.py:941
  - `sponsor_nationality` ← —. Что это: Гражданство спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оф | код: services/values.py:941
  - `sponsor_position` ← карточка клиента. Что это: Руководитель спонсора Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в о | код: services/values.py:941
  - `passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1099, services/render.py:54
  - `place_date_of_birth` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок,  | код: services/values.py:2035
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `place_date` ← карточка клиента. Что это: Место и дата подписания (Индонезия) Тип: doc_service — служебное поле документа — номер, дата, срок,  | код: services/values.py:976
  - `sponsor_company` ← карточка клиента. Что это: Компания-спонсор Тип: logic — логика оформления — люди, компании и адреса, которые участвуют в оформл | код: services/values.py:940
  - `job_and_position` ← карточка клиента. Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — берутся из реальных док | код: services/values.py:2085
  - `signatory_name` ← карточка клиента. Что это: Имя подписанта от агентства Тип: logic — логика оформления — люди, компании и адреса, которые участву | код: services/values.py:2083
  - `signatory_name_2` ← карточка клиента. Что это: Имя подписанта от агентства Тип: logic — логика оформления — люди, компании и адреса, которые участву
  - `client_citizenship` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:2037
  - `passport_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1102
  - `address_in_indonesia` ← карточка клиента. Что это: Адрес клиента в Индонезии Тип: client_fact — фактические данные клиента — берутся из реальных докумен | код: services/values.py:737
  - `itk_no` ← ввод администратора. Что это: Номер разрешения на пребывание (ИТК) Тип: client_fact — фактические данные клиента — берутся из реаль | код: services/values.py:1349
  - `itk_expiry` ← ввод администратора. Что это: Срок разрешения на пребывание Тип: client_fact — фактические данные клиента — берутся из реальных док | код: services/values.py:1349
  - `addressee_line1` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:738
  - `addressee_line2` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:738
  - `addressee_line3` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:739
  - `attorney_occupation` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:939
  - `attorney_nik` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:939
  - `attorney_address` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:738
  - `client_gender` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:1887
  - `place_birth_inline` ← logic. Пример значения взят из оригинального заполненного бланка (МАРКАРОВА, 24.08.2026) — подставляется в превью HTM | код: services/values.py:1980

`employment_contract__default`:
  - `company_full_name` ← документы клиента. Организация, в которой работает клиент — из заявки (или из пула организаций). Американские организации подстав
  - `company_type` ← logic. Организационно-правовая форма: Limited Liability Company для российских организаций, General Corporation для о
  - `company_country` ← logic. Страна регистрации организации: Russia, India — по записи организации.
  - `company_entity_no` ← logic. Номер регистрации организации: ОГРН, при отсутствии — ИНН (из пула организаций).
  - `company_address_1` ← logic. Адрес организации из пула. Если в пуле только город — дополняется страной (Moscow, Russia), как в подлинных до
  - `company_address_2` ← logic. Продолжение адреса организации, если есть. Пустое значение не печатается.
  - `company_block` ← logic. Фраза о работодателе целиком: «Название, a Limited Liability Company incorporated under the laws of …, Entity 
  - `company_link` ← logic. Краткое описание деятельности организации — фраза «a company engaged in …» из подлинников. В подлинниках: «a c
  - `contract_no` ← logic. Номер договора как в подлинниках: «номер/год» или короткий номер из учёта организации — 14/25, 03/25, 1248. В 
  - `contract_date` ← заявка / вручную. Дата договора — дата начала договора из заявки.
  - `contract_place` ← заявка / вручную. Город заключения договора — город клиента, по умолчанию Moscow.
  - `employee_full_name` ← документы клиента. ФИО работника латиницей, как в паспорте (BUDKO OLEG).
  - `employee_short` ← logic. Подпись работника: фамилия и инициал (BUDKO O.).
  - `passport_number` ← документы клиента. Номер паспорта клиента.
  - `date_of_birth` ← документы клиента. Дата рождения клиента.
  - `nationality` ← документы клиента. Национальность. Сокращение из карточки («RUSIA») печатается как RUSSIAN FEDERATION, как в подлинниках.
  - `place_of_birth` ← документы клиента. Место рождения в формате подлинников: «город, страна» (Petrozavodsk, Russia / Uzbekistan, USSR / Moscow Region
  - `position_title` ← заявка / вручную. Должность клиента в организации — из комментария (brief) заявки. Подставляется и в шапку раздела, и в перечень
  - `services_list` ← llm. Перечень обязанностей: пункты по профессии из справочника (короткий и средний варианты), переносимый список.
  - `base_salary` ← заявка / вручную. Оклад в формате подлинников: «600,000.00» без слова «руб.» — валюта по договору организации.
  - `term_start_date` ← заявка / вручную. Дата начала работы — дата договора заявки.
  - `term_end_date` ← logic. Дата окончания: начало + 5 лет.
  - `signer_title` ← logic. Должность подписанта организации: GENERAL DIRECTOR.
  - `signer_name` ← logic. Полное ФИО подписанта организации (General Director — Кузнецов Олег Юрьевич и т. п.). Если в карточке организа
  - `governing_law` ← derived. — нет описания —


## E33G-EXT — Продление E33G КИТАС

### Шаг 1. Состав пакета

**Готовим мы (5 документа):**
- `bank_statement_3m__sber` — Банковская справка 3 мес. (Сбер) (bank_stmt_3m)
- `bank_statement_3m__tbank` — Банковская справка 3 мес. (Т-Банк) (bank_stmt_3m)
- `cv__format_CLIENT` — Резюме (CV) — формат Сиваева (cv)
- `employment_contract__default` — Employment Contract (договор работы с организацией) (employment_contract)
- `remote_work_agreement__default` — Remote Work Agreement (контракт) (work_agreement)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`bank_statement_3m__sber`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `doc_date`, `balance_rub`, `account_no`, `contract_date`, `contract_no`

**`bank_statement_3m__tbank`** — 10 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `balance_rub`, `doc_date`

**`cv__format_CLIENT`** — 20 переменных: `cv_profession`, `cv_name`, `cv_date_of_birth`, `cv_place_of_birth`, `cv_nationality`, `cv_passport_no`, `cv_summary`, `cv_job1_title`, `cv_job1_period`, `cv_job1_company`, `cv_job1_bullets`, `cv_job2_period`, `cv_job2_company`, `cv_job2_bullets`, `cv_languages`, `full_name_latin`, `cv_skills_hard`, `cv_education_degree`, `cv_education_school`, `cv_education_years`

**`employment_contract__default`** — 25 переменных: `company_full_name`, `company_type`, `company_country`, `company_entity_no`, `company_address_1`, `company_address_2`, `company_block`, `company_link`, `contract_no`, `contract_date`, `contract_place`, `employee_full_name`, `employee_short`, `passport_number`, `date_of_birth`, `nationality`, `place_of_birth`, `position_title`, `services_list`, `base_salary`, `term_start_date`, `term_end_date`, `signer_title`, `signer_name`, `governing_law`

**`remote_work_agreement__default`** — 29 переменных: `passport_expiry`, `passport_issue_date`, `passport_issued_by`, `the_company_confirms_that`, `services_list`, `agreement_date`, `company_name_in_quotes`, `date_of_birth`, `full_name_latin`, `inn_kpp_ogrn`, `nationality`, `passport_number`, `place_of_birth`, `employee_address`, `contract_no`, `employer_name`, `employee_name`, `company_registered_address`, `company_inn`, `company_kpp`, `company_ogrn`, `position_title`, `term_start_date`, `term_end_date`, `annual_amount_numeric`, `annual_amount_words`, `monthly_amount_numeric`, `monthly_amount_words`, `contractor_full_name`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `contract_no` — в 3 документах: `bank_statement_3m__sber`, `employment_contract__default`, `remote_work_agreement__default`
- `address_live` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_rub` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_words` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `card_mask` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `client_name` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `contract_date` — в 2 документах: `bank_statement_3m__sber`, `employment_contract__default`
- `date_of_birth` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `doc_date` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `full_name_latin` — в 2 документах: `cv__format_CLIENT`, `remote_work_agreement__default`
- `nationality` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `passport_number` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `period_from` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_to` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `place_of_birth` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `position_title` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `ref_no` — в 2 документах: `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `services_list` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_end_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_start_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`

**Источник каждой переменной:**

`bank_statement_3m__sber`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81

`bank_statement_3m__tbank`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82

`cv__format_CLIENT`:
  - `cv_profession` ← заявка / вручную. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:869
  - `cv_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:267, services/render.py:246
  - `cv_date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1538
  - `cv_place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1540
  - `cv_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1530
  - `cv_passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1535
  - `cv_summary` ← llm. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:729
  - `cv_job1_title` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job2_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_languages` ← документы клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:1371, services/cv_gen.py:959
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `cv_skills_hard` ← карточка клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:980, services/cv_gen.py:867
  - `cv_education_degree` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:903
  - `cv_education_school` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1369, services/cv_gen.py:872
  - `cv_education_years` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:875

`employment_contract__default`:
  - `company_full_name` ← документы клиента. Организация, в которой работает клиент — из заявки (или из пула организаций). Американские организации подстав
  - `company_type` ← logic. Организационно-правовая форма: Limited Liability Company для российских организаций, General Corporation для о
  - `company_country` ← logic. Страна регистрации организации: Russia, India — по записи организации.
  - `company_entity_no` ← logic. Номер регистрации организации: ОГРН, при отсутствии — ИНН (из пула организаций).
  - `company_address_1` ← logic. Адрес организации из пула. Если в пуле только город — дополняется страной (Moscow, Russia), как в подлинных до
  - `company_address_2` ← logic. Продолжение адреса организации, если есть. Пустое значение не печатается.
  - `company_block` ← logic. Фраза о работодателе целиком: «Название, a Limited Liability Company incorporated under the laws of …, Entity 
  - `company_link` ← logic. Краткое описание деятельности организации — фраза «a company engaged in …» из подлинников. В подлинниках: «a c
  - `contract_no` ← logic. Номер договора как в подлинниках: «номер/год» или короткий номер из учёта организации — 14/25, 03/25, 1248. В 
  - `contract_date` ← заявка / вручную. Дата договора — дата начала договора из заявки.
  - `contract_place` ← заявка / вручную. Город заключения договора — город клиента, по умолчанию Moscow.
  - `employee_full_name` ← документы клиента. ФИО работника латиницей, как в паспорте (BUDKO OLEG).
  - `employee_short` ← logic. Подпись работника: фамилия и инициал (BUDKO O.).
  - `passport_number` ← документы клиента. Номер паспорта клиента.
  - `date_of_birth` ← документы клиента. Дата рождения клиента.
  - `nationality` ← документы клиента. Национальность. Сокращение из карточки («RUSIA») печатается как RUSSIAN FEDERATION, как в подлинниках.
  - `place_of_birth` ← документы клиента. Место рождения в формате подлинников: «город, страна» (Petrozavodsk, Russia / Uzbekistan, USSR / Moscow Region
  - `position_title` ← заявка / вручную. Должность клиента в организации — из комментария (brief) заявки. Подставляется и в шапку раздела, и в перечень
  - `services_list` ← llm. Перечень обязанностей: пункты по профессии из справочника (короткий и средний варианты), переносимый список.
  - `base_salary` ← заявка / вручную. Оклад в формате подлинников: «600,000.00» без слова «руб.» — валюта по договору организации.
  - `term_start_date` ← заявка / вручную. Дата начала работы — дата договора заявки.
  - `term_end_date` ← logic. Дата окончания: начало + 5 лет.
  - `signer_title` ← logic. Должность подписанта организации: GENERAL DIRECTOR.
  - `signer_name` ← logic. Полное ФИО подписанта организации (General Director — Кузнецов Олег Юрьевич и т. п.). Если в карточке организа
  - `governing_law` ← derived. — нет описания —

`remote_work_agreement__default`:
  - `passport_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1102
  - `passport_issue_date` ← карточка клиента. Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1101, services/render.py:131
  - `passport_issued_by` ← карточка клиента. Что это: Кем выдан паспорт Тип: client_fact — фактические данные клиента — берутся из реальных документов клие | код: services/values.py:219
  - `the_company_confirms_that` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:948
  - `services_list` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:1051
  - `agreement_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1351
  - `company_name_in_quotes` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1115, services/employer_pool.py:196
  - `date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1089, services/cv_gen.py:778
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `inn_kpp_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1314
  - `nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1096, services/render.py:57
  - `passport_number` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1098, services/render.py:54
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:219, services/render.py:58
  - `employee_address` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81
  - `employer_name` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:218, services/employer_pool.py:195
  - `employee_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218, services/render.py:250
  - `company_registered_address` ← карточка клиента. Что это: Адрес компании Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента | код: services/values.py:223, services/employer_pool.py:197
  - `company_inn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:198
  - `company_kpp` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:199
  - `company_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1119, services/employer_pool.py:200
  - `position_title` ← карточка клиента. Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — берутся из реальных док | код: services/values.py:1213
  - `term_start_date` ← карточка клиента. Что это: Начало срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формир | код: services/values.py:1351
  - `term_end_date` ← карточка клиента. Что это: Окончание срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1352
  - `annual_amount_numeric` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1270, services/salary_pool.py:101
  - `annual_amount_words` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1271, services/salary_pool.py:103
  - `monthly_amount_numeric` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1272, services/salary_pool.py:102
  - `monthly_amount_words` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1273, services/salary_pool.py:104
  - `contractor_full_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218


## E33G-NEW — Новый E33G КИТАС (Remote Worker)

### Шаг 1. Состав пакета

**Готовим мы (7 документа):**
- `bank_statement_12m__sber` — Банковская справка 12 мес. (Сбер) (bank_stmt_12m)
- `bank_statement_12m__tbank` — Банковская справка 12 мес. (Т-Банк) (bank_stmt_12m)
- `bank_statement_3m__sber` — Банковская справка 3 мес. (Сбер) (bank_stmt_3m)
- `bank_statement_3m__tbank` — Банковская справка 3 мес. (Т-Банк) (bank_stmt_3m)
- `cv__format_CLIENT` — Резюме (CV) — формат Сиваева (cv)
- `employment_contract__default` — Employment Contract (договор работы с организацией) (employment_contract)
- `remote_work_agreement__default` — Remote Work Agreement (контракт) (work_agreement)

**Даёт клиент:**
- Загранпаспорт клиента — паспорт: серия/номер, кем выдан, даты
- Фотография клиента — фото 3×4/4×6 в цвете
- Справка банка об остатке — остаток, период, номер справки, банк
- Адрес проживания и регистрации — город, улица, дом, индекс

**Опционально (если есть у клиента):**
- Свидетельство о браке — для подачи с супругом(ой)
- Свидетельство о рождении — для подачи с детьми
- Действующий KITAS / ITK-пермит — при продлении и конверсии
- Трудовая книжка (ИТК) — встречается у ~7% клиентов
- Commitment / guarantee letter — для зависимых членов семьи

### Шаг 2. Переменные документов пакета

**`bank_statement_12m__sber`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `doc_date`, `contract_date`, `contract_no`, `account_no`, `balance_rub`

**`bank_statement_12m__tbank`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `contract_no`, `account_no`, `balance_rub`, `doc_date`, `contract_date`

**`bank_statement_3m__sber`** — 13 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `doc_date`, `balance_rub`, `account_no`, `contract_date`, `contract_no`

**`bank_statement_3m__tbank`** — 10 переменных: `doc_no`, `card_mask`, `ref_no`, `address_live`, `balance_words`, `client_name`, `period_from`, `period_to`, `balance_rub`, `doc_date`

**`cv__format_CLIENT`** — 20 переменных: `cv_profession`, `cv_name`, `cv_date_of_birth`, `cv_place_of_birth`, `cv_nationality`, `cv_passport_no`, `cv_summary`, `cv_job1_title`, `cv_job1_period`, `cv_job1_company`, `cv_job1_bullets`, `cv_job2_period`, `cv_job2_company`, `cv_job2_bullets`, `cv_languages`, `full_name_latin`, `cv_skills_hard`, `cv_education_degree`, `cv_education_school`, `cv_education_years`

**`employment_contract__default`** — 25 переменных: `company_full_name`, `company_type`, `company_country`, `company_entity_no`, `company_address_1`, `company_address_2`, `company_block`, `company_link`, `contract_no`, `contract_date`, `contract_place`, `employee_full_name`, `employee_short`, `passport_number`, `date_of_birth`, `nationality`, `place_of_birth`, `position_title`, `services_list`, `base_salary`, `term_start_date`, `term_end_date`, `signer_title`, `signer_name`, `governing_law`

**`remote_work_agreement__default`** — 29 переменных: `passport_expiry`, `passport_issue_date`, `passport_issued_by`, `the_company_confirms_that`, `services_list`, `agreement_date`, `company_name_in_quotes`, `date_of_birth`, `full_name_latin`, `inn_kpp_ogrn`, `nationality`, `passport_number`, `place_of_birth`, `employee_address`, `contract_no`, `employer_name`, `employee_name`, `company_registered_address`, `company_inn`, `company_kpp`, `company_ogrn`, `position_title`, `term_start_date`, `term_end_date`, `annual_amount_numeric`, `annual_amount_words`, `monthly_amount_numeric`, `monthly_amount_words`, `contractor_full_name`

### Шаг 3. Откуда берётся и с чем связано

**Сквозные переменные пакета** (одно значение — сразу в нескольких документах):

- `contract_no` — в 5 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `employment_contract__default`, `remote_work_agreement__default`
- `address_live` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_rub` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `balance_words` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `card_mask` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `client_name` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `contract_date` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `employment_contract__default`
- `doc_date` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `doc_no` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_from` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `period_to` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `ref_no` — в 4 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`, `bank_statement_3m__tbank`
- `account_no` — в 3 документах: `bank_statement_12m__sber`, `bank_statement_12m__tbank`, `bank_statement_3m__sber`
- `date_of_birth` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `full_name_latin` — в 2 документах: `cv__format_CLIENT`, `remote_work_agreement__default`
- `nationality` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `passport_number` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `place_of_birth` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `position_title` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `services_list` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_end_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`
- `term_start_date` — в 2 документах: `employment_contract__default`, `remote_work_agreement__default`

**Источник каждой переменной:**

`bank_statement_12m__sber`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56

`bank_statement_12m__tbank`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460

`bank_statement_3m__sber`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `account_no` ← карточка клиента. Что это: Номер счёта Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:1123, services/autofill.py:81
  - `contract_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1460
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81

`bank_statement_3m__tbank`:
  - `doc_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `card_mask` ← карточка клиента. Что это: Маска номера карты Тип: client_fact — фактические данные клиента — берутся из реальных документов кли | код: services/values.py:1127, services/autofill.py:81
  - `ref_no` ← карточка клиента. Что это: Номер документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сис | код: services/values.py:529, services/autofill.py:81
  - `address_live` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222, services/render.py:53
  - `balance_words` ← карточка клиента. Что это: Остаток на счёте (прописью) Тип: client_fact — фактические данные клиента — берутся из реальных докум | код: services/values.py:1688, services/autofill.py:68
  - `client_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:217, services/render.py:50
  - `period_from` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1137, services/render.py:549
  - `period_to` ← карточка клиента. Что это: Период выписки банка Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1139, services/render.py:548
  - `balance_rub` ← карточка клиента. Что это: Остаток на счёте (цифрами) Тип: client_fact — фактические данные клиента — берутся из реальных докуме | код: services/values.py:442, services/autofill.py:56
  - `doc_date` ← карточка клиента. Что это: Дата формирования документа Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: ф | код: services/values.py:976, services/autofill.py:82

`cv__format_CLIENT`:
  - `cv_profession` ← заявка / вручную. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:869
  - `cv_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:267, services/render.py:246
  - `cv_date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1538
  - `cv_place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1540
  - `cv_nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1530
  - `cv_passport_no` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1535
  - `cv_summary` ← llm. Что это: Резюме: служебные поля Тип: descriptive — обзорное описание — текст, который система подбирает по дан | код: services/values.py:979, services/cv_gen.py:729
  - `cv_job1_title` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job1_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:981, services/cv_gen.py:894
  - `cv_job2_period` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_company` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_job2_bullets` ← llm. Что это: Резюме: опыт работы Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:982, services/cv_gen.py:895
  - `cv_languages` ← документы клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:1371, services/cv_gen.py:959
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `cv_skills_hard` ← карточка клиента. Что это: Резюме: навыки Тип: descriptive — обзорное описание — текст, который система подбирает по данным клие | код: services/values.py:980, services/cv_gen.py:867
  - `cv_education_degree` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:903
  - `cv_education_school` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1369, services/cv_gen.py:872
  - `cv_education_years` ← карточка клиента. Что это: Резюме: образование Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1370, services/cv_gen.py:875

`employment_contract__default`:
  - `company_full_name` ← документы клиента. Организация, в которой работает клиент — из заявки (или из пула организаций). Американские организации подстав
  - `company_type` ← logic. Организационно-правовая форма: Limited Liability Company для российских организаций, General Corporation для о
  - `company_country` ← logic. Страна регистрации организации: Russia, India — по записи организации.
  - `company_entity_no` ← logic. Номер регистрации организации: ОГРН, при отсутствии — ИНН (из пула организаций).
  - `company_address_1` ← logic. Адрес организации из пула. Если в пуле только город — дополняется страной (Moscow, Russia), как в подлинных до
  - `company_address_2` ← logic. Продолжение адреса организации, если есть. Пустое значение не печатается.
  - `company_block` ← logic. Фраза о работодателе целиком: «Название, a Limited Liability Company incorporated under the laws of …, Entity 
  - `company_link` ← logic. Краткое описание деятельности организации — фраза «a company engaged in …» из подлинников. В подлинниках: «a c
  - `contract_no` ← logic. Номер договора как в подлинниках: «номер/год» или короткий номер из учёта организации — 14/25, 03/25, 1248. В 
  - `contract_date` ← заявка / вручную. Дата договора — дата начала договора из заявки.
  - `contract_place` ← заявка / вручную. Город заключения договора — город клиента, по умолчанию Moscow.
  - `employee_full_name` ← документы клиента. ФИО работника латиницей, как в паспорте (BUDKO OLEG).
  - `employee_short` ← logic. Подпись работника: фамилия и инициал (BUDKO O.).
  - `passport_number` ← документы клиента. Номер паспорта клиента.
  - `date_of_birth` ← документы клиента. Дата рождения клиента.
  - `nationality` ← документы клиента. Национальность. Сокращение из карточки («RUSIA») печатается как RUSSIAN FEDERATION, как в подлинниках.
  - `place_of_birth` ← документы клиента. Место рождения в формате подлинников: «город, страна» (Petrozavodsk, Russia / Uzbekistan, USSR / Moscow Region
  - `position_title` ← заявка / вручную. Должность клиента в организации — из комментария (brief) заявки. Подставляется и в шапку раздела, и в перечень
  - `services_list` ← llm. Перечень обязанностей: пункты по профессии из справочника (короткий и средний варианты), переносимый список.
  - `base_salary` ← заявка / вручную. Оклад в формате подлинников: «600,000.00» без слова «руб.» — валюта по договору организации.
  - `term_start_date` ← заявка / вручную. Дата начала работы — дата договора заявки.
  - `term_end_date` ← logic. Дата окончания: начало + 5 лет.
  - `signer_title` ← logic. Должность подписанта организации: GENERAL DIRECTOR.
  - `signer_name` ← logic. Полное ФИО подписанта организации (General Director — Кузнецов Олег Юрьевич и т. п.). Если в карточке организа
  - `governing_law` ← derived. — нет описания —

`remote_work_agreement__default`:
  - `passport_expiry` ← карточка клиента. Что это: Срок действия паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1102
  - `passport_issue_date` ← карточка клиента. Что это: Дата выдачи паспорта Тип: client_fact — фактические данные клиента — берутся из реальных документов к | код: services/values.py:1101, services/render.py:131
  - `passport_issued_by` ← карточка клиента. Что это: Кем выдан паспорт Тип: client_fact — фактические данные клиента — берутся из реальных документов клие | код: services/values.py:219
  - `the_company_confirms_that` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:948
  - `services_list` ← карточка клиента. Что это: Фраза подтверждения компании Тип: descriptive — обзорное описание — текст, который система подбирает  | код: services/values.py:1051
  - `agreement_date` ← карточка клиента. Что это: Дата договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует систе | код: services/values.py:1351
  - `company_name_in_quotes` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1115, services/employer_pool.py:196
  - `date_of_birth` ← карточка клиента. Что это: Дата рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:1089, services/cv_gen.py:778
  - `full_name_latin` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:66, services/cv_gen.py:808
  - `inn_kpp_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1314
  - `nationality` ← карточка клиента. Что это: Гражданство клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов кл | код: services/values.py:1096, services/render.py:57
  - `passport_number` ← карточка клиента. Что это: Номер паспорта клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:1098, services/render.py:54
  - `place_of_birth` ← карточка клиента. Что это: Место рождения клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов | код: services/values.py:219, services/render.py:58
  - `employee_address` ← карточка клиента. Что это: Адрес клиента в стране проживания Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:222
  - `contract_no` ← карточка клиента. Что это: Номер договора Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формирует сист | код: services/values.py:1124, services/autofill.py:81
  - `employer_name` ← карточка клиента. Что это: Компания-работодатель Тип: client_fact — фактические данные клиента — берутся из реальных документов  | код: services/values.py:218, services/employer_pool.py:195
  - `employee_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218, services/render.py:250
  - `company_registered_address` ← карточка клиента. Что это: Адрес компании Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента | код: services/values.py:223, services/employer_pool.py:197
  - `company_inn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:198
  - `company_kpp` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1118, services/employer_pool.py:199
  - `company_ogrn` ← карточка клиента. Что это: Реквизиты компании (ИНН/КПП/ОГРН) Тип: client_fact — фактические данные клиента — берутся из реальных | код: services/values.py:1119, services/employer_pool.py:200
  - `position_title` ← карточка клиента. Что это: Профессия и должность клиента Тип: client_fact — фактические данные клиента — берутся из реальных док | код: services/values.py:1213
  - `term_start_date` ← карточка клиента. Что это: Начало срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: формир | код: services/values.py:1351
  - `term_end_date` ← карточка клиента. Что это: Окончание срока (договор) Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1352
  - `annual_amount_numeric` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1270, services/salary_pool.py:101
  - `annual_amount_words` ← карточка клиента. Что это: Годовая сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фор | код: services/values.py:1271, services/salary_pool.py:103
  - `monthly_amount_numeric` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1272, services/salary_pool.py:102
  - `monthly_amount_words` ← карточка клиента. Что это: Месячная сумма по договору Тип: doc_service — служебное поле документа — номер, дата, срок, суммы: фо | код: services/values.py:1273, services/salary_pool.py:104
  - `contractor_full_name` ← карточка клиента. Что это: ФИО клиента Тип: client_fact — фактические данные клиента — берутся из реальных документов клиента ил | код: services/values.py:218

