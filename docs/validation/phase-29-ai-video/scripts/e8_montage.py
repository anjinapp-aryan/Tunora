"""E8/E9: validate generated clips and assemble the beat-cut montage with the approved LGPL FFmpeg
(lab script, not production). Mirrors the production renderer's conventions: argument lists only,
`file:` inputs, scale-to-cover + crop, 30 fps, OpenH264 at the VideoOutputProfile HD bitrate, AAC 192k.

Usage: python e8_montage.py <plan.json> <clip_dir> <clip_suffix> <out.mp4> <portrait|landscape>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

BIN = Path(r"I:\Tunora\backend\tools\ffmpeg\bin")
FFMPEG, FFPROBE = str(BIN / "ffmpeg.exe"), str(BIN / "ffprobe.exe")
LAB = Path(__file__).resolve().parents[1]
PROFILES = {"portrait": (1080, 1920), "landscape": (1920, 1080)}  # vertical_hd / landscape_hd
FPS = 30


def probe(path: Path) -> dict:
    r = subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,nb_read_frames,r_frame_rate,codec_name:format=duration,size",
                        "-of", "json", f"file:{path}"], capture_output=True, text=True, timeout=120)
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    return {"ok": r.returncode == 0 and bool(s), "width": s.get("width"), "height": s.get("height"),
            "frames": int(s.get("nb_read_frames") or 0), "codec": s.get("codec_name"),
            "duration": float(d.get("format", {}).get("duration") or 0), "bytes": int(d.get("format", {}).get("size") or 0)}


def detect(path: Path) -> dict:
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", f"file:{path}", "-vf",
                        "blackdetect=d=0.3:pix_th=0.10,freezedetect=n=-60dB:d=1.0", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=300)
    return {"black_segments": len(re.findall(r"black_start", r.stderr)),
            "freeze_segments": len(re.findall(r"freeze_start", r.stderr)), "decode_ok": r.returncode == 0}


def main() -> None:
    plan_path, clip_dir, suffix, out, orientation = sys.argv[1:6]
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    w, h = PROFILES[orientation]
    report, inputs, chains = [], [], []
    for i, shot in enumerate(plan["shots"]):
        clip = Path(clip_dir) / f"clip{shot['index']:02d}_{suffix}.mp4"
        info = {**probe(clip), **detect(clip)}
        info["valid"] = info["ok"] and info["decode_ok"] and info["duration"] >= shot["duration"] - 0.02 and info["black_segments"] == 0
        report.append({"shot": shot["index"], "clip": clip.name, **info})
        inputs += ["-protocol_whitelist", "file", "-i", f"file:{clip}"]
        chains.append(f"[{i}:v]trim=duration={shot['duration']:.3f},setpts=PTS-STARTPTS,fps={FPS},"
                      f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1[v{i}]")
    n = len(plan["shots"])
    start, end = plan["shots"][0]["start"], plan["shots"][-1]["end"]
    graph = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]"
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", *inputs,
           "-protocol_whitelist", "file", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", f"file:{LAB / 'song/source.mp3'}",
           "-filter_complex", graph, "-map", "[v]", "-map", f"{n}:a:0",
           "-c:v", "libopenh264", "-profile:v", "high", "-b:v", "8M", "-maxrate", "10M", "-bufsize", "16M",
           "-r", str(FPS), "-g", str(FPS * 2), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-t", f"{end - start:.3f}", "-movflags", "+faststart", out]
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    seconds = round(time.perf_counter() - t0, 1)
    final = probe(Path(out)) if r.returncode == 0 else {"ok": False, "stderr": r.stderr[-800:]}
    a = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration,sample_rate,codec_name",
                        "-of", "json", f"file:{out}"], capture_output=True, text=True).stdout
    result = {"clips": report, "assembly_seconds": seconds, "window": [start, end], "target_duration": round(end - start, 3),
              "final": final, "final_audio": json.loads(a or "{}").get("streams")}
    Path(out).with_suffix(".json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "clips"}, indent=1))
    for c in report:
        print(c["shot"], c["clip"], c["width"], c["height"], c["frames"], round(c["duration"], 3), "black", c["black_segments"],
              "freeze", c["freeze_segments"], "valid", c["valid"])


if __name__ == "__main__":
    main()
