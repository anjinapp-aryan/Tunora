"""Phase 25: visual polish as composable style data (docs/PHASE-25-MUSIC-VIDEO-VISUAL-POLISH.md).

The Phase 23 styles must stay byte-identical (golden files generated from the committed Phase 23/24
builder); the new "cinematic" and "karaoke" styles are pure configuration of shared primitives.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_music_videos import router as music_videos_router
from app.music_videos import ass_builder, models
from app.music_videos import timed_lyrics as tl
from app.music_videos.renderer import FFmpegLibassRenderer
from tests.music_videos.conftest import FAKE_TOOLS, JPEG, tone, video

GOLDEN = Path(__file__).parent / "golden"
LYRICS = tl.parse(json.loads((GOLDEN / "timed_lyrics.json").read_text(encoding="utf-8")))
PHASE23 = ("minimal_white", "dreamy", "bold")


def _events(script: str) -> list[str]:
    return [l for l in script.splitlines() if l.startswith("Dialogue:")]


def test_domain_api_and_builder_offer_exactly_the_same_styles():
    assert set(models.STYLES) == set(ass_builder.STYLES)
    assert set(PHASE23) < set(models.STYLES) and {"cinematic", "karaoke"} < set(models.STYLES)


@pytest.mark.parametrize("name", PHASE23)
def test_phase23_styles_are_byte_identical_to_before(name):
    expected = (GOLDEN / f"phase23_{name}.ass").read_text(encoding="utf-8")
    assert ass_builder.build(LYRICS, name, 1080, 1920, "I Will Rise") == expected
    assert not ass_builder.uses_primitives(ass_builder.STYLES[name])


def test_cinematic_title_is_visible_on_the_first_frame_and_there_is_an_end_card():
    events = _events(ass_builder.build(LYRICS, "cinematic", 1080, 1920, "I Will Rise"))
    titles = [e for e in events if ",Title," in e]
    assert len(titles) == 2
    assert titles[0].startswith("Dialogue: 1,0:00:00.00,") and "\\fad(0," in titles[0]  # no fade-in: thumbnail
    assert titles[0].endswith("I WILL RISE")
    assert titles[1].split(",")[2] == "0:00:30.00"  # end card runs to the very end


def test_cinematic_pops_one_word_at_a_time_without_changing_line_width():
    events = [e for e in _events(ass_builder.build(LYRICS, "cinematic", 1080, 1920)) if ",Active," in e]
    first_line = [e for e in events if "WAKE" in e.split(",,", 1)[1].split("\\N")[0]]
    assert len(first_line) == 1 + len(LYRICS.lines[0].words)  # lead-in + one event per sung word
    popped = [re.findall(r"\\1c&H008AD9FF&?\\fscy118", e) for e in first_line[1:]]
    assert all(len(p) == 1 for p in popped)  # exactly one active word per event
    assert all("\\fscx" not in e.split(",,", 1)[1] for e in events)  # never a horizontal scale
    assert "\\move(" in first_line[0] and all("\\move(" not in e for e in first_line[1:])  # rise only on entry


def test_karaoke_sweeps_with_the_karaoke_fill_and_uses_capitals():
    active = [e for e in _events(ass_builder.build(LYRICS, "karaoke", 1080, 1920)) if ",Active," in e]
    assert active and all("\\kf" in e for e in active)
    assert "I WAKE UP TO A BRAND NEW DAY" in re.sub(r"\{[^}]*\}", "", active[0])


@pytest.mark.parametrize("name", ["cinematic", "karaoke"])
def test_new_styles_keep_lyric_text_inert(name):
    evil = tl.parse({"version": 1, "duration": 10.0, "lines": [
        {"text": t, "words": [{"text": t, "start": 1.0 + i, "end": 1.5 + i}]}
        for i, t in enumerate(["{\\p1}m 0 0 l 99 99", "{\\fnImpact}x", "a\\Nb"])]})
    for e in _events(ass_builder.build(evil, name, 1080, 1920, title="{\\p1}t")):
        user = re.sub(r"\{\\(?:an|pos|move|blur|fsp|fad|t|1c|1a|fscy|k|kf|r)[^}]*\}", "", e.split(",,", 1)[1])
        assert "{" not in user and "}" not in user and "\\P1" not in user.upper().replace("\\N", "")


def test_background_treatment_is_style_data_and_the_vignette_stays_cheap():
    r = FFmpegLibassRenderer(FAKE_TOOLS)
    old = r._command(Path("a.flac"), Path("b.mp4"), True, 1080, 1920, 10.0, "minimal_white", Path("o.mp4"))
    new = r._command(Path("a.flac"), Path("b.mp4"), True, 1080, 1920, 10.0, "cinematic", Path("o.mp4"))
    g_old, g_new = old[old.index("-filter_complex") + 1], new[new.index("-filter_complex") + 1]
    assert "vignette" not in g_old and "1166:2072" not in g_old  # Phase 23 graph untouched
    assert "scale=1166:2072" in g_new and "sin(2*PI*t/40)" in g_new  # drift on video backgrounds
    # Measured: vignette on YUV, undithered, before colorlevels ~ +0.6 s / 60 s; after it ~ +11 s.
    assert g_new.index("vignette=angle=PI/5.5:dither=0") < g_new.index("colorlevels")


async def test_the_api_accepts_the_new_styles_and_still_rejects_unknown_ones(mvh):
    app = FastAPI()
    app.include_router(music_videos_router)
    app.state.job_service, app.state.music_video_service = mvh.service, mvh.mv
    client = TestClient(app)
    version = await mvh.vocal_version()
    post = lambda style: client.post(f"/api/songs/{version.song_id}/music-videos",  # noqa: E731
                                     params={"source_version_id": version.id, "style": style},
                                     content=JPEG, headers={"Content-Type": "image/jpeg"})
    assert post("cinematic").json()["style"] == "cinematic"
    assert post("karaoke").json()["style"] == "karaoke"
    assert post("neon").status_code == 422


def test_a_real_cinematic_render_with_a_looping_video_background(approved_tools, tmp_path):
    audio = tone(approved_tools, tmp_path / "a.flac", 8)
    bg = video(approved_tools, tmp_path / "bg.mp4", seconds=2)
    lines = [{"text": t, "words": [{"text": w, "start": round(1 + i * 2 + j * 0.3, 2), "end": round(1.25 + i * 2 + j * 0.3, 2)}
                                   for j, w in enumerate(t.split())]} for i, t in enumerate(["I will rise", "I will reach the open sky"])]
    lyrics = tl.parse({"version": 1, "duration": 8.0, "lines": lines})
    result = FFmpegLibassRenderer(approved_tools).render(audio, lyrics, bg, "cinematic", "9:16", tmp_path / "o.mp4", title="Test")
    info = json.loads(subprocess.run([str(approved_tools.ffprobe), "-v", "error", "-show_entries",
                                      "stream=codec_name,width,height:format=duration", "-of", "json", str(result.output)],
                                     capture_output=True, text=True, check=True).stdout)
    v = next(s for s in info["streams"] if s["codec_name"] == "h264")
    assert (v["width"], v["height"]) == (1080, 1920) and abs(float(info["format"]["duration"]) - 8) < 0.1
    err = subprocess.run([str(approved_tools.ffmpeg), "-hide_banner", "-i", str(result.output), "-vf",
                          "blackdetect=d=0.1:pix_th=0.10", "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    assert "black_start" not in err
