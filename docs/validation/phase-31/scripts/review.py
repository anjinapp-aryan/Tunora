"""Phase 31 user-review package (lab only).

  python review.py strips              12-frame strip per clip (frames 0,7,...,70,76) -> contact-sheets/strips/<id>.jpg
  python review.py sheets              one sheet per motion folder (all strips of that folder stacked)
  python review.py manifest            review/manifest.json + manifest.csv + index.html (watch every clip in a browser)
                                       + metrics/motion_metrics.jsonl (motion_metrics.py on every valid clip)
Scores live in review/scores.json (written by the reviewer) and are merged into the manifest when present.
"""
from __future__ import annotations

import csv
import html
import json
import subprocess
import sys
from pathlib import Path

P31 = Path(__file__).resolve().parent
sys.path.insert(0, str(P31))
from motion_metrics import metrics  # noqa: E402

FF = r"I:\Tunora\backend\tools\ffmpeg\bin\ffmpeg.exe"
FONT = "I\\:/Tunora/backend/app/music_videos/fonts/Poppins-SemiBold.ttf"
PICK = [0, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 76]


def workload_shots() -> list[dict]:
    shots = []
    for f in sorted((P31 / "jobs").glob("*.json")):
        w = json.loads(f.read_text(encoding="utf-8"))
        if "state_dir" not in w:  # montage plans live in jobs/ too
            continue
        state = Path(w["state_dir"]) / "state.json"
        st = json.loads(state.read_text(encoding="utf-8"))["shots"] if state.exists() else {}
        mfile = Path(w["state_dir"]) / "metrics.jsonl"
        recs = {}
        if mfile.exists():
            for line in mfile.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                recs[r["shot_id"]] = r  # last attempt wins
        for s in w["shots"]:
            if s["kind"] != "fastwan_clip":
                continue
            r = recs.get(s["shot_id"], {})
            shots.append({**s, "workload": f.name, "status": st.get(s["shot_id"], {}).get("status", "PENDING"),
                          "attempts": st.get(s["shot_id"], {}).get("attempts", 0), "record": r})
    return shots


def strip(shot: dict) -> Path:
    clip = Path(shot["out"])
    out = P31 / "contact-sheets/strips" / f"{shot['shot_id']}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    land = shot["width"] > shot["height"]
    tw = 300 if land else 160
    sel = "+".join(f"eq(n\\,{i})" for i in PICK)
    m = shot.get("meta", {})
    label = f"{shot['shot_id']}  {m.get('wording', '')}  seed {shot['seed']}  | {m.get('action', '')} | cam: {m.get('camera', '')}"
    label = label.replace(":", " -").replace("'", "")[:170]
    vf = (f"select='{sel}',scale={tw}:-2,tile={len(PICK)}x1,pad=iw:ih+30:0:30:black,"
          f"drawtext=fontfile='{FONT}':text='{label}':fontcolor=white:fontsize=17:x=8:y=6")
    subprocess.run([FF, "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", f"file:{clip}", "-vf", vf,
                    "-frames:v", "1", "-q:v", "3", str(out)], check=True, timeout=120)
    return out


def sheets(shots: list[dict]) -> None:
    by = {}
    for s in shots:
        p = P31 / "contact-sheets/strips" / f"{s['shot_id']}.jpg"
        if p.exists():
            parent = Path(s["out"]).parent
            key = f"{parent.parent.name}" if parent.name == "clips" else parent.name  # montage/clips vs montage_16x9/clips
            by.setdefault(key, []).append(p)
    for folder, ps in by.items():
        out = P31 / "contact-sheets" / f"{folder}.jpg"
        ins = []
        for p in ps:
            ins += ["-i", f"file:{p}"]
        if len(ps) == 1:
            subprocess.run([FF, "-hide_banner", "-v", "error", "-y", *ins, "-q:v", "3", str(out)], check=True)
        else:
            subprocess.run([FF, "-hide_banner", "-v", "error", "-y", *ins, "-filter_complex",
                            "".join(f"[{i}:v]" for i in range(len(ps))) + f"vstack=inputs={len(ps)}", "-q:v", "3", str(out)], check=True)
        print("sheet", out.name, len(ps))


