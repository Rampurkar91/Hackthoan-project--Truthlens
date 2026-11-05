"""TruthLens API — AI-powered document forensics & contextual intelligence.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
The built frontend (frontend/dist) is served from the same origin when present.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import store
from .config import CASES_DIR, FRONTEND_DIST, MAX_UPLOAD_MB
from .pipeline import dossier, runner
from .pipeline.ingest import doc_dir, ingest_file, page_path

app = FastAPI(title="TruthLens", version="1.0.0",
              description="Observe → Correlate → Explain. Document forensics with evidence trails.")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ health -
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "truthlens", "version": "1.0.0"}


# ------------------------------------------------------------------- cases -
class CaseIn(BaseModel):
    name: str


@app.post("/api/cases")
def create_case(body: CaseIn):
    return store.create_case(body.name.strip() or "Untitled case")


@app.get("/api/cases")
def list_cases():
    return store.list_cases()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    docs = store.list_documents(case_id)
    for d in docs:
        d["meta"] = {k: v for k, v in d["meta"].items()
                    if k in ("pages", "photo_bbox", "signature", "error")}
        d["visual_regions"] = []  # keep payload small; findings carry regions
    matrix_file = CASES_DIR / case_id / "matrix.json"
    return {
        "case": case,
        "documents": docs,
        "fields": store.list_fields(case_id),
        "findings": store.list_findings(case_id),
        "matrix": json.loads(matrix_file.read_text()) if matrix_file.exists() else [],
        "audit": store.list_audit(case_id),
        "chain": store.verify_audit(case_id),
    }


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str):
    if not store.get_case(case_id):
        raise HTTPException(404, "case not found")
    with store._LOCK:
        c = store._conn()
        for tbl in ("decisions",):
            c.execute(f"DELETE FROM {tbl} WHERE finding_id IN (SELECT id FROM findings WHERE case_id=?)", (case_id,))
        for tbl in ("findings", "fields", "documents", "audit", "cases"):
            c.execute(f"DELETE FROM {tbl} WHERE {'id' if tbl == 'cases' else 'case_id'}=?", (case_id,))
        c.commit()
    shutil.rmtree(CASES_DIR / case_id, ignore_errors=True)
    return {"deleted": case_id}


# --------------------------------------------------------------- documents -
@app.post("/api/cases/{case_id}/documents")
async def upload_documents(case_id: str, background: BackgroundTasks,
                           files: list[UploadFile]):
    if not store.get_case(case_id):
        raise HTTPException(404, "case not found")
    if not files:
        raise HTTPException(400, "no files")
    added = []
    for up in files:
        data = await up.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"{up.filename} exceeds {MAX_UPLOAD_MB} MB")
        suffix = Path(up.filename or "upload").suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            raise HTTPException(415, f"unsupported type: {suffix}")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        # reserve an id, ingest, then register
        from .store import new_id
        did = new_id("doc")
        try:
            meta = ingest_file(case_id, did, tmp_path, up.filename)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(400, f"could not ingest {up.filename}: {e}")
        tmp_path.unlink(missing_ok=True)
        with store._LOCK:
            store._conn().execute(
                "INSERT INTO documents (id, case_id, filename, sha256, pages, status, meta, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (did, case_id, up.filename, meta["sha256"], len(meta["pages"]),
                 "ingested", json.dumps(meta), store.now()))
            store._conn().commit()
        store.audit(case_id, "document.ingested",
                    {"doc_id": did, "filename": up.filename,
                     "sha256": meta["sha256"], "pages": len(meta["pages"])})
        added.append(store.get_document(did))
    background.add_task(runner.analyze_case, case_id)
    return {"added": added, "status": "analyzing"}


@app.post("/api/cases/{case_id}/analyze")
def analyze(case_id: str, background: BackgroundTasks):
    if not store.get_case(case_id):
        raise HTTPException(404, "case not found")
    background.add_task(runner.analyze_case, case_id)
    return {"status": "analyzing"}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    d = store.get_document(doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    d["fields"] = store.list_fields(d["case_id"], doc_id)
    d["findings"] = [f for f in store.list_findings(d["case_id"]) if f["doc_id"] == doc_id]
    lines = d["meta"].get("ocr_lines", {})
    d["ocr_lines"] = lines
    d["visual_regions"] = d["meta"].get("visual_regions", [])
    return d


@app.get("/api/documents/{doc_id}/pages/{page}.png")
def get_page(doc_id: str, page: int):
    d = store.get_document(doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    p = page_path(d["case_id"], doc_id, page)
    if not p.exists():
        raise HTTPException(404, "page not found")
    return FileResponse(p, media_type="image/png")


@app.get("/api/documents/{doc_id}/original")
def get_original(doc_id: str):
    d = store.get_document(doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    p = Path(d["meta"]["original"])
    if not p.exists():
        raise HTTPException(404, "original not found")
    return FileResponse(p, filename=d["filename"])


# ---------------------------------------------------------------- findings -
class DecisionIn(BaseModel):
    decision: str          # confirmed | dismissed | needs_review
    note: str = ""
    reviewer: str = "reviewer"


@app.post("/api/findings/{finding_id}/decision")
def decide(finding_id: str, body: DecisionIn):
    if body.decision not in ("confirmed", "dismissed", "needs_review"):
        raise HTTPException(400, "decision must be confirmed|dismissed|needs_review")
    f = store.record_decision(finding_id, body.decision, body.note, body.reviewer)
    if not f:
        raise HTTPException(404, "finding not found")
    return f


# ------------------------------------------------------------------- audit -
@app.get("/api/cases/{case_id}/audit")
def get_audit(case_id: str):
    if not store.get_case(case_id):
        raise HTTPException(404, "case not found")
    return {"entries": store.list_audit(case_id), "chain": store.verify_audit(case_id)}


# ----------------------------------------------------------------- dossier -
@app.get("/api/cases/{case_id}/dossier.pdf")
def get_dossier(case_id: str):
    if not store.get_case(case_id):
        raise HTTPException(404, "case not found")
    try:
        out = dossier.build_dossier(case_id)
    except Exception as e:
        raise HTTPException(500, f"dossier generation failed: {e}")
    return FileResponse(out, filename=f"truthlens-dossier-{case_id}.pdf",
                        media_type="application/pdf")


# ------------------------------------------------------------------ demo ---
@app.post("/api/cases/{case_id}/demo")
def load_demo(case_id: str, background: BackgroundTasks, variant: str = "tampered"):
    """Load the synthetic sample case (genuine or tampered) into this case."""
    if not store.get_case(case_id):
        raise HTTPException(404, "case not found")
    if variant not in ("genuine", "tampered"):
        raise HTTPException(400, "variant must be genuine|tampered")
    from .samples.generate import build_set
    files = build_set(variant)
    added = []
    for f in files:
        from .store import new_id
        did = new_id("doc")
        meta = ingest_file(case_id, did, Path(f["path"]), f["name"])
        with store._LOCK:
            store._conn().execute(
                "INSERT INTO documents (id, case_id, filename, sha256, pages, status, meta, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (did, case_id, f["name"], meta["sha256"], len(meta["pages"]),
                 "ingested", json.dumps(meta), store.now()))
            store._conn().commit()
        store.audit(case_id, "document.ingested",
                    {"doc_id": did, "filename": f["name"], "sha256": meta["sha256"],
                     "pages": len(meta["pages"]), "source": f"demo:{variant}"})
        added.append(store.get_document(did))
    background.add_task(runner.analyze_case, case_id)
    return {"added": added, "variant": variant, "status": "analyzing"}


# ------------------------------------------------------- static frontend ---
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return JSONResponse({
            "service": "TruthLens API",
            "docs": "/docs",
            "note": "Frontend not built yet. Run: cd frontend && npm install && npm run build",
        })
