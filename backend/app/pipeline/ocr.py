"""Step 2 — OCR & extraction (RapidOCR: PaddleOCR models on ONNX runtime).

Runs fully offline. Every text line keeps its quadrilateral, axis-aligned
bounding box and recognition confidence so findings can trace back to pixels.
"""
from __future__ import annotations

import threading

import numpy as np
from PIL import Image

_LOCK = threading.Lock()
_ENGINE = None


def engine():
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            import os
            os.environ.setdefault("OMP_NUM_THREADS", "2")
            from rapidocr_onnxruntime import RapidOCR
            # Cap threads (default -1 thrashes small CPU quotas) and bound the
            # detection side so A4 scans stay fast without losing glyph detail.
            threads = int(os.environ.get("TRUTHLENS_OCR_THREADS", "2"))
            _ENGINE = RapidOCR(
                det_limit_type="max", det_limit_side_len=1400,
                det_intra_op_num_threads=threads, cls_intra_op_num_threads=threads,
                rec_intra_op_num_threads=threads, det_inter_op_num_threads=1,
                cls_inter_op_num_threads=1, rec_inter_op_num_threads=1,
            )
    return _ENGINE


def ocr_page(image_path: str) -> list[dict]:
    """Return text lines: {text, score, bbox:[x,y,w,h], poly:[[x,y]x4]}."""
    img = np.array(Image.open(image_path).convert("RGB"))
    eng = engine()  # init lock is separate from the inference lock
    with _LOCK:
        result, _ = eng(img)
    lines = []
    for poly, text, score in result or []:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        x, y = min(xs), min(ys)
        lines.append({
            "text": text.strip(),
            "score": round(float(score), 4),
            "bbox": [round(x, 1), round(y, 1), round(max(xs) - x, 1), round(max(ys) - y, 1)],
            "poly": [[round(float(a), 1), round(float(b), 1)] for a, b in poly],
        })
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    return lines


def ocr_document(pages: list[dict]) -> dict[int, list[dict]]:
    return {p["page"]: ocr_page(p["path"]) for p in pages}
