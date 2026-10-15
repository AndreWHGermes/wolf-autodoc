#!/usr/bin/env python3
"""Склейка «оригинал | HTML-сборка» в одну картинку для визуальной сверки."""
import io
import sys

import pymupdf
from PIL import Image


def img(p: str, dpi: int = 170) -> Image.Image:
    d = pymupdf.open(p)
    pm = d[0].get_pixmap(dpi=dpi)
    i = Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGB")
    d.close()
    return i


a = img(sys.argv[1])
b = img(sys.argv[2])
c = Image.new("RGB", (a.width + b.width + 20, max(a.height, b.height)), "white")
c.paste(a, (0, 0))
c.paste(b, (a.width + 20, 0))
c.thumbnail((1800, 1300))
out = sys.argv[3]
c.save(out)
print("картинка:", out, c.size)
