# Реальный комплект Bridging — фото от Андрея 05.10.2026 (клиент Anna CLIENT)

Источник: 10 фотографий реально поданных документов (эта папка, `1.jpg` … `10.jpg`).
Задача этого файла — быть справочником для шаблонов: как выглядят настоящие документы,
что заполняется синим, а что делается руками.

## Состав комплекта

1. **Permohonan** — письмо в Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai,
   Nomor `60/PTAPB-SP/02.10.2026`, Hal: Permohonan Bridging Visa 60 Hari.
   Подпись + печать PT Alpha Prime Bali. (`3.jpg`)
2. **Surat Kuasa** — доверенность: Bartosz Pawel Nafalski (Director PT Alpha Prime Bali,
   Poland) → Marcellena Nirmala Chrisma Moeri (NIK `5171015403930001`), Badung, 2 October 2026.
   (`4.jpg`–`10.jpg`, страница 1)
3. **Surat Permintaan dan Jaminan** — заявление и гарантия от Marcellena Nirmala Chrisma Moeri
   (гражданка Индонезии, NIK `5171015403930001`) по клиенту. **Требует марку METERAI + подпись.**
   (`2.jpg`, и низ страниц `4.jpg`–`10.jpg`)
4. **FORM E-02 — Statement Letter** — заявление клиента. **Значения вписываются СИНИМ цветом
   ПЕЧАТНЫМИ (заглавными) буквами. Требует марку METERAI и подпись от руки.** (`1.jpg`)

## Значения формы E-02 из подлинника (Anna CLIENT)

- Full Name: `ANNA CLIENT`
- Place, Date of Birth: `USSR, 15-04-1973`
- Nationality: `RUSSIA`
- Occupation: пусто (это норма, не ошибка)
- Passport Number: `552025444`
- Date of Issue: `13-01-2026`, Date of Expiry: `13-01-2036`
- Stay Permit Number: `B12E21E1094928-C`
- Address in Indonesia: `JL. TEGAL SARI NO.25, TIBUBENENG, KUTA UTARA, BADUNG, BALI 80361`
- Phone Number: `00`
- Email: `CLIENT@alpha-prime.group`
- Existing Stay Permit: `VISIT STAY PERMIT (ITK), VALID UNTIL 05-10-2026`
- Guarantor: пусто
- Purpose of application: `VISA BRIDGING TO E33G`
- Stay Permit to be applied for: `BRIDGE`
- От руки: дата `07.10.2026`, подпись `Anna CLIENT`, наклеена марка METERAI 10 000

## Правила, которые из этого следуют

- Значения E-02 — **синим, заглавными буквами** (в шаблонах сделано: цвет `#1F4E79`,
  `text-transform:uppercase`; файлы `template.html.before_blue` — до правки).
- Форма E-02 бывает двух видов: старая «плоская» (значения чёрным, 18 pt — есть в архивном
  пакете, стр. 6) и актуальная с синей шапкой минuстерства и заголовком STATEMENT LETTER.
  У нас в шаблоне актуальная шапка уже есть — подложка `blocks/static/tpl_assets/4edcfc7fe9ad03a0.jpg`.
- Пустые Occupation и Guarantor — норма: в подлиннике они пустые.
- Ручные шаги (нельзя напечатать): марка METERAI + подпись — в E-02 и в Surat Permintaan dan
  Jaminan; в Permohonan и Surat Kuasa — печать PT и подпись, марки нет.

## Вопросы на согласование (вынести Андрею)

1. «И ещё одна синяя форма» — какая именно? В присланных фото синим заполнена только E-02.
2. Формулировка Purpose for conversion: в базе стоит длинная
   `Conversion of Bridging Visa to KITAS E33G`, а в подлинниках и в этом фото —
   `Visa Bridging to E33G`. Какую оставляем для конверсии?
3. Поле `stay_permit_to_be_applied_for`: в подлиннике мостовой `BRIDGE`, в базе пример
   подменён длинной формулировкой Purpose — надо развести.
