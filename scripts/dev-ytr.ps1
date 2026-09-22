#Requires -Version 5.1
<#
.SYNOPSIS
  Local FastAPI (:5000) + Nuxt (:3000) for YTRatings.

.EXAMPLE
  .\scripts\dev-ytr.ps1
  .\scripts\dev-ytr.ps1 -ApiOnly
  .\scripts\dev-ytr.ps1 -WebOnly
  .\scripts\dev-ytr.ps1 -InPlace   # same window, Ctrl+C kills both
#>
param(
  [switch]$ApiOnly,
  [switch]$WebOnly,
  [switch]$InPlace
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Fetcher = Join-Path $RepoRoot "yt_fetcher"
$Frontend = Join-Path $RepoRoot "frontend-nuxt"
$Python = Join-Path $Fetcher ".venv\Scripts\python.exe"

function Assert-Python {
  if (-not (Test-Path $Python)) {
    throw "No venv at $Python`n  cd yt_fetcher; poetry install"
  }
}

function Assert-Frontend {
  if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
    throw "Missing frontend-nuxt/package.json"
  }
  if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "npm install (frontend-nuxt)..." -ForegroundColor Yellow
    Push-Location $Frontend
    try { npm install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
  }
}

$apiCmd = "& `"$Python`" -m uvicorn app.fast_api.main:app --host 127.0.0.1 --port 5000 --reload"
$webCmd = "npm run dev"

Write-Host ""
if (-not $WebOnly) { Write-Host "FastAPI  http://127.0.0.1:5000/docs" -ForegroundColor Cyan }
if (-not $ApiOnly) { Write-Host "Nuxt     http://127.0.0.1:3000" -ForegroundColor Cyan }
Write-Host ""

if ($InPlace) {
  $procs = @()
  try {
    if (-not $WebOnly) {
      Assert-Python
      $procs += Start-Process -FilePath $Python -WorkingDirectory $Fetcher -PassThru -NoNewWindow -ArgumentList @(
        "-m", "uvicorn", "app.fast_api.main:app",
        "--host", "127.0.0.1", "--port", "5000", "--reload"
      )
    }
    if (-not $ApiOnly) {
      Assert-Frontend
      $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
      if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction Stop }
      $procs += Start-Process -FilePath $npmCmd.Source -WorkingDirectory $Frontend -PassThru -NoNewWindow -ArgumentList @("run", "dev")
    }
    Write-Host "Ctrl+C stops everything." -ForegroundColor DarkGray
    Wait-Process -Id ($procs.Id)
  }
  finally {
    foreach ($p in $procs) {
      if ($p -and -not $p.HasExited) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
      }
    }
  }
  return
}

if (-not $WebOnly) {
  Assert-Python
  Start-Process powershell -WorkingDirectory $Fetcher -ArgumentList @(
    "-NoExit", "-Command", $apiCmd
  )
}

if (-not $ApiOnly) {
  Assert-Frontend
  Start-Process powershell -WorkingDirectory $Frontend -ArgumentList @(
    "-NoExit", "-Command", $webCmd
  )
}

Write-Host "Opened separate windows. Close them (or Ctrl+C in each) to stop." -ForegroundColor DarkGray
