# Пакеты документов Wolf AutoDoc — глобальная инструкция

Построено по реальным папкам клиентов на Google Диске: **70 папок, 457 документов** (распознаны по содержанию, а не по имени файла).
На Диске ничего не изменялось — только чтение.

## 1. Из чего состоит пакет: клиентское и наше

**Даёт клиент** (кладём в его папку на Диске):
- Справка банка об остатке — 135 файлов
- Фотография клиента — 65 файлов
- Паспорт клиента — 63 файлов
- Скриншоты (переписка/подтверждения) — 35 файлов
- Свидетельство о браке — 14 файлов
- Свидетельство о рождении — 11 файлов
- KITAS / stay permit — 10 файлов
- Трудовая книжка (ИТК) — опционально — 2 файлов

**Генерируем мы**:
- Remote Work Agreement (наш договор) — 62 файлов
- Employment agreement — 13 файлов
- Commitment / guarantee letter (генерируем) — 8 файлов
- Permohonan — заявление (генерируем) — 2 файлов
- Резюме (генерируем) — 2 файлов
- Письмо Conversion (генерируем) — 2 файлов
- FORM E-02 (генерируем) — 1 файлов
- Work Agreement — 1 файлов

## 2. Продукт → обязательные документы

### BRIDGING

Генерируем (по системе):
- `bridging_request_letter__denpasar` (bridging_letter)
- `bridging_request_letter__ngurahrai` (bridging_letter)
- `bridging_request_letter__tabanan` (bridging_letter)
- `cv__format_CLIENT` (cv)
- `employment_contract__default` (employment_contract)
- `remote_work_agreement__default` (work_agreement)
- `statement_letter_e02__default` (statement_e02_bridging)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента, Фотография клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

### C1

Генерируем (по системе):
- `bank_statement_3m__sber` (bank_stmt_3m)
- `bank_statement_3m__tbank` (bank_stmt_3m)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента, Фотография клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

### C1-EXT

Генерируем (по системе):
- `bank_statement_3m__sber` (bank_stmt_3m)
- `bank_statement_3m__tbank` (bank_stmt_3m)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

### CONV

Генерируем (по системе):
- `conversion_request_letter__denpasar` (conversion_letter)
- `conversion_request_letter__ngurahrai` (conversion_letter)
- `cv__format_CLIENT` (cv)
- `employment_contract__default` (employment_contract)
- `remote_work_agreement__default` (work_agreement)
- `statement_letter_e02__default` (statement_e02_conversion)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента, Фотография клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

### D12

Генерируем (по системе):
- `bank_statement_3m__sber` (bank_stmt_3m)
- `bank_statement_3m__tbank` (bank_stmt_3m)
- `cv__format_CLIENT` (cv)
- `d12_cover_letter__default` (d12_sponsor_letters)
- `employment_contract__default` (employment_contract)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента, Фотография клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

### E33G-EXT

Генерируем (по системе):
- `bank_statement_3m__sber` (bank_stmt_3m)
- `bank_statement_3m__tbank` (bank_stmt_3m)
- `cv__format_CLIENT` (cv)
- `employment_contract__default` (employment_contract)
- `remote_work_agreement__default` (work_agreement)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента, Фотография клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

### E33G-NEW

Генерируем (по системе):
- `bank_statement_12m__sber` (bank_stmt_12m)
- `bank_statement_12m__tbank` (bank_stmt_12m)
- `bank_statement_3m__sber` (bank_stmt_3m)
- `bank_statement_3m__tbank` (bank_stmt_3m)
- `cv__format_CLIENT` (cv)
- `employment_contract__default` (employment_contract)
- `remote_work_agreement__default` (work_agreement)

Обязательно от клиента: Справка банка об остатке, Паспорт клиента, Фотография клиента
Опционально (встречается у части клиентов): трудовая книжка (ИТК), свидетельство о браке, свидетельство о рождении, KITAS.

## 3. Что реально лежит в папках клиентов

