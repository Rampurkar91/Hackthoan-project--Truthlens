# 🔍 TruthLens

**AI-Powered Document Forensics & Contextual Intelligence**

> **Observe → Correlate → Explain**

OCR reads documents. It does not *verify* them. TruthLens turns extraction into
evidence-driven investigation: it detects visual tampering, correlates fields
across documents, explains every finding in plain language, and traces each one
back to the exact pixels it came from — with a hash-chained audit trail and a
downloadable investigation dossier.

Built for the **DataOps Innovation Hackathon — Problem Statement 1**.
The original pitch deck is in [`docs/TruthLens_Hackathon_Deck.pdf`](docs/TruthLens_Hackathon_Deck.pdf).

---

## ✨ What it does

| | |
|---|---|
| **Visual forensics** | Error-Level Analysis (ELA), scan noise-floor breaks, font/baseline drift, copy-move duplication, signature placement, and ID-photo replacement signals — each highlighted on the original page with a confidence score. |
| **Contextual intelligence** | Tolerant entity matching (initials, spacing, date formats) compares name, DOB, address and income across documents. Real conflicts are flagged; harmless variation is not. |
| **Three honest levels** | Every finding is **Observed**, **Inconsistent**, or **Potential manipulation** — *never* “confirmed fraud”. A human makes the final call. |
| **Click-to-trace** | Finding → source document → page → bounding box. Every field keeps its page, box and OCR confidence. |
| **Evidence & audit** | SQLite evidence store + SHA-256 hash-chained audit log of uploads, runs, findings and reviewer decisions. Chain integrity is verifiable. |
| **Investigation dossier** | One-click PDF: overview, extracted fields, correlation matrix, findings with highlighted region crops, limitations, and audit summary. |

## 🎬 Live demo

The app ships with two synthetic, fully fictional sample cases:

- **Tampered demo** — an ID with a swapped photo and overwritten DOB, a bank
  statement with an overwritten address/DOB and a copy-moved branch stamp, and
  an inflated declared income. Reproduces the deck's example exactly
  (DOB `12-04-1991` vs `21-04-1991`, `Pune 411038` vs `Mumbai 400001`,
  ₹9,60,000 declared vs ₹4,10,000 average credits).
- **Genuine demo** — the same three documents, consistent and untampered,
  producing a clean baseline.

Open the app → **Load tampered demo** → watch findings appear → click a finding
to trace it to the source pixels → open the **Matrix** tab → record a reviewer
decision → **Download dossier**.

## 🚀 Quick start

### One command (backend serves the built UI)

```bash
# 1. Python deps
pip install -r backend/requirements.txt

# 2. Build the frontend
cd frontend && npm install && npm run build && cd ..

# 3. Run everything on http://localhost:8000
bash scripts/start.sh
```

Then open **http://localhost:8000**.

### Development mode (hot reload)

```bash
pip install -r backend/requirements.txt
bash scripts/dev.sh        # FastAPI :8000  +  Vite :5173 (proxies /api)
```

Open **http://localhost:5173**.

> **Requirements:** Python 3.10+, Node 18+. OCR runs fully offline
> (RapidOCR bundles PaddleOCR ONNX models in the wheel — no model downloads).

## 🧪 Tests

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_truthlens.py -q
```

The suite covers normalization, audit-chain tamper detection, income logic, and
full end-to-end runs on both sample sets (classification, field extraction,
conflict detection, escalation, clean genuine baseline, dossier generation and
reviewer decisions).

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Input layer      PDF / scans / images · upload UI · doc IDs + SHA-256   │
├──────────────────────────────────────────────────────────────────────┤
│  Perception       RapidOCR (PaddleOCR ONNX) · row/layout grouping ·      │
│                   keyword document classifier                          │
├──────────────────────────────────────────────────────────────────────┤
│  Forensic engine  ELA · noise-floor breaks · font/baseline drift ·       │
│                   copy-move (ORB) · signature placement · photo region │
├──────────────────────────────────────────────────────────────────────┤
│  Reasoning        tolerant entity matching · rule contextual checks ·  │
│                   cross-doc correlation · explanation engine (+LLM hook)│
├──────────────────────────────────────────────────────────────────────┤
│  Evidence store   SQLite findings/fields/regions · hash-chained audit ·  │
│                   reviewer decisions · dossier PDF generator           │
└──────────────────────────────────────────────────────────────────────┘
```

**The 7-step pipeline** (every step writes to the audit log):

1. **Ingest & Classify** — hash, store original, render pages, classify type
2. **OCR & Extract** — text lines with quadrilateral, box and confidence
3. **Structure Fields** — name, DOB, address, income, PAN, account, salary credits
4. **Visual Forensics** — pixel-level signals on the original page
5. **Contextual Checks** — within-document rules (dates, PIN/city, formats)
6. **Cross-Doc Correlation** — entity matrix + conflicts; visual agreement escalates
7. **Evidence & Dossier** — findings, traceability, audit chain, PDF dossier

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for module-by-module detail.

