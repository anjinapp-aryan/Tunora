"""Phase 11: EXTRACT (stem/track separation via ACE-Step's native base-tier `extract` task
type, see docs/PHASE-11-IMPLEMENTATION.md). Reuses the exact same creative-operation machinery
already proven for EXTEND/REMIX/REPAINT (tests/songs/test_operations.py): a new immutable
Version, source lineage, provider mapping, security and error conventions -- extended, not
duplicated.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.providers.errors import UnsupportedOperationError
from app.songs.errors import InvalidIdError, InvalidOperationError, SourceVersionNotFoundError
from app.songs.operations import TRACK_NAMES
from tests.songs.test_operations import ace_request, api_source, complete, first_version, op_url, queue_result, wrap
from tests.songs.test_service_versions import ACE_ID, Harness

ALL_OPS = frozenset({"ORIGINAL", "EXTEND", "REMIX", "REPAINT", "EXTRACT"})


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    harness.provider.supported_operations = ALL_OPS
    return harness


# -- creation, lineage, immutability ---------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_creates_a_new_version_without_touching_the_source(h):
    _, v1 = await first_version(h, seed=5)
    before = h.repository.get_version(v1.id)

    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")

    v2 = h.repository.get_version(job.version_id)
    assert (v2.version_number, v2.song_id, v2.operation, v2.source_version_id) == (2, v1.song_id, "EXTRACT", v1.id)
    assert v2.operation_params == {"track_name": "vocals"}
    request = h.provider.generate_calls[-1]
    assert (request.operation, request.track_name) == ("EXTRACT", "vocals")
    assert request.source_audio_path == str(h.storage.get_path(v1.audio.key))
    # The source is untouched.
    assert h.repository.get_version(v1.id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("track", TRACK_NAMES)
async def test_extract_accepts_every_verified_track_name(h, track):
    _, v1 = await first_version(h)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name=track)
    assert h.repository.get_version(job.version_id).operation_params == {"track_name": track}


@pytest.mark.asyncio
async def test_extract_normalizes_case_and_whitespace_in_the_track_name(h):
    _, v1 = await first_version(h)
    job = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="  VOCALS  ")
    assert h.repository.get_version(job.version_id).operation_params == {"track_name": "vocals"}


@pytest.mark.asyncio
async def test_extract_lineage_chains_and_branches_like_other_operations(h):
    _, v1 = await first_version(h)
    j2 = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
    j2 = await complete(h, j2)
    j3 = await h.service.create_version_from_operation(v1.song_id, j2.version_id, "EXTRACT", track_name="drums")

    versions = {v.version_number: v for v in h.repository.list_versions(v1.song_id)}
    assert [versions[n].operation for n in (1, 2, 3)] == ["ORIGINAL", "EXTRACT", "EXTRACT"]
    assert [versions[n].source_version_id for n in (1, 2, 3)] == [None, v1.id, j2.version_id]


# -- validation -------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("track", [None, "", "   ", "banjo", "VOCAL", "vocals; drop table versions", "../etc/passwd"])
async def test_extract_rejects_unsupported_or_malformed_track_names_and_creates_nothing(h, track):
    _, v1 = await first_version(h)
    with pytest.raises(InvalidOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name=track)
    assert len(h.repository.list_versions(v1.song_id)) == 1


@pytest.mark.asyncio
async def test_extract_does_not_require_a_prompt_or_a_known_source_duration(h):
    """Unlike REMIX/REPAINT, EXTRACT needs no user prompt and no source-duration bound (unlike
    EXTEND/REPAINT) -- it operates on the whole source audio regardless of length."""

    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    job = await complete(h, job, duration=None)  # unknown duration
    v1 = h.repository.get_version(job.version_id)
    extract = await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
    assert h.repository.get_version(extract.version_id).version_number == 2


# -- security: cross-song, unknown, malformed ids ----------------------------------------------


@pytest.mark.asyncio
async def test_extract_from_another_songs_version_or_an_unknown_version_is_refused(h):
    _, a1 = await first_version(h, "song a")
    _, b1 = await first_version(h, "song b")
    for song_id, version_id in [(a1.song_id, b1.id), (b1.song_id, a1.id), (a1.song_id, "ver-does-not-exist")]:
        with pytest.raises(SourceVersionNotFoundError):
            await h.service.create_version_from_operation(song_id, version_id, "EXTRACT", track_name="vocals")
    for bad in ("../../etc/passwd", "..\\x", "a/b", "C:\\x", "ver-1' OR '1'='1", "x" * 81, "", "a b"):
        with pytest.raises(InvalidIdError):
            await h.service.create_version_from_operation(a1.song_id, bad, "EXTRACT", track_name="vocals")
    assert len(h.repository.list_versions(a1.song_id)) == 1 and len(h.repository.list_versions(b1.song_id)) == 1


@pytest.mark.asyncio
async def test_extract_unsupported_by_the_provider_is_refused_without_side_effects(tmp_path):
    h = Harness(tmp_path)  # default FakeProvider supports ORIGINAL only
    job = await h.service.create_and_submit(GenerationRequest(prompt="p"))
    job = await complete(h, job)
    v1 = h.repository.get_version(job.version_id)
    with pytest.raises(UnsupportedOperationError):
        await h.service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
    assert len(h.repository.list_versions(v1.song_id)) == 1


# -- HTTP API -----------------------------------------------------------------------------------


@pytest.fixture
def client(h):
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = h.service
    return TestClient(app)


def test_api_extract_creates_a_new_version_with_the_extracted_track_field(client, h):
    v1 = api_source(client, h)
    queue_result(h, b"VOX" * 300, 20.0)
    extract = client.post(op_url(v1, "extract"), json={"track_name": "vocals"}).json()
    assert extract["version_number"] == 2

    versions = client.get(f"/api/songs/{v1['song_id']}").json()["versions"]
    by_number = {v["version_number"]: v for v in versions}
    assert by_number[2]["operation"] == "EXTRACT"
    assert by_number[2]["extracted_track"] == "vocals"
    assert by_number[1]["extracted_track"] is None  # only the EXTRACT version carries this


def test_api_extract_rejects_an_unsupported_track_type(client, h):
    v1 = api_source(client, h)
    r = client.post(op_url(v1, "extract"), json={"track_name": "banjo"})
    assert r.status_code == 422
    assert len(client.get(f"/api/songs/{v1['song_id']}").json()["versions"]) == 1


def test_api_extract_rejects_missing_track_name(client, h):
    v1 = api_source(client, h)
    assert client.post(op_url(v1, "extract"), json={}).status_code == 422


def test_api_extract_rejects_cross_song_version(client, h):
    v1 = api_source(client, h)
    other = api_source(client, h)
    r = client.post(f"/api/songs/{v1['song_id']}/versions/{other['version_id']}/extract", json={"track_name": "vocals"})
    assert r.status_code == 404


def test_api_extract_response_never_leaks_provider_or_path_details(client, h):
    v1 = api_source(client, h)
    queue_result(h, b"VOX" * 100, 20.0)
    r = client.post(op_url(v1, "extract"), json={"track_name": "vocals"})
    text = r.text + client.get(f"/api/songs/{v1['song_id']}").text
    for leaked in (str(h.tmp_path), "source_audio_path", "absolute_path", ACE_ID, "/v1/audio", "acestep-v15-base"):
        assert leaked not in text, leaked


# -- provider mapping (ACE-Step) -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_step_maps_extract_to_the_base_model_with_batch_size_one(tmp_path):
    provider = AceStepMusicGenerationProvider(base_url="http://127.0.0.1:8001")
    with respx.mock(base_url="http://127.0.0.1:8001") as mock:
        route = mock.post("/release_task").mock(return_value=httpx.Response(200, json=wrap({"task_id": "t1"})))
        await provider.generate(ace_request(tmp_path, operation="EXTRACT", track_name="vocals"))
    body = route.calls.last.request.content
    assert b"ID3-SOURCE-BYTES" in body and b'name="src_audio"' in body
    for key, value in {
        "task_type": "extract", "track_name": "vocals", "model": "acestep-v15-base", "batch_size": "1",
    }.items():
        assert f'name="{key}"\r\n\r\n{value}\r\n'.encode() in body, key


def test_ace_step_extract_needs_a_track_name():
    from app.providers.errors import ProviderResponseError

    with pytest.raises(ProviderResponseError):
        AceStepMusicGenerationProvider._operation_fields(  # noqa: SLF001 -- exercising the mapping directly
            GenerationRequest(prompt="p", operation="EXTRACT", source_audio_path="/x")
        )