| клиент | продукт | клиентские документы | наши документы |
|---|---|---|---|
| CLIENT_068 | — | Скриншоты (переписка/подтверждения)×7, Свидетельство о рождении×3, Свидетельство о браке×3, KITAS / stay permit×1, Паспорт клиента×1, Фотография клиента×1 | Commitment / guarantee letter (генерируем)×1 |
| CLIENT | — | Скриншоты (переписка/подтверждения)×4, Свидетельство о рождении×2, Свидетельство о браке×2, Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Commitment / guarantee letter (генерируем)×2, Remote Work Agreement (наш договор)×1 |
| CLIENT_002 | — | Справка банка об остатке×3, Фотография клиента×2, Свидетельство о браке×2, KITAS / stay permit×1, Скриншоты (переписка/подтверждения)×1 | Commitment / guarantee letter (генерируем)×1, Remote Work Agreement (наш договор)×1 |
| CLIENT_035 | C1, E33G-NEW | Скриншоты (переписка/подтверждения)×4, Справка банка об остатке×3, KITAS / stay permit×1, Паспорт клиента×1, Фотография клиента×1, Свидетельство о рождении×1, Свидетельство о браке×1 | Commitment / guarantee letter (генерируем)×1, Remote Work Agreement (наш договор)×1 |
| CLIENT_048 | C1 | Справка банка об остатке×2, KITAS / stay permit×1, Паспорт клиента×1, Скриншоты (переписка/подтверждения)×1 | Permohonan — заявление (генерируем)×2, Employment agreement×2, FORM E-02 (генерируем)×1, Резюме (генерируем)×1, Remote Work Agreement (наш договор)×1 |
| CLIENT_004 | — | Справка банка об остатке×2, Свидетельство о рождении×1, Свидетельство о браке×1, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1, Commitment / guarantee letter (генерируем)×1 |
| CLIENT_042 | E33G-NEW | Свидетельство о рождении×2, Справка банка об остатке×2, Скриншоты (переписка/подтверждения)×2, KITAS / stay permit×1, Свидетельство о браке×1, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_031 | — | Справка банка об остатке×2, Скриншоты (переписка/подтверждения)×2, KITAS / stay permit×1, Свидетельство о рождении×1, Свидетельство о браке×1, Паспорт клиента×1, Фотография клиента×1 | Commitment / guarantee letter (генерируем)×1, Remote Work Agreement (наш договор)×1 |
| ANZHELIKA | — | Скриншоты (переписка/подтверждения)×4, KITAS / stay permit×2, Свидетельство о браке×2, Справка банка об остатке×2 | — |
| Suarev Denis&Alia | E33G-NEW | Справка банка об остатке×4, Паспорт клиента×2, Фотография клиента×2 | Remote Work Agreement (наш договор)×2 |
| CLIENT_006 | C1 | Фотография клиента×3, Справка банка об остатке×2, Трудовая книжка (ИТК) — опционально×1, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_026 | E33G-NEW | Фотография клиента×3, Справка банка об остатке×2, Скриншоты (переписка/подтверждения)×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_056 | — | Паспорт клиента×3, Справка банка об остатке×2, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_037 | E33G-NEW | Фотография клиента×2, Справка банка об остатке×2, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1, Employment agreement×1 |
| CLIENT_007 | — | Справка банка об остатке×1, KITAS / stay permit×1, Свидетельство о рождении×1, Свидетельство о браке×1, Паспорт клиента×1, Скриншоты (переписка/подтверждения)×1 | Commitment / guarantee letter (генерируем)×1 |
| CLIENT_053 | E33G-NEW | Справка банка об остатке×2, KITAS / stay permit×1, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_008 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Employment agreement×2 |
| CLIENT_027 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1, Employment agreement×1 |
| CLIENT_018 | — | Справка банка об остатке×2 | Remote Work Agreement (наш договор)×2, Резюме (генерируем)×1 |
| CLIENT_067 | E33G-NEW | Справка банка об остатке×2, Фотография клиента×2, Скриншоты (переписка/подтверждения)×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_062 | — | Справка банка об остатке×3, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_021 | C1 | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Employment agreement×2 |
| CLIENT_005 | — | Справка банка об остатке×2, Фотография клиента×1, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_033 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×2 |
| CLIENT_020 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×2 |
| CLIENT_012 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×2, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_013 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1, Скриншоты (переписка/подтверждения)×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_003 | C1 | Справка банка об остатке×2, Фотография клиента×1, Паспорт клиента×1 | Письмо Conversion (генерируем)×1, Remote Work Agreement (наш договор)×1 |
| CLIENT_060 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_022 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_001 | E33G-NEW | Справка банка об остатке×2, Скриншоты (переписка/подтверждения)×2 | Remote Work Agreement (наш договор)×1 |
| CLIENT_017 | C1, D12, E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_045 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_044 | C1, E33G-NEW | Справка банка об остатке×1, Трудовая книжка (ИТК) — опционально×1, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_030 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_009 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_050 | — | Справка банка об остатке×2, Фотография клиента×2 | Remote Work Agreement (наш договор)×1 |
| CLIENT_059 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Employment agreement×1 |
| CLIENT_063 | — | Справка банка об остатке×2, Фотография клиента×2 | Remote Work Agreement (наш договор)×1 |
| CLIENT_023 | C1 | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_036 | C1, E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_065 | E33G-EXT, E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_043 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_011 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_066 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_015 | — | Справка банка об остатке×2, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_016 | E33G-NEW | Справка банка об остатке×2, Скриншоты (переписка/подтверждения)×2 | Remote Work Agreement (наш договор)×1 |
| CLIENT_029 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_064 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_057 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_014 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_051 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_061 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_019 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_025 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_032 | BRIDGING, E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Employment agreement×1 |
| CLIENT_041 | E33G-EXT | Паспорт клиента×1, Справка банка об остатке×1 | Remote Work Agreement (наш договор)×1, Письмо Conversion (генерируем)×1 |
| CLIENT_024 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_052 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_040 | C1 | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Employment agreement×1 |
| CLIENT_058 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_054 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_034 | E33G-EXT | Справка банка об остатке×2, Паспорт клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_049 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_055 | E33G-NEW | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Employment agreement×1 |
| CLIENT_038 | — | Справка банка об остатке×2, Паспорт клиента×1, Фотография клиента×1 | Remote Work Agreement (наш договор)×1 |
| CLIENT_010 | — | Справка банка об остатке×2, Фотография клиента×2 | Remote Work Agreement (наш договор)×1 |
| CLIENT_039 | E33G-NEW | Паспорт клиента×1, Фотография клиента×1 | Work Agreement×1 |
| CLIENT_047 | C1 | Скриншоты (переписка/подтверждения)×2, Справка банка об остатке×1 | Employment agreement×1 |
| CLIENT_028 | — | Паспорт клиента×1 | — |