def manifest(shots: list[dict]) -> None:
    scores = {}
    sf = P31 / "review/scores.json"
    if sf.exists():
        scores = json.loads(sf.read_text(encoding="utf-8"))
    mm = {}
    mfile = P31 / "metrics/motion_metrics.jsonl"
    if mfile.exists():
        for line in mfile.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            mm[Path(r["clip"]).resolve()] = r
    new = []
    for s in shots:
        p = Path(s["out"]).resolve()
        if s["status"] == "COMPLETED" and p not in mm:
            mm[p] = metrics(p)
            new.append(mm[p])
    with mfile.open("a", encoding="utf-8") as fh:
        for r in new:
            fh.write(json.dumps(r) + "\n")
    rows = []
    for s in shots:
        r, m = s["record"], s.get("meta", {})
        mt = mm.get(Path(s["out"]).resolve(), {})
        sc = scores.get(s["shot_id"], {})
        rows.append({"shot_id": s["shot_id"], "file": str(Path(s["out"]).relative_to(P31)), "folder": Path(s["out"]).parent.name,
                     "motion_id": m.get("motion_id", ""), "motion": m.get("motion", ""), "wording": m.get("wording", ""),
                     "stage": m.get("stage", ""), "action": m.get("action", ""), "camera": m.get("camera", ""),
                     "keyframe": m.get("keyframe", ""), "seed": s["seed"], "prompt": s["prompt"],
                     "resolution": f"{s['width']}x{s['height']}", "frames": s["frames"],
                     "duration_s": (r.get("output") or {}).get("duration", ""),
                     "generation_s": r.get("wall_seconds", ""), "vram_peak_mib": r.get("vram_peak_mib", ""),
                     "worker_rss_peak_gb": r.get("worker_rss_peak_gb", ""), "ram_min_avail_gb": r.get("ram_min_avail_gb", ""),
                     "technical_status": s["status"], "attempts": s["attempts"], "failure_reason": r.get("failure_reason", ""),
                     "energy": mt.get("energy", ""), "centre_energy": mt.get("centre_energy", ""),
                     "edge_ratio": mt.get("edge_ratio", ""), "zoom": mt.get("zoom", ""), "shift_px": mt.get("shift_px", ""),
                     "luma_jump_max": mt.get("luma_jump_max", ""),
                     **{k: sc.get(k, "") for k in ("realism", "mechanics", "identity", "stability", "usability", "executed",
                                                   "failures", "notes")}})
    (P31 / "review").mkdir(exist_ok=True)
    (P31 / "review/manifest.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    with (P31 / "review/manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    cards = []
    for r in rows:
        if r["technical_status"] != "COMPLETED":
            cards.append(f"<div class=c><b>{html.escape(r['shot_id'])}</b> {html.escape(r['technical_status'])} {html.escape(str(r['failure_reason']))}</div>")
            continue
        score = " · ".join(f"{k} {r[k]}" for k in ("realism", "mechanics", "identity", "stability", "usability") if r[k] != "")
        cards.append(
            f"<div class=c><video src='../{html.escape(r['file'].replace(chr(92), '/'))}' controls loop muted preload=metadata></video>"
            f"<b>{html.escape(r['shot_id'])}</b> {html.escape(r['motion'])} {html.escape(r['wording'])} seed {r['seed']}"
            f"<br><i>{html.escape(r['action'])}</i><br>camera: {html.escape(r['camera'])}"
            f"<br>gen {r['generation_s']} s · energy {r['energy']} · edge/centre {r['edge_ratio']} · zoom {r['zoom']}"
            f"<br><span class=s>{html.escape(score)}</span> <span class=f>{html.escape(str(r['failures']))}</span>"
            f"<br>{html.escape(str(r['notes']))}</div>")
    page = ("<!doctype html><meta charset=utf-8><title>Phase 31 motion review</title><style>"
            "body{font:13px system-ui;background:#111;color:#ddd;margin:16px}.g{display:flex;flex-wrap:wrap;gap:12px}"
            ".c{width:260px;background:#1c1c1c;padding:8px;border-radius:6px}video{width:100%;background:#000}"
            ".s{color:#8f8}.f{color:#f99}</style><h1>Phase 31 — motion vocabulary review</h1>"
            "<p>Each clip loops; scores are the reviewer's. Your own verdict goes in review/user-review.md.</p>"
            f"<div class=g>{''.join(cards)}</div>")
    (P31 / "review/index.html").write_text(page, encoding="utf-8")
    print("manifest rows", len(rows), "new metrics", len(new))


if __name__ == "__main__":
    mode = sys.argv[1]
    shots = workload_shots()
    if mode == "strips":
        for s in shots:
            if s["status"] == "COMPLETED" and not (P31 / "contact-sheets/strips" / f"{s['shot_id']}.jpg").exists():
                print("strip", strip(s).name)
    elif mode == "sheets":
        sheets(shots)
    elif mode == "manifest":
        manifest(shots)
