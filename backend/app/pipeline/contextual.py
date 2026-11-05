"""Step 5 — Contextual checks inside a single document (rule engine)."""
from __future__ import annotations

import re
from datetime import date

from .normalize import (CITY_PINCODE, age_years, extract_city, extract_pincode,
                        parse_date)


def check_document(doc: dict, fields: list[dict]) -> list[dict]:
    """Return finding drafts (level 'observed' or 'inconsistent')."""
    out = []
    by_key = {f["key"]: f for f in fields}

    def ev(f):
        return [{"doc_id": doc["id"], "page": f["page"], "bbox": f["bbox"],
                 "field_id": f["id"], "label": f["label"], "value": f["value"]}]

    dob = by_key.get("dob")
    if dob:
        iso = dob["normalized"] or parse_date(dob["value"])
        if not iso:
            out.append({"level": "inconsistent", "category": "contextual",
                        "kind": "dob_unparseable", "doc_id": doc["id"],
                        "title": "Date of birth could not be parsed",
                        "confidence": 0.7, "evidence": ev(dob),
                        "facts": {"value": dob["value"]}})
        else:
            age = age_years(iso)
            if age is not None and not (0 <= age <= 120):
                out.append({"level": "inconsistent", "category": "contextual",
                            "kind": "dob_implausible", "doc_id": doc["id"],
                            "title": "Implausible date of birth",
                            "confidence": 0.85, "evidence": ev(dob),
                            "facts": {"dob": iso, "implied_age": round(age, 1)}})
            elif age is not None and age < 18 and doc["doc_type"] in ("application_form", "bank_statement"):
                out.append({"level": "inconsistent", "category": "contextual",
                            "kind": "dob_minor", "doc_id": doc["id"],
                            "title": "Applicant appears to be a minor",
                            "confidence": 0.8, "evidence": ev(dob),
                            "facts": {"dob": iso, "implied_age": round(age, 1)}})

    addr = by_key.get("address")
    if addr:
        pin, city = extract_pincode(addr["value"]), extract_city(addr["value"])
        if pin and pin in CITY_PINCODE and city:
            expected = CITY_PINCODE[pin]
            if city != expected and expected not in city and city not in expected:
                out.append({"level": "inconsistent", "category": "contextual",
                            "kind": "pincode_city", "doc_id": doc["id"],
                            "title": "City and PIN code disagree",
                            "confidence": 0.8, "evidence": ev(addr),
                            "facts": {"city": city, "pincode": pin,
                                      "expected_city": expected}})

    pan = by_key.get("pan")
    if pan and not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", pan["value"].strip()):
        out.append({"level": "observed", "category": "contextual",
                    "kind": "pan_format", "doc_id": doc["id"],
                    "title": "PAN does not match the standard format",
                    "confidence": 0.6, "evidence": ev(pan),
                    "facts": {"value": pan["value"]}})

    aad = by_key.get("aadhaar")
    if aad:
        digits = re.sub(r"\D", "", aad["value"])
        if len(digits) == 12 and digits[0] in "01":
            out.append({"level": "observed", "category": "contextual",
                        "kind": "aadhaar_leading", "doc_id": doc["id"],
                        "title": "Aadhaar number starts with 0 or 1",
                        "confidence": 0.6, "evidence": ev(aad),
                        "facts": {"value": aad["value"],
                                  "note": "UIDAI numbers never begin with 0 or 1"}})
    return out
