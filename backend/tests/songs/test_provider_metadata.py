"""Phase 10: surfacing the generation provider's own reported metadata
(bpm/genres/key_scale/time_signature) on the Song/Version API.

This is a pure plumbing feature -- ACE-Step already computes and returns this
data (see app/providers/ace_step.py); Tunora previously only exposed it on
JobResponse. No new dependency, no migration, no independent analysis: this
suite proves the read path (Job.result -> VersionEntry.metadata ->
VersionResponse.metadata) is correct, safely null where the provider didn't
report something, and never leaks anything beyond the four allowlisted
fields.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.repository import _version_metadata_from_result  # noqa: SLF001 -- unit-testing the helper directly
from app.songs.models import VersionMetadata
from tests.songs.test_service_versions import Harness


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


# -- the extraction helper, in isolation --------------------------------------------------------


def test_extracts_all_four_fields_when_the_provider_reported_all_of_them():
    result = {"metadata": {"bpm": 128, "genres": "Pop", "key_scale": "C major", "time_signature": "4/4"}}
    assert _version_metadata_from_result(result) == VersionMetadata(
        bpm=128.0, genres="Pop", key_scale="C major", time_signature="4/4"
    )


def test_partial_metadata_keeps_missing_fields_as_none_not_fabricated():
    result = {"metadata": {"bpm": 90, "genres": "", "key_scale": "", "time_signature": ""}}
    parsed = _version_metadata_from_result(result)
    assert parsed == VersionMetadata(bpm=90.0, genres=None, key_scale=None, time_signature=None)
    # ACE-Step's own convention defaults an unreported string field to "" -- normalized to None here.
    assert parsed.genres is None and parsed.key_scale is None and parsed.time_signature is None


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"metadata": {}},
        {"metadata": {"bpm": "", "genres": "", "key_scale": "", "time_signature": ""}},
        {"audio": {"key": "job-1/job-1.mp3"}, "duration": 10.0},  # legacy shape: no "metadata" key at all
        {"metadata": "not-a-dict"},
        {"metadata": None},
    ],
)
def test_absent_or_empty_metadata_returns_none_not_an_empty_object(result):
    assert _version_metadata_from_result(result) is None


@pytest.mark.parametrize(
    "bad_bpm",
    [True, False, "128", [], {}, None],
)
def test_malformed_bpm_is_dropped_not_coerced(bad_bpm):
    result = {"metadata": {"bpm": bad_bpm, "genres": "Rock"}}
    parsed = _version_metadata_from_result(result)
    assert parsed is not None and parsed.bpm is None and parsed.genres == "Rock"


@pytest.mark.parametrize("bad_value", [123, [], {}, True])
def test_malformed_string_fields_are_dropped_not_coerced(bad_value):
    result = {"metadata": {"bpm": 100, "genres": bad_value}}
    parsed = _version_metadata_from_result(result)
    assert parsed is not None and parsed.bpm == 100.0 and parsed.genres is None


def test_never_leaks_provider_transport_or_other_fields_through_the_helper():
    result = {
        "metadata": {
            "bpm": 100,
            "genres": "Pop",
            "audio_url": "http://127.0.0.1:8001/v1/audio?path=/secret",
            "prompt": "a secret prompt",
            "lyrics": "secret lyrics",
        }
    }
    parsed = _version_metadata_from_result(result)
    assert parsed == VersionMetadata(bpm=100.0, genres="Pop", key_scale=None, time_signature=None)
    assert not hasattr(parsed, "audio_url") and not hasattr(parsed, "prompt") and not hasattr(parsed, "lyrics")


# -- through the domain / repository -------------------------------------------------------------


@pytest.mark.asyncio
async def test_song_details_carries_the_versions_own_provider_metadata(h):
    job = await h.generate_to_completion(
        "a song", metadata={"bpm": 128, "genres": "Pop", "key_scale": "C major", "time_signature": "4/4"}
    )
    song_id = h.repository.get_version(job.version_id).song_id
    entries = h.repository.list_version_entries(song_id)
    assert len(entries) == 1
    assert entries[0].metadata == VersionMetadata(bpm=128.0, genres="Pop", key_scale="C major", time_signature="4/4")


@pytest.mark.asyncio
async def test_each_version_carries_its_own_metadata_never_a_sibling_versions(h):
    job1 = await h.generate_to_completion("v1", metadata={"bpm": 90, "genres": "Jazz"})
    song_id = h.repository.get_version(job1.version_id).song_id
    job2 = await h.generate_to_completion("v2", song_id=song_id, metadata={"bpm": 140, "genres": "Techno"})

    entries = {e.version.id: e for e in h.repository.list_version_entries(song_id)}
    assert entries[job1.version_id].metadata == VersionMetadata(bpm=90.0, genres="Jazz")
    assert entries[job2.version_id].metadata == VersionMetadata(bpm=140.0, genres="Techno")
    # explicitly not swapped
    assert entries[job1.version_id].metadata != entries[job2.version_id].metadata


@pytest.mark.asyncio
async def test_a_version_whose_job_never_completed_has_no_metadata(h):
    from app.providers.base import GenerationJob, GenerationRequest, JobState

    h.provider.generate_response = GenerationJob(job_id="pending-task", provider="ace-step", status=JobState.QUEUED)
    pending = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    song_id = h.repository.get_version(pending.version_id).song_id

    entries = h.repository.list_version_entries(song_id)
    assert entries[0].metadata is None
    assert entries[0].version.audio is None  # audio is independently absent too, but that's not why metadata is None


@pytest.mark.asyncio
async def test_a_version_with_no_provider_metadata_at_all_has_none(h):
    job = await h.generate_to_completion("a song", metadata={})
    song_id = h.repository.get_version(job.version_id).song_id
    entries = h.repository.list_version_entries(song_id)
    assert entries[0].metadata is None
    assert entries[0].version.audio is not None  # audio still works even though metadata is absent


@pytest.mark.asyncio
async def test_cross_song_isolation_a_songs_metadata_never_appears_under_another_song(h):
    job_a = await h.generate_to_completion("song a", metadata={"bpm": 77, "genres": "Blues"})
    job_b = await h.generate_to_completion("song b", metadata={"bpm": 200, "genres": "Metal"})
    song_a = h.repository.get_version(job_a.version_id).song_id
    song_b = h.repository.get_version(job_b.version_id).song_id

    entries_a = h.repository.list_version_entries(song_a)
    entries_b = h.repository.list_version_entries(song_b)
    assert len(entries_a) == 1 and len(entries_b) == 1
    assert entries_a[0].metadata == VersionMetadata(bpm=77.0, genres="Blues")
    assert entries_b[0].metadata == VersionMetadata(bpm=200.0, genres="Metal")


# -- through the HTTP API -------------------------------------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


@pytest.mark.asyncio
async def test_api_exposes_metadata_with_source_provider_and_null_for_missing_fields(h, client):
    job = await h.generate_to_completion("a song", metadata={"bpm": 128, "genres": "Pop"})
    song_id = h.repository.get_version(job.version_id).song_id

    body = client.get(f"/api/songs/{song_id}").json()
    metadata = body["versions"][0]["metadata"]
    assert metadata == {"bpm": 128.0, "genres": "Pop", "key_scale": None, "time_signature": None, "source": "provider"}


@pytest.mark.asyncio
async def test_api_metadata_is_null_when_the_provider_reported_nothing(h, client):
    job = await h.generate_to_completion("a song", metadata={})
    song_id = h.repository.get_version(job.version_id).song_id

    body = client.get(f"/api/songs/{song_id}").json()
    assert body["versions"][0]["metadata"] is None


@pytest.mark.asyncio
async def test_api_response_never_exposes_the_full_result_json_or_provider_internals(h, client):
    job = await h.generate_to_completion(
        "a song",
        metadata={
            "bpm": 128,
            "genres": "Pop",
            "audio_url": "http://127.0.0.1:8001/v1/audio?path=/secret/leak.mp3",
            "prompt": "a very distinctive secret prompt marker XYZZY",
        },
    )
    song_id = h.repository.get_version(job.version_id).song_id

    response = client.get(f"/api/songs/{song_id}")
    text = response.text
    # The provider's own transport URL and internal metadata keys must never leak,
    # regardless of where in result_json they live. (Tunora's own response legitimately
    # has an "audio_url" *key* pointing at its own /api/jobs/.../audio route -- only the
    # provider's URL *value* and the leaked prompt text are checked here.)
    for leaked in ("127.0.0.1:8001", "/v1/audio?path=", "XYZZY"):
        assert leaked not in text
    metadata = response.json()["versions"][0]["metadata"]
    assert set(metadata) == {"bpm", "genres", "key_scale", "time_signature", "source"}


@pytest.mark.asyncio
async def test_api_still_serves_audio_and_playback_when_metadata_is_absent(h, client):
    """Missing optional provider metadata must never break the actually-important thing: playback."""

    job = await h.generate_to_completion("a song", metadata={})
    song_id = h.repository.get_version(job.version_id).song_id

    details = client.get(f"/api/songs/{song_id}").json()
    assert details["versions"][0]["metadata"] is None
    assert details["versions"][0]["audio"] is not None
    audio_response = client.get(details["versions"][0]["audio"]["audio_url"])
    assert audio_response.status_code == 200


@pytest.mark.asyncio
async def test_existing_fields_are_unchanged_when_metadata_is_added(h, client):
    """Backward compatibility: adding `metadata` must not remove/rename anything else."""

    job = await h.generate_to_completion("a song", metadata={"bpm": 100})
    song_id = h.repository.get_version(job.version_id).song_id
    version = client.get(f"/api/songs/{song_id}").json()["versions"][0]
    assert set(version) == {
        "id", "version_number", "is_latest", "operation", "source_version_number", "status", "created_at",
        "duration", "audio", "prompt", "lyrics", "language", "instrumental", "seed", "metadata",
        "extracted_track",  # Phase 11 addition, null here (not an EXTRACT version)
    }
