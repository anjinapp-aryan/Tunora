"""Phase 26: Unified Creation Workflow -- Audio + Video / Lyrics Video in one request.

The Create page starts the song (POST /api/jobs, which returns the new Version's id at once) and
then asks for a Music Video of that exact Version with wait_for_audio=true. The video waits as
WAITING_FOR_AUDIO, renders only after that Version's audio exists, and can never fail, change or
regenerate the audio. Audio Only never reaches any of this (see test_workflow.py).
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_music_videos import router as music_videos_router
from app.jobs.models import JobStatus
from app.music_videos.errors import (
    InvalidMusicVideoRequestError,
    MusicVideoInProgressError,
    MusicVideoStateError,
    RenderError,
)
from app.music_videos.models import MusicVideoStatus
from app.music_videos.service import public_error
from app.providers.base import GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.songs.errors import SourceAudioUnavailableError, SourceVersionNotFoundError
from tests.music_videos.conftest import JPEG, LYRICS
from tests.songs.test_service_versions import ACE_ID


async def _start_song(mvh, **spec):
    """What the Create page's first call does: Song + Version + Job, audio not generated yet."""

    job = await mvh.service.create_and_submit(GenerationRequest(prompt="a song", lyrics=spec.pop("lyrics", LYRICS), **spec))
    assert job.status == JobStatus.SUBMITTED and job.version_id
    return job, mvh.repository.get_version(job.version_id)


async def _finish_song(mvh, job, *, ok: bool = True):
    if ok:
        mvh.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
        mvh.provider.result_response = GenerationResult(
            job_id=ACE_ID, audio_path=mvh.source_audio(f"out-{job.id}.mp3", b"ID3-real-audio"), duration=12.5)
    else:
        mvh.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.FAILED, message="gpu oom")]
    return await mvh.service.poll_once(job.id)


async def _create_waiting(mvh, version, **kw):
    async def chunks():
        yield JPEG
    return await mvh.mv.create(version.song_id, source_version_id=kw.pop("source_version_id", version.id),
                               style=kw.pop("style", "cinematic"), aspect_ratio="9:16", media_type="image/jpeg",
                               chunks=chunks(), wait_for_audio=True)


def _sha(mvh, version_id) -> str:
    version = mvh.repository.get_version(version_id)
    return hashlib.sha256(mvh.storage.get_path(version.audio.key).read_bytes()).hexdigest()


async def test_audio_and_video_waits_for_the_exact_new_version_then_renders_it(mvh):
    job, version = await _start_song(mvh)
    video = await _create_waiting(mvh, version)
    assert video.status == MusicVideoStatus.WAITING_FOR_AUDIO
    assert video.source_version_id == job.version_id  # the exact Version, never "latest"/"v1"
    assert mvh.aligner.calls == [] and mvh.renderer.calls == []

    await _finish_song(mvh, job)
    sha = _sha(mvh, version.id)
    done = mvh.mv.generate(video.id)
    assert done.status == MusicVideoStatus.COMPLETED and done.source_version_id == version.id
    audio_path = mvh.storage.get_path(mvh.repository.get_version(version.id).audio.key)
    assert mvh.aligner.calls[0][0] == audio_path and mvh.renderer.calls[0]["audio"] == audio_path
    assert mvh.renderer.calls[0]["style"] == "cinematic"
    assert _sha(mvh, version.id) == sha
    assert len(mvh.provider.generate_calls) == 1  # one audio generation, never a second one
    assert len(mvh.repository.list_versions(version.song_id)) == 1


async def test_a_ready_version_skips_waiting(mvh):
    version = await mvh.vocal_version()
    video = await _create_waiting(mvh, version)
    assert video.status == MusicVideoStatus.PENDING


async def test_without_wait_for_audio_a_version_still_generating_is_rejected(mvh):
    _, version = await _start_song(mvh)
    with pytest.raises(SourceAudioUnavailableError):
        await mvh.create(version)  # the Phase 23/24 "create video later" contract is unchanged
    assert mvh.mv_repository.list_for_song(version.song_id) == []


async def test_when_the_audio_fails_the_video_fails_safely_and_cannot_be_retried(mvh):
    job, version = await _start_song(mvh)
    video = await _create_waiting(mvh, version)
    assert (await _finish_song(mvh, job, ok=False)).status == JobStatus.FAILED
    failed = mvh.mv.generate(video.id)
    assert failed.status == MusicVideoStatus.FAILED and failed.error.startswith("source_failed")
    assert public_error(failed) == "The song's audio could not be generated, so this video was not made."
    assert "gpu" not in public_error(failed)
    assert mvh.renderer.calls == [] and len(mvh.provider.generate_calls) == 1
    with pytest.raises(SourceAudioUnavailableError):
        mvh.mv.retry(video.id)  # nothing to render from; the audio is never regenerated by a video


async def test_a_video_failure_after_the_audio_leaves_the_audio_and_retry_reuses_it(mvh):
    job, version = await _start_song(mvh)
    video = await _create_waiting(mvh, version)
    await _finish_song(mvh, job)
    sha = _sha(mvh, version.id)
    mvh.renderer.error = RenderError("boom")
    assert mvh.mv.generate(video.id).status == MusicVideoStatus.FAILED
    assert mvh.service.get(job.id).status == JobStatus.COMPLETED and _sha(mvh, version.id) == sha

    mvh.renderer.error = None
    retried = mvh.mv.retry(video.id)
    assert retried.id == video.id and retried.source_version_id == version.id
    assert mvh.mv.generate(video.id).status == MusicVideoStatus.COMPLETED
    assert _sha(mvh, version.id) == sha and len(mvh.provider.generate_calls) == 1
    assert len(mvh.repository.list(500)) == 1  # retry created no Job and no Version


