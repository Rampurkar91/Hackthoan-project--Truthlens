"""Demo document generator — synthetic 'genuine' and 'tampered' case files.

Everything is drawn locally with Pillow (no external assets except two
AI-generated fictional portraits). Documents are rendered as scanned-style
JPEGs / image PDFs with a uniform noise floor, so the forensic engine has a
realistic signal to work with:

  genuine set   — application form, ID proof, bank statement, all consistent
  tampered set  — ID photo swapped + DOB overwritten; statement address &
                  DOB overwritten + bank stamp copy-moved; declared income
                  inflated on the form (matches the hackathon deck example)

All names, numbers and addresses are fictional.
"""
from __future__ import annotations

import io
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..config import SAMPLES_CACHE_DIR

ASSETS = Path(__file__).resolve().parent / "assets"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
if not FONT_DIR.exists():  # portable fallback (macOS / other Linux layouts)
    for cand in ("/usr/share/fonts/TTF", "/Library/Fonts", "/System/Library/Fonts"):
        if Path(cand).exists():
            FONT_DIR = Path(cand)
            break


def font(size: int, bold=False, serif=False) -> ImageFont.FreeTypeFont:
    name = ("DejaVuSerif.ttf" if serif else
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    p = FONT_DIR / name
    if not p.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(p), size)


A4 = (1240, 1754)
CARD = (1000, 630)
BODY = 26
INK = (20, 22, 28)
PAPER = (250, 250, 247)


def _portrait(name: str, size: tuple[int, int]) -> Image.Image:
    p = ASSETS / name
    if p.exists():
        img = Image.open(p).convert("RGB")
        return img.resize(size, Image.LANCZOS)
    # fallback: neutral placeholder avatar
    img = Image.new("RGB", size, (210, 214, 220))
    d = ImageDraw.Draw(img)
    w, h = size
    d.ellipse((w * 0.3, h * 0.15, w * 0.7, h * 0.55), fill=(150, 155, 165))
    d.ellipse((w * 0.15, h * 0.6, w * 0.85, h * 1.3), fill=(150, 155, 165))
    return img


def _signature(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
               seed: int = 7, color=(25, 35, 120)):
    rng = random.Random(seed)
    p1, p2, p3 = rng.uniform(2, 4), rng.uniform(5, 8), rng.uniform(0, 6.28)
    a1, a2 = h * 0.28, h * 0.12
    pts = []
    for t in np.linspace(0, 1, 160):
        px = x + t * w
        py = y + h / 2 + a1 * math.sin(p1 * t * math.pi + p3) + a2 * math.sin(p2 * t * math.pi)
        py += (t - 0.5) * h * 0.15
        pts.append((px, py))
    draw.line(pts, fill=color, width=3, joint="curve")
    draw.line([(x + w * 0.1, y + h * 0.8), (x + w * 0.95, y + h * 0.72)],
              fill=color, width=2)


