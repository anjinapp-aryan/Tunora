"""Phase 19 developer-only GPU operating-envelope measurement (no product code, no new dependency).

Runs REAL Tunora operations against a throwaway backend (own database/storage under --work-dir, port 8010)
that talks to the running ACE-Step server, and samples `nvidia-smi` every 0.5 s while each one runs.
Reported peaks are OBSERVED sampled maxima, not guaranteed absolute hardware peaks (a spike shorter than
the sampling interval can be missed).

Usage (Windows, from the repo root; ACE-Step must be running with the launcher's configuration):
    backend\\.venv\\Scripts\\python.exe docs\\validation\\gpu_envelope.py --work-dir <scratch dir> [--quick]
Uses only the standard library plus `nvidia-smi`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request

BACKEND = "http://127.0.0.1:8010"
ACE = "http://127.0.0.1:8001"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


class Sampler:
    """Background nvidia-smi sampler: memory.used (MiB) and utilization.gpu (%) every 0.5 s."""

    def __init__(self):
        self.samples = []
        self._run = False
        self._thread = None

    def _loop(self):
        while self._run:
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=10).stdout.strip().split(",")
                self.samples.append((time.time(), int(out[0]), int(out[1])))
            except Exception:
                pass
            time.sleep(0.5)

    def start(self):
        self.samples = []
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._run = False
        self._thread.join(timeout=5)
        mem = [s[1] for s in self.samples] or [0]
        util = [s[2] for s in self.samples] or [0]
        return {"before_mib": mem[0], "peak_mib": max(mem), "after_mib": mem[-1], "max_gpu_util_pct": max(util), "samples": len(mem)}


def gpu_now():
    return int(subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip())


def ram_free_gb():
    out = subprocess.run(["powershell", "-Command", "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)"],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else None


def models_loaded():
    inv = call("GET", ACE + "/v1/model_inventory")["data"]["models"]
    return sorted(m["name"] for m in inv if m["is_loaded"])


class Backend:
    def __init__(self, work):
        self.work = work
        self.proc = None
        self.n = 0

    def start(self):
        self.n += 1
        env = dict(os.environ, TUNORA_DB_PATH=os.path.join(self.work, "t.db"), TUNORA_STORAGE_ROOT=os.path.join(self.work, "audio"))
        env.pop("VIRTUAL_ENV", None)
        py = os.path.join(REPO, "backend", ".venv", "Scripts", "python.exe")
        self.proc = subprocess.Popen([py, "-m", "uvicorn", "app.main:app", "--port", "8010"], cwd=os.path.join(REPO, "backend"), env=env,
                                     stdout=open(os.path.join(self.work, f"backend{self.n}.log"), "wb"), stderr=subprocess.STDOUT)
        for _ in range(80):
            try:
                urllib.request.urlopen(BACKEND + "/docs", timeout=2)
                return
            except Exception:
                time.sleep(0.5)
        raise SystemExit("backend did not start")

    def kill(self):
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
        time.sleep(2)


def wait(job_id, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = call("GET", f"{BACKEND}/api/jobs/{job_id}")
        if st["status"] in ("COMPLETED", "FAILED"):
            return st
        time.sleep(0.5)
    raise SystemExit("timeout waiting for " + job_id)


def measure(label, submit, results, sampler, note=""):
    sampler.start()
    t0 = time.time()
    job = submit()
    st = wait(job["id"])
    secs = round(time.time() - t0, 1)
    m = sampler.stop()
    row = {"operation": label, "status": st["status"], "seconds": secs, **m, "models_loaded": models_loaded(), "ram_free_gb": ram_free_gb(), "note": note}
    results.append(row)
    print(json.dumps(row), flush=True)
    return job, st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--quick", action="store_true", help="skip the 60 s and 180 s creates")
    ap.add_argument("--out", default=None, help="write the JSON results here")
    a = ap.parse_args()
    shutil.rmtree(a.work_dir, ignore_errors=True)
    os.makedirs(a.work_dir)
    results, sampler, be = [], Sampler(), Backend(a.work_dir)
    print(f"ACE-Step models loaded at start: {models_loaded()} | GPU MiB now: {gpu_now()} | free RAM GB: {ram_free_gb()}", flush=True)
    be.start()

    def create(duration, title):
        return lambda: call("POST", BACKEND + "/api/jobs", {"prompt": "upbeat pop song with clear female vocals, drums, bass and synth", "lyrics": "la la la sing along tonight, we are alive", "instrumental": False, "duration": duration, "title": title})

    durations = [10, 30] if a.quick else [10, 30, 60, 180]
    songs = {}
    for d in durations:
        job, st = measure(f"Create {d} s", create(d, f"Envelope {d}"), results, sampler)
        songs[d] = job
    base = songs[30] if 30 in songs else songs[durations[0]]
    song, ver = base["song_id"], base["version_id"]

    def op(name, body):
        return lambda: call("POST", f"{BACKEND}/api/songs/{song}/versions/{ver}/{name}", body)

    measure("Extend +30 s (from 30 s)", op("extend", {"extend_seconds": 30}), results, sampler)
    measure("Remix (from 30 s)", op("remix", {"prompt": "slow warm acoustic piano version", "remix_strength": 0.7}), results, sampler)
    measure("Repaint 10-20 s (from 30 s)", op("repaint", {"prompt": "add a soft pad", "repaint_start": 10, "repaint_end": 20}), results, sampler)
    for track in ("vocals", "drums", "bass", "guitar"):
        measure(f"Extract {track} (from 30 s)", op("extract", {"track_name": track}), results, sampler)
    measure("Another Take (from 30 s)", op("another_take", {}), results, sampler)
    if 180 in songs:
        s180, v180 = songs[180]["song_id"], songs[180]["version_id"]
        measure("Extract drums (from 180 s)", lambda: call("POST", f"{BACKEND}/api/songs/{s180}/versions/{v180}/extract", {"track_name": "drums"}), results, sampler)
        measure("Repaint 60-90 s (from 180 s)", lambda: call("POST", f"{BACKEND}/api/songs/{s180}/versions/{v180}/repaint", {"prompt": "brighter", "repaint_start": 60, "repaint_end": 90}), results, sampler)

    # Two jobs submitted at once: ACE-Step queues them; record what actually overlaps.
    sampler.start()
    t0 = time.time()
    j1 = create(30, "Concurrent A")()
    j2 = create(30, "Concurrent B")()
    max_running, order = 0, []
    while time.time() - t0 < 600:
        jobs = [call("GET", f"{BACKEND}/api/jobs/{j['id']}") for j in (j1, j2)]
        stats = call("GET", ACE + "/v1/stats")["data"]["jobs"]
        max_running = max(max_running, stats.get("running", 0))
        for j in jobs:
            if j["status"] in ("COMPLETED", "FAILED") and j["id"] not in [o[0] for o in order]:
                order.append((j["id"], j["status"], round(time.time() - t0, 1)))
        if len(order) == 2:
            break
        time.sleep(0.5)
    m = sampler.stop()
    row = {"operation": "2 concurrent Creates (30 s each)", "status": [o[1] for o in order], "seconds_each_finished": [o[2] for o in order],
           "ace_step_max_running_at_once": max_running, **m, "models_loaded": models_loaded()}
    results.append(row)
    print(json.dumps(row), flush=True)

    # Backend kill/restart in the middle of a 60 s generation (Phase 16 recovery path).
    sampler.start()
    t0 = time.time()
    rj = create(60, "Recovery envelope")()
    while call("GET", f"{BACKEND}/api/jobs/{rj['id']}")["status"] not in ("RUNNING", "COMPLETED", "FAILED") and time.time() - t0 < 60:
        time.sleep(0.3)
    be.kill()
    be.start()
    st = wait(rj["id"])
    m = sampler.stop()
    row = {"operation": "60 s Create with backend kill/restart (recovery)", "status": st["status"], "seconds": round(time.time() - t0, 1), **m, "models_loaded": models_loaded()}
    results.append(row)
    print(json.dumps(row), flush=True)
    be.kill()
    if a.out:
        json.dump(results, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
