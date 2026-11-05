# TruthLens — Architecture Notes

This document explains how the pipeline is implemented, module by module, and
the design decisions behind the forensic signals.

## Design principles

1. **Evidence over verdicts.** The system never outputs "fraud". It emits
   *Observed*, *Inconsistent* and *Potential manipulation* findings, each with
   the facts that produced it and suggested verification steps.
2. **Everything traces to pixels.** OCR lines, fields and findings all carry a
   page number and bounding box in the rendered page's coordinate space, so the
   UI can overlay them and the dossier can crop them.
3. **Tamper-evident history.** Every upload, pipeline step, finding and reviewer
   decision is appended to a per-case SHA-256 hash chain. Editing any past entry
   breaks the chain, which `verify_audit` detects.
4. **Offline & reproducible.** OCR models ship inside the RapidOCR wheel; the
   explanation engine is deterministic. The optional LLM hook only rephrases
   grounded facts.

## Data flow

```
upload ─▶ ingest (hash + render) ─▶ OCR ─▶ classify ─▶ fields
                                              │
                                              ▼
                                      visual forensics ─▶ visual findings
                                              │
                                              ▼
                                      contextual checks ─▶ contextual findings
                                              │
              (all documents ready)           ▼
                                      cross-doc correlation ─▶ conflict findings
                                              │   (visual agreement escalates level)
                                              ▼
                                      evidence store + audit ─▶ dossier PDF
```

## Modules

### `pipeline/ingest.py`
Copies the original byte-for-byte into `data/cases/{case}/{doc}/original.*`,
computes SHA-256, and renders each PDF page to PNG with PyMuPDF (zoom capped so
the longest edge ≤ 2200 px). Images are normalized to RGB PNG.

### `pipeline/ocr.py`
Wraps RapidOCR (PaddleOCR v4 detection + recognition on ONNX Runtime). Thread
counts are capped (default 2) because the ONNX default of `-1` thrashes small
CPU quotas; detection side is bounded to 1400 px. Returns lines with
`{text, score, bbox, poly}`. A module lock serializes inference; engine init is
lazy and separate to avoid a nested-lock deadlock.

### `pipeline/classify.py`
Keyword scoring over OCR text for `application_form`, `id_proof`,
`bank_statement`. Matches both spaced and space-stripped text because OCR
sometimes merges bold headers (`IDENTITYCARD`). Stores the score breakdown.

### `pipeline/fields.py`
Groups OCR lines into visual rows (vertical overlap), joins split
`Label:`/`value` boxes, then extracts typed fields with regex + label matching
(space-stripped tolerant). Address continuation lines are merged. Salary
credits on statements are averaged into a derived `avg_salary` field. Every
field keeps page, value bounding box and OCR confidence.

### `pipeline/forensics.py`
The visual signal families:

- **ELA** — re-save the page as JPEG q90, measure the residual, grid it into
  16 px blocks, and flag blocks whose robust-z score against the page median is
  extreme *and* whose absolute error exceeds a floor (avoids flagging ordinary
  text antialiasing on near-uniform pages).
- **Noise break** — high-pass residual energy in a local window. Genuine scans
  have a uniform noise floor; an overwrite pastes a clean rectangle, so its
  inter-glyph background is *smoother* (or a noisy patch is *noisier*). Text and
  strong edges are masked with a thin margin so background between letters stays
  measurable.
- **Font drift** — compares field-line glyph-box heights to the page median
  (strong deviations only, since OCR box height varies with caps/descenders),
  and compares neighbours within `Label: value` rows. Subtler overwrites are
  caught by the noise signal instead.
- **Copy-move** — ORB self-matching with displacement voting; text boxes are
  excluded so repeated table rows don't false-positive. A duplicated stamp/logo
  yields a consistent displacement cluster.
- **Signature** — locates ink above the printed "Signature" anchor, measures
  density and overlap with printed text. Cross-document similarity is computed
  in the runner via ORB feature matching (partial capability).
- **Photo region** — Haar face detection on ID proofs approximates the photo
  box; ELA/noise anomalies inside it are reported as possible photo replacement.

Regions of *different* families that agree on the same pixels are merged and
escalated to **Potential manipulation** by the runner.

### `pipeline/contextual.py`
Within-document rules: DOB parseability/plausibility/minor age, city vs PIN
code, PAN format, Aadhaar leading digit.

### `pipeline/correlate.py`
Builds the field × document matrix. Name matching tolerates initials/order/
spelling (RapidFuzz); dates are normalized to ISO; addresses compare city/PIN;
income compares declared vs annualized statement credits (a "check", not a hard
conflict). A conflict whose field pixels overlap a visual forensic region is
escalated to **Potential manipulation** and the explanation notes the agreement.

### `pipeline/explain.py`
Template-grounded explanations per finding kind, always paired with verification
steps. `llm_refine` optionally asks an OpenAI-compatible endpoint to rewrite the
wording using only the provided facts; it falls back to the template on any error.

### `pipeline/runner.py`
Orchestrates per-document analysis then case-level correlation, writing an audit
entry at each step. Auto-findings without reviewer decisions are cleared and
regenerated on re-run; decided findings are preserved.

### `pipeline/dossier.py`
ReportLab PDF: cover + summary, document overview with hashes, extracted fields,
correlation matrix, findings with highlighted region crops and trace references,
reviewer decisions, limitations, and audit-chain summary.

### `store.py`
SQLite (WAL) with tables `cases, documents, fields, findings, decisions, audit`.
The audit chain: `hash_n = SHA256(hash_{n-1} | ts | event | canonical_json(payload))`.
`verify_audit` recomputes the chain and reports the first broken link.

## Frontend

React + Vite (no UI framework dependency). `App.jsx` owns case state and polls
while analyzing. `DocumentViewer` renders the page image with an SVG overlay of
finding regions and (optional) field boxes; selecting a finding scrolls its
region into view (click-to-trace). Tabs: Findings (filter by level, record
decisions), Matrix, Fields, Audit (re-verify chain). The dev server proxies
`/api` to FastAPI; in production FastAPI serves the built `dist/` from the same
origin.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `TRUTHLENS_DATA` | `backend/data` | Evidence store location |
| `TRUTHLENS_MAX_UPLOAD_MB` | `25` | Per-file upload limit |
| `TRUTHLENS_OCR_THREADS` | `2` | ONNX intra-op threads |
| `TRUTHLENS_LLM_URL/KEY/MODEL` | unset | Optional explanation polishing |
