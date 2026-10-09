"""Phase 30 lab controller (NOT production): runs a workload of shots, one child process per shot.

Usage: python controller.py <workload.json> [--max-shots N] [--min-free-gb G]

workload.json: {"name", "state_dir", "timeout_factor", "max_attempts",
                "shots": [{"shot_id", "kind", "out", "prompt", "width", "height", "seed", "expected_seconds",
                           ["frames"], ["image"], ["refs"], ["inject"], ["inject_attempts"]}]}

Guarantees tested in Phase 30:
  * per-shot hard timeout = expected_seconds x timeout_factor; graceful CTRL_BREAK, then forced tree kill
  * every child process (and its descendants) verified gone before the next shot
  * per-shot checkpoint in <state_dir>/state.json (atomic replace); restart resumes, never redoes COMPLETED
  * a shot left RUNNING by a dead controller is reset (its orphan worker is killed first)
  * output validation (ffprobe + full decode + blackdetect/freezedetect for clips, PIL verify for images)
  * disk pre-flight; per-shot VRAM/RAM/disk metrics -> <state_dir>/metrics.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

LAB = Path(__file__).resolve().parents[1]
PY = str(LAB / ".venv/Scripts/python.exe")
WORKER = str(Path(__file__).with_name("shot_worker.py"))
FF = Path(r"I:\Tunora\backend\tools\ffmpeg\bin")
ENV = dict(os.environ, HF_HOME=str(LAB / "hf-home"), HF_HUB_OFFLINE="1", PYTHONUTF8="1", PYTHONFAULTHANDLER="1")


def gpu_used() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=10).stdout
    return int(out.strip().splitlines()[0])


def ram_avail_gb() -> float:
    return round(psutil.virtual_memory().available / 2**30, 2)


def disk_free_gb(path: Path) -> float:
    return round(shutil.disk_usage(path.anchor).free / 2**30, 2)


def worker_processes() -> list[psutil.Process]:
    # Phase 30 fix: the first version matched ANY process whose command line merely contained the text
    # "shot_worker.py" and killed unrelated shells (soak clip_s11). Only python interpreters whose script
    # argument IS shot_worker.py count as workers.
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if (p.info["name"] or "").lower() == "python.exe" and len(cmd) >= 2 and \
                    any(Path(a).name == "shot_worker.py" for a in cmd[1:3]):
                found.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return found


def kill_tree(proc: psutil.Process, grace: float = 15.0) -> str:
    try:
        procs = [proc] + proc.children(recursive=True)
    except psutil.NoSuchProcess:
        return "already_gone"
    try:
        proc.send_signal(signal.CTRL_BREAK_EVENT)  # child started in its own process group
    except Exception:
        pass
    gone, alive = psutil.wait_procs(procs, timeout=grace)
    if alive:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        gone2, alive = psutil.wait_procs(alive, timeout=15)
        return "forced" if not alive else f"STILL_ALIVE:{[p.pid for p in alive]}"
    return "graceful"


def validate(shot: dict) -> tuple[bool, str, dict]:
    out = Path(shot["out"])
    if not out.exists():
        return False, "missing_output", {}
    if out.stat().st_size == 0:
        return False, "empty_output", {}
    if shot["kind"] != "fastwan_clip":
        try:
            from PIL import Image
            with Image.open(out) as im:
                im.verify()
            with Image.open(out) as im:
                size = im.size
            ok = list(size) == [shot["width"], shot["height"]]
            return ok, "" if ok else f"wrong_size:{size}", {"size": list(size), "bytes": out.stat().st_size}
        except Exception as exc:
            return False, f"invalid_image:{exc.__class__.__name__}", {}
    r = subprocess.run([str(FF / "ffprobe.exe"), "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,nb_read_frames:format=duration", "-of", "json",
                        f"file:{out}"], capture_output=True, text=True, timeout=120)
    try:
        d = json.loads(r.stdout or "{}")
        s = d["streams"][0]
        info = {"width": s["width"], "height": s["height"], "frames": int(s.get("nb_read_frames") or 0),
                "duration": float(d["format"]["duration"]), "bytes": out.stat().st_size}
    except Exception:
        return False, "invalid_video:ffprobe", {}
    det = subprocess.run([str(FF / "ffmpeg.exe"), "-hide_banner", "-nostdin", "-v", "info", "-xerror", "-i", f"file:{out}",
                          "-vf", "blackdetect=d=0.3:pix_th=0.10,freezedetect=n=-60dB:d=1.0", "-an", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=300)
    info["black_segments"] = len(re.findall(r"black_start", det.stderr))
    info["freeze_segments"] = len(re.findall(r"freeze_start", det.stderr))
    if det.returncode != 0:
        return False, "invalid_video:decode", info
    if info["frames"] != shot["frames"] or [info["width"], info["height"]] != [shot["width"], shot["height"]]:
        return False, f"invalid_video:shape {info['width']}x{info['height']}x{info['frames']}", info
    if info["black_segments"]:
        return False, "invalid_video:black", info
    return True, "", info


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"shots": {}, "events": []}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def shot(self, sid: str) -> dict:
        return self.data["shots"].setdefault(sid, {"status": "PENDING", "attempts": 0, "history": []})

    def event(self, **kw) -> None:
        self.data["events"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **kw})
        self.save()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workload")
    ap.add_argument("--max-shots", type=int, default=0, help="stop the controller after N shots (resume test)")
    ap.add_argument("--min-free-gb", type=float, default=3.0)
    args = ap.parse_args()
    wl = json.loads(Path(args.workload).read_text(encoding="utf-8"))
    sdir = Path(wl["state_dir"]); sdir.mkdir(parents=True, exist_ok=True)
    st = State(sdir / "state.json")
    metrics = sdir / "metrics.jsonl"
    factor, max_attempts = wl.get("timeout_factor", 2.5), wl.get("max_attempts", 2)
    st.event(type="controller_start", pid=os.getpid(), workload=wl["name"], shots=len(wl["shots"]))

    # Recovery after a controller crash: orphan workers and RUNNING shots.
    orphans = worker_processes()
    for p in orphans:
        st.event(type="orphan_worker_found", pid=p.pid, kill=kill_tree(p, grace=5))
    for sid, s in st.data["shots"].items():
        if s["status"] == "RUNNING":
            s["status"] = "PENDING"
            s["history"].append({"result": "INTERRUPTED_BY_CONTROLLER_EXIT"})
            st.event(type="reset_running", shot=sid)
    st.save()

    done_this_run = 0
    for shot in wl["shots"]:
        sid = shot["shot_id"]
        s = st.shot(sid)
        if s["status"] == "COMPLETED":
            ok, _, _ = validate(shot)
            if ok:
                continue
            s["status"] = "PENDING"
            st.event(type="completed_output_invalid_on_resume", shot=sid)
        if s["status"] == "FAILED" and s["attempts"] >= max_attempts:
            continue
        if args.max_shots and done_this_run >= args.max_shots:
            st.event(type="controller_stop_requested", after=done_this_run)
            return 0
        free = disk_free_gb(Path(shot["out"]))
        if free < args.min_free_gb:
            s["status"] = "BLOCKED_DISK"
            st.event(type="disk_preflight_block", shot=sid, free_gb=free, min_free_gb=args.min_free_gb)
            print(f"[controller] disk pre-flight blocked at {sid}: {free} GB free", flush=True)
            return 2

        while s["attempts"] < max_attempts:
            s["attempts"] += 1
            attempt = s["attempts"]
            job = dict(shot)
            if job.get("inject") and attempt not in job.get("inject_attempts", [1]):
                job.pop("inject")
            job_path = sdir / f"{sid}.job.json"
            job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            Path(shot["out"]).unlink(missing_ok=True)
            timeout = shot["expected_seconds"] * factor
            rec = {"shot_id": sid, "attempt": attempt, "kind": shot["kind"], "inject": job.get("inject"),
                   "start": time.strftime("%Y-%m-%d %H:%M:%S"), "timeout_s": round(timeout),
                   "vram_before_mib": gpu_used(), "ram_avail_before_gb": ram_avail_gb(),
                   "disk_free_before_gb": free}
            s["status"] = "RUNNING"; st.save()
            log = open(sdir / f"{sid}.attempt{attempt}.log", "w", encoding="utf-8")
            t0 = time.perf_counter()
            child = subprocess.Popen([PY, WORKER, str(job_path)], stdout=log, stderr=subprocess.STDOUT, env=ENV,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            rec["pid"] = child.pid
            peak = {"vram": 0, "rss": 0, "min_avail": 1e9}
            stop = threading.Event()

            def sample():
                while not stop.is_set():
                    try:
                        peak["vram"] = max(peak["vram"], gpu_used())
                        pp = psutil.Process(child.pid)
                        rss = sum(p.memory_info().rss for p in [pp] + pp.children(recursive=True))
                        peak["rss"] = max(peak["rss"], rss)
                    except Exception:
                        pass
                    peak["min_avail"] = min(peak["min_avail"], psutil.virtual_memory().available)
                    stop.wait(0.5)

            th = threading.Thread(target=sample, daemon=True); th.start()
            try:
                rc = child.wait(timeout=timeout)
                rec["termination"] = "exited"
            except subprocess.TimeoutExpired:
                rec["termination"] = "timeout:" + kill_tree(psutil.Process(child.pid))
                rc = child.poll()
            stop.set(); th.join()
            log.close()
            rec["wall_seconds"] = round(time.perf_counter() - t0, 1)
            rec["exit_code"] = rc
            leftovers = [p.pid for p in worker_processes()]
            if leftovers:
                rec["orphans_after_exit"] = leftovers
                for pid in leftovers:
                    try:
                        kill_tree(psutil.Process(pid), grace=5)
                    except psutil.NoSuchProcess:
                        pass
            # VRAM recovery: wait (max 30 s) for VRAM to return near the pre-shot level.
            t1 = time.perf_counter()
            while time.perf_counter() - t1 < 30 and gpu_used() > rec["vram_before_mib"] + 300:
                time.sleep(0.5)
            rec["vram_recovery_seconds"] = round(time.perf_counter() - t1, 1)
            rec.update({"vram_peak_mib": peak["vram"], "vram_after_mib": gpu_used(),
                        "worker_rss_peak_gb": round(peak["rss"] / 2**30, 2),
                        "ram_min_avail_gb": round(peak["min_avail"] / 2**30, 2), "ram_avail_after_gb": ram_avail_gb(),
                        "disk_free_after_gb": disk_free_gb(Path(shot["out"])),
                        "python_procs_after": len([p for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower() == 'python.exe'])})
            ok, reason, info = validate(shot) if rc == 0 else (False, f"exit_code:{rc}" if rec["termination"] == "exited" else rec["termination"], {})
            rec.update({"valid": ok, "failure_reason": reason, "output": info,
                        "end": time.strftime("%Y-%m-%d %H:%M:%S")})
            res = Path(shot["out"] + ".result.json")
            if res.exists():
                rec["worker_result"] = json.loads(res.read_text(encoding="utf-8"))
            with metrics.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            s["history"].append({k: rec[k] for k in ("attempt", "exit_code", "termination", "valid", "failure_reason", "wall_seconds")})
            s["status"] = "COMPLETED" if ok else "FAILED"
            st.save()
            print(f"[controller] {sid} attempt={attempt} rc={rc} {rec['termination']} valid={ok} {reason} "
                  f"wall={rec['wall_seconds']}s vram {rec['vram_before_mib']}->{rec['vram_peak_mib']}->{rec['vram_after_mib']} "
                  f"rss_peak={rec['worker_rss_peak_gb']}GB min_avail={rec['ram_min_avail_gb']}GB", flush=True)
            if ok:
                break
        done_this_run += 1
    summary = {k: sum(1 for s in st.data["shots"].values() if s["status"] == k) for k in ("COMPLETED", "FAILED", "PENDING", "BLOCKED_DISK")}
    st.event(type="controller_done", summary=summary)
    print("[controller] done", summary, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
