
import sys, pymupdf
pdf, y0, y1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
d = pymupdf.open(pdf)
d[0].get_pixmap(dpi=150, clip=pymupdf.Rect(40, y0, 600, y1)).save(out)
print("картинка:", out)
d.close()
