"""Phase 31: objective motion metrics for one clip (lab only; numpy + the approved FFmpeg, no new dependency).

These numbers SUPPORT the visual review; they do not replace it (a big number can be a deformation, not a dance).

  energy          mean |frame[t] - frame[t-1]| over the whole frame (0-255 grey levels)
  centre_energy   same, central subject region (middle 50 % width x middle 80 % height)
  edge_energy     same, left/right 15 % strips (mostly background: rises with camera motion, not subject motion)
  edge_ratio      edge_energy / centre_energy  (>~0.8 suggests camera/background motion; <~0.4 subject-only motion)
  displacement    mean |last - first| (how far the picture ends from where it started)
  shift_px        global translation first->last by phase correlation, in pixels of the 176x320 analysis frame
  zoom            best scale s in [0.80, 1.40] with centre-crop(first, 1/s) resized ~= last  (1.00 = no zoom).
                  Verified on a synthetic centred zoom (1.20 -> 1.20); UNRELIABLE for an off-centre push (e.g. toward
                  the face) combined with a shift: K2 (a visible push-in) reads 0.92. Visual review decides camera moves.
  opening_ratio   mean change of the first 6 frame pairs / median change (fast settling move at the clip start)
  freeze_ratio    fraction of consecutive frame pairs with energy < 0.25 (near-identical frames)
  luma_jump_max   largest change of mean brightness between consecutive frames (lighting jump / flicker)
  luma_jitter     std of consecutive mean-brightness changes
Usage: python motion_metrics.py <clip.mp4> [...]   -> JSON lines on stdout
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

FF = r"I:\Tunora\backend\tools\ffmpeg\bin\ffmpeg.exe"
W, H = 176, 320  # analysis size (portrait); landscape clips are analysed at 320x176


def frames(path: Path) -> np.ndarray:
    probe = subprocess.run([FF, "-hide_banner", "-nostdin", "-i", f"file:{path}"], capture_output=True, text=True)
    landscape = " 1280x704" in probe.stderr
    w, h = (H, W) if landscape else (W, H)
    raw = subprocess.run([FF, "-hide_banner", "-nostdin", "-v", "error", "-i", f"file:{path}", "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=300).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    fa, fb = np.fft.fft2(a * win), np.fft.fft2(b * win)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-9
    c = np.abs(np.fft.ifft2(r))
    y, x = np.unravel_index(np.argmax(c), c.shape)
    if y > a.shape[0] // 2:
        y -= a.shape[0]
    if x > a.shape[1] // 2:
        x -= a.shape[1]
    return float(x), float(y)


def zoom(a: np.ndarray, b: np.ndarray) -> float:
    h, w = a.shape
    best, best_err = 1.0, float("inf")
    for s in np.arange(0.80, 1.401, 0.02):
        if s >= 1.0:  # zoom in: crop centre of a, enlarge
            ch, cw = int(round(h / s)), int(round(w / s))
            y0, x0 = (h - ch) // 2, (w - cw) // 2
            cand = np.asarray(Image.fromarray(a[y0:y0 + ch, x0:x0 + cw]).resize((w, h), Image.BILINEAR))
            ref = b
        else:  # zoom out: crop centre of b instead
            ch, cw = int(round(h * s)), int(round(w * s))
            y0, x0 = (h - ch) // 2, (w - cw) // 2
            cand = a
            ref = np.asarray(Image.fromarray(b[y0:y0 + ch, x0:x0 + cw]).resize((w, h), Image.BILINEAR))
        err = float(np.mean(np.abs(cand - ref)))
        if err < best_err:
            best, best_err = float(s), err
    return round(best, 2)


def metrics(path: Path) -> dict:
    f = frames(path)
    n, h, w = f.shape
    d = np.abs(np.diff(f, axis=0))
    per = d.mean(axis=(1, 2))
    cy0, cy1, cx0, cx1 = int(h * 0.1), int(h * 0.9), int(w * 0.25), int(w * 0.75)
    centre = d[:, cy0:cy1, cx0:cx1].mean()
    e = int(w * 0.15)
    edge = np.concatenate([d[:, :, :e], d[:, :, -e:]], axis=2).mean()
    luma = f.mean(axis=(1, 2))
    dl = np.diff(luma)
    sx, sy = phase_shift(f[0], f[-1])
    return {"clip": str(path), "frames": int(n), "energy": round(float(per.mean()), 2),
            "energy_p90": round(float(np.percentile(per, 90)), 2),
            "centre_energy": round(float(centre), 2), "edge_energy": round(float(edge), 2),
            "edge_ratio": round(float(edge / max(centre, 1e-6)), 2),
            "displacement": round(float(np.abs(f[-1] - f[0]).mean()), 2),
            "shift_px": [round(sx, 1), round(sy, 1)], "zoom": zoom(f[0], f[-1]),
            "freeze_ratio": round(float((per < 0.25).mean()), 2),
            # first 6 frame changes (0.25 s) vs the clip's median change: >~1.5 = a fast "settling" move away from the
            # keyframe at the start of the clip (visible at every montage cut)
            "opening_ratio": round(float(per[:6].mean() / max(np.median(per), 1e-6)), 2),
            "luma_jump_max": round(float(np.abs(dl).max()), 2), "luma_jitter": round(float(dl.std()), 2),
            "energy_profile": [round(float(x), 2) for x in per[:: max(1, len(per) // 12)]]}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(metrics(Path(p))), flush=True)
