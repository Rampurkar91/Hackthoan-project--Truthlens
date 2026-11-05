#!/usr/bin/env bash
# Start TruthLens (backend serves the built frontend on one port).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d frontend/dist ]; then
  echo "==> Building frontend…"
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

echo "==> Starting TruthLens on http://0.0.0.0:8000"
cd backend
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
