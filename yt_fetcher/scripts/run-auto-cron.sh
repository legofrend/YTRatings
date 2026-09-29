#!/usr/bin/env bash
# VPS wrapper for `auto` (host venv, not Docker). Triggered by deploy/systemd/ytr-auto.timer.
# Setup venv once: python3.12 -m venv .venv && .venv/bin/pip install -r <(poetry export --with ingest)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
exec .venv/bin/python -m app.main auto --ntfy info >> logs/auto-cron.log 2>&1
