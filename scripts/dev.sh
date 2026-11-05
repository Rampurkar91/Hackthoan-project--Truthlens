#!/usr/bin/env bash
# Development mode: FastAPI (8000) + Vite dev server (5173, proxies /api).
set -euo pipefail
cd "$(dirname "$0")/.."

(cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACK=$!
trap "kill $BACK 2>/dev/null || true" EXIT

cd frontend
npm install --no-audit --no-fund
exec npm run dev
