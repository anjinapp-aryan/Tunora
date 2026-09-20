<#
.SYNOPSIS
  Starts Tunora: ACE-Step (8001), the FastAPI backend (8000) and the Next.js frontend (3000).

.DESCRIPTION
  Each service runs in its own PowerShell window (logs stay visible). A service whose port is
  already listening is left alone (no duplicates). The script then waits until each port is
  listening and the service answers over HTTP (ACE-Step loads a model; allow a minute or two).
  Shared logic lives in tunora-services.ps1. See docs/TUNORA-SERVICE-MANAGEMENT.md.

.PARAMETER NoWait      Start the services but do not wait for them.
.PARAMETER OpenBrowser Open http://localhost:3000/create once the frontend is actually listening.
.PARAMETER WaitSeconds How long to wait for each service (default 240).

.EXAMPLE
  .\start-tunora.ps1 -OpenBrowser
#>
[CmdletBinding()]
param(
    [switch]$NoWait,
    [switch]$OpenBrowser,
    [int]$WaitSeconds = 240
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tunora-services.ps1")

$failed = Start-AllTunora -Root $PSScriptRoot -WaitSeconds $WaitSeconds -NoWait:$NoWait

if ($failed.Count -gt 0) {
    Write-Host ("Not ready: {0}" -f ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
if ($OpenBrowser -and -not $NoWait -and (Test-TunoraPort 3000)) { Start-Process "http://localhost:3000/create" }
