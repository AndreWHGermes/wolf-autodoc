#!/usr/bin/env python3
"""Правки разметки банковской справки 3 мес Т-Банк по замечаниям Андрея (06.10.2026).

1. Между номером справки и именем клиента в оригинале есть пустая строка:
   «No ae32271197» (y 133.3) → «CLIENT_048» (y 154.0) → адрес (y 164.3) → вторая строка адреса (y 174.6).
   В нашем эталоне значения стояли плотнее (145.1 / 155.8 / 165.9), из-за чего в сборке
   имя шло сразу под номером. Сдвигаем зоны шапки на разницу высот оригинала.
2. Правка фиксируется в frame/manual_zones.json, чтобы конвейер (frame_all) её не перезаписал.

Запуск: python3 scripts/fix_3m_tbank_header.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

T = Path("/opt/wolf_v2/data/templates/bank_statement_3m__tbank")
# насколько опустить значения шапки (по координатам оригинала)
SHIFT = {"client_name": 8.93, "address_live": 8.52, "address_live_2": 8.67}
HEADER_X = 290.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    f = T / "fields.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    changed = []
    for z in data["zones"]:
        d = SHIFT.get(z.get("var"))
        if not d or z.get("page") != 0:
            continue
        if float(z["bbox"][0]) < HEADER_X:      # нижнее вхождение имени (у подписи) не трогаем
            continue
        z["bbox"] = [z["bbox"][0], round(z["bbox"][1] + d, 2), z["bbox"][2], round(z["bbox"][3] + d, 2)]
        if z.get("origin"):
            z["origin"] = [z["origin"][0], round(z["origin"][1] + d, 2)]
        z["source"] = "manual"
        z["note"] = "сдвиг по оригиналу: между номером и именем есть пустая строка"
        changed.append("%s y=%.1f→%.1f" % (z["var"], z["bbox"][1] - d, z["bbox"][1]))
    print("сдвинуто зон:", len(changed))
    for c in changed:
        print("   ", c)
    if a.apply:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        man = T / "frame" / "manual_zones.json"
        man.parent.mkdir(parents=True, exist_ok=True)
        prev = json.loads(man.read_text(encoding="utf-8")).get("zones", []) if man.exists() else []
        keep = [z for z in prev if z.get("var") not in SHIFT]
        keep += [z for z in data["zones"] if z.get("var") in SHIFT and z.get("page") == 0 and float(z["bbox"][0]) >= HEADER_X]
        man.write_text(json.dumps({"zones": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("зафиксировано в", man)
    return 0


if __name__ == "__main__":
    sys.exit(main())
