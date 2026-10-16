"""Облегчение веса шаблонов, не меняя форму: шрифты → WOFF2, подложки → палитра.

Зачем: старые каркасы Сбера весят 1,5 МБ (полные TTF в base64 + PNG-подложка), из-за
этого страница конструктора грузится 4–5 секунд и интерфейс «залипает». Форма при этом
не меняется: те же подложка, шрифты и координаты, только сжатые.

Запуск:
    PYTHONPATH=/opt/wolf_v2 /usr/bin/python3 scripts/lighten_template.py <code> [--apply]
"""
from __future__ import annotations

import base64
import io
import pathlib
import re
import shutil
import sys

from PIL import Image
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "data" / "templates"
BACKUP = pathlib.Path("/opt/wolf_backups/template_lightening")


def ttf_to_woff2(raw: bytes) -> bytes:
    font = TTFont(io.BytesIO(raw))
    out = io.BytesIO()
    font.flavor = "woff2"
    font.save(out)
    return out.getvalue()


def lighten(code: str, apply: bool = False) -> None:
    path = TPL / code / "template.html"
    src = path.read_text(encoding="utf-8")
    size_before = len(src.encode("utf-8"))

    # 1) шрифты TTF → WOFF2
    def _font(m: re.Match) -> str:
        raw = base64.b64decode(m.group(1))
        try:
            packed = ttf_to_woff2(raw)
        except Exception as exc:  # noqa: BLE001
            print("   шрифт не сжат (%s) — оставляю как есть" % exc)
            return m.group(0)
        print("   шрифт: %d КБ → %d КБ" % (len(raw) // 1024, len(packed) // 1024))
        return "data:font/woff2;base64," + base64.b64encode(packed).decode("ascii")

    src = re.sub(r"data:font/ttf;base64,([A-Za-z0-9+/=]{500,})", _font, src)
    src = src.replace("format('truetype')", "format('woff2')").replace('format("truetype")', 'format("woff2")')

    # 2) подложки: PNG → палитра (текст и логотип остаются резкими, вес падает в разы)
    def _img(m: re.Match) -> str:
        raw = base64.b64decode(m.group(2))
        if len(raw) < 40_000:
            return m.group(0)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        q = im.quantize(colors=64, method=Image.MEDIANCUT, dither=Image.NONE)
        buf = io.BytesIO()
        q.save(buf, format="PNG", optimize=True)
        packed = buf.getvalue()
        if len(packed) >= len(raw):
            print("   подложка %dx%d: сжатие не дало выигрыша, оставляю PNG" % (im.width, im.height))
            return m.group(0)
        print("   подложка %dx%d: %d КБ → %d КБ" % (im.width, im.height, len(raw) // 1024, len(packed) // 1024))
        return "data:image/png;base64," + base64.b64encode(packed).decode("ascii")

    src = re.sub(r"data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=]{500,})", _img, src)
    size_after = len(src.encode("utf-8"))
    print("   итог: %d КБ → %d КБ" % (size_before // 1024, size_after // 1024))

    if not apply:
        print("   (пробный прогон, файл не тронут)")
        return
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, BACKUP / ("%s__%s.html" % (code, path.stat().st_mtime_ns)))
    path.write_text(src, encoding="utf-8")
    print("   записано: %s" % path)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    for c in (args or []):
        print("=== %s" % c)
        lighten(c, apply)
