"""The Lyrics -> TimedLyrics boundary (Phase 23).

    Raw lyrics (the Version's stored text, never modified)
        -> LyricsAligner (forced alignment today; manual timing later)
        -> TimedLyrics (validated; matched lines + unaligned_lines)
        -> MusicVideoRenderer

`LocalForcedAligner` runs `align_worker` in a separate process: no API key, no network (the
Whisper `base` weights are read from the local cache; the first-ever run downloads them once), CPU
only, and the same approved LGPL FFmpeg the renderer uses.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from app.music_videos import timed_lyrics
from app.music_videos.errors import AlignmentError
from app.music_videos.ffmpeg import FFmpegTools
from app.music_videos.timed_lyrics import TimedLyrics, TimedLyricsError

_EXIT_REASONS = {
    3: "the local alignment engine is not installed (uv sync --extra music-video)",
    4: "there are no lyric lines to align",
    5: "the aligner could not match the lyric words one-to-one",
    6: "the approved FFmpeg could not be pinned for alignment",
}


class LyricsAligner(ABC):
    @abstractmethod
    def align(self, audio_path: Path, lyrics: str, language: str) -> TimedLyrics:
        """Time `lyrics` against the audio. Raises AlignmentError."""


class LocalForcedAligner(LyricsAligner):
    def __init__(self, tools: FFmpegTools, model: str = "base", timeout_seconds: float = 900.0) -> None:
        self._tools = tools
        self._model = model
        self._timeout = timeout_seconds

    def align(self, audio_path: Path, lyrics: str, language: str) -> TimedLyrics:
        with tempfile.TemporaryDirectory(prefix="tunora-align-") as work:
            lyrics_file = Path(work) / "lyrics.txt"
            out_file = Path(work) / "timed.json"
            lyrics_file.write_text(lyrics, encoding="utf-8")
            args = [sys.executable, "-m", "app.music_videos.align_worker",
                    "--audio", str(audio_path), "--lyrics-file", str(lyrics_file),
                    "--ffmpeg-dir", str(self._tools.bin_dir), "--out", str(out_file),
                    "--model", self._model, "--language", language or "en"]
            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=self._timeout,
                                      cwd=Path(__file__).resolve().parents[2])
            except subprocess.TimeoutExpired as exc:
                raise AlignmentError("lyric alignment timed out") from exc
            if proc.returncode != 0:
                reason = _EXIT_REASONS.get(proc.returncode, f"exit {proc.returncode}: {proc.stderr[-600:]}")
                raise AlignmentError(f"lyric alignment failed: {reason}")
            try:
                return timed_lyrics.load(out_file)
            except TimedLyricsError as exc:
                raise AlignmentError(f"alignment produced invalid TimedLyrics: {exc}") from exc
