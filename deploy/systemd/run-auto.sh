#!/usr/bin/env bash
# VPS wrapper for `auto` (host venv, not Docker). Triggered by ytr-auto.timer (UTC).
# Setup venv once: cd apps/api && python3.12 -m venv .venv && .venv/bin/pip install -r <(poetry export --with ingest)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../apps/api" && pwd)"
cd "$ROOT"
mkdir -p logs
exec .venv/bin/python -m app.main auto --ntfy info >> logs/auto-cron.log 2>&1
