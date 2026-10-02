"""Пул российских адресов и генератор адреса для банковских документов.

Задача: если реального адреса клиента нет ни в заявке, ни в прикреплённых
документах — собрать корректный адрес в России самому.

Порядок работы (см. resolve_address):
  1) реальный российский адрес клиента  -> используем как есть;
  2) известен только город (место рождения, кем выдан паспорт, текст
     документов)                         -> берём ЭТОТ город;
  3) нет даже города                      -> берём город из пула.

Улица, дом и квартира подбираются детерминированно по seed: у одного
клиента один адрес, и он не меняется между запусками.

Формат записи повторяет архивные бланки банковских выписок:
    <индекс>, <город> [, <край/область>], Ul <улица> , D. <дом>, Kv. <квартира>

Границы значений взяты из статистики архивных документов
(/root/.hermes/cache/scratch/addr_analysis.py, 35 адресов):
  - дома в реальных справках: 1..15 (медиана ~7), максимум 144;
  - квартиры: почти все <= 90, единичные выбросы 315..749.
Для генерации берём осмысленный диапазон: дом 1..20, квартира 1..100.
"""
from __future__ import annotations

import hashlib
import random
import re

# ── Пул городов: индекс-префикс, транслит названия, область/край, центральные улицы ──
# Улицы — реальные, в центре города. Транслит в стиле архивных справок.
CITIES = [
    {
        "name": "Moscow", "region": "", "zip": (101000, 129999),
        "streets": ["Tverskaya Ul", "Arbat Ul", "Nikolskaya Ul", "Petrovka Ul",
                    "Myasnitskaya Ul", "Pokrovka Ul", "Prechistenka Ul", "Ostozhenka Ul",
                    "Kuznetskiy Most Ul", "Neglinnaya Ul", "Maroseyka Ul", "Sretenka Ul",
                    "Rozhdestvenka Ul", "Znamenka Ul", "Vozdvizhenka Ul",
                    "Bolshaya Dmitrovka Ul", "Malaya Dmitrovka Ul", "Lubyanskiy Proezd",
                    "Kamergerskiy Pereulok", "Stoleshnikov Pereulok", "Bolshaya Lubyanka Ul",
                    "Solyanka Ul", "Varvarka Ul", "Ilyinka Ul", "Tverskaya-Yamskaya Ul",
                    "Sadovaya-Kudrinskaya Ul", "Zubovskiy Bulvar", "Gogolevskiy Bulvar"],
    },
    {
        "name": "Saint Petersburg", "region": "", "zip": (190000, 199999),
        "streets": ["Nevskiy Prospekt", "Bolshaya Konyushennaya Ul", "Malaya Morskaya Ul",
                    "Bolshaya Morskaya Ul", "Gorokhovaya Ul", "Sadovaya Ul",
                    "Italianskaya Ul", "Karavannaya Ul", "Liteyniy Prospekt",
                    "Vladimirskiy Prospekt", "Zagorodnyy Prospekt", "Razezzhaya Ul",
                    "Pushkinskaya Ul", "Ul Marata", "Ul Zhukovskogo", "Ul Pestelya",
                    "Naberezhnaya Reki Fontanki", "Naberezhnaya Reki Moyki",
                    "Naberezhnaya Kanala Griboyedova", "Ul Rubinshteyna",
                    "Kirochnaya Ul", "Ul Nekrasova", "Mokhovaya Ul", "Ul Belinskogo"],
    },
    {
        "name": "Novosibirsk", "region": "Novosibirskaya Obl", "zip": (630000, 630099),
        "streets": ["Krasnyy Prospekt", "Ul Lenina", "Ul Kirova", "Ul Gorkogo",
                    "Ul Sovetskaya", "Ul Frunze", "Ul Kommunisticheskaya", "Ul Michurina",
                    "Ul Shamshurina", "Ul Ordzhonikidze", "Ul CLIENTova", "Ul Gogolya",
                    "Ul Chaplygina", "Ul Kamenskaya", "Ul Serebrennikovskaya",
                    "Ul CLIENTa Gorkogo", "Ul Dostoevskogo", "Ul Narymskaya"],
    },
    {
        "name": "Yekaterinburg", "region": "Sverdlovskaya Obl", "zip": (620000, 620099),
        "streets": ["Prospekt Lenina", "Ul Malysheva", "Ul Lenina", "Ul Mira",
                    "Ul Pushkina", "Ul Karla Libknekhta", "Ul Gogolya", "Ul Kuybysheva",
                    "Ul Turgeneva", "Ul Belinskogo", "Ul Dekabristov", "Ul Sacco i Vanzetti",
                    "Ul Marksa", "Ul Krylova", "Ul Gorkogo", "Ul Vaynera",
                    "Ul Radishcheva", "Ul Pervomayskaya"],
    },
    {
        "name": "Kazan", "region": "Respublika Tatarstan", "zip": (420000, 420099),
        "streets": ["Ul Baumana", "Ul Kremlyovskaya", "Ul Pushkina", "Ul Ostrovskogo",
                    "Ul Profsoyuznaya", "Ul Dostoevskogo", "Ul Universitetskaya",
                    "Ul Karla Marksa", "Ul Butlerova", "Ul Shchapova", "Ul Gogolya",
                    "Ul Zhukovskogo", "Ul CLIENTa Gorkogo", "Ul Kavi Nadzhmi",
                    "Ul Telmana", "Ul Spartakovskaya", "Ul Ershova"],
    },
    {
        "name": "Nizhny Novgorod", "region": "Nizhegorodskaya Obl", "zip": (603000, 603099),
        "streets": ["Ul Bolshaya Pokrovskaya", "Ul Rozhdestvenskaya", "Ul Varvarskaya",
                    "Ul Alekseevskaya", "Ul Piskunova", "Ul Ulyanova", "Ul Minina",
                    "Ul Pochainskaya", "Ul Zvezdinka", "Ul Kovalikhinskaya",
                    "Ul Sovetskaya", "Ul Belinskogo", "Ul Ulyanova", "Ul Gruzinskaya"],
    },
    {
        "name": "Chelyabinsk", "region": "Chelyabinskaya Obl", "zip": (454000, 454099),
        "streets": ["Ul Kirova", "Prospekt Lenina", "Ul Kommuny", "Ul Vorovskogo",
                    "Ul Truda", "Ul Pushkina", "Ul Tsvillinga", "Ul Krasnaya",
                    "Ul Karla Marksa", "Ul Entuziastov", "Ul Molodogvardeytsev",
                    "Ul Soboleva", "Ul Elizavety", "Ul Krasnoarmeyskaya"],
    },
    {
        "name": "Samara", "region": "Samarskaya Obl", "zip": (443000, 443099),
        "streets": ["Ul Kuybysheva", "Ul Lenina", "Ul Voronezhskaya", "Ul Sadovaya",
                    "Ul Chapaevskaya", "Ul Frunze", "Ul Molodogvardeyskaya",
                    "Ul Leningradskaya", "Ul Galaktionovskaya", "Ul Ulyanovskaya",
                    "Ul Krasnoarmeyskaya", "Ul Vilonovskaya", "Ul Novo-Sadovaya"],
    },
    {
        "name": "Omsk", "region": "Omskaya Obl", "zip": (644000, 644099),
        "streets": ["Ul Lenina", "Prospekt Marksa", "Ul Gagarina", "Ul Internatsionalnaya",
                    "Ul K Marxa", "Ul Mire", "Ul Pushkina", "Ul Uchebnaya",
                    "Ul Ordzonikidze", "Ul Zhukova", "Ul Bulatova", "Ul Komarova"],
    },
    {
        "name": "Rostov-na-Donu", "region": "Rostovskaya Obl", "zip": (344000, 344099),
        "streets": ["Bolshaya Sadovaya Ul", "Ul Sadovaya", "Prospekt Voroshilovskiy",
                    "Ul Pushkinskaya", "Ul Krasnoarmeyskaya", "Ul Sokolova",
                    "Ul Budennovskiy", "Ul Shaumyana", "Ul Gazetnyy", "Ul CLIENTa Gorkogo",
                    "Ul Ulyanovskaya", "Ul Temernitskaya"],
    },
    {
        "name": "Ufa", "region": "Respublika Bashkortostan", "zip": (450000, 450099),
        "streets": ["Prospekt Oktyabrya", "Ul Lenina", "Ul Pushkina", "Ul Kommunisticheskaya",
                    "Ul Zaki Validi", "Ul Gogolya", "Ul Aksakova", "Ul Revolyutsionnaya",
                    "Ul Karla Marksa", "Ul Tsyurupy", "Ul Mustaya Karima", "Ul Dostoevskogo"],
    },
    {
        "name": "Krasnoyarsk", "region": "Krasnoyarskiy Krai", "zip": (660000, 660099),
        "streets": ["Prospekt Mira", "Ul Lenina", "Ul Kirova", "Ul Marksa",
                    "Ul Dubrovinskogo", "Ul Karla Marksa", "Ul Perekalskogo",
                    "Ul Uritskogo", "Ul Bograda", "Ul Mira", "Ul Gorkogo", "Ul Sukhacheva"],
    },
    {
        "name": "Voronezh", "region": "Voronezhskaya Obl", "zip": (394000, 394099),
        "streets": ["Prospekt Revolyutsii", "Ul Kirova", "Ul Plekhanovskaya",
                    "Ul Pushkinskaya", "Ul Karla Marksa", "Ul Nikitinskaya",
                    "Ul Fedora Engelsa", "Ul Teatralnaya", "Ul Srednemoskovskaya",
                    "Ul Koltsovskaya", "Ul Ordzhonikidze", "Ul Kommunarov"],
    },
    {
        "name": "Perm", "region": "Permskiy Kray", "zip": (614000, 614099),
        "streets": ["Komsomolskiy Prospekt", "Ul Lenina", "Ul Sibirskaya",
                    "Ul Petropavlovskaya", "Ul Komsomolskiy", "Ul Pushkina",
                    "Ul Lunacharskogo", "Ul CLIENTa Gorkogo", "Ul Ordzhonikidze",
                    "Ul Borchaninova", "Ul Kirova", "Ul Ekaterininskaya"],
    },
    {
        "name": "Volgograd", "region": "Volgogradskaya Obl", "zip": (400000, 400099),
        "streets": ["Prospekt Lenina", "Ul Mira", "Ul Volodarskogo", "Ul Gogolya",
                    "Ul Kommunisticheskaya", "Ul Chapaeva", "Ul Krasnoznamenskaya",
                    "Ul Sovetskaya", "Ul Pushkina", "Ul Raboche-Krestyanskaya",
                    "Ul Proletarskaya", "Ul Kalinina"],
    },
    {
        "name": "Krasnodar", "region": "Krasnodarskiy Krai", "zip": (350000, 350099),
        "streets": ["Ul Krasnaya", "Ul Krasnoarmeyskaya", "Ul Severnaya", "Ul Gorkogo",
                    "Ul Mira", "Ul Stavropolskaya", "Ul Oktyabrskaya", "Ul Lenina",
                    "Ul Kommunarov", "Ul Pushkina", "Ul Rashpilevskaya", "Ul Budennogo"],
    },
    {
        "name": "Saratov", "region": "Saratovskaya Obl", "zip": (410000, 410099),
        "streets": ["Prospekt Stolypina", "Ul Moskovskaya", "Ul Kirova", "Ul Volskaya",
                    "Ul Chaplina", "Ul Radishcheva", "Ul Gorkogo", "Ul Sacco i Vanzetti",
                    "Ul Universitetskaya", "Ul Mironova", "Ul Pervomayskaya"],
    },
    {
        "name": "Tyumen", "region": "Tyumenskaya Obl", "zip": (625000, 625099),
        "streets": ["Ul Respubliki", "Ul Lenina", "Ul Pervomayskaya", "Ul Kirova",
                    "Ul Vodoprovodnaya", "Ul Ordzhonikidze", "Ul Volodarskogo",
                    "Ul Chelyuskintsev", "Ul Melnikaite", "Ul Dzerzhinskogo",
                    "Ul Tsvillinga", "Ul Gogolya"],
    },
    {
        "name": "Irkutsk", "region": "Irkutskaya Obl", "zip": (664000, 664099),
        "streets": ["Ul Lenina", "Ul Karla Marksa", "Ul Uritskogo", "Ul Kirova",
                    "Ul Dekabrskikh Sobytiy", "Ul Mira", "Ul Frunze", "Ul Sukhbaatora",
                    "Ul Zhelyabova", "Ul Gorkogo", "Ul Babushkina", "Ul Lapina"],
    },
    {
        "name": "Khabarovsk", "region": "Khabarovskiy Krai", "zip": (680000, 680099),
        "streets": ["Ul Muravyova-Amurskogo", "Ul Lenina", "Ul Karla Marksa",
                    "Ul Pushkina", "Ul Gogolya", "Ul Turgeneva", "Ul Komsomolskaya",
                    "Ul Frunze", "Ul Serysheva", "Ul Dzerzhinskogo", "Ul Sheronova"],
    },
    {
        "name": "Vladivostok", "region": "Primorskiy Kray", "zip": (690000, 690099),
        "streets": ["Ul Svetlanskaya", "Ul Aleutskaya", "Ul Admirala Fokina",
                    "Ul Pushkinskaya", "Ul Uborevicha", "Ul Postysheva",
                    "Ul Pogranichnaya", "Ul Verkhneportovaya", "Ul Okeanskiy Prospekt"],
    },
    {
        "name": "Kaliningrad", "region": "Kaliningradskaya Obl", "zip": (236000, 236099),
        "streets": ["Prospekt Mira", "Ul Leninskiy", "Ul Teatralnaya", "Ul Chernyakhovskogo",
                    "Ul Klinicheskaya", "Ul Gorkogo", "Ul Shevchenko", "Ul Zoologicheskaya",
                    "Ul Moskovskiy Prospekt", "Ul Frunze"],
    },
    {
        "name": "Sochi", "region": "Krasnodarskiy Krai", "zip": (354000, 354099),
        "streets": ["Ul Navaginskaya", "Ul Morskaya", "Ul Kurortnyy Prospekt",
                    "Ul Vorovskogo", "Ul Moskvina", "Ul Ordzhonikidze",
                    "Ul Gorkogo", "Ul Pushkinskaya", "Ul Teatralnaya"],
    },
    {
        "name": "Tula", "region": "Tulskaya Obl", "zip": (300000, 300099),
        "streets": ["Prospekt Lenina", "Ul Metallistov", "Ul Sovetskaya",
                    "Ul Mendeleevskaya", "Ul Pervomayskaya", "Ul Komsomolskaya",
                    "Ul Lenina", "Ul Touristskaya", "Ul Svobody"],
    },
    {
        "name": "Yaroslavl", "region": "Yaroslavskaya Obl", "zip": (150000, 150099),
        "streets": ["Ul Svobody", "Ul Pervomayskaya", "Ul Respublikanskaya",
                    "Ul Komsomolskaya", "Ul Andropova", "Ul Trefoleva",
                    "Ul Sovetskaya", "Ul Volzhskaya Naberezhnaya", "Ul Deputatskaya"],
    },
    {
        "name": "Penza", "region": "Penzenskaya Obl", "zip": (440000, 440099),
        "streets": ["Ul Moskovskaya", "Ul Kirova", "Ul Lenina", "Ul Bakunina",
                    "Ul Volodarskogo", "Ul Pushkina", "Ul Sura", "Ul Kuprina",
                    "Ul Krasnaya", "Ul Uritskogo", "Ul Chkalova", "Ul Marksa"],
    },
    {
        "name": "Petrozavodsk", "region": "Respublika Kareliya", "zip": (185000, 185099),
        "streets": ["Prospekt Lenina", "Ul Kirova", "Ul Pushkinskaya", "Ul Gogolya",
                    "Ul Engelsa", "Ul Marata", "Ul Antikaynena", "Ul Kirova",
                    "Ul Proletarskaya", "Ul Chapaeva", "Ul Nevskogo"],
    },
    {
        "name": "Stavropol", "region": "Stavropolskiy Kray", "zip": (355000, 355099),
        "streets": ["Prospekt Karla Marksa", "Ul Lenina", "Ul Mira", "Ul Dovatortsev",
                    "Ul Pushkina", "Ul Sovetskaya", "Ul Morozova", "Ul CLIENTa",
                    "Ul Kominterna", "Ul Lermontova", "Ul Serova"],
    },
    {
        "name": "Orenburg", "region": "Orenburgskaya Obl", "zip": (460000, 460099),
        "streets": ["Ul Sovetskaya", "Ul Kirova", "Ul Leninskaya", "Ul Pushkinskaya",
                    "Ul Krasnoznamennaya", "Ul Pravdy", "Ul Volodarskogo",
                    "Ul Komsomolskaya", "Ul Chicherina", "Ul Proletarskaya"],
    },
    {
        "name": "Achinsk", "region": "Krasnoyarskiy Krai", "zip": (662150, 662169),
        "streets": ["Ul Lenina", "Ul Kirova", "Ul Kravchenko", "Ul Karla Marksa",
                    "Ul Sovetskaya", "Ul Gagarina", "Ul Pionerskaya", "Ul Mira"],
    },
    {
        "name": "Ramenskoe", "region": "Moskovskaya Obl", "zip": (140100, 140109),
        "streets": ["Ul Solnechnaya", "Ul Kirova", "Ul Lenina", "Ul Krasnoarmeyskaya",
                    "Ul Mikhalevicha", "Ul Rabochaya", "Ul Pushkina", "Ul Sadovaya"],
    },
]

