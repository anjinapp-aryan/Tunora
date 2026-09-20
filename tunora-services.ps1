<#
  Shared helpers for start-tunora.ps1 / stop-tunora.ps1 / restart-tunora.ps1 (dot-sourced, not run directly).
  Windows PowerShell 5.1 compatible. No external dependencies.

  SAFETY MODEL (why stopping by port is acceptable)
  -------------------------------------------------
  Ports 8001 (ACE-Step), 8000 (backend) and 3000 (frontend) are RESERVED for Tunora. The scripts
  never kill by process NAME (never "all python" / "all node"); they only stop the process that
  owns one of those three listening ports, plus its child tree and the "Tunora - ..." console
  window that launched it. Extra guard: the port owner must look like a Tunora runtime
  (python / node / uvicorn / npm / cmd / powershell). Anything else on a reserved port is
  reported (PID, name, command line) and left alone unless -Force is passed.
  Processes on other ports are never touched.
#>

$script:TunoraServices = @(
    @{ Key = "ace";      Name = "ACE-Step"; Port = 8001; Title = "Tunora - ACE-Step"; Url = "http://127.0.0.1:8001"; Health = "http://127.0.0.1:8001/health" },
    @{ Key = "backend";  Name = "Backend";  Port = 8000; Title = "Tunora - Backend";  Url = "http://127.0.0.1:8000"; Health = "http://127.0.0.1:8000/api/jobs?limit=1" },
    @{ Key = "frontend"; Name = "Frontend"; Port = 3000; Title = "Tunora - Frontend"; Url = "http://localhost:3000";  Health = "http://127.0.0.1:3000/create" }
)

$script:LooksLikeTunora = '^(python|pythonw|node|uvicorn|npm|npx|cmd|powershell|pwsh)(\.exe)?$'

function Write-Step([string]$Tag, [string]$Message, [string]$Color = "White") {
    Write-Host ("[{0}] {1}" -f $Tag, $Message) -ForegroundColor $Color
}

function Write-Banner([string]$Title) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

# True when something is listening on the port (IPv4 or IPv6).
function Test-TunoraPort([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

# Distinct PIDs that own a listening socket on the port.
function Get-TunoraPortPids([int]$Port) {
    $rows = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $rows) { return @() }
    return @($rows | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })
}

# Name / command line of a PID, for reports.
function Get-TunoraProcessInfo([int]$ProcessId) {
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $cim) { return $null }
    $cmd = [string]$cim.CommandLine
    if ($cmd.Length -gt 160) { $cmd = $cmd.Substring(0, 160) + "..." }
    return [pscustomobject]@{ Pid = $ProcessId; Name = $cim.Name; ParentPid = $cim.ParentProcessId; CommandLine = $cmd }
}

# The "Tunora - <name>" console windows (powershell.exe) that are ancestors of a PID.
function Get-TunoraHostWindows([int]$ProcessId) {
    $found = @()
    $current = $ProcessId
    for ($i = 0; $i -lt 8 -and $current -gt 0; $i++) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $current" -ErrorAction SilentlyContinue
        if (-not $cim) { break }
        if ($cim.Name -eq "powershell.exe" -and [string]$cim.CommandLine -match "WindowTitle = 'Tunora - ") { $found += [int]$cim.ProcessId }
        $current = [int]$cim.ParentProcessId
    }
    return $found
}

function Assert-TunoraPath([string]$Path, [string]$Hint) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing: $Path`n$Hint" }
}

# Fail early, before any window opens.
function Assert-TunoraPrerequisites([string]$Root) {
    Assert-TunoraPath (Join-Path $Root "ACE-Step-1.5") "ACE-Step is a git submodule. Run: git submodule update --init"
    Assert-TunoraPath (Join-Path $Root "ACE-Step-1.5\.venv\Scripts\python.exe") "Run 'uv sync' inside ACE-Step-1.5."
    Assert-TunoraPath (Join-Path $Root "backend\.venv\Scripts\python.exe") "Run 'uv sync' inside backend."
    Assert-TunoraPath (Join-Path $Root "frontend\package.json") "The frontend project is missing."
    Assert-TunoraPath (Join-Path $Root "frontend\node_modules") "Run 'npm install' inside frontend."
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm was not found on PATH." }
}

# Opens a new PowerShell window (logs stay visible) running $Command in $WorkDir.
function Start-TunoraWindow([string]$Title, [string]$WorkDir, [string]$Command) {
    $inner = "`$Host.UI.RawUI.WindowTitle = '$Title'; Set-Location -LiteralPath '$WorkDir'; $Command"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-NoProfile", "-Command", $inner) | Out-Null
}

function Get-TunoraLaunch([hashtable]$Service, [string]$Root) {
    switch ($Service.Key) {
        "ace"      { return @{ Dir = (Join-Path $Root "ACE-Step-1.5"); Cmd = "& '.\.venv\Scripts\python.exe' -m acestep.api_server --host 127.0.0.1 --port $($Service.Port)" } }
        "backend"  { return @{ Dir = (Join-Path $Root "backend");      Cmd = "`$env:ACE_STEP_BASE_URL = 'http://127.0.0.1:8001'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port $($Service.Port)" } }
        "frontend" { return @{ Dir = (Join-Path $Root "frontend");     Cmd = "`$env:TUNORA_API_URL = 'http://127.0.0.1:8000'; npm run dev -- -p $($Service.Port)" } }
    }
}

