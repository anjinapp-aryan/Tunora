"""MusicVideoRenderer: audio + TimedLyrics + background + style -> 9:16 MP4 (Phase 23).

Adapted from the validated Phase 22B prototype (`render.py`); the filter graph, encoder settings
and safety rules are unchanged. Changes: the FFmpeg binaries come from `ffmpeg.approved_ffmpeg()`
(policy-checked), 9:16 with OpenH264 is the only production path, and FFmpeg has a timeout.

Composition only -- no AI model, no network, no API key:
    background (image: slow pan, or video: looped) -> scale/crop to 1080x1920
    -> colour-preserving darkening -> lyrics via libass -> H.264 (OpenH264) + AAC.

Safety rules:
  * FFmpeg runs as an argument list (never a shell). Lyrics go into a file (the ASS script),
    never onto the command line (no Windows ~8 KB limit, no injection).
  * No caller-supplied path appears in the filtergraph: the ASS script and fonts sit in a private
    temporary directory and are referenced by fixed relative names.
  * Inputs must be existing regular files with an allowed extension, are opened through FFmpeg's
    `file:` protocol only (`-protocol_whitelist file`), and are probed before use.
  * The output is written inside the temporary directory and moved into place only on success.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.music_videos import ass_builder
from app.music_videos.errors import InvalidMusicVideoRequestError, RenderError
from app.music_videos.ffmpeg import FFmpegTools
from app.music_videos.timed_lyrics import TimedLyrics

ASPECTS = {"9:16": (1080, 1920)}
FPS = 30
FONTS_DIR = Path(__file__).resolve().parent / "fonts"
AUDIO_EXT = {".flac", ".mp3", ".wav"}
AUDIO_CODECS = {"flac", "mp3", "pcm_s16le", "pcm_s24le", "pcm_f32le"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
IMAGE_CODECS = {"mjpeg", "png"}
VIDEO_EXT = {".mp4", ".mov", ".webm"}
VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "av1", "mpeg4"}
MAX_BACKGROUND_PIXELS = 7680 * 4320  # refuse decompression bombs
ENCODER_ARGS = ["-c:v", "libopenh264", "-profile:v", "high", "-b:v", "8M", "-maxrate", "10M",
                "-bufsize", "16M"]


@dataclass(frozen=True)
class RenderResult:
    output: Path
    seconds: float
    size_bytes: int
    lines_rendered: int


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    codecs: frozenset[str]
    width: int = 0
    height: int = 0


class MusicVideoRenderer(ABC):
    @abstractmethod
    def render(self, audio_path: Path, timed_lyrics: TimedLyrics, background_path: Path, style: str,
               aspect_ratio: str, output_path: Path, title: Optional[str] = None) -> RenderResult: ...


def probe(tools: FFmpegTools, path: Path, kind: str) -> MediaInfo:
    """ffprobe one local file. `kind` is "audio" or "video" (image backgrounds are video streams)."""

    result = subprocess.run(
        [str(tools.ffprobe), "-v", "error", "-protocol_whitelist", "file",
         "-show_entries", "stream=codec_type,codec_name,width,height:format=duration", "-of", "json",
         f"file:{path}"], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise InvalidMusicVideoRequestError(f"The {kind} file is not a readable media file.")
    data = json.loads(result.stdout or "{}")
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == kind]
    if not streams:
        raise InvalidMusicVideoRequestError(f"The {kind} file has no {kind} stream.")
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    first = streams[0]
    return MediaInfo(duration, frozenset(s.get("codec_name", "") for s in streams),
                     int(first.get("width") or 0), int(first.get("height") or 0))


def check_background(tools: FFmpegTools, path: Path) -> MediaInfo:
    """Validate a background file by extension and by what ffprobe finds inside it."""

    is_video = path.suffix.lower() in VIDEO_EXT
    if path.suffix.lower() not in (VIDEO_EXT | IMAGE_EXT):
        raise InvalidMusicVideoRequestError("Background must be a JPG, PNG, MP4, MOV or WebM file.")
    info = probe(tools, path, "video")
    if not info.codecs & (VIDEO_CODECS if is_video else IMAGE_CODECS):
        raise InvalidMusicVideoRequestError("The background uses an unsupported format.")
    if info.width <= 0 or info.height <= 0 or info.width * info.height > MAX_BACKGROUND_PIXELS:
        raise InvalidMusicVideoRequestError("The background resolution is not supported.")
    if is_video and info.duration <= 0:
        raise InvalidMusicVideoRequestError("The background video has no duration.")
    # ffprobe only reads headers. A file with a valid header but undecodable pixel data (e.g. a
    # PNG with a corrupt IDAT) would pass the checks above and then make the looped render retry
    # the decode forever (Phase 24 finding). Decode one real frame, failing on the first error.
    try:
        decoded = subprocess.run(
            [str(tools.ffmpeg), "-hide_banner", "-nostdin", "-v", "error", "-xerror",
             "-protocol_whitelist", "file", "-i", f"file:{path}", "-map", "0:v:0", "-frames:v", "1",
             "-f", "null", "-"], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise InvalidMusicVideoRequestError("The background file could not be decoded.") from None
    if decoded.returncode != 0:
        raise InvalidMusicVideoRequestError("The background file could not be decoded.")
    return info


class FFmpegLibassRenderer(MusicVideoRenderer):
    """The production renderer: LGPL FFmpeg + libass, CPU only."""

    def __init__(self, tools: FFmpegTools, fonts_dir: Path = FONTS_DIR) -> None:
        self._tools = tools
        self._fonts_dir = fonts_dir

    @staticmethod
    def _input(path: Path, allowed: set[str], what: str) -> Path:
        path = Path(path)
        if path.suffix.lower() not in allowed:
            raise RenderError(f"{what}: unsupported file type")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise RenderError(f"{what}: file not found") from None
        if not resolved.is_file():
            raise RenderError(f"{what}: not a regular file")
        return resolved

    def render(self, audio_path: Path, timed_lyrics: TimedLyrics, background_path: Path, style: str,
               aspect_ratio: str, output_path: Path, title: Optional[str] = None) -> RenderResult:
        if aspect_ratio not in ASPECTS:
            raise RenderError("unsupported aspect ratio")
        if style not in ass_builder.STYLES:
            raise RenderError("unknown style")
        width, height = ASPECTS[aspect_ratio]

        audio = self._input(audio_path, AUDIO_EXT, "audio")
        a = probe(self._tools, audio, "audio")
        if not a.codecs & AUDIO_CODECS or a.duration <= 0:
            raise RenderError("audio: unsupported codec")
        if abs(a.duration - timed_lyrics.duration) > 1.0:
            raise RenderError("TimedLyrics were made for a different audio file (duration mismatch)")
        is_video = Path(background_path).suffix.lower() in VIDEO_EXT
        background = self._input(background_path, VIDEO_EXT | IMAGE_EXT, "background")
        check_background(self._tools, background)

        output = Path(output_path)
        if output.suffix.lower() != ".mp4" or not output.parent.is_dir():
            raise RenderError("output must be an .mp4 in an existing directory")
        output = output.resolve()
        if output in (audio, background):
            raise RenderError("output would overwrite an input")

        with tempfile.TemporaryDirectory(prefix="tunora-mv-") as work:
            work_dir = Path(work)
            (work_dir / "lyrics.ass").write_text(
                ass_builder.build(timed_lyrics, style, width, height, title), encoding="utf-8")
            shutil.copytree(self._fonts_dir, work_dir / "fonts")
            args = self._command(audio, background, is_video, width, height, a.duration, style,
                                 work_dir / "out.mp4")
            started = time.monotonic()
            try:
                proc = subprocess.run(args, cwd=work_dir, capture_output=True, text=True,
                                      timeout=max(300.0, a.duration * 10))
            except subprocess.TimeoutExpired as exc:
                raise RenderError("ffmpeg timed out") from exc
            seconds = time.monotonic() - started
            if proc.returncode != 0 or not (work_dir / "out.mp4").is_file():
                raise RenderError(f"ffmpeg failed (exit {proc.returncode}): {proc.stderr[-800:]}")
            shutil.move(str(work_dir / "out.mp4"), output)
        return RenderResult(output, round(seconds, 1), output.stat().st_size, len(timed_lyrics.lines))

    def _command(self, audio: Path, bg: Path, is_video: bool, w: int, h: int, duration: float,
                 style: str, out: Path) -> list[str]:
        dim = ass_builder.STYLES[style].dim
        if is_video:
            bg_in = ["-stream_loop", "-1", "-protocol_whitelist", "file", "-i", f"file:{bg}"]
            fit = f"fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        else:  # still image: cover at 112 % and pan slowly across the spare margin
            bw, bh = int(w * 1.12) // 2 * 2, int(h * 1.12) // 2 * 2
            bg_in = ["-loop", "1", "-framerate", str(FPS), "-protocol_whitelist", "file",
                     "-i", f"file:{bg}"]
            fit = (f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                   f"crop={w}:{h}:x='(iw-ow)/2*(1+sin(2*PI*t/40))':y='(ih-oh)/2*(1+cos(2*PI*t/50))'")
        # Darken for readability without greying out the colours. LGPL filters only: FFmpeg's
        # `eq` filter is GPL-only and absent from the approved build.
        top = 1 - dim * 0.4
        graph = (f"[0:v]{fit},setsar=1,colorlevels=romax={top:.3f}:gomax={top:.3f}:bomax={top:.3f},"
                 f"hue=s=1.15,ass=lyrics.ass:fontsdir=fonts,scale=out_range=tv,format=yuv420p[v]")
        return [str(self._tools.ffmpeg), "-hide_banner", "-nostdin", "-y", *bg_in,
                "-protocol_whitelist", "file", "-i", f"file:{audio}",
                "-filter_complex", graph, "-map", "[v]", "-map", "1:a:0",
                *ENCODER_ARGS, "-color_range", "tv", "-g", str(FPS * 2), "-r", str(FPS),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out)]