def _scan(img: Image.Image, noise: float = 2.2, quality: int = 92) -> Image.Image:
    arr = np.array(img).astype(np.float32)
    arr += np.random.default_rng(42).normal(0, noise, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _save_jpg(img: Image.Image, path: Path, quality=92):
    img.save(path, "JPEG", quality=quality)


def _save_pdf(img: Image.Image, path: Path):
    img.save(path, "PDF", resolution=150.0)


# ------------------------------------------------------------ application --
def application_form(path: Path, income: str = "Rs. 9,60,000"):
    img = Image.new("RGB", A4, PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, A4[0] - 40, A4[1] - 40), outline=(120, 125, 135), width=2)
    d.text((80, 70), "UNITY BANK", font=font(40, bold=True), fill=(15, 40, 90))
    d.text((80, 130), "Loan Application Form", font=font(32, bold=True), fill=INK)
    d.text((80, 185), "Application No. LA-2025-04117", font=font(22), fill=(70, 75, 85))
    img.paste(_portrait("person_a.jpg", (210, 250)), (950, 70))
    d.rectangle((950, 70, 1160, 320), outline=(120, 125, 135), width=2)

    rows = [
        ("Applicant Name", "Rahul K. Sharma"),
        ("Date of Birth", "12-04-1991"),
        ("Address", "12 MG Road, Pune 411038"),
        ("Annual Income", income),
        ("PAN", "ABCPS1234K"),
        ("Phone", "98220 12345"),
        ("Email", "rahul.sharma@example.com"),
        ("Employment", "Salaried - Acme Corp"),
        ("Requested Amount", "Rs. 5,00,000"),
    ]
    y = 320
    for label, value in rows:
        d.text((80, y), f"{label}: {value}", font=font(BODY), fill=INK)
        y += 62

    d.text((80, 950), "Declaration", font=font(26, bold=True), fill=INK)
    d.text((80, 995), "I declare that the information provided above is true and correct to the",
           font=font(21), fill=(60, 65, 75))
    d.text((80, 1030), "best of my knowledge. I authorize the bank to verify these details with",
           font=font(21), fill=(60, 65, 75))
    d.text((80, 1065), "the relevant authorities and credit bureaus.", font=font(21), fill=(60, 65, 75))

    _signature(d, 90, 1480, 280, 90)
    d.text((90, 1590), "Signature", font=font(22), fill=INK)
    d.text((800, 1590), "Date: 15-10-2025", font=font(BODY), fill=INK)
    _save_pdf(_scan(img), path)


# ------------------------------------------------------------------- ID ----
def id_proof(path: Path) -> dict:
    img = Image.new("RGB", CARD, (245, 246, 248))
    d = ImageDraw.Draw(img)
    d.rectangle((8, 8, CARD[0] - 8, CARD[1] - 8), outline=(30, 60, 120), width=4)
    d.text((300, 25), "GOVERNMENT OF INDIA", font=font(30, bold=True), fill=(15, 40, 90))
    d.text((390, 72), "IDENTITY CARD", font=font(24, bold=True), fill=INK)
    photo_box = (40, 130, 280, 420)
    img.paste(_portrait("person_a.jpg", (240, 290)), (40, 130))
    d.rectangle(photo_box, outline=(120, 125, 135), width=2)

    fields = [
        ("Name", "Rahul Sharma"),
        ("DOB", "12-04-1991"),
        ("Address", "Pune 411038"),
        ("ID No", "1234 5678 9012"),
    ]
    boxes = {}
    y = 150
    for label, value in fields:
        lab = f"{label}: "
        d.text((320, y), lab, font=font(24), fill=INK)
        lw = d.textlength(lab, font=font(24))
        d.text((320 + lw, y), value, font=font(24), fill=INK)
        vw = d.textlength(value, font=font(24))
        boxes[label] = [320 + lw, y, vw, 34]
        y += 62
    d.text((320, 430), "Valid till: 12-04-2031", font=font(24), fill=INK)
    _signature(d, 690, 470, 240, 80)
    d.text((750, 565), "Signature", font=font(18), fill=INK)
    scanned = _scan(img)
    _save_jpg(scanned, path)
    return {"photo_box": photo_box, "dob_box": boxes["DOB"], "size": CARD}


