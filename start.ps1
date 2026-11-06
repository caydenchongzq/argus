<#
.SYNOPSIS
  Start Argus — local TradingAgents dashboard (127.0.0.1 only).
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
  Write-Warning "TradingAgents data not found at $ta — set TRADINGAGENTS_ROOT if needed."
}

if ($Install -or -not (Test-Path (Join-Path $Root ".venv"))) {
  Write-Host "Creating venv and installing Argus dependencies..." -ForegroundColor Cyan
  python -m venv .venv
  & "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip
  & "$Root\.venv\Scripts\pip.exe" install -r requirements.txt
}

$env:TRADINGAGENTS_ROOT = if ($env:TRADINGAGENTS_ROOT) { $env:TRADINGAGENTS_ROOT } else { $ta }
$env:DASHBOARD_RUNS_DIR = Join-Path $Root "runs"
$env:ARGUS_PORT = "$Port"

Write-Host ""
Write-Host "  Argus  ->  http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  TradingAgents root ->  $($env:TRADINGAGENTS_ROOT)"
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

& "$Root\.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port $Port
