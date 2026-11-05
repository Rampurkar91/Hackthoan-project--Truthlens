"""Normalization helpers shared by extraction, contextual checks and correlation."""
from __future__ import annotations

import re
from datetime import date, datetime

HONORIFICS = {"mr", "mrs", "ms", "shri", "smt", "dr", "kumari"}

CITY_PINCODE = {
    "411038": "pune", "411001": "pune", "411004": "pune",
    "400001": "mumbai", "400002": "mumbai", "400050": "mumbai",
    "110001": "new delhi", "560001": "bengaluru", "600001": "chennai",
    "500001": "hyderabad", "700001": "kolkata", "380001": "ahmedabad",
}


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_name(name: str) -> dict:
    """Return tokens, initials-stripped key and display form."""
    s = re.sub(r"[^a-zA-Z .]", " ", name).lower()
    tokens = [t for t in s.replace(".", " ").split() if t and t not in HONORIFICS]
    full = [t for t in tokens if len(t) > 1]
    initials = [t[0] for t in tokens if len(t) == 1]
    return {"tokens": tokens, "full": full, "initials": initials,
            "key": " ".join(full), "display": norm_space(name)}


def names_match(a: str, b: str) -> tuple[bool, str]:
    """Tolerate initials, ordering and spacing; flag real differences."""
    from rapidfuzz import fuzz
    na, nb = normalize_name(a), normalize_name(b)
    if not na["full"] or not nb["full"]:
        return False, "missing name tokens"
    if na["key"] == nb["key"]:
        return True, "identical after normalization"
    sa, sb = set(na["full"]), set(nb["full"])
    if sa <= sb or sb <= sa:
        return True, "same name, middle name/initial omitted"
    ratio = fuzz.token_set_ratio(na["key"], nb["key"])
    if ratio >= 90 and (sa & sb):
        return True, f"minor spelling variation (similarity {ratio}%)"
    return False, f"different names (similarity {ratio}%)"


DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%m-%y", "%d %b %Y", "%d %B %Y"]


def parse_date(s: str) -> str | None:
    s = norm_space(s).replace(",", "")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def find_dates(s: str) -> list[str]:
    return re.findall(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", s)


def parse_amount(s: str) -> float | None:
    s = s.replace("₹", " ").replace("Rs.", " ").replace("Rs", " ").replace("INR", " ")
    m = re.search(r"(\d[\d,]*\.?\d*)", s)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def format_inr(v: float | None) -> str:
    if v is None:
        return "n/a"
    return "₹" + format(int(round(v)), ",d") if float(v).is_integer() else f"₹{v:,.2f}"


def extract_pincode(address: str) -> str | None:
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", address)
    return m.group(1) if m else None


def extract_city(address: str) -> str | None:
    a = address.lower()
    for city in set(CITY_PINCODE.values()):
        if city in a:
            return city
    pin = extract_pincode(address)
    if pin and pin in CITY_PINCODE:
        return CITY_PINCODE[pin]
    return None


def age_years(dob_iso: str, on: date | None = None) -> float | None:
    try:
        dob = date.fromisoformat(dob_iso)
    except ValueError:
        return None
    on = on or date.today()
    return (on - dob).days / 365.25


def bbox_union(boxes: list[list[float]]) -> list[float]:
    boxes = [b for b in boxes if b]
    if not boxes:
        return []
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)]


def bbox_overlap(a: list[float], b: list[float]) -> float:
    """Intersection over smaller area — good for 'region agrees with field'."""
    if not a or not b:
        return 0.0
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    smaller = min(aw * ah, bw * bh) or 1
    return inter / smaller
