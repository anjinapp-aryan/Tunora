"""Phase 31 analysis (lab only): performance/reliability from controller metrics + score/vocabulary tables.

  python analyze.py   -> reports/performance.json, reports/vocabulary.json (printed summary)
"""
from __future__ import annotations

import json
import shutil
import statistics as st
from pathlib import Path

P31 = Path(__file__).resolve().parent
KEYS = ["realism", "mechanics", "identity", "stability", "usability"]


def records() -> list[dict]:
    out = []
    for m in sorted((P31 / "metrics").glob("*/metrics.jsonl")):
        for line in m.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            r["state"] = m.parent.name
            out.append(r)
    return out


def perf(recs: list[dict]) -> dict:
    clips = [r for r in recs if r["kind"] == "fastwan_clip"]
    kfs = [r for r in recs if r["kind"] == "klein_keyframe"]

    def summary(rs: list[dict]) -> dict:
        ok = [r for r in rs if r["valid"]]
        w = [r["wall_seconds"] for r in ok]
        return {"attempts": len(rs), "valid": len(ok), "failed_attempts": len(rs) - len(ok),
                "timeouts": sum(1 for r in rs if str(r.get("termination", "")).startswith("timeout")),
                "wall_mean_s": round(st.mean(w), 1) if w else None, "wall_median_s": round(st.median(w), 1) if w else None,
                "wall_min_s": min(w) if w else None, "wall_max_s": max(w) if w else None,
                "slowest": max(ok, key=lambda r: r["wall_seconds"])["shot_id"] if ok else None,
                "vram_peak_mib_max": max((r["vram_peak_mib"] for r in rs), default=None),
                "worker_rss_peak_gb_max": max((r["worker_rss_peak_gb"] for r in rs), default=None),
                "ram_min_avail_gb_min": min((r["ram_min_avail_gb"] for r in rs), default=None),
                "timeout_budget_used_max": round(max((r["wall_seconds"] / r["timeout_s"] for r in ok), default=0), 2),
                "orphans_after_exit": sum(1 for r in rs if r.get("orphans_after_exit")),
                "vram_recovery_s_max": max((r.get("vram_recovery_seconds", 0) for r in rs), default=None)}

    disk = {}
    for d in sorted((P31 / "outputs").iterdir()):
        if d.is_dir():
            disk[d.name] = round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 2**20, 1)
    return {"clips": summary(clips), "keyframes": summary(kfs), "disk_mib_by_folder": disk,
            "disk_mib_total": round(sum(disk.values()), 1), "disk_free_gb_now": round(shutil.disk_usage("I:\\").free / 2**30, 2),
            "gpu_seconds_total": round(sum(r["wall_seconds"] for r in recs), 1),
            "interrupted_attempts": "see state.json history INTERRUPTED_BY_CONTROLLER_EXIT"}


def vocabulary() -> dict:
    """Group every scored clip by motion category; montage clips (mp_/ml_) count under the motion they used."""
    s = json.loads((P31 / "review/scores.json").read_text(encoding="utf-8"))
    rows = {r["shot_id"]: r for r in json.loads((P31 / "review/manifest.json").read_text(encoding="utf-8"))}
    out = {}
    for sid, v in s.items():
        cat = sid.split("_")[0]
        if cat in ("mp", "ml"):
            cat = rows[sid]["motion_id"]  # e.g. "K2" -> K
        key = cat[0] if cat[0] in "ABCDEFGHIJKLMN" and cat[1:] in ("1", "2", "3") else cat
        out.setdefault(key, []).append(
            {"clip": sid, "wording": cat, "mean": round(st.mean(v[k] for k in KEYS), 2), "usability": v["usability"],
             "executed": v["executed"]})
    return {k: {"clips": v, "avg_mean": round(st.mean(x["mean"] for x in v), 2),
                "avg_usability": round(st.mean(x["usability"] for x in v), 2)} for k, v in sorted(out.items())}


if __name__ == "__main__":
    recs = records()
    p = perf(recs)
    v = vocabulary()
    (P31 / "reports").mkdir(exist_ok=True)
    (P31 / "reports/performance.json").write_text(json.dumps(p, indent=1), encoding="utf-8")
    (P31 / "reports/vocabulary.json").write_text(json.dumps(v, indent=1), encoding="utf-8")
    print(json.dumps(p, indent=1))
    for k, x in v.items():
        print(k, x["avg_mean"], x["avg_usability"], [(c["clip"], c["usability"]) for c in x["clips"]])
