<#
.SYNOPSIS
  Starts Tunora: ACE-Step (8001), the FastAPI backend (8000) and the Next.js frontend (3000).

.DESCRIPTION
  Each service runs in its own PowerShell window. A service that is already answering on its
  port is left alone. The script then waits until every service actually responds over HTTP
  (ACE-Step loads a model and can take a minute or two) and prints a summary.

.PARAMETER NoWait      Start the services but do not wait for them to become healthy.
.PARAMETER OpenBrowser Open the frontend in the default browser once it is ready.
.PARAMETER WaitSeconds How long to wait for each service (default 240).

.EXAMPLE
  .\start-tunora.ps1 -OpenBrowser
#>
[CmdletBinding()]
param(
    [switch]$NoWait,
    [switch]$OpenBrowser,
    [int]$WaitSeconds = 240,
    [int]$AcePort = 8001,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"

$Root     = $PSScriptRoot
$AceDir   = Join-Path $Root "ACE-Step-1.5"
$BackDir  = Join-Path $Root "backend"
$FrontDir = Join-Path $Root "frontend"

function Write-Step($Tag, $Message, $Color) { Write-Host ("[{0}] {1}" -f $Tag, $Message) -ForegroundColor $Color }

# True when something is listening on the port (IPv4 or IPv6).
function Test-Port([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

# True when the URL answers with a 2xx status within a few seconds.
function Test-Http([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
    }
    catch { return $false }
}

# Opens a new PowerShell window running $Command in $WorkDir, with a recognisable title.
function Start-ServiceWindow([string]$Title, [string]$WorkDir, [string]$Command) {
    $inner = "`$Host.UI.RawUI.WindowTitle = '$Title'; Set-Location -LiteralPath '$WorkDir'; $Command"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-NoProfile", "-Command", $inner) | Out-Null
}

function Assert-Path([string]$Path, [string]$Hint) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing: $Path`n$Hint"
    }
}

# Fail early, with a useful message, before opening any window.
Assert-Path $AceDir   "ACE-Step is a git submodule. Run: git submodule update --init"
Assert-Path (Join-Path $AceDir ".venv\Scripts\python.exe") "Run 'uv sync' inside ACE-Step-1.5."
Assert-Path (Join-Path $BackDir ".venv\Scripts\python.exe") "Run 'uv sync' inside backend."
Assert-Path (Join-Path $FrontDir "node_modules") "Run 'npm install' inside frontend."
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm was not found on PATH." }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "        TUNORA STARTUP" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$services = @(
    @{ Name = "ACE-Step"; Port = $AcePort;      Health = "http://127.0.0.1:$AcePort/health";      Url = "http://127.0.0.1:$AcePort" },
    @{ Name = "Backend";  Port = $BackendPort;  Health = "http://127.0.0.1:$BackendPort/api/jobs?limit=1"; Url = "http://127.0.0.1:$BackendPort" },
    @{ Name = "Frontend"; Port = $FrontendPort; Health = "http://127.0.0.1:$FrontendPort/create";  Url = "http://localhost:$FrontendPort" }
)

# ------------------------------------------
# ACE-Step (model server; the slow one to start)
# ------------------------------------------
if (Test-Port $AcePort) {
    Write-Step "OK" "ACE-Step already listening on :$AcePort" Green
}
else {
    Write-Step "START" "ACE-Step :$AcePort" Yellow
    Start-ServiceWindow "Tunora - ACE-Step" $AceDir "& '.\.venv\Scripts\python.exe' -m acestep.api_server --host 127.0.0.1 --port $AcePort"
}

# ------------------------------------------
# Backend (FastAPI). Data lives in backend\ (tunora.db, data\audio) unless
# TUNORA_DB_PATH / TUNORA_STORAGE_ROOT are already set in the environment.
# ------------------------------------------
if (Test-Port $BackendPort) {
    Write-Step "OK" "Backend already listening on :$BackendPort" Green
}
else {
    Write-Step "START" "Backend :$BackendPort" Yellow
    Start-ServiceWindow "Tunora - Backend" $BackDir "`$env:ACE_STEP_BASE_URL = 'http://127.0.0.1:$AcePort'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
}

# ------------------------------------------
# Frontend (Next.js dev server; proxies /api/* to the backend)
# ------------------------------------------
if (Test-Port $FrontendPort) {
    Write-Step "OK" "Frontend already listening on :$FrontendPort" Green
}
else {
    Write-Step "START" "Frontend :$FrontendPort" Yellow
    Start-ServiceWindow "Tunora - Frontend" $FrontDir "`$env:TUNORA_API_URL = 'http://127.0.0.1:$BackendPort'; npm run dev -- -p $FrontendPort"
}

# ------------------------------------------
# Wait until each service really answers
# ------------------------------------------
$failed = @()
if (-not $NoWait) {
    Write-Host ""
    Write-Host "Waiting for services to respond (up to $WaitSeconds s each)..." -ForegroundColor Cyan
    foreach ($s in $services) {
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        $ready = $false
        while ((Get-Date) -lt $deadline) {
            if (Test-Http $s.Health) { $ready = $true; break }
            Start-Sleep -Seconds 3
        }
        if ($ready) { Write-Step "READY" "$($s.Name)  $($s.Url)" Green }
        else { Write-Step "FAIL" "$($s.Name) did not respond at $($s.Health) - check its window" Red; $failed += $s.Name }
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Services:" -ForegroundColor Cyan
foreach ($s in $services) { Write-Host ("{0,-9}: {1}" -f $s.Name, $s.Url) -ForegroundColor White }
Write-Host "Library  : http://localhost:$FrontendPort/library" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if ($failed.Count -gt 0) {
    Write-Host ("Not ready: {0}" -f ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
if ($OpenBrowser -and -not $NoWait) { Start-Process "http://localhost:$FrontendPort/create" }
