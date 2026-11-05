"""Central configuration for the TruthLens backend."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("TRUTHLENS_DATA", BACKEND_DIR / "data"))
CASES_DIR = DATA_DIR / "cases"
DB_PATH = DATA_DIR / "truthlens.db"
SAMPLES_CACHE_DIR = DATA_DIR / "samples_cache"
FRONTEND_DIST = REPO_DIR / "frontend" / "dist"

MAX_UPLOAD_MB = int(os.environ.get("TRUTHLENS_MAX_UPLOAD_MB", "25"))
PDF_RENDER_ZOOM = 2.0          # PyMuPDF render scale for OCR quality
MAX_PAGE_EDGE = 2200           # cap rendered page size (px)

# Optional OpenAI-compatible LLM endpoint for richer explanations.
# When unset, TruthLens uses its deterministic explanation engine (offline).
LLM_URL = os.environ.get("TRUTHLENS_LLM_URL", "")
LLM_KEY = os.environ.get("TRUTHLENS_LLM_KEY", "")
LLM_MODEL = os.environ.get("TRUTHLENS_LLM_MODEL", "gpt-4o-mini")

LEVELS = ("observed", "inconsistent", "potential_manipulation")
LEVEL_LABELS = {
    "observed": "Observed",
    "inconsistent": "Inconsistent",
    "potential_manipulation": "Potential manipulation",
}

for d in (DATA_DIR, CASES_DIR, SAMPLES_CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
