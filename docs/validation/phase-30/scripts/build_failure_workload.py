"""E10 failure-injection workload (lab only). Expected outcome pattern documented in `expected`."""
import json
from pathlib import Path

P30 = Path(__file__).resolve().parent
base = json.loads((P30 / "jobs/identity_kf_klein_10.json").read_text(encoding="utf-8"))["shots"]
clip = json.loads((P30 / "jobs/soak_clips_50.json").read_text(encoding="utf-8"))["shots"][0]
OUT = P30 / "failures/outputs"


def kf(i, src, **kw):
    s = dict(src)
    s.update({"shot_id": f"fi_{i:02d}", "out": str(OUT / f"fi_{i:02d}.png")}, **kw)
    s.pop("spec", None)
    return s


shots = [
    kf(1, base[0]),
    kf(2, base[1]),
    kf(3, base[2], inject="exception", inject_attempts=[1, 2]),
    kf(4, base[3]),
    kf(5, base[4]),
    kf(6, base[5], inject="crash_after_load", inject_attempts=[1]),
    kf(7, base[6], inject="hang_after_load", inject_attempts=[1, 2], expected_seconds=40),
    kf(8, base[7], inject="missing_output", inject_attempts=[1, 2]),
    kf(9, base[8], inject="invalid_output", inject_attempts=[1, 2]),
    dict({k: v for k, v in clip.items() if k != "spec"}, shot_id="fi_10", out=str(OUT / "fi_10.mp4"), inject="corrupt_mp4", inject_attempts=[1]),
    kf(11, base[9]),
]
expected = {"fi_01": "COMPLETED", "fi_02": "COMPLETED", "fi_03": "FAILED (exception x2)", "fi_04": "COMPLETED",
            "fi_05": "COMPLETED", "fi_06": "COMPLETED on retry (crash after load)", "fi_07": "FAILED (hang -> timeout kill x2)",
            "fi_08": "FAILED (missing output x2)", "fi_09": "FAILED (invalid output x2)",
            "fi_10": "COMPLETED on retry (corrupt mp4 caught by validation)", "fi_11": "COMPLETED"}
wl = {"name": "E10 failure injection", "state_dir": str(P30 / "failures/state"), "timeout_factor": 2.5, "max_attempts": 2,
      "shots": shots, "expected": expected}
(P30 / "jobs/failure_injection.json").write_text(json.dumps(wl, indent=1, ensure_ascii=False), encoding="utf-8")
print(len(shots))
