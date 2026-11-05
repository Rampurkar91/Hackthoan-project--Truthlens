"""Step 4 — Visual forensic analysis.

Signal families (all computed on the original rendered page):
  * ELA            — error-level analysis: regions whose JPEG compression
                     history differs from the rest of the page.
  * noise break    — local high-pass noise energy; pasted/overwritten patches
                     are usually cleaner (or noisier) than the surrounding scan.
  * font drift     — glyph-box height / baseline / density compared to
                     neighbouring text (uses OCR geometry).
  * copy-move      — duplicated image blocks found by ORB self-matching with
                     consistent displacement voting (text areas excluded).
  * signature      — placement, ink density, overlap with printed text.
  * photo region   — face located on ID proofs; anomalies there are reported
                     as possible image replacement.

Each signal returns regions with a 0..1 score. Nothing here concludes fraud;
the reasoning layer assigns Observed / Inconsistent / Potential manipulation.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from .normalize import bbox_overlap, bbox_union

MIN_REGION_AREA = 700


# --------------------------------------------------------------- helpers ---
def _load_gray(path: str) -> tuple[np.ndarray, np.ndarray]:
    rgb = np.array(Image.open(path).convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return rgb, gray


def _text_mask(shape, lines: list[dict], dilate: int = 6) -> np.ndarray:
    mask = np.zeros(shape[:2], np.uint8)
    for l in lines:
        x, y, w, h = [int(v) for v in l["bbox"]]
        cv2.rectangle(mask, (max(0, x - dilate), max(0, y - dilate)),
                      (x + w + dilate, y + h + dilate), 255, -1)
    return mask


def _clusters_to_regions(mask: np.ndarray, energy: np.ndarray,
                         min_area: int = MIN_REGION_AREA, max_frac: float = 0.20):
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    regions = []
    page_area = mask.shape[0] * mask.shape[1]
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area or area > page_area * max_frac:
            continue
        mean_e = float(energy[labels == i].mean())
        regions.append({"bbox": [int(x), int(y), int(w), int(h)],
                        "area": int(area), "mean_energy": mean_e})
    return regions


# ------------------------------------------------------------------- ELA ---
def ela_regions(rgb: np.ndarray, lines: list[dict]) -> list[dict]:
    """Block-wise ELA energy; flag blocks far from the page's robust median."""
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    buf.seek(0)
    resaved = np.array(Image.open(buf).convert("RGB")).astype(np.float32)
    diff = np.abs(rgb.astype(np.float32) - resaved).mean(axis=2)

    block = 16
    h, w = diff.shape
    bh, bw = h // block, w // block
    if bh < 4 or bw < 4:
        return []
    grid = diff[:bh * block, :bw * block].reshape(bh, block, bw, block).mean(axis=(1, 3))

    # Ignore flat-white blocks (ELA ~0 everywhere) via activity floor.
    med = float(np.median(grid))
    mad = float(np.median(np.abs(grid - med))) or 1e-6
    if med < 0.35:          # page has essentially no JPEG history (clean render)
        return []
    z = (grid - med) / (1.4826 * mad)
    # robust-z gate AND an absolute error-level floor, so near-uniform pages
    # don't flag ordinary text antialiasing as anomalies
    mask_grid = ((np.abs(z) > 4.0) & (np.abs(grid - med) > 1.2)).astype(np.uint8) * 255
    mask = cv2.resize(mask_grid, (bw * block, bh * block), interpolation=cv2.NEAREST)
    full = np.zeros(diff.shape, np.uint8)
    full[:mask.shape[0], :mask.shape[1]] = mask

    out = []
    for r in _clusters_to_regions(full, diff, min_area=900):
        x, y, bw2, bh2 = r["bbox"]
        gz = float(np.abs(z[max(0, y // block):max(1, (y + bh2) // block),
                            max(0, x // block):max(1, (x + bw2) // block)]).mean())
        score = float(np.clip(0.45 + gz / 14.0, 0.4, 0.95))
        out.append({**r, "score": round(score, 3),
                    "details": {"method": "ELA q90", "median_error": round(med, 3),
                                "region_error": round(r["mean_energy"], 3),
                                "robust_z": round(gz, 2)}})
    return out


# ---------------------------------------------------------- noise breaks ---
def noise_regions(gray: np.ndarray, lines: list[dict]) -> list[dict]:
    """Background noise energy: pasted patches break the scan's noise floor."""
    g = gray.astype(np.float32)
    hp = g - cv2.GaussianBlur(g, (0, 0), 3)
    energy = cv2.boxFilter(hp * hp, -1, (31, 31))

    # Keep a thin margin around glyphs so the BACKGROUND between letters stays
    # measurable: an overwrite fills a clean rectangle, so its inter-glyph
    # background lacks the scan noise floor that genuine text surroundings have.
    valid = _text_mask(gray.shape, lines, dilate=3) == 0
    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8)) > 0
    valid &= ~edges
    if valid.sum() < 5000:
        return []
    med = float(np.median(energy[valid]))
    if med < 0.6:            # pristine digital page, no scan noise to compare
        return []

    low = ((energy < med * 0.30) & valid).astype(np.uint8) * 255
    high = ((energy > med * 3.5) & valid).astype(np.uint8) * 255

    out = []
    for r in _clusters_to_regions(low, energy, min_area=400):
        ratio = r["mean_energy"] / med
        score = float(np.clip(0.9 - ratio, 0.5, 0.95))
        out.append({**r, "score": round(score, 3), "direction": "smoother",
                    "details": {"method": "high-pass noise energy",
                                "page_noise": round(med, 3),
                                "region_noise": round(r["mean_energy"], 3),
                                "ratio": round(ratio, 3)}})
    for r in _clusters_to_regions(high, energy, min_area=1200):
        ratio = r["mean_energy"] / med
        score = float(np.clip(0.4 + ratio / 12.0, 0.4, 0.9))
        out.append({**r, "score": round(score, 3), "direction": "noisier",
                    "details": {"method": "high-pass noise energy",
                                "page_noise": round(med, 3),
                                "region_noise": round(r["mean_energy"], 3),
                                "ratio": round(ratio, 3)}})
    return out


# ------------------------------------------------------------ font drift ---
def font_drift_regions(lines: list[dict]) -> list[dict]:
    """Compare glyph-box heights & baselines within rows and across the page."""
    out = []
    body = [l for l in lines if l["score"] > 0.7 and len(l["text"]) >= 4]
    if len(body) < 4:
        return out
    # Compare like-for-like: 'Label: value' field lines are typeset uniformly
    # on genuine forms; headers/footers/table cells are not part of this set.
    field_lines = [l for l in body if ":" in l["text"] and len(l["text"]) >= 8]
    heights = np.array([l["bbox"][3] for l in (field_lines or body)])
    med_h = float(np.median(heights))

    # 1) field-line height outliers. OCR box height varies ~±20% with glyph
    # content (caps/descenders), so only flag strong (>22%, >4px) deviations;
    # subtler overwrites are caught by the noise-break signal instead.
    for l in (field_lines or []):
        h = l["bbox"][3]
        ratio = h / med_h
        if 0.5 < ratio < 1.7 and abs(ratio - 1) > 0.22 and abs(h - med_h) > 4:
            out.append({"bbox": l["bbox"], "score": round(min(0.9, 0.4 + abs(ratio - 1) * 2), 3),
                        "direction": "size",
                        "details": {"method": "glyph height vs page body",
                                    "line": l["text"][:60], "line_height": round(h, 1),
                                    "page_median": round(med_h, 1),
                                    "ratio": round(ratio, 3)}})

    # 2) within-row neighbours: label vs value boxes on the same baseline
    rows: list[list[dict]] = []
    for l in sorted(body, key=lambda t: t["bbox"][1]):
        placed = False
        for row in rows:
            r0 = row[0]["bbox"]
            y_overlap = min(r0[1] + r0[3], l["bbox"][1] + l["bbox"][3]) - max(r0[1], l["bbox"][1])
            if y_overlap > 0.5 * min(r0[3], l["bbox"][3]):
                row.append(l)
                placed = True
                break
        if not placed:
            rows.append([l])
    for row in rows:
        if len(row) < 2:
            continue
        # Only compare neighbours on 'Label: value' rows; table cells vary
        # naturally (digits, commas) and are not typeset field values.
        if not any(":" in l["text"] for l in row):
            continue
        row.sort(key=lambda t: t["bbox"][0])
        hs = [l["bbox"][3] for l in row]
        base = float(np.median(hs))
        for l in row:
            h = l["bbox"][3]
            ratio = h / base
            bottom = l["bbox"][1] + h
            bottoms = [r["bbox"][1] + r["bbox"][3] for r in row if r is not l]
            bshift = abs(bottom - float(np.median(bottoms)))
            if (abs(ratio - 1) > 0.20 and abs(h - base) > 3) or bshift > 0.34 * base:
                out.append({"bbox": l["bbox"],
                            "score": round(min(0.92, 0.45 + abs(ratio - 1) * 2 + bshift / (base * 4)), 3),
                            "direction": "row",
                            "details": {"method": "neighbour comparison in row",
                                        "line": l["text"][:60],
                                        "line_height": round(h, 1),
                                        "row_median": round(base, 1),
                                        "baseline_shift_px": round(bshift, 1)}})
    # dedupe overlapping reports of the same line
    dedup = []
    for r in sorted(out, key=lambda r: -r["score"]):
        if not any(bbox_overlap(r["bbox"], d["bbox"]) > 0.6 for d in dedup):
            dedup.append(r)
    return dedup


# ------------------------------------------------------------- copy-move ---
def copymove_regions(gray: np.ndarray, lines: list[dict]) -> list[dict]:
    """ORB self-matching + displacement voting; text boxes are excluded."""
    mask = 255 - _text_mask(gray.shape, lines, dilate=5)
    orb = cv2.ORB_create(nfeatures=4000)
    kp, des = orb.detectAndCompute(gray, mask)
    if des is None or len(kp) < 30:
        return []
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = bf.knnMatch(des, des, k=3)
    votes: dict[tuple[int, int], list] = {}
    for mlist in pairs:
        for m in mlist[1:]:
            if m.queryIdx == m.trainIdx:
                continue
            if m.distance > 38:
                continue
            p, q = kp[m.queryIdx].pt, kp[m.trainIdx].pt
            dx, dy = q[0] - p[0], q[1] - p[1]
            if (dx * dx + dy * dy) ** 0.5 < 60:
                continue
            key = (int(round(dx / 12)), int(round(dy / 12)))
            votes.setdefault(key, []).append((p, q))
            break
    if not votes:
        return []
    key, matches = max(votes.items(), key=lambda kv: len(kv[1]))
    if len(matches) < 12:
        return []
    pts = np.array([p for pair in matches for p in pair], np.float32)
    x, y, w, h = cv2.boundingRect(pts)
    pad = 12
    x, y = max(0, x - pad), max(0, y - pad)
    w = min(gray.shape[1] - x, w + 2 * pad)
    h = min(gray.shape[0] - y, h + 2 * pad)
    score = float(np.clip(0.4 + len(matches) / 60.0, 0.4, 0.9))
    return [{"bbox": [int(x), int(y), int(w), int(h)], "area": int(w * h),
             "score": round(score, 3),
             "details": {"method": "ORB self-match + displacement voting",
                         "matched_keypoints": len(matches),
                         "displacement_px": [key[0] * 12, key[1] * 12]}}]


# ------------------------------------------------------------- signature ---
def signature_info(gray: np.ndarray, lines: list[dict]) -> dict | None:
    """Locate a signature near its printed anchor; measure ink & overlap."""
    anchors = [l for l in lines if "signature" in l["text"].lower()
               or l["text"].lower().strip() in ("sign", "sd/-", "sd/-")]
    if not anchors:
        return None
    a = anchors[0]["bbox"]
    h, w = gray.shape
    rw = int(min(max(a[2] * 1.8, 220), w * 0.5))
    rh = 110
    x1 = int(max(0, min(a[0] - 20, w - rw)))
    y1 = int(max(0, a[1] - rh))
    crop = gray[y1:y1 + rh, x1:x1 + rw]
    if crop.size == 0:
        return None
    ink = crop < 120
    density = float(ink.mean())
    if density < 0.008:
        return {"present": False, "anchor_bbox": a, "bbox": [], "density": density}
    ys, xs = np.where(ink)
    bx, by = int(xs.min()) + x1, int(ys.min()) + y1
    bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    bbox = [bx, by, bw, bh]
    overlaps = []
    for l in lines:
        if l is anchors[0] or "signature" in l["text"].lower():
            continue
        if bbox_overlap(bbox, l["bbox"]) > 0.18:
            overlaps.append(l["text"][:50])
    return {"present": True, "anchor_bbox": a, "bbox": bbox,
            "density": round(density, 4), "overlaps_text": overlaps,
            "crop": crop}


# ------------------------------------------------------------ photo region -
def photo_region(gray: np.ndarray, doc_type: str) -> list[float] | None:
    """Approximate the ID photo from a detected face (ID proofs only)."""
    if doc_type != "id_proof":
        return None
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    px = max(0, int(x - w * 0.55))
    py = max(0, int(y - h * 0.55))
    pw = min(gray.shape[1] - px, int(w * 2.1))
    ph = min(gray.shape[0] - py, int(h * 2.4))
    return [px, py, pw, ph]


# ------------------------------------------------------------- orchestrate -
def analyze_page(path: str, page: int, lines: list[dict], doc_type: str) -> dict:
    rgb, gray = _load_gray(path)
    regions: list[dict] = []

    for r in ela_regions(rgb, lines):
        regions.append({"kind": "ela", "page": page, **r})
    for r in noise_regions(gray, lines):
        regions.append({"kind": "noise", "page": page, **r})
    for r in font_drift_regions(lines):
        regions.append({"kind": "font", "page": page, **r})
    for r in copymove_regions(gray, lines):
        regions.append({"kind": "copymove", "page": page, **r})

    photo = photo_region(gray, doc_type)
    if photo:
        for r in regions:
            if r["kind"] in ("ela", "noise") and bbox_overlap(r["bbox"], photo) > 0.35:
                r["kind"] = "photo"
                r["details"] = {**r["details"], "note": "anomaly inside ID photo region"}

    sig = signature_info(gray, lines)
    signature = None
    if sig and sig.get("present"):
        signature = {k: v for k, v in sig.items() if k != "crop"}
        if sig["overlaps_text"]:
            regions.append({"kind": "signature", "page": page, "bbox": sig["bbox"],
                            "score": 0.6,
                            "details": {"method": "placement check",
                                        "overlaps_text": sig["overlaps_text"],
                                        "ink_density": sig["density"]}})
    return {"regions": regions, "photo_bbox": photo, "signature": signature,
            "signature_crop": sig.get("crop") if sig else None}
