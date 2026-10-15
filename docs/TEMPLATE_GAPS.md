# Сверка шаблонов с оригинальными примерами (по строкам)

Дата: 06.10.2026 09:50

Обозначения: «нет в HTML» — строка образца без пары в шаблоне (обычно данные клиента внутри переменной), «лишнее» — блок шаблона без пары в образце.
```

=== №1 bank_statement_3m__tbank
    блоков: HTML=19, пример=19 (строк с текстом)
    нет в HTML: 0
    лишнее в HTML: 0

=== №2 bank_statement_3m__sber
    блоков: HTML=14, пример=14 (строк с текстом)
    нет в HTML: 1
       top=54.2    кегль=12.0  '19 VAVILOVA ST., MOSCOW, 117312, SBERBANK'
    лишнее в HTML: 0

=== №3 bank_statement_12m__tbank
    блоков: HTML=18, пример=18 (строк с текстом)
    нет в HTML: 0
    лишнее в HTML: 0

=== №4 bank_statement_12m__sber
    блоков: HTML=14, пример=14 (строк с текстом)
    нет в HTML: 1
       top=54.2    кегль=12.0  '19 VAVILOVA ST., MOSCOW, 117312, SBERBANK'
    лишнее в HTML: 0

=== №7 cv__format_CLIENT
    блоков: HTML=20, пример=31 (строк с текстом)
    нет в HTML: 11
       top=156.5   кегль=10.08 'Experienced in managing company operations, business'
       top=168.0   кегль=10.08 'team leadership. Works fully remotely and independen'
       top=251.3   кегль=10.08 'objectives.'
       top=264.7   кегль=10.08 "•  Developing and implementing the Company's busines"
       top=278.2   кегль=10.08 '•  Overseeing sales, procurement, supply chain and c'
       top=289.4   кегль=10.08 'suppliers.'
    лишнее в HTML: 0

=== №8 d12_cover_letter__default
    блоков: HTML=60, пример=59 (строк с текстом)
    нет в HTML: 0
    лишнее в HTML: 0

=== №9 statement_letter_e02__default
    блоков: HTML=59, пример=58 (строк с текстом)
    нет в HTML: 1
       top=663.1   кегль=12.0  'untrue, then I am willing to be charged under the pr'
    лишнее в HTML: 1
       top=674.0   кегль=9.5   var=place                  '{{place}}, {{doc_date}}'

=== №11 remote_work_agreement__default
    блоков: HTML=92, пример=77 (строк с текстом)
    нет в HTML: 2
       top=52.3    кегль=10.08 'Payments shall be made via international bank transf'
       top=274.8   кегль=10.08 'jurisdiction, and shall not be considered an employe'
    лишнее в HTML: 10
       top=618.0   кегль=9.81  var=term_end_date          'remai nvalid until {{ term_end_date }}, '
       top=617.76  кегль=9.81  var=term_end_date          'remai nvalid until {{ term_end_date }}, '
       top=721.2   кегль=9.81  var=employee_name          'Name: {{ employee_name }}'
       top=732.72  кегль=10.08 var=passport_number        'Passport: {{ passport_number }}, valid u'
       top=232.08  кегль=9.0   var=company_incorporated_phrase '{{ company_incorporated_phrase }}'
       top=337.1   кегль=10.08 var=place_of_birth         'Birth :{{ place_of_birth }}, (here inaft'

=== №13 conversion_request_letter__default
    блоков: HTML=60, пример=62 (строк с текстом)
    нет в HTML: 2
       top=416.7   кегль=10.5  'kami dengan data sebagai berikut:'
       top=594.5   кегль=10.0  'Kecamatan Ubud, Kabupaten Gianyar, Bali 80552'
    лишнее в HTML: 0

=== №14 bridging_request_letter__default
    блоков: HTML=61, пример=60 (строк с текстом)
    нет в HTML: 0
    лишнее в HTML: 1
       top=724.0   кегль=10.5  var=signatory_name         '{{signatory_name}}'

=== №18 employment_contract__default
    блоков: HTML=93, пример=91 (строк с текстом)
    нет в HTML: 1
       top=407.0   кегль=11.04 'Russian Federation, Place of Birth: Stavropolsky Kra'
    лишнее в HTML: 1
       top=757.11  кегль=11.7  var=term_end_date          '{{term_end_date}}'
```
