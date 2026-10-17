"""Что за документы приходят от клиентов и куда они идут в нашей работе.

Смотрит только имена файлов (быстро, весь архив), группирует по смыслу
и показывает, какие переменные система берёт из каждого типа.

Запуск: python3 scripts/inventory_client_docs.py [--all]
"""
import collections
import re
import sys
from pathlib import Path

CACHE = Path('/opt/wolf_v2/data/gdrive_cache')

# смысловой тип → признаки в имени файла → что из него берём и куда применяем
TYPES = [
    ("паспорт", ("паспорт", "passport", "загран"),
     "номер, срок, дата выдачи, кем выдан, дата и место рождения, гражданство → все документы"),
    ("карточка ВНЖ / ITK", ("itk", "kitas", "kitas", "itap", "stay permit", "внж"),
     "номер и срок ВНЖ, номер паспорта, дата рождения, гражданство, адрес в Индонезии → письма, E-02, продление"),
    ("виза / bridging", ("visa", "виза", "bridging", "b211", "e33g", "c1", "ковид"),
     "номер и срок визы → письма, E-02, заявление на продление"),
    ("справка банка об остатке", ("bankstatement", "bank statement", "bank_statement", "остатке",
                                  "balance", "personalbank", "personal bank", "справка о доступном"),
     "банк, счёт, остаток, сумма прописью, маска карты, период, номер документа → справки Т-Банк/Сбер"),
    ("выписка о движении средств", ("movement", "движение", "funds", "выписк"),
     "период, обороты, поступления, крупные поступления, контрагенты → справка о движении, подтверждение дохода"),
    ("свидетельство о браке/рождении", ("marriage", "birth", "свидетельств", "брак", "рожден"),
     "состав семьи → анкеты, письма (пока вручную)"),
    ("документы о компании", ("incorporation", "incumbency", "certificate", "business", "регистрац",
                              "company", "ltd", "llc"),
     "название, ИНН, директор, адрес компании → договоры, письма (работодатель)"),
    ("трудовой договор / офер", ("employment", "agreement", "contract", "offer", "договор", "трудовой"),
     "должность, оклад, дата, организация → наш договор (Remote Work / Employment)"),
    ("диплом / образование", ("diploma", "degree", "education", "диплом", "образован", "bachelor", "master"),
     "учебное заведение, специальность, год → резюме"),
    ("резюме / CV", ("resume", "cv", "резюме"),
     "опыт, навыки, образование, языки → резюме"),
    ("фотография клиента", ("foto", "photo", "фото", "img_", "img-", "wp_"),
     "фото на документы — в текст документов не идёт"),
    ("справка с работы / 2-НДФЛ", ("ндфл", "2ndfl", "income", "доход", "salary", "справка с работы", "зарплат"),
     "доход, работодатель → подтверждение дохода"),
    ("анкета / заявление клиента", ("form", "анкета", "заявление", "application", "questionnaire"),
     "контактные данные, состав семьи, цель поездки → карточка, письма"),
    ("квитанции / чеки", ("receipt", "квитанц", "чек", "invoice", "payment"),
     "оплаты — в документы не идут, в карточку как отметка"),
    ("перевод / нотариат", ("translation", "перевод", "notari", "апостиль", "apostille"),
     "переводы документов — источник текста, если основного нет"),
]


def main() -> None:
    show_all = '--all' in sys.argv
    folders = sorted(CACHE.glob('client_*'), key=lambda p: int(p.name.split('_')[1]))

    hits = collections.defaultdict(lambda: {"files": 0, "clients": set(), "examples": []})
    other = collections.defaultdict(lambda: {"files": 0, "clients": set(), "examples": []})

    for folder in folders:
        cid = int(folder.name.split('_')[1])
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            low = f.name.lower()
            matched = False
            for title, keys, _use in TYPES:
                if any(k in low for k in keys):
                    h = hits[title]
                    h["files"] += 1
                    h["clients"].add(cid)
                    if len(h["examples"]) < 3 and f.name[:40] not in h["examples"]:
                        h["examples"].append(f.name[:40])
                    matched = True
                    break
            if not matched:
                key = re.sub(r'[\d_\-\.]+', ' ', f.name.lower()).strip()[:26] or '(без имени)'
                o = other[key]
                o["files"] += 1
                o["clients"].add(cid)
                if len(o["examples"]) < 2:
                    o["examples"].append(f.name[:40])

    print('=== типы документов в архиве (%d клиентов) ===' % len(folders))
    for title, keys, use in TYPES:
        h = hits[title]
        if not h["files"]:
            print('\n%-32s НЕТ ФАЙЛОВ' % title)
            continue
        print('\n%-32s файлов %-4d  у %d клиентов' % (title, h["files"], len(h["clients"])))
        print('   берём: %s' % use)
        print('   примеры: %s' % '; '.join(h["examples"]))

    print('\n=== что не попало в типы (по частоте) ===')
    for key, o in sorted(other.items(), key=lambda kv: -kv[1]["files"])[:20]:
        print('   %-28s файлов %-3d у %d  пример: %s' % (key, o["files"], len(o["clients"]),
                                                         o["examples"][0] if o["examples"] else ''))
    if show_all:
        print('\nвсе прочие ключи:', ', '.join(sorted(other)))


if __name__ == '__main__':
    main()