## 4. Реальные образцы по группам документов

Ссылка на файл на Диске: `https://drive.google.com/file/d/<id>/view`

### Справка банка об остатке (135 файлов)

- ANZHELIKA — —
- CLIENT_035 — https://drive.google.com/file/d/1xL6ptLijY5bA5iIgj-by2YRyKNYIf4TQ/view
- CLIENT_022 — https://drive.google.com/file/d/1VcJJgroQfJKXYcK2r9fdgP0xTyIMXweg/view
- CLIENT_001 — https://drive.google.com/file/d/1K7qxvxthBqx7m0IejZ2LWbq6L3s_U8YK/view
- CLIENT_017 — https://drive.google.com/file/d/1Z5j1ssKsPM_KF97YOjfg-kFNs9IhYyPg/view
- CLIENT_045 — https://drive.google.com/file/d/1gxyDrglwBMLhK14858Y-iFrGxADf9dLC/view

### Фотография клиента (65 файлов)

- CLIENT_035 — https://drive.google.com/file/d/1sbensNJcxpZreEHTl2z7ftkZctJlMl2Q/view
- CLIENT_017 — https://drive.google.com/file/d/1Zy3KOiYwmOwpNJjwaRR61VS0xQTQVVR4/view
- CLIENT_045 — https://drive.google.com/file/d/1EfWrgX6OqwmoVpwP24R0IVR8_NHHKgke/view
- CLIENT_008 — https://drive.google.com/file/d/15L4PERhNQZYKpcUG25zbGAxXH1gE594i/view
- CLIENT_027 — https://drive.google.com/file/d/1poh4O9kYoCT0VxJk-hZ7ijVVB9NgiNbu/view
- CLIENT_067 — https://drive.google.com/file/d/1VvMlStsQM3n-P7NBxJtd2HRGF2cwc8jr/view

