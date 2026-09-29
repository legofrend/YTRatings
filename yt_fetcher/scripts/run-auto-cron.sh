#!/usr/bin/env bash
# VPS cron wrapper: Europe/Moscow schedule in crontab, this runs `auto`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
exec docker compose --profile ingest run --rm ingest auto --ntfy info
