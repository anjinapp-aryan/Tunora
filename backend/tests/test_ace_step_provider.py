"""Unit tests for AceStepMusicGenerationProvider against mocked HTTP responses.

No network access and no ACE-Step server required — respx intercepts httpx
calls at the transport level. See test_ace_step_smoke.py for the real,
end-to-end test against a running local ACE-Step server.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.providers.ace_step import AceStepMusicGenerationProvider
from app.providers.base import GenerationRequest, JobState
from app.providers.errors import (
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

BASE_URL = "http://127.0.0.1:8001"


def _wrap(data, code=200, error=None):
    return {"data": data, "code": code, "error": error, "timestamp": 0, "extra": None}


def _query_result_item(status: int, stage: str, **extra_first_item_fields):
    first_item = {"file": "", "status": status, "stage": stage, "progress": 0.0, **extra_first_item_fields}
    return {"task_id": "task-123", "result": json.dumps([first_item]), "status": status}


@pytest.fixture
def provider():
    return AceStepMusicGenerationProvider(base_url=BASE_URL)


@pytest.mark.asyncio
async def test_generate_submits_and_extracts_task_id(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(
            return_value=httpx.Response(
                200, json=_wrap({"task_id": "task-123", "status": "queued", "queue_position": 1})
            )
        )
        job = await provider.generate(GenerationRequest(prompt="uplifting pop song"))

    assert job.job_id == "task-123"
    assert job.provider == "ace-step"
    assert job.status == JobState.QUEUED


@pytest.mark.asyncio
async def test_generate_maps_request_fields_onto_release_task_payload(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post("/release_task").mock(
            return_value=httpx.Response(200, json=_wrap({"task_id": "t1"}))
        )
        await provider.generate(
            GenerationRequest(
                prompt="p", lyrics="la la", language="kn", duration=30.0, seed=42, batch_size=2
            )
        )

    sent = json.loads(route.calls.last.request.content)
    assert sent["prompt"] == "p"
    assert sent["lyrics"] == "la la"
    assert sent["vocal_language"] == "kn"
    assert sent["audio_duration"] == 30.0
    assert sent["seed"] == 42
    assert sent["use_random_seed"] is False
    assert sent["batch_size"] == 2


@pytest.mark.asyncio
async def test_generate_instrumental_forces_empty_lyrics(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.post("/release_task").mock(
            return_value=httpx.Response(200, json=_wrap({"task_id": "t1"}))
        )
        await provider.generate(GenerationRequest(prompt="p", lyrics="ignored", instrumental=True))

    sent = json.loads(route.calls.last.request.content)
    assert sent["lyrics"] == ""


@pytest.mark.asyncio
async def test_get_status_queued(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_wrap([_query_result_item(0, "queued")]))
        )
        status = await provider.get_status("task-123")

    assert status.status == JobState.QUEUED


@pytest.mark.asyncio
async def test_get_status_running(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(
                200, json=_wrap([_query_result_item(0, "running", progress=0.4)])
            )
        )
        status = await provider.get_status("task-123")

    assert status.status == JobState.RUNNING
    assert status.progress == 0.4


@pytest.mark.asyncio
async def test_get_status_failed(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(
                200, json=_wrap([_query_result_item(2, "failed", error="CUDA OOM")])
            )
        )
        status = await provider.get_status("task-123")

    assert status.status == JobState.FAILED
    assert status.message == "CUDA OOM"


@pytest.mark.asyncio
async def test_get_result_succeeded_maps_audio_and_metadata(provider):
    # Confirmed via a real local run: ACE-Step's "file" field is already a
    # `/v1/audio?path=<url-encoded absolute path>` route string, not a raw
    # filesystem path — see AceStepMusicGenerationProvider's module docstring.
    file_field = "/v1/audio?path=I%3A%5Coutput%5Csong.mp3"
    succeeded_item = {
        "file": file_field,
        "status": 1,
        "stage": "succeeded",
        "prompt": "uplifting pop song",
        "lyrics": "la la",
        "metas": {"bpm": 120, "duration": 30.5, "genres": "pop", "keyscale": "C major", "timesignature": "4/4"},
    }
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(
                200,
                json=_wrap([{"task_id": "task-123", "status": 1, "result": json.dumps([succeeded_item])}]),
            )
        )
        result = await provider.get_result("task-123")

    assert result.audio_path == "I:\\output\\song.mp3"
    assert result.duration == 30.5
    assert result.metadata["bpm"] == 120
    assert result.metadata["audio_url"] == f"{BASE_URL}{file_field}"


@pytest.mark.asyncio
async def test_get_result_raises_on_failed_job(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(
                200, json=_wrap([_query_result_item(2, "failed", error="model load error")])
            )
        )
        with pytest.raises(ProviderResponseError, match="model load error"):
            await provider.get_result("task-123")


@pytest.mark.asyncio
async def test_get_result_raises_when_job_not_finished(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/query_result").mock(
            return_value=httpx.Response(200, json=_wrap([_query_result_item(0, "running")]))
        )
        with pytest.raises(ProviderResponseError, match="not finished"):
            await provider.get_result("task-123")


@pytest.mark.asyncio
async def test_request_timeout_raises_provider_timeout_error(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(side_effect=httpx.ReadTimeout("timed out"))
        with pytest.raises(ProviderTimeoutError):
            await provider.generate(GenerationRequest(prompt="p"))


@pytest.mark.asyncio
async def test_connection_error_raises_provider_unavailable_error(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(side_effect=httpx.ConnectError("connection refused"))
        with pytest.raises(ProviderUnavailableError):
            await provider.generate(GenerationRequest(prompt="p"))


@pytest.mark.asyncio
async def test_malformed_json_response_raises_provider_response_error(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(
            return_value=httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})
        )
        with pytest.raises(ProviderResponseError):
            await provider.generate(GenerationRequest(prompt="p"))


@pytest.mark.asyncio
async def test_response_missing_data_envelope_raises_provider_response_error(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))
        with pytest.raises(ProviderResponseError):
            await provider.generate(GenerationRequest(prompt="p"))


@pytest.mark.asyncio
async def test_response_missing_task_id_raises_provider_response_error(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(200, json=_wrap({"status": "queued"})))
        with pytest.raises(ProviderResponseError, match="task_id"):
            await provider.generate(GenerationRequest(prompt="p"))


@pytest.mark.asyncio
async def test_server_error_raises_provider_unavailable_error(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/release_task").mock(return_value=httpx.Response(503, text="Service Unavailable"))
        with pytest.raises(ProviderUnavailableError):
            await provider.generate(GenerationRequest(prompt="p"))


@pytest.mark.asyncio
async def test_health_check_true_when_ok(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/health").mock(return_value=httpx.Response(200, json=_wrap({"status": "ok"})))
        assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_health_check_false_when_unreachable(provider):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/health").mock(side_effect=httpx.ConnectError("refused"))
        assert await provider.is_available() is False