## 🧰 Technology stack & honest capability status

| Component | Tools used | Status |
|---|---|---|
| OCR / layout | RapidOCR (PaddleOCR v4 ONNX), row grouping | ✅ Implemented (printed text) |
| Image forensics | OpenCV — ELA, noise energy, ORB copy-move, font metrics | ✅ Implemented |
| Entity matching + reasoning | RapidFuzz + rule engine + explanation engine | ✅ Implemented |
| LLM explanations | Deterministic engine; optional OpenAI-compatible hook | ✅ Implemented (offline default) |
| Signature analysis | Placement + ORB similarity | 🟡 Partial |
| Handwriting / multilingual OCR | — | ⬜ Planned |
| Dossier / audit / traceability | ReportLab, SQLite, SHA-256 hash chain | ✅ Implemented |

> The deck asks teams to update the status column to match what was actually
> built — the table above reflects this implementation honestly.

### Optional LLM hookup

Explanations are generated by a deterministic, fact-grounded engine by default
(reproducible and offline). To let an LLM polish the wording (it can rephrase
but never invent evidence), set:

```bash
export TRUTHLENS_LLM_URL="https://api.openai.com/v1"
export TRUTHLENS_LLM_KEY="sk-..."
export TRUTHLENS_LLM_MODEL="gpt-4o-mini"
```

## 📁 Project structure

```
backend/
  app/
    main.py              FastAPI routes + static frontend serving
    config.py            paths, limits, optional LLM config
    store.py             SQLite evidence store + hash-chained audit log
    pipeline/
      ingest.py          1 · hash, store, render pages (PyMuPDF)
      ocr.py             2 · RapidOCR wrapper (offline, thread-capped)
      classify.py        1 · keyword document classifier
      fields.py          3 · structured field extraction with boxes
      forensics.py       4 · ELA, noise, font drift, copy-move, signature, photo
      contextual.py      5 · within-document rule checks
      correlate.py       6 · entity matrix + cross-document conflicts
      explain.py         · explanation engine + optional LLM refine
      runner.py          · orchestrates the pipeline, writes audit
      dossier.py         7 · ReportLab investigation dossier
      normalize.py       · name/date/amount/address normalization
    samples/generate.py  synthetic genuine + tampered demo documents
    tests/               pytest suite + manual diagnostic
frontend/
  src/                   React + Vite UI (viewer, findings, matrix, audit)
docs/                    pitch deck + architecture notes
scripts/                 start.sh (prod) · dev.sh (hot reload)
```

## 🔌 API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness |
| `POST` | `/api/cases` | Create a case |
| `GET` | `/api/cases/{id}` | Full case state (docs, fields, findings, matrix, audit) |
| `POST` | `/api/cases/{id}/documents` | Upload files (multipart) → auto-analyze |
| `POST` | `/api/cases/{id}/demo?variant=tampered\|genuine` | Load sample case |
| `POST` | `/api/cases/{id}/analyze` | Re-run analysis |
| `GET` | `/api/documents/{id}/pages/{n}.png` | Rendered page |
| `POST` | `/api/findings/{id}/decision` | Record reviewer decision |
| `GET` | `/api/cases/{id}/audit` | Audit entries + chain verification |
| `GET` | `/api/cases/{id}/dossier.pdf` | Download investigation dossier |

Interactive API docs at **`/docs`** (Swagger UI).

## ⚖️ Judging criteria mapping

- **Contextual intelligence (20)** — cross-document entity matrix, tolerant
  matching, conflict + income checks, plain-language explanations.
- **OCR + extraction (15)** — offline PaddleOCR models, structured fields with
  page/box/confidence traceability.
- **Visual forensics (15)** — ELA, noise breaks, font drift, copy-move,
  signature and photo-replacement signals with highlighted regions.
- **Document understanding (15)** — classification, layout row grouping,
  contextual rules, three-level findings, dossier + audit trail.

## ⚠️ Limitations

- OCR can misread characters; every field is traceable to its page image.
- Visual signals are statistical observations — legitimate re-saves, printer
  artefacts and template variations can produce similar patterns.
- Signature analysis is partial (placement + feature similarity, not handwriting expertise).
- Handwriting and multilingual OCR are planned, not implemented.
- **No finding is a fraud determination.** A qualified human reviewer decides.

## 📄 License

MIT — see [`LICENSE`](LICENSE). Demo documents and portraits are synthetic and fictional.

---

<p align="center"><b>TruthLens</b> · Observe → Correlate → Explain</p>
