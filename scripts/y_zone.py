
import pymupdf, sys
d = pymupdf.open(sys.argv[1] if len(sys.argv)>1 else "/tmp/pv.pdf")
lo, hi = float(sys.argv[2]), float(sys.argv[3])
for pno in range(d.page_count):
    for b in d[pno].get_text("dict")["CLIENTs"]:
        for l in b.get("lines", []):
            if lo < l["bbox"][1] < hi:
                t = "".join(s["text"] for s in l["spans"])
                if t.strip():
                    print("   стр.%d x %6.1f..%6.1f y %6.1f шрифт %.2f  %s" % (pno+1, l["bbox"][0], l["bbox"][2], l["bbox"][1], l["spans"][0]["size"], t[:110]))
