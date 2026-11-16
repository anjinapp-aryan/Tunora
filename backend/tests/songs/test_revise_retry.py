"""Phase 28: Revise & Retry -- a NEW Version of the same Song from one explicit Version's inputs.

Revise = the user edited the inputs; Retry = unchanged inputs (typically after a failed
generation). Both go through POST /api/jobs with song_id + source_version_id, create a new Job
and Version (lineage REVISE from the source), and never touch the source Version, Job or audio.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.providers.errors import ProviderUnavailableError
from app.songs.errors import InvalidIdError, InvalidOperationError, SongNotFoundError, SourceVersionNotFoundError
from tests.jobs.test_recovery import ScriptedProvider, _audio, _restart
from tests.songs.test_service_versions import ACE_ID, Harness

OPS = frozenset({"ORIGINAL", "EXTEND", "REMIX", "REPAINT", "EXTRACT", "ANOTHER_TAKE", "REVISE"})
SPEC = dict(prompt="warm acoustic ballad", lyrics="[Verse]\nla la la", language="en", duration=60.0, seed=7,
            instrumental=False)


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    harness.provider.supported_operations = OPS
    return harness


async def _complete(h, job, content=b"ID3-audio"):
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(job_id=ACE_ID, audio_path=h.source_audio(f"o-{job.id}.mp3", content),
                                                  duration=12.5)
    return await h.service.poll_once(job.id)


async def _song(h, **spec):
    job = await h.generate_to_completion(**{**SPEC, **spec})
    return h.repository.get_version(job.version_id)


def _sha(h, version) -> str:
    return hashlib.sha256(h.storage.get_path(h.repository.get_version(version.id).audio.key).read_bytes()).hexdigest()


# -- revise ------------------------------------------------------------------------------------------


async def test_revise_creates_a_new_version_of_the_same_song_and_leaves_the_source_alone(h):
    v1 = await _song(h)
    before, sha = h.repository.get_version(v1.id), _sha(h, v1)
    edited = GenerationRequest(**{**SPEC, "prompt": "dark synthwave", "lyrics": "[Chorus]\nnew words", "duration": 120.0})
    job = await h.service.create_revision(v1.song_id, v1.id, edited)
    assert job.status == JobStatus.SUBMITTED
    v2 = h.repository.get_version(job.version_id)
    assert (v2.song_id, v2.version_number, v2.id != v1.id) == (v1.song_id, 2, True)
    assert (v2.operation, v2.source_version_id) == ("REVISE", v1.id)
    assert v2.operation_params == {"changed": ["prompt", "lyrics", "duration"]}
    assert (v2.spec.prompt, v2.spec.lyrics, v2.spec.duration, v2.spec.seed) == ("dark synthwave", "[Chorus]\nnew words", 120.0, 7)
    # The source is untouched: row, spec, job and audio.
    assert h.repository.get_version(v1.id) == before and _sha(h, v1) == sha
    assert h.provider.generate_calls[-1].operation == "REVISE"
    await _complete(h, job, b"NEW-AUDIO")
    v2 = h.repository.get_version(v2.id)
    assert v2.audio is not None and v2.audio.key != before.audio.key and _sha(h, v1) == sha


async def test_revise_starts_from_the_explicit_version_not_the_latest_or_the_first(h):
    v1 = await _song(h)
    v2 = h.repository.get_version((await h.generate_to_completion(song_id=v1.song_id, **{**SPEC, "prompt": "v2 idea"})).version_id)
    await h.generate_to_completion(song_id=v1.song_id, **{**SPEC, "prompt": "v3 idea"})  # latest is v3
    job = await h.service.create_revision(v1.song_id, v2.id, GenerationRequest(**{**SPEC, "prompt": "v2 idea"}))
    v4 = h.repository.get_version(job.version_id)
    assert (v4.version_number, v4.source_version_id) == (4, v2.id)
    assert v4.operation_params == {"changed": []}  # identical inputs = a retry of v2


async def test_settings_changes_are_recorded_only_on_the_new_version(h):
    v1 = await _song(h)
    job = await h.service.create_revision(v1.song_id, v1.id, GenerationRequest(
        **{**SPEC, "language": "kn", "seed": None, "instrumental": True, "lyrics": ""}))
    v2 = h.repository.get_version(job.version_id)
    assert v2.operation_params == {"changed": ["lyrics", "language", "seed", "instrumental"]}
    assert (v2.spec.language, v2.spec.seed, v2.spec.instrumental) == ("kn", None, True)
    assert h.repository.get_version(v1.id).spec == GenerationRequest(**SPEC)


async def test_cross_song_unknown_and_malformed_sources_are_rejected_before_anything_is_written(h):
    a, b = await _song(h), await _song(h, prompt="other song")
    count = len(h.repository.list(500))
    with pytest.raises(SourceVersionNotFoundError):
        await h.service.create_revision(a.song_id, b.id, GenerationRequest(**SPEC))
    with pytest.raises(SourceVersionNotFoundError):
        await h.service.create_revision(a.song_id, "ver-missing", GenerationRequest(**SPEC))
    with pytest.raises(SongNotFoundError):
        await h.service.create_revision("song-missing", a.id, GenerationRequest(**SPEC))
    with pytest.raises(InvalidIdError):
        await h.service.create_revision(a.song_id, "../x", GenerationRequest(**SPEC))
    with pytest.raises(InvalidOperationError):
        await h.service.create_revision(a.song_id, a.id, GenerationRequest(**{**SPEC, "prompt": "   "}))
    assert len(h.repository.list(500)) == count and len(h.repository.list_versions(a.song_id)) == 1


async def test_an_extracted_track_cannot_be_revised(h):
    v1 = await _song(h)
    extract = replace(v1, id="ver-extract", version_number=9, operation="EXTRACT", source_version_id=v1.id, audio=None)
    conn = sqlite3.connect(h.db)
    conn.execute("INSERT INTO versions (id, song_id, version_number, prompt, lyrics, language, instrumental, provider, "
                 "created_at, operation, source_version_id) VALUES (?, ?, 9, 'p', '', 'en', 0, 'fake', '2026-01-01T00:00:00+00:00', "
                 "'EXTRACT', ?)",
                 (extract.id, v1.song_id, v1.id))
    conn.commit()
    conn.close()
    with pytest.raises(InvalidOperationError):
        await h.service.create_revision(v1.song_id, extract.id, GenerationRequest(**SPEC))


def test_the_ace_step_provider_runs_revise_as_plain_text_to_music():
    assert "REVISE" in AceStepMusicGenerationProvider.supported_operations
    assert "REVISE" in AceStepMusicGenerationProvider._TEXT_TO_MUSIC_OPERATIONS
    payload = AceStepMusicGenerationProvider(base_url="http://x")._build_release_task_payload(
        GenerationRequest(**{**SPEC, "operation": "REVISE"}))
    assert payload["audio_duration"] == 60.0 and payload["seed"] == 7 and "task_type" not in payload


# -- retry after a failure -------------------------------------------------------------------------------


async def test_a_failed_generation_keeps_its_inputs_and_retry_is_a_new_attempt(h):
    h.provider.generate_response = ProviderUnavailableError("ACE-Step is down")
    failed = await h.service.create_and_submit(GenerationRequest(**SPEC), title="My Song")
    assert failed.status == JobStatus.FAILED
    v1 = h.repository.get_version(failed.version_id)
    assert v1.spec == GenerationRequest(**SPEC) and v1.audio is None  # the inputs survived the failure

    h.provider.generate_response = GenerationJob(job_id=ACE_ID, provider="ace-step", status=JobState.QUEUED)
    retry = await h.service.create_revision(v1.song_id, v1.id, GenerationRequest(**SPEC))
    assert retry.id != failed.id and retry.status == JobStatus.SUBMITTED
    assert h.service.get(failed.id).status == JobStatus.FAILED  # history is not rewritten
    v2 = h.repository.get_version(retry.version_id)
    assert (v2.song_id, v2.version_number, v2.source_version_id, v2.operation_params) == (v1.song_id, 2, v1.id, {"changed": []})
    assert h.repository.get_song(v1.song_id).title == "My Song"  # same Song, no duplicate
    await _complete(h, retry)
    assert len({s.song.id for s in h.repository.list_song_summaries(query="", sort="newest", limit=50)}) == 1


# -- API -------------------------------------------------------------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


async def test_api_revise_contract_and_errors(h, client):
    v1 = await _song(h)
    other = await _song(h, prompt="other")
    body = {**SPEC, "song_id": v1.song_id, "source_version_id": v1.id, "prompt": "revised idea"}
    h.provider.status_responses = [GenerationStatus(job_id=ACE_ID, status=JobState.SUCCEEDED)]
    h.provider.result_response = GenerationResult(job_id=ACE_ID, audio_path=h.source_audio("rev.mp3", b"R" * 99), duration=12.5)
    r = client.post("/api/jobs", json=body)
    assert r.status_code == 200, r.text
    assert (r.json()["song_id"], r.json()["version_number"]) == (v1.song_id, 2)
    details = client.get(f"/api/songs/{v1.song_id}").json()
    newest = details["versions"][0]
    assert (newest["operation"], newest["source_version_number"], newest["prompt"]) == ("REVISE", 1, "revised idea")
    assert newest["requested_duration"] == 60.0 and details["versions"][1]["prompt"] == SPEC["prompt"]
    assert r.json()["version_id"] != v1.id

    assert client.post("/api/jobs", json={**body, "source_version_id": other.id}).status_code == 404  # cross-song
    assert client.post("/api/jobs", json={**body, "source_version_id": "ver-nope"}).status_code == 404
    assert client.post("/api/jobs", json={**body, "source_version_id": "../../etc"}).status_code == 422
    no_song = {k: v for k, v in body.items() if k != "song_id"}
    assert client.post("/api/jobs", json=no_song).status_code == 422
    assert client.post("/api/jobs", json={**body, "prompt": " "}).status_code == 422


# -- restart recovery --------------------------------------------------------------------------------------


@pytest.fixture
def world(tmp_path):
    from app.jobs.service import JobService

    harness = Harness(tmp_path)
    provider = ScriptedProvider()
    provider.supported_operations = OPS
    harness.provider = provider
    harness.service = JobService(repository=harness.repository, provider=provider, storage=harness.storage,
                                 poll_interval_seconds=0.0)
    return harness


async def test_a_revision_in_flight_is_recovered_after_a_restart(world):
    first = await world.service.create_and_submit(GenerationRequest(**SPEC))
    world.provider.script[first.provider_job_id] = {"statuses": [JobState.SUCCEEDED], "result": _audio(world, "one.mp3")}
    await world.service.poll_once(first.id)
    v1 = world.repository.get_version(world.repository.get(first.id).version_id)

    revision = await world.service.create_revision(v1.song_id, v1.id, GenerationRequest(**{**SPEC, "prompt": "new"}))
    world.provider.script[revision.provider_job_id] = {"statuses": [JobState.RUNNING, JobState.SUCCEEDED],
                                                       "result": _audio(world, "two.mp3")}
    summary = await _restart(world).recover_unfinished_jobs()  # the process died after submitting
    assert summary["completed"] == 1
    assert (revision.provider_job_id, "REVISE") in world.provider.registered
    v2 = world.repository.get_version(world.repository.get(revision.id).version_id)
    assert (v2.operation, v2.source_version_id, v2.version_number) == ("REVISE", v1.id, 2) and v2.audio is not None
    assert len(world.provider.generate_calls) == 2  # never resubmitted
