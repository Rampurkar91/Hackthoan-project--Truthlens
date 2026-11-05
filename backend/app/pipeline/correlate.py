"""Step 6 — Cross-document correlation.

Builds the entity matrix (field × document) and detects conflicts, tolerating
harmless variation (initials, spacing, date formats). Visual forensic regions
that agree with a conflicted field escalate it to 'potential_manipulation'.
"""
from __future__ import annotations

from .normalize import (bbox_overlap, extract_city, extract_pincode,
                        format_inr, names_match, parse_date)

MATRIX_KEYS = [
    ("name", "Name"),
    ("dob", "Date of birth"),
    ("address", "Address"),
    ("income", "Income"),
]


def _cell(fields: list[dict], key: str, doc_id: str):
    if key == "income":
        f = next((f for f in fields if f["doc_id"] == doc_id and f["key"] == "income"), None)
        if f:
            return f
        return next((f for f in fields if f["doc_id"] == doc_id and f["key"] == "avg_salary"), None)
    return next((f for f in fields if f["doc_id"] == doc_id and f["key"] == key), None)


def build_matrix(documents: list[dict], fields: list[dict]) -> list[dict]:
    rows = []
    for key, label in MATRIX_KEYS:
        cells = []
        for d in documents:
            f = _cell(fields, key, d["id"])
            cells.append({
                "doc_id": d["id"],
                "value": f["value"] if f else None,
                "field_id": f["id"] if f else None,
                "page": f["page"] if f else None,
                "bbox": f["bbox"] if f else None,
                "derived": bool(f and f["key"] == "avg_salary"),
            })
        rows.append({"key": key, "label": label, "cells": cells, "status": "n/a"})
    return rows


def _status_name(vals):
    vals = [v for v in vals if v]
    if len(vals) < 2:
        return "n/a", ""
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            ok, why = names_match(vals[i]["value"], vals[j]["value"])
            if not ok:
                return "conflict", why
    return "consistent", "matches after tolerant entity matching"


def _status_dob(vals):
    vals = [v for v in vals if v]
    if len(vals) < 2:
        return "n/a", ""
    isos = {(v.get("normalized") or parse_date(v["value"]) or v["value"]) for v in vals}
    if len(isos) == 1:
        return "consistent", "identical after date normalization"
    return "conflict", "dates differ: " + " vs ".join(sorted(isos))


def _status_address(vals):
    vals = [v for v in vals if v]
    if len(vals) < 2:
        return "n/a", ""
    pins = {extract_pincode(v["value"]) for v in vals}
    cities = {extract_city(v["value"]) for v in vals}
    pins.discard(None)
    cities.discard(None)
    if len(pins) > 1 or len(cities) > 1:
        return "conflict", "different city/PIN code across documents"
    return "consistent", "same locality after normalization"


def _status_income(vals, fields):
    declared = next((v for v in vals if v and not v.get("derived")), None)
    derived = next((v for v in vals if v and v.get("derived")), None)
    if not declared or not derived:
        return "n/a", ""
    try:
        d = float(declared["normalized"])
        m = float(derived["normalized"]) * 12
    except (ValueError, TypeError, KeyError):
        return "n/a", ""
    if m <= 0:
        return "n/a", ""
    ratio = m / d
    if ratio < 0.7:
        return "check", (f"statement credits annualize to {format_inr(m)}, "
                         f"only {ratio * 100:.0f}% of declared {format_inr(d)}")
    if ratio > 1.6:
        return "check", (f"statement credits annualize to {format_inr(m)}, "
                         f"well above declared {format_inr(d)}")
    return "consistent", "declared income supported by statement credits"


def correlate(documents: list[dict], fields: list[dict],
              visual_regions: dict[str, list[dict]]) -> dict:
    """Return {matrix, conflicts:[finding drafts]}."""
    matrix = build_matrix(documents, fields)
    conflicts = []

    def evidence_for(vals):
        ev = []
        for v in vals:
            if v and v.get("field_id"):
                ev.append({"doc_id": v["doc_id"], "page": v["page"], "bbox": v["bbox"],
                           "field_id": v["field_id"], "value": v["value"]})
        return ev

    def visual_support(vals):
        """Visual regions overlapping any conflicted field's pixels."""
        hits = []
        for v in vals:
            if not v or not v.get("bbox"):
                continue
            for r in visual_regions.get(v["doc_id"], []):
                if r["page"] == v["page"] and bbox_overlap(r["bbox"], v["bbox"]) > 0.25:
                    hits.append({"doc_id": v["doc_id"], **r})
        return hits

    for row in matrix:
        vals = []
        for c in row["cells"]:
            if c["value"] is None:
                vals.append(None)
                continue
            f = next((f for f in fields if f["id"] == c["field_id"]), None)
            vals.append({**c, "normalized": f["normalized"] if f else ""})

        status_fn = {"name": _status_name, "dob": _status_dob,
                     "address": _status_address,
                     "income": lambda v: _status_income(v, fields)}[row["key"]]
        status, why = status_fn(vals)
        row["status"] = status
        row["note"] = why
        if status not in ("conflict", "check"):
            continue

        present = [v for v in vals if v]
        support = visual_support(present) if status == "conflict" else []
        level = "potential_manipulation" if support else "inconsistent"
        values_txt = "; ".join(
            f"{next(d['filename'] for d in documents if d['id'] == v['doc_id'])}: {v['value']}"
            for v in present)
        title = {"name": "Name differs across documents",
                 "dob": "Date of birth conflict across documents",
                 "address": "Address conflict across documents",
                 "income": "Declared income not supported by bank credits"}[row["key"]]
        conflicts.append({
            "level": level, "category": "cross_document", "kind": f"x_{row['key']}",
            "doc_id": present[0]["doc_id"] if present else None,
            "title": title, "confidence": 0.9 if status == "conflict" else 0.7,
            "evidence": evidence_for(present),
            "facts": {"field": row["key"], "values": values_txt, "reason": why,
                      "matrix_status": status,
                      "visual_support": [
                          {"doc_id": s["doc_id"], "kind": s["kind"], "page": s["page"],
                           "bbox": s["bbox"], "score": s["score"]} for s in support]},
        })
        # attach supporting visual evidence refs for click-to-trace
        for s in support:
            conflicts[-1]["evidence"].append(
                {"doc_id": s["doc_id"], "page": s["page"], "bbox": s["bbox"],
                 "label": f"visual:{s['kind']}", "value": ""})
    return {"matrix": matrix, "conflicts": conflicts}
