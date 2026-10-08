"""Tunora's FFmpeg policy for Music Videos (Phase 23; docs/LICENSE-AUDIT.md: LGPL-only).

Phase 22B found that the FFmpeg on this machine's PATH (winget "full_build") is configured with
`--enable-gpl` / libx264, and that FFmpeg's `eq` filter is GPL-only. So Tunora never assumes an
FFmpeg is acceptable: it resolves one binary, reads its own build configuration, refuses any
`--enable-gpl` / `--enable-nonfree` build, and requires exactly the capabilities the validated
renderer uses (libass `ass` filter, `colorlevels`/`hue`, OpenH264 H.264 encoder, native AAC).

Resolution order (nothing is ever downloaded):
  1. TUNORA_FFMPEG_DIR   -- a directory containing ffmpeg + ffprobe
  2. backend/tools/ffmpeg/bin -- where the operator places the approved LGPL build (git-ignored)
  3. ffmpeg on PATH      -- accepted only if it passes the same checks
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.music_videos.errors import FFmpegPolicyError

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "tools" / "ffmpeg" / "bin"
FORBIDDEN_FLAGS = ("--enable-gpl", "--enable-nonfree")
REQUIRED_FILTERS = ("ass", "colorlevels", "hue", "scale", "crop", "setsar", "format")
REQUIRED_ENCODERS = ("libopenh264", "aac")
logger = logging.getLogger(__name__)
_EXE = ".exe" if sys.platform == "win32" else ""


@dataclass(frozen=True)
class FFmpegTools:
    ffmpeg: Path
    ffprobe: Path
    version: str          # first line of `ffmpeg -version`
    configuration: str    # the `configuration:` line, verbatim

    @property
    def bin_dir(self) -> Path:
        return self.ffmpeg.parent


Runner = Callable[[list[str]], str]


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=True).stdout


def _candidate_dirs() -> list[Path]:
    dirs = []
    env = os.environ.get("TUNORA_FFMPEG_DIR")
    if env:
        dirs.append(Path(env))
    dirs.append(DEFAULT_DIR)
    on_path = shutil.which("ffmpeg")
    if on_path:
        dirs.append(Path(on_path).parent)
    return dirs


def inspect(bin_dir: Path, run: Runner = _run) -> FFmpegTools:
    """Verify one FFmpeg installation against the policy. Raises FFmpegPolicyError."""

    ffmpeg, ffprobe = bin_dir / f"ffmpeg{_EXE}", bin_dir / f"ffprobe{_EXE}"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise FFmpegPolicyError("FFmpeg/ffprobe not found.")
    try:
        version_text = run([str(ffmpeg), "-hide_banner", "-version"])
        filters = run([str(ffmpeg), "-hide_banner", "-filters"])
        encoders = run([str(ffmpeg), "-hide_banner", "-encoders"])
    except (OSError, subprocess.SubprocessError) as exc:
        raise FFmpegPolicyError("FFmpeg could not be run.") from exc
    lines = version_text.splitlines()
    configuration = next((l.strip() for l in lines if l.strip().startswith("configuration:")), "")
    if not configuration:
        raise FFmpegPolicyError("FFmpeg build configuration could not be verified.")
    flags = configuration.split()
    forbidden = [f for f in FORBIDDEN_FLAGS if f in flags]
    if forbidden:
        raise FFmpegPolicyError(
            f"FFmpeg at this location is a GPL/non-free build ({', '.join(forbidden)}); "
            "Tunora requires an LGPL-only build.")
    filter_names = {parts[1] for parts in (l.split() for l in filters.splitlines()) if len(parts) >= 3}
    encoder_names = {parts[1] for parts in (l.split() for l in encoders.splitlines()) if len(parts) >= 2}
    missing = [f"filter {n}" for n in REQUIRED_FILTERS if n not in filter_names]
    missing += [f"encoder {n}" for n in REQUIRED_ENCODERS if n not in encoder_names]
    if missing:
        raise FFmpegPolicyError(f"FFmpeg is missing required features: {', '.join(missing)}.")
    return FFmpegTools(ffmpeg, ffprobe, lines[0].strip() if lines else "", configuration)


def resolve(run: Runner = _run) -> FFmpegTools:
    """The first candidate that passes the policy. Rejections are reported, never skipped silently."""

    reasons = []
    for bin_dir in _candidate_dirs():
        try:
            return inspect(bin_dir, run)
        except FFmpegPolicyError as exc:
            logger.warning("rejected FFmpeg candidate %s: %s", bin_dir, exc)
            reasons.append(f"{bin_dir}: {exc}")
    raise FFmpegPolicyError(
        "No approved FFmpeg found. Install an LGPL-only FFmpeg build (with libass and OpenH264) in "
        "backend/tools/ffmpeg or set TUNORA_FFMPEG_DIR. Checked: " + "; ".join(reasons or ["nothing"]))


_cached: Optional[FFmpegTools] = None


def approved_ffmpeg() -> FFmpegTools:
    """Resolve once per process (the check runs three short FFmpeg commands)."""

    global _cached
    if _cached is None:
        _cached = resolve()
    return _cached
