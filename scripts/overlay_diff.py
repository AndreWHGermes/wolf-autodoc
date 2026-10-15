"""Наложение двух PDF для визуального сравнения.

Оригинал печатается красным, наш документ — синим.
Там, где они совпадают, цвет становится тёмно-серым (почти чёрным):
чем меньше цветного, тем точнее совпадение. Дополнительно считается
процент расхождения и разбивка по горизонтальным полосам листа.
"""
import sys

import pymupdf
from PIL import Image, ImageChops, ImageDraw

DPI = int(sys.argv[4]) if len(sys.argv) > 4 else 150


def page_image(pdf, page=0):
    doc = pymupdf.open(pdf)
    pix = doc[page].get_pixmap(dpi=DPI)
    return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)


def mask(img, thr=200):
    """Чёрная маска текста (255 = есть текст)."""
    g = img.convert('L')
    return g.point(lambda v: 255 if v < thr else 0)


orig, ours = page_image(sys.argv[1]), page_image(sys.argv[2])
w, h = max(orig.width, ours.width), max(orig.height, ours.height)


def fit(im):
    c = Image.new('RGB', (w, h), 'white')
    c.paste(im, (0, 0))
    return c


orig, ours = fit(orig), fit(ours)
mo, mn = mask(orig), mask(ours)

# маски в 3 оттенка: оригинал — красный, наш — синий, совпадение — тёмный
both = ImageChops.multiply(mo, mn)
only_o = ImageChops.subtract(mo, both)
only_n = ImageChops.subtract(mn, both)

out = Image.new('RGB', (w, h), 'white')
out.paste(Image.new('RGB', (w, h), (255, 90, 90)), (0, 0))
out.paste(Image.new('RGB', (w, h), (90, 90, 255)), (0, 0))
out.paste(Image.new('RGB', (w, h), (55, 55, 55)), (0, 0), both)
out.paste(Image.new('RGB', (w, h), (235, 40, 40)), (0, 0), only_o)
out.paste(Image.new('RGB', (w, h), (40, 40, 235)), (0, 0), only_n)
out.save(sys.argv[3])

n_o = mo.histogram()[255]
n_n = mn.histogram()[255]
n_both = both.histogram()[255]
n_diff = n_o + n_n - 2 * n_both
print('пиксели текста: оригинал %d, наш %d, совпало %d' % (n_o, n_n, n_both))
print('расхождение: %d px = %.1f%% от объёма текста' % (n_diff, 100.0 * n_diff / max(n_o, n_n, 1)))

# где именно расходится: полосы по 5% высоты и колонки по 5% ширины
diff_img = ImageChops.add(only_o, only_n)
step_y, step_x = h // 20, w // 20
rows = []
for i in range(20):
    box = (0, i * step_y, w, min(h, (i + 1) * step_y))
    px = diff_img.crop(box).histogram()[255]
    if px:
        rows.append((i * step_y, px))
rows.sort(key=lambda r: -r[1])
print('самые расходящиеся полосы (y в pt от верха, пикселей):')
for y, px in rows[:6]:
    print('   y≈%5.1f pt: %d px' % (y / DPI * 72.0, px))
print('сохранено: %s' % sys.argv[3])
