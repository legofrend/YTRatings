#!/usr/bin/env bash
# Local FastAPI (:5000) + Nuxt (:3000) for YTRatings.
# Usage:
#   ./scripts/dev-ytr.sh
#   ./scripts/dev-ytr.sh --api-only
#   ./scripts/dev-ytr.sh --web-only
set -euo pipefail

API_ONLY=0
WEB_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-only) API_ONLY=1; shift ;;
    --web-only) WEB_ONLY=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FETCHER="$ROOT/yt_fetcher"
FRONTEND="$ROOT/frontend-nuxt"

if [[ -x "$FETCHER/.venv/Scripts/python.exe" ]]; then
  PYTHON="$FETCHER/.venv/Scripts/python.exe"
elif [[ -x "$FETCHER/.venv/bin/python" ]]; then
  PYTHON="$FETCHER/.venv/bin/python"
else
  PYTHON=""
fi

PIDS=()
cleanup() {
  for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

if [[ "$WEB_ONLY" -eq 0 ]]; then
  [[ -n "$PYTHON" ]] || { echo "No venv. cd yt_fetcher && poetry install" >&2; exit 1; }
  echo "FastAPI  http://127.0.0.1:5000/docs"
  (cd "$FETCHER" && "$PYTHON" -m uvicorn app.fast_api.main:app --host 127.0.0.1 --port 5000 --reload) &
  PIDS+=($!)
fi

if [[ "$API_ONLY" -eq 0 ]]; then
  [[ -f "$FRONTEND/package.json" ]] || { echo "Missing frontend-nuxt" >&2; exit 1; }
  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    echo "npm install (frontend-nuxt)..."
    (cd "$FRONTEND" && npm install)
  fi
  echo "Nuxt     http://127.0.0.1:3000"
  (cd "$FRONTEND" && npm run dev) &
  PIDS+=($!)
fi

echo "Ctrl+C stops everything."
wait
