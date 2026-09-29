"""Phase 27: multi-format output -- one canonical VideoOutputProfile from API to FFmpeg.

The client sends only an allowlisted profile id. Width, height, aspect ratio, layout canvas and
encoder settings all come from app/music_videos/profiles.py; the default stays 9:16 1080x1920.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_music_videos import router as music_videos_router
from app.jobs import migrations
from app.music_videos import ass_builder, profiles
from app.music_videos import timed_lyrics as tl
from app.music_videos.errors import InvalidMusicVideoRequestError, RenderError
from app.music_videos.models import MusicVideoStatus
from app.music_videos.renderer import FFmpegLibassRenderer
from app.songs.errors import SourceVersionNotFoundError
from tests.music_videos.conftest import FAKE_TOOLS, JPEG, image, tone, video
from tests.music_videos.test_renderer_real import LONG, black_segments, decode_errors, lyrics, probe

EXPECTED = {
    "vertical_hd": ("portrait", "9:16", 1080, 1920, "HD"),
    "vertical_4k": ("portrait", "9:16", 2160, 3840, "4K"),
    "landscape_hd": ("landscape", "16:9", 1920, 1080, "HD"),
    "landscape_4k": ("landscape", "16:9", 3840, 2160, "4K"),
    "square_hd": ("square", "1:1", 1080, 1080, "HD"),
}


# -- the canonical table ---------------------------------------------------------------------------


def test_exactly_the_five_profiles_with_exact_dimensions():
    assert set(profiles.PROFILES) == set(EXPECTED)  # no square 4K, no custom sizes
    for pid, (orientation, ratio, w, h, res) in EXPECTED.items():
        p = profiles.get_profile(pid)
        assert (p.id, p.orientation, p.aspect_ratio, p.width, p.height, p.resolution_class) == (pid, orientation, ratio, w, h, res)
        assert p.width % 2 == 0 and p.height % 2 == 0  # yuv420p needs even sizes
    assert profiles.DEFAULT_PROFILE_ID == "vertical_hd"


def test_4k_profiles_reuse_their_hd_layout_canvas_and_get_a_higher_bitrate():
    for hd, uhd in (("vertical_hd", "vertical_4k"), ("landscape_hd", "landscape_4k")):
        a, b = profiles.PROFILES[hd], profiles.PROFILES[uhd]
        assert (a.canvas_width, a.canvas_height) == (b.canvas_width, b.canvas_height) == (a.width, a.height)
        assert (b.width, b.height) == (a.width * 2, a.height * 2)
        assert int(b.video_bitrate[:-1]) > int(a.video_bitrate[:-1])
    assert profiles.PROFILES["vertical_hd"].video_bitrate == "8M"  # the Phase 23 encoder settings


@pytest.mark.parametrize("bad", ["", "VERTICAL_HD", "square_4k", "1080x1920", "vertical_hd ", "../x", None, 7])
def test_unknown_or_malformed_profiles_are_rejected(bad):
    with pytest.raises(InvalidMusicVideoRequestError):
        profiles.get_profile(bad)


def test_the_renderer_accepts_profile_ids_and_the_legacy_9_16_value_only():
    assert profiles.renderer_profile("9:16") is profiles.PROFILES["vertical_hd"]
    assert profiles.renderer_profile("16:9") is None and profiles.renderer_profile("3840x2160") is None


# -- service ---------------------------------------------------------------------------------------


async def _create(mvh, version, **kw):
    async def chunks():
        yield JPEG
    return await mvh.mv.create(version.song_id, source_version_id=kw.pop("source_version_id", version.id),
                               style=kw.pop("style", "cinematic"), media_type="image/jpeg", chunks=chunks(), **kw)


@pytest.mark.parametrize("pid", list(EXPECTED))
async def test_the_chosen_profile_is_stored_and_reaches_the_renderer(mvh, pid):
    version = await mvh.vocal_version()
    video = await _create(mvh, version, output_profile=pid)
    assert (video.output_profile, video.aspect_ratio) == (pid, EXPECTED[pid][1])
    assert mvh.mv.get(video.id).output_profile == pid  # persisted
    assert mvh.mv.generate(video.id).status == MusicVideoStatus.COMPLETED
    assert mvh.renderer.calls[-1]["profile"] == pid  # never silently replaced


async def test_no_profile_means_vertical_hd_and_a_matching_legacy_aspect_ratio_is_accepted(mvh):
    version = await mvh.vocal_version()
    video = await _create(mvh, version)
    assert (video.output_profile, video.aspect_ratio) == ("vertical_hd", "9:16")
    mvh.mv.generate(video.id)
    legacy = await _create(mvh, version, aspect_ratio="9:16")  # a Phase 23-26 request
    assert legacy.output_profile == "vertical_hd"


async def test_a_conflicting_aspect_ratio_or_unknown_profile_stores_nothing(mvh):
    version = await mvh.vocal_version()
    with pytest.raises(InvalidMusicVideoRequestError, match="16:9"):
        await _create(mvh, version, output_profile="landscape_hd", aspect_ratio="9:16")
    with pytest.raises(InvalidMusicVideoRequestError):
        await _create(mvh, version, output_profile="ultra_8k")
    assert mvh.mv_repository.list_for_song(version.song_id) == []
    assert not any(mvh.mv_storage.root.rglob("*"))


async def test_cross_song_versions_are_still_rejected_for_every_profile(mvh):
    mine, other = await mvh.vocal_version(), await mvh.vocal_version()
    with pytest.raises(SourceVersionNotFoundError):
        await _create(mvh, mine, source_version_id=other.id, output_profile="landscape_4k")


async def test_several_formats_of_one_version_are_separate_videos_and_retry_keeps_the_format(mvh):
    version = await mvh.vocal_version()
    made = []
    for pid, style in (("vertical_hd", "cinematic"), ("landscape_hd", "cinematic"), ("vertical_4k", "karaoke")):
        v = await _create(mvh, version, output_profile=pid, style=style)
        mvh.mv.generate(v.id)
        made.append(v.id)
    listed = {v.id: (v.output_profile, v.style, v.status) for v in mvh.mv.list_for_song(version.song_id)}
    assert listed == {made[0]: ("vertical_hd", "cinematic", MusicVideoStatus.COMPLETED),
                      made[1]: ("landscape_hd", "cinematic", MusicVideoStatus.COMPLETED),
                      made[2]: ("vertical_4k", "karaoke", MusicVideoStatus.COMPLETED)}

    failing = await _create(mvh, version, output_profile="square_hd")
    mvh.renderer.error = RenderError("boom")
    assert mvh.mv.generate(failing.id).status == MusicVideoStatus.FAILED
    mvh.renderer.error = None
    retried = mvh.mv.retry(failing.id)
    assert retried.output_profile == "square_hd"
    assert mvh.mv.generate(failing.id).status == MusicVideoStatus.COMPLETED
    assert mvh.renderer.calls[-1]["profile"] == "square_hd"


# -- persistence -----------------------------------------------------------------------------------


def test_v6_databases_upgrade_to_v7_and_old_videos_become_vertical_hd(tmp_path):
    db = tmp_path / "v6.db"
    conn = sqlite3.connect(db)
    for target, step in ((1, migrations._to_v1), (2, migrations._to_v2), (3, migrations._to_v3), (4, migrations._to_v4),
                         (5, migrations._to_v5), (6, migrations._to_v6)):
        migrations._run_step(conn, target, step)
    conn.execute("INSERT INTO songs (id, title, created_at, updated_at) VALUES ('song-a', 'A', 't', 't')")
    conn.execute("INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, "
                 "provider, created_at) VALUES ('ver-a', 'song-a', 1, 'p', 'la', 'en', 0, 'ace-step', 't')")
    conn.execute("INSERT INTO music_videos (id, song_id, source_version_id, status, style, aspect_ratio, background_key, "
                 "background_media_type, created_at, updated_at) VALUES ('mv-old', 'song-a', 'ver-a', 'COMPLETED', "
                 "'bold', '9:16', 'mv-old/background.jpg', 'image/jpeg', 't', 't')")
    conn.commit()
    migrations.migrate(conn)
    migrations.migrate(conn)  # idempotent
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    assert conn.execute("SELECT output_profile, aspect_ratio, style FROM music_videos").fetchone() == ("vertical_hd", "9:16", "bold")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE music_videos SET output_profile = 'landscape_4k' WHERE id = 'mv-old'")
    conn.close()


# -- API -------------------------------------------------------------------------------------------


@pytest.fixture
def client(mvh):
    app = FastAPI()
    app.include_router(music_videos_router)
    app.state.job_service, app.state.music_video_service = mvh.service, mvh.mv
    return TestClient(app)


def _post(client, version, **params):
    return client.post(f"/api/songs/{version.song_id}/music-videos", params={"source_version_id": version.id, **params},
                       content=JPEG, headers={"Content-Type": "image/jpeg"})


async def test_api_returns_the_backend_dimensions_for_each_profile(client, mvh):
    version = await mvh.vocal_version()
    for pid, (_, ratio, w, h, res) in EXPECTED.items():
        r = _post(client, version, output_profile=pid)
        assert r.status_code == 202, r.text
        body = r.json()
        assert (body["output_profile"], body["aspect_ratio"], body["width"], body["height"], body["resolution"]) == (pid, ratio, w, h, res)
        mvh.mv.generate(body["id"])


async def test_api_rejects_bad_profiles_and_never_takes_client_dimensions(client, mvh):
    version = await mvh.vocal_version()
    for bad in ("square_4k", "", "vertical_HD", "1920x1080"):
        assert _post(client, version, output_profile=bad).status_code == 422
    assert _post(client, version, output_profile="landscape_hd", aspect_ratio="1:1").status_code == 422
    assert _post(client, version, aspect_ratio="21:9").status_code == 422
    # Unknown parameters such as width/height are ignored: the default profile decides the size.
    body = _post(client, version, width=99999, height=-1).json()
    assert (body["output_profile"], body["width"], body["height"]) == ("vertical_hd", 1080, 1920)
    assert "99999" not in json.dumps(body)


# -- aspect-aware layout -----------------------------------------------------------------------------


def test_portrait_layout_is_the_original_and_other_canvases_scale_from_safe_zone_fractions():
    s = ass_builder.STYLES["cinematic"]
    assert ass_builder.layout_for(1080, 1920, s) == ass_builder.Layout(1080, 1920, "portrait", 1.0, 90, 153)
    assert ass_builder.layout_for(1920, 1080, s) == ass_builder.Layout(1920, 1080, "landscape", 0.9, 160, 86)
    assert ass_builder.layout_for(1080, 1080, s) == ass_builder.Layout(1080, 1080, "square", 0.85, 90, 86)


@pytest.mark.parametrize("pid", ["landscape_hd", "square_hd", "vertical_4k", "landscape_4k"])
@pytest.mark.parametrize("style", sorted(ass_builder.STYLES))
def test_every_style_lays_out_on_every_canvas_centred_inside_the_safe_area(pid, style):
    p = profiles.PROFILES[pid]
    doc = json.loads((Path(__file__).parent / "golden" / "timed_lyrics.json").read_text(encoding="utf-8"))
    script = ass_builder.build(tl.parse(doc), style, p.canvas_width, p.canvas_height, "I Will Rise")
    assert f"PlayResX: {p.canvas_width}" in script and f"PlayResY: {p.canvas_height}" in script
    lay = ass_builder.layout_for(p.canvas_width, p.canvas_height, ass_builder.STYLES[style])
    active = next(l for l in script.splitlines() if l.startswith("Style: Active,")).split(",")
    assert int(active[2]) == lay.size(ass_builder.STYLES[style].active_size)
    assert (int(active[19]), int(active[20]), int(active[21])) == (lay.margin_x, lay.margin_x, lay.margin_v)
    cx, cy = lay.center
    for line in script.splitlines():
        if "\\pos(" in line:
            assert f"\\pos({cx},{cy})" in line  # lyrics and title cards are centred on this canvas


def test_the_filter_graph_covers_the_frame_without_stretching_at_4k():
    p = profiles.PROFILES["landscape_4k"]
    r = FFmpegLibassRenderer(FAKE_TOOLS)
    for is_video, style in ((True, "minimal_white"), (True, "cinematic"), (False, "karaoke")):
        args = r._command(Path("a.flac"), Path("b.mp4"), is_video,
                          p.width, p.height, 10.0, style, Path("o.mp4"))
        graph = args[args.index("-filter_complex") + 1]
        assert "force_original_aspect_ratio=increase" in graph  # scale to COVER, keeping the shape
        assert "crop=3840:2160" in graph  # then crop the overflow to the exact frame


# -- real renders (skipped without the approved LGPL FFmpeg) -----------------------------------------


@pytest.mark.parametrize("pid,bg_kind", [("landscape_hd", "image"), ("square_hd", "video"), ("vertical_4k", "image"),
                                         ("landscape_4k", "video")])
def test_real_render_has_the_exact_profile_dimensions_and_no_black_bars(approved_tools, tmp_path, pid, bg_kind):
    p = profiles.PROFILES[pid]
    audio = tone(approved_tools, tmp_path / "a.flac", 3)
    # A background of the "wrong" shape on purpose: portrait art in landscape frames and vice versa.
    bg = image(approved_tools, tmp_path / "bg.png", "720x1280" if p.width >= p.height else "1280x720") \
        if bg_kind == "image" else video(approved_tools, tmp_path / "bg.mp4", seconds=1)
    result = FFmpegLibassRenderer(approved_tools).render(
        audio, lyrics(3, ["I will rise", LONG]), bg, "minimal_white", pid, tmp_path / "out.mp4", title="Test")
    info = probe(approved_tools, result.output)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (v["codec_name"], v["width"], v["height"], v["pix_fmt"]) == ("h264", p.width, p.height, "yuv420p")
    assert (a["codec_name"], a["sample_rate"]) == ("aac", "48000")
    assert abs(float(info["format"]["duration"]) - 3) < 0.1
    assert decode_errors(approved_tools, result.output) == "" and black_segments(approved_tools, result.output) == 0
    # No letterbox/pillarbox bars (the approved LGPL build has no GPL-only cropdetect): decode one
    # frame as 8-bit luma and check that every outer row and column has picture in it, not bar black.
    raw = subprocess.run([str(approved_tools.ffmpeg), "-v", "error", "-ss", "1.5", "-i", str(result.output), "-frames:v", "1",
                          "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    assert len(raw) == p.width * p.height
    rows = [raw[y * p.width:(y + 1) * p.width] for y in (0, 1, p.height - 2, p.height - 1)]
    cols = [bytes(raw[y * p.width + x] for y in range(p.height)) for x in (0, 1, p.width - 2, p.width - 1)]
    for edge in rows + cols:
        assert sum(edge) / len(edge) > 20, "black bar at the frame edge"


def test_the_renderer_rejects_unknown_profiles(approved_tools, tmp_path):
    audio = tone(approved_tools, tmp_path / "a.flac", 2)
    with pytest.raises(RenderError, match="output profile"):
        FFmpegLibassRenderer(approved_tools).render(audio, lyrics(2, ["x"]), image(approved_tools, tmp_path / "b.png"),
                                                    "cinematic", "3840x2160", tmp_path / "o.mp4")
