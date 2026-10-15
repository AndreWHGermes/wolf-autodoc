
import glob, os, re
import pymupdf
root = "/opt/wolf_v2/data/gdrive_cache"
files = [p for p in glob.glob(root + "/**/*", recursive=True) if os.path.isfile(p)]
print("файлов в кэше сканов:", len(files))
pdfs = [p for p in files if p.lower().endswith(".pdf")]
cand = [p for p in pdfs if re.search(r"(?i)пасп|passport|загран", os.path.basename(p))]
print("PDF всего: %d, из них похожих на паспорт: %d" % (len(pdfs), len(cand)))
found = 0
for p in (cand or pdfs)[:40]:
    try:
        d = pymupdf.open(p)
        t = " ".join(" ".join(pg.get_text() for pg in d).split())
        d.close()
    except Exception:
        continue
    m = re.search(r"P[<A-Z]{0,3}[A-Z]{3}[A-Z<]{8,}", t)
    ot = re.search(r"(?i)(отчество|father'?s name)\s*[:\-]?\s*([A-Za-zА-Яа-я\- ]{3,30})", t)
    if m or ot:
        found += 1
        if found <= 6:
            print("\n ", os.path.relpath(p, root)[:90])
            if m: print("    MRZ:", m.group(0)[:70])
            if ot: print("    отчество:", ot.group(2)[:40])
print("\nвсего с MRZ или отчеством:", found)