# ------------------------------------------------------------- statement ---
def bank_statement(path: Path, address: str = "Pune 411038", dob: str = "12-04-1991"):
    img = Image.new("RGB", A4, PAPER)
    d = ImageDraw.Draw(img)
    d.text((80, 60), "UNITY BANK", font=font(38, bold=True), fill=(15, 40, 90))
    d.text((80, 115), "Account Statement", font=font(30, bold=True), fill=INK)
    d.text((80, 170), "Statement Period: 01-04-2025 to 30-09-2025", font=font(24), fill=INK)

    info = [
        ("Customer Name", "Rahul Sharma"),
        ("DOB (KYC)", dob),
        ("Address", address),
        ("Account Number", "001234567890"),
        ("IFSC", "UTIB0000123"),
    ]
    y = 240
    for label, value in info:
        d.text((80, y), f"{label}: {value}", font=font(24), fill=INK)
        y += 48

    # transactions table (no ruling lines: clean typeset)
    cols = [80, 260, 680, 860, 1030]
    headers = ["Date", "Description", "Debit", "Credit", "Balance"]
    y = 560
    for c, h in zip(cols, headers):
        d.text((c, y), h, font=font(22, bold=True), fill=INK)
    y += 50
    txns = [
        ("01-04-2025", "SALARY CREDIT ACME CORP", None, 34000),
        ("03-04-2025", "UPI PAYMENT GROCERY", 4200, None),
        ("05-04-2025", "RENT TRANSFER", 15000, None),
        ("01-05-2025", "SALARY CREDIT ACME CORP", None, 34500),
        ("04-05-2025", "UTILITY BILL PAYMENT", 2300, None),
        ("01-06-2025", "SALARY CREDIT ACME CORP", None, 33800),
        ("06-06-2025", "ATM WITHDRAWAL", 5000, None),
        ("01-07-2025", "SALARY CREDIT ACME CORP", None, 34200),
        ("05-07-2025", "UPI PAYMENT FUEL", 1800, None),
        ("01-08-2025", "SALARY CREDIT ACME CORP", None, 34000),
        ("04-08-2025", "INSURANCE PREMIUM", 6500, None),
        ("01-09-2025", "SALARY CREDIT ACME CORP", None, 34500),
        ("05-09-2025", "RENT TRANSFER", 15000, None),
        ("28-09-2025", "INTEREST CREDIT", None, 410),
    ]
    balance = 100000
    fnum = font(21)
    for date, desc, debit, credit in txns:
        balance += (credit or 0) - (debit or 0)
        d.text((cols[0], y), date, font=fnum, fill=INK)
        d.text((cols[1], y), desc, font=fnum, fill=INK)
        if debit:
            d.text((cols[2], y), f"{debit:,.2f}", font=fnum, fill=(140, 30, 30))
        if credit:
            d.text((cols[3], y), f"{credit:,.2f}", font=fnum, fill=(20, 100, 45))
        d.text((cols[4], y), f"{balance:,.2f}", font=fnum, fill=INK)
        y += 46

    d.text((80, y + 30), f"Closing Balance: {balance:,.2f}", font=font(24, bold=True), fill=INK)

    # circular branch stamp (graphic; copy-move target in the tampered set)
    stamp_box = _stamp(img, (950, 1480))
    _signature(d, 90, 1480, 260, 85, seed=7)
    d.text((90, 1585), "Authorised Signature", font=font(22), fill=INK)
    scanned = _scan(img)
    _save_pdf(scanned, path)
    return {"stamp_box": stamp_box, "size": A4}


def _stamp(img: Image.Image, center: tuple[int, int]) -> tuple[int, int, int, int]:
    d = ImageDraw.Draw(img)
    cx, cy = center
    r = 88
    col = (35, 55, 160)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=4)
    d.ellipse((cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14), outline=col, width=2)
    d.text((cx - 62, cy - 34), "UNITY BANK", font=font(17, bold=True), fill=col)
    d.text((cx - 66, cy - 6), "PUNE BRANCH", font=font(15, bold=True), fill=col)
    d.text((cx - 40, cy + 22), "* 411038 *", font=font(14, bold=True), fill=col)
    return (cx - r, cy - r, cx + r, cy + r)


# ------------------------------------------------------------- tampering ---
def _overwrite(img: Image.Image, box, new_text: str, size: int = 31,
               bg=(245, 246, 248), dy: int = 2):
    """Erase a value and re-type it in a different font/size/baseline.

    The patch is pasted WITHOUT the scan noise floor and re-compressed once,
    exactly like a real cut-and-paste edit on a scanned document.
    """
    x, y, w, h = box
    pad = 6
    d = ImageDraw.Draw(img)
    d.rectangle((x - pad, y - pad, x + w + pad + 30, y + h + pad), fill=bg)
    d.text((x, y + dy - 4), new_text, font=font(size, serif=True), fill=INK)