### Паспорт клиента (63 файлов)

- CLIENT_035 — https://drive.google.com/file/d/1c5ATVkJbWYzf5jSkIUKNyOQYZ1XLNoLf/view
- CLIENT_022 — https://drive.google.com/file/d/1DUqXmsDzB4BnM8YI_w_D_fmapGprJg6Q/view
- CLIENT_017 — https://drive.google.com/file/d/1jF5nAqsl5S2DryBn3UajHFrb5SqhHSQQ/view
- CLIENT_045 — https://drive.google.com/file/d/1IS09ReGZvgQWZpl0kMgJ2rDzupcIqrM9/view
- CLIENT_048 — https://drive.google.com/file/d/16jCetqeOzoCLjrYcaeboLXkJtrkHZybf/view
- CLIENT_008 — https://drive.google.com/file/d/1vZVkLxe5KJ2PxCuvYnzk0nMFMyIMtWAs/view

### Remote Work Agreement (наш договор) (62 файлов)

- CLIENT_035 — https://drive.google.com/file/d/1MXF-d6nPtzeirffnnuTRw9Y4n5PtNn82/view
- CLIENT_022 — https://drive.google.com/file/d/1FR1crb5IdGSPUr3PPTS53pxfmwLQeSjZ/view
- CLIENT_001 — https://drive.google.com/file/d/1Zyd8mRMFkxCOvpdkICHfz8YDmZ-rz43u/view
- CLIENT_017 — https://drive.google.com/file/d/1vUCORxL3huSeMBGWZzbQ2UUjb08BahBU/view
- CLIENT_045 — https://drive.google.com/file/d/1us57cGpvqJuTxfVk-3ZMfaMmfTodGAKe/view
- CLIENT_048 — https://drive.google.com/file/d/1_OW5poHARjaTFB0GnQ0hBdGhtG2WiBue/view

### Скриншоты (переписка/подтверждения) (35 файлов)

- ANZHELIKA — —
- CLIENT — —
- CLIENT_035 — —
- CLIENT_001 — https://drive.google.com/file/d/1pKN7einZFlLCNDdFJd8N4Z3C8D4kWd5n/view
- CLIENT_048 — https://drive.google.com/file/d/1DR2ZYflxCaOyq8v3Q0Usz1Q1zvLEb5yZ/view
- CLIENT_067 — https://drive.google.com/file/d/1KINBDX-kpfiqEdDLNxJ3I_TYKuNVVZJj/view

### Свидетельство о браке (14 файлов)

- ANZHELIKA — —
- CLIENT — —
- CLIENT_035 — https://drive.google.com/file/d/1UdZhmWV5bLSRIDFVMew0GdUEXqJGg3iM/view
- CLIENT_004 — https://drive.google.com/file/d/1u-e1MyCuj0L7fuHYrRpeJvkq7NuILEyL/view
- CLIENT_068 — —
- CLIENT_007 — https://drive.google.com/file/d/14BojE6UiMYHeQc9J6zFwlIk_Y2aozuuF/view

### Employment agreement (13 файлов)

- CLIENT_048 — https://drive.google.com/file/d/1M5bc2oXD1JjJ5DRFToaqPlfhlWLUdNf_/view
- CLIENT_008 — https://drive.google.com/file/d/1v2Y739lNOcqoya7S1oXcnSjNTftkwWIT/view
- CLIENT_027 — https://drive.google.com/file/d/1PCFThEpgHtKACpnZBUD52SoyWBjwxMpt/view
- CLIENT_021 — https://drive.google.com/file/d/1wYJRqX-56GV8pA890PKIlYC1889UG6y9/view
- CLIENT_059 — https://drive.google.com/file/d/130vhhzAITlyy9wRNiBnTo-Vls9NPl-Om/view
- CLIENT_037 — https://drive.google.com/file/d/14S7XqeycgcrY_7iRSgs259DrffXrRdsz/view

