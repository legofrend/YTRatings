#Requires -Version 5.1
<#
.SYNOPSIS
  Optional commit -> push -> Nuxt SSG -> VPS pull + docker rebuild -> sync frontend/dist

.EXAMPLE
  .\scripts\deploy-ytr.ps1 -CommitMessage "Ship edit-channels + Shift+click JSONL template"
  .\scripts\deploy-ytr.ps1 -SkipCommit
  .\scripts\deploy-ytr.ps1 -SkipCommit -SkipGenerate
  .\scripts\deploy-ytr.ps1 -SkipDocker
#>
param(
  [string]$CommitMessage = "",
  [string]$RemoteHost = "root@o2t4.ru",
  [string]$RemoteRoot = "/var/www/o2t4/backend/YTRatings",
  [string]$ApiBase = "https://ytr.o2t4.ru/api/ytr/v2",
  [switch]$SkipCommit,
  [switch]$SkipPush,
  [switch]$SkipGenerate,
  [switch]$SkipDocker,
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Step([string]$msg) {
  Write-Host ""
  Write-Host "=== $msg ===" -ForegroundColor Cyan
}

function Assert-Ok([string]$what) {
  if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "$what failed (exit $LASTEXITCODE)"
  }
}

$branch = (git branch --show-current).Trim()
if (-not $branch) { throw "Detached HEAD - checkout a branch first" }

# --- git commit ---
if (-not $SkipCommit) {
  Step "git status"
  git status -sb
  $dirty = git status --porcelain
  if ($dirty) {
    if (-not $CommitMessage) {
      throw "Working tree dirty. Pass -CommitMessage '...' or -SkipCommit"
    }
    Step "git add + commit"
    git add -u
    git add `
      scripts/deploy-ytr.ps1 `
      scripts/deploy-ytr.sh `
      yt_fetcher/app/channel/edit_channels.py `
      yt_fetcher/scripts/channel_edits.example.csv `
      yt_fetcher/scripts/channel_edits.example.jsonl `
      2>$null
    git status -sb
    git commit -m $CommitMessage
    Assert-Ok "git commit"
  } else {
    Write-Host "Nothing to commit."
  }
}

# --- push ---
if (-not $SkipPush) {
  Step "git push ($branch)"
  git push -u origin HEAD
  Assert-Ok "git push"
}

$distLocal = Join-Path $RepoRoot "frontend\dist"
$ssgOut = Join-Path $RepoRoot "frontend-nuxt\.output\public"

# --- SSG ---
if (-not $SkipGenerate) {
  Step "Nuxt SSG (NUXT_API_BASE=$ApiBase)"
  Push-Location (Join-Path $RepoRoot "frontend-nuxt")
  try {
    $env:NUXT_API_BASE = $ApiBase
    $env:NUXT_PUBLIC_API_BASE = "/api/ytr/v2"
    $env:NUXT_PUBLIC_SITE_URL = "https://ytr.o2t4.ru"
    $env:NUXT_IGNORE_LOCK = "1"
    npm run generate
    Assert-Ok "npm run generate"
  } finally {
    Pop-Location
  }

  if (-not (Test-Path $ssgOut)) {
    throw "SSG output missing: $ssgOut"
  }

  Step "Mirror SSG to frontend/dist (keep local channel_logo/)"
  New-Item -ItemType Directory -Force -Path $distLocal | Out-Null
  robocopy $ssgOut $distLocal /E /XD channel_logo /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed (exit $LASTEXITCODE)"
  }
  $global:LASTEXITCODE = 0
}

# --- VPS: pull + docker ---
if (-not $SkipDocker) {
  Step "VPS git pull + docker compose up --build"
  $remoteCmd = "set -e; cd '$RemoteRoot'; git fetch origin; git checkout '$branch' || git checkout -B '$branch' origin/$branch; git pull --ff-only origin '$branch'; cd yt_fetcher; docker compose up -d --build; docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
  ssh $RemoteHost $remoteCmd
  Assert-Ok "remote docker deploy"
}

# --- VPS: sync frontend dist (preserve remote channel_logo/) ---
if (-not $SkipFrontend) {
  if (-not (Test-Path $distLocal)) {
    throw "Local frontend/dist missing - run without -SkipGenerate first"
  }
  Step "Sync frontend/dist to VPS (exclude channel_logo/)"
  $remoteDist = "$RemoteRoot/frontend/dist"
  $sshCmd = "mkdir -p '$remoteDist'; tar -xf - -C '$remoteDist'"
  & tar -C $distLocal --exclude=channel_logo -cf - . | ssh $RemoteHost $sshCmd
  Assert-Ok "frontend sync"

  Step "nginx reload"
  ssh $RemoteHost "nginx -t; systemctl reload nginx"
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "nginx reload returned $LASTEXITCODE"
  }
}

Step "Done"
Write-Host "Live: https://ytr.o2t4.ru/"
Write-Host "API:  https://ytr.o2t4.ru/api/ytr/v2/categories"
