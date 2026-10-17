#!/usr/bin/env python3
"""Разметка анкет письма (Bridging / Conversion / D12) по подписям полей.

Письмо устроено как анкета: слева подпись («Nama», «Pekerjaan», …), справа — значение.
Значит зону можно определить без знания значений: берём подпись, ставим зону на текст
справа от «:» и привязываем переменную. Верхняя анкета — данные подписанта/спонсора,
нижняя (после «selaku penerima kuasa») — данные клиента.

    map_letter_fields.py <code> [--apply]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path("/opt/wolf_v2")
sys.path.insert(0, str(ROOT))
import pymupdf  # noqa: E402

# подпись поля -> (переменная в верхней анкете, переменная в нижней анкете)
LABELS = {
    "nama": ("sponsor_person_name", "client_name"),
    "pekerjaan": ("occupation", "occupation"),
    "kewarganegaraan": ("sponsor_citizenship", "nationality"),
    "nik": ("sponsor_nik", "client_nik"),
    "alamat": ("sponsor_address", "client_address"),
    "jenis kelamin": ("gender", "gender"),
    "tempat/tgl. lahir": ("place_date_of_birth", "place_date_of_birth"),
    "tempat/tanggal lahir": ("place_date_of_birth", "place_date_of_birth"),
    "no. paspor": ("passport_number", "passport_number"),
    "masa berlaku paspor": ("passport_expiry", "passport_expiry"),
    "nomor itk": ("itk_number", "itk_number"),
    "masa berlaku itk": ("itk_expiry", "itk_expiry"),
    "tanggal lahir": ("date_of_birth", "date_of_birth"),
    "paspor": ("passport_number", "passport_number"),
}
SPLIT = ("selaku penerima kuasa", "data sebagai berikut")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    td = ROOT / "data" / "templates" / a.code
    doc = pymupdf.open(str(td / "example_filled.pdf"))
    page = doc[0]

    lines = {}
    for w in page.get_text("words"):
        lines.setdefault(round(w[1], 1), []).append(w)
    y_split = min([y for y in lines
                   if any(s in " ".join(x[4] for x in lines[y]).lower() for s in SPLIT)] or [10 ** 6])

    fields_path = td / "fields.json"
    fields = json.loads(fields_path.read_text(encoding="utf-8"))
    zones = fields["zones"] if isinstance(fields, dict) else fields
    have = {(z.get("var"), round(z["bbox"][1], 1)) for z in zones if z.get("bbox")}

    added = []
    for y in sorted(lines):
        ws = sorted(lines[y], key=lambda x: x[0])
        text = " ".join(x[4] for x in ws).strip()
        m = re.match(r"^([A-Za-z\./ ]+?)\s*:\s*(.*)$", text)
        if not m:
            continue
        label = m.group(1).strip().lower()
        if label not in LABELS:
            continue
        up, low = LABELS[label]
        var = up if y < y_split else low
        # зона — текст справа от «:»
        after = [x for x in ws if x[4] == ":" or (x[0] > 205)]
        after = [x for x in after if x[4] != ":"]
        if not after:
            continue
        box = [min(x[0] for x in after) - 1, y - 1, max(x[2] for x in after) + 1, max(x[3] for x in after) + 1]
        if label == "alamat":
            # адрес занимает 1–2 строки: полосу вырезаем с запасом, иначе вторая строка
            # старого адреса остаётся в подложке и накладывается на наше значение
            box[3] = round(max(x[3] for x in after) + 28.0, 2)
        if (var, round(box[1], 1)) in have:
            # зона уже есть — обновляем прямоугольник (у адреса он шире: нужен запас
            # на вторую строку, иначе старый адрес бланка просвечивает под нашим)
            for z in zones:
                if z.get("var") == var and z.get("bbox") and round(z["bbox"][1], 1) == round(box[1], 1):
                    z["bbox"] = [round(v, 2) for v in box]
                    break
            continue
        zones.append({"var": var, "bbox": [round(v, 2) for v in box]})
        added.append((var, round(y, 1), text[:44]))

    print("%s: добавлено зон анкет: %d" % (a.code, len(added)))
    for var, y, t in added:
        print("   y%-6.1f %-24s %s" % (y, var, t))
    if a.apply:
        # пишем всегда: у адресных зон мог обновиться прямоугольник (запас на вторую
        # строку), и без записи в файл это изменение теряется
        fields_path.write_text(json.dumps(fields, ensure_ascii=False, indent=1), encoding="utf-8")
        print("записано:", fields_path, "| новых зон:", len(added))


if __name__ == "__main__":
    main()
