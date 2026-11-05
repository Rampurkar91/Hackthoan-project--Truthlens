"""Step 3 — Structure fields.

Turns OCR lines into typed fields (name, dob, address, income, PAN, account…).
Lines are first grouped into visual rows so 'Label:' and 'value' boxes are
joined even when OCR splits them. Every field keeps page, bounding box and
OCR confidence for click-to-trace.
"""
from __future__ import annotations

import re

from .normalize import (bbox_union, find_dates, norm_space, normalize_name,
                        parse_amount, parse_date)

NAME_LABELS = ["applicant name", "customer name", "holder name", "full name", "name"]
NAME_EXCLUDE = ["bank name", "branch name", "file name", "company name", "employer name"]
DOB_LABELS = ["date of birth", "dob", "birth date", "d.o.b"]
ADDR_LABELS = ["address", "residential address", "permanent address"]
INCOME_LABELS = ["annual income", "gross annual income", "yearly income", "income"]


def group_rows(lines: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for l in sorted(lines, key=lambda t: (t["bbox"][1], t["bbox"][0])):
        placed = False
        for row in rows:
            r0 = row[0]["bbox"]
            overlap = (min(r0[1] + r0[3], l["bbox"][1] + l["bbox"][3])
                       - max(r0[1], l["bbox"][1]))
            if overlap > 0.5 * min(r0[3], l["bbox"][3]):
                row.append(l)
                placed = True
                break
        if not placed:
            rows.append([l])
    for row in rows:
        row.sort(key=lambda t: t["bbox"][0])
    rows.sort(key=lambda r: r[0]["bbox"][1])
    return rows


def _row_text(row: list[dict]) -> str:
    return norm_space(" ".join(l["text"] for l in row))


def _row_score(row: list[dict]) -> float:
    return round(sum(l["score"] for l in row) / len(row), 4)


def _split_label_value(text: str) -> tuple[str, str] | None:
    if ":" in text:
        label, value = text.split(":", 1)
        return norm_space(label).lower(), norm_space(value)
    return None


def _value_bbox(row: list[dict]) -> list[float]:
    """Bbox of the value part: boxes after the one containing ':'."""
    if len(row) == 1:
        l = row[0]
        x, y, w, h = l["bbox"]
        cut = l["text"].find(":")
        if cut < 0:
            return l["bbox"]
        frac = (cut + 1) / max(len(l["text"]), 1)
        return [round(x + w * frac, 1), y, round(w * (1 - frac), 1), h]
    idx = next((i for i, l in enumerate(row) if ":" in l["text"]), None)
    if idx is None:
        return bbox_union([l["bbox"] for l in row])
    first = row[idx]
    if first["text"].rstrip().endswith(":"):
        rest = row[idx + 1:]
        return bbox_union([l["bbox"] for l in rest]) if rest else first["bbox"]
    # colon inside a merged box: approximate split, then add following boxes
    x, y, w, h = first["bbox"]
    cut = first["text"].find(":")
    frac = (cut + 1) / max(len(first["text"]), 1)
    part = [round(x + w * frac, 1), y, round(w * (1 - frac), 1), h]
    return bbox_union([part] + [l["bbox"] for l in row[idx + 1:]])


def extract_fields(ocr_pages: dict[int, list[dict]], doc_type: str) -> list[dict]:
    fields: list[dict] = []
    seen: set[str] = set()

    def add(key, label, value, row, page, normalized="", bbox=None):
        value = norm_space(value)
        if not value or key in seen:
            return
        seen.add(key)
        fields.append({
            "key": key, "label": label, "value": value, "normalized": normalized,
            "page": page, "bbox": bbox or _value_bbox(row),
            "confidence": _row_score(row),
        })

    salary_credits: list[dict] = []

    for page, lines in ocr_pages.items():
        rows = group_rows(lines)
        for i, row in enumerate(rows):
            text = _row_text(row)
            low = text.lower()
            # OCR often drops spaces ("DateofBirth:"): match space-stripped too
            low_ns = low.replace(" ", "")
            lv = _split_label_value(text)
            label_ns = lv[0].replace(" ", "") if lv else ""

            # ---- name ----
            if lv and not any(x.replace(" ", "") in label_ns for x in NAME_EXCLUDE):
                label, value = lv
                if any(label_ns == k.replace(" ", "") or label_ns.startswith(k.replace(" ", ""))
                       for k in NAME_LABELS) and value:
                    if re.search(r"[A-Za-z]{2,}", value):
                        add("name", "Name", value, row, page,
                            normalized=normalize_name(value)["key"])

            # ---- dob ----
            if any(k.replace(" ", "") in low_ns for k in DOB_LABELS):
                dates = find_dates(text)
                if dates:
                    iso = parse_date(dates[0])
                    add("dob", "Date of birth", dates[0], row, page, normalized=iso or "")

            # ---- address (may continue on the next row) ----
            if lv and any(label_ns == k.replace(" ", "") or label_ns.startswith(k.replace(" ", ""))
                          for k in ADDR_LABELS):
                value = lv[1]
                bbox = _value_bbox(row)
                if i + 1 < len(rows):
                    nxt = rows[i + 1]
                    ntext = _row_text(nxt)
                    gap = nxt[0]["bbox"][1] - (row[0]["bbox"][1] + row[0]["bbox"][3])
                    if ":" not in ntext and len(ntext) < 60 and -5 < gap < 45:
                        value = norm_space(value + ", " + ntext)
                        bbox = bbox_union([bbox] + [l["bbox"] for l in nxt])
                add("address", "Address", value, row, page, bbox=bbox)

            # ---- income ----
            if lv and any(label_ns == k.replace(" ", "") for k in INCOME_LABELS):
                amt = parse_amount(lv[1])
                if amt:
                    add("income", "Annual income", lv[1], row, page, normalized=str(amt))

            # ---- PAN / Aadhaar / account / IFSC ----
            m = re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", text)
            if m:
                add("pan", "PAN", m.group(0), row, page, normalized=m.group(0))
            m = re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\b", text)
            if m and not any(x in low.replace(" ", "") for x in ("account", "idno", "validtill")):
                add("aadhaar", "Aadhaar", m.group(0), row, page,
                    normalized=m.group(0).replace(" ", ""))
            if lv and "account" in lv[0] and re.search(r"\d{6,}", lv[1]):
                add("account_number", "Account number", lv[1], row, page,
                    normalized=re.sub(r"\D", "", lv[1]))
            m = re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", text)
            if m:
                add("ifsc", "IFSC", m.group(0), row, page, normalized=m.group(0))

            # ---- salary credits on statements ----
            if "salary" in low and ("credit" in low or doc_type == "bank_statement"):
                amounts = re.findall(r"\d[\d,]*\.\d{2}|\d[\d,]{3,}", text)
                parsed = [parse_amount(a) for a in amounts]
                parsed = [p for p in parsed if p and p >= 1000]
                if parsed:
                    # credit column = largest amount that is not the running
                    # balance (the last number on the row)
                    amt = max(parsed[:-1]) if len(parsed) > 1 else parsed[0]
                    salary_credits.append({"value": amt, "page": page,
                                           "bbox": bbox_union([l["bbox"] for l in row]),
                                           "text": text, "score": _row_score(row)})

    if salary_credits:
        avg = sum(c["value"] for c in salary_credits) / len(salary_credits)
        fields.append({
            "key": "avg_salary", "label": "Avg monthly salary credit",
            "value": f"₹{avg:,.0f} ({len(salary_credits)} credits)",
            "normalized": str(round(avg, 2)), "page": salary_credits[0]["page"],
            "bbox": salary_credits[0]["bbox"],
            "confidence": round(sum(c["score"] for c in salary_credits) / len(salary_credits), 3),
        })
    return fields
