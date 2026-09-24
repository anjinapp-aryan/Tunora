<#
.SYNOPSIS
  Restarts Tunora: stop all services, wait for the ports to be free, start them again, verify, open the browser.

.DESCRIPTION
  STOP -> WAIT FOR PORTS TO FREE -> START ACE-Step -> START FastAPI -> START Next.js -> VERIFY -> OPEN.
  Uses tunora-services.ps1; see docs/TUNORA-SERVICE-MANAGEMENT.md.

.PARAMETER NoBrowser  Do not open http://localhost:3000/create at the end.
.PARAMETER WaitSeconds How long to wait for each service (default 240).

.EXAMPLE
  .\restart-tunora.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$Force,
    [int]$WaitSeconds = 240
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tunora-services.ps1")

Assert-TunoraPrerequisites $PSScriptRoot   # fail before stopping anything if we could not start again

if (-not (Stop-AllTunora -Force:$Force)) {
    Write-Host "Restart aborted: some ports are still in use (see above). Nothing was started." -ForegroundColor Red
    exit 1
}
foreach ($s in $script:TunoraServices) {
    if (-not (Wait-TunoraPort $s.Port 30 $false)) { Write-Host "Port $($s.Port) did not free up. Aborting." -ForegroundColor Red; exit 1 }
}

$failed = Start-AllTunora -Root $PSScriptRoot -WaitSeconds $WaitSeconds
if ($failed.Count -gt 0) {
    Write-Host ("Not ready: {0}" -f ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
if (-not $NoBrowser -and (Test-TunoraPort 3000)) { Start-Process "http://localhost:3000/create" }