### Свидетельство о рождении (11 файлов)

- CLIENT — —
- CLIENT_035 — https://drive.google.com/file/d/1mnB6n5ENby8tIeLTxVL8_aawgKomBTWC/view
- CLIENT_004 — https://drive.google.com/file/d/1YKVn-6kuRRh1FNQYLisPRCEagNlIpJQD/view
- CLIENT_068 — —
- CLIENT_007 — https://drive.google.com/file/d/1uKpSw2hC1ErBncmLSHP8clXROUrDlrCV/view
- CLIENT_042 — https://drive.google.com/file/d/1NgTQSsx-vxQVJwdGGTFUUXn1wgnhTcNL/view

### KITAS / stay permit (10 файлов)

- ANZHELIKA — —
- CLIENT_035 — https://drive.google.com/file/d/1JYXlFJhC8dELdeHlC_9NX4voxITXKVWe/view
- CLIENT_048 — https://drive.google.com/file/d/1gVfGk-95jsmByiPnErMotU2oAuJBcLO3/view
- CLIENT_068 — —
- CLIENT_007 — https://drive.google.com/file/d/1_UJo1TYE0jPwDxVmP8Iqh_-h_yTfK_EG/view
- CLIENT_042 — https://drive.google.com/file/d/1N7BF82e3VjbozMw73WBJ31SQjNPy_HsD/view

### Commitment / guarantee letter (генерируем) (8 файлов)

- CLIENT — —
- CLIENT_035 — https://drive.google.com/file/d/1jFKdhRuDr9c8L4uYn81D5CEir7me6SBw/view
- CLIENT_004 — https://drive.google.com/file/d/10obJfXrWcNLH44QNzlAkxMo5-u2JsI7i/view
- CLIENT_068 — —
- CLIENT_007 — https://drive.google.com/file/d/1TIvW_YnWS0-mrvnhtZT0Ixfv2ABbLgMB/view
- CLIENT_002 — https://drive.google.com/file/d/1MEdX3YoOKOkI4i9jVqusp42YsaPyVGer/view

### Учебные материалы (к делу не относятся) (4 файлов)

- CLIENT_068 — —

### Permohonan — заявление (генерируем) (2 файлов)

- CLIENT_048 — https://drive.google.com/file/d/1ojly-fZmvd0qj5RT3Xco7MMHNB9VinWI/view

### Резюме (генерируем) (2 файлов)

- CLIENT_048 — https://drive.google.com/file/d/1-v8S4K6RnWdwEIK0aUBUjEnKf2B6Ba2z/view
- CLIENT_018 — https://drive.google.com/file/d/1Pwk-iYa9JLu8WfykpXuSffTYGSQ5MFSE/view

### Трудовая книжка (ИТК) — опционально (2 файлов)

- CLIENT_044 — https://drive.google.com/file/d/1fNDTQRjqHt2n9E3kk3Kzv-0sWwoeutMs/view
- CLIENT_006 — https://drive.google.com/file/d/1-JK1fqYHzv_7W4Rt-MOdWdCx0H98iwin/view

### Письмо Conversion (генерируем) (2 файлов)

- CLIENT_041 — https://drive.google.com/file/d/1fo55YnFfJiVnWz0eFgTf15nHQb5gp-PK/view
- CLIENT_003 — https://drive.google.com/file/d/1F_Qnggq1qOxUsiOvwqN4b3W4WmkYUXD_/view

### FORM E-02 (генерируем) (1 файлов)

- CLIENT_048 — https://drive.google.com/file/d/1a6DE2Xx8MfRLVUFiKSGJDPMMyVfDRUhE/view

### Work Agreement (1 файлов)

- CLIENT_039 — https://drive.google.com/file/d/1RIu9pQTpr-cA_AB9ipzpfGRevQvBf-zN/view

## 5. Проверка полноты пакета

Реализовано в `services/pack_check.py`: по заявке берётся продукт, требуемые документы, статусы наших документов и клиентские документы (карточка + скан папки на Диске). Отчёт: прогресс, чего нет из нашего, чего нет от клиента.

