"""Phase 31 lab self-test (no GPU): `python lab_selftest.py`. Exit 0 = all checks pass.

Must NOT run while a GPU controller is running: test 6 starts a real controller, and every controller kills orphan
shot_worker.py processes on start (by design). The test refuses to start if a controller is running.
"""
import hashlib
import json
import py_compile
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

P31 = Path(__file__).resolve().parent
P30 = P31.parent / "phase-30"
sys.path.insert(0, str(P31))
import controller  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def controller_running() -> bool:
    for p in psutil.process_iter(["name", "cmdline"]):
        cmd = p.info["cmdline"] or []
        if (p.info["name"] or "").lower() == "python.exe" and any(Path(a).name == "controller.py" for a in cmd[1:3]):
            return True
    return False


if controller_running():
    print("REFUSED: a controller is running (GPU work in progress); run the self-test afterwards")
    sys.exit(2)

# 1. every lab script compiles
for f in sorted(P31.glob("*.py")):
    try:
        py_compile.compile(str(f), doraise=True)
        check(f"compile {f.name}", True)
    except py_compile.PyCompileError as exc:
        check(f"compile {f.name}", False, str(exc))

# 2. harness reused unchanged from Phase 30 (byte-identical)
for name in ("controller.py", "shot_worker.py", "keep_awake.py", "contact_sheet.py"):
    a, b = (hashlib.sha256((d / name).read_bytes()).hexdigest() for d in (P30, P31))
    check(f"harness {name} identical to Phase 30", a == b)

# 3. workloads: unique ids, positive timeouts, controlled design (within a category only the action/camera differ)
for f in sorted((P31 / "jobs").glob("*.json")):
    w = json.loads(f.read_text(encoding="utf-8"))
    if "state_dir" not in w:  # montage plan, not a workload
        check(f"plan {f.name} bars contiguous", all(abs(a["end"] - b["start"]) < 1e-6 for a, b in zip(w["shots"], w["shots"][1:])))
        continue
    ids = [s["shot_id"] for s in w["shots"]]
    check(f"workload {f.name} ids unique / timeouts", len(ids) == len(set(ids)) and all(s["expected_seconds"] > 0 for s in w["shots"]))
m = json.loads((P31 / "jobs/matrix.json").read_text(encoding="utf-8"))["shots"]
check("matrix: 14 categories x 2 wordings", len(m) == 28 and len({s["meta"]["motion_id"] for s in m}) == 14)
check("matrix: one seed for every stage-1 clip", {s["seed"] for s in m} == {31001})
fixed_ok = True
for s in m:
    tail = s["prompt"].split(". Setting: ", 1)[1].split(" Camera: ")[0]
    fixed_ok &= tail == json.loads((P31 / "jobs/matrix.json").read_text(encoding="utf-8"))["shots"][0]["prompt"].split(". Setting: ", 1)[1].split(" Camera: ")[0]
check("matrix: setting/light text identical in every clip", fixed_ok)
check("matrix: K-M vary only the camera text", all(
    a["meta"]["action"] == b["meta"]["action"] and a["meta"]["camera"] != b["meta"]["camera"]
    for a, b in zip(m[20:26:2], m[21:26:2])))
check("matrix: A-J vary only the action text (static camera)", all(
    s["meta"]["camera"] == "static camera" for s in m if s["meta"]["motion_id"] in "ABCDEFGHIJ"))

