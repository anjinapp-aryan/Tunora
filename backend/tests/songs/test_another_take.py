"""Phase 13: ANOTHER_TAKE -- a fresh generation of the same creative idea as a NEW Version.

Reuses the creative-operation machinery of tests/songs/test_operations.py (lineage, immutability,
security conventions). No source audio is read, the seed is left to the provider, and exactly one
output becomes exactly one Version (docs/PHASE-13-IMPLEMENTATION.md).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationRequest
from app.providers.errors import ProviderUnavailableError, UnsupportedOperationError
from app.songs.errors import InvalidIdError, InvalidOperationError, SourceVersionNotFoundError
from tests.songs.test_operations import api_source, complete, first_version, op_url, queue_result, wrap
from tests.songs.test_service_versions import ACE_ID, Harness

ALL_OPS = frozenset({"ORIGINAL", "EXTEND", "REMIX", "REPAINT", "EXTRACT", "ANOTHER_TAKE"})
SPEC = dict(lyrics="la la la", language="kn", instrumental=False, duration=45.0)


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    harness.provider.supported_operations = ALL_OPS
    return harness


async def source(h, prompt="warm piano ballad", **spec):
    """A completed ORIGINAL version whose request carried `spec` and whose stored audio is 12.5 s."""

    job = await h.service.create_and_submit(GenerationRequest(prompt=prompt, **spec), title="I Will Rise")
    job = await complete(h, job, duration=12.5, content=b"SOURCE-AUDIO" * 100)
    return job, h.repository.get_version(job.version_id)


# -- creation, lineage, immutability -------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_take_creates_exactly_one_new_version_and_leaves_the_source_untouched(h):
    _, v1 = await source(h, seed=5, **SPEC)
    before = h.repository.get_version(v1.id)
    audio_before = h.storage.get_path(v1.audio.key).read_bytes()

    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")

    assert len(h.repository.list_versions(v1.song_id)) == 2  # exactly one new Version
    v2 = h.repository.get_version(job.version_id)
    assert (v2.version_number, v2.song_id, v2.operation, v2.source_version_id) == (2, v1.song_id, "ANOTHER_TAKE", v1.id)
    assert v2.id != v1.id and job.id != v1.id
    assert h.repository.get_version(v1.id) == before
    assert h.storage.get_path(v1.audio.key).read_bytes() == audio_before


@pytest.mark.asyncio
async def test_another_take_copies_the_creative_inputs_and_nothing_else(h):
    _, v1 = await source(h, **SPEC)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")

    request = h.provider.generate_calls[-1]
    assert (request.prompt, request.lyrics, request.language, request.instrumental, request.duration) == (
        "warm piano ballad", "la la la", "kn", False, 45.0,
    )
    assert request.operation == "ANOTHER_TAKE"
    for unused in ("source_audio_path", "source_duration", "extend_seconds", "repaint_start", "repaint_end",
                   "remix_strength", "track_name", "batch_size"):
        assert getattr(request, unused) is None, unused
    v2 = h.repository.get_version(job.version_id)
    assert (v2.spec.prompt, v2.spec.lyrics, v2.spec.language, v2.spec.instrumental, v2.spec.duration) == (
        "warm piano ballad", "la la la", "kn", False, 45.0,
    )
    assert v2.operation_params is None


@pytest.mark.asyncio
async def test_another_take_never_reuses_the_source_seed_or_batch_size(h):
    _, v1 = await source(h, seed=1234, batch_size=4)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")
    assert h.provider.generate_calls[-1].seed is None  # the provider picks a fresh random seed
    assert h.provider.generate_calls[-1].batch_size is None
    v2 = h.repository.get_version(job.version_id)
    assert v2.spec.seed is None and v2.spec.batch_size is None
    assert h.repository.get_version(v1.id).spec.seed == 1234  # the source keeps its own seed


@pytest.mark.asyncio
async def test_another_take_falls_back_to_the_stored_audio_duration(h):
    _, v1 = await source(h)  # the request had no duration; the stored audio is 12.5 s
    await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")
    assert h.provider.generate_calls[-1].duration == 12.5


@pytest.mark.asyncio
async def test_another_take_needs_no_source_audio(h):
    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))  # never completed: no audio
    v1 = h.repository.get_version(job.version_id)
    assert v1.audio is None
    take = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")
    assert h.repository.get_version(take.version_id).version_number == 2


@pytest.mark.asyncio
async def test_takes_chain_and_branch_with_song_scoped_numbering(h):
    _, v1 = await first_version(h)
    j2 = await complete(h, await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE"))
    j3 = await h.service.create_version_from_operation(v1.song_id, j2.version_id, "ANOTHER_TAKE")
    j4 = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")  # branch from V1 again

    versions = {v.version_number: v for v in h.repository.list_versions(v1.song_id)}
    assert sorted(versions) == [1, 2, 3, 4]
    assert [versions[n].source_version_id for n in (1, 2, 3, 4)] == [None, v1.id, j2.version_id, v1.id]
    assert [versions[n].operation for n in (1, 2, 3, 4)] == ["ORIGINAL", "ANOTHER_TAKE", "ANOTHER_TAKE", "ANOTHER_TAKE"]
    assert j4.version_id == versions[4].id and j3.version_id == versions[3].id


@pytest.mark.asyncio
async def test_concurrent_takes_get_unique_consecutive_version_numbers(h):
    _, v1 = await first_version(h)
    jobs = await asyncio.gather(
        *[h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE") for _ in range(5)]
    )
    numbers = sorted(h.repository.get_version(j.version_id).version_number for j in jobs)
    assert numbers == [2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_another_take_from_an_extended_version_copies_its_spec_not_the_extend_parameters(h):
    _, v1 = await first_version(h, prompt="base idea", duration=20.0)
    ext = await complete(h, await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTEND", extend_seconds=10))
    await h.service.create_version_from_operation(v1.song_id, ext.version_id, "ANOTHER_TAKE")
    request = h.provider.generate_calls[-1]
    assert (request.prompt, request.duration, request.operation) == ("base idea", 30.0, "ANOTHER_TAKE")
    assert request.extend_seconds is None


# -- validation, security, failure ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_take_of_an_extracted_track_is_refused_and_creates_nothing(h):
    _, v1 = await first_version(h)
    ext = await complete(h, await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals"))
    with pytest.raises(InvalidOperationError):
        await h.service.create_version_from_operation(v1.song_id, ext.version_id, "ANOTHER_TAKE")
    assert len(h.repository.list_versions(v1.song_id)) == 2


@pytest.mark.asyncio
async def test_another_take_from_another_songs_or_unknown_version_is_refused(h):
    _, a1 = await first_version(h, "song a")
    _, b1 = await first_version(h, "song b")
    for song_id, version_id in [(a1.song_id, b1.id), (b1.song_id, a1.id), (a1.song_id, "ver-does-not-exist")]:
        with pytest.raises(SourceVersionNotFoundError):
            await h.service.create_version_from_operation(song_id, version_id, "ANOTHER_TAKE")
    for bad in ("../../etc/passwd", "a/b", "C:\\x", "ver-1' OR '1'='1", "x" * 81, "", "a b"):
        with pytest.raises(InvalidIdError):
            await h.service.create_version_from_operation(a1.song_id, bad, "ANOTHER_TAKE")
    assert len(h.repository.list_versions(a1.song_id)) == 1 and len(h.repository.list_versions(b1.song_id)) == 1


@pytest.mark.asyncio
async def test_another_take_unsupported_by_the_provider_is_refused_without_side_effects(tmp_path):
    h = Harness(tmp_path)  # default FakeProvider supports ORIGINAL only
    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    v1 = h.repository.get_version((await complete(h, job)).version_id)
    with pytest.raises(UnsupportedOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")
    assert len(h.repository.list_versions(v1.song_id)) == 1


@pytest.mark.asyncio
async def test_a_provider_failure_fails_the_new_job_and_keeps_history_intact(h):
    _, v1 = await first_version(h)
    before = h.repository.get_version(v1.id)
    h.provider.generate_response = ProviderUnavailableError("down")
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "ANOTHER_TAKE")

    assert job.status is JobStatus.FAILED
    assert sorted(v.version_number for v in h.repository.list_versions(v1.song_id)) == [1, 2]
    failed = h.repository.get_version(job.version_id)
    assert failed.audio is None and failed.operation == "ANOTHER_TAKE"
    assert h.repository.get_version(v1.id) == before


# -- HTTP API -------------------------------------------------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


def test_api_another_take_creates_a_new_version_with_lineage_via_the_existing_operation_route(client, h):
    v1 = api_source(client, h)
    v1_bytes = client.get(f"/api/jobs/{v1['id']}/audio").content
    queue_result(h, b"TAKE" * 300, 20.0)
    take = client.post(op_url(v1, "another_take"), json={}).json()
    assert take["version_number"] == 2 and take["song_id"] == v1["song_id"] and take["id"] != v1["id"]

    versions = {v["version_number"]: v for v in client.get(f"/api/songs/{v1['song_id']}").json()["versions"]}
    assert (versions[2]["operation"], versions[2]["source_version_number"], versions[2]["is_latest"]) == ("ANOTHER_TAKE", 1, True)
    assert versions[2]["seed"] is None and versions[1]["operation"] == "ORIGINAL"
    assert versions[2]["prompt"] == versions[1]["prompt"]
    assert client.get(f"/api/jobs/{v1['id']}/audio").content == v1_bytes  # source audio unchanged
    assert client.get(f"/api/jobs/{take['id']}/audio").content == b"TAKE" * 300


def test_api_another_take_rejects_cross_song_malformed_and_unknown_operations(client, h):
    v1 = api_source(client, h)
    other = api_source(client, h)
    r = client.post(f"/api/songs/{v1['song_id']}/versions/{other['version_id']}/another_take", json={})
    assert r.status_code == 404
    assert client.post(f"/api/songs/{v1['song_id']}/versions/bad'id/another_take", json={}).status_code == 422
    for op in ("another-take", "regenerate", "variation", "ANOTHER_TAKE_X"):
        assert client.post(op_url(v1, op), json={}).status_code == 422, op
    assert len(client.get(f"/api/songs/{v1['song_id']}").json()["versions"]) == 1


def test_api_another_take_ignores_client_supplied_generation_fields(client, h):
    v1 = api_source(client, h)
    queue_result(h, b"TAKE" * 100, 20.0)
    r = client.post(
        op_url(v1, "another_take"),
        json={"prompt": "hijack", "lyrics": "x", "track_name": "vocals", "extend_seconds": 5},
    )
    assert r.status_code == 200
    sent = h.provider.generate_calls[-1]
    assert (sent.prompt, sent.lyrics, sent.track_name, sent.extend_seconds) == ("quiet piano", "", None, None)


def test_api_another_take_response_never_leaks_provider_or_path_details(client, h):
    v1 = api_source(client, h)
    queue_result(h, b"TAKE" * 100, 20.0)
    r = client.post(op_url(v1, "another_take"), json={})
    text = r.text + client.get(f"/api/songs/{v1['song_id']}").text
    for leaked in (str(h.tmp_path), "source_audio_path", "absolute_path", ACE_ID, "/v1/audio"):
        assert leaked not in text, leaked


# -- provider mapping (ACE-Step) -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_step_maps_another_take_to_plain_text_to_music_with_a_random_seed():
    provider = AceStepMusicGenerationProvider(base_url="http://127.0.0.1:8001")
    request = GenerationRequest(prompt="p", lyrics="l", language="hi", duration=30.0, operation="ANOTHER_TAKE")
    with respx.mock(base_url="http://127.0.0.1:8001") as mock:
        route = mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "t1"})))
        await provider.generate(request)
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("application/json")  # no source-audio upload
    body = json.loads(sent.content)
    assert body["audio_duration"] == 30.0 and body["use_random_seed"] is True
    assert body["vocal_language"] == "hi" and body["lyrics"] == "l"
    for absent in ("task_type", "seed", "batch_size", "src_audio", "repainting_start"):
        assert absent not in body, absent


def test_ace_step_advertises_another_take():
    assert "ANOTHER_TAKE" in AceStepMusicGenerationProvider.supported_operations
