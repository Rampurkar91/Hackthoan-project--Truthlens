"""Document classification (rule + keyword scoring over OCR text).

Lightweight and explainable: the score breakdown is stored with the document
so a reviewer can see *why* a label was chosen.
"""
from __future__ import annotations

KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "application_form": [
        ("application form", 3), ("loan application", 3), ("applicant", 2),
        ("annual income", 2), ("declaration", 1.5), ("application no", 2),
        ("requested amount", 2), ("employment", 1), ("form", 0.5),
    ],
    "id_proof": [
        ("identity card", 3), ("government of india", 2.5), ("id card", 3),
        ("aadhaar", 3), ("permanent account number", 3), ("pan card", 3),
        ("id no", 2), ("date of birth", 1), ("dob", 1), ("holder", 1),
    ],
    "bank_statement": [
        ("account statement", 3), ("bank statement", 3), ("opening balance", 2.5),
        ("closing balance", 2.5), ("account number", 2), ("salary credit", 2.5),
        ("debit", 1.5), ("credit", 1.5), ("balance", 1), ("ifsc", 1.5),
        ("statement period", 2.5), ("transaction", 1),
    ],
}

LABELS = {
    "application_form": "Application form",
    "id_proof": "ID proof",
    "bank_statement": "Bank statement",
    "unknown": "Unclassified",
}


def classify(ocr_pages: dict[int, list[dict]]) -> dict:
    text = " ".join(l["text"] for lines in ocr_pages.values() for l in lines).lower()
    # OCR sometimes drops spaces in bold headers ("IDENTITYCARD"): match both
    # the spaced text and a space-stripped variant.
    nospace = text.replace(" ", "")
    scores = {}
    for dtype, kws in KEYWORDS.items():
        hits = [(kw, w) for kw, w in kws
                if kw in text or kw.replace(" ", "") in nospace]
        scores[dtype] = {"score": round(sum(w for _, w in hits), 2),
                         "matched": [kw for kw, _ in hits]}
    best = max(scores, key=lambda k: scores[k]["score"])
    total = sum(s["score"] for s in scores.values()) or 1.0
    if scores[best]["score"] < 2:
        return {"doc_type": "unknown", "confidence": 0.3, "scores": scores,
                "label": LABELS["unknown"]}
    return {"doc_type": best, "confidence": round(min(0.99, scores[best]["score"] / total), 2),
            "scores": scores, "label": LABELS[best]}
