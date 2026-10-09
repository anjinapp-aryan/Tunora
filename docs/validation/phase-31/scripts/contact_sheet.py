"""Labelled contact sheets with the approved FFmpeg (drawtext + Poppins OFL font). Lab only.

Usage:
  python contact_sheet.py images <out.jpg> <cols> <tile_w> <label_prefix> <img1> [img2 ...]
  python contact_sheet.py clips  <out.jpg> <tile_w> <clip1.mp4> [clip2 ...]   (rows = clips, 4 frames each: 0, 1/3, 2/3, last)
Labels come from the sibling .result.json / job metadata where available.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FF = r"I:\Tunora\backend\tools\ffmpeg\bin\ffmpeg.exe"
FONT = "I\\:/Tunora/backend/app/music_videos/fonts/Poppins-SemiBold.ttf"


def label_for(path: Path, prefix: str) -> str:
    sid = path.stem
    job = path.parents[2] / "jobs"
    seed = ""
    for f in job.glob("*.json"):
        try:
            for s in json.loads(f.read_text(encoding="utf-8")).get("shots", []):
                if Path(s["out"]).resolve() == path.resolve():
                    seed = f" seed {s['seed']}"
                    break
        except Exception:
            pass
        if seed:
            break
    return f"{sid}{seed} {prefix}".replace(":", "-")


def tile_filter(i: int, label: str, w: int, h: int) -> str:
    return (f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"drawbox=x=0:y=ih-26:w=iw:h=26:color=black@0.6:t=fill,"
            f"drawtext=fontfile='{FONT}':text='{label}':fontcolor=white:fontsize=15:x=6:y=h-21[t{i}]")


def images(out: str, cols: int, w: int, prefix: str, imgs: list[str]) -> None:
    h = int(w * 1280 / 704)
    inputs, chains = [], []
    for i, p in enumerate(imgs):
        inputs += ["-i", p]
        chains.append(tile_filter(i, label_for(Path(p), prefix), w, h))
    n = len(imgs)
    rows = (n + cols - 1) // cols
    while n < rows * cols:  # pad grid with black tiles
        inputs += ["-f", "lavfi", "-i", f"color=black:s={w}x{h}:d=1"]
        chains.append(f"[{n}:v]null[t{n}]")
        n += 1
    layout = "|".join(f"{(k % cols) * w}_{(k // cols) * h}" for k in range(n))
    graph = ";".join(chains) + ";" + "".join(f"[t{k}]" for k in range(n)) + f"xstack=inputs={n}:layout={layout}[o]"
    subprocess.run([FF, "-hide_banner", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[o]",
                    "-frames:v", "1", "-q:v", "3", out], check=True)


def clips(out: str, w: int, paths: list[str]) -> None:
    h = int(w * 1280 / 704)
    rows = []
    tmp = Path(out).with_suffix("")
    for r, p in enumerate(paths):
        row = f"{tmp}_row{r}.png"
        sid = Path(p).stem
        subprocess.run([FF, "-hide_banner", "-v", "error", "-y", "-i", p, "-vf",
                        f"select='eq(n\\,0)+eq(n\\,25)+eq(n\\,51)+eq(n\\,76)',scale={w}:{h},tile=4x1,"
                        f"drawbox=x=0:y=0:w=150:h=24:color=black@0.6:t=fill,"
                        f"drawtext=fontfile='{FONT}':text='{sid}':fontcolor=white:fontsize=15:x=6:y=4",
                        "-fps_mode", "passthrough", "-frames:v", "1", row], check=True)
        rows.append(row)
    inputs = sum((["-i", r] for r in rows), [])
    subprocess.run([FF, "-hide_banner", "-v", "error", "-y", *inputs, "-filter_complex",
                    "".join(f"[{i}]" for i in range(len(rows))) + f"vstack=inputs={len(rows)}[o]" if len(rows) > 1 else "[0]null[o]",
                    "-map", "[o]", "-frames:v", "1", "-q:v", "3", out], check=True)
    for r in rows:
        Path(r).unlink(missing_ok=True)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "images":
        images(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6:])
    else:
        clips(sys.argv[2], int(sys.argv[3]), sys.argv[4:])
