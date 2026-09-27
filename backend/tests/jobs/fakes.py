"""A scriptable fake MusicGenerationProvider for job-lifecycle unit tests.

No HTTP, no GPU — pure in-memory doubles so JobService tests never depend on
ACE-Step or the network. Real end-to-end behavior is covered separately by
tests/test_job_lifecycle_smoke.py.
"""

from __future__ import annotations

from typing import Union

from pathlib import Path

from app.providers.base import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    MusicGenerationProvider,
)
from app.storage.base import AudioStorage, StoredAudio


class FakeProvider(MusicGenerationProvider):
    name = "fake"

    def __init__(self) -> None:
        self.generate_response: Union[GenerationJob, Exception, None] = None
        self.status_responses: list[Union[GenerationStatus, Exception]] = []
        self.result_response: Union[GenerationResult, Exception, None] = None
        self.generate_calls: list[GenerationRequest] = []
        self.status_calls: list[str] = []
        self.result_calls: list[str] = []

    async def generate(self, request: GenerationRequest) -> GenerationJob:
        self.generate_calls.append(request)
        if isinstance(self.generate_response, Exception):
            raise self.generate_response
        assert self.generate_response is not None, "test must set generate_response"
        return self.generate_response

    async def get_status(self, job_id: str) -> GenerationStatus:
        self.status_calls.append(job_id)
        item = self.status_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get_result(self, job_id: str) -> GenerationResult:
        self.result_calls.append(job_id)
        if isinstance(self.result_response, Exception):
            raise self.result_response
        assert self.result_response is not None, "test must set result_response"
        return self.result_response


class FakeAudioStorage(AudioStorage):
    """A no-op AudioStorage double for JobService tests that don't care
    about storage specifics -- see tests/storage/ for real LocalAudioStorage
    coverage, and tests/jobs/test_service_storage_integration.py for
    JobService wired to the real LocalAudioStorage.
    """

    def __init__(self) -> None:
        self.save_response: "StoredAudio | Exception | None" = None
        self.save_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[str] = []
        self.delete_response: "Exception | None" = None

    def save(self, source_path, *, job_id: str, media_type: str) -> StoredAudio:
        self.save_calls.append((str(source_path), job_id, media_type))
        if isinstance(self.save_response, Exception):
            raise self.save_response
        if self.save_response is not None:
            return self.save_response
        return StoredAudio(
            key=f"{job_id}/{job_id}.mp3",
            absolute_path=f"/fake-storage/{job_id}/{job_id}.mp3",
            filename=f"{job_id}.mp3",
            media_type=media_type,
            size_bytes=1234,
        )

    def get_path(self, key: str) -> Path:
        return Path("/fake-storage") / key

    def exists(self, key: str) -> bool:
        return True

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        if self.delete_response is not None:
            raise self.delete_response
