"""JobService wired to the REAL LocalAudioStorage (still with a FakeProvider
-- no network/GPU). Confirms the storage integration end-to-end at the
service level, distinct from tests/storage/ (storage in isolation) and
tests/jobs/test_service.py (lifecycle in isolation with FakeAudioStorage).
"""

from __future__ import annotations

import pytest

from app.jobs.models import JobStatus
from app.jobs.repository import InMemoryJobRepository
from app.jobs.service import JobService
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.storage.errors import StorageWriteError
from app.storage.local import LocalAudioStorage
from tests.jobs.fakes import FakeProvider


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def ace_step_output_dir(tmp_path):
    d = tmp_path / "ace-step-temp-output"
    d.mkdir()
    return d


@pytest.fixture
def storage(tmp_path):
    return LocalAudioStorage(tmp_path / "tunora-storage")


@pytest.fixture
def service(provider, storage):
    return JobService(
        repository=InMemoryJobRepository(), provider=provider, storage=storage, poll_interval_seconds=0.0
    )


async def _run_to_completion(service, provider, source_path: str) -> object:
    provider.generate_response = GenerationJob(job_id="ace-task", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))
    provider.status_responses = [GenerationStatus(job_id="ace-task", status=JobState.SUCCEEDED)]
    provider.result_response = GenerationResult(
        job_id="ace-task", audio_path=source_path, duration=12.5, metadata={"bpm": 100}
    )
    return await service.poll_once(job.id)


@pytest.mark.asyncio
async def test_successful_generation_is_persisted_into_tunora_storage(service, provider, storage, ace_step_output_dir):
    source_file = ace_step_output_dir / "8741640e-abc-temp.mp3"
    source_file.write_bytes(b"real-ish-audio-bytes")

    job = await _run_to_completion(service, provider, str(source_file))

    assert job.status == JobStatus.COMPLETED
    assert job.result["audio"]["key"] == f"{job.id}/{job.id}.mp3"
    resolved = storage.get_path(job.result["audio"]["key"])
    assert resolved.is_file()
    assert resolved.read_bytes() == b"real-ish-audio-bytes"


@pytest.mark.asyncio
async def test_provider_temp_path_not_leaked_into_job_result(service, provider, ace_step_output_dir):
    source_file = ace_step_output_dir / "8741640e-abc-temp.mp3"
    source_file.write_bytes(b"data")

    job = await _run_to_completion(service, provider, str(source_file))

    assert str(ace_step_output_dir) not in str(job.result)
    assert job.result["audio"]["absolute_path"] != str(source_file)


@pytest.mark.asyncio
async def test_storage_failure_marks_job_failed_not_completed(service, provider):
    job_setup = GenerationJob(job_id="ace-task", provider="ace-step", status=JobState.QUEUED)
    provider.generate_response = job_setup
    job = await service.create_and_submit(GenerationRequest(prompt="p"))

    provider.status_responses = [GenerationStatus(job_id="ace-task", status=JobState.SUCCEEDED)]
    # A source path that does not exist -> LocalAudioStorage raises SourceArtifactMissingError.
    provider.result_response = GenerationResult(
        job_id="ace-task", audio_path="/does/not/exist.mp3", duration=1.0, metadata={}
    )

    updated = await service.poll_once(job.id)

    assert updated.status == JobStatus.FAILED
    assert "Failed to store generated audio" in updated.error
    assert updated.result is None


@pytest.mark.asyncio
async def test_no_partial_artifact_reported_as_completed_on_storage_write_error(
    service, provider, storage, ace_step_output_dir, monkeypatch
):
    source_file = ace_step_output_dir / "temp.mp3"
    source_file.write_bytes(b"data")

    def _boom(*args, **kwargs):
        raise StorageWriteError("simulated disk failure")

    monkeypatch.setattr(storage, "save", _boom)

    job = await _run_to_completion(service, provider, str(source_file))

    assert job.status == JobStatus.FAILED
    assert job.result is None


@pytest.mark.asyncio
async def test_existing_step_12_transitions_still_work_with_storage_wired_in(service, provider):
    """Guards against a Step 13 regression of Step 12's own state machine."""

    provider.generate_response = GenerationJob(job_id="ace-task", provider="ace-step", status=JobState.QUEUED)
    job = await service.create_and_submit(GenerationRequest(prompt="p"))
    assert job.status == JobStatus.SUBMITTED

    provider.status_responses = [GenerationStatus(job_id="ace-task", status=JobState.QUEUED)]
    updated = await service.poll_once(job.id)
    assert updated.status == JobStatus.QUEUED

    provider.status_responses = [GenerationStatus(job_id="ace-task", status=JobState.RUNNING)]
    updated = await service.poll_once(job.id)
    assert updated.status == JobStatus.RUNNING
