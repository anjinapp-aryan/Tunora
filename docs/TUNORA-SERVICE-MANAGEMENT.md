# Tunora local service management

Three local services, managed by PowerShell scripts in the repo root (Windows PowerShell 5.1, no extra dependencies):

| Service | Port | Directory |
|---|---|---|
| ACE-Step (model server) | 8001 | `ACE-Step-1.5` |
| FastAPI backend | 8000 | `backend` |
| Next.js frontend | 3000 | `frontend` |

## Daily workflow

```powershell
.\start-tunora.ps1      # start what is not running (add -OpenBrowser to open /create)
.\stop-tunora.ps1       # stop all three
.\restart-tunora.ps1    # stop, wait for ports to free, start, verify, open /create (-NoBrowser to skip)
```

## What each script does

- **start-tunora.ps1**: checks prerequisites (both `.venv\Scripts\python.exe`, `frontend\package.json`, `node_modules`, `npm`) and fails with a clear message before opening anything. For each port already listening it prints the owning PID and starts nothing (no duplicates). Otherwise it opens a new PowerShell window per service (logs stay visible). It then waits for each port to listen and each service to answer HTTP (ACE-Step loads a model; up to 240 s, `-WaitSeconds`). A service that never listens is reported as failed and the script exits 1. `-NoWait` skips waiting; `-OpenBrowser` opens `http://localhost:3000/create` only after port 3000 is listening.
- **stop-tunora.ps1**: for each port finds the owning PID, prints `Stopping Tunora service on port N, PID X`, ends that process tree (graceful `taskkill` first, forced for that PID only after 5 s) and closes the `Tunora - ...` window that hosted it. Prints "Nothing running" for idle ports, then verifies every port is free (exit 1 otherwise).
- **restart-tunora.ps1**: checks prerequisites first (so a broken setup does not leave you with nothing running), stops all, waits until 8001/8000/3000 are really free, starts all three, verifies, opens the browser.
- **tunora-services.ps1**: shared helpers (`Test-TunoraPort`, `Get-TunoraPortPids`, `Stop-TunoraService`, `Wait-TunoraPort`, `Start-TunoraService`, ...). Dot-sourced by the three scripts; not run directly.

## Safety model

Nothing is killed by process name, so other Python/Node projects are untouched. Only the process that **listens on 8001, 8000 or 3000** (reserved for Tunora), its children and its Tunora console window are stopped. Extra guard: the port owner must look like a Tunora runtime (python, node, uvicorn, npm, cmd, powershell). Anything else on those ports is reported with PID, name and command line and left running; `-Force` overrides. Start never kills anything; an occupied port is reported and assumed to be the service.

## Troubleshooting

- **"Missing: ...\.venv\Scripts\python.exe"**: run `uv sync` in that project. **"Missing node_modules"**: `npm install` in `frontend`. **ACE-Step folder empty**: `git submodule update --init`.
- **Port still listening after stop**: the owner may be another user's or elevated process; run PowerShell as administrator or stop it yourself (see below).
- **Frontend "did not answer"**: first `next dev` compile can be slow; check its window. Only one `next dev` can use a given `.next` dir.
- **ACE-Step not ready**: the model is still loading; watch its window.

## Start manually (three windows)

```powershell
cd I:\Tunora\ACE-Step-1.5; $env:ACESTEP_CONFIG_PATH2 = "acestep-v15-base"; & ".\.venv\Scripts\python.exe" -m acestep.api_server --host 127.0.0.1 --port 8001
cd I:\Tunora\backend;      .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd I:\Tunora\frontend;     npm run dev
```

## Who is using a port?

```powershell
$p = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId = $p" | Select ProcessId, Name, CommandLine
```

## ACE-Step second model (required for Extract)

`tunora-services.ps1` starts ACE-Step with `ACESTEP_CONFIG_PATH2=acestep-v15-base` (a second model slot next to the default turbo model). Extract needs the base model: turbo does not support the `extract` task, and ACE-Step **silently** falls back to the turbo handler when the requested model is not loaded (`acestep/api/job_model_selection.py`). Tunora now checks the `dit_model` field of every Extract result and fails the job (visibly, with the generic "Generation failed." message) unless it is `acestep-v15-base`; nothing is saved for a rejected result.

- Both models load on the first request (the health check alone does not load them). Measured on the RTX 5060 Ti 16 GB: idle about 1.5 GB after start; both models plus the language model resident about 11.6 GB; peak about 14.9-15.3 GB during real generations (turbo only: about 10.2 GB). Headroom is about 1-1.4 GB.
- If you start ACE-Step without the variable (for example a manual start), Extract jobs fail; Create, Extend, Remix, Repaint and Another Take are unaffected.
- To free the extra VRAM you can drop the variable (Extract then fails visibly by design).
