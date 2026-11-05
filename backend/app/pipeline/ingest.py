"""Step 1 — Ingest & classify inputs.

Accepts PDF, PNG, JPG, WEBP, BMP, TIFF. Computes SHA-256, stores the original
byte-for-byte, and renders every page to a PNG the rest of the pipeline uses.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pymupdf as fitz  # PyMuPDF
from PIL import Image

from ..config import CASES_DIR, MAX_PAGE_EDGE, PDF_RENDER_ZOOM

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}


def doc_dir(case_id: str, doc_id: str) -> Path:
    d = CASES_DIR / case_id / doc_id
    (d / "pages").mkdir(parents=True, exist_ok=True)
    return d


def ingest_file(case_id: str, doc_id: str, src: Path, filename: str) -> dict:
    """Copy original into the evidence store and render pages. Returns meta."""
    d = doc_dir(case_id, doc_id)
    ext = Path(filename).suffix.lower()
    original = d / f"original{ext}"
    shutil.copyfile(src, original)
    sha = hashlib.sha256(original.read_bytes()).hexdigest()

    pages: list[dict] = []
    if ext in PDF_EXTS:
        with fitz.open(original) as pdf:
            for i, page in enumerate(pdf):
                zoom = PDF_RENDER_ZOOM
                rect = page.rect
                scale = min(zoom, MAX_PAGE_EDGE / max(rect.width, rect.height))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                out = d / "pages" / f"page_{i + 1}.png"
                pix.save(out)
                pages.append({"page": i + 1, "path": str(out),
                              "width": pix.width, "height": pix.height})
    elif ext in IMAGE_EXTS:
        img = Image.open(original).convert("RGB")
        if max(img.size) > MAX_PAGE_EDGE:
            r = MAX_PAGE_EDGE / max(img.size)
            img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        out = d / "pages" / "page_1.png"
        img.save(out)
        pages.append({"page": 1, "path": str(out), "width": img.width, "height": img.height})
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return {"sha256": sha, "pages": pages, "original": str(original), "ext": ext}


def page_path(case_id: str, doc_id: str, page: int) -> Path:
    return CASES_DIR / case_id / doc_id / "pages" / f"page_{page}.png"
