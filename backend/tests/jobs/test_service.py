"""JobService unit tests — a FakeProvider stands in for ACE-Step, so these
never touch the network or the GPU. Real end-to-end coverage lives in
tests/test_job_lifecycle_smoke.py.
"""

from __future__ import annotations

import pytest

from app.jobs.errors import JobNotFoundError
from app.jobs.models import JobStatus
from app.jobs.repository import InMemoryJobRepository
from app.jobs.service import JobService
from app.providers.base import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    JobState,
)
from app.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.jobs.fakes import FakeAudioStorage, FakeProvider


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def storage():
    return FakeAudioStorage()


@pytest.fixture
def repository():
    return InMemoryJobRepository()


@pytest.fixture
def service(repository, provider, storage):
    return JobService(repository=repository, provider=provider, storage=storage, poll_interval_seconds=0.0)


@pytest.mark.asyncio
async def test_create_and_submit_moves_created_to_submitted_and_persists(service, provider, repository):
    provider.generate_response = GenerationJob(job_id="ace-task-1", provider="ace-step", status=JobState.QUEUED)

    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    assert job.status == JobStatus.SUBMITTED
    assert job.submitted_at is not None
    persisted = repository.get(job.id)
    assert persisted is not None
    assert persisted.status == JobStatus.SUBMITTED


@pytest.mark.asyncio
async def test_provider_job_id_is_stored_separately_from_tunora_job_id(service, provider):
    provider.generate_response = GenerationJob(job_id="ace-task-xyz", provider="ace-step", status=JobState.QUEUED)

    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    assert job.provider_job_id == "ace-task-xyz"
    assert job.id != job.provider_job_id
    assert job.id.startswith("tunora-")


@pytest.mark.asyncio
async def test_create_and_submit_marks_failed_when_provider_unavailable(service, provider, repository):
    provider.generate_response = ProviderUnavailableError("connection refused")

    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    assert job.status == JobStatus.FAILED
    assert "connection refused" in job.error
    assert repository.get(job.id).status == JobStatus.FAILED


@pytest.mark.asyncio
async def test_poll_once_queued(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.QUEUED)]
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_poll_once_running_after_queued(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.QUEUED)]
    await service.poll_once(job.id)
    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.RUNNING, progress=0.5)]
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.RUNNING
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_poll_once_completed_stores_result(service, provider, storage):
    from app.storage.base import StoredAudio

    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.SUCCEEDED)]
    provider.result_response = GenerationResult(
        job_id="t1", audio_path="/tmp/ace-step-output/song.mp3", duration=30.0, metadata={"bpm": 120}
    )
    storage.save_response = StoredAudio(
        key=f"{job.id}/{job.id}.mp3",
        absolute_path=f"/tunora-storage/{job.id}/{job.id}.mp3",
        filename=f"{job.id}.mp3",
        media_type="audio/mpeg",
        size_bytes=999,
    )
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.COMPLETED
    assert updated.completed_at is not None
    assert updated.result["duration"] == 30.0
    assert updated.result["metadata"] == {"bpm": 120}
    assert updated.result["audio"]["key"] == f"{job.id}/{job.id}.mp3"
    assert updated.result["audio"]["size_bytes"] == 999
    # The provider's own temporary path must never appear as the persisted result.
    assert "/tmp/ace-step-output" not in str(updated.result)
    # Storage must be asked to persist exactly the provider's returned audio_path.
    assert storage.save_calls == [("/tmp/ace-step-output/song.mp3", job.id, "audio/mpeg")]


@pytest.mark.asyncio
async def test_provider_transport_metadata_is_stripped_from_persisted_result(service, provider, storage):
    """AceStepMusicGenerationProvider.get_result() adds audio_url/audio_paths
    pointing at ACE-Step's own /v1/audio route into GenerationResult.metadata
    (see app/providers/ace_step.py). Once Tunora owns storage, those must not
    leak into the persisted (and therefore public API) job result."""

    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.SUCCEEDED)]
    provider.result_response = GenerationResult(
        job_id="t1",
        audio_path="/tmp/song.mp3",
        duration=10.0,
        metadata={
            "audio_url": "http://127.0.0.1:8001/v1/audio?path=/tmp/song.mp3",
            "audio_paths": ["/tmp/song.mp3"],
            "bpm": 120,
            "prompt": "p",
        },
    )
    updated = await service.poll_once(job.id)

    assert "audio_url" not in updated.result["metadata"]
    assert "audio_paths" not in updated.result["metadata"]
    assert updated.result["metadata"] == {"bpm": 120, "prompt": "p"}


