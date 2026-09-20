#!/usr/bin/env bash
# Git Bash / WSL / Linux: same pipeline as deploy-ytr.ps1
# Usage:
#   ./scripts/deploy-ytr.sh -m "Ship edit-channels"
#   ./scripts/deploy-ytr.sh --skip-commit
#   ./scripts/deploy-ytr.sh --skip-commit --skip-generate
set -euo pipefail

COMMIT_MSG=""
REMOTE_HOST="${REMOTE_HOST:-root@o2t4.ru}"
REMOTE_ROOT="${REMOTE_ROOT:-/var/www/o2t4/backend/YTRatings}"
API_BASE="${API_BASE:-https://ytr.o2t4.ru/api/ytr/v2}"
SKIP_COMMIT=0
SKIP_PUSH=0
SKIP_GENERATE=0
SKIP_DOCKER=0
SKIP_FRONTEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message) COMMIT_MSG="$2"; shift 2 ;;
    --skip-commit) SKIP_COMMIT=1; shift ;;
    --skip-push) SKIP_PUSH=1; shift ;;
    --skip-generate) SKIP_GENERATE=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --skip-frontend) SKIP_FRONTEND=1; shift ;;
    --remote) REMOTE_HOST="$2"; shift 2 ;;
    --api-base) API_BASE="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BRANCH="$(git branch --show-current)"
[[ -n "$BRANCH" ]] || { echo "Detached HEAD"; exit 1; }

step() { printf '\n=== %s ===\n' "$1"; }

if [[ "$SKIP_COMMIT" -eq 0 ]]; then
  step "git status"
  git status -sb
  if [[ -n "$(git status --porcelain)" ]]; then
    [[ -n "$COMMIT_MSG" ]] || { echo "Dirty tree: pass -m '...' or --skip-commit"; exit 1; }
    step "git add + commit"
    git add -u
    git add scripts/deploy-ytr.ps1 scripts/deploy-ytr.sh \
      yt_fetcher/app/channel/edit_channels.py \
      yt_fetcher/scripts/channel_edits.example.csv \
      yt_fetcher/scripts/channel_edits.example.jsonl 2>/dev/null || true
    git commit -m "$COMMIT_MSG"
  else
    echo "Nothing to commit."
  fi
fi

if [[ "$SKIP_PUSH" -eq 0 ]]; then
  step "git push ($BRANCH)"
  git push -u origin HEAD
fi

DIST_LOCAL="$ROOT/frontend/dist"
SSG_OUT="$ROOT/frontend-nuxt/.output/public"

if [[ "$SKIP_GENERATE" -eq 0 ]]; then
  step "Nuxt SSG (NUXT_API_BASE=$API_BASE)"
  (
    cd frontend-nuxt
    export NUXT_API_BASE="$API_BASE"
    export NUXT_PUBLIC_API_BASE="/api/ytr/v2"
    export NUXT_PUBLIC_SITE_URL="https://ytr.o2t4.ru"
    export NUXT_IGNORE_LOCK=1
    npm run generate
  )
  [[ -d "$SSG_OUT" ]] || { echo "SSG output missing: $SSG_OUT"; exit 1; }

  step "Mirror SSG → frontend/dist (keep channel_logo/)"
  mkdir -p "$DIST_LOCAL"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude 'channel_logo/' "$SSG_OUT"/ "$DIST_LOCAL"/
  else
    # portable fallback
    find "$DIST_LOCAL" -mindepth 1 ! -path '*/channel_logo/*' ! -name 'channel_logo' -exec rm -rf {} + 2>/dev/null || true
    tar -C "$SSG_OUT" -cf - . | tar -C "$DIST_LOCAL" -xf -
  fi
fi

if [[ "$SKIP_DOCKER" -eq 0 ]]; then
  step "VPS git pull + docker compose up --build"
  ssh "$REMOTE_HOST" bash -s <<EOF
set -e
cd '$REMOTE_ROOT'
git fetch origin
git checkout '$BRANCH' || git checkout -B '$BRANCH' "origin/$BRANCH"
git pull --ff-only origin '$BRANCH'
cd yt_fetcher
docker compose up -d --build
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
EOF
fi

if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
  [[ -d "$DIST_LOCAL" ]] || { echo "frontend/dist missing"; exit 1; }
  step "Sync frontend/dist → VPS (exclude channel_logo/)"
  REMOTE_DIST="$REMOTE_ROOT/frontend/dist"
  ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_DIST'"
  tar -C "$DIST_LOCAL" --exclude=channel_logo -cf - . | ssh "$REMOTE_HOST" "tar -xf - -C '$REMOTE_DIST'"
  step "nginx reload"
  ssh "$REMOTE_HOST" "nginx -t && systemctl reload nginx" || echo "WARN: nginx reload failed"
fi

step "Done"
echo "Live: https://ytr.o2t4.ru/"
