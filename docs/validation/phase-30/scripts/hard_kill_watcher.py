"""E11 helper (lab only): when <shot> has been RUNNING for <delay> s, kill ONLY the controller process
(not its children), deliberately orphaning the running worker. Usage: python hard_kill_watcher.py clip_s25 60"""
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

P30 = Path(__file__).resolve().parent
ST = P30 / "soak/state/state.json"
LOG = P30 / "resume/hard_kill.log"
shot, delay = sys.argv[1], float(sys.argv[2])

while True:
    try:
        d = json.loads(ST.read_text(encoding="utf-8"))
        if d["shots"].get(shot, {}).get("status") == "RUNNING":
            break
    except Exception:
        pass
    time.sleep(3)
time.sleep(delay)
d = json.loads(ST.read_text(encoding="utf-8"))
ctrl = [e for e in d["events"] if e["type"] == "controller_start"][-1]["pid"]
workers = [p.pid for p in psutil.process_iter(["cmdline"])
           if p.info["cmdline"] and any("shot_worker.py" in a for a in p.info["cmdline"])]
msg = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "shot_running": shot, "killed_controller_pid": ctrl,
       "worker_pids_left_running": workers}
r = subprocess.run(["taskkill", "/F", "/PID", str(ctrl)], capture_output=True, text=True)  # controller only, not /T
msg["taskkill"] = (r.returncode, r.stdout.strip()[:200])
time.sleep(3)
msg["controller_alive_after"] = psutil.pid_exists(ctrl)
msg["workers_alive_after"] = [p for p in workers if psutil.pid_exists(p)]
with LOG.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(msg) + "\n")
print(json.dumps(msg), flush=True)
