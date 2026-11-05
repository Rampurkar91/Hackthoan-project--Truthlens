# TruthLens — 3-minute demo video

**File:** [`TruthLens_3min_Demo.mp4`](TruthLens_3min_Demo.mp4) · 1920×1080 · 25 fps · H.264 + AAC · 3:01
**Subtitles:** [`TruthLens_3min_Demo.srt`](TruthLens_3min_Demo.srt) (same timings as the narration)

A narrated walkthrough of the working prototype: the problem, the idea, and a
full demonstration of the pipeline on the built-in *tampered* sample case
(application form + ID card + bank statement, fully synthetic).

Everything shown on screen comes from a real run of the pipeline — the same
`assets/*.json` output the app renders, the real evidence crops, the real
SHA-256 audit chain and the real 6-page dossier PDF. The UI panels are drawn
from that data at video-legible sizes rather than screen-recorded.

## Chapters

| Time | Chapter | What you see |
|---|---|---|
| 0:00 | Title | TruthLens — Observe → Correlate → Explain |
| 0:13 | The blind spot | Three documents, four tampering signals that OCR cannot see; the clean text extraction |
| 0:31 | The idea | Observe / Correlate / Explain + the 7-step pipeline and the hash-chained audit log |
| 0:56 | Prototype · load a case | Hero screen → *Load tampered demo* → analysis runs |
| 1:10 | Prototype · findings | 10 findings stream in, labelled Observed / Inconsistent / Potential manipulation; click-to-trace on the DOB conflict; declared vs documented income |
| 1:40 | Visual forensics | Real ELA map + evidence crops (photo region, font drift, address overwrite, copy-move stamp, signature placement) and the escalation rule |
| 1:59 | Correlation & decisions | Cross-document matrix with the real conflicts; reviewer decision recorded |
| 2:13 | Audit & dossier | Hash-chained audit entries + the generated dossier PDF |
| 2:30 | Honest by design | The three levels, capability status table, genuine-sample baseline |
| 2:47 | Impact | Faster KYC, fewer forged applications, audit-ready evidence |

## Narration script

> **0:00** Every loan, every account, every KYC check starts with documents.
> And almost every system that reads them has the same blind spot. This is TruthLens.
>
> **0:13** OCR turns a scanned document into clean text. A swapped photograph, an
> overwritten date of birth, a doctored address, an inflated salary — all of it comes
> out looking like ordinary text. The data is extracted, and the fraud goes straight
> through the gap.
>
> **0:31** TruthLens closes that gap with three moves. Observe the pixels. Correlate
> the documents. Explain every finding. Seven steps run on every upload: ingest and
> classify, OCR, structure fields, visual forensics, contextual checks, cross-document
> correlation, and evidence with a dossier. Every step is written to a hash-chained
> audit log.
>
> **0:56** Here is the working prototype. It ships with a synthetic tampered case: an
> application form, an ID card and a bank statement, all fully fictional. One click,
> and the pipeline runs in seconds.
>
> **1:10** Ten findings come back, labelled Observed, Inconsistent or Potential
> manipulation. Never confirmed fraud. The application form says twelve oh four,
> ninety-one. Both other documents say twenty-one oh four. The address reads Pune on
> two documents and Mumbai on the third. Nine point six lakh declared, against four
> point one lakh of annualised bank credits. And every card traces back to the exact
> pixels it came from.
>
> **1:40** Underneath, the forensic engine measures compression error, noise-floor
> breaks, font drift, copy-move duplication, signature placement and photo-region
> anomalies. When two independent signals agree on the same pixels, the finding is
> escalated, and the explanation says exactly why.
>
> **1:59** The matrix lines up every field across every document, tolerant of initials,
> spacing and date formats. A reviewer confirms, flags or dismisses each finding, and
> that decision is timestamped in the chain.
>
> **2:13** The audit trail is a SHA-256 hash chain. Edit any past entry, and
> verification breaks. One click produces the investigation dossier: file hashes,
> extracted fields, the full matrix, and cropped evidence for every finding.
>
> **2:30** Not everything is a red flag. The genuine sample produces a clean baseline.
> And the capability table is honest: OCR, forensics, correlation and the dossier are
> implemented. Handwriting and multilingual OCR are planned.
>
> **2:47** Faster KYC reviews, fewer forged applications, and an evidence trail that
> stands up to audit. TruthLens: observe, correlate, explain.

## Reproducing the run shown in the video

```bash
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
bash scripts/start.sh          # http://localhost:8000
# → Load tampered demo → wait for the 7-step pipeline → click any finding
```

Demo data is generated locally by `backend/app/samples/generate.py`; all names,
numbers, portraits and documents are synthetic and fictional.
