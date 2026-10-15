"""Сборка глобальной инструкции по пакетам документов для конструктора.

Читает:
  data/gCLIENT_archive/_kinds.json        — распознанные документы клиентов (тип по содержанию)
  /root/.hermes/cache/scratch/app_CLIENT_folder.json — связь заявка ↔ продукт ↔ папка
  /root/.hermes/cache/scratch/CLIENT_unique.json       — файлы с Диска (file_id → ссылка)
  data/wolf.db (CLIENT, CLIENT_CLIENT, CLIENT)

Пишет: docs/DOCUMENT_PACKS_GUIDE.md — продукт → обязательные документы, что даёт клиент,
что генерируем мы, реальные образцы со ссылками на Диск, состав клиентских папок.
"""
import collections
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')

ROOT = Path('/opt/wolf_v2')
OUT = ROOT / 'docs' / 'DOCUMENT_PACKS_GUIDE.md'
KINDS = ROOT / 'data' / 'gCLIENT_archive' / '_kinds.json'
LINKS = Path('/root/.hermes/cache/scratch/app_CLIENT_folder.json')
UNIQ = Path('/root/.hermes/cache/scratch/CLIENT_unique.json')

KIND_RU = {
    'BANK_STATEMENT': 'Справка банка об остатке', 'PHOTO': 'Фотография клиента',
    'PASSPORT': 'Паспорт клиента', 'REMOTE_WORK_AGREEMENT': 'Remote Work Agreement (наш договор)',
    'WORK_AGREEMENT': 'Work Agreement', 'EMPLOYMENT_AGREEMENT': 'Employment agreement',
    'ITK': 'Трудовая книжка (ИТК) — опционально', 'STAY_PERMIT_KITAS': 'KITAS / stay CLIENT',
    'MARRIAGE_CERT': 'Свидетельство о браке', 'BIRTH_CERT': 'Свидетельство о рождении',
    'COMMITMENT_LETTER': 'Commitment / guarantee letter (генерируем)',
    'CV': 'Резюме (генерируем)', 'FORM_E02': 'FORM E-02 (генерируем)',
    'PERMOHONAN': 'Permohonan — заявление (генерируем)',
    'SURAT_KUASA': 'Surat Kuasa — доверенность (генерируем)',
    'SURAT_PERMINTAAN_JAMINAN': 'Surat Permintaan dan Jaminan (генерируем)',
    'BRIDGING_LETTER': 'Письмо Bridging (генерируем)', 'CONVERSION_LETTER': 'Письмо Conversion (генерируем)',
    'D12_LETTER': 'Письмо D12 (генерируем)', 'SCREENSHOT': 'Скриншоты (переписка/подтверждения)',
    'ENGLISH_WORKSHEET': 'Учебные материалы (к делу не относятся)', 'KTP': 'KTP (индонезийский ID)',
    'FUNDS_MOVEMENT': 'Справка о движении средств', 'UNREADABLE': 'Без текстового слоя (скан/фото)',
    'OTHER': 'Прочее',
}
# клиентские (даёт клиент) и наши (генерируем) — по факту разбора папок
CLIENT_KINDS = {'BANK_STATEMENT', 'PHOTO', 'PASSPORT', 'ITK', 'STAY_PERMIT_KITAS',
                'MARRIAGE_CERT', 'BIRTH_CERT', 'KTP', 'FUNDS_MOVEMENT', 'SCREENSHOT'}
OURS_KINDS = {'REMOTE_WORK_AGREEMENT', 'WORK_AGREEMENT', 'EMPLOYMENT_AGREEMENT', 'CV',
              'FORM_E02', 'PERMOHONAN', 'SURAT_KUASA', 'SURAT_PERMINTAAN_JAMINAN',
              'BRIDGING_LETTER', 'CONVERSION_LETTER', 'D12_LETTER', 'COMMITMENT_LETTER'}
# обязательные клиентские по продуктам (по разбору: справка/паспорт/фото — у всех)
REQUIRED_CLIENT = {
    'BRIDGING': ['BANK_STATEMENT', 'PASSPORT', 'PHOTO'],
    'CONV': ['BANK_STATEMENT', 'PASSPORT', 'PHOTO'],
    'C1': ['BANK_STATEMENT', 'PASSPORT', 'PHOTO'],
    'C1-EXT': ['BANK_STATEMENT', 'PASSPORT'],
    'D12': ['BANK_STATEMENT', 'PASSPORT', 'PHOTO'],
    'E33G-NEW': ['BANK_STATEMENT', 'PASSPORT', 'PHOTO'],
    'E33G-EXT': ['BANK_STATEMENT', 'PASSPORT', 'PHOTO'],
}


