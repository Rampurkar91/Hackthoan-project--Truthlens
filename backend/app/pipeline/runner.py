"""Pipeline orchestrator — runs the 7-step investigation and writes evidence.

  1 Ingest & classify → 2 OCR → 3 Fields → 4 Visual forensics →
  5 Contextual checks → 6 Cross-doc correlation → 7 Evidence & dossier

Every step appends to the hash-chained audit log. Findings are never labelled
'fraud': levels are observed / inconsistent / potential_manipulation.
"""
from __future__ import annotations

import traceback

import cv2
import numpy as np

from .. import store
from ..config import CASES_DIR
from . import classify, contextual, correlate, explain, fields, forensics, ocr
from .normalize import bbox_overlap, bbox_union

VISUAL_TITLES = {
    "ela": "Compression anomaly (ELA)",
    "noise": "Noise-floor break",
    "font": "Font / baseline drift",
    "copymove": "Copy-move duplication",
    "photo": "Possible photo replacement",
    "signature": "Signature placement anomaly",
}


def _merge_visual_regions(regions: list[dict]) -> list[list[dict]]:
    """Group regions of different kinds that agree on the same pixels."""
    groups: list[list[dict]] = []
    for r in sorted(regions, key=lambda r: -r["score"]):
        placed = False
        for g in groups:
            if any(x["page"] == r["page"] and bbox_overlap(x["bbox"], r["bbox"]) > 0.3
                   for x in g):
                g.append(r)
                placed = True
                break
        if not placed:
            groups.append([r])
    return groups


def _visual_findings(doc: dict, analysis: dict) -> list[dict]:
    """Turn raw regions into findings, escalating when signals agree."""
    drafts = []
    groups = _merge_visual_regions(analysis["regions"])
    for g in groups:
        kinds = {r["kind"] for r in g}
        bbox = bbox_union([r["bbox"] for r in g])
        page = g[0]["page"]
        score = max(r["score"] for r in g)
        if len(kinds) >= 2:
            level = "potential_manipulation"
            conf = min(0.95, score + 0.1)
            title = "Multiple forensic signals agree on one region"
            explanation = (
                "Independent analyses — " + ", ".join(sorted(kinds)) +
                " — all flag the same region on page " + str(page) + ". "
                "Agreement between different signal families makes accidental "
                "artefacts less likely. This is potential manipulation, not a "
                "confirmed conclusion; a human reviewer must decide.")
            steps = ["Inspect the highlighted region on the original document",
                     "Request the source file / re-scan and re-run the analysis",
                     "Verify the affected field values with the issuer"]
            drafts.append({"level": level, "category": "visual_forensic",
                           "kind": "combined", "doc_id": doc["id"], "title": title,
                           "explanation": explanation, "verification": steps,
                           "confidence": round(conf, 3),
                           "facts": {"kinds": sorted(kinds)},
                           "evidence": [{"doc_id": doc["id"], "page": page, "bbox": bbox,
                                         "label": "region", "value": ", ".join(sorted(kinds))}]})
        else:
            r = g[0]
            draft = {"level": "observed", "category": "visual_forensic",
                     "kind": r["kind"], "doc_id": doc["id"],
                     "title": VISUAL_TITLES.get(r["kind"], "Visual anomaly"),
                     "confidence": r["score"],
                     "facts": {**r.get("details", {}), "details": r.get("details", {}),
                               "direction": r.get("direction", "")},
                     "evidence": [{"doc_id": doc["id"], "page": r["page"],
                                   "bbox": r["bbox"], "label": r["kind"], "value": ""}]}
            text, steps = explain.explain_finding(draft)
            draft["explanation"], draft["verification"] = text, steps
            drafts.append(draft)
    return drafts


def analyze_document(doc_id: str) -> None:
    doc = store.get_document(doc_id)
    if not doc:
        return
    case_id = doc["case_id"]
    try:
        store.update_document(doc_id, status="processing")
        pages = doc["meta"]["pages"]

        # 2 — OCR
        ocr_pages = ocr.ocr_document(pages)
        n_lines = sum(len(v) for v in ocr_pages.values())
        store.audit(case_id, "pipeline.ocr", {"doc_id": doc_id, "lines": n_lines})

        # 1 — classify (needs OCR text)
        cls = classify.classify(ocr_pages)
        store.update_document(doc_id, doc_type=cls["doc_type"],
                              type_confidence=cls["confidence"])
        store.audit(case_id, "pipeline.classify",
                    {"doc_id": doc_id, "doc_type": cls["doc_type"],
                     "confidence": cls["confidence"]})
        doc = store.get_document(doc_id)

        # 3 — fields
        extracted = fields.extract_fields(ocr_pages, cls["doc_type"])
        store.replace_fields(doc_id, case_id, extracted)
        store.audit(case_id, "pipeline.fields",
                    {"doc_id": doc_id, "fields": [f["key"] for f in extracted]})
        saved_fields = store.list_fields(case_id, doc_id)

        # 4 — visual forensics
        store.clear_auto_findings(case_id, doc_id=doc_id,
                                  categories=["visual_forensic", "contextual"])
        all_regions, sig_crops = [], {}
        photo_bbox, signature = None, None
        for p in pages:
            lines = ocr_pages[p["page"]]
            analysis = forensics.analyze_page(p["path"], p["page"], lines, cls["doc_type"])
            all_regions.extend(analysis["regions"])
            if analysis["photo_bbox"]:
                photo_bbox = analysis["photo_bbox"]
            if analysis["signature"]:
                signature = analysis["signature"]
            if analysis["signature_crop"] is not None:
                sig_crops[p["page"]] = analysis["signature_crop"]
        for draft in _visual_findings(doc, {"regions": all_regions}):
            store.add_finding(case_id, **{k: v for k, v in draft.items() if k != "facts"})
        store.audit(case_id, "pipeline.forensics",
                    {"doc_id": doc_id, "regions": len(all_regions)})

        # signature crops for cross-document similarity
        meta = doc["meta"]
        meta["photo_bbox"] = photo_bbox
        meta["signature"] = signature
        meta["visual_regions"] = all_regions
        meta["ocr_lines"] = {str(k): v for k, v in ocr_pages.items()}
        store.update_document(doc_id, meta=meta)
        for pg, crop in sig_crops.items():
            out = CASES_DIR / case_id / doc_id / f"signature_{pg}.png"
            cv2.imwrite(str(out), crop)

        # 5 — contextual checks
        for draft in contextual.check_document(doc, saved_fields):
            text, steps = explain.explain_finding(draft)
            draft["explanation"], draft["verification"] = text, steps
            store.add_finding(case_id, **{k: v for k, v in draft.items() if k != "facts"})
        store.audit(case_id, "pipeline.contextual", {"doc_id": doc_id})

        store.update_document(doc_id, status="ready")
    except Exception as e:  # keep the case usable, record the failure
        store.update_document(doc_id, status="error",
                              meta={**(doc.get("meta") or {}), "error": str(e)})
        store.audit(case_id, "pipeline.error",
                    {"doc_id": doc_id, "error": str(e),
                     "trace": traceback.format_exc()[-1500:]})


