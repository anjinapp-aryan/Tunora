"""GPU hand-off test (lab only): ACE-Step start -> load (one 10 s generation) -> stop via Tunora's
stop-tunora.ps1 -> confirm VRAM release. Usage: python handoff_ace.py <label>
Starts ACE-Step with the same command as tunora-services.ps1 (port 8001, ACESTEP_CONFIG_PATH2).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from monitor import gpu_used_mib

ACE_DIR = Path(r"I:\Tunora\ACE-Step-1.5")
BASE = "http://127.0.0.1:8001"
LOG = Path(__file__).resolve().parents[1] / "logs" / "handoff.jsonl"


def http(path: str, body: dict | None = None, timeout: float = 10):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    rec: dict = {"label": label, "vram_before_start_mib": gpu_used_mib()}
    peak = {"v": 0}
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            peak["v"] = max(peak["v"], gpu_used_mib())
            stop.wait(0.5)

    threading.Thread(target=sample, daemon=True).start()
    env = dict(os.environ, ACESTEP_CONFIG_PATH2="acestep-v15-base")
    t0 = time.perf_counter()
    proc = subprocess.Popen([str(ACE_DIR / ".venv/Scripts/python.exe"), "-m", "acestep.api_server", "--host", "127.0.0.1",
                             "--port", "8001"], cwd=ACE_DIR, env=env,
                            stdout=open(LOG.with_name(f"ace_{label}.log"), "w"), stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    while True:
        try:
            http("/health", timeout=3)
            break
        except Exception:
            if proc.poll() is not None:
                raise SystemExit(f"ACE-Step exited with {proc.returncode}")
            time.sleep(1)
    rec["ace_ready_seconds"] = round(time.perf_counter() - t0, 1)
    rec["vram_after_health_mib"] = gpu_used_mib()

    t1 = time.perf_counter()
    task = http("/release_task", {"prompt": "short calm piano test", "lyrics": "", "vocal_language": "en",
                                  "audio_format": "mp3", "audio_duration": 10, "use_random_seed": False, "seed": 7},
                timeout=60)
    task_id = (task.get("data") or task)["task_id"]
    status = None
    while time.perf_counter() - t1 < 900:
        res = http("/query_result", {"task_id_list": [task_id]}, timeout=30)
        item = (res.get("data") if isinstance(res, dict) else res)[0]
        status = item.get("status")
        if status in (1, 2):
            break
        time.sleep(2)
    rec["generation_status"] = {1: "succeeded", 2: "failed"}.get(status, f"timeout/{status}")
    rec["first_generation_seconds"] = round(time.perf_counter() - t1, 1)
    time.sleep(3)
    rec["vram_loaded_idle_mib"] = gpu_used_mib()
    rec["vram_peak_while_ace_mib"] = peak["v"]

    t2 = time.perf_counter()
    stopper = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              r"I:\Tunora\stop-tunora.ps1"], capture_output=True, text=True, timeout=180)
    rec["stop_script_exit"] = stopper.returncode
    rec["stop_script_tail"] = stopper.stdout[-600:]
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass
    deadline = time.perf_counter() + 60
    while time.perf_counter() < deadline and gpu_used_mib() > rec["vram_before_start_mib"] + 300:
        time.sleep(0.5)
    rec["stop_to_vram_released_seconds"] = round(time.perf_counter() - t2, 1)
    rec["vram_after_stop_mib"] = gpu_used_mib()
    rec["ace_process_alive_after_stop"] = proc.poll() is None
    stop.set()
    rec["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
