"""Manual diagnostic: run OCR + classification + fields + forensics on the
generated sample sets and print everything. Usage:

    cd backend && PYTHONPATH=. python3 tests/sample_check.py
"""
import time
import warnings

warnings.filterwarnings("ignore")

import pymupdf
from PIL import Image

from app.config import SAMPLES_CACHE_DIR
from app.pipeline import classify, fields, forensics, ocr


def main():
    for variant in ("genuine", "tampered"):
        print(f"\n########## {variant.upper()} ##########", flush=True)
        for name in ("application_form.pdf", "id_proof.jpg", "bank_statement.pdf"):
            f = SAMPLES_CACHE_DIR / variant / name
            if not f.exists():
                from app.samples.generate import build_set
                build_set(variant)
            if f.suffix == ".pdf":
                with pymupdf.open(f) as pdf:
                    pix = pdf[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                p = f.with_suffix(".render.png")
                img.save(p)
            else:
                p = f
            t0 = time.time()
            lines = ocr.ocr_page(str(p))
            cls = classify.classify({1: lines})
            flds = fields.extract_fields({1: lines}, cls["doc_type"])
            a = forensics.analyze_page(str(p), 1, lines, cls["doc_type"])
            print(f"\n--- {name} -> {cls['doc_type']} ({cls['confidence']}) "
                  f"[{time.time() - t0:.1f}s]", flush=True)
            for fl in flds:
                print(f"   {fl['key']:16s} = {fl['value']!r}")
            print(f"   regions={len(a['regions'])} photo={a['photo_bbox']} "
                  f"sig={bool(a['signature'])}")
            for r in a["regions"]:
                print(f"   [{r['kind']:9s}] {r['score']:.2f} bbox={r['bbox']} "
                      f"{str(r.get('details', {}))[:100]}")


if __name__ == "__main__":
    main()
