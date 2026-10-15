# Документ №5 «Резюме (CV) — расширенный формат» — разбор переменных
Шаблон `cv__format_detailed`, templates.id = 5, файл `data/templates/cv__format_detailed/template.html`
Разбор: 04.10.2026

## Почему «18» и «31» не сходятся
- В самом документе (видимая часть) — **24 переменные**.
- В базе шаблона — **31 запись**: 22 рабочие + `client_photo_url` + `full_name_latin` + 7 «сирот».
- В HTML зашит служебный блок «CV variable catalogue» — 26 имён из старого макета
  (`full_name`, `position`, `birth_date`, `education_institution` и т.п.). Код его не читает,
  это мусор от перевода PDF → HTML. Он и создаёт путаницу в счётчиках.
- Бейдж на странице конструктора показывает «📊 24 переменных».

## Дубли и сироты
| переменная | статус | решение |
|---|---|---|
| `full_name_latin` | в документе НЕ выводится (только в мусорном каталоге) | дубль `cv_name` → убрать |
| `passport_number` | в документе НЕ выводится | дубль `cv_passport_no` → убрать |
| `cv_job3_title / period / company / bullets` | в документе третьего места работы нет | не используются |
| `cv_education_school`, `cv_education_years` | в документе образование = степень + примечание | не используются |
| каталог `data-cv-vars` в HTML (26 имён) | никем не читается | удалить |

## Карта: как заполнять каждую переменную
**К** — из карточки клиента (без ИИ), **И** — генерирует ИИ по документам и правилу, **С** — выбор из списка.

### Шапка документа
| переменная | способ | откуда | куда вставляется |
|---|---|---|---|
| `client_photo_url` | К | фото из карточки (base64) | рамка фото слева вверху |
| `cv_name` | К | ФИО из карточки, латиницей заглавными | имя под фото |

### Личные данные
| переменная | способ | откуда | формат |
|---|---|---|---|
| `cv_date_of_birth` | К | карточка / загранпаспорт | «November 3, 1990» — месяц словом |
| `cv_place_of_birth` | К | загранпаспорт | «Yakutsk, Yakutskaya ASSR, USSR» |
| `cv_nationality` | К + С | паспорт; список стран | «Russian Federation» |
| `cv_passport_no` | К | паспорт | «77 9937194» — серия и номер через пробел |
| `cv_passport_issue` | К | паспорт | «August 14, 2026» |
| `cv_passport_expiry` | К | паспорт | «August 14, 2036» |

### О себе
| `cv_summary` | И | резюме и документы клиента | абзац 3–5 строк на английском |

### Опыт работы — 2 места в макете
| `cv_job1_title` | И | резюме / договор | должность на английском |
| `cv_job1_period` | И | резюме | «March 2018 – Present» |
| `cv_job1_company` | И | резюме / договор | «LLC ROBUSTA, Moscow, Russia» |
| `cv_job1_bullets` | И | резюме | 3–5 строк, каждая с глагола действия |
| `cv_job2_*` | И | то же | то же |

### Образование
| `cv_education_degree` | И + С | диплом / резюме; список степеней | «Bachelor of Economics» |
| `cv_education_note` | И | резюме | специализация, диплом с отличием; пусто, если нечего добавить |

### Навыки
| `cv_skills_hard` | И + С | резюме; пул типовых | через запятую: B2B Sales, Contract Negotiation |
| `cv_skills_soft` | И + С | пул типовых (личные качества) | Team Leadership, Time Management |
| `cv_skills_tools` | И + С | пул типовых (программы) | Salesforce, Microsoft Office Suite |
| `cv_languages` | С | пул «язык (уровень)» | Russian (Native), English (Upper-Intermediate / B2) |

## Пул вариантов для списков (типовые формулировки, без персональных данных)
- **Гражданство:** Russian Federation · Kazakhstan · Belarus · Ukraine · Uzbekistan · Kyrgyzstan · Armenia · Turkey
- **Степень:** Bachelor of … · Master of … · Specialist / Diploma · PhD
- **Языки:** Russian (Native) · English (A2 / B1 / B2 / C1 / C2, Upper-Intermediate) · Indonesian (Basic / B1) · Chinese (HSK 3 / 4 / 5)
- **Личные качества:** Team Leadership · Time Management · Problem Solving · Communication · Adaptability ·
  Attention to Detail · Multitasking · Stress Resistance
- **Программы:** Microsoft Office Suite · Google Workspace · Excel (advanced) · 1C · Bitrix24 · Jira ·
  Salesforce · Adobe Photoshop · AutoCAD · CRM
- **Профессиональные навыки (заготовки по сферам):** B2B Sales · Contract Negotiation · Client Relations ·
  Recruitment · Payroll · Financial Reporting · IT Support · Network Administration · Kitchen Operations ·
  Inventory Management · Marketing Strategy · SMM

## Правило безопасности
История значений (`variable_value_history`, 68 записей по этому шаблону) содержит **персональные данные
клиентов** — ФИО, паспорта. Она работает как история по своей заявке, но **не должна** становиться
словарём подсказок для других клиентов. Пулы вариантов — только типовые формулировки выше.

## Как править
- Подпись поля — в конструкторе, у самого поля.
- Правило заполнения — там же; применяется ко всем заявкам.
- Значение по умолчанию — для полей, одинаковых у всех.
- Заявка читает те же переменные, поэтому правка шаблона сразу видна в заявке.
