"""Phase 30 analysis (lab only): soak time series, leak trend, timing, failure rates -> metrics/*.json|csv."""
from __future__ import annotations

import csv
import json
import statistics as st
from pathlib import Path

P30 = Path(__file__).resolve().parent


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def slope(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 4) if den else None


def summarize(recs: list[dict]) -> dict:
    ok = [r for r in recs if r["valid"]]
    def stat(key, rs=ok):
        v = [r[key] for r in rs if r.get(key) is not None]
        return {"n": len(v), "min": min(v), "max": max(v), "mean": round(st.mean(v), 2), "median": round(st.median(v), 2)} if v else None
    return {"attempts": len(recs), "valid": len(ok), "invalid": len(recs) - len(ok),
            "failure_reasons": sorted({r["failure_reason"] for r in recs if not r["valid"]}),
            "wall_seconds": stat("wall_seconds"), "vram_peak_mib": stat("vram_peak_mib"),
            "vram_after_mib": stat("vram_after_mib", recs), "worker_rss_peak_gb": stat("worker_rss_peak_gb"),
            "ram_min_avail_gb": stat("ram_min_avail_gb", recs), "ram_avail_after_gb": stat("ram_avail_after_gb", recs),
            "vram_recovery_seconds": stat("vram_recovery_seconds", recs),
            "orphans_after_exit": sum(1 for r in recs if r.get("orphans_after_exit")),
            "output_bytes": stat("bytes", [dict(r, bytes=r["output"].get("bytes")) for r in ok if r.get("output")])}


def main() -> None:
    out = P30 / "metrics"; out.mkdir(exist_ok=True)
    soak = load(P30 / "soak/state/metrics.jsonl")
    # series = last attempt per shot in execution order (time series of the soak)
    series = sorted(soak, key=lambda r: r["start"])
    with (out / "soak_timeseries.csv").open("w", newline="", encoding="utf-8") as fh:
        cols = ["seq", "shot_id", "attempt", "start", "end", "frames", "wall_seconds", "pid", "exit_code", "termination", "valid",
                "failure_reason", "vram_before_mib", "vram_peak_mib", "vram_after_mib", "vram_recovery_seconds",
                "ram_avail_before_gb", "worker_rss_peak_gb", "ram_min_avail_gb", "ram_avail_after_gb",
                "disk_free_before_gb", "disk_free_after_gb", "output_bytes", "python_procs_after", "orphans_after_exit"]
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for i, r in enumerate(series, 1):
            w.writerow({**{c: r.get(c) for c in cols}, "seq": i, "frames": (r.get("output") or {}).get("frames"),
                        "output_bytes": (r.get("output") or {}).get("bytes")})
    idx = list(range(1, len(series) + 1))
    trend = {
        "vram_after_slope_mib_per_shot": slope(idx, [r["vram_after_mib"] for r in series]),
        "ram_avail_after_slope_gb_per_shot": slope(idx, [r["ram_avail_after_gb"] for r in series]),
        "worker_rss_peak_slope_gb_per_shot": slope(idx, [r["worker_rss_peak_gb"] for r in series]),
        "wall_seconds_slope_per_shot_77f": slope([i for i, r in zip(idx, series) if (r.get("output") or {}).get("frames") == 77],
                                                 [r["wall_seconds"] for r in series if (r.get("output") or {}).get("frames") == 77]),
        "python_procs_after_max": max(r["python_procs_after"] for r in series) if series else None,
        "disk_used_by_soak_gb": round(series[0]["disk_free_before_gb"] - series[-1]["disk_free_after_gb"], 2) if series else None,
    }
    by_frames = {}
    for f in (77, 121):
        rs = [r for r in series if (r.get("output") or {}).get("frames") == f or (not r["valid"] and f == 77)]
        by_frames[f] = summarize([r for r in rs if (r.get("output") or {}).get("frames") == f])
    checkpoints = {}
    for n in (10, 20, 30, 50):
        part = series[:n]
        checkpoints[n] = {"valid": sum(r["valid"] for r in part), "of": len(part),
                          "vram_after_max": max((r["vram_after_mib"] for r in part), default=None),
                          "ram_avail_after_min": min((r["ram_avail_after_gb"] for r in part), default=None)}
    report = {
        "soak": summarize(series), "soak_by_frames": by_frames, "soak_trend": trend, "soak_checkpoints": checkpoints,
        "e1_baseline": summarize(load(P30 / "worker/e1/metrics.jsonl")),
        "identity_keyframes_klein": summarize(load(P30 / "identity/klein_state/metrics.jsonl")),
        "identity_keyframes_zimage": summarize(load(P30 / "identity/zimage_state/metrics.jsonl")),
        "identity_refs": summarize(load(P30 / "identity/refs_state/metrics.jsonl")),
        "failure_injection": [{k: r.get(k) for k in ("shot_id", "attempt", "inject", "termination", "exit_code", "valid", "failure_reason",
                                                     "wall_seconds", "vram_before_mib", "vram_peak_mib", "vram_after_mib")}
                              for r in load(P30 / "failures/state/metrics.jsonl")],
    }
    (out / "phase30_summary.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("soak", "soak_trend", "soak_checkpoints")}, indent=1))


if __name__ == "__main__":
    main()
