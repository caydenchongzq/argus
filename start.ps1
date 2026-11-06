<#
.SYNOPSIS
  Start Argus - local TradingAgents dashboard (127.0.0.1 only).
#>
[CmdletBinding()]
param(
  [int]$Port = 8787,
  [switch]$Install
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$ta = "D:\software development\trading\TradingAgents"
if (-not (Test-Path (Join-Path $ta "data\my_book.json"))) {
  Write-Warning "TradingAgents data not found at $ta - set TRADINGAGENTS_ROOT if needed."
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$venvPip = Join-Path $Root ".venv\Scripts\pip.exe"

if ($Install -or -not (Test-Path $venvPython)) {
  Write-Host "Creating venv and installing Argus dependencies..." -ForegroundColor Cyan
  python -m venv .venv
  & $venvPython -m pip install --upgrade pip
  & $venvPip install -r requirements.txt
}

if ($env:TRADINGAGENTS_ROOT) {
  # keep existing
} else {
  $env:TRADINGAGENTS_ROOT = $ta
}
$env:DASHBOARD_RUNS_DIR = Join-Path $Root "runs"
$env:ARGUS_PORT = "$Port"

Write-Host ""
Write-Host ("  Argus  ->  http://127.0.0.1:{0}" -f $Port) -ForegroundColor Green
Write-Host ("  TradingAgents root ->  {0}" -f $env:TRADINGAGENTS_ROOT)
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

& $venvPython -m uvicorn server:app --host 127.0.0.1 --port $Port
