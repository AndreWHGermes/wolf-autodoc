"""Вернуть точечные линии в бланк формы (E-02 и подобные).

В подлиннике под каждым значением идёт точечная линия «: ………………». При подготовке
чистого бланка вырезание значений стирало линию вместе с текстом, и документ выходил
без точек — не как бумага иммиграции.

Линия РИСУЕТСЯ заново вектором (ряд точек). Копировать полосу из подлинника нельзя:
в полосе вместе с линией лежит значение прежнего клиента, и оно попадает в бланк.

Запуск: /usr/bin/python3 scripts/restore_dotted_lines.py <code> [--apply]
"""
import sys
from pathlib import Path

import pymupdf

ROOT = Path("/opt/wolf_v2")
DOT_GAP = 1.9          # шаг точек, pt
DOT_LEN = 0.55         # длина точки, pt
LEFT_SKIP = 6.0        # отступ от начала линии (там стоит двоеточие)


def dotted_spans(page):
    """Спаны-линии подлинника: строка из точек (': ………………')."""
    out = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for s in ln.get("spans", []):
                t = s["text"]
                if len(t) < 8:
                    continue
                dots = sum(1 for c in t if c in ".·…_")
                if dots / len(t) > 0.6:
                    out.append({"rect": pymupdf.Rect(s["bbox"]), "color": s["color"],
                                "text": t})
    return out


def draw_dotted(page, rect, color=0):
    """Ряд точек по низу строки: линия идёт ПОД значением, от двоеточия до края."""
    y = rect.y1 - 1.6
    shape = page.new_shape()
    x = rect.x0 + LEFT_SKIP
    while x < rect.x1:
        shape.draw_line(pymupdf.Point(x, y), pymupdf.Point(min(x + DOT_LEN, rect.x1), y))
        x += DOT_GAP
    shape.finish(color=_rgb(color), width=0.5, lineCap=1)
    shape.commit()


def _rgb(c):
    return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)


def restore(code: str, apply: bool = False) -> int:
    tpl = ROOT / "data" / "templates" / code
    src, blank = tpl / "example_filled.pdf", tpl / "blank.pdf"
    if not src.exists() or not blank.exists():
        return 0
    ref = pymupdf.open(str(src))
    doc = pymupdf.open(str(blank))
    lines = dotted_spans(ref[0])
    # Что уже есть в бланке: текстовые ряды точек И обычные векторные подчёркивания.
    # Без векторных линий скрипт считает все линии отсутствующими и рисует дубли.
    have = dotted_spans(doc[0])
    have += [{"rect": g["rect"], "color": 0, "text": "", "vector": True}
             for g in doc[0].get_drawings()
             if g["rect"].height < 4 and g["rect"].width > 40]
    added = 0
    for ln in lines:
        r = ln["rect"]
        same = [h for h in have if abs(h["rect"].y0 - r.y0) < 1.5]
        # Линия считается целой, только если идёт от начала поля до конца. Остаток справа
        # (значение вырезалось вместе с началом линии) — это не линия, её надо дорисовать.
        if any(h["rect"].x0 <= r.x0 + 12 and h["rect"].x1 >= r.x1 - 12 for h in same):
            continue
        draw_dotted(doc[0], r, ln["color"])
        added += 1

    # Недорезанные линии: если у строки остался только правый хвост, дорисовываем её
    # от начала поля — так все подчёркивания идут от двоеточия до конца, как в бланке.
    if lines:
        ref_x0 = min(l["rect"].x0 for l in lines)
        ref_x1 = max(l["rect"].x1 for l in lines)
        for h in have:
            r = h["rect"]
            if r.x0 > ref_x0 + 20 and r.width < (ref_x1 - ref_x0) - 20:
                draw_dotted(doc[0], pymupdf.Rect(ref_x0, r.y0, ref_x1, r.y1), h.get("color", 0))  # y берём у остатка
                added += 1

    # Строка-метка без линии: если рядом (в том же блоке полей) линии есть, а под меткой
    # пусто — дорисовываем линию от начала поля до конца, как у соседних строк.
    if lines:
        ref_x0 = min(l["rect"].x0 for l in lines)
        ref_x1 = max(l["rect"].x1 for l in lines)
        have_y = [h["rect"].y0 for h in have] + [g["rect"].y0 for g in doc[0].get_drawings()
                                                 if g["rect"].height < 4 and g["rect"].width > 40]
        have_y += [l["rect"].y0 for l in lines]
        for blk in doc[0].get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                t = " ".join(sp["text"] for sp in ln["spans"]).strip()
                if not t.endswith(":") or len(t) < 5:
                    continue
                base = ln["bbox"][1]
                # линия в этом бланке стоит примерно через 10.7 pt под верхом метки
                if any(abs(y - (base + 10.7)) < 6 for y in have_y):
                    continue
                # рядом должны быть линии (иначе это заголовок, а не поле)
                if not any(-40 < (y - base) < 0 for y in have_y):
                    continue
                draw_dotted(doc[0], pymupdf.Rect(ref_x0, base + 10.7, ref_x1, base + 12.3), 0)
                added += 1
    if apply and added:
        doc.saveIncr()
    doc.close()
    ref.close()
    return added


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    for code in [a for a in args if not a.startswith("--")]:
        tpl = ROOT / "data" / "templates" / code
        ref, blank = tpl / "example_filled.pdf", tpl / "blank.pdf"
        if not ref.exists() or not blank.exists():
            print("нет файлов у %s" % code)
            continue
        d1, d2 = pymupdf.open(str(ref)), pymupdf.open(str(blank))
        print("%s: линий в подлиннике %d, в бланке %d" % (code, len(dotted_spans(d1[0])), len(dotted_spans(d2[0]))))
        d1.close()
        d2.close()
        if apply:
            print("   нарисовано линий: %d" % restore(code, apply=True))


if __name__ == "__main__":
    main()
