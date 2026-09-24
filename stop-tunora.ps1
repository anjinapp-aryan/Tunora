<#
.SYNOPSIS
  Stops the Tunora services listening on ports 8001 (ACE-Step), 8000 (backend) and 3000 (frontend).

.DESCRIPTION
  Stops only the process that owns each reserved port (plus its children and the "Tunora - ..."
  window that hosted it): graceful first, then forced for that specific PID. Never kills by
  process name. A port held by something that does not look like a Tunora runtime is reported
  and left alone unless -Force is given. See docs/TUNORA-SERVICE-MANAGEMENT.md.

.EXAMPLE
  .\stop-tunora.ps1
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tunora-services.ps1")

if (-not (Stop-AllTunora -Force:$Force)) { exit 1 }
