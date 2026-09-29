#!/usr/bin/env bash
# VPS cron wrapper (host poetry, not Docker). Schedule in crontab, TZ=Europe/Moscow.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
export PATH="${HOME}/.local/bin:${PATH}"
exec poetry run python -m app.main auto --ntfy info >> logs/auto-cron.log 2>&1
