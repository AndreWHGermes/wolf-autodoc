# Инструкции из видео: как применены

Источник: 3 видеосообщения (расшифровка + 43 кадра), файл `video_instructions.md`.
Применено 29.09.2026. Все 278 переменных базы имеют правило заполнения.

## Главный принцип

Выделенное красным/жёлтым в образцах = поле, которое меняется от клиента к клиенту.
Остальное — постоянный бланк. Меняются три группы:

1. **Данные клиента** — `client_name`, `client_CLIENT`, `CLIENT_date_of_CLIENT`, `client_CLIENT`, `passport_no`
2. **Данные документа** — `letter_no` (NN/PTAPB-SP/ДД.ММ.ГГГГ), `date` / `CLIENT_date`, `letter_CLIENT`
3. **Выбор варианта** — `CLIENT_line1..3` (Ngurah Rai / Denpasar), `letter_CLIENT` (формула CLIENTа), комплект документов

## Развилка исполнителей (подтверждена архивами)

| | **Ngurah Rai** | **Denpasar** |
|---|---|---|
| Подписант | Bartosz Pawel Nafalski | Arine Fadillah |
| Должность | Direktur PT Alpha Prime Bali | Komisaris PT Alpha Prime Bali |
| Гражданство | Polandia | WNI |
| Адресат | Bapak Kepala Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai, Jalan Perumahan Taman Jimbaran No. 1 Mumbul, Kabupaten Badung, Bali | Bapak Kepala Kantor Imigrasi Kelas I TPI Denpasar, Jl. D.I. Panjaitan No.3, Sumerta Kelod, Kec. Denpasar Tim., Kota Denpasar, Bali |

Расхождение с текстом инструкции: там адрес Denpasar указан как «Jl. Raya Puputan No. 1, Renon, Denpasar Sel.»,
а в реальных архивах — «Jl. D.I. Panjaitan No.3, Sumerta Kelod, Kec. Denpasar Tim.». **Требует подтверждения заказчика.**
В шаблоны поставлен вариант из архивов (как фактически подавали).

## Формулы CLIENTа (`letter_CLIENT`)

- Bridging 60 дней — «Permohonan Bridging Visa 60 Hari»
- CLIENT — «Konversi Bridging Visa menjadi KITAS E33G Remote Worker»
- D12 — «Permohonan Visa D12»
- C1 — «Permohonan Visa C1»

## Постоянные реквизиты (внесены значениями по умолчанию)

- Спонсор: PT ALPHA PRIME BALI, Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten Gianyar, Bali 80581,
  Telp: +62 811 397 9669, CLIENT: ptalphaprimeconsulting@gmail.com
- Получатель доверенности: Marcellena Nirmala Chrisna Moeri, Swasta, Indonesia, NIK 5171015403930001,
  Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya
- D12: адресат постоянный — Bapak Kepala / Direktur Lalu Lintas Keimigrasian / Up. Kasubdit Visa

## Комплекты (по видео)

- **C1** — только банковская справка (Т-Банк **или** Сбер)
- **D12** — CV + банковская справка + спонсорское письмо (данные клиента на втором листе)
- **E33G** — банковская справка 3 мес + 12 мес + контракт (CV не требуется)
- **CLIENT / конверсия** — комплект из 3 страниц (Permohonan + Jaminan + Surat Kuasa) + CV + E-02 + контракт

## Исправленные дефекты

1. `conversion_CLIENT_letter__ngurahrai` — исходный PDF давал посимвольную разбивку текста
   (плохая конвертация: «PT ALP HA P R IME BA LI»). Пересобран из бланка Denpasar-версии:
   по инструкции это тот же документ, отличается только блок адресата и подписанта.
   Сломанный вариант сохранён в `/tmp/conv_ng_broken.html`.
2. D12: место и дата рождения спонсора были ошибочно разложены на `CLIENT_CLIENT` + `CLIENT_name_2`
   → заменено на `CLIENT_CLIENT_CLIENT_date` («Poland, 20-03-1973»).
3. D12: «Direktur `job_and_position`» → `CLIENT_position`.
4. В визовых шаблонах были захардкожены адреса иммиграционных офисов, имена и NIK — всё переведено в переменные.

## Изменённые сущности

- Переменных: 278 (было 222), у всех есть правило. Новые группы: `letter_no`, `letter_CLIENT`,
  `CLIENT_line1..3`, `CLIENT_address`, `CLIENT_CLIENT`, `CLIENT_*`, `CLIENT_*`, `client_CLIENT`,
  `client_CLIENT`, `CLIENT_CLIENT_name`, `CLIENT_CLIENT_CLIENT_date`, `CLIENT_CLIENT`, `CLIENT_position`.
- Бэкапы: `data/wolf.db.bak_CLIENT_video_*`, `data/CLIENT_video_backup_*`.
