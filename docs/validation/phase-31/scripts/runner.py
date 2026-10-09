"""Phase 31 unattended runner (lab only). Launched as an OS-level process (WMI Win32_Process.Create) so it does not
die with the interactive tool session (Phase 30 lesson). Runs the given workloads one after another, one controller
at a time, and keeps the PC awake while it runs (SetThreadExecutionState, released on exit; no power settings change).

Usage: python runner.py <workload.json> [<workload.json> ...]      log: logs/runner.log (+ per-workload controller logs)
A logoff/shutdown still stops it; the controller's state.json then resumes on the next start (COMPLETED shots skip).
"""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

P31 = Path(__file__).resolve().parent
PY = str(P31.parent / ".venv/Scripts/python.exe")
LOG = P31 / "logs/runner.log"


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def controller_running() -> bool:
    import psutil
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if (p.info["name"] or "").lower() == "python.exe" and any(Path(a).name == "controller.py" for a in cmd[1:3]):
                return True
        except Exception:
            pass
    return False


ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
log(f"runner start pid={__import__('os').getpid()} workloads={sys.argv[1:]}")
# Never two controllers at once (a starting controller kills "orphan" workers, which would include a live one).
while controller_running():
    time.sleep(20)
log("no other controller running; starting")
try:
    for wl in sys.argv[1:]:
        name = Path(wl).stem
        log(f"start {name}")
        with (P31 / f"logs/{name}.controller.log").open("a", encoding="utf-8") as out:
            rc = subprocess.call([PY, str(P31 / "controller.py"), str(P31 / wl), "--min-free-gb", "2.0"],
                                 stdout=out, stderr=subprocess.STDOUT, cwd=str(P31))
        log(f"end {name} rc={rc}")
        if rc == 2:  # disk pre-flight block: stop, state preserved
            log("disk pre-flight block; stopping")
            break
finally:
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    log("runner exit")
