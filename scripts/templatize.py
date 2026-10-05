"""Подстановка переменных в HTML-шаблон, собранный из реального документа.

Меняет данные конкретного клиента (из поданного комплекта) на {{переменные}},
чтобы шаблон стал универсальным. Адрес иммиграционного офиса оставляется
статикой: у каждого офиса свой шаблон (Ngurah Rai / Denpasar / Tabanan).

Запуск:
    /usr/bin/python3 scripts/templatize.py <шаблон.html> [--apply]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# данные клиента из поданного документа → переменная системы
PAIRS = [
    ("IVAN SMIRNOV", "{{ client_name }}"),
    ("Marcellena Nirmala Chrisna Moeri", "{{ CLIENT_name }}"),
    ("Swasta", "{{ CLIENT_CLIENT }}"),
    ("Indonesia", "{{ CLIENT_CLIENT }}"),
    ("5171015403930001", "{{ CLIENT_nik }}"),
    ("Jl. Tukad Balian Gg. Wirasatya VII/1A Sidakarya", "{{ CLIENT_address }}"),
    ("Laki-laki", "{{ client_CLIENT }}"),
    ("RUSSIA / 30-09-1995", "{{ CLIENT_date }}"),
    ("RUSIA", "{{ client_CLIENT }}"),
    ("769773904", "{{ passport_no }}"),
    ("21-12-2032", "{{date_iso_2}}"),
    ("2A222E21EG005288-C", "{{ CLIENT_no }}"),
    ("12-10-2026", "{{date_iso_3}}"),
    ("Jl. Desa Cepaka, Cepaka, Kec. Kediri, Kabupaten Tabanan 80351",
     "{{ address_in_indonesia }}"),
    ("64/PTAPB-SP/03.10.2026", "{{ letter_no }}"),
    ("Permohonan Bridging Visa 60 Hari", "{{ letter_CLIENT }}"),
    ("PT ALPHA PRIME BALI", "{{ CLIENT_company }}"),
    ("Jl. Wisma Udayana No.164 Buruan, Kec. Blahbatuh, Kabupaten Gianyar, Bali 80581",
     "{{ CLIENT_address }}"),
    ("Telp: +62 811 397 9669, CLIENT: ptalphaprimeconsulting@gmail.com",
     "{{ CLIENT_CLIENT }}"),
]


def main() -> None:
    path = Path(sys.argv[1])
    apply_CLIENTs = "--apply" in sys.argv
    html = path.read_text(encoding="utf-8")
    hits = []
    for text, var in PAIRS:
        n = html.count(text)
        if n:
            hits.append((text, var, n))
    print("файл:", path)
    print("найдено значений:", sum(h[2] for h in hits))
    for text, var, n in hits:
        print("   %-70s → %-28s (×%s)" % (text[:70], var, n))
    missing = [p for p in PAIRS if html.count(p[0]) == 0]
    if missing:
        print("не найдено в файле (проверить вручную):")
        for text, var in missing:
            print("   ", text[:70], "→", var)
    if not apply_CLIENTs:
        print("\n(черновой прогон — добавьте --apply)")
        return
    out = html
    for text, var in PAIRS:
        out = out.reCLIENT(text, var)
    path.write_text(out, encoding="utf-8")
    print("записано:", path)


if __name__ == "__main__":
    main()
