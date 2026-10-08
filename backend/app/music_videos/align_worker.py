"""Lyrics -> TimedLyrics by local forced alignment (stable-ts, MIT; Whisper weights, MIT).

Adapted from the validated Phase 22B prototype (`align.py`). Runs as its own process
(`python -m app.music_videos.align_worker ...`, started by `LocalForcedAligner`) so that torch and
the Whisper model never load into the API process and a stuck alignment can be killed.

It never invents or rewrites lyrics: it only times the lyric text it is given, and reports every
line it could not time in `unaligned_lines` instead of returning bogus timestamps. Two failure
signatures seen on real ACE-Step songs (Phase 22A/22B) are detected:
  * pinned tail -- words stuck at start == end == audio duration (lyrics the audio never reaches)
  * collapsed line -- a whole line squeezed to < 0.1 s per word (a line the singer skipped)

Line grouping (one display line per lyric line; "[Chorus]"-style tags skipped) is adapted from
dcmcand/dynamic-typography-videos scripts/transcribe.py (Apache-2.0).

Exit codes: 0 ok (JSON written to --out), 3 alignment engine not installed, 4 nothing to align,
5 refusing (engine returned a different number of words), 6 FFmpeg not the approved one.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PINNED_EPSILON = 0.25
MIN_SECONDS_PER_WORD = 0.1


def lyric_lines(text: str) -> list[str]:
    """Display lines: non-blank, not a "[Section]" tag, punctuation-only tokens (e.g. "-") dropped
    because the aligner does not time them."""

    out = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line or (line.startswith("[") and line.endswith("]") and line.count("[") == 1):
            continue
        line = " ".join(t for t in line.split() if any(ch.isalnum() for ch in t))
        if line:
            out.append(line)
    return out


def probe_duration(ffprobe: str, audio: Path) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration",
         "-of", "json", f"file:{audio}"], capture_output=True, text=True, check=True, timeout=60)
    return float(json.loads(result.stdout)["format"]["duration"])


def group(words: list[tuple[str, float, float]], lines: list[str], duration: float) -> tuple[list, list]:
    """Split aligned words back into lyric lines and keep only the lines that were really timed."""

    timed, unaligned, i = [], [], 0
    for line in lines:
        n = len(line.split())
        chunk = words[i:i + n]
        i += n
        pinned = any(e - s <= 0.001 and s >= duration - PINNED_EPSILON for _, s, e in chunk)
        collapsed = (chunk[-1][2] - chunk[0][1]) < MIN_SECONDS_PER_WORD * n
        if pinned or collapsed:
            unaligned.append(line)
            continue
        timed.append({"text": line, "words": [
            {"text": t, "start": round(s, 3), "end": round(max(e, s), 3)} for t, s, e in chunk]})
    return timed, unaligned


def main() -> int:
    p = argparse.ArgumentParser(description="Tunora lyric forced alignment worker")
    p.add_argument("--audio", type=Path, required=True)
    p.add_argument("--lyrics-file", type=Path, required=True)
    p.add_argument("--ffmpeg-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="base")
    p.add_argument("--language", default="en")
    a = p.parse_args()

    # Whisper decodes audio by running `ffmpeg` from PATH: pin the approved build and prove it.
    os.environ["PATH"] = str(a.ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
    found = shutil.which("ffmpeg")
    if not found or Path(found).resolve().parent != a.ffmpeg_dir.resolve():
        print("ffmpeg does not resolve to the approved build", file=sys.stderr)
        return 6

    lines = lyric_lines(a.lyrics_file.read_text(encoding="utf-8"))
    if not lines:
        print("no lyric lines to align", file=sys.stderr)
        return 4
    try:
        import stable_whisper  # optional extra: `uv sync --extra music-video`
    except ImportError:
        print("stable-ts is not installed", file=sys.stderr)
        return 3

    ffprobe = str(Path(found).with_name(Path(found).name.replace("ffmpeg", "ffprobe")))
    duration = probe_duration(ffprobe, a.audio)
    started = time.monotonic()
    model = stable_whisper.load_model(a.model, device="cpu",
                                      download_root=os.environ.get("TUNORA_ALIGNER_MODEL_DIR") or None)
    result = model.align(str(a.audio), "\n".join(lines), language=a.language)
    seconds = time.monotonic() - started

    words = [(w.word.strip(), float(w.start), float(w.end))
             for seg in result.segments for w in seg.words if w.word.strip()]
    expected = sum(len(l.split()) for l in lines)
    if len(words) != expected:
        print(f"aligner returned {len(words)} words for {expected} lyric words", file=sys.stderr)
        return 5
    timed, unaligned = group(words, lines, duration)
    a.out.write_text(json.dumps({
        "version": 1,
        "duration": round(duration, 3),
        "source": {"kind": "forced_alignment", "tool": f"stable-ts {stable_whisper.__version__}",
                   "model": a.model, "device": "cpu", "language": a.language,
                   "align_seconds": round(seconds, 1)},
        "lines": timed,
        "unaligned_lines": unaligned,
    }, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
