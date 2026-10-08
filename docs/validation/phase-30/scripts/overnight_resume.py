"""Unattended overnight completion of the Phase 30 soak (lab only). Launched DETACHED so it survives the
Claude Code session ending. It starts a resume controller ("Run C") as soon as either
  (a) the planned hard kill of the Run B controller has happened (resume/watcher.out written), or
  (b) the Run B controller is gone for any other reason (e.g. the session that launched it ended),
and exits once the soak workload reports done. All output: soak/runC.log, resume/overnight.log."""
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

P30 = Path(__file__).resolve().parent
LAB = P30.parent
ST = P30 / "soak/state/state.json"
LOG = P30 / "resume/overnight.log"


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def controllers() -> list[int]:
    return [p.pid for p in psutil.process_iter(["cmdline"])
            if p.info["cmdline"] and any("controller.py" in a for a in p.info["cmdline"])
            and any("soak_clips_50" in a for a in p.info["cmdline"])]


def all_done() -> bool:
    try:
        d = json.loads(ST.read_text(encoding="utf-8"))
    except Exception:
        return False
    return len(d["shots"]) == 50 and all(s["status"] in ("COMPLETED", "FAILED") for s in d["shots"].values())


log("overnight_resume started")
while True:
    if all_done():
        log("soak already complete; exiting")
        sys.exit(0)
    if not controllers():
        reason = "planned hard kill" if (P30 / "resume/watcher.out").stat().st_size > 0 else "controller not running"
        log(f"starting Run C ({reason})")
        with (P30 / "soak/runC.log").open("a", encoding="utf-8") as out:
            rc = subprocess.run([str(LAB / ".venv/Scripts/python.exe"), str(P30 / "controller.py"),
                                 str(P30 / "jobs/soak_clips_50.json")], stdout=out, stderr=subprocess.STDOUT,
                                env=dict(__import__("os").environ, PYTHONUTF8="1")).returncode
        log(f"Run C exited rc={rc}; done={all_done()}")
        if all_done() or rc != 0:
            sys.exit(rc)
    time.sleep(10)
