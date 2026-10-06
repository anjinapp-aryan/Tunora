"""Phase 30 lab self-test (no GPU): run `python lab_selftest.py`. Exit 0 = all checks pass."""
import json
import py_compile
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

P30 = Path(__file__).resolve().parent
sys.path.insert(0, str(P30))
import controller  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# 1. every lab script compiles
for f in sorted(P30.glob("*.py")):
    try:
        py_compile.compile(str(f), doraise=True)
        check(f"compile {f.name}", True)
    except py_compile.PyCompileError as exc:
        check(f"compile {f.name}", False, str(exc))

# 2. workloads load, shot ids unique, timeouts derive from expected_seconds
for f in sorted((P30 / "jobs").glob("*.json")):
    if f.name == "shot_specs.json":
        continue
    w = json.loads(f.read_text(encoding="utf-8"))
    ids = [s["shot_id"] for s in w["shots"]]
    check(f"workload {f.name}", len(ids) == len(set(ids)) and all(s["expected_seconds"] > 0 for s in w["shots"]))

# 3. validation: a real soak clip passes, garbage and truncated files fail
clip = next((P30 / "outputs/clips").glob("s01.mp4"))
shot = {"kind": "fastwan_clip", "out": str(clip), "width": 704, "height": 1280, "frames": 77}
check("validate real clip", controller.validate(shot)[0])
with tempfile.TemporaryDirectory() as td:
    junk = Path(td) / "junk.mp4"; junk.write_bytes(b"not a video")
    check("validate junk mp4 rejected", not controller.validate(dict(shot, out=str(junk)))[0])
    trunc = Path(td) / "trunc.mp4"; trunc.write_bytes(clip.read_bytes()[: clip.stat().st_size // 3])
    check("validate truncated mp4 rejected", not controller.validate(dict(shot, out=str(trunc)))[0])
    check("validate missing output rejected", controller.validate(dict(shot, out=str(Path(td) / "none.mp4")))[1] == "missing_output")
    img = next((P30 / "outputs/keyframes_klein").glob("s01.png"))
    ishot = {"kind": "klein_keyframe", "out": str(img), "width": 704, "height": 1280}
    check("validate real keyframe", controller.validate(ishot)[0])
    check("validate wrong size rejected", not controller.validate(dict(ishot, width=999))[0])

# 4. regression: orphan matcher must NOT match a shell whose command line merely mentions shot_worker.py
decoy = subprocess.Popen(["cmd", "/c", "ping -n 6 127.0.0.1 >nul & rem shot_worker.py"],
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
time.sleep(1)
matched = [p.pid for p in controller.worker_processes()]
check("orphan matcher ignores decoy shell", decoy.pid not in matched, f"matched={matched}")
decoy.kill()

# 5. state file round-trip (atomic replace)
with tempfile.TemporaryDirectory() as td:
    st = controller.State(Path(td) / "state.json")
    st.shot("x")["status"] = "COMPLETED"; st.save()
    check("state round-trip", controller.State(Path(td) / "state.json").data["shots"]["x"]["status"] == "COMPLETED")

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
print(f"{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
