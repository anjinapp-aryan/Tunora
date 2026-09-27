"""Shared fixtures for the Music Video tests (Phase 23).

`MVHarness` = the existing Song/Version test Harness (real SQLite file, fake ACE-Step provider)
plus a Music Video repository on the SAME database file, real file storage under tmp_path, and
fake aligner/renderer/FFmpeg so service/API tests run without FFmpeg or Whisper. Tests that need
the real approved FFmpeg use the `approved_tools` fixture, which skips when none is installed.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.music_videos import ffmpeg as ffmpeg_policy
from app.music_videos.ffmpeg import FFmpegTools
from app.music_videos.renderer import RenderResult
from app.music_videos.repository import SqliteMusicVideoRepository
from app.music_videos.service import MusicVideoService
from app.music_videos.storage import MusicVideoStorage
from app.music_videos.timed_lyrics import TimedLyrics, parse
from tests.songs.test_service_versions import Harness

LYRICS = "[Verse]\nI wake up to a brand new day\nWith every fear I walk away\n\n[Chorus]\nI will rise"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64

FAKE_TOOLS = FFmpegTools(Path("ffmpeg"), Path("ffprobe"), "ffmpeg version test", "configuration: --enable-version3")


def timed_doc(lines: list[str], duration: float = 12.5, unaligned: list[str] | None = None) -> dict:
    out, t = [], 1.0
    for text in lines:
        words = []
        for w in text.split():
            words.append({"text": w, "start": round(t, 3), "end": round(t + 0.3, 3)})
            t += 0.35
        out.append({"text": text, "words": words})
    return {"version": 1, "duration": duration, "source": {"kind": "test"}, "lines": out,
            "unaligned_lines": unaligned or []}


@dataclass
class FakeAligner:
    doc: dict | None = None
    error: Exception | None = None
    calls: list = field(default_factory=list)

    def align(self, audio_path: Path, lyrics: str, language: str) -> TimedLyrics:
        self.calls.append((Path(audio_path), lyrics, language))
        if self.error:
            raise self.error
        return parse(self.doc or timed_doc(["I wake up to a brand new day"], unaligned=["I will rise"]))


@dataclass
class FakeRenderer:
    error: Exception | None = None
    calls: list = field(default_factory=list)

    def render(self, audio_path, timed_lyrics, background_path, style, aspect_ratio, output_path, title=None):
        self.calls.append(dict(audio=Path(audio_path), lines=len(timed_lyrics.lines), background=Path(background_path),
                               style=style, aspect=aspect_ratio, output=Path(output_path), title=title))
        if self.error:
            raise self.error
        Path(output_path).write_bytes(b"\x00\x00\x00\x18ftypisom fake mp4")
        return RenderResult(Path(output_path), 0.1, Path(output_path).stat().st_size, len(timed_lyrics.lines))


class MVHarness(Harness):
    def __init__(self, tmp_path: Path):
        super().__init__(tmp_path)
        self.mv_repository = SqliteMusicVideoRepository(self.db)
        self.mv_storage = MusicVideoStorage(tmp_path / "music-videos")
        self.aligner = FakeAligner()
        self.renderer = FakeRenderer()
        self.tools_error: Exception | None = None
        self.mv = MusicVideoService(
            repository=self.mv_repository, jobs=self.service, storage=self.mv_storage,
            tools_provider=self._tools, aligner_factory=lambda tools: self.aligner,
            renderer_factory=lambda tools: self.renderer, background_checker=lambda tools, path: None,
        )

    def _tools(self) -> FFmpegTools:
        if self.tools_error:
            raise self.tools_error
        return FAKE_TOOLS

    async def vocal_version(self, **spec):
        job = await self.generate_to_completion(lyrics=spec.pop("lyrics", LYRICS), **spec)
        return self.repository.get_version(job.version_id)

    async def create(self, version, body: bytes = JPEG, media_type: str = "image/jpeg", **kw):
        async def chunks():
            yield body
        return await self.mv.create(version.song_id, source_version_id=kw.pop("source_version_id", version.id),
                                    style=kw.pop("style", "minimal_white"), aspect_ratio=kw.pop("aspect_ratio", "9:16"),
                                    media_type=media_type, chunks=chunks())


@pytest.fixture
def mvh(tmp_path) -> MVHarness:
    return MVHarness(tmp_path)


@pytest.fixture(scope="session")
def approved_tools() -> FFmpegTools:
    try:
        return ffmpeg_policy.resolve()
    except ffmpeg_policy.FFmpegPolicyError as exc:
        pytest.skip(f"no approved LGPL FFmpeg installed: {exc}")


def make_media(tools: FFmpegTools, out: Path, *args: str) -> Path:
    subprocess.run([str(tools.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *args, str(out)],
                   check=True, timeout=120)
    return out


def tone(tools: FFmpegTools, out: Path, seconds: float) -> Path:
    return make_media(tools, out, "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
                      "-ac", "2", "-ar", "48000")


def image(tools: FFmpegTools, out: Path, size: str = "1920x1080") -> Path:
    return make_media(tools, out, "-f", "lavfi", "-i", f"gradients=s={size}:d=1", "-frames:v", "1", "-update", "1")


def video(tools: FFmpegTools, out: Path, seconds: float = 2.0) -> Path:
    return make_media(tools, out, "-f", "lavfi", "-i", f"testsrc2=s=1280x720:r=30:d={seconds}",
                      "-c:v", "libopenh264", "-pix_fmt", "yuv420p")