# «USSR», «Russia», пусто, иностранный город — город определить нельзя
_NO_CITY = {"ussr", "russia", "russian", "rf", "россия", "", "none", "null"}

# транслит для городов, которых нет в пуле, но которые пишут в анкетах
CITY_ALIASES = {
    "moskva": "Moscow", "мосkva": "Moscow", "moscow": "Moscow", "москва": "Moscow",
    "st petersburg": "Saint Petersburg", "saint petersburg": "Saint Petersburg",
    "spb": "Saint Petersburg", "petersburg": "Saint Petersburg", "ленинград": "Saint Petersburg",
    "nizhny novgorod": "Nizhny Novgorod", "nizhniy novgorod": "Nizhny Novgorod",
    "nizhny": "Nizhny Novgorod", "nizhniy": "Nizhny Novgorod",
    "yekaterinburg": "Yekaterinburg", "ekaterinburg": "Yekaterinburg",
    "rostov": "Rostov-na-Donu", "rostov-na-donu": "Rostov-na-Donu",
    "kuibyshev": "Samara", "kuybyshev": "Samara", "krasnodar": "Krasnodar",
    "petrozavodsk": "Petrozavodsk", "kareliya": "Petrozavodsk", "karelia": "Petrozavodsk",
    "penza": "Penza", "penzenskaya": "Penza", "penzenskaya obl": "Penza",
    "samarskaya": "Samara", "samara obl": "Samara", "krasnoyarskii krai": "Krasnoyarsk",
    "krasnoyarsk": "Krasnoyarsk", "krasnoyarskii": "Krasnoyarsk",
    "perm region": "Perm", "permskiy": "Perm", "perm": "Perm", "perm krai": "Perm",
    "stavropol": "Stavropol", "stavropolskiy": "Stavropol",
    "orenburg": "Orenburg", "orenburgskaya": "Orenburg",
    "moskovskaya": "Moscow", "moskovskaya obl": "Moscow", "moskva g": "Moscow",
    "leningradskaya": "Saint Petersburg", "leningrad": "Saint Petersburg",
    "chelyabinskaya": "Chelyabinsk", "nizhegorodskaya": "Nizhny Novgorod",
    "kazan": "Kazan", "tatarstan": "Kazan", "bashkortostan": "Ufa",
    "ufa": "Ufa", "achinsk": "Achinsk", "ramenskoe": "Ramenskoe",
    "amur oblast": "Khabarovsk", "rostovskaya": "Rostov-na-Donu",
}