def _signature_similarity(case_id: str, docs: list[dict]) -> list[dict]:
    """Cross-document signature similarity (partial capability, observed only)."""
    crops = []
    for d in docs:
        p = CASES_DIR / case_id / d["id"] / "signature_1.png"
        if p.exists():
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                crops.append((d, img))
    out = []
    orb = cv2.ORB_create(nfeatures=1000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    for i in range(len(crops)):
        for j in range(i + 1, len(crops)):
            (da, ia), (db, ib) = crops[i], crops[j]
            ha = 120
            ia = cv2.resize(ia, (int(ia.shape[1] * ha / ia.shape[0]), ha))
            ib = cv2.resize(ib, (int(ib.shape[1] * ha / ib.shape[0]), ha))
            ka, desa = orb.detectAndCompute(ia, None)
            kb, desb = orb.detectAndCompute(ib, None)
            if desa is None or desb is None or len(ka) < 8 or len(kb) < 8:
                continue
            matches = bf.match(desa, desb)
            good = [m for m in matches if m.distance < 45]
            ratio = len(good) / max(1, min(len(ka), len(kb)))
            if ratio > 0.30:
                out.append({
                    "level": "observed", "category": "cross_document",
                    "kind": "sig_similar", "doc_id": da["id"],
                    "title": "Very similar signatures across documents",
                    "explanation": (
                        f"Signature regions on {da['filename']} and {db['filename']} share "
                        f"{ratio * 100:.0f}% of local features. Reuse of the same signature "
                        "image can be legitimate (digitally affixed) or a pasted copy — "
                        "treat as an observation, not a conclusion."),
                    "verification": ["Compare against a wet-ink specimen",
                                     "Check whether signatures were affixed digitally"],
                    "confidence": round(min(0.8, 0.4 + ratio), 3),
                    "evidence": [
                        {"doc_id": da["id"], "page": 1,
                         "bbox": (da["meta"].get("signature") or {}).get("bbox", []),
                         "label": "signature", "value": da["filename"]},
                        {"doc_id": db["id"], "page": 1,
                         "bbox": (db["meta"].get("signature") or {}).get("bbox", []),
                         "label": "signature", "value": db["filename"]},
                    ]})
    return out


def analyze_case(case_id: str) -> None:
    """Run per-document analysis, then case-level correlation. Blocking."""
    store.set_case_status(case_id, "analyzing")
    store.audit(case_id, "pipeline.run.started", {})
    try:
        docs = store.list_documents(case_id)
        for d in docs:
            if d["status"] != "ready":
                analyze_document(d["id"])

        docs = store.list_documents(case_id)
        ready = [d for d in docs if d["status"] == "ready"]
        all_fields = store.list_fields(case_id)
        visual = {d["id"]: d["meta"].get("visual_regions", []) for d in ready}

        # 6 — cross-document correlation
        store.clear_auto_findings(case_id, categories=["cross_document"])
        result = correlate.correlate(ready, all_fields, visual)
        for draft in result["conflicts"]:
            text, steps = explain.explain_finding(draft)
            draft["explanation"] = explain.llm_refine(text, draft.get("facts", {}), steps)
            draft["verification"] = steps
            store.add_finding(case_id, **{k: v for k, v in draft.items() if k != "facts"})
        for draft in _signature_similarity(case_id, ready):
            store.add_finding(case_id, **draft)

        # persist matrix for UI + dossier
        import json
        (CASES_DIR / case_id / "matrix.json").write_text(json.dumps(result["matrix"], indent=2))
        store.audit(case_id, "pipeline.correlation",
                    {"documents": len(ready),
                     "conflicts": sum(1 for r in result["matrix"]
                                      if r["status"] in ("conflict", "check"))})
        store.set_case_status(case_id, "ready")
        store.audit(case_id, "pipeline.run.finished",
                    {"findings": len(store.list_findings(case_id))})
    except Exception as e:
        store.set_case_status(case_id, "error")
        store.audit(case_id, "pipeline.error",
                    {"error": str(e), "trace": traceback.format_exc()[-1500:]})