# Starts one service unless its port is already taken. Returns "started" | "already" | "blocked".
function Start-TunoraService([hashtable]$Service, [string]$Root) {
    if (Test-TunoraPort $Service.Port) {
        foreach ($p in (Get-TunoraPortPids $Service.Port)) {
            $info = Get-TunoraProcessInfo $p
            $who = if ($info) { "PID $p ($($info.Name))" } else { "PID $p" }
            Write-Step "OK" "$($Service.Name) already running on port $($Service.Port), $who" Green
            if ($info -and $info.Name -notmatch $script:LooksLikeTunora) {
                Write-Step "WARN" "Port $($Service.Port) is held by an unexpected process: $($info.CommandLine)" Yellow
            }
        }
        return "already"
    }
    $launch = Get-TunoraLaunch $Service $Root
    Write-Step "START" "$($Service.Name) on port $($Service.Port)" Yellow
    Start-TunoraWindow $Service.Title $launch.Dir $launch.Cmd
    return "started"
}

# Waits until the port is listening. Returns $true/$false.
function Wait-TunoraPort([int]$Port, [int]$TimeoutSeconds, [bool]$Listening = $true) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Test-TunoraPort $Port) -eq $Listening) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return ((Test-TunoraPort $Port) -eq $Listening)
}

# True when the URL answers 2xx within a few seconds.
function Test-TunoraHttp([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
    }
    catch { return $false }
}

# Ends one PID and its children: polite first, then forced for that specific PID tree only.
function Stop-TunoraPid([int]$ProcessId, [int]$GraceSeconds = 5) {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return }
    & cmd.exe /c "taskkill /PID $ProcessId /T >nul 2>&1"
    $deadline = (Get-Date).AddSeconds($GraceSeconds)
    while ((Get-Date) -lt $deadline -and (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 300 }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        & cmd.exe /c "taskkill /PID $ProcessId /T /F >nul 2>&1"
    }
}

# Stops whatever owns the service port. Returns "stopped" | "idle" | "refused" | "failed".
function Stop-TunoraService([hashtable]$Service, [switch]$Force) {
    $port = $Service.Port
    $owners = Get-TunoraPortPids $port
    if ($owners.Count -eq 0) {
        Write-Step "IDLE" "Nothing running on port $port" DarkGray
        return "idle"
    }
    foreach ($owner in $owners) {
        $info = Get-TunoraProcessInfo $owner
        $name = if ($info) { $info.Name } else { "?" }
        if ($info -and $info.Name -notmatch $script:LooksLikeTunora -and -not $Force) {
            Write-Step "SKIP" "Port $port is held by PID $owner ($name), which does not look like a Tunora runtime. Not stopping it (use -Force to override): $($info.CommandLine)" Red
            return "refused"
        }
        Write-Step "STOP" "Stopping Tunora service on port $port, PID $owner ($name)" Yellow
        $windows = Get-TunoraHostWindows $owner
        Stop-TunoraPid $owner
        foreach ($w in $windows) { Stop-TunoraPid $w 2 }   # close the Tunora console window that hosted it
    }
    if (Wait-TunoraPort $port 15 $false) { return "stopped" }
    Write-Step "FAIL" "Port $port is still listening after the stop attempt (owner may need elevated rights)." Red
    return "failed"
}

# Stops all three services; prints the summary. Returns $true when all ports are free.
function Stop-AllTunora([switch]$Force) {
    $results = @{}
    foreach ($s in $script:TunoraServices) { $results[$s.Key] = Stop-TunoraService $s -Force:$Force }
    Write-Banner "TUNORA STOP"
    $ok = $true
    foreach ($s in $script:TunoraServices) {
        $free = -not (Test-TunoraPort $s.Port)
        if (-not $free) { $ok = $false }
        $state = if ($free) { "stopped" } else { "STILL RUNNING ($($results[$s.Key]))" }
        Write-Host ("{0,-9}: {1}  (port {2})" -f $s.Name, $state, $s.Port) -ForegroundColor $(if ($free) { "White" } else { "Red" })
    }
    Write-Host ("=" * 60) -ForegroundColor Cyan
    return $ok
}

# Starts whatever is missing, waits for the ports (and, unless -NoWait, HTTP health), prints the summary.
# Returns the names of services that did not come up.
function Start-AllTunora([string]$Root, [int]$WaitSeconds = 240, [switch]$NoWait) {
    Assert-TunoraPrerequisites $Root
    Write-Banner "TUNORA STARTUP"
    foreach ($s in $script:TunoraServices) { [void](Start-TunoraService $s $Root) }

    $failed = @()
    if (-not $NoWait) {
        Write-Host ""
        Write-Host "Waiting for services (up to $WaitSeconds s each; ACE-Step loads a model)..." -ForegroundColor Cyan
        foreach ($s in $script:TunoraServices) {
            if (-not (Wait-TunoraPort $s.Port $WaitSeconds $true)) {
                Write-Step "FAIL" "$($s.Name) failed to start / port $($s.Port) not listening - check its window" Red
                $failed += $s.Name
                continue
            }
            $deadline = (Get-Date).AddSeconds($WaitSeconds)
            $ready = $false
            while ((Get-Date) -lt $deadline) {
                if (Test-TunoraHttp $s.Health) { $ready = $true; break }
                Start-Sleep -Seconds 2
            }
            if ($ready) { Write-Step "READY" "$($s.Name)  $($s.Url)" Green }
            else { Write-Step "FAIL" "$($s.Name) is listening on $($s.Port) but did not answer $($s.Health)" Red; $failed += $s.Name }
        }
    }

    Write-Banner "TUNORA STARTUP"
    foreach ($s in $script:TunoraServices) { Write-Host ("{0,-9}: {1}" -f $s.Name, $s.Url) -ForegroundColor White }
    Write-Host "Library  : http://localhost:3000/library" -ForegroundColor White
    Write-Host ("=" * 60) -ForegroundColor Cyan
    return $failed
}