def tampered_id(genuine_path: Path, out_path: Path, info: dict):
    img = Image.open(genuine_path).convert("RGB")
    # 1) overwrite DOB 12-04-1991 -> 21-04-1991 (serif, larger, shifted)
    _overwrite(img, info["dob_box"], "21-04-1991", size=31, bg=(245, 246, 248))
    # 2) swap the photograph (different person, smoothed, no scan noise)
    from PIL import ImageFilter
    pb = info["photo_box"]
    replacement = _portrait("person_b.jpg", (pb[2] - pb[0], pb[3] - pb[1]))
    replacement = replacement.filter(ImageFilter.GaussianBlur(0.6))
    img.paste(replacement, (pb[0], pb[1]))
    _save_jpg(img, out_path, quality=90)


def tampered_statement(genuine_path: Path, out_path: Path, info: dict):
    # genuine statement was saved as image-PDF; reopen its pixels
    import pymupdf as fitz
    with fitz.open(genuine_path) as pdf:
        pix = pdf[0].get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    # locate the two value strings by re-drawing geometry: we know the layout
    # info rows start at y=240, step 48, font 24, x=80.
    d = ImageDraw.Draw(img)
    f24 = font(24)
    dob_label_w = d.textlength("DOB (KYC): ", font=f24)
    addr_label_w = d.textlength("Address: ", font=f24)
    dob_y = 240 + 48
    addr_y = 240 + 96
    dob_w = d.textlength("12-04-1991", font=f24)
    addr_w = d.textlength("Pune 411038", font=f24)
    _overwrite(img, (80 + dob_label_w, dob_y, dob_w, 32), "21-04-1991",
               size=33, bg=PAPER)
    _overwrite(img, (80 + addr_label_w, addr_y, addr_w, 32), "Mumbai 400001",
               size=33, bg=PAPER)

    # copy-move: duplicate the branch stamp to a second location
    sb = info["stamp_box"]
    stamp = img.crop(sb)
    img.paste(stamp, (430, sb[1]))
    _save_pdf(img, out_path)


# ------------------------------------------------------------------ build --
def build_set(variant: str) -> list[dict]:
    """Generate (or reuse cached) sample files. Returns [{name, path}]."""
    assert variant in ("genuine", "tampered")
    out_dir = SAMPLES_CACHE_DIR / variant
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = out_dir / ".complete"
    files = [
        {"name": "application_form.pdf", "path": out_dir / "application_form.pdf"},
        {"name": "id_proof.jpg", "path": out_dir / "id_proof.jpg"},
        {"name": "bank_statement.pdf", "path": out_dir / "bank_statement.pdf"},
    ]
    if marker.exists() and all(f["path"].exists() for f in files):
        return [{"name": f["name"], "path": str(f["path"])} for f in files]

    if variant == "genuine":
        application_form(files[0]["path"], income="Rs. 4,10,000")
        id_proof(files[1]["path"])
        bank_statement(files[2]["path"])
    else:
        application_form(files[0]["path"], income="Rs. 9,60,000")
        id_info = id_proof(out_dir / "_id_genuine.jpg")
        tampered_id(out_dir / "_id_genuine.jpg", files[1]["path"], id_info)
        st_info = bank_statement(out_dir / "_statement_genuine.pdf")
        tampered_statement(out_dir / "_statement_genuine.pdf", files[2]["path"], st_info)
    marker.write_text("ok")
    return [{"name": f["name"], "path": str(f["path"])} for f in files]


if __name__ == "__main__":
    for v in ("genuine", "tampered"):
        for f in build_set(v):
            print(v, f["name"], f["path"])
