# Приёмка HTML-шаблонов

Дата: 06.10.2026 10:55

```
№1   bank_statement_3m__tbank               НА ПЕРЕДЕЛКУ (2)
   стр1: наложение (77%) — '127287,' ↔ 'RUSSIA TEL.: +7 495 648-10-00, T'
   стр1: наложение (79%) — 'Unishinaia, D. 71, Korp. 1, Kv. ' ↔ 'D. 71, Korp. 1, Kv. 376'

№2   bank_statement_3m__sber                НА ПЕРЕДЕЛКУ (3)
   стр1: наложение (87%) — 'Petrozavodsk, Krasnaya St, D. 36' ↔ 'Russian Federation, Republic of '
   стр1: наложение (80%) — 'issued' ↔ 'for CLIENT_021 Alekseevi'
   стр1: наложение (77%) — 'thousand five hundred eight rubl' ↔ '(one million two hundred thirty-'

№3   bank_statement_12m__tbank              НА ПЕРЕДЕЛКУ (2)
   стр1: наложение (80%) — 'for' ↔ 'CLIENT CLIENT.'
   стр1: наложение (77%) — 'thousand three hundred nine rubl' ↔ 'thousand three hundred nine rubl'

№4   bank_statement_12m__sber               НА ПЕРЕДЕЛКУ (3)
   стр1: наложение (87%) — 'Petrozavodsk, Krasnaya St, D. 36' ↔ 'Russian Federation, Republic of '
   стр1: наложение (80%) — 'issued' ↔ 'for CLIENT_021 Alekseevi'
   стр1: наложение (77%) — 'thousand five hundred eight rubl' ↔ '(one million two hundred thirty-'

№7   cv__format_CLIENT                      НА ПЕРЕДЕЛКУ (2)
   стр1: наложение (48%) — 'applicable laws and' ↔ 'Lomonosov Moscow State Universit'
   нет места в шаблоне для 6 строк примера (первые: •  Developing and implementi; •  Overseeing sales, procure; •  Supervising staff, monito)

№8   d12_cover_letter__default              ГОДЕН


№9   statement_letter_e02__default          НА ПЕРЕДЕЛКУ (5)
   стр1: наложение (94%) — 'such,' ↔ 'I will apply for a new Limited S'
   стр1: наложение (96%) — 'issued' ↔ 'and will be responsible for any '
   стр1: наложение (94%) — 'be' ↔ 'untrue, then I am willing to be '
   стр1: наложение (95%) — 'REGULATIONS, 06.10.2026' ↔ '(place),(dd, month, yyyy)'
   лишних блоков в шаблоне: 1 (первые: {{place}}, {{doc_date}})

№11  remote_work_agreement__default         НА ПЕРЕДЕЛКУ (11)
   стр2: наложение (41%) — 'LLC Consulting Group "MAYAK"' ↔ 'Contractor shall be solely respo'
   стр3: наложение (47%) — 'Passport: , valid until' ↔ 'with registered address at Mosco'
   стр3: наложение (91%) — 'Passport: , valid until' ↔ 'Federation,'
   стр3: наложение (42%) — 'Date: 30th September 2026' ↔ ', Passport N o: , Date of Bi rth'
   стр3: наложение (84%) — 'with registered address at Mosco' ↔ 'Federation,'
   лишних блоков в шаблоне: 10 (первые: remai nvalid until {{ term_e; remai nvalid until {{ term_e; Name: {{ employee_name }})
   строка шаблона y=618 сдвинута на 11.4pt от примера — 'remai nvalid until {{ term_end_date }}, '
   строка шаблона y=618 сдвинута на 11.6pt от примера — 'remai nvalid until {{ term_end_date }}, '
   строка шаблона y=232 сдвинута на 5.4pt от примера — '{{ company_incorporated_phrase }}'
   строка шаблона y=337 сдвинута на 3.6pt от примера — 'Birth :{{ place_of_birth }}, (here inaft'
   строка шаблона y=445 сдвинута на 7.1pt от примера — '{{ engagement_line }}'

№13  conversion_request_letter__default     НА ПЕРЕДЕЛКУ (1)
   нет места в шаблоне для 1 строк примера (первые: Kecamatan Ubud, Kabupaten Gi)

№14  bridging_request_letter__default       НА ПЕРЕДЕЛКУ (1)
   лишних блоков в шаблоне: 1 (первые: {{signatory_name}})

№18  employment_contract__default           НА ПЕРЕДЕЛКУ (3)
   стр1 y=266: выходит за поле (x 519..595) — 'Moscow, Russia'
   стр1 y=277: выходит за поле (x 460..570) — '01 September 2025'
   нет места в шаблоне для 4 строк примера (первые: Linguamarina, Inc.,  a Gener; S tart Date:  01   September; P a ss port: 76 3655709)
```