def main() -> int:
    kinds = json.loads(KINDS.read_text(encoding='utf-8'))
    uniq = json.loads(UNIQ.read_text(encoding='utf-8'))
    links = json.loads(LINKS.read_text(encoding='utf-8'))
    con = sqlite3.connect(str(ROOT / 'data' / 'wolf.db'))
    con.row_factory = sqlite3.Row
    prods = {r['id']: r['code'] for r in con.execute("SELECT id, code FROM CLIENT")}
    tpls = {r['id']: r['code'] for r in con.execute("SELECT id, code FROM CLIENT")}
    prod_tpl = collections.defaultdict(list)
    for r in con.execute("SELECT CLIENT_id, template_id, slot_code FROM CLIENT_CLIENT"):
        prod_tpl[prods.get(r['CLIENT_id'], '?')].append((tpls.get(r['template_id'], '?'), r['slot_code'] or ''))

    folder_prod = {}
    for l in links:
        if l.get('folder'):
            folder_prod.setdefault(l['folder'], set()).add(l['CLIENT'])
    by_client = collections.defaultdict(list)
    for k in kinds:
        by_client[k['client']].append(k)
    by_id = {f['id']: f for f in uniq}

    L = ['# Пакеты документов Wolf AutoDoc — глобальная инструкция', '']
    L.append('Построено по реальным папкам клиентов на Google Диске: **%d папок, %d документов** '
             '(распознаны по содержанию, а не по имени файла).' % (len(by_client), len(kinds)))
    L.append('На Диске ничего не изменялось — только чтение.')
    L.append('')
    L.append('## 1. Из чего состоит пакет: клиентское и наше')
    L.append('')
    cl = collections.Counter(); ours = collections.Counter()
    for k in kinds:
        if k['kind'] in CLIENT_KINDS: cl[k['kind']] += 1
        elif k['kind'] in OURS_KINDS: ours[k['kind']] += 1
    L.append('**Даёт клиент** (кладём в его папку на Диске):')
    for k, n in cl.most_common():
        L.append('- %s — %d файлов' % (KIND_RU.get(k, k), n))
    L.append('')
    L.append('**Генерируем мы**:')
    for k, n in ours.most_common():
        L.append('- %s — %d файлов' % (KIND_RU.get(k, k), n))
    L.append('')
    L.append('## 2. Продукт → обязательные документы')
    L.append('')
    for code in sorted(prod_tpl):
        docs = prod_tpl[code]
        L.append('### %s' % code)
        L.append('')
        L.append('Генерируем (по системе):')
        for tpl, slot in sorted(docs):
            L.append('- `%s` (%s)' % (tpl, slot or '—'))
        L.append('')
        need = REQUIRED_CLIENT.get(code) or []
        if need:
            L.append('Обязательно от клиента: ' + ', '.join(KIND_RU.get(x, x) for x in need))
        L.append('Опционально (встречается у части клиентов): трудовая книжка (ИТК), '
                 'свидетельство о браке, свидетельство о рождении, KITAS.')
        L.append('')
    # реальные составы папок
    L.append('## 3. Что реально лежит в папках клиентов')
    L.append('')
    L.append('| клиент | продукт | клиентские документы | наши документы |')
    L.append('|---|---|---|---|')
    for c, items in sorted(by_client.items(), key=lambda kv: -len(kv[1])):
        kinds_c = collections.Counter(i['kind'] for i in items)
        p = ', '.join(sorted(folder_prod.get(c, []))) or '—'
        cli = ', '.join('%s×%d' % (KIND_RU.get(k, k), n) for k, n in kinds_c.most_common() if k in CLIENT_KINDS) or '—'
        our = ', '.join('%s×%d' % (KIND_RU.get(k, k), n) for k, n in kinds_c.most_common() if k in OURS_KINDS) or '—'
        L.append('| %s | %s | %s | %s |' % (c, p, cli, our))
    L.append('')
    # образцы каждой группы со ссылками
    L.append('## 4. Реальные образцы по группам документов')
    L.append('')
    L.append('Ссылка на файл на Диске: `https://CLIENT.google.com/file/d/<id>/view`')
    L.append('')
    groups = collections.defaultdict(list)
    for k in kinds:
        if k['kind'] in ('UNREADABLE', 'OTHER'):
            continue
        groups[k['kind']].append(k)
    for kind, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        L.append('### %s (%d файлов)' % (KIND_RU.get(kind, kind), len(items)))
        L.append('')
        seen = set()
        for it in items:
            if it['client'] in seen:
                continue
            seen.add(it['client'])
            fid = next((f['id'] for f in uniq if f['client'] == it['client'] and f['name'] == it['name']), '')
            url = 'https://CLIENT.google.com/file/d/%s/view' % fid if fid else '—'
            L.append('-%s — `%s` — %s' % ('' if not url else '', it['client'], url) if False else
                     '- %s — %s' % (it['client'], url))
            if len(seen) >= 6:
                break
        L.append('')
    L.append('## 5. Проверка полноты пакета')
    L.append('')
    L.append('Реализовано в `CLIENT/pack_check.py`: по заявке берётся продукт, требуемые '
             'документы, статусы наших документов и клиентские документы (карточка + скан '
             'папки на Диске). Отчёт: прогресс, чего нет из нашего, чего нет от клиента.')
    L.append('')
    OUT.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('инструкция:', OUT, '| строк:', len(L))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
