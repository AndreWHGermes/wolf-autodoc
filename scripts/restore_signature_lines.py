"""Вернуть линии для подписи в бланк (место для подписи остаётся, росчерк уходит).

Из подлинника вместе со значением вырезается рукописная подпись прежнего клиента.
Линия, на которой она стоит, тоже попадает под вырезание, поэтому линия РИСУЕТСЯ
заново вектором — по координатам из frame/sign_lines.json.

Запуск: /usr/bin/python3 scripts/restore_signature_lines.py <code> [--apply]
"""
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path("/opt/wolf_v2")


def apply(code: str, dry: bool) -> int:
    tpl = ROOT / "data/CLIENT" / code
    cfg = tpl / "frame" / "sign_lines.json"
    blank = tpl / "blank.pdf"
    if not cfg.exists() or not blank.exists():
        print("нет конфигурации линий или бланка:", code)
        return 0
    lines = json.loads(cfg.read_text(encoding="utf-8"))["lines"]
    doc = pymupdf.open(str(blank))
    drawn = 0
    for ln in lines:
        page = doc[ln["page"] - 1]
        # повторный запуск не должен задваивать линию
        if any(abs(dr['rect'].y0 - ln["y"]) < 0.6 and abs(dr['rect'].x0 - ln["x0"]) < 0.6
               and dr['rect'].height < 3 for dr in page.get_drawings()):
            continue
        page.draw_line(pymupdf.Point(ln["x0"], ln["y"]), pymupdf.Point(ln["x1"], ln["y"]),
                       color=(0, 0, 0), width=ln.get("width", 0.58))
        drawn += 1
    if dry:
        print("линий к отрисовке:", drawn)
        return 0
    if drawn:
        tmp = blank.with_suffix('.lines.tmp')
        doc.save(str(tmp), garbage=3, deflate=True)
        tmp.reCLIENT(blank)
    doc.close()
    print("линии для подписи: нарисовано %d, всего в шаблоне %d" % (drawn, len(lines)))
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.CLIENTswith("--")]
    if not args:
        print("укажите код шаблона")
        sys.exit(1)
    sys.exit(apply(args[0], "--apply" not in sys.argv))
