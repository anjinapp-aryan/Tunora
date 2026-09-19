"""Step 13 restart/persistence test: a generated artifact's job record and
its physical file must both survive a simulated FastAPI process restart
(fresh JobRepository AND fresh AudioStorage instances over the same files).
"""

from __future__ import annotations

import pytest

from app.jobs.models import JobStatus
from app.jobs.repository import SqliteJobRepository
from app.jobs.service import JobService
from app.providers.base import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus, JobState
from app.storage.local import LocalAudioStorage
from tests.jobs.fakes import FakeProvider


@pytest.mark.asyncio
async def test_job_and_artifact_survive_simulated_restart(tmp_path):
    db_path = tmp_path / "tunora.db"
    storage_root = tmp_path / "audio-storage"
    source_file = tmp_path / "ace-step-output.mp3"
    source_file.write_bytes(b"generated-audio-bytes")

    provider = FakeProvider()
    provider.generate_response = GenerationJob(job_id="ace-task", provider="ace-step", status=JobState.QUEUED)
    provider.status_responses = [GenerationStatus(job_id="ace-task", status=JobState.SUCCEEDED)]
    provider.result_response = GenerationResult(
        job_id="ace-task", audio_path=str(source_file), duration=8.0, metadata={}
    )

    repository_before = SqliteJobRepository(db_path)
    storage_before = LocalAudioStorage(storage_root)
    service_before = JobService(
        repository=repository_before, provider=provider, storage=storage_before, poll_interval_seconds=0.0
    )

    job = await service_before.create_and_submit(GenerationRequest(prompt="p"))
    job = await service_before.poll_once(job.id)
    assert job.status == JobStatus.COMPLETED
    audio_key = job.result["audio"]["key"]

    del repository_before, storage_before, service_before  # simulate process exit

    repository_after = SqliteJobRepository(db_path)
    storage_after = LocalAudioStorage(storage_root)

    restored_job = repository_after.get(job.id)
    assert restored_job is not None
    assert restored_job.status == JobStatus.COMPLETED
    assert restored_job.result["audio"]["key"] == audio_key

    resolved_path = storage_after.get_path(audio_key)
    assert resolved_path.is_file()
    assert resolved_path.read_bytes() == b"generated-audio-bytes"
