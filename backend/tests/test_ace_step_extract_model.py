"""Phase 14: Extract runs on the required base model, or the job fails visibly.

ACE-Step silently falls back to its primary (turbo) handler when the requested model is not
loaded; the result item's `dit_model` is the authoritative record of what actually ran. These
tests cover the provider check and the whole path through JobService (a rejected result never
becomes a Version's audio or a saved file).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_jobs import router as jobs_router
from app.api.routes_songs import router as songs_router
from app.jobs.models import JobStatus
from app.jobs.service import JobService
from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationRequest
from app.providers.errors import ProviderResponseError
from tests.songs.test_operations import ace_request, first_version
from tests.songs.test_service_versions import Harness

BASE_URL = "http://127.0.0.1:8001"


def _wrap(data):
    return {"data": data, "code": 200, "error": None, "timestamp": 0, "extra": None}


def _result(task_id: str, path: str, **first_item):
    item = {"file": f"/v1/audio?path={path}", "status": 1, "stage": "succeeded", "metas": {}, **first_item}
    return _wrap([{"task_id": task_id, "result": json.dumps([item]), "status": 1}])


async def _extract_submitted(mock, provider, tmp_path, task_id="task-x"):
    mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": task_id})))
    return await provider.generate(ace_request(tmp_path, operation="EXTRACT", track_name="vocals"))


@pytest.fixture
def provider():
    return AceStepMusicGenerationProvider(base_url=BASE_URL)


@pytest.mark.asyncio
async def test_extract_result_from_the_base_model_is_accepted(provider, tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        await _extract_submitted(mock, provider, tmp_path)
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result("task-x", "/a/b.mp3", dit_model="acestep-v15-base"))
        )
        result = await provider.get_result("task-x")
    assert result.audio_path == "/a/b.mp3"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [{"dit_model": "acestep-v15-turbo"}, {"dit_model": ""}, {"dit_model": None}, {}, {"dit_model": "acestep-v15-base-x"}],
)
async def test_extract_result_from_any_other_model_or_without_a_model_is_rejected(provider, tmp_path, fields):
    with respx.mock(base_url=BASE_URL) as mock:
        await _extract_submitted(mock, provider, tmp_path)
        mock.post("/query_result").mock(return_value=httpx.Response(200, json=_result("task-x", "/a/b.mp3", **fields)))
        with pytest.raises(ProviderResponseError, match="required model"):
            await provider.get_result("task-x")


@pytest.mark.asyncio
async def test_other_operations_are_not_checked_against_the_extract_model(provider, tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": "t1"})))
        await provider.generate(GenerationRequest(prompt="p"))  # ORIGINAL
        await provider.generate(ace_request(tmp_path, operation="REMIX", source_duration=10.0))
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result("t1", "/a/b.mp3", dit_model="acestep-v15-turbo"))
        )
        assert (await provider.get_result("t1")).audio_path == "/a/b.mp3"


@pytest.mark.asyncio
async def test_the_expectation_is_removed_once_the_result_is_read(provider, tmp_path):
    with respx.mock(base_url=BASE_URL) as mock:
        await _extract_submitted(mock, provider, tmp_path, "task-x")
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result("task-x", "/a/b.mp3", dit_model="acestep-v15-base"))
        )
        await provider.get_result("task-x")
    assert provider._expected_models == {}  # noqa: SLF001 -- nothing accumulates


@pytest.mark.asyncio
async def test_the_expectation_map_is_bounded(provider, tmp_path):
    provider._EXPECTED_MODEL_LIMIT = 3  # noqa: SLF001
    with respx.mock(base_url=BASE_URL) as mock:
        for i in range(6):
            await _extract_submitted(mock, provider, tmp_path, f"task-{i}")
    assert list(provider._expected_models) == ["task-3", "task-4", "task-5"]  # noqa: SLF001


# -- through JobService: a rejected result never becomes a Version's audio -----------------------


def _real_service(h):
    provider = AceStepMusicGenerationProvider(base_url=BASE_URL)
    return JobService(repository=h.repository, provider=provider, storage=h.storage, poll_interval_seconds=0.0)


@pytest.mark.asyncio
async def test_a_wrong_model_extract_fails_the_job_and_saves_no_audio(tmp_path):
    h = Harness(tmp_path)
    _, v1 = await first_version(h)
    service = _real_service(h)
    produced = tmp_path / "produced.mp3"
    produced.write_bytes(b"TURBO-OUTPUT")

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": "task-x"})))
        job = await service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result("task-x", str(produced), dit_model="acestep-v15-turbo"))
        )
        job = await service.poll_once(job.id)

    assert job.status is JobStatus.FAILED
    version = h.repository.get_version(job.version_id)
    assert version.audio is None and version.operation == "EXTRACT"
    assert h.repository.get_version(v1.id) == v1  # the source is untouched
    assert not list((tmp_path / "audio").glob(f"{job.id}*"))  # nothing stored for the failed job


@pytest.mark.asyncio
async def test_a_base_model_extract_completes_through_the_service(tmp_path):
    h = Harness(tmp_path)
    _, v1 = await first_version(h)
    service = _real_service(h)
    produced = tmp_path / "produced.mp3"
    produced.write_bytes(b"BASE-OUTPUT")

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": "task-x"})))
        job = await service.create_version_from_operation(v1.song_id, v1.id, "EXTRACT", track_name="vocals")
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result("task-x", str(produced), dit_model="acestep-v15-base"))
        )
        job = await service.poll_once(job.id)

    assert job.status is JobStatus.COMPLETED
    assert h.repository.get_version(job.version_id).audio is not None


@pytest.mark.asyncio
async def test_the_public_api_hides_the_model_details_of_a_rejected_extract(tmp_path):
    h = Harness(tmp_path)
    _, v1 = await first_version(h)
    app = FastAPI()
    app.include_router(jobs_router)
    app.include_router(songs_router)
    app.state.job_service = _real_service(h)
    produced = tmp_path / "produced.mp3"
    produced.write_bytes(b"TURBO-OUTPUT")

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"task_id": "task-x"})))
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_result("task-x", str(produced), dit_model="acestep-v15-turbo"))
        )
        with TestClient(app) as client:
            created = client.post(
                f"/api/songs/{v1.song_id}/versions/{v1.id}/extract", json={"track_name": "vocals"}
            ).json()
            body = client.get(f"/api/jobs/{created['id']}").json()
            details = client.get(f"/api/songs/{v1.song_id}").text

    assert body["status"] == "FAILED" and body["result"] is None
    for text in (json.dumps(body), details):
        for leaked in ("acestep-v15", "dit_model", "required model", str(tmp_path)):
            assert leaked not in text, leaked
