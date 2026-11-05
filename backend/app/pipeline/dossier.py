"""Step 7 — Investigation dossier (PDF) with reportlab.

Sections: overview → documents & hashes → extracted fields → cross-document
matrix → findings (with highlighted region crops) → reviewer decisions →
limitations → audit-chain summary. Every finding references document, page
and bounding box so it traces back to the exact pixels.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .. import store
from ..config import CASES_DIR, LEVEL_LABELS
from .ingest import page_path

NAVY = colors.HexColor("#101828")
ACCENT = colors.HexColor("#2563eb")
AMBER = colors.HexColor("#b45309")
RED = colors.HexColor("#b91c1c")
BLUE = colors.HexColor("#1d4ed8")
GRAY = colors.HexColor("#475467")
LIGHT = colors.HexColor("#f2f4f7")

LEVEL_COLOR = {"observed": BLUE, "inconsistent": AMBER, "potential_manipulation": RED}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("TLTitle", parent=ss["Title"], fontSize=24, textColor=NAVY, spaceAfter=4))
    ss.add(ParagraphStyle("TLSub", parent=ss["Normal"], fontSize=11, textColor=GRAY, spaceAfter=14))
    ss.add(ParagraphStyle("TLH2", parent=ss["Heading2"], fontSize=14, textColor=NAVY,
                          spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("TLBody", parent=ss["Normal"], fontSize=9.5, leading=13, textColor=NAVY))
    ss.add(ParagraphStyle("TLSmall", parent=ss["Normal"], fontSize=8, leading=10.5, textColor=GRAY))
    ss.add(ParagraphStyle("TLMono", parent=ss["Normal"], fontName="Courier", fontSize=7.5,
                          leading=10, textColor=GRAY))
    return ss


def _esc(s: str) -> str:
    # Helvetica lacks the ₹ glyph; render it as "Rs." to avoid tofu boxes.
    return (str(s).replace("₹", "Rs.").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _region_crop(doc_id: str, case_id: str, page: int, bbox: list, pad: int = 40,
                 max_w: float = 150 * mm) -> Image | None:
    p = page_path(case_id, doc_id, page)
    if not p.exists() or not bbox:
        return None
    img = cv2.imread(str(p))
    if img is None:
        return None
    x, y, w, h = [int(v) for v in bbox]
    H, W = img.shape[:2]
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(W, x + w + pad), min(H, y + h + pad)
    crop = img[y1:y2, x1:x2].copy()
    cv2.rectangle(crop, (x - x1, y - y1), (x - x1 + w, y - y1 + h), (40, 40, 230), 3)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    buf = io.BytesIO()
    PILImage.fromarray(rgb).save(buf, "PNG")
    buf.seek(0)
    iw, ih = rgb.shape[1], rgb.shape[0]
    scale = min(max_w / iw, 70 * mm / ih, 1.0)
    return Image(buf, width=iw * scale, height=ih * scale)


def _page_thumb(case_id: str, doc_id: str, page: int, boxes: list[dict],
                width: float = 120 * mm) -> Image | None:
    p = page_path(case_id, doc_id, page)
    if not p.exists():
        return None
    img = cv2.imread(str(p))
    if img is None:
        return None
    for b in boxes:
        if not b.get("bbox"):
            continue
        x, y, w, h = [int(v) for v in b["bbox"]]
        color = {"potential_manipulation": (40, 40, 230), "inconsistent": (30, 130, 220),
                 "observed": (220, 150, 30)}.get(b.get("level", "observed"), (220, 150, 30))
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 4)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    buf = io.BytesIO()
    PILImage.fromarray(rgb).save(buf, "PNG")
    buf.seek(0)
    ih, iw = rgb.shape[:2]
    return Image(buf, width=width, height=width * ih / iw)


def build_dossier(case_id: str) -> Path:
    case = store.get_case(case_id)
    docs = store.list_documents(case_id)
    flds = store.list_fields(case_id)
    findings = store.list_findings(case_id)
    audit_rows = store.list_audit(case_id)
    chain = store.verify_audit(case_id)
    matrix_file = CASES_DIR / case_id / "matrix.json"
    matrix = json.loads(matrix_file.read_text()) if matrix_file.exists() else []

    store.audit(case_id, "dossier.generated", {"findings": len(findings)})

    out = CASES_DIR / case_id / "dossier.pdf"
    ss = _styles()
    doc = SimpleDocTemplate(str(out), pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title=f"TruthLens dossier — {case['name']}")
    story = []

    # ---- cover ----
    story.append(Paragraph("TruthLens", ss["TLTitle"]))
    story.append(Paragraph("Investigation dossier · Observe → Correlate → Explain", ss["TLSub"]))
    story.append(Paragraph(f"<b>Case:</b> {_esc(case['name'])} &nbsp;&nbsp; <b>ID:</b> {case_id}", ss["TLBody"]))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.now(timezone.utc).isoformat(timespec='seconds')}", ss["TLBody"]))
    counts = {lvl: sum(1 for f in findings if f["level"] == lvl) for lvl in LEVEL_LABELS}
    summary = " &nbsp;·&nbsp; ".join(
        f"<font color='{LEVEL_COLOR[l].hexval()}'><b>{counts[l]}</b> {LEVEL_LABELS[l]}</font>"
        for l in LEVEL_LABELS)
    story.append(Spacer(1, 6))
    story.append(Paragraph(summary, ss["TLBody"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This dossier is investigative support. TruthLens never labels a finding as confirmed "
        "fraud — levels are <b>Observed</b>, <b>Inconsistent</b> and <b>Potential manipulation</b>, "
        "and a human reviewer makes the final call.", ss["TLSmall"]))

    # ---- documents ----
    story.append(Paragraph("1 · Document overview", ss["TLH2"]))
    rows = [["File", "Type", "Pages", "SHA-256 (first 24)", "Status"]]
    for d in docs:
        rows.append([d["filename"], d["doc_type"], str(d["pages"]),
                     d["sha256"][:24] + "…", d["status"]])
    t = Table(rows, colWidths=[52 * mm, 32 * mm, 14 * mm, 52 * mm, 24 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(t)

    # ---- fields ----
    story.append(Paragraph("2 · Extracted fields (with source trace)", ss["TLH2"]))
    rows = [["Document", "Field", "Value", "Page", "Conf."]]
    for f in flds:
        dname = next((d["filename"] for d in docs if d["id"] == f["doc_id"]), f["doc_id"])
        rows.append([dname, f["label"], _esc(f["value"])[:60], str(f["page"]),
                     f"{f['confidence']:.2f}"])
    if len(rows) > 1:
        t = Table(rows, colWidths=[44 * mm, 34 * mm, 66 * mm, 12 * mm, 16 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5dd")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)
    else:
        story.append(Paragraph("No fields extracted.", ss["TLSmall"]))

    # ---- matrix ----
    story.append(Paragraph("3 · Cross-document correlation matrix", ss["TLH2"]))
    if matrix:
        header = ["Field"] + [d["filename"] for d in docs] + ["Status"]
        rows = [header]
        for r in matrix:
            cells = []
            for c in r["cells"]:
                v = c["value"] or "—"
                cells.append(_esc(v)[:34] + (" (derived)" if c.get("derived") else ""))
            rows.append([r["label"]] + cells + [r["status"].upper()])
        ncols = len(header)
        base = 176 / ncols
        t = Table(rows, colWidths=[base * mm] * ncols)
        style = [("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                 ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5dd")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        for i, r in enumerate(matrix, start=1):
            col = {"conflict": RED, "check": AMBER, "consistent": colors.HexColor("#157f3d")}.get(r["status"])
            if col:
                style.append(("TEXTCOLOR", (ncols - 1, i), (ncols - 1, i), col))
                style.append(("FONTNAME", (ncols - 1, i), (ncols - 1, i), "Helvetica-Bold"))
        t.setStyle(TableStyle(style))
        story.append(t)
    else:
        story.append(Paragraph("Run analysis to populate the matrix.", ss["TLSmall"]))

    # ---- findings ----
    story.append(PageBreak())
    story.append(Paragraph("4 · Findings", ss["TLH2"]))
    if not findings:
        story.append(Paragraph("No findings — documents are consistent with the checks performed.", ss["TLBody"]))
    for i, f in enumerate(findings, 1):
        block = []
        col = LEVEL_COLOR[f["level"]]
        block.append(Paragraph(
            f"<font color='{col.hexval()}'><b>[{LEVEL_LABELS[f['level']].upper()}]</b></font> "
            f"<b>{i}. {_esc(f['title'])}</b> &nbsp; <font size=8 color='#475467'>"
            f"confidence {f['confidence']:.0%} · {f['category']} · status: {f['status']}</font>",
            ss["TLBody"]))
        block.append(Spacer(1, 3))
        block.append(Paragraph(_esc(f["explanation"]), ss["TLBody"]))
        if f.get("verification"):
            block.append(Paragraph("<b>Verify next:</b> " +
                                   "; ".join(_esc(v) for v in f["verification"]), ss["TLSmall"]))
        refs = []
        for ev in f.get("evidence", []):
            dname = next((d["filename"] for d in docs if d["id"] == ev.get("doc_id")), "?")
            bb = ev.get("bbox") or []
            bbtxt = f" @ [{', '.join(str(int(v)) for v in bb)}]" if bb else ""
            refs.append(f"{dname} p.{ev.get('page', '?')}{bbtxt}")
        if refs:
            block.append(Paragraph("<b>Trace:</b> " + _esc(" · ".join(refs)), ss["TLMono"]))
        # region crops (max 2 per finding)
        shown = 0
        for ev in f.get("evidence", []):
            if shown >= 2:
                break
            crop = _region_crop(ev.get("doc_id", ""), case_id, ev.get("page", 1), ev.get("bbox") or [])
            if crop:
                block.append(Spacer(1, 4))
                block.append(crop)
                shown += 1
        if f.get("decisions"):
            for dec in f["decisions"]:
                block.append(Paragraph(
                    f"<b>Reviewer decision:</b> {dec['decision']} — {_esc(dec['note'] or 'no note')} "
                    f"({dec['reviewer']}, {dec['created_at']})", ss["TLSmall"]))
        block.append(Spacer(1, 10))
        if len(block) < 8:
            story.append(KeepTogether(block))
        else:
            story.extend(block)

    # ---- limitations ----
    story.append(Paragraph("5 · Limitations & areas to verify", ss["TLH2"]))
    for lim in [
        "OCR can misread characters; every field should be checked against the page image (click-to-trace in the app).",
        "Visual signals (ELA, noise, font metrics, copy-move) are statistical observations. Legitimate re-saves, "
        "printer artefacts and template variations can produce similar patterns.",
        "Signature analysis is partial: placement and feature similarity only — no forensic handwriting expertise.",
        "Handwriting and multilingual OCR are planned, not implemented in this build.",
        "Cross-document checks cover name, DOB, address and income; other entities are not yet correlated.",
        "No finding constitutes a fraud determination. A qualified human reviewer must decide.",
    ]:
        story.append(Paragraph("• " + lim, ss["TLSmall"]))
        story.append(Spacer(1, 2))

    # ---- audit ----
    story.append(Paragraph("6 · Audit trail summary", ss["TLH2"]))
    story.append(Paragraph(
        f"{len(audit_rows)} hash-chained entries · chain "
        f"{'<b>VERIFIED</b>' if chain['valid'] else '<b>BROKEN at ' + str(chain.get('broken_at')) + '</b>'}",
        ss["TLBody"]))
    story.append(Paragraph("Head hash: " + chain.get("head_hash", "—"), ss["TLMono"]))
    rows = [["#", "Timestamp (UTC)", "Event"]]
    for r in audit_rows[-18:]:
        rows.append([str(r["seq"]), r["ts"], r["event"]])
    t = Table(rows, colWidths=[12 * mm, 52 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5dd")),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(t)

    doc.build(story)
    return out
