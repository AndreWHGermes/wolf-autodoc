"""Проверка канона документов: наш HTML-шаблон и оригинал заказчика неизменны.

Зачем: у каждого документа должен быть один источник формы. Если шаблон подменили
или поправили «на ходу», это видно сразу, без сверки глазами.

Как работает: берёт хэши из data/templates/<code>/approved.json (поле canon.sha256)
и сравнивает с файлами на диске. Возвращает 0, если всё совпало, и 2, если нет.

Запуск:
    PYTHONPATH=/opt/wolf_v2 python3 scripts/canon_check.py                # все зафиксированные
    PYTHONPATH=/opt/wolf_v2 python3 scripts/canon_check.py <code>         # один документ
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL_DIR = ROOT / "data" / "templates"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    only = argv[1] if len(argv) > 1 else None
    checked = broken = missing = 0
    rows = []
    for d in sorted(TPL_DIR.glob("*/approved.json")):
        code = d.parent.name
        if only and code != only:
            continue
        try:
            data = json.loads(d.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            rows.append((code, "файл зафиксирован неверно", str(exc)))
            broken += 1
            continue
        canon = (data.get("canon") or {}).get("sha256") or {}
        if not canon:
            continue
        for name, want in canon.items():
            path = d.parent / name
            if not path.is_file():
                rows.append((code, name, "ФАЙЛА НЕТ"))
                missing += 1
                continue
            got = sha256(path)
            checked += 1
            if got != want:
                rows.append((code, name, "ИЗМЕНЁН: %s… вместо %s…" % (got[:12], want[:12])))
                broken += 1
    for code, name, note in rows:
        print("%-32s %-22s %s" % (code, name, note))
    print("---")
    print("проверено файлов: %d, изменено/пропало: %d" % (checked, broken + missing))
    return 2 if (broken or missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