# 4. validation: a real Phase 31 clip passes; junk / truncated / missing / wrong-size are rejected
clips = sorted((P31 / "outputs").glob("*/*.mp4"))
clip = next((c for c in clips if c.parent.name not in ("montage", "montage_16x9")), None)
if clip:
    shot = {"kind": "fastwan_clip", "out": str(clip), "width": 704, "height": 1280, "frames": 77}
    check("validate real clip", controller.validate(shot)[0], str(clip))
    with tempfile.TemporaryDirectory() as td:
        junk = Path(td) / "junk.mp4"; junk.write_bytes(b"not a video")
        check("validate junk rejected", not controller.validate(dict(shot, out=str(junk)))[0])
        trunc = Path(td) / "trunc.mp4"; trunc.write_bytes(clip.read_bytes()[: clip.stat().st_size // 3])
        check("validate truncated rejected", not controller.validate(dict(shot, out=str(trunc)))[0])
        check("validate missing rejected", controller.validate(dict(shot, out=str(Path(td) / "x.mp4")))[1] == "missing_output")
        check("validate wrong frame count rejected", not controller.validate(dict(shot, frames=121))[0])
else:
    check("validate real clip", False, "no Phase 31 clip yet")

# 5. orphan matcher must NOT match a shell that merely mentions shot_worker.py (Phase 30 regression)
decoy = subprocess.Popen(["cmd", "/c", "ping -n 6 127.0.0.1 >nul & rem shot_worker.py"],
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
time.sleep(1)
check("orphan matcher ignores decoy shell", decoy.pid not in [p.pid for p in controller.worker_processes()])
decoy.kill()

# 6. timeout + failure isolation with the REAL controller (no GPU: injected failures happen before torch loads)
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    shots = [
        {"shot_id": "hang", "kind": "fastwan_clip", "out": str(td / "hang.mp4"), "prompt": "x", "width": 704, "height": 1280,
         "frames": 77, "seed": 1, "expected_seconds": 4, "inject": "hang", "inject_attempts": [1, 2]},
        {"shot_id": "missing", "kind": "fastwan_clip", "out": str(td / "missing.mp4"), "prompt": "x", "width": 704,
         "height": 1280, "frames": 77, "seed": 1, "expected_seconds": 30, "inject": "missing_output", "inject_attempts": [1, 2]},
        {"shot_id": "exception", "kind": "fastwan_clip", "out": str(td / "exc.mp4"), "prompt": "x", "width": 704,
         "height": 1280, "frames": 77, "seed": 1, "expected_seconds": 30, "inject": "exception", "inject_attempts": [1, 2]},
    ]
    wl = td / "wl.json"
    wl.write_text(json.dumps({"name": "selftest", "state_dir": str(td / "state"), "timeout_factor": 2.5, "max_attempts": 1,
                              "shots": shots}), encoding="utf-8")
    t0 = time.perf_counter()
    r = subprocess.run([controller.PY, str(P31 / "controller.py"), str(wl), "--min-free-gb", "0.5"], capture_output=True,
                       text=True, timeout=300, env=controller.ENV)
    took = time.perf_counter() - t0
    st = json.loads((td / "state/state.json").read_text(encoding="utf-8"))["shots"]
    recs = [json.loads(x) for x in (td / "state/metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    hang = next(x for x in recs if x["shot_id"] == "hang")
    check("timeout: hung worker killed at its budget", hang["termination"].startswith("timeout:") and 10 <= hang["wall_seconds"] < 40,
          f"{hang['termination']} {hang['wall_seconds']}s")
    check("failure isolation: controller continued past failures", r.returncode == 0 and len(recs) == 3, r.stdout[-300:])
    check("failure isolation: each failure recorded", all(st[s]["status"] == "FAILED" for s in ("hang", "missing", "exception")))
    check("failure reasons distinct", {x["shot_id"]: x["failure_reason"] for x in recs}["missing"] == "missing_output")
    check("no worker process left behind", controller.worker_processes() == [], str(controller.worker_processes()))
    check("selftest controller run bounded", took < 200, f"{took:.0f}s")

# 7. montage outputs (when present): 1080x1920 / 1920x1080, 30 fps, H.264, AAC audio preserved for the full length
for name, (w, h) in (("montage/montage_9x16.mp4", (1080, 1920)), ("montage_16x9/montage_16x9.mp4", (1920, 1080))):
    p = P31 / "outputs" / name
    if not p.exists():
        check(f"{name} present", False, "not built yet")
        continue
    r = subprocess.run([str(controller.FF / "ffprobe.exe"), "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,width,height,r_frame_rate,duration,sample_rate:format=duration",
                        "-of", "json", f"file:{p}"], capture_output=True, text=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    dur = float(d["format"]["duration"])
    check(f"{name} resolution {w}x{h}", (v["width"], v["height"]) == (w, h), f"{v['width']}x{v['height']}")
    check(f"{name} 30 fps", v["r_frame_rate"] == "30/1", v["r_frame_rate"])
    check(f"{name} H.264", v["codec_name"] == "h264", v["codec_name"])
    check(f"{name} AAC audio present and full length", a is not None and a["codec_name"] == "aac" and abs(float(a["duration"]) - dur) < 0.1,
          f"{a and a.get('duration')} vs {dur}")
    dec = subprocess.run([str(controller.FF / "ffmpeg.exe"), "-v", "error", "-xerror", "-i", f"file:{p}", "-f", "null", "-"],
                         capture_output=True, text=True)
    check(f"{name} decodes fully", dec.returncode == 0)

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
print(f"{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