def _city_entry(name: str):
    """Находит город в пуле (по имени или алиасу)."""
    if not name:
        return None
    key = str(name).strip().lower()
    if key in CITY_ALIASES:
        key = CITY_ALIASES[key].lower()
    for c in CITIES:
        if c["name"].lower() == key:
            return c
    for c in CITIES:                      # частичное совпадение: «Moscow g», «Moscow, Russia»
        if key.CLIENTswith(c["name"].lower()):
            return c
    return None


def detect_city(*sources) -> str:
    """Пытается определить город клиента по любому тексту (место рождения, адрес, документы)."""
    for s in sources:
        if not s:
            continue
        text = str(s)
        low = text.strip().lower()
        if low in _NO_CITY:
            continue
        ent = _city_entry(text)
        if ent:
            return ent["name"]
        m = re.search(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", text)
        if m:
            ent = _city_entry(m.group(1))
            if ent:
                return ent["name"]
    return ""


def generate_address(seed, city: str | None = None) -> dict:
    """Адрес в России по seed. Один и тот же seed -> один и тот же адрес.

    Возвращает: {"address": строка в формате справки, "city": город, "generated": True}
    """
    key = str(seed or "wolf")
    rnd = random.Random("addr-" + key)
    entry = _city_entry(city) if city else None
    if not entry:
        entry = rnd.choice(CITIES)

    street = rnd.choice(entry["streets"])
    house = rnd.randint(1, 20)            # по статистике архивных справок: медиана ~7
    flat = rnd.randint(1, 100)            # верхняя граница — требование заказчика
    zip_code = rnd.randint(entry["zip"][0], entry["zip"][0] + 99)
    region = entry["region"]

    if entry["name"] == "Moscow":
        addr = f"{zip_code}, Moscow, {street} , D. {house}, Kv. {flat}"
    elif region:
        addr = f"{zip_code}, {region}, G {entry['name']}, {street} , D. {house}, Kv. {flat}"
    else:
        addr = f"{zip_code}, {entry['name']}, {street} , D. {house}, Kv. {flat}"

    return {"address": addr, "city": entry["name"], "generated": True}


def resolve_address(seed, real_address: str = "", city_hint: str = "") -> dict:
    """Главная функция: реальный адрес -> адрес по городу клиента -> случайный город."""
    from CLIENT.doc_parse import is_russian_address

    if real_address and is_russian_address(real_address):
        return {"address": str(real_address).strip(), "city": detect_city(real_address),
                "generated": False}

    city = detect_city(city_hint, real_address)
    return generate_address(seed, city or None)
