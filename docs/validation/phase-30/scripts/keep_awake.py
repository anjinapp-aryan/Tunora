"""Lab helper: prevent idle system sleep while the soak controller runs (SetThreadExecutionState).
No power settings are changed; the request is released automatically when this process exits.
Exits when no soak controller is running for 60 s."""
import ctypes
import time

import psutil

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def controller_running() -> bool:
    for p in psutil.process_iter(["name", "cmdline"]):
        cmd = p.info["cmdline"] or []
        if (p.info["name"] or "").lower() == "python.exe" and any(a.endswith("controller.py") for a in cmd[1:3]):
            return True
    return False


ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
print(time.strftime("%H:%M:%S"), "keep-awake ON", flush=True)
idle = 0
while idle < 6:
    time.sleep(10)
    idle = 0 if controller_running() else idle + 1
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
print(time.strftime("%H:%M:%S"), "keep-awake OFF (no controller)", flush=True)
