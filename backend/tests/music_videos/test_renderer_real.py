"""The production renderer with the REAL approved LGPL FFmpeg + libass (Phase 23).

No GPU, no network, no Whisper: TimedLyrics are given directly. Skipped only when no approved
FFmpeg is installed (see the `approved_tools` fixture).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from app.music_videos import timed_lyrics as tl
from app.music_videos.errors import InvalidMusicVideoRequestError, RenderError
from app.music_videos.renderer import FFmpegLibassRenderer, check_background
from tests.music_videos.conftest import image, make_media, tone, video
from tests.music_videos.test_timed_lyrics_and_ass import EVIL

LONG = "When the night is getting colder and I cannot see the way ahead of me I remember why I started"


def lyrics(duration: float, texts: list[str]) -> tl.TimedLyrics:
    lines, t = [], 0.5
    for text in texts:
        words = text.split()
        step = min(0.25, (duration - t - 0.5) / max(len(words), 1) / max(len(texts), 1))
        lines.append({"text": text, "words": [{"text": w, "start": round(t + i * step, 3),
                                               "end": round(t + (i + 1) * step, 3)} for i, w in enumerate(words)]})
        t += step * len(words) + 0.2
    return tl.parse({"version": 1, "duration": duration, "lines": lines})


def probe(tools, path: Path) -> dict:
    out = subprocess.run([str(tools.ffprobe), "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,profile,width,height,avg_frame_rate,pix_fmt,sample_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def black_segments(tools, path: Path) -> int:
    err = subprocess.run([str(tools.ffmpeg), "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.1:pix_th=0.10",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return len(re.findall("black_start", err))


def decode_errors(tools, path: Path) -> str:
    return subprocess.run([str(tools.ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "-"],
                          capture_output=True, text=True).stderr.strip()


@pytest.fixture
def renderer(approved_tools):
    return FFmpegLibassRenderer(approved_tools)


def test_image_background_renders_a_valid_1080x1920_h264_aac_mp4(approved_tools, renderer, tmp_path):
    audio = tone(approved_tools, tmp_path / "a.flac", 6)
    bg = image(approved_tools, tmp_path / "bg.png")
    result = renderer.render(audio, lyrics(6, ["Rise", "I will reach the open sky", LONG]), bg, "minimal_white",
                             "9:16", tmp_path / "out.mp4", title="Test")
    info = probe(approved_tools, result.output)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (v["codec_name"], v["width"], v["height"], v["avg_frame_rate"], v["pix_fmt"]) == ("h264", 1080, 1920, "30/1", "yuv420p")
    assert (a["codec_name"], a["sample_rate"]) == ("aac", "48000")
    assert abs(float(info["format"]["duration"]) - 6) < 0.1
    assert decode_errors(approved_tools, result.output) == "" and black_segments(approved_tools, result.output) == 0
    assert result.lines_rendered == 3


def test_a_short_background_video_loops_to_cover_the_whole_song(approved_tools, renderer, tmp_path):
    audio = tone(approved_tools, tmp_path / "a.wav", 7)
    bg = video(approved_tools, tmp_path / "bg.mp4", seconds=2)  # 16:9 and much shorter than the song
    result = renderer.render(audio, lyrics(7, ["I wake up to a brand new day", LONG, LONG]), bg, "bold", "9:16",
                             tmp_path / "out.mp4")
    info = probe(approved_tools, result.output)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert abs(float(info["format"]["duration"]) - 7) < 0.1
    assert black_segments(approved_tools, result.output) == 0
    assert decode_errors(approved_tools, result.output) == ""


def test_malicious_lyric_text_renders_as_plain_text(approved_tools, renderer, tmp_path):
    audio = tone(approved_tools, tmp_path / "a.flac", 6)
    bg = image(approved_tools, tmp_path / "bg.jpg")
    result = renderer.render(audio, lyrics(6, EVIL), bg, "dreamy", "9:16", tmp_path / "out.mp4", title="{\\p1}x")
    assert result.output.is_file() and decode_errors(approved_tools, result.output) == ""


def test_invalid_inputs_are_rejected_before_ffmpeg_runs(approved_tools, renderer, tmp_path):
    audio = tone(approved_tools, tmp_path / "a.flac", 6)
    bg = image(approved_tools, tmp_path / "bg.png")
    good = lyrics(6, ["hello"])
    fake = tmp_path / "fake.mp3"
    fake.write_text("not audio")
    cases = [
        (Path("..") / ".." / "Windows" / "nope.flac", bg, tmp_path / "o.mp4", RenderError),
        (Path("C:/Windows/win.ini"), bg, tmp_path / "o.mp4", RenderError),
        (audio, Path("C:/Windows/notepad.exe"), tmp_path / "o.mp4", RenderError),
        (Path("concat:a.flac|b.flac"), bg, tmp_path / "o.mp4", RenderError),
        (fake, bg, tmp_path / "o.mp4", InvalidMusicVideoRequestError),
        (audio, bg, tmp_path / "o.bat", RenderError),
        (audio, bg, bg, RenderError),
    ]
    for audio_path, background, output, error in cases:
        with pytest.raises(error):
            renderer.render(audio_path, good, background, "minimal_white", "9:16", output)
    with pytest.raises(RenderError, match="different audio"):
        renderer.render(audio, lyrics(60, ["hello"]), bg, "minimal_white", "9:16", tmp_path / "o.mp4")
    with pytest.raises(RenderError, match="aspect"):
        renderer.render(audio, good, bg, "minimal_white", "16:9", tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_background_checks_reject_non_video_files_and_decompression_bombs(approved_tools, tmp_path):
    audio_as_mp4 = make_media(approved_tools, tmp_path / "audio-only.mp4", "-f", "lavfi", "-i", "sine=d=1")
    with pytest.raises(InvalidMusicVideoRequestError, match="no video stream"):
        check_background(approved_tools, audio_as_mp4)
    bomb = image(approved_tools, tmp_path / "huge.png", size="8000x6000")
    with pytest.raises(InvalidMusicVideoRequestError, match="resolution"):
        check_background(approved_tools, bomb)
    assert check_background(approved_tools, image(approved_tools, tmp_path / "ok.jpg")).width == 1920


def test_every_ffmpeg_input_is_pinned_to_the_local_file_protocol(approved_tools, tmp_path):
    for background in (Path("C:/x/bg.mp4"), Path("C:/x/bg.png")):
        args = FFmpegLibassRenderer(approved_tools)._command(Path("C:/x/a.flac"), background,
                                                             background.suffix == ".mp4", 1080, 1920, 10.0,
                                                             "minimal_white", tmp_path / "o.mp4")
        inputs = [i for i, a in enumerate(args) if a == "-i"]
        assert len(inputs) == 2
        for i in inputs:
            assert args[i + 1].startswith("file:")
            assert args[i - 2:i] == ["-protocol_whitelist", "file"]
        graph = args[args.index("-filter_complex") + 1]
        assert "C:" not in graph and "x/" not in graph  # no caller path inside the filtergraph


def test_no_shell_is_ever_used_by_the_music_video_code():
    for source in (Path(__file__).resolve().parents[2] / "app" / "music_videos").glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "shell=True" not in text and "os.system" not in text and "os.popen" not in text, source.name
