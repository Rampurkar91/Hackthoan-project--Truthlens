"""Explanation engine — 'Explain' in Observe → Correlate → Explain.

Deterministic, template-grounded explanations by default (fully offline and
reproducible for the demo). If TRUTHLENS_LLM_URL / TRUTHLENS_LLM_KEY are set,
an OpenAI-compatible chat endpoint is asked to rewrite the explanation; the
structured facts and verification steps always come from the rule engine, so
the LLM can phrase but never invent evidence.
"""
from __future__ import annotations

import json
import urllib.request

from ..config import LLM_KEY, LLM_MODEL, LLM_URL

VISUAL_KINDS = {
    "ela": ("Compression history differs in this region",
            "Error-level analysis re-compresses the page and measures the residual. "
            "This region's residual deviates strongly from the page median, which "
            "happens when content was pasted or re-saved at a different quality.",
            ["Request the original digital file and compare its compression metadata",
             "Ask the issuing authority to confirm the document's content"]),
    "noise": ("Background noise break around this region",
              "Scanned pages carry a uniform sensor/JPEG noise floor. This region is "
              "significantly {direction} than the surrounding background, a typical "
              "side-effect of erasing and re-typing content or pasting a patch.",
              ["Inspect the physical document under magnification",
               "Re-scan the document and check whether the anomaly persists"]),
    "font": ("Font size / baseline drift on this text",
             "The glyph box for “{line}” differs from neighbouring text "
             "({metric}). Genuine forms are typeset uniformly; a drifted size or "
             "baseline suggests the value was added or replaced later.",
             ["Compare with a genuine specimen of the same form/template",
              "Verify the field value with the issuing authority"]),
    "copymove": ("Duplicated image block detected",
                 "ORB features match another part of the same page with a consistent "
                 "displacement ({matched_keypoints} keypoints). A block of pixels appears "
                 "twice, which is characteristic of copy-move editing (e.g. a duplicated "
                 "stamp, logo or row).",
                 ["Check whether the duplicated element should legitimately repeat",
                  "Request the source file to inspect layers/objects"]),
    "photo": ("Photo region shows replacement signals",
              "The ID photo area has a different compression/noise signature than the "
              "rest of the card ({method}). This is consistent with the photograph "
              "having been swapped after the card was produced.",
              ["Verify identity in person or via a trusted video KYC",
               "Confirm the photo with the issuing authority's records"]),
    "signature": ("Signature overlaps printed text",
                  "The ink region above the signature anchor overlaps printed text "
                  "({overlaps_text}). Genuine signatures are placed in the reserved "
                  "space; overlap can indicate a pasted signature image.",
                  ["Compare with a known genuine signature specimen",
                   "Check signature placement on a genuine specimen of the form"]),
}

CONTEXTUAL_KINDS = {
    "dob_unparseable": ("The value “{value}” is not a recognizable date format.",
                        ["Confirm the date of birth against the original record"]),
    "dob_implausible": ("The date of birth {dob} implies an age of {implied_age} years, which is outside a plausible range.",
                        ["Re-check the OCR reading against the page image",
                         "Verify the date with the issuing authority"]),
    "dob_minor": ("The date of birth {dob} implies the applicant is {implied_age} years old — under 18.",
                  ["Confirm eligibility rules for this product",
                   "Verify the date of birth from a primary record"]),
    "pincode_city": ("The address names {city}, but PIN code {pincode} belongs to {expected_city}.",
                     ["Confirm the current address with the applicant",
                      "Check a recent utility bill or bank record"]),
    "pan_format": ("“{value}” does not match the PAN pattern AAAAA9999A.",
                   ["Verify the PAN on the income-tax portal"]),
    "aadhaar_leading": ("UIDAI Aadhaar numbers never start with 0 or 1; this one does.",
                        ["Verify the Aadhaar via UIDAI offline XML / QR verification"]),
}

CROSS_KINDS = {
    "x_name": ("Names differ beyond harmless variation: {values}. {reason}.",
               ["Confirm legal name from a primary ID",
                "Check for marriage/name-change documentation"]),
    "x_dob": ("Date of birth does not agree across documents: {values}. {reason}.",
              ["Verify the date of birth against the birth certificate or primary ID",
               "Check whether one document was re-issued with corrected details"]),
    "x_address": ("Addresses point to different localities: {values}. {reason}.",
                  ["Ask which address is current and request a supporting proof",
                   "Check whether the applicant recently relocated"]),
    "x_income": ("Declared income is not supported by bank credits. {reason}.",
                 ["Request salary slips or Form 16 for the declared amount",
                  "Ask about other accounts or variable pay components"]),
}


def _fmt(template: str, facts: dict) -> str:
    try:
        return template.format(**facts)
    except (KeyError, IndexError):
        return template


def explain_finding(f: dict) -> tuple[str, list[str]]:
    """Return (explanation, verification_steps) for a finding draft."""
    kind, facts = f.get("kind", ""), f.get("facts", {})
    category = f["category"]

    if category == "visual_forensic":
        title, body, steps = VISUAL_KINDS.get(kind, ("Visual anomaly detected", "A forensic signal fired on this region.", ["Manual inspection recommended"]))
        if kind == "font":
            d = facts.get("details", {})
            facts = {**facts, "line": d.get("line", "this text"),
                     "metric": (f"height {d.get('line_height')}px vs row median "
                                f"{d.get('row_median', d.get('page_median'))}px"
                                + (f", baseline shifted {d.get('baseline_shift_px')}px"
                                   if d.get("baseline_shift_px") else ""))}
        if kind == "noise":
            facts = {**facts, "direction": facts.get("direction", "smoother")}
        if kind == "copymove":
            facts = {**facts, "matched_keypoints": facts.get("details", {}).get("matched_keypoints", "many")}
        if kind == "photo":
            facts = {**facts, "method": facts.get("details", {}).get("method", "ELA/noise")}
        if kind == "signature":
            facts = {**facts, "overlaps_text": ", ".join(facts.get("details", {}).get("overlaps_text", []))}
        return _fmt(body, facts), list(steps)

    if category == "contextual":
        body, steps = CONTEXTUAL_KINDS.get(kind, ("A contextual rule fired.", ["Manual review recommended"]))
        return _fmt(body, facts), list(steps)

    if category == "cross_document":
        body, steps = CROSS_KINDS.get(kind, ("Values conflict across documents: {values}.", ["Verify against primary records"]))
        text = _fmt(body, facts)
        if facts.get("visual_support"):
            kinds = ", ".join(sorted({s["kind"] for s in facts["visual_support"]}))
            text += (f" Visual forensics independently flags the same region ({kinds}), "
                     "so several signals agree — escalated to potential manipulation. "
                     "A human reviewer must make the final call.")
        return text, list(steps)

    if category == "combined":
        return f["explanation"], f.get("verification", [])

    return "Finding requires review.", ["Manual review recommended"]


def llm_refine(explanation: str, facts: dict, steps: list[str]) -> str:
    """Optional: ask an OpenAI-compatible endpoint to polish the wording."""
    if not LLM_URL or not LLM_KEY:
        return explanation
    try:
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content":
                 "You are a document-forensics analyst. Rewrite the explanation clearly "
                 "for a reviewer in 2-3 sentences. Never claim confirmed fraud; findings "
                 "are observations requiring human review. Use only the given facts."},
                {"role": "user", "content": json.dumps(
                    {"explanation": explanation, "facts": facts, "verify_next": steps})},
            ],
            "max_tokens": 220, "temperature": 0.2,
        }
        req = urllib.request.Request(
            LLM_URL.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip() or explanation
    except Exception:
        return explanation
