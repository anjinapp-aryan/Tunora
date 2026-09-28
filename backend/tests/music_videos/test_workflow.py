"""Phase 24: audio-first workflow -- Music Video is an optional derivative of one Version.

Audio-only generation never touches Music Video code or storage; a video failure never fails the
Version; retry and delete act only on video state; many videos may come from one Version.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_music_videos import router as music_videos_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.music_videos.errors import (
    InvalidMusicVideoRequestError,
    MusicVideoInProgressError,
    MusicVideoStateError,
    RenderError,
)
from app.music_videos.models import MusicVideoStatus
from app.music_videos.renderer import check_background
from app.songs.errors import SourceAudioUnavailableError
from tests.music_videos.conftest import image


def _sha(mvh, version) -> str:
    return hashlib.sha256(mvh.storage.get_path(version.audio.key).read_bytes()).hexdigest()


def _counts(mvh, version) -> tuple[int, int, int]:
    return (len(mvh.repository.list(500)), len(mvh.repository.list_versions(version.song_id)),
            len(mvh.provider.generate_calls) if hasattr(mvh.provider, "generate_calls") else -1)


async def test_audio_only_generation_never_creates_music_video_state_or_files(mvh):
    job = await mvh.generate_to_completion(lyrics="la la")
    assert job.status == JobStatus.COMPLETED
    version = mvh.repository.get_version(job.version_id)
    assert mvh.mv_repository.list_for_song(version.song_id) == []
    assert not any(mvh.mv_storage.root.rglob("*"))  # no video directory, no file
    assert mvh.aligner.calls == [] and mvh.renderer.calls == []


async def test_a_failed_video_leaves_the_version_job_and_audio_untouched(mvh):
    version = await mvh.vocal_version()
    sha, before = _sha(mvh, version), _counts(mvh, version)
    job_status = [j.status for j in mvh.repository.list(500) if j.version_id == version.id]
    mvh.renderer.error = RenderError("boom")
    failed = mvh.mv.generate((await mvh.create(version)).id)
    assert failed.status == MusicVideoStatus.FAILED
    assert mvh.repository.get_version(version.id) == version
    assert [j.status for j in mvh.repository.list(500) if j.version_id == version.id] == job_status == [JobStatus.COMPLETED]
    assert _sha(mvh, version) == sha and _counts(mvh, version) == before


async def test_retry_repeats_only_the_video_work_from_the_same_version_and_background(mvh):
    version = await mvh.vocal_version()
    sha, before = _sha(mvh, version), _counts(mvh, version)
    mvh.renderer.error = RenderError("transient")
    video = await mvh.create(version, style="dreamy")
    mvh.mv.generate(video.id)
    mvh.renderer.error = None

    retried = mvh.mv.retry(video.id)
    assert (retried.id, retried.status, retried.error, retried.timed_lyrics) == (video.id, MusicVideoStatus.PENDING, None, None)
    done = mvh.mv.generate(video.id)
    assert done.status == MusicVideoStatus.COMPLETED
    call = mvh.renderer.calls[-1]
    assert (call["style"], call["background"]) == ("dreamy", mvh.mv_storage.get_path(video.background_key))
    assert mvh.aligner.calls[-1][0] == mvh.storage.get_path(version.audio.key)  # same source audio
    assert mvh.mv_repository.get(video.id).source_version_id == version.id
    assert _sha(mvh, version) == sha and _counts(mvh, version) == before  # no new Job/Version/generation


async def test_retry_is_refused_unless_failed_or_while_another_video_of_the_version_runs(mvh, monkeypatch):
    version = await mvh.vocal_version()
    done = await mvh.create(version)
    mvh.mv.generate(done.id)
    with pytest.raises(MusicVideoStateError, match="Only a failed"):
        mvh.mv.retry(done.id)

    mvh.renderer.error = RenderError("x")
    failed = await mvh.create(version)
    mvh.mv.generate(failed.id)
    mvh.renderer.error = None
    await mvh.create(version)  # a new one is now in progress for the same Version
    with pytest.raises(MusicVideoInProgressError):
        mvh.mv.retry(failed.id)


async def test_retry_is_refused_when_the_source_audio_or_the_background_is_gone(mvh):
    version = await mvh.vocal_version()
    mvh.renderer.error = RenderError("x")
    video = await mvh.create(version)
    mvh.mv.generate(video.id)
    mvh.mv_storage.get_path(video.background_key).unlink()
    with pytest.raises(MusicVideoStateError, match="background is no longer available"):
        mvh.mv.retry(video.id)
    mvh.storage.get_path(version.audio.key).unlink()
    with pytest.raises(SourceAudioUnavailableError):
        mvh.mv.retry(video.id)


async def test_several_videos_can_come_from_the_same_version(mvh):
    version = await mvh.vocal_version()
    ids = []
    for style in ("minimal_white", "dreamy", "bold"):
        video = await mvh.create(version, style=style)
        mvh.mv.generate(video.id)
        ids.append(video.id)
    videos = mvh.mv_repository.list_for_song(version.song_id)
    assert {v.id for v in videos} == set(ids)
    assert {v.source_version_id for v in videos} == {version.id}
    assert all(v.status == MusicVideoStatus.COMPLETED for v in videos)


async def test_deleting_a_video_keeps_the_song_version_audio_and_other_videos(mvh):
    version = await mvh.vocal_version()
    sha, before = _sha(mvh, version), _counts(mvh, version)
    keep, drop = await mvh.create(version), None
    mvh.mv.generate(keep.id)
    drop = await mvh.create(version)
    mvh.mv.generate(drop.id)

    mvh.mv.delete(drop.id)
    assert mvh.mv_repository.get(drop.id) is None and not (mvh.mv_storage.root / drop.id).exists()
    assert mvh.mv_repository.get(keep.id) is not None and (mvh.mv_storage.root / keep.id).exists()
    assert mvh.repository.get_song(version.song_id) is not None
    assert mvh.repository.get_version(version.id) == version
    assert _sha(mvh, version) == sha and _counts(mvh, version) == before


async def test_a_video_still_being_generated_cannot_be_deleted(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    with pytest.raises(MusicVideoStateError, match="still being generated"):
        mvh.mv.delete(video.id)


async def test_after_a_restart_an_interrupted_video_can_be_retried(mvh):
    version = await mvh.vocal_version()
    video = await mvh.create(version)
    mvh.mv_repository.update(replace(mvh.mv_repository.get(video.id), status=MusicVideoStatus.RENDERING))
    assert mvh.mv.recover_interrupted() == 1
    mvh.mv.retry(video.id)
    assert mvh.mv.generate(video.id).status == MusicVideoStatus.COMPLETED


# -- HTTP ------------------------------------------------------------------------------------------


@pytest.fixture
def client(mvh):
    app = FastAPI()
    for router in (jobs_router, songs_router, music_videos_router):
        app.include_router(router)
    app.state.job_service = mvh.service
    app.state.music_video_service = mvh.mv
    return TestClient(app)


async def test_retry_and_delete_endpoints(client, mvh):
    version = await mvh.vocal_version()
    mvh.renderer.error = RenderError(r"C:\secret")
    created = client.post(f"/api/songs/{version.song_id}/music-videos", params={"source_version_id": version.id},
                          content=b"\xff\xd8\xff\xe0" + b"\x00" * 64, headers={"Content-Type": "image/jpeg"}).json()
    assert client.get(f"/api/music-videos/{created['id']}").json()["status"] == "FAILED"
    assert client.delete(f"/api/music-videos/{created['id']}/retry").status_code == 405

    mvh.renderer.error = None
    r = client.post(f"/api/music-videos/{created['id']}/retry")
    assert r.status_code == 202 and r.json()["status"] == "PENDING" and r.json()["id"] == created["id"]
    assert client.get(f"/api/music-videos/{created['id']}").json()["status"] == "COMPLETED"  # task ran
    assert client.post(f"/api/music-videos/{created['id']}/retry").status_code == 409  # not failed any more
    assert client.post("/api/music-videos/mv-missing/retry").status_code == 404
    assert client.post("/api/music-videos/..%2Fx/retry").status_code == 404

    assert client.delete(f"/api/music-videos/{created['id']}").status_code == 204
    assert client.get(f"/api/music-videos/{created['id']}").status_code == 404
    assert client.delete(f"/api/music-videos/{created['id']}").status_code == 404
    assert client.get(f"/api/songs/{version.song_id}").status_code == 200  # the Song and its Version remain


# -- background decode check (Phase 24 robustness fix) -------------------------------------------------


def test_a_background_with_a_valid_header_but_corrupt_pixels_is_rejected_fast(approved_tools, tmp_path):
    good = image(approved_tools, tmp_path / "ok.png", size="640x360")
    data = bytearray(good.read_bytes())
    at = data.find(b"IDAT")
    data[at + 8: at + 408] = b"\x5a" * 400
    bad = tmp_path / "corrupt.png"
    bad.write_bytes(bytes(data))
    assert check_background(approved_tools, good).width == 640
    with pytest.raises(InvalidMusicVideoRequestError, match="could not be decoded"):
        check_background(approved_tools, bad)  # previously passed the probe and hung the render
