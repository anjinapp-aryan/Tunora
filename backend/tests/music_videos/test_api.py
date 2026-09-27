"""Music Video HTTP API (Phase 23): contract, allowlist, errors, serving, deletion."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_music_videos import router as music_videos_router
from app.api.routes_songs import router as songs_router
from app.music_videos.errors import FFmpegPolicyError, RenderError
from tests.music_videos.conftest import JPEG, MP4, timed_doc


@pytest.fixture
def client(mvh):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.include_router(music_videos_router)
    app.state.job_service = mvh.service
    app.state.music_video_service = mvh.mv
    return TestClient(app)


def post(client, song_id, version_id, body=JPEG, content_type="image/jpeg", **params):
    return client.post(f"/api/songs/{song_id}/music-videos",
                       params={"source_version_id": version_id, **params},
                       content=body, headers={"Content-Type": content_type})


def assert_no_internals(payload):
    text = json.dumps(payload)
    for forbidden in ("background", "output_key", "timed_lyrics", "secret", ":\\\\", "data/", "tools", "Traceback"):
        assert forbidden not in text, forbidden


async def test_create_then_poll_then_play(client, mvh):
    version = await mvh.vocal_version()
    r = post(client, version.song_id, version.id, style="dreamy")
    assert r.status_code == 202
    created = r.json()
    assert created["status"] == "PENDING" and created["video_url"] is None
    assert (created["aspect_ratio"], created["width"], created["height"], created["style"]) == ("9:16", 1080, 1920, "dreamy")
    assert created["source_version_number"] == version.version_number

    done = client.get(f"/api/music-videos/{created['id']}").json()  # the background task already ran
    assert done["status"] == "COMPLETED" and done["video_url"] == f"/api/music-videos/{created['id']}/video"
    assert done["duration"] == 12.5 and done["size_bytes"] > 0 and done["error"] is None
    assert done["matched_line_count"] == 1 and done["unmatched_lines"] == ["I will rise"]
    assert_no_internals(done)

    listed = client.get(f"/api/songs/{version.song_id}/music-videos").json()["items"]
    assert [v["id"] for v in listed] == [created["id"]]

    video = client.get(done["video_url"])
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert video.headers["x-content-type-options"] == "nosniff" and "inline" in video.headers["content-disposition"]
    ranged = client.get(done["video_url"], headers={"Range": "bytes=0-3"})
    assert ranged.status_code == 206 and len(ranged.content) == 4


async def test_errors_map_to_safe_statuses(client, mvh):
    a = await mvh.vocal_version()
    b = await mvh.vocal_version()
    assert post(client, "song-missing", a.id).status_code == 404
    assert post(client, a.song_id, "ver-missing").status_code == 404
    assert post(client, a.song_id, b.id).status_code == 404  # another song's version
    assert post(client, a.song_id, "..%2F..%2Fetc").status_code in (404, 422)
    assert post(client, a.song_id, a.id, style="neon").status_code == 422
    assert post(client, a.song_id, a.id, aspect_ratio="16:9").status_code == 422
    assert post(client, a.song_id, a.id, body=b"<svg/>", content_type="image/svg+xml").status_code == 422
    assert post(client, a.song_id, a.id, body=b"MZ exe", content_type="image/png").status_code == 422
    too_big = client.post(f"/api/songs/{a.song_id}/music-videos", params={"source_version_id": a.id},
                          content=JPEG, headers={"Content-Type": "image/jpeg", "Content-Length": str(10**12)})
    assert too_big.status_code == 413
    assert client.get("/api/music-videos/mv-missing").status_code == 404
    assert client.get("/api/music-videos/..%2Fsecret/video").status_code == 404
    assert client.get("/api/songs/song-missing/music-videos").status_code == 404


async def test_a_duplicate_request_while_generating_is_409(client, mvh, monkeypatch):
    monkeypatch.setattr(mvh.mv, "generate", lambda video_id: None)  # keep the first one in progress
    version = await mvh.vocal_version()
    first = post(client, version.song_id, version.id)
    assert first.status_code == 202
    second = post(client, version.song_id, version.id, body=MP4, content_type="video/mp4")
    assert second.status_code == 409
    assert client.get(f"/api/music-videos/{first.json()['id']}/video").status_code == 404  # not finished yet


async def test_no_approved_ffmpeg_is_503_without_details(client, mvh):
    mvh.tools_error = FFmpegPolicyError(r"C:\ffmpeg --enable-gpl")
    version = await mvh.vocal_version()
    r = post(client, version.song_id, version.id)
    assert r.status_code == 503 and "gpl" not in r.text.lower() and "C:" not in r.text


async def test_a_failed_video_shows_only_a_safe_message(client, mvh):
    mvh.renderer.error = RenderError(r"ffmpeg failed: C:\secret\lyrics.ass Traceback")
    version = await mvh.vocal_version()
    created = post(client, version.song_id, version.id).json()
    failed = client.get(f"/api/music-videos/{created['id']}").json()
    assert failed["status"] == "FAILED" and failed["error"] == "Music video generation failed."
    assert failed["video_url"] is None
    assert_no_internals(failed)


async def test_zero_matched_lyrics_is_reported(client, mvh):
    mvh.aligner.doc = timed_doc([], unaligned=["I wake up to a brand new day"])
    version = await mvh.vocal_version()
    created = post(client, version.song_id, version.id).json()
    failed = client.get(f"/api/music-videos/{created['id']}").json()
    assert failed["error"] == "None of this version's lyrics could be matched to its audio."
    assert failed["unmatched_lines"] == ["I wake up to a brand new day"]


async def test_deleting_the_song_deletes_its_music_videos_and_files(client, mvh):
    version = await mvh.vocal_version()
    created = post(client, version.song_id, version.id).json()
    assert any(mvh.mv_storage.root.rglob("*.mp4"))
    assert client.delete(f"/api/songs/{version.song_id}").status_code == 204
    assert client.get(f"/api/music-videos/{created['id']}").status_code == 404
    assert not any(p.is_file() for p in mvh.mv_storage.root.rglob("*"))


async def test_song_details_and_versions_are_unchanged_by_music_videos(client, mvh):
    version = await mvh.vocal_version()
    before = client.get(f"/api/songs/{version.song_id}").json()
    post(client, version.song_id, version.id)
    after = client.get(f"/api/songs/{version.song_id}").json()
    assert before["versions"] == after["versions"]