async def test_cross_song_and_unknown_versions_are_rejected(mvh):
    _, mine = await _start_song(mvh)
    other = await mvh.vocal_version()
    with pytest.raises(SourceVersionNotFoundError):
        await _create_waiting(mvh, mine, source_version_id=other.id)
    with pytest.raises(SourceVersionNotFoundError):
        await _create_waiting(mvh, mine, source_version_id="no-such-version")
    assert not any(mvh.mv_storage.root.rglob("*"))


async def test_instrumental_or_lyric_less_songs_cannot_get_a_lyrics_video(mvh):
    _, instrumental = await _start_song(mvh, lyrics="", instrumental=True)
    with pytest.raises(InvalidMusicVideoRequestError):
        await _create_waiting(mvh, instrumental)
    assert not any(mvh.mv_storage.root.rglob("*"))


async def test_one_waiting_video_per_version_but_delete_needs_it_finished(mvh):
    _, version = await _start_song(mvh)
    video = await _create_waiting(mvh, version)
    with pytest.raises(MusicVideoInProgressError):
        await _create_waiting(mvh, version)
    with pytest.raises(MusicVideoStateError):
        mvh.mv.delete(video.id)


async def test_waiting_never_holds_the_render_lock(mvh):
    _, waiting_version = await _start_song(mvh)
    waiting = await _create_waiting(mvh, waiting_version)
    ready = await mvh.create(await mvh.vocal_version())
    mvh.mv._audio_poll_seconds = 0.01
    thread = mvh.mv.start_waiting(waiting.id)
    result: list = []
    other = threading.Thread(target=lambda: result.append(mvh.mv.generate(ready.id)))
    other.start()
    other.join(timeout=10)
    assert result and result[0].status == MusicVideoStatus.COMPLETED  # rendered while the other waits
    mvh.mv.stop()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert mvh.mv.get(waiting.id).status == MusicVideoStatus.WAITING_FOR_AUDIO  # stop leaves it resumable


async def test_restart_resumes_waiting_videos_and_fails_interrupted_renders(mvh):
    job, version = await _start_song(mvh)
    waiting = await _create_waiting(mvh, version)
    rendering = await mvh.create(await mvh.vocal_version())
    mvh.mv_repository.update(replace(rendering, status=MusicVideoStatus.RENDERING))

    assert mvh.mv.recover_interrupted() == 1
    assert mvh.mv.get(rendering.id).status == MusicVideoStatus.FAILED
    assert mvh.mv.get(waiting.id).status == MusicVideoStatus.WAITING_FOR_AUDIO

    await _finish_song(mvh, job)
    mvh.mv._audio_poll_seconds = 0.01
    started: list[str] = []
    original = mvh.mv.start_waiting
    mvh.mv.start_waiting = lambda vid: started.append(vid) or original(vid)
    assert mvh.mv.resume_waiting() == [waiting.id] and started == [waiting.id]
    for _ in range(500):
        if mvh.mv.get(waiting.id).status == MusicVideoStatus.COMPLETED:
            break
        threading.Event().wait(0.01)
    assert mvh.mv.get(waiting.id).status == MusicVideoStatus.COMPLETED


async def test_deleting_the_song_while_waiting_ends_the_wait_quietly(mvh):
    _, version = await _start_song(mvh)
    video = await _create_waiting(mvh, version)
    mvh.service.delete_song(version.song_id)
    assert mvh.mv.generate(video.id) is None


async def test_api_wait_for_audio_starts_a_waiting_video_and_hides_internals(mvh):
    app = FastAPI()
    app.include_router(music_videos_router)
    app.state.job_service, app.state.music_video_service = mvh.service, mvh.mv
    started: list[str] = []
    mvh.mv.start_waiting = started.append
    client = TestClient(app)
    _, version = await _start_song(mvh)
    url = f"/api/songs/{version.song_id}/music-videos"
    headers = {"Content-Type": "image/jpeg"}

    res = client.post(url, params={"source_version_id": version.id, "style": "karaoke", "wait_for_audio": "true"},
                      content=JPEG, headers=headers)
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "WAITING_FOR_AUDIO" and body["source_version_id"] == version.id
    assert body["source_version_number"] == 1 and body["video_url"] is None and body["error"] is None
    assert started == [body["id"]] and mvh.renderer.calls == []
    assert "background" not in res.text and str(mvh.tmp_path) not in res.text

    other = await mvh.vocal_version()
    res = client.post(url, params={"source_version_id": other.id, "wait_for_audio": "true"}, content=JPEG, headers=headers)
    assert res.status_code == 404  # another song's version
    res = client.post(url, params={"source_version_id": version.id, "wait_for_audio": "maybe"}, content=JPEG, headers=headers)
    assert res.status_code == 422
    res = client.post(url, params={"source_version_id": version.id, "style": "neon", "wait_for_audio": "true"},
                      content=JPEG, headers=headers)
    assert res.status_code == 422
