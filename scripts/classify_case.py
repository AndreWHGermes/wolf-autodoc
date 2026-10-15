#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Классификатор новой заявки: определяет группу пакета и выдаёт план сборки.

Использование:
    /usr/bin/python3 scripts/classify_case.py <папка с документами клиента>
    /usr/bin/python3 scripts/classify_case.py data/gdrive_cache/client_65

Зачем: новая заявка опознаётся по составу документов, и по группе сразу берётся
штатный план сборки (какие документы делать, какие поля откуда брать).
"""
import sys, re, pathlib
import pymupdf

PLANS = {
 'E33G (новый)': [
   'Remote Work Agreement (годовой доход ≥ 60 000 USD)',
   'Справка банка 12 мес (остаток ≥ 2 000 USD)',
   'CV (должность = должность в договоре = occupation в E-02)',
   'FORM E-02 (национальность RUSIA, телефон 00, email на домене агентства)',
   'Фото 4×6, страница паспорта со штампом, itinerary',
 ],
 'ITK → Bridging → E33G': [
   'Permohonan (письмо в иммиграцию, офис по адресу проживания)',
   'Surat Kuasa (доверенность) + Surat Permintaan dan Jaminan (METERAI)',
   'FORM E-02: цель «Visa Bridging to E33G», статус «Bridging»',
   'Remote Work Agreement, справка банка, CV',
   'Подача не позднее 3 дней до окончания ITK (практика — 7–25 дней)',
 ],
 'C1 / визит': [
   'Справка банка 3 мес (остаток ≥ 2 000 USD)',
   'Договор по документам клиента (удалёнка или трудовой)',
   'Письмо-гарантия спонсора, обратный билет (документ клиента)',
 ],
 'D12': [
   'Справка банка 3 мес (порог 5 000 USD — выше, чем у остальных!)',
   'Письмо-обложка D12, CV, itinerary',
   'Работа и доход в Индонезии запрещены, конверсия невозможна',
 ],
 'Семейный': [
   'Комплект на каждого члена семьи (паспорт, фото, справка)',
   'Свидетельство о браке / о рождении + перевод',
   'Statement of commitment от супруга',
 ],
}


def read(path):
    txt = []
    for f in sorted(pathlib.Path(path).rglob('*')):
        if f.is_file() and f.suffix.lower() == '.pdf':
            try:
                d = pymupdf.open(f)
                txt.append('\n'.join(p.get_text() for p in d))
            except Exception:
                pass
    return '\n'.join(txt), [f.name for f in pathlib.Path(path).rglob('*') if f.is_file()]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    p = sys.argv[1]
    blob, names = read(p)
    has = {
      'паспорт': any(re.search(r'passport|паспорт|загран', n, re.I) for n in names),
      'фото': any(re.search(r'photo|фото', n, re.I) for n in names),
      'статус': bool(re.search(r'PERMIT NUMBER|Visa No\.', blob)),
      'справка': bool(re.search(r'bank|personal|справка|bankstatement', ' '.join(names), re.I)),
      'договор': bool(re.search(r'REMOTE WORK AGREEMENT|EMPLOYMENT CONTRACT|INDEPENDENT CONTRACTOR', blob)),
      'резюме': any(re.search(r'resume|\bcv\b', n, re.I) for n in names),
      'письмо': bool(re.search(r'PT ALPHA PRIME BALI|SURAT PERMINTAAN', blob)),
      'E-02': bool(re.search(r'STATEMENT LETTER|FORM E-02', blob)),
      'семья': any(re.search(r'marriage|birth|pernikahan|kelahiran|свидетельств', n, re.I) for n in names),
    }
    z = {
      'stay_no': (re.search(r'PERMIT NUMBER\s*:?\s*([A-Z0-9-]{8,20})', blob) or
                  re.search(r'Visa No\.\s*:?\s*([A-Z0-9-]{8,20})', blob)),
      'office_addr': re.search(r'Address(?: in Indonesia)?[^:]*:?\s*([^\n]{12,90})', blob),
      'firm': re.search(r'\(?(LLC "[^"]+"|Linguamarina, Inc\.|XCL Education[^,]*|[A-Z][A-Za-z&.,\- ]{3,40}(?:Inc|LLC|Ltd)\.?)\)?, a (?:company|General Corporation)', blob),
      'position': re.search(r'(?:engages the Contractor as an?|position of)\s+([A-Z][A-Za-z /&+\-]{2,40}?)(?:\s+to provide|\s+and the Employee|,|\n)', blob),
      'balance': re.search(r'deposit balance is\s*([\d \u00a0,.]{5,20})\s*rubles', blob),
      'bridging': bool(re.search(r'Bridging', blob, re.I)),
      'd12': bool(re.search(r'\bD12\b', blob)),
    }
    yn = lambda b: 'есть' if b else 'НЕТ'
    print('ПАПКА:', p)
    print('СОСТАВ:', '  '.join('%s: %s' % (k, yn(v)) for k, v in has.items()))
    print('\nНАЙДЕННЫЕ ЗНАЧЕНИЯ:')
    for k, m in z.items():
        if m and not isinstance(m, bool):
            print('   %-14s %s' % (k, m.group(1).strip()[:80]))
    if z['bridging']:
        group = 'ITK → Bridging → E33G'
    elif z['d12']:
        group = 'D12'
    elif (z['stay_no'] and re.search(r'E33G|B12E2', z['stay_no'].group(1))) or (
            re.search(r'Limited Stay Visa', blob) and has['договор']):
        group = 'E33G (новый)'
    elif has['семья']:
        group = 'Семейный'
    elif has['договор'] and has['справка']:
        group = 'C1 / визит'
    else:
        group = 'не определена (мало документов)'
    print('\nГРУППА ЗАЯВКИ:', group)
    plan = PLANS.get(group)
    if plan:
        print('ПЛАН СБОРКИ:')
        for i, step in enumerate(plan, 1):
            print('   %d. %s' % (i, step))
    print('\nЧЕГО НЕ ХВАТАЕТ ДЛЯ ПОЛНОГО ПАКЕТА:',
          ', '.join(k for k, v in has.items() if not v and k in ('паспорт', 'фото', 'статус', 'справка', 'договор', 'резюме')) or 'всё есть')


if __name__ == '__main__':
    main()