@pytest.mark.asyncio
async def test_poll_once_failed_from_running(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.RUNNING)]
    await service.poll_once(job.id)
    provider.status_responses = [
        GenerationStatus(job_id="t1", status=JobState.FAILED, message="CUDA OOM")
    ]
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.FAILED
    assert updated.error == "CUDA OOM"
    assert updated.failed_at is not None


@pytest.mark.asyncio
async def test_poll_once_provider_error_marks_job_failed(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [ProviderUnavailableError("server down")]
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.FAILED
    assert "server down" in updated.error


@pytest.mark.asyncio
async def test_poll_once_get_result_failure_marks_job_failed(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.SUCCEEDED)]
    provider.result_response = ProviderResponseError("malformed result")
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.FAILED
    assert "malformed result" in updated.error


@pytest.mark.asyncio
async def test_poll_once_unknown_job_raises_not_found(service):
    with pytest.raises(JobNotFoundError):
        await service.poll_once("does-not-exist")


def test_get_unknown_job_raises_not_found(service):
    with pytest.raises(JobNotFoundError):
        service.get("does-not-exist")


@pytest.mark.asyncio
async def test_poll_once_is_noop_once_terminal(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))
    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.FAILED, message="boom")]
    await service.poll_once(job.id)

    # No further status_responses queued -- if poll_once called the provider
    # again this would raise IndexError, proving it short-circuits on terminal jobs.
    updated = await service.poll_once(job.id)
    assert updated.status == JobStatus.FAILED


@pytest.mark.asyncio
async def test_backwards_provider_transition_fails_job_instead_of_crashing(service, provider):
    """RUNNING -> QUEUED is not a valid Tunora transition; JobService must
    convert that into a clean FAILED job rather than letting the
    InvalidTransitionError escape the polling loop."""

    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))
    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.RUNNING)]
    await service.poll_once(job.id)

    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.QUEUED)]
    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.FAILED
    assert "Invalid state" in updated.error


@pytest.mark.asyncio
async def test_run_until_terminal_polls_until_completed(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [
        GenerationStatus(job_id="t1", status=JobState.QUEUED),
        GenerationStatus(job_id="t1", status=JobState.RUNNING),
        GenerationStatus(job_id="t1", status=JobState.SUCCEEDED),
    ]
    provider.result_response = GenerationResult(job_id="t1", audio_path="/x.mp3", duration=5.0, metadata={})

    final = await service.run_until_terminal(job.id)

    assert final.status == JobStatus.COMPLETED
    assert len(provider.status_calls) == 3


@pytest.mark.asyncio
async def test_run_until_terminal_times_out_marks_failed(repository, provider, storage):
    service = JobService(
        repository=repository, provider=provider, storage=storage, poll_interval_seconds=0.0, max_poll_seconds=0.0
    )
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))
    provider.status_responses = [GenerationStatus(job_id="t1", status=JobState.QUEUED)]

    final = await service.run_until_terminal(job.id)

    assert final.status == JobStatus.FAILED
    assert "Timed out" in final.error


@pytest.mark.asyncio
async def test_multiple_jobs_are_tracked_independently(service, provider):
    provider.generate_response = GenerationJob(job_id="t1", provider="ace-step", status=JobState.QUEUED)
    job1 = await service.create_and_submit(GenerationRequest(prompt="song one"))
    provider.generate_response = GenerationJob(job_id="t2", provider="ace-step", status=JobState.QUEUED)
    job2 = await service.create_and_submit(GenerationRequest(prompt="song two"))

    assert job1.id != job2.id
    assert job1.provider_job_id != job2.provider_job_id
    assert {j.id for j in service.list()} == {job1.id, job2.id}
